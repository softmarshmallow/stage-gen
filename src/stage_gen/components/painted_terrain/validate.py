"""Admission for a returned painting, run inside the provider's own retry budget.

Everything here is measured on what the model sent back, before publication touches it,
because that is the only place a refusal is cheap: a failure re-rolls inside the existing
six attempts instead of failing a run after the money is spent. Publication's own checks
live in ``canonicalize`` and answer a different question -- whether the canonicalizer did
its job -- which is why they are strict where these are gross.

Two of the four measurements exist because a hunting map breaks an assumption the runner
could make. Its ground is one near-continuous mass, so a mean over empty cells is a fair
summary of leakage. Here the map is 71 per cent air: a model can fill every one of the
forty hop-gap cells completely and still score 0.07 on that mean. So leakage is measured
per cell and again along the two structures that actually matter -- the gaps a player
jumps through, and the air a floating deck hangs in.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, cast

from PIL import Image, ImageChops

from stage_gen.components.painted_terrain.canonicalize import (
    occupancy_window,
    painted_terrain_segment_band,
)
from stage_gen.components.painted_terrain.guide import (
    RGB,
    cell_exposure,
    decode_rgba,
    material_palette,
    painted_terrain_guide_layout,
    require_occupancy,
)
from stage_gen.components.painted_terrain.segments import (
    PAINTED_TERRAIN_CELL_PX,
    PaintedTerrainSegment,
)
from stage_gen.components.painted_terrain.silhouette import (
    PAINTED_TERRAIN_VISIBLE_ALPHA,
    painted_silhouette_report,
)

PAINTED_TERRAIN_SOURCE_ID: Final = "painted-terrain-source-v1"

RGBA = tuple[int, int, int, int]

#: A gross floor on how much of the authored geometry came back painted at all. Gross
#: because the deterministic base covers what is missing; what it refuses is a model that
#: answered a different question.
_MIN_SOLID_COVERAGE: Final = 0.45

#: Floors on the silhouette band's inner core -- the part of a cell that must be drawn
#: whatever the art does at its edges. Measured against the core rather than the whole
#: cell because a deck's end cell is exposed on two sides and a correctly organic
#: silhouette rounds that corner; a whole-cell floor reads a rounded corner as a hole.
_MIN_SOLID_CORE_COVERAGE: Final = 0.60

#: The walking surface is the one line a player reads footing from, so an unpainted third
#: of it publishes as a flat band of registration colour exactly where it is most visible.
_MIN_SURFACE_CORE_COVERAGE: Final = 0.80

#: How much of an empty cell's guaranteed-clear core -- the part of it more than the
#: outward tolerance away from any terrain -- may be painted.
#:
#: The question this asks is not "did paint reach the air", because publication clips to
#: the band regardless. It is "would clipping this painting look wrong". Foliage trailing
#: below a ledge clips to a slightly shorter trail and reads fine; a measured pair of real
#: returns hung roots and flowers into 0.15 and 0.27 of a core doing exactly that. A gap
#: filled solid clips to two stubs pointing at each other, and a painted backdrop clips
#: away to nothing -- and both of those score 1.0, so the floor sits well clear of the art
#: and well clear of the failures. The two structures that genuinely must stay open have
#: their own rules below rather than leaning on this one.
_MAX_EMPTY_CORE_COVERAGE: Final = 0.35

#: A hop gap is the air between two masses on one level, and it is where the player jumps
#: through. Unlike the general case there is nothing decorative to protect here, so this
#: stays tight: both measured returns left every gap at 0.0.
_MAX_GAP_CORE_COVERAGE: Final = 0.15

#: Consecutive filled cells permitted below a deck. One is a thick underside; two is a
#: support, and a support is rock the player walks straight through.
_MAX_DECK_SUPPORT_RUN: Final = 1

#: How close a painted pixel may sit to a guide colour before it counts as guide showing
#: through, as a Chebyshev distance in RGB, and the share of the painted region allowed to
#: sit that close. Coverage checks cannot see this at all: every guide pixel is opaque, so
#: they measure alpha rather than authorship.
_MAX_GUIDE_RESIDUE_DISTANCE: Final = 10
_MAX_GUIDE_RESIDUE_SHARE: Final = 0.06


def validate_painted_terrain_source(
    source: bytes,
    *,
    occupancy: Sequence[str],
    segment: PaintedTerrainSegment,
    guide: bytes,
    material_identity: str,
    material_references: Sequence[bytes],
) -> dict[str, object]:
    """Refuse a painting that did not answer this guide, and say by how much."""

    rows, _ = require_occupancy(occupancy)
    layout = painted_terrain_guide_layout(occupancy, segment)
    painting = decode_rgba(source, label="painted terrain source")
    if painting.size != (layout.canvas_width, layout.canvas_height):
        raise ValueError(
            f"painted terrain source must be exactly {layout.canvas_width}x{layout.canvas_height}"
        )
    guide_image = decode_rgba(guide, label="painted terrain guide")
    if guide_image.size != painting.size:
        raise ValueError("painted terrain source and guide must share the provider canvas")
    darkest, brightest = cast("tuple[int, int]", painting.getchannel("A").getextrema())
    if darkest != 0 or brightest < PAINTED_TERRAIN_VISIBLE_ALPHA:
        raise ValueError(
            "painted terrain source must carry both true transparency and opaque material"
        )

    window = painting.crop(layout.central_box)
    full = Image.new(
        "RGBA",
        (segment.columns * PAINTED_TERRAIN_CELL_PX, rows * PAINTED_TERRAIN_CELL_PX),
        (0, 0, 0, 0),
    )
    full.paste(window, (0, layout.window_top_row * PAINTED_TERRAIN_CELL_PX))
    columns = occupancy_window(occupancy, segment)
    band = painted_terrain_segment_band(occupancy, segment)
    silhouette = painted_silhouette_report(full.getchannel("A"), columns, band=band)
    coverage = _cell_coverage(full.getchannel("A"), occupancy, segment)
    palette = material_palette(material_references, material_identity)
    residue = guide_residue_share(painting, guide_image, palette)

    facts: dict[str, object] = {
        "schema_version": 1,
        "kind": PAINTED_TERRAIN_SOURCE_ID,
        "segment_id": segment.segment_id,
        "material_identity": material_identity,
        "solid_coverage": coverage.solid_coverage,
        "guide_residue_share": residue,
        "silhouette": silhouette,
        "minimum_solid_coverage": _MIN_SOLID_COVERAGE,
        "minimum_solid_core_coverage_threshold": _MIN_SOLID_CORE_COVERAGE,
        "minimum_surface_core_coverage_threshold": _MIN_SURFACE_CORE_COVERAGE,
        "maximum_empty_core_coverage_threshold": _MAX_EMPTY_CORE_COVERAGE,
        "maximum_gap_core_coverage_threshold": _MAX_GAP_CORE_COVERAGE,
        "maximum_deck_support_run": _MAX_DECK_SUPPORT_RUN,
        "maximum_guide_residue_share": _MAX_GUIDE_RESIDUE_SHARE,
    }

    if coverage.solid_coverage < _MIN_SOLID_COVERAGE:
        raise ValueError(
            f"painted terrain source painted {coverage.solid_coverage} of the authored "
            f"terrain, below {_MIN_SOLID_COVERAGE}"
        )
    core = silhouette["minimum_solid_core_coverage"]
    if isinstance(core, float) and core < _MIN_SOLID_CORE_COVERAGE:
        raise ValueError(
            "painted terrain source left an authored cell mostly unpainted at "
            f"{silhouette['minimum_solid_core_cell']} ({core})"
        )
    surface = silhouette["minimum_surface_core_coverage"]
    if isinstance(surface, float) and surface < _MIN_SURFACE_CORE_COVERAGE:
        raise ValueError(
            "painted terrain source left the walking surface unpainted at "
            f"{silhouette['minimum_surface_core_cell']} ({surface})"
        )
    gap_core = silhouette["maximum_gap_core_coverage"]
    if isinstance(gap_core, float) and gap_core > _MAX_GAP_CORE_COVERAGE:
        raise ValueError(
            "painted terrain source closed a gap the player jumps through at cell "
            f"{silhouette['maximum_gap_core_cell']} ({gap_core})"
        )
    support = silhouette["deck_support_run"]
    if isinstance(support, int) and support > _MAX_DECK_SUPPORT_RUN:
        raise ValueError(
            f"painted terrain source hung a {support}-cell support under a floating deck"
        )
    empty_core = silhouette["maximum_empty_core_coverage"]
    if isinstance(empty_core, float) and empty_core > _MAX_EMPTY_CORE_COVERAGE:
        raise ValueError(
            "painted terrain source painted air the player moves through at cell "
            f"{silhouette['maximum_empty_core_cell']} ({empty_core})"
        )
    if residue > _MAX_GUIDE_RESIDUE_SHARE:
        raise ValueError(f"painted terrain source left {residue} of its painting as guide colour")
    return facts


def guide_residue_share(
    painting: Image.Image, guide: Image.Image, palette: tuple[RGB, RGB]
) -> float:
    """Share of the painted region still sitting on a guide colour.

    Measured where guide and painting are both opaque, so it asks about authorship rather
    than about alpha. A model that paints *around* the guide's blocks instead of over them
    passes every coverage floor.
    """

    considered = ImageChops.darker(
        guide.getchannel("A").point(lambda v: 255 if v >= PAINTED_TERRAIN_VISIBLE_ALPHA else 0),
        painting.getchannel("A").point(lambda v: 255 if v >= PAINTED_TERRAIN_VISIBLE_ALPHA else 0),
    )
    total = considered.histogram()[255]
    if total == 0:
        return 0.0
    near = Image.new("L", painting.size, 0)
    rgb = painting.convert("RGB")
    for colour in palette:
        bands = rgb.split()
        close = None
        for channel, value in zip(bands, colour, strict=True):
            distance = ImageChops.difference(channel, Image.new("L", painting.size, value))
            hit = distance.point(lambda v: 255 if v <= _MAX_GUIDE_RESIDUE_DISTANCE else 0)
            close = hit if close is None else ImageChops.darker(close, hit)
        assert close is not None
        near = ImageChops.lighter(near, close)
    return round(ImageChops.darker(near, considered).histogram()[255] / total, 4)


@dataclass(frozen=True, slots=True)
class _CellCoverage:
    solid_coverage: float
    minimum_solid_cell_coverage: float
    minimum_solid_cell: list[int] | None
    minimum_top_cell_coverage: float
    minimum_top_cell: list[int] | None


def _cell_coverage(
    alpha: Image.Image, occupancy: Sequence[str], segment: PaintedTerrainSegment
) -> _CellCoverage:
    cell = PAINTED_TERRAIN_CELL_PX
    opaque = alpha.point(lambda v: 255 if v >= PAINTED_TERRAIN_VISIBLE_ALPHA else 0)
    painted = 0.0
    area = 0
    worst_cell: tuple[float, int, int] | None = None
    worst_top: tuple[float, int, int] | None = None
    for row in range(len(occupancy)):
        for column in range(segment.start_column, segment.end_column):
            if occupancy[row][column] != "1":
                continue
            local = column - segment.start_column
            box = (local * cell, row * cell, (local + 1) * cell, (row + 1) * cell)
            covered = opaque.crop(box).histogram()[255] / (cell * cell)
            painted += covered
            area += 1
            if worst_cell is None or covered < worst_cell[0]:
                worst_cell = (covered, row, column)
            if cell_exposure(occupancy, row, column).top and (
                worst_top is None or covered < worst_top[0]
            ):
                worst_top = (covered, row, column)
    if area == 0:
        raise ValueError("painted terrain segment has no authored terrain")
    return _CellCoverage(
        solid_coverage=round(painted / area, 4),
        minimum_solid_cell_coverage=round(worst_cell[0], 4) if worst_cell else 0.0,
        minimum_solid_cell=[worst_cell[1], worst_cell[2]] if worst_cell else None,
        minimum_top_cell_coverage=round(worst_top[0], 4) if worst_top else 1.0,
        minimum_top_cell=[worst_top[1], worst_top[2]] if worst_top else None,
    )


def painted_terrain_join_discontinuity(
    plate: Image.Image, *, boundaries: Sequence[int], cell_px: int = PAINTED_TERRAIN_CELL_PX
) -> dict[str, object]:
    """How visible each cut is, as its column step against the map's own distribution.

    Two independently painted segments agree on silhouette by construction -- the band is
    computed map-wide -- so what remains at a cut is a possible discontinuity in material.
    A join is invisible when the step across it is unremarkable among all the steps inside
    the paintings, which is a thing to measure rather than squint at.
    """

    rgba = plate.convert("RGBA")
    width, height = rgba.size
    pixels = rgba.load()
    assert pixels is not None
    steps: list[float] = []
    at_column: dict[int, float] = {}
    for x in range(width - 1):
        total = 0
        count = 0

        for y in range(height):
            left = cast("RGBA", pixels[x, y])
            right = cast("RGBA", pixels[x + 1, y])
            if left[3] < PAINTED_TERRAIN_VISIBLE_ALPHA or right[3] < PAINTED_TERRAIN_VISIBLE_ALPHA:
                continue
            total += sum(abs(left[index] - right[index]) for index in range(3))
            count += 1
        if count == 0:
            continue
        step = total / (3 * count)
        steps.append(step)
        at_column[x] = step
    if not steps:
        raise ValueError("painted terrain plate has no opaque column pair to measure")
    steps.sort()
    median = steps[len(steps) // 2]
    joins: dict[str, dict[str, float | None]] = {}
    for boundary in boundaries:
        x = boundary * cell_px - 1
        measured = at_column.get(x)
        joins[str(boundary)] = {
            "step": round(measured, 3) if measured is not None else None,
            "ratio_to_median": (
                round(measured / median, 3) if measured is not None and median else None
            ),
        }
    return {
        "median_column_step": round(median, 3),
        "p95_column_step": round(steps[int(len(steps) * 0.95)], 3),
        "joins": joins,
    }


__all__ = [
    "PAINTED_TERRAIN_SOURCE_ID",
    "guide_residue_share",
    "painted_terrain_join_discontinuity",
    "validate_painted_terrain_source",
]
