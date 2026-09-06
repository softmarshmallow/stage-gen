"""Deterministic gates. Every threshold here is refusal-bearing.

The division of labour is the repository's usual one: a gate here refuses what
can be measured, and a judge is asked only what cannot be. So this file refuses
opaque returns, cropped canvases, merged strip cells, vignetted ground, hard-cut
decals and a flame cycle that does not close; it says nothing about whether the
art is any good, and nothing about pictorial pitch, which no measurement of a
single flat picture can recover.

Two gates carry findings rather than refusals. ``floor_plate_suspected`` is
advisory because a low wide base is sometimes the object (a firepit's stone
ring) and sometimes the defect (a tree standing on a painted disc of soil), and
only a reviewer can tell which. The flame-cycle closure gate refuses, but its
recorded fallback is ping-pong playback rather than a failed run.

Pure PIL plus the repository's own media helpers. No numpy.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from io import BytesIO
from typing import Final, Protocol, cast

from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat

from stage_gen.media.guide_lattice import (
    GuideLattice,
    detect_guide_lattice,
    extract_guided_cells,
)
from stage_gen.media.loop_construction import mirror_repeat
from stage_gen.media.sprite_sheets import (
    AlphaComponentRepackContract,
    measure_alpha_ground_contact,
    measure_alpha_subjects,
    repack_alpha_components,
)


class _BandAccess(Protocol):
    """One single-band image's pixels.

    Pillow types ``Image.load()`` as a union over every band count and every
    pixel depth. A mask, a luma plane and an alpha channel each have exactly one
    band, so the narrowing is stated once here rather than at each of a dozen
    call sites.
    """

    def __getitem__(self, xy: tuple[int, int]) -> int: ...


def _band(image: Image.Image) -> _BandAccess:
    return cast(_BandAccess, image.load())


def _extrema(band: Image.Image) -> tuple[int, int]:
    """One single-band image's darkest and brightest value."""

    return cast("tuple[int, int]", band.getextrema())


ALPHA_THRESHOLD: Final = 16
#: Border alpha this high means the subject runs off the canvas, or the provider
#: returned a full-bleed picture instead of a cutout.
BORDER_ALPHA_MAX: Final = 16
BORDER_ALPHA_MEAN_MAX: Final = 0.5
VISIBLE_FRACTION_MIN: Final = 0.01
#: Clear space under the feet, so the runtime's foot row is the object's own.
BOTTOM_PADDING_MIN_PX: Final = 8
#: An object whose lowest paint is above this sits in the air on its own card.
GROUND_CONTACT_MIN: Final = 0.55
#: A base band this many times wider than the band just above it, this solidly
#: filled, is probably a painted floor plate. Advisory, surfaced to the reviewer.
FLOOR_PLATE_WIDENING_MIN: Final = 1.6
FLOOR_PLATE_FILL_MIN: Final = 0.55
#: The band, as a share of subject height, that the footprint is measured over.
FOOTPRINT_BAND_SHARE: Final = 0.06
#: How far up the subject the floor-plate test looks for the object's own width.
FLOOR_PLATE_REFERENCE_HEIGHT: Final = 0.20
#: Per-cell painted share a strip cell must clear to count as drawn.
CELL_VISIBLE_MIN: Final = 0.005
#: Cross-cell figure-height spread. Tight for cycles, where the figure stays
#: upright; wide for actions, where a bend toward the camera honestly drops
#: the head by nearly half (wren's front gather: 39-46% across six attempts,
#: every one with its feet on the same line). Height alone cannot tell a bend
#: from a zoom; the feet line below can, so the action limit is loose and the
#: feet line is the re-framing detector.
CELL_HEIGHT_SPREAD_CYCLE: Final = 0.12
CELL_HEIGHT_SPREAD_ACTION: Final = 0.55
#: How far the figure's lowest painted row may move across cells, as a share
#: of the canvas height. A pose keeps its feet; a re-framed cell does not.
CELL_FEET_LINE_SPREAD: Final = 0.06
_CYCLE_STATES: Final = frozenset({"idle", "walk"})
#: Ground uniformity: per-block luma may deviate this far from the global mean.
GROUND_BLOCK_DEVIATION_MAX: Final = 0.12
GROUND_BLOCKS: Final = 4
#: Corner-to-centre luma ratio outside this band is a vignette.
GROUND_CORNER_RATIO: Final = (0.90, 1.10)
#: Playable value band. The prompt's mid-value clause measurably lifts a plate
#: (0.186 to 0.235 on the first A/B, with block deviation halved) but does not
#: reach the mid-value it asks for: a forest-floor subject under a muted-palette
#: style brief pulls the value down harder than the clause pulls it up. A floor
#: here refuses a plate the runtime would then darken again for canopy shade and
#: for night, and the refusal is retried inside the existing attempt budget.
# The ceiling was 0.74 while the viewer showed every plate gamma-dark (the
# custom shaders wrote linear light as sRGB until 2026-09-05); with the
# display honest and every plate levelled to its authored target, a pale
# scree at 0.76 is a usable plate. The floor stays: a dark plate cannot be
# lifted without banding.
GROUND_LUMA_RANGE: Final = (0.30, 0.84)
#: The viewer's play zoom, pixels per metre of ground. The busy-ness gate
#: judges the plate at this scale, because that is the only scale at which
#: anyone looks at it. prompts.py states the same number to the model.
PLAY_PX_PER_METER: Final = 70
#: Local contrast at play scale, as a share of the plate's mean value. Four
#: plates in minimal-v20 measured 0.054 (the meadow, the one that read as
#: ground) against 0.078, 0.095 and 0.097 (the three that read as noise).
#: The limit sits just above the plate that worked.
GROUND_BUSYNESS_MAX: Final = 0.062
#: A fabric plate is a drawn stroke in every square metre, and the reference's
#: turf, run through this same metric off the play shots (2026-09-06, pass
#: five, GROUND.md), measures 0.10 to 0.13; the field limit above would refuse
#: the reference itself. The forest floor and the scree, re-briefed as
#: fabrics, arrived at 0.12 and 0.09 and read as turf and stone at play zoom.
FABRIC_BUSYNESS_MAX: Final = 0.14
#: A fabric carries its value in its ink and arrives dark: the three woodland
#: turf draws landed at 0.19 to 0.27 under a brief that asked for mid-dark.
#: The consumer levels every plate to its authored target with a gain the
#: manifest clamps to [0.5, 2.5], so a plate at a fifth of white is a gain
#: of 1.8 toward a 0.36 target, not a dark ground; the field band's floor
#: (0.30) was written before the leveller existed.
FABRIC_LUMA_RANGE: Final = (0.20, 0.84)
#: Blur radius, in play pixels, that separates a mark from the ground under it.
GROUND_BUSYNESS_BLUR_PX: Final = 7
#: Water is a dark plane and is allowed to be one, short of black.
WATER_LUMA_RANGE: Final = (0.14, 0.60)
#: A weather cover plate (snow) is pale by definition: the ground band's
#: ceiling would refuse it, and a cover darker than the ground it hides is
#: not a cover.
COVER_LUMA_RANGE: Final = (0.55, 0.97)
#: Mirror repeat makes this exactly zero; the gate exists so that a future
#: seam-repaint path is measured by the same rule rather than a kinder one.
TILE_EDGE_DELTA_MAX: Final = 6.0 / 255.0
#: The macro plate is a colour field and must carry no drawing. FIND_EDGES on a
#: soft mottle averages a few thousandths; on an inked ground plate it is over
#: 0.05. The limit sits well below the drawn side.
MACRO_LUMA_RANGE: Final = (0.36, 0.68)
MACRO_EDGE_MEAN_MAX: Final = 0.02
MACRO_HALF_DEVIATION_MAX: Final = 0.22
#: A litter cutout fills a readable fraction of its cell, and nothing touches a
#: guide line: the inset is the empty margin required on every side of a cell.
CLUTTER_CELL_COVERAGE: Final = (0.02, 0.60)
#: A standing plant fills most of its cell's height and a good part of its
#: width; the litter's ceiling would refuse every waist-high one.
PLANT_CELL_COVERAGE: Final = (0.03, 0.85)
#: An inventory icon fills its cell more than a litter piece does: about two
#: thirds by the brief, and a plump glyph may run to three quarters.
ICON_CELL_COVERAGE: Final = (0.05, 0.75)
CLUTTER_CELL_INSET: Final = 0.03
#: A prop sheet's cells keep the sprite gate, with two floors lowered. The
#: sheet's point is one shared scale, so a knee-high stump beside a full pine
#: is a small thing mid-cell by design: about one percent of a 512-px cell,
#: with its base near the middle. The sprite floors (1% visible, base in the
#: lower 45%) exist to keep a lone sprite from wasting its canvas, and that
#: is not the question a sheet cell answers.
SHEET_CELL_INSET: Final = CLUTTER_CELL_INSET
#: A sheet is cut at the emptiest seam near each half line, not on the half
#: line itself, searched this far either side of it. The dead snag's four
#: looks came back eighteen times with the top row's roots a few pixels under
#: the canvas midline and the bottom row's tips a few pixels over it: clean
#: cutouts every time, severed every time by a cut the model could not see.
SHEET_SEAM_SEARCH_SHARE: Final = 0.15
SHEET_VISIBLE_FRACTION_MIN: Final = 0.002
SHEET_GROUND_CONTACT_MIN: Final = 0.30
#: A decal must feather. This share of its visible pixels must be partial alpha.
DECAL_SOFT_EDGE_SHARE_MIN: Final = 0.05
#: A ground patch must not be a disc. The silhouette's radius is sampled every
#: two degrees about its centroid and this is the floor on its coefficient of
#: variation: a circle measures 0.00, the v26 skirts 0.02 to 0.06 (and they
#: read as discs under every tree), a 1.3:1 ellipse 0.09, a lobed blot 0.16,
#: the elongated path pad 0.27.
DECAL_IRREGULARITY_MIN: Final = 0.12
DECAL_RADIUS_SAMPLES: Final = 180
#: Alpha at or above this is the body and is lifted to fully opaque: the
#: provider returns 254 for a flat fill and refusing that refuses every plate.
OPAQUE_LIFT_MIN: Final = 250
#: Alpha at or below this is exterior and is cleared in colour as well as alpha.
TRANSPARENT_CLEAR_MAX: Final = 8
#: How far the body's colour is pushed out under the soft rim.
ALPHA_BLEED_PASSES: Final = 2
ALPHA_BLEED_KERNEL_PX: Final = 5
#: Lattice geometry the flame strip must come back with.
LATTICE_RESIDUAL_MAX_PX: Final = 3.0
FLAME_CELL_COVERAGE: Final = (0.05, 0.85)
#: Consecutive-frame silhouette overlap. Below the floor is a jump cut; above
#: the ceiling is a duplicated frame.
FLAME_CONTINUITY_IOU: Final = (0.45, 0.98)
#: Flame base row drift across cells, as a share of cell height.
FLAME_BASE_DRIFT_MAX: Final = 0.10


class GateError(ValueError):
    """One or more refusals, reported together so a run learns everything at once."""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = list(reasons)
        super().__init__("; ".join(self.reasons))


# --- pixel helpers -------------------------------------------------------------------


def _open(data: bytes) -> Image.Image:
    with Image.open(BytesIO(data)) as opened:
        return opened.convert("RGBA")


def _mask(image: Image.Image, threshold: int = ALPHA_THRESHOLD) -> Image.Image:
    return image.getchannel("A").point(lambda value: 255 if value > threshold else 0)


def _luma(image: Image.Image) -> Image.Image:
    return image.convert("RGB").convert("L")


def _mean(image: Image.Image) -> float:
    histogram = image.histogram()
    total = sum(histogram)
    if not total:
        return 0.0
    return sum(index * count for index, count in enumerate(histogram)) / total / 255.0


def canonicalize_sprite_alpha(data: bytes) -> tuple[bytes, dict[str, object]]:
    """Lift the near-opaque body to full, bleed its colour outward, clear the rest.

    Three measured facts about what this provider returns, all from the first
    live run. The body tops out at **alpha 254, never 255** -- the dust module
    found the same thing, and refusing that would refuse every plate the provider
    can make. The exterior is *nearly* clear but its RGB is a dark olive (mean
    around 9 of 255), not zero. And the rim between the two is a soft
    antialiased band, one to two percent of the canvas.

    A hard alpha cutoff hides all of that. Alpha-to-coverage, which is what the
    soft-edge foliage uses, does not: it keeps the rim, and the rim's colour is
    that dark exterior, so grass and thorn would carry a dark fringe. So the
    body's colour is dilated outward under the rim first, and only then is the
    exterior cleared in both colour and alpha.

    The dilation is a max filter rather than a premultiplied blur-and-divide: on
    art masked to black it spreads the body outward by construction, it needs no
    division, and it runs in C instead of a three-million-pixel Python loop.
    """

    image = _open(data)
    alpha = image.getchannel("A")
    before = list(alpha.getextrema())
    rgb = image.convert("RGB")

    body = alpha.point(lambda value: 255 if value >= OPAQUE_LIFT_MIN else 0)
    masked = Image.composite(rgb, Image.new("RGB", image.size, (0, 0, 0)), body)
    dilated = masked
    for _ in range(ALPHA_BLEED_PASSES):
        dilated = dilated.filter(ImageFilter.MaxFilter(ALPHA_BLEED_KERNEL_PX))

    lifted = alpha.point(
        lambda value: (
            255 if value >= OPAQUE_LIFT_MIN else (0 if value <= TRANSPARENT_CLEAR_MAX else value)
        )
    )
    coloured = Image.composite(rgb, dilated, body)
    keep = lifted.point(lambda value: 255 if value > 0 else 0)
    result = Image.composite(
        Image.merge("RGBA", (*coloured.split(), lifted)),
        Image.new("RGBA", image.size, (0, 0, 0, 0)),
        keep,
    )

    buffer = BytesIO()
    result.save(buffer, format="PNG")
    histogram = lifted.histogram()
    pixels = float(image.width * image.height)
    return buffer.getvalue(), {
        "kind": "oblique-survival-sprite-alpha-v1",
        "source_alpha_extrema": before,
        "canonical_alpha_extrema": list(lifted.getextrema()),
        "opaque_share": round(histogram[255] / pixels, 5),
        "soft_rim_share": round(
            sum(histogram[TRANSPARENT_CLEAR_MAX + 1 : OPAQUE_LIFT_MIN]) / pixels, 5
        ),
        "bleed_passes": ALPHA_BLEED_PASSES,
        "bleed_kernel_px": ALPHA_BLEED_KERNEL_PX,
    }


def _iou(first: Image.Image, second: Image.Image) -> float:
    if first.size != second.size:
        second = second.resize(first.size, Image.Resampling.NEAREST)
    intersection = sum(ImageChops.darker(first, second).histogram()[255:])
    union = sum(ImageChops.lighter(first, second).histogram()[255:])
    return intersection / union if union else 0.0


# --- transparent canvases ------------------------------------------------------------


def gate_transparent_canvas(
    data: bytes, *, width: int, height: int, visible_fraction_min: float = VISIBLE_FRACTION_MIN
) -> dict[str, object]:
    """Port of the platformer's isolated-asset gate, unchanged in substance."""

    reasons: list[str] = []
    image = _open(data)
    if image.size != (width, height):
        reasons.append(f"canvas is {image.size[0]}x{image.size[1]}, expected {width}x{height}")
    alpha = image.getchannel("A")
    low, high = _extrema(alpha)
    if high <= ALPHA_THRESHOLD:
        reasons.append("nothing is painted")
    if low > 200:
        reasons.append("the canvas is opaque; the provider returned a picture, not a cutout")
    mask = _mask(image)
    box = mask.getbbox()
    visible = sum(mask.histogram()[255:]) / float(image.size[0] * image.size[1])
    if visible < visible_fraction_min:
        reasons.append(f"visible fraction {visible:.4f} is under {visible_fraction_min}")
    border_max, border_mean = _border_alpha(alpha)
    if border_max > BORDER_ALPHA_MAX:
        reasons.append(f"border alpha peaks at {border_max}; the subject runs off the canvas")
    if border_mean > BORDER_ALPHA_MEAN_MAX:
        reasons.append(f"border alpha mean {border_mean:.2f} suggests a full-bleed background")
    if reasons:
        raise GateError(reasons)
    return {
        "width": image.size[0],
        "height": image.size[1],
        "alpha_min": low,
        "alpha_max": high,
        "visible_fraction": round(visible, 5),
        "bbox": list(box) if box else None,
        "border_alpha_max": border_max,
        "border_alpha_mean": round(border_mean, 3),
    }


def _border_alpha(alpha: Image.Image) -> tuple[int, float]:
    width, height = alpha.size
    pixels = _band(alpha)
    values: list[int] = []
    for x in range(width):
        values.append(pixels[x, 0])
        values.append(pixels[x, height - 1])
    for y in range(height):
        values.append(pixels[0, y])
        values.append(pixels[width - 1, y])
    return max(values), sum(values) / len(values)


# --- props ---------------------------------------------------------------------------


def gate_prop(
    data: bytes,
    *,
    width: int,
    height: int,
    max_components: int,
    ground_contact_min: float = GROUND_CONTACT_MIN,
    visible_fraction_min: float = VISIBLE_FRACTION_MIN,
) -> dict[str, object]:
    """Alpha, component count, ground contact, footprint, floor-plate suspicion."""

    facts = gate_transparent_canvas(
        data, width=width, height=height, visible_fraction_min=visible_fraction_min
    )
    reasons: list[str] = []
    # The shared measurement raises rather than returning zero when the paint is
    # all specks, which is itself the refusal we want to report in our own words.
    try:
        subjects: dict[str, object] = dict(measure_alpha_subjects(data))
    except ValueError as error:
        raise GateError([f"no component is large enough to be the subject: {error}"]) from error
    count = int(cast(int, subjects.get("subject_count", 0) or 0))
    if count > max_components:
        reasons.append(f"{count} separate objects came back, at most {max_components} allowed")
    contact = measure_alpha_ground_contact(data)
    bottom_padding = int(cast(float, contact.get("bottom_padding_pixels", 0) or 0))
    contact_y = float(cast(float, contact.get("ground_contact_y_normalized", 1.0) or 1.0))
    if bottom_padding < BOTTOM_PADDING_MIN_PX:
        reasons.append(
            f"only {bottom_padding}px of clear space under the object, need {BOTTOM_PADDING_MIN_PX}"
        )
    if contact_y < ground_contact_min:
        reasons.append(
            f"the object's base sits at {contact_y:.2f} of the canvas; it is floating in its card"
        )
    if reasons:
        raise GateError(reasons)
    # Both were measured off this same picture a moment ago, so they are read
    # back rather than recomputed; the casts state what that gate published.
    box = cast("list[int] | None", facts.get("bbox"))
    centre_x = (
        round(
            ((float(box[0]) + float(box[2])) / 2.0) / max(1.0, float(cast(int, facts["width"]))), 4
        )
        if box
        else 0.5
    )
    return {
        **facts,
        "subjects": subjects,
        "ground_contact": contact,
        "center_x_normalized": centre_x,
        **_footprint(data),
    }


def gate_prop_sheet(
    data: bytes,
    *,
    columns: int,
    rows: int,
    cell_px: int,
    states: Sequence[str],
    max_components: int,
) -> tuple[dict[str, bytes], dict[str, object]]:
    """Every look of one prop on one native-alpha canvas: split by geometry, gate each as a sprite.

    No lattice and no keying. The canvas is asked for with true alpha, the
    same route the sprites use, and divided into equal cells by arithmetic;
    what the gate asks is that each cell holds one look with clear space to
    its borders, so a look that wandered across a border is refused by name.
    All or nothing, and every cell's complaint survives, so a sheet refused
    for one bad cell reports the other three as well. Returns the canonical
    per-look sprites keyed by state, in reading order, plus a sheet record
    with one entry per cell carrying the sprite gate's facts.
    """

    image = _open(data)
    expected = (columns * cell_px, rows * cell_px)
    if image.size != expected:
        raise GateError(
            [f"canvas is {image.size[0]}x{image.size[1]}, expected {expected[0]}x{expected[1]}"]
        )
    if len(states) != columns * rows:
        raise GateError([f"{len(states)} looks named for {columns * rows} cells"])
    alpha = image.getchannel("A")
    low, _high = _extrema(alpha)
    if low > 200:
        raise GateError(["the canvas is opaque; the provider returned a picture, not a cutout"])

    inset = round(cell_px * SHEET_CELL_INSET)
    mask = _mask(image)
    column_seams = _sheet_seams(mask, count=columns, cell_px=cell_px, axis="x")
    row_seams = _sheet_seams(mask, count=rows, cell_px=cell_px, axis="y")
    reasons: list[str] = []
    sprites: dict[str, bytes] = {}
    records: list[dict[str, object]] = []
    for index, state in enumerate(states):
        label = f"cell {index} ({state})"
        column, row = index % columns, index // columns
        left, right = column_seams[column], column_seams[column + 1]
        top, bottom = row_seams[row], row_seams[row + 1]
        cell = image.crop((left, top, right, bottom))
        # Severed means paint ON a seam line within this cell's span: the seam
        # was chosen as the emptiest line, so anything still on it is a look
        # the cut would go through.
        severed = any(
            painted_on(mask, seam, axis, low, high)
            for seam, axis, low, high in (
                (left, "x", top, bottom),
                (right, "x", top, bottom),
                (top, "y", left, right),
                (bottom, "y", left, right),
            )
            if 0 < seam < (mask.size[0] if axis == "x" else mask.size[1])
        )
        if severed:
            reasons.append(f"{label}: the object crosses the seam into its neighbour's cell")
        # An empty seam means neither neighbour is cut; the clearance a
        # sprite wants at its edge is then delivery format, added as
        # transparent padding on the interior sides only. The canvas's own
        # edges get no padding: a look cropped by the provider stays refused.
        pad = (
            inset if column > 0 else 0,
            inset if row > 0 else 0,
            inset if column < columns - 1 else 0,
            inset if row < rows - 1 else 0,
        )
        cell = ImageOps.expand(cell, border=pad, fill=(0, 0, 0, 0))
        cell_w, cell_h = cell.size
        box = _mask(cell).getbbox()
        if box and (
            box[0] < inset or box[1] < inset or box[2] > cell_w - inset or box[3] > cell_h - inset
        ):
            reasons.append(
                f"{label}: the object reaches its cell's border; it is not its own cutout"
            )
        buffer = BytesIO()
        cell.save(buffer, format="PNG")
        png = buffer.getvalue()
        try:
            facts = gate_prop(
                png,
                width=cell_w,
                height=cell_h,
                max_components=max_components,
                ground_contact_min=SHEET_GROUND_CONTACT_MIN,
                visible_fraction_min=SHEET_VISIBLE_FRACTION_MIN,
            )
        except GateError as error:
            reasons.extend(f"{label}: {reason}" for reason in error.reasons)
            continue
        canonical, alpha_facts = canonicalize_sprite_alpha(png)
        sprites[state] = canonical
        records.append(
            {
                "index": index,
                "state": state,
                "x": left,
                "y": top,
                "w": cell_w,
                "h": cell_h,
                "padding": list(pad),
                "alpha_canonicalization": alpha_facts,
                **facts,
            }
        )
    if reasons:
        raise GateError(reasons)
    return sprites, {
        "schema_version": 1,
        "kind": "oblique-survival-prop-sheet-v2",
        "columns": columns,
        "rows": rows,
        "cell_px": cell_px,
        "transparency": "native",
        "seams": {"x": column_seams, "y": row_seams},
        "cells": records,
    }


def painted_on(mask: Image.Image, at: int, axis: str, low: int, high: int) -> bool:
    """Whether the line ``at`` (a column for "x", a row for "y") is painted between low and high."""

    pixels = mask.load()
    assert pixels is not None
    if axis == "x":
        return any(pixels[at, y] for y in range(low, high))
    return any(pixels[x, at] for x in range(low, high))


def _sheet_seams(mask: Image.Image, *, count: int, cell_px: int, axis: str) -> list[int]:
    """Where to cut: the emptiest line near each interior half line, else the line itself.

    The outer edges are fixed. For each interior line the search window is
    ``SHEET_SEAM_SEARCH_SHARE`` of a cell either side, and the line with the
    fewest painted pixels wins; a tie keeps the arithmetic line. A look that
    crosses every candidate is still refused by the inset check downstream.
    """

    width, height = mask.size
    length = width if axis == "x" else height
    pixels = mask.load()
    assert pixels is not None

    def painted(at: int) -> int:
        if axis == "x":
            return sum(1 for y in range(height) if pixels[at, y])
        return sum(1 for x in range(width) if pixels[x, at])

    seams = [0]
    reach = round(cell_px * SHEET_SEAM_SEARCH_SHARE)
    for k in range(1, count):
        line = k * cell_px
        best, best_count = line, painted(line)
        for offset in range(1, reach + 1):
            for candidate in (line - offset, line + offset):
                if 0 < candidate < length:
                    hits = painted(candidate)
                    if hits < best_count:
                        best, best_count = candidate, hits
            if best_count == 0:
                break
        seams.append(best)
    seams.append(length)
    return seams


def _footprint(data: bytes) -> dict[str, object]:
    """Width of the lowest sliver of the subject, plus the floor-plate flag.

    A prop's collision radius is what its base covers, not what its canopy
    covers, so the measurement is taken over a thin band at the very bottom.

    The floor-plate test compares that band against the band immediately above
    it, not against the whole silhouette. Comparing against the silhouette flags
    every naturally wide-based object -- a boulder, a tent, a firepit -- and a
    flag that fires on almost everything tells a reviewer nothing. A painted disc
    of soil is specifically a base much wider than the object standing on it.
    """

    image = _open(data)
    mask = _mask(image)
    box = mask.getbbox()
    if box is None:
        return {"footprint_width_px": 0, "floor_plate_suspected": False}
    left, top, right, bottom = box
    subject_height = bottom - top
    subject_width = right - left
    band = max(2, round(subject_height * FOOTPRINT_BAND_SHARE))

    def band_width_at(offset: int) -> int:
        top_y = max(top, bottom - band - offset)
        bottom_y = max(top_y + 1, bottom - offset)
        strip = mask.crop((left, top_y, right, bottom_y))
        strip_box = strip.getbbox()
        return (strip_box[2] - strip_box[0]) if strip_box else 0

    base_width = band_width_at(0)
    # Compare against the width a fifth of the way up, not the band immediately
    # above: a painted disc of soil is thicker than one measurement band, so an
    # adjacent comparison lands inside the plate and reads no widening at all.
    above_width = band_width_at(int(subject_height * FLOOR_PLATE_REFERENCE_HEIGHT))
    strip = mask.crop((left, bottom - band, right, bottom))
    fill = sum(strip.histogram()[255:]) / float(max(1, band * subject_width))
    widening = base_width / above_width if above_width else 0.0
    suspected = widening >= FLOOR_PLATE_WIDENING_MIN and fill >= FLOOR_PLATE_FILL_MIN
    return {
        "footprint_width_px": base_width,
        "footprint_band_px": band,
        "footprint_band_fill": round(fill, 4),
        "band_above_width_px": above_width,
        "base_widening": round(widening, 3),
        "subject_width_px": subject_width,
        "subject_height_px": subject_height,
        # Not a refusal: a firepit really is a wide solid ring at its base. The
        # reviewer decides whether it is the object or a painted patch of soil.
        "floor_plate_suspected": bool(suspected),
    }


# --- motion strips -------------------------------------------------------------------


def gate_motion_atlas(
    data: bytes, *, width: int, height: int, columns: int, state: str
) -> tuple[bytes, dict[str, object]]:
    """Validate a single-row strip, then repack it to canonical cells."""

    facts = gate_transparent_canvas(data, width=width, height=height)
    reasons: list[str] = []
    image = _open(data)
    cell = image.width // columns
    heights: list[int] = []
    feet: list[int] = []
    shares: list[float] = []
    for index in range(columns):
        crop = image.crop((index * cell, 0, (index + 1) * cell, image.height))
        mask = _mask(crop)
        share = sum(mask.histogram()[255:]) / float(cell * image.height)
        shares.append(round(share, 5))
        if share < CELL_VISIBLE_MIN:
            reasons.append(f"cell {index} is effectively empty ({share:.4f})")
        box = mask.getbbox()
        heights.append((box[3] - box[1]) if box else 0)
        feet.append(box[3] if box else 0)
    if reasons:
        raise GateError(reasons)

    ordered = sorted(heights)
    median = ordered[len(ordered) // 2] or 1
    spread = max(abs(value - median) / median for value in heights)
    limit = CELL_HEIGHT_SPREAD_CYCLE if state in _CYCLE_STATES else CELL_HEIGHT_SPREAD_ACTION
    if spread > limit:
        reasons.append(
            f"figure height varies {spread:.0%} across cells (limit {limit:.0%} for {state}); "
            "the provider re-framed between frames"
        )
    # The feet line: every cell stands on the same invisible ground line, so a
    # zoom or a re-crop moves the lowest painted row and a pose does not.
    feet_spread = (max(feet) - min(feet)) / float(image.height)
    if feet_spread > CELL_FEET_LINE_SPREAD:
        reasons.append(
            f"the feet line moves {feet_spread:.0%} of the canvas across cells "
            f"(limit {CELL_FEET_LINE_SPREAD:.0%}); the provider re-framed between frames"
        )
    if reasons:
        raise GateError(reasons)

    canonical, repack = repack_alpha_components(
        data,
        AlphaComponentRepackContract(
            rows=1, columns=columns, required_cells=columns, gutter=12, anchor="bottom"
        ),
    )
    return canonical, {
        **facts,
        "state": state,
        "columns": columns,
        "rows": 1,
        "cell_visible_fractions": shares,
        "cell_subject_heights_px": heights,
        "cell_height_spread": round(spread, 4),
        "cell_height_spread_limit": limit,
        "cell_feet_px": feet,
        "cell_feet_line_spread": round(feet_spread, 4),
        "cell_feet_line_spread_limit": CELL_FEET_LINE_SPREAD,
        "repack": repack,
    }


# --- ground --------------------------------------------------------------------------


def _half_variance_radius_px(luma: Image.Image, *, working: int = 256) -> float:
    """The blur radius at which half the plate's variance is gone, in source px.

    An estimate of feature size, and only an estimate: ink lines and colour
    blobs both count, so a fine inked material and a coarse flat one can land
    near each other. It is recorded for comparison across runs, never refused
    on; the judge is asked the semantic question instead.
    """

    small = luma.resize((working, working), Image.Resampling.BOX)
    total = ImageStat.Stat(small).var[0]
    if total <= 1e-9:
        return 0.0
    low, high = 0.25, float(working) / 2.0
    for _ in range(18):
        mid = (low + high) / 2.0
        remaining = ImageStat.Stat(small.filter(ImageFilter.GaussianBlur(mid))).var[0]
        if remaining > total / 2.0:
            low = mid
        else:
            high = mid
    scale = luma.width / float(working)
    return round(((low + high) / 2.0) * 2.0 * scale, 2)


def gate_ground_texture(
    data: bytes,
    *,
    width: int,
    height: int,
    texel_meters: float | None = None,
    luma_range: tuple[float, float] = GROUND_LUMA_RANGE,
    busyness_max: float = GROUND_BUSYNESS_MAX,
) -> dict[str, object]:
    """Opaque, uniformly lit, fine-featured, and quiet at play zoom.

    ``luma_range`` is the ground's band by default; water declares a darker one.
    The busy-ness check needs ``texel_meters`` to know the play scale and is
    skipped without it.
    """

    reasons: list[str] = []
    image = _open(data)
    if image.size != (width, height):
        reasons.append(f"canvas is {image.size[0]}x{image.size[1]}, expected {width}x{height}")
    low, _high = _extrema(image.getchannel("A"))
    if low < 250:
        reasons.append("a ground plate must come back fully opaque")
    luma = _luma(image)
    global_mean = _mean(luma)
    block_w = luma.width // GROUND_BLOCKS
    block_h = luma.height // GROUND_BLOCKS
    blocks: list[float] = []
    for row in range(GROUND_BLOCKS):
        for column in range(GROUND_BLOCKS):
            crop = luma.crop(
                (column * block_w, row * block_h, (column + 1) * block_w, (row + 1) * block_h)
            )
            blocks.append(_mean(crop))
    if not luma_range[0] <= global_mean <= luma_range[1]:
        reasons.append(
            f"the plate's mean value is {global_mean:.3f}, outside the playable band "
            f"[{luma_range[0]}, {luma_range[1]}]; the runtime darkens the ground "
            "again for canopy shade and for night, so it must arrive at a mid value"
        )
    deviation = max(abs(value - global_mean) for value in blocks) / max(global_mean, 1e-6)
    if deviation > GROUND_BLOCK_DEVIATION_MAX:
        reasons.append(
            f"brightness varies {deviation:.0%} between blocks (limit "
            f"{GROUND_BLOCK_DEVIATION_MAX:.0%}); the plate has a large feature or a gradient"
        )
    quarter_w = luma.width // 4
    quarter_h = luma.height // 4
    corners = [
        _mean(luma.crop((0, 0, quarter_w, quarter_h))),
        _mean(luma.crop((luma.width - quarter_w, 0, luma.width, quarter_h))),
        _mean(luma.crop((0, luma.height - quarter_h, quarter_w, luma.height))),
        _mean(
            luma.crop((luma.width - quarter_w, luma.height - quarter_h, luma.width, luma.height))
        ),
    ]
    centre = _mean(
        luma.crop(
            (
                luma.width // 2 - quarter_w // 2,
                luma.height // 2 - quarter_h // 2,
                luma.width // 2 + quarter_w // 2,
                luma.height // 2 + quarter_h // 2,
            )
        )
    )
    ratio = (sum(corners) / len(corners)) / max(centre, 1e-6)
    if not GROUND_CORNER_RATIO[0] <= ratio <= GROUND_CORNER_RATIO[1]:
        reasons.append(f"corner-to-centre brightness ratio {ratio:.2f} is a vignette")
    busyness = ground_busyness(luma, texel_meters) if texel_meters else None
    if busyness is not None and busyness > busyness_max:
        reasons.append(
            f"the plate is too busy: local contrast at play zoom is {busyness:.3f} of its mean "
            f"value (limit {busyness_max}); it reads as speckle, not ground. Most of the canvas "
            "must be plain flat ground colour, with a few marks in tones close to it"
        )
    if reasons:
        raise GateError(reasons)
    feature_px = _half_variance_radius_px(luma)
    facts: dict[str, object] = {
        "width": image.size[0],
        "height": image.size[1],
        "luma_mean": round(global_mean, 4),
        "block_deviation": round(deviation, 4),
        "corner_centre_ratio": round(ratio, 4),
        "feature_scale_estimate_px": feature_px,
    }
    if texel_meters:
        facts["texel_meters"] = texel_meters
        facts["feature_scale_estimate_meters"] = round(feature_px * texel_meters / luma.width, 4)
        facts["busyness_at_play"] = round(busyness or 0.0, 4)
        facts["busyness_limit"] = busyness_max
    return facts


def ground_busyness(luma: Image.Image, texel_meters: float) -> float:
    """Local contrast of the plate at play zoom, as a share of its mean value.

    The plate is shrunk to the size it has on screen, a blur of it stands for
    the ground under the marks, and the mean absolute difference is how much
    the marks stand out. This is the number the eye reads as "busy": a plate
    of pale seed heads on straw scored 0.054 and read as ground; a bed of
    ink-outlined pebbles scored 0.097 and read as noise. Scaling the plate up
    does not change it, which is why a bigger texel was not the fix.
    """

    play_px = max(16, round(texel_meters * PLAY_PX_PER_METER))
    small = luma.resize((play_px, play_px), Image.Resampling.LANCZOS)
    ground = small.filter(ImageFilter.GaussianBlur(GROUND_BUSYNESS_BLUR_PX))
    marks = ImageChops.difference(small, ground)
    return _mean(marks) / max(_mean(small), 1e-6)


def _edge_mean(luma: Image.Image) -> float:
    return _mean(luma.filter(ImageFilter.FIND_EDGES))


def gate_macro_plate(data: bytes, *, width: int, height: int) -> dict[str, object]:
    """A colour field with no drawing in it, at a neutral mean.

    The plate is multiplied over the material, so its mean is normalised away
    in the shader and only its variation survives. What it must not carry is
    ink: any line in it repeats every forty-eight metres as a line.
    """

    reasons: list[str] = []
    image = _open(data)
    if image.size != (width, height):
        reasons.append(f"canvas is {image.size[0]}x{image.size[1]}, expected {width}x{height}")
    low, _high = _extrema(image.getchannel("A"))
    if low < 250:
        reasons.append("a macro plate must come back fully opaque")
    luma = _luma(image)
    mean = _mean(luma)
    if not MACRO_LUMA_RANGE[0] <= mean <= MACRO_LUMA_RANGE[1]:
        reasons.append(
            f"mean value {mean:.3f} is outside [{MACRO_LUMA_RANGE[0]}, {MACRO_LUMA_RANGE[1]}]; "
            "the plate is a multiplier and must arrive near mid-grey"
        )
    edges = _edge_mean(luma)
    if edges > MACRO_EDGE_MEAN_MAX:
        reasons.append(
            f"edge energy {edges:.4f} is over {MACRO_EDGE_MEAN_MAX}; the plate has lines or "
            "texture in it, and a macro plate must be soft washes only"
        )
    halves = [
        _mean(luma.crop((0, 0, luma.width // 2, luma.height))),
        _mean(luma.crop((luma.width // 2, 0, luma.width, luma.height))),
        _mean(luma.crop((0, 0, luma.width, luma.height // 2))),
        _mean(luma.crop((0, luma.height // 2, luma.width, luma.height))),
    ]
    deviation = max(abs(value - mean) for value in halves) / max(mean, 1e-6)
    if deviation > MACRO_HALF_DEVIATION_MAX:
        reasons.append(
            f"one half of the plate is {deviation:.0%} off the mean (limit "
            f"{MACRO_HALF_DEVIATION_MAX:.0%}); that is a gradient, not a mottle"
        )
    if reasons:
        raise GateError(reasons)
    return {
        "width": image.size[0],
        "height": image.size[1],
        "luma_mean": round(mean, 4),
        "edge_mean": round(edges, 5),
        "half_deviation": round(deviation, 4),
    }


#: A litter piece's contact ratio: the mean value of its lowest band over its
#: highest band. Recorded for every cell and gating none, after two runs of
#: trying: the ratio reads colour as light (a mushroom's pale stem under its
#: dark cap scored 1.43 with a good contact ring, a dark bark piece 0.98 with
#: a good crescent), a thinner band reads the ink outline as the crescent
#: (the old sticker stone and the new pressed stone both scored 0.61), and a
#: bottom-contour flatness test cannot see a piece made of three pebbles.
#: Contact is semantic; the review judges it. This number is for the record.
CLUTTER_CONTACT_RATIO_MAX: Final = 0.92
#: Share of the piece's height taken as its upper and lower bands.
CLUTTER_CONTACT_BAND: Final = 0.30
#: Contact classes the ratio refuses. Empty on purpose; see above.
CLUTTER_CONTACT_GATED: Final[tuple[str, ...]] = ()


def clutter_contact_ratio(cell: Image.Image) -> float | None:
    """Lower-band over upper-band mean value of the covered pixels, or None if empty."""

    mask = _mask(cell)
    box = mask.getbbox()
    if not box:
        return None
    luma = _luma(cell)
    height = box[3] - box[1]
    band = max(1, round(height * CLUTTER_CONTACT_BAND))

    def band_mean(top: int, bottom: int) -> float:
        region = (box[0], top, box[2], bottom)
        values = luma.crop(region).tobytes()
        weights = mask.crop(region).tobytes()
        total = 0.0
        count = 0
        for value, weight in zip(values, weights, strict=True):
            if weight:
                total += value
                count += 1
        return total / count if count else 0.0

    upper = band_mean(box[1], box[1] + band)
    lower = band_mean(box[3] - band, box[3])
    return lower / max(upper, 1e-6)


def _flat_rgb(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    return Image.alpha_composite(Image.new("RGBA", rgba.size, (0, 0, 0, 255)), rgba).convert("RGB")


#: A pixel this close to the guide cyan (R low, G and B high and close) is the
#: lattice's ghost, cleared from a cut cell whatever its alpha.
GUIDE_GHOST_MAX_RED: Final = 110
GUIDE_GHOST_MIN_GREEN: Final = 120


def _clear_guide_ghost(cell: Image.Image) -> None:
    """Zero the alpha of every pixel drawn in the guide's cyan, in place."""

    r, g, b, a = cell.split()
    red_low = r.point(lambda v: 255 if v <= GUIDE_GHOST_MAX_RED else 0)
    green_high = g.point(lambda v: 255 if v >= GUIDE_GHOST_MIN_GREEN else 0)
    blue_high = b.point(lambda v: 255 if v >= GUIDE_GHOST_MIN_GREEN - 20 else 0)
    ghost = ImageChops.multiply(ImageChops.multiply(red_low, green_high), blue_high)
    cell.putalpha(ImageChops.subtract(a, ghost))


#: A cut cell's pixels this far (px) from its opaque core are its own
#: antialiased rim; anything semi-transparent beyond that is a halo.
HALO_RIM_PX: Final = 2


#: An opaque blob smaller than this (px) inside a cut cell is a fleck of the
#: halo that reached full alpha, not a leaf: a leaf at the sheet's scale is
#: sixty pixels and more.
HALO_SPECK_MAX_PX: Final = 40
#: A pixel darker than this (0-255 luma) at less than full alpha is halo or
#: ink; ink is kept by the rim round the plant's colour, halo is not.
HALO_INK_LUMA: Final = 50
#: Alpha (0-255) from which a coloured pixel counts as the plant: the
#: viewer's alpha cutoff, a half.
HALO_COLOUR_ALPHA_MIN: Final = 128


def _sizeable_components(mask: Image.Image) -> Image.Image:
    """The mask with every connected blob under HALO_SPECK_MAX_PX cleared."""

    width, height = mask.size
    pixels = bytearray(mask.tobytes())
    seen = bytearray(width * height)
    out = bytearray(width * height)
    for start in range(width * height):
        if not pixels[start] or seen[start]:
            continue
        stack = [start]
        seen[start] = 1
        blob: list[int] = []
        while stack:
            index = stack.pop()
            blob.append(index)
            x, y = index % width, index // width
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < width and 0 <= ny < height:
                    n = ny * width + nx
                    if pixels[n] and not seen[n]:
                        seen[n] = 1
                        stack.append(n)
        if len(blob) >= HALO_SPECK_MAX_PX:
            for index in blob:
                out[index] = 255
    return Image.frombytes("L", (width, height), bytes(out))


def strip_halo(cell: Image.Image) -> tuple[Image.Image, float]:
    """Clear the soft dark halo a sheet draw paints round a cutout.

    The plant sheets came back with a shadowy haze of alpha 0.5 to 0.98
    spilling a cell's width round every plant, which the style forbids and
    the consumer would draw as a dark fuzz. The plant is its opaque core
    plus a two-pixel rim; every other semi-transparent pixel is cleared.
    Returns the cell and the share of the cell's painted alpha that was
    halo, for the record."""

    alpha = cell.getchannel("A")
    # The plant is what is opaque, or what has colour at all (a thin stem's
    # antialiased pixels are green at half alpha; the halo is near-black at
    # any alpha), in blobs of at least a leaf's size; its ink outline and
    # rim ride along within two pixels.
    opaque = alpha.point(lambda v: 255 if v >= OPAQUE_LIFT_MIN else 0)
    # Colour counts from the consumer's own cutoff up: the halo's outer
    # fringe is a dark-teal blend at alpha 0.1 that no card ever draws.
    painted = alpha.point(lambda v: 255 if v >= HALO_COLOUR_ALPHA_MIN else 0)
    coloured = ImageChops.multiply(
        painted, cell.convert("RGB").convert("L").point(lambda v: 255 if v >= HALO_INK_LUMA else 0)
    )
    core = _sizeable_components(ImageChops.lighter(opaque, coloured))
    rim = core.filter(ImageFilter.MaxFilter(2 * HALO_RIM_PX + 1))
    painted = alpha.point(lambda v: 255 if v > 0 else 0)
    halo = ImageChops.subtract(painted, rim)
    before = sum(alpha.histogram()[1:])
    kept = ImageChops.multiply(alpha, rim)
    out = cell.copy()
    out.putalpha(kept)
    stripped = sum(halo.histogram()[255:])
    return out, (stripped / before if before else 0.0)


def guided_cells(
    image: Image.Image, *, columns: int, rows: int, cell_px: int, native_alpha: bool
) -> tuple[dict[tuple[int, int], Image.Image], GuideLattice]:
    """Cells cut along the detected guides, with the alpha they came with or keyed off magenta.

    With ``native_alpha`` the guides are found on the picture laid over black
    (a clear pixel's colour is anything, and must not read as cyan), the cells
    are cut with the same margins the shared extractor uses, and their alpha
    is the provider's own. Without it, the shared extractor keys the magenta.
    """

    if not native_alpha:
        return extract_guided_cells(image, columns=columns, rows=rows, canonical_cell_px=cell_px)
    rgba = image.convert("RGBA")
    lattice = detect_guide_lattice(_flat_rgb(rgba), expected_columns=columns, expected_rows=rows)
    cells: dict[tuple[int, int], Image.Image] = {}
    for row in range(rows):
        for column in range(columns):
            left = lattice.x_lines[column][1] + 3
            right = lattice.x_lines[column + 1][0] - 2
            top = lattice.y_lines[row][1] + 3
            bottom = lattice.y_lines[row + 1][0] - 2
            if right <= left or bottom <= top:
                raise ValueError(f"collapsed guided crop at cell {(column, row)}")
            cell = rgba.crop((left, top, right, bottom)).resize(
                (cell_px, cell_px), Image.Resampling.LANCZOS
            )
            # The provider's guide edge leaves a ghost of alpha 4 to 11 along
            # the cut; clear it the way the sprite canonicaliser clears its
            # exterior, so a cell's border is empty rather than nearly empty.
            cell.putalpha(
                cell.getchannel("A").point(lambda v: 0 if v <= TRANSPARENT_CLEAR_MAX else v)
            )
            # The plant sheet's draws came back with the guides glowing: a
            # cyan haze of alpha up to 160 spilling a few pixels into every
            # cell, which the isolation test read as the piece touching its
            # guide. A pixel in the guide's own colour is the lattice's, not
            # the piece's, whatever its alpha, so it is cleared; nothing on a
            # sheet is drawn in the guide cyan (the look contract's palette
            # has no cyan in it).
            _clear_guide_ghost(cell)
            cells[(column, row)] = cell
    return cells, lattice


def gate_clutter_sheet(
    data: bytes,
    *,
    columns: int,
    rows: int,
    cell_px: int,
    template: bytes | None = None,
    contacts: Sequence[str] | None = None,
    native_alpha: bool = False,
    coverage: tuple[float, float] = CLUTTER_CELL_COVERAGE,
    halo: bool = False,
    inset_fraction: float = CLUTTER_CELL_INSET,
) -> tuple[bytes, dict[str, object]]:
    """The fire strip's lattice paintover, asked of sixteen still cutouts.

    With ``halo`` each cell has its soft halo stripped (``strip_halo``)
    before it is measured and before it is laid on the canonical sheet.
    ``inset_fraction`` is the margin inside the cut a piece must keep clear
    of; a season look of a sheet sets it to zero, since a snow cap grows a
    plant that already fills its cell and the cut at the guide is what
    matters, not the margin (the lattice must still be found intact).

    Returns the canonical RGBA sheet keyed off the magenta backing, plus one
    record per cell. Continuity is not a question here; isolation is: a piece
    that touches a guide line is a piece the extractor slices. ``contacts``
    names each cell's declared contact class; the class and a contact ratio
    travel in the record for the reviewer, and refuse nothing.
    """

    reasons: list[str] = []
    image = _open(data)
    expected = (columns * cell_px, rows * cell_px)
    if image.size != expected:
        raise GateError(
            [f"canvas is {image.size[0]}x{image.size[1]}, expected {expected[0]}x{expected[1]}"]
        )
    try:
        lattice = detect_guide_lattice(
            _flat_rgb(image) if native_alpha else image.convert("RGB"),
            expected_columns=columns,
            expected_rows=rows,
        )
    except ValueError as error:
        raise GateError([f"the guide lattice did not survive the paintover: {error}"]) from error
    residual = max(lattice.x_maximum_residual_px, lattice.y_maximum_residual_px)
    if residual > LATTICE_RESIDUAL_MAX_PX:
        raise GateError(
            [
                f"guide lattice drifted {residual:.1f}px (limit {LATTICE_RESIDUAL_MAX_PX}); "
                "the provider repainted the guides instead of painting between them"
            ]
        )
    try:
        cells, _ = guided_cells(
            image, columns=columns, rows=rows, cell_px=cell_px, native_alpha=native_alpha
        )
    except ValueError as error:
        raise GateError([f"cells could not be recovered from the lattice: {error}"]) from error
    if len(cells) != columns * rows:
        raise GateError([f"{len(cells)} cells recovered, expected {columns * rows}"])

    keyed = [cells[(column, row)] for row in range(rows) for column in range(columns)]
    halo_shares: list[float] = []
    if halo:
        stripped = []
        for cell in keyed:
            cell, share_ = strip_halo(cell)
            stripped.append(cell)
            halo_shares.append(round(share_, 4))
        keyed = stripped
    inset = round(cell_px * inset_fraction)
    records: list[dict[str, object]] = []
    for index, cell in enumerate(keyed):
        mask = _mask(cell)
        share = sum(mask.histogram()[255:]) / float(cell_px * cell_px)
        box = mask.getbbox()
        if not coverage[0] <= share <= coverage[1]:
            reasons.append(
                f"cell {index} covers {share:.1%} of its cell, outside "
                f"{coverage[0]:.0%}-{coverage[1]:.0%}"
            )
        if box and (
            box[0] < inset or box[1] < inset or box[2] > cell_px - inset or box[3] > cell_px - inset
        ):
            reasons.append(f"cell {index}'s piece touches its guide line; it will be sliced")
        contact = contacts[index] if contacts is not None and index < len(contacts) else None
        ratio = clutter_contact_ratio(cell) if box else None
        if (
            contact in CLUTTER_CONTACT_GATED
            and ratio is not None
            and ratio > CLUTTER_CONTACT_RATIO_MAX
        ):
            reasons.append(
                f"cell {index} is a sticker: its lower edge is {ratio:.2f} of the value of its "
                f"upper edge (limit {CLUTTER_CONTACT_RATIO_MAX}); a {contact} piece needs a dark "
                "contact shadow along its lower edge"
            )
        records.append(
            {
                "index": index,
                "x": (index % columns) * cell_px,
                "y": (index // columns) * cell_px,
                "w": cell_px,
                "h": cell_px,
                "coverage": round(share, 4),
                "bbox": list(box) if box else None,
                **({"halo_stripped": halo_shares[index]} if halo else {}),
                "contact": contact,
                "contact_ratio": round(ratio, 4) if ratio is not None else None,
            }
        )
    if reasons:
        raise GateError(reasons)

    canvas = Image.new("RGBA", expected, (0, 0, 0, 0))
    for index, cell in enumerate(keyed):
        canvas.alpha_composite(cell, ((index % columns) * cell_px, (index // columns) * cell_px))
    buffer = BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue(), {
        "schema_version": 1,
        "kind": "oblique-survival-clutter-sheet-v1",
        "columns": columns,
        "rows": rows,
        "cell_px": cell_px,
        "lattice_residual_px": round(residual, 3),
        "inset_px": inset,
        "cells": records,
        "template_bound": template is not None,
    }


def mirror_repeat_2d(data: bytes) -> tuple[bytes, dict[str, object]]:
    """Mirror on x, then on y, by transposing between the two passes.

    ``loop_construction.mirror_repeat`` is x-only, and honestly so: every one of
    its constructions crops and pastes along width. Two axes is not a parameter
    of that module but a different problem, whose real work is the four corners
    where two seams meet. Mirroring twice sidesteps that entirely and is exact by
    construction; the price is a visible period-two symmetry, which the viewer's
    stochastic tiling breaks up. A generative two-axis seam repaint is listed
    under what this spike deliberately does not do.
    """

    horizontal, first = mirror_repeat(data)
    with Image.open(BytesIO(horizontal)) as opened:
        transposed = opened.convert("RGBA").transpose(Image.Transpose.TRANSPOSE)
    buffer = BytesIO()
    transposed.save(buffer, format="PNG")
    both, second = mirror_repeat(buffer.getvalue())
    with Image.open(BytesIO(both)) as opened:
        restored = opened.convert("RGBA").transpose(Image.Transpose.TRANSPOSE)
    out = BytesIO()
    restored.save(out, format="PNG")
    return out.getvalue(), {
        "schema_version": 1,
        "kind": "mirror-repeat-2d-v1",
        "guarantee": "reflection",
        "x_pass": first,
        "y_pass": second,
        "period_width": restored.width,
        "period_height": restored.height,
        "provider_operations": 0,
    }


def gate_tileable_2d(data: bytes) -> dict[str, object]:
    """Opposite edges must match. Mirror repeat makes this exactly zero."""

    image = _luma(_open(data))
    width, height = image.size
    pixels = _band(image)
    horizontal = sum(abs(pixels[0, y] - pixels[width - 1, y]) for y in range(height)) / (
        height * 255.0
    )
    vertical = sum(abs(pixels[x, 0] - pixels[x, height - 1]) for x in range(width)) / (
        width * 255.0
    )
    if horizontal > TILE_EDGE_DELTA_MAX or vertical > TILE_EDGE_DELTA_MAX:
        raise GateError(
            [
                f"edges do not wrap: horizontal delta {horizontal:.4f}, vertical {vertical:.4f} "
                f"(limit {TILE_EDGE_DELTA_MAX:.4f})"
            ]
        )
    return {
        "horizontal_edge_delta": round(horizontal, 6),
        "vertical_edge_delta": round(vertical, 6),
    }


#: How far the published feather reaches in from the drawn edge, at sprite scale.
DECAL_FEATHER_RADIUS_PX: Final = 24


def decal_soft_edge_share(data: bytes) -> float:
    histogram = _open(data).getchannel("A").histogram()
    visible = sum(histogram[ALPHA_THRESHOLD + 1 :])
    soft = sum(histogram[ALPHA_THRESHOLD + 1 : 241])
    return soft / float(visible) if visible else 0.0


def decal_irregularity(data: bytes) -> float:
    """How far the silhouette is from a disc: radius spread about the centroid.

    The outermost visible pixel along each of ``DECAL_RADIUS_SAMPLES`` rays is
    the radius on that ray; the result is std / mean over the rays. A disc is
    zero however feathered it is, because the feather is uniform, and a lobed
    or elongated patch is not. An empty canvas is zero too.
    """

    mask = _open(data).getchannel("A").point(lambda v: 255 if v > ALPHA_THRESHOLD else 0)
    bbox = mask.getbbox()
    if bbox is None:
        return 0.0
    width, height = mask.size
    pixels = _band(mask)
    sum_x = sum_y = count = 0
    for y in range(bbox[1], bbox[3]):
        for x in range(bbox[0], bbox[2]):
            if pixels[x, y]:
                sum_x += x
                sum_y += y
                count += 1
    centre_x, centre_y = sum_x / count, sum_y / count
    reach = float(max(width, height))
    radii: list[float] = []
    for sample in range(DECAL_RADIUS_SAMPLES):
        angle = 2.0 * math.pi * sample / DECAL_RADIUS_SAMPLES
        cos, sin = math.cos(angle), math.sin(angle)
        best = 0.0
        step = 0.0
        while step < reach:
            x = round(centre_x + step * cos)
            y = round(centre_y + step * sin)
            if not (0 <= x < width and 0 <= y < height):
                break
            if pixels[x, y]:
                best = step
            step += 1.0
        radii.append(best)
    mean = sum(radii) / len(radii)
    if mean <= 0.0:
        return 0.0
    variance = sum((r - mean) ** 2 for r in radii) / len(radii)
    return math.sqrt(variance) / mean


def feather_decal_edge(data: bytes, *, radius_px: int = DECAL_FEATHER_RADIUS_PX) -> bytes:
    """Fade a decal's outer edge to nothing, deterministically.

    The soft edge is a compositing property, not a drawing one, and asking a
    model for it costs attempts: the package's own style bans soft falloff
    inside a shape, so a plate-guided decal comes back hard-cut and the gate
    burns six tries refusing it. Blurring alpha and taking the MINIMUM against
    the original only ever softens inward -- the drawn silhouette never grows,
    and fully transparent stays fully transparent.
    """

    image = _open(data)
    alpha = image.getchannel("A")
    softened = ImageChops.darker(alpha, alpha.filter(ImageFilter.GaussianBlur(radius_px)))
    image.putalpha(softened)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def gate_decal(
    data: bytes,
    *,
    width: int,
    height: int,
    soft_edge: bool = True,
    irregularity_min: float = DECAL_IRREGULARITY_MIN,
) -> dict[str, object]:
    """A decal that does not feather reads as a sticker, and a disc reads as a disc.

    ``soft_edge`` is False at generation time, where the edge has not been
    feathered yet; the published decal is gated with it on.
    """

    facts = gate_transparent_canvas(data, width=width, height=height)
    share = decal_soft_edge_share(data)
    reasons: list[str] = []
    if soft_edge and share < DECAL_SOFT_EDGE_SHARE_MIN:
        reasons.append(
            f"only {share:.1%} of the decal is partial alpha (need "
            f"{DECAL_SOFT_EDGE_SHARE_MIN:.0%}); its edges are hard-cut"
        )
    irregularity = decal_irregularity(data)
    if irregularity < irregularity_min:
        reasons.append(
            f"the patch is a disc: its radius varies by {irregularity:.3f} of its mean "
            f"(need {irregularity_min:.2f}); ask for a lopsided, lumpy shape"
        )
    if reasons:
        raise GateError(reasons)
    return {
        **facts,
        "soft_edge_share": round(share, 4),
        "irregularity": round(irregularity, 4),
        "irregularity_min": irregularity_min,
    }


# --- weather -------------------------------------------------------------------------
#
# Three sheets, one question a consumer depends on and nothing else: each must
# hold its pieces one per cell (two halves for the drops, four quarters for the
# splashes and the bolts) so a consumer can cut by arithmetic. What the streaks
# and bolts look like is the brief's
# business and the reviewer's, never a threshold's. The shared dust validator
# is not reused here on purpose: its "wisps" floor (a piece filling under 35%
# of its box) refuses every thin ripple ring and every jagged bolt, which is
# exactly what these two sheets are made of.

#: A cell sheet: one piece per cell (two halves, or four quarters), each inset
#: from the cell's edges so cutting on the half lines never clips it. The piece is measured on
#: its opaque BODY, the alpha canonicalisation lifts to full, not on its soft
#: rim: the first live bolt sheet drew four clean bolts whose antialiased tips
#: ran eight to seventeen pixels past their cores and touched the half lines
#: by that rim alone. A rim clipped by a pixel is invisible at play scale; a
#: core clipped is a broken bolt, and that is what this refuses.
SHEET_BODY_ALPHA: Final = OPAQUE_LIFT_MIN
#: One percent of the half: five pixels at 1024. A core clipped by that much at
#: a tip is invisible on a thirteen-metre card, and what crosses into the
#: neighbouring cell is bounded by the same five pixels.
SHEET_QUADRANT_INSET: Final = 0.01
SPLASH_CELL_COVERAGE: Final = (0.004, 0.45)
DROPS_CELL_COVERAGE: Final = (0.001, 0.30)
STRIKE_CELL_COVERAGE: Final = (0.004, 0.40)
#: A bolt is tall: its box at least this many times higher than wide (a fork
#: that reaches sideways is still a bolt at two), and it spans at least this
#: share of its quarter's height.
STRIKE_TALLNESS_MIN: Final = 2.0
STRIKE_SPAN_MIN: Final = 0.55


def gate_quadrant_sheet(
    data: bytes,
    *,
    width: int,
    height: int,
    kinds: Sequence[str],
    coverage_range: tuple[float, float],
    tallness_min: float | None = None,
    span_min: float | None = None,
) -> dict[str, object]:
    """One piece per cell, each inset from the half lines; optionally tall.

    Two kinds lay the cells side by side as halves, four as quarters. Returns
    one cell record per cell in reading order, with the tight box of what is
    painted there, so the consumer cuts by arithmetic and the reviewer sees
    each piece named.
    """

    if len(kinds) not in (2, 4):
        raise ValueError("a cell sheet names two or four cells")
    facts = gate_transparent_canvas(data, width=width, height=height, visible_fraction_min=0.002)
    image = _open(data)
    mask = _mask(image, threshold=SHEET_BODY_ALPHA)
    half_w = image.size[0] // 2
    half_h = image.size[1] // 2 if len(kinds) == 4 else image.size[1]
    reasons: list[str] = []
    cells: list[dict[str, object]] = []
    for index, kind in enumerate(kinds):
        x0 = (index % 2) * half_w
        y0 = (index // 2) * half_h
        quarter = mask.crop((x0, y0, x0 + half_w, y0 + half_h))
        box = quarter.getbbox()
        coverage = sum(quarter.histogram()[255:]) / float(half_w * half_h)
        label = f"cell {index} ({kind})"
        if box is None:
            reasons.append(f"{label} is empty")
            cells.append({"kind": kind, "x": x0, "y": y0, "w": half_w, "h": half_h, "bbox": None})
            continue
        if not coverage_range[0] <= coverage <= coverage_range[1]:
            reasons.append(
                f"{label} covers {coverage:.3f} of its quarter, outside "
                f"{coverage_range[0]}-{coverage_range[1]}"
            )
        # Only the half lines cut: a piece may run to the canvas edge on its
        # outer sides (the border check above already bounds that), but it
        # must keep clear of the two inner edges its quarter shares.
        inset_x = SHEET_QUADRANT_INSET * half_w
        inset_y = SHEET_QUADRANT_INSET * half_h
        inner_x = box[2] > half_w - inset_x if index % 2 == 0 else box[0] < inset_x
        inner_y = len(kinds) == 4 and (box[3] > half_h - inset_y if index < 2 else box[1] < inset_y)
        if inner_x or inner_y:
            reasons.append(f"{label} reaches a half line of the sheet, which would cut it")
        box_w, box_h = box[2] - box[0], box[3] - box[1]
        if tallness_min is not None and box_h < tallness_min * box_w:
            reasons.append(
                f"{label} is {box_w}x{box_h}, not {tallness_min:g} times taller than wide"
            )
        if span_min is not None and box_h < span_min * half_h:
            reasons.append(
                f"{label} spans {box_h / half_h:.2f} of its quarter's height, under {span_min}"
            )
        cells.append(
            {
                "kind": kind,
                "x": x0,
                "y": y0,
                "w": half_w,
                "h": half_h,
                "bbox": [x0 + box[0], y0 + box[1], x0 + box[2], y0 + box[3]],
                "coverage": round(coverage, 4),
            }
        )
    if reasons:
        raise GateError(reasons)
    return {**facts, "body_alpha_min": SHEET_BODY_ALPHA, "cells": cells}


# --- effects -------------------------------------------------------------------------


def gate_fx_strip(
    data: bytes,
    *,
    columns: int,
    rows: int,
    cell_px: int,
    template: bytes | None = None,
    native_alpha: bool = False,
) -> tuple[bytes, dict[str, object]]:
    """Lattice geometry, per-cell coverage, and whether the cycle actually closes.

    Returns the canonical RGBA grid, keyed off the magenta backing, plus the
    record. The continuity measurement is the point of the gate: a sixteen-cell
    sheet of unrelated flames passes every other check and is useless as an
    animation.
    """

    reasons: list[str] = []
    image = _open(data)
    expected = (columns * cell_px, rows * cell_px)
    if image.size != expected:
        reasons.append(
            f"canvas is {image.size[0]}x{image.size[1]}, expected {expected[0]}x{expected[1]}"
        )
    if reasons:
        raise GateError(reasons)

    try:
        lattice = detect_guide_lattice(
            _flat_rgb(image) if native_alpha else image.convert("RGB"),
            expected_columns=columns,
            expected_rows=rows,
        )
    except ValueError as error:
        raise GateError([f"the guide lattice did not survive the paintover: {error}"]) from error
    residual = max(lattice.x_maximum_residual_px, lattice.y_maximum_residual_px)
    if residual > LATTICE_RESIDUAL_MAX_PX:
        reasons.append(
            f"guide lattice drifted {residual:.1f}px (limit {LATTICE_RESIDUAL_MAX_PX}); "
            "the provider repainted the guides instead of painting between them"
        )
    if reasons:
        raise GateError(reasons)

    try:
        cells, _ = guided_cells(
            image, columns=columns, rows=rows, cell_px=cell_px, native_alpha=native_alpha
        )
    except ValueError as error:
        raise GateError([f"cells could not be recovered from the lattice: {error}"]) from error
    if len(cells) != columns * rows:
        raise GateError([f"{len(cells)} cells recovered, expected {columns * rows}"])

    # extract_guided_cells already keys the magenta backing to alpha; keying
    # again would hand back a bare mask instead of a picture.
    keyed = [cells[(column, row)] for row in range(rows) for column in range(columns)]
    masks = [_mask(cell) for cell in keyed]

    coverage: list[float] = []
    bases: list[float] = []
    for index, mask in enumerate(masks):
        share = sum(mask.histogram()[255:]) / float(cell_px * cell_px)
        coverage.append(round(share, 4))
        if not FLAME_CELL_COVERAGE[0] <= share <= FLAME_CELL_COVERAGE[1]:
            reasons.append(
                f"cell {index} covers {share:.1%} of its cell, outside "
                f"{FLAME_CELL_COVERAGE[0]:.0%}-{FLAME_CELL_COVERAGE[1]:.0%}"
            )
        box = mask.getbbox()
        bases.append((box[3] / cell_px) if box else 0.0)
    if reasons:
        raise GateError(reasons)

    drift = max(bases) - min(bases)
    if drift > FLAME_BASE_DRIFT_MAX:
        reasons.append(
            f"the flame base moves {drift:.0%} of a cell across the strip (limit "
            f"{FLAME_BASE_DRIFT_MAX:.0%}); it will jitter vertically in play"
        )

    overlaps: list[float] = []
    for index in range(len(masks)):
        overlaps.append(round(_iou(masks[index], masks[(index + 1) % len(masks)]), 4))
    low = min(overlaps)
    high = max(overlaps)
    mode = "loop"
    if low < FLAME_CONTINUITY_IOU[0]:
        worst = overlaps.index(low)
        if worst == len(overlaps) - 1:
            # Only the wrap is broken: the frames animate, the cycle just does
            # not close. Ping-pong playback is the honest fallback, recorded so
            # the viewer plays it that way rather than stuttering once a cycle.
            mode = "ping_pong"
        else:
            reasons.append(
                f"cells {worst} and {worst + 1} share only {low:.0%} of their silhouette "
                f"(floor {FLAME_CONTINUITY_IOU[0]:.0%}); this is a jump cut, not an animation"
            )
    if high > FLAME_CONTINUITY_IOU[1]:
        duplicate = overlaps.index(high)
        reasons.append(
            f"cells {duplicate} and {(duplicate + 1) % len(overlaps)} are {high:.0%} identical; "
            "the provider duplicated a frame"
        )
    if reasons:
        raise GateError(reasons)

    canvas = Image.new("RGBA", expected, (0, 0, 0, 0))
    for index, cell in enumerate(keyed):
        canvas.alpha_composite(cell, ((index % columns) * cell_px, (index // columns) * cell_px))
    buffer = BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue(), {
        "schema_version": 1,
        "kind": "oblique-survival-fx-strip-v1",
        "columns": columns,
        "rows": rows,
        "cell_px": cell_px,
        "frames": columns * rows,
        "mode": mode,
        "lattice_residual_px": round(residual, 3),
        "cell_coverage": coverage,
        "cell_base_y_normalized": [round(value, 4) for value in bases],
        "base_drift": round(drift, 4),
        "continuity_iou": overlaps,
        "template_bound": template is not None,
    }


def strip_playback_order(frames: object, mode: object) -> list[int]:
    """The frame order the viewer plays, so a ping-pong fallback is explicit.

    Both arguments are read straight off a strip record, whose values are
    ``object``, so the narrowing is stated here once instead of at every call.
    """

    count = cast(int, frames)
    if mode != "ping_pong" or count < 2:
        return list(range(count))
    return list(range(count)) + list(range(count - 2, 0, -1))
