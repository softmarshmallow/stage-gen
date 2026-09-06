"""Offline tests for the oblique-survival gates.

Each gate gets one image it must accept and one it must refuse, drawn here so
the test says what the defect is rather than depending on a stored file. Nothing
under this file reads a run: a gate is a pure function of bytes, and that is the
only reason the whole set is free to execute on every gate.

    uv run pytest tests/unit/recipes/oblique_survival/test_gates.py
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from typing import Any, Final, cast

import pytest
from PIL import Image, ImageDraw, ImageFilter

from stage_gen.media import measure_alpha_ground_contact
from stage_gen.media.guide_lattice import detect_guide_lattice
from stage_gen.recipes.oblique_survival import gates, templates
from stage_gen.recipes.oblique_survival.manifest import alpha_bbox
from stage_gen.recipes.oblique_survival.prepared_survival import (
    _look_drift,
    _normalise_look,
    plate_busyness_max,
    plate_gate_kwargs,
)
from stage_gen.recipes.oblique_survival.survival_request import load_package

PACKAGE: Final = Path("library/games/ember-hollow")
CANVAS: Final = (1024, 1024)


def _facts(record: Mapping[str, object]) -> dict[str, Any]:
    """A gate record, read as the JSON it is.

    Every gate types its record ``object``-valued, so a caller is forced to
    narrow what it reads. A test asserts about pictures it drew itself, and
    naming the type of each field at every assertion would bury the claim under
    the narrowing. One conversion at the call site says the same thing once.
    """

    return dict(record)


def _pair[T](gated: tuple[T, Mapping[str, object]]) -> tuple[T, dict[str, Any]]:
    """The same, for a gate that returns its canonical bytes beside the record."""

    canonical, record = gated
    return canonical, dict(record)


def _alpha(image: Image.Image, x: int, y: int) -> int:
    """One pixel's alpha. Pillow types a pixel as a union no checker can narrow."""

    return cast(tuple[int, int, int, int], image.getpixel((x, y)))[3]


def _bbox(data: bytes) -> tuple[int, int, int, int]:
    """The alpha bounding box a test drew something into, so it is never absent."""

    box = alpha_bbox(data)
    assert box is not None
    return box


def _rand(seed: int) -> Callable[[], float]:
    """A tiny deterministic generator so a test draws the same picture every time."""

    state = seed & 0xFFFFFFFF

    def step() -> float:
        nonlocal state
        state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
        return state / 4294967296.0

    return step


def _png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _prop(
    *,
    width: int = 300,
    height: int = 600,
    base_width: int | None = None,
    bottom_padding: int = 60,
    components: int = 1,
) -> bytes:
    """A plain upright object, optionally standing on a wider painted base."""

    image = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    mid = CANVAS[0] // 2
    bottom = CANVAS[1] - bottom_padding
    top = bottom - height
    for index in range(components):
        offset = (index - (components - 1) / 2) * (width + 40)
        draw.rectangle(
            [mid + offset - width // 2, top, mid + offset + width // 2, bottom],
            fill=(120, 90, 60, 255),
        )
    if base_width:
        band = max(4, height // 10)
        draw.rectangle(
            [mid - base_width // 2, bottom - band, mid + base_width // 2, bottom],
            fill=(90, 78, 54, 255),
        )
    return _png(image)


def _ground(*, vignette: bool = False, blotch: bool = False) -> bytes:
    image = Image.new("RGB", CANVAS, (110, 100, 74))
    draw = ImageDraw.Draw(image)
    for index in range(2000):
        angle = index * 2.399963
        radius = 12.0 * math.sqrt(index)
        x = int(CANVAS[0] / 2 + math.cos(angle) * radius) % CANVAS[0]
        y = int(CANVAS[1] / 2 + math.sin(angle) * radius) % CANVAS[1]
        draw.ellipse([x - 4, y - 4, x + 4, y + 4], fill=(104, 96, 70))
    if blotch:
        draw.ellipse([300, 300, 760, 760], fill=(210, 200, 170))
    if vignette:
        overlay = Image.new("L", CANVAS, 0)
        shade = ImageDraw.Draw(overlay)
        for step in range(CANVAS[0] // 2, 0, -8):
            shade.ellipse(
                [
                    CANVAS[0] // 2 - step,
                    CANVAS[1] // 2 - step,
                    CANVAS[0] // 2 + step,
                    CANVAS[1] // 2 + step,
                ],
                fill=int(200 * (step / (CANVAS[0] / 2)) ** 2),
            )
        image = Image.composite(Image.new("RGB", CANVAS, (12, 10, 8)), image, overlay)
    return _png(image.convert("RGBA"))


def _strip(
    heights: list[int],
    *,
    columns: int = 4,
    empty: int | None = None,
    feet: list[int] | None = None,
) -> bytes:
    """Blocks of the given heights on one ground line, or on ``feet`` (px up from the bottom)."""

    image = Image.new("RGBA", (1536, 1024), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    cell = 1536 // columns
    for index in range(columns):
        if index == empty:
            continue
        height = heights[index % len(heights)]
        lift = feet[index % len(feet)] if feet else 0
        left = index * cell + cell // 2 - 90
        bottom = 1024 - 12 - lift
        draw.rectangle([left, bottom - height, left + 180, bottom], fill=(80, 70, 100, 255))
    return _png(image)


def _flame_strip(
    *, columns: int = 4, rows: int = 4, jump_at: int | None = None, duplicate_at: int | None = None
) -> bytes:
    """Paint the lattice template the way an obedient provider would."""

    cell = templates.LATTICE_CELL_PX
    with Image.open(BytesIO(templates.lattice_template(columns, rows, cell))) as opened:
        image = opened.convert("RGBA")
    draw = ImageDraw.Draw(image)
    frames = columns * rows
    for index in range(frames):
        source = index
        if duplicate_at is not None and index == duplicate_at:
            source = index - 1
        phase = source / frames
        if jump_at is not None and index == jump_at:
            phase += 0.5
        x0 = (index % columns) * cell
        y0 = (index // columns) * cell
        mid = x0 + cell // 2
        base = y0 + int(cell * 0.9)
        for layer, colour in ((1.0, (232, 150, 46)), (0.66, (246, 202, 96))):
            lean = math.sin(phase * math.tau + layer) * cell * 0.16
            reach = 0.58 + 0.10 * math.sin(phase * math.tau + layer * 1.7)
            tip = base - int(cell * reach * layer)
            half = int(cell * (0.22 + 0.05 * math.cos(phase * math.tau)) * layer)
            draw.polygon(
                [(mid - half, base), (mid + int(lean), tip), (mid + half, base)],
                fill=(*colour, 255),
            )
    return _png(image)


# --- transparent canvases -------------------------------------------------------------


def test_a_clean_cutout_passes() -> None:
    facts = _facts(gates.gate_transparent_canvas(_prop(), width=CANVAS[0], height=CANVAS[1]))
    assert facts["visible_fraction"] > gates.VISIBLE_FRACTION_MIN
    assert facts["border_alpha_max"] == 0


def test_an_opaque_return_is_refused() -> None:
    opaque = _png(Image.new("RGBA", CANVAS, (30, 40, 50, 255)))
    with pytest.raises(gates.GateError) as error:
        _facts(gates.gate_transparent_canvas(opaque, width=CANVAS[0], height=CANVAS[1]))
    assert any("opaque" in reason for reason in error.value.reasons)


def test_a_subject_running_off_the_canvas_is_refused() -> None:
    image = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle([200, 200, 1023, 1023], fill=(120, 90, 60, 255))
    with pytest.raises(gates.GateError) as error:
        _facts(gates.gate_transparent_canvas(_png(image), width=CANVAS[0], height=CANVAS[1]))
    assert any("runs off the canvas" in reason for reason in error.value.reasons)


def test_the_wrong_canvas_size_is_refused() -> None:
    small = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    ImageDraw.Draw(small).rectangle([100, 100, 400, 400], fill=(120, 90, 60, 255))
    with pytest.raises(gates.GateError):
        _facts(gates.gate_transparent_canvas(_png(small), width=CANVAS[0], height=CANVAS[1]))


# --- props ----------------------------------------------------------------------------


def test_a_prop_reports_its_footprint_and_contact() -> None:
    facts = _facts(gates.gate_prop(_prop(), width=CANVAS[0], height=CANVAS[1], max_components=1))
    assert facts["footprint_width_px"] == pytest.approx(300, abs=4)
    assert facts["ground_contact"]["bottom_padding_pixels"] >= gates.BOTTOM_PADDING_MIN_PX
    assert facts["floor_plate_suspected"] is False


def test_a_prop_standing_on_a_painted_disc_is_flagged_not_refused() -> None:
    facts = _facts(
        gates.gate_prop(
            _prop(width=120, base_width=760), width=CANVAS[0], height=CANVAS[1], max_components=1
        )
    )
    assert facts["floor_plate_suspected"] is True
    assert facts["base_widening"] > gates.FLOOR_PLATE_WIDENING_MIN


def test_a_naturally_wide_base_is_not_flagged() -> None:
    # A boulder is widest at the ground; the flag must not fire on that or it
    # tells a reviewer nothing.
    facts = _facts(
        gates.gate_prop(
            _prop(width=700, height=400), width=CANVAS[0], height=CANVAS[1], max_components=1
        )
    )
    assert facts["floor_plate_suspected"] is False


def test_a_second_object_is_refused() -> None:
    with pytest.raises(gates.GateError) as error:
        _facts(
            gates.gate_prop(
                _prop(width=180, components=2), width=CANVAS[0], height=CANVAS[1], max_components=1
            )
        )
    assert any("separate objects" in reason for reason in error.value.reasons)


def test_a_prop_with_no_clear_space_under_it_is_refused() -> None:
    with pytest.raises(gates.GateError) as error:
        _facts(
            gates.gate_prop(
                _prop(bottom_padding=2), width=CANVAS[0], height=CANVAS[1], max_components=1
            )
        )
    assert any("clear space" in reason for reason in error.value.reasons)


# --- motion strips --------------------------------------------------------------------


def test_a_consistent_cycle_strip_passes_and_repacks() -> None:
    canonical, record = _pair(
        gates.gate_motion_atlas(
            _strip([600, 604, 598, 602]), width=1536, height=1024, columns=4, state="walk"
        )
    )
    assert record["cell_height_spread"] < gates.CELL_HEIGHT_SPREAD_CYCLE
    with Image.open(BytesIO(canonical)) as opened:
        # The repack sizes canonical cells to the art it found, so the canvas is
        # its own; what must hold is that it is still a four-column grid.
        assert opened.size[0] % 4 == 0
        assert opened.size[0] > 0 and opened.size[1] > 0


def test_a_reframed_cycle_strip_is_refused() -> None:
    with pytest.raises(gates.GateError) as error:
        _pair(
            gates.gate_motion_atlas(
                _strip([600, 600, 900, 600]), width=1536, height=1024, columns=4, state="walk"
            )
        )
    assert any("re-framed" in reason for reason in error.value.reasons)


def test_an_action_strip_is_allowed_more_variation_than_a_cycle() -> None:
    heights = [600, 600, 720, 600]
    with pytest.raises(gates.GateError):
        _pair(
            gates.gate_motion_atlas(
                _strip(heights), width=1536, height=1024, columns=4, state="walk"
            )
        )
    _canonical, record = _pair(
        gates.gate_motion_atlas(_strip(heights), width=1536, height=1024, columns=4, state="gather")
    )
    assert record["cell_height_spread_limit"] == gates.CELL_HEIGHT_SPREAD_ACTION


def test_a_bend_toward_the_camera_passes_and_a_moved_feet_line_does_not() -> None:
    # A front-facing gather drops the head by nearly half with the feet still
    # on the line: a pose, not a zoom. The same heights with the feet lifted
    # in one cell is a re-crop, and that is what the gate refuses.
    heights = [600, 420, 340, 600]
    _canonical, record = _pair(
        gates.gate_motion_atlas(_strip(heights), width=1536, height=1024, columns=4, state="gather")
    )
    assert record["cell_height_spread"] > 0.4
    assert record["cell_feet_line_spread"] == 0.0
    with pytest.raises(gates.GateError) as error:
        _pair(
            gates.gate_motion_atlas(
                _strip(heights, feet=[0, 0, 120, 0]),
                width=1536,
                height=1024,
                columns=4,
                state="gather",
            )
        )
    assert any("feet line" in reason for reason in error.value.reasons)
    # A cycle stays tight on height whatever its feet do.
    with pytest.raises(gates.GateError):
        _pair(
            gates.gate_motion_atlas(
                _strip(heights), width=1536, height=1024, columns=4, state="walk"
            )
        )


def test_an_empty_cell_is_refused() -> None:
    with pytest.raises(gates.GateError) as error:
        _pair(
            gates.gate_motion_atlas(
                _strip([600], empty=2), width=1536, height=1024, columns=4, state="idle"
            )
        )
    assert any("effectively empty" in reason for reason in error.value.reasons)


# --- ground ---------------------------------------------------------------------------


def test_an_even_ground_plate_passes() -> None:
    facts = _facts(gates.gate_ground_texture(_ground(), width=CANVAS[0], height=CANVAS[1]))
    assert facts["block_deviation"] < gates.GROUND_BLOCK_DEVIATION_MAX


def test_a_vignetted_ground_plate_is_refused() -> None:
    with pytest.raises(gates.GateError) as error:
        _facts(gates.gate_ground_texture(_ground(vignette=True), width=CANVAS[0], height=CANVAS[1]))
    assert error.value.reasons


def test_one_large_feature_is_refused() -> None:
    with pytest.raises(gates.GateError) as error:
        _facts(gates.gate_ground_texture(_ground(blotch=True), width=CANVAS[0], height=CANVAS[1]))
    assert any("large feature" in reason or "gradient" in reason for reason in error.value.reasons)


def test_mirroring_twice_makes_both_edges_exact() -> None:
    tiled, record = _pair(gates.mirror_repeat_2d(_ground()))
    assert record["period_width"] == CANVAS[0] * 2
    assert record["period_height"] == CANVAS[1] * 2
    edges = _facts(gates.gate_tileable_2d(tiled))
    assert edges["horizontal_edge_delta"] == 0.0
    assert edges["vertical_edge_delta"] == 0.0


def test_an_untiled_plate_is_refused_by_the_edge_gate() -> None:
    image = Image.new("RGB", CANVAS, (40, 40, 40))
    ImageDraw.Draw(image).rectangle([0, 0, 200, CANVAS[1]], fill=(230, 230, 230))
    with pytest.raises(gates.GateError):
        _facts(gates.gate_tileable_2d(_png(image.convert("RGBA"))))


def test_a_dark_plate_passes_only_under_the_water_band() -> None:
    image = Image.new("RGB", CANVAS, (40, 58, 62))
    draw = ImageDraw.Draw(image)
    rand = _rand(5)
    for _ in range(1500):
        x = int(rand() * CANVAS[0])
        y = int(rand() * CANVAS[1])
        draw.ellipse([x - 4, y - 4, x + 4, y + 4], fill=(52, 70, 74))
    data = _png(image.convert("RGBA"))
    with pytest.raises(gates.GateError):
        _facts(gates.gate_ground_texture(data, width=CANVAS[0], height=CANVAS[1]))
    facts = _facts(
        gates.gate_ground_texture(
            data, width=CANVAS[0], height=CANVAS[1], luma_range=gates.WATER_LUMA_RANGE
        )
    )
    assert facts["luma_mean"] < gates.GROUND_LUMA_RANGE[0]


# --- the macro plate --------------------------------------------------------------------


def _mottle(*, inked: bool = False, gradient: bool = False) -> bytes:
    image = Image.new("RGB", CANVAS, (128, 128, 128))
    draw = ImageDraw.Draw(image)
    rand = _rand(11)
    for _ in range(30):
        x = int(rand() * CANVAS[0])
        y = int(rand() * CANVAS[1])
        radius = int(CANVAS[0] * (0.12 + rand() * 0.18))
        shift = int((rand() - 0.5) * 50)
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=(128 + shift,) * 3)
    image = image.filter(ImageFilter.GaussianBlur(50))
    if inked:
        ink = ImageDraw.Draw(image)
        for step in range(0, CANVAS[0], 24):
            ink.line([(step, 0), (step + 40, CANVAS[1])], fill=(30, 30, 30), width=3)
    if gradient:
        pixels = image.load()
        assert pixels is not None
        for x in range(CANVAS[0]):
            gain = 0.4 + 1.2 * x / CANVAS[0]
            for y in range(0, CANVAS[1], 1):
                r, g, b = cast(tuple[int, int, int], pixels[x, y])
                pixels[x, y] = (
                    int(min(255, r * gain)),
                    int(min(255, g * gain)),
                    int(min(255, b * gain)),
                )
    return _png(image.convert("RGBA"))


def test_a_soft_mottle_passes_the_macro_gate() -> None:
    facts = _facts(gates.gate_macro_plate(_mottle(), width=CANVAS[0], height=CANVAS[1]))
    assert facts["edge_mean"] < gates.MACRO_EDGE_MEAN_MAX
    assert gates.MACRO_LUMA_RANGE[0] <= facts["luma_mean"] <= gates.MACRO_LUMA_RANGE[1]


def test_an_inked_plate_is_refused_as_a_macro() -> None:
    with pytest.raises(gates.GateError) as error:
        _facts(gates.gate_macro_plate(_mottle(inked=True), width=CANVAS[0], height=CANVAS[1]))
    assert any("lines or texture" in reason for reason in error.value.reasons)


def test_a_gradient_is_refused_as_a_macro() -> None:
    with pytest.raises(gates.GateError) as error:
        _facts(gates.gate_macro_plate(_mottle(gradient=True), width=CANVAS[0], height=CANVAS[1]))
    assert any("gradient" in reason for reason in error.value.reasons)


# --- the litter sheet ---------------------------------------------------------------------


def _litter_sheet(
    *, crossing: int | None = None, empty: int | None = None, contact: bool = False
) -> bytes:
    """Sixteen discs; with ``contact`` each wears a dark crescent along its lower edge."""

    columns = rows = 4
    cell = templates.LATTICE_CELL_PX
    # Painted the way an obedient provider would: on the transparent lattice,
    # leaving what it does not paint clear.
    image = Image.open(BytesIO(templates.lattice_template(columns, rows))).convert("RGBA")
    draw = ImageDraw.Draw(image)
    for index in range(columns * rows):
        if index == empty:
            continue
        cx = (index % columns) * cell + cell // 2
        cy = (index // columns) * cell + cell // 2
        radius = cell // 5
        if index == crossing:
            draw.ellipse(
                [cx - radius, cy - radius, cx + cell // 2 + 6, cy + radius], fill=(120, 90, 60, 255)
            )
        else:
            draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius], fill=(120, 90, 60, 255)
            )
            if contact:
                draw.chord(
                    [cx - radius, cy - radius, cx + radius, cy + radius],
                    20,
                    160,
                    fill=(40, 30, 20, 255),
                )
    return _png(image)


def test_a_clean_litter_sheet_passes_and_reports_every_cell() -> None:
    canonical, record = _pair(
        gates.gate_piece_sheet(
            _litter_sheet(), columns=4, rows=4, cell_px=templates.LATTICE_CELL_PX, native_alpha=True
        )
    )
    assert len(record["cells"]) == 16
    assert all(cell["bbox"] for cell in record["cells"])
    with Image.open(BytesIO(canonical)) as opened:
        assert opened.mode == "RGBA"
        assert opened.getchannel("A").getextrema()[0] == 0


def test_a_piece_on_a_guide_line_is_refused() -> None:
    with pytest.raises(gates.GateError) as error:
        _pair(
            gates.gate_piece_sheet(
                _litter_sheet(crossing=5),
                columns=4,
                rows=4,
                cell_px=templates.LATTICE_CELL_PX,
                native_alpha=True,
            )
        )
    assert any("guide line" in reason or "lattice" in reason for reason in error.value.reasons)


def test_an_empty_litter_cell_is_refused() -> None:
    with pytest.raises(gates.GateError) as error:
        _pair(
            gates.gate_piece_sheet(
                _litter_sheet(empty=9),
                columns=4,
                rows=4,
                cell_px=templates.LATTICE_CELL_PX,
                native_alpha=True,
            )
        )
    assert any("cell 9" in reason for reason in error.value.reasons)


# --- the prop sheet -------------------------------------------------------------------


def _prop_sheet(*, crossing: int | None = None, empty: int | None = None) -> bytes:
    """Four looks of one thing at one scale on a transparent canvas: tall, short, thin, wide."""

    columns = rows = 2
    cell = templates.SHEET_CELL_PX
    image = Image.new("RGBA", (columns * cell, rows * cell), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    shapes = [(140, 420), (140, 90), (40, 420), (300, 120)]  # (width, height)
    for index, (width, height) in enumerate(shapes):
        if index == empty:
            continue
        cx = (index % columns) * cell + cell // 2
        bottom = (index // columns) * cell + cell - 40
        right = cx + width // 2
        if index == crossing:
            right = (index % columns) * cell + cell + 4
        draw.rectangle([cx - width // 2, bottom - height, right, bottom], fill=(120, 90, 60, 255))
    return _png(image)


def test_a_prop_sheet_splits_into_one_gated_sprite_per_look() -> None:
    looks = ("grown", "stump", "sapling", "rubble")
    sprites, record = _pair(
        gates.gate_prop_sheet(
            _prop_sheet(),
            columns=2,
            rows=2,
            cell_px=templates.SHEET_CELL_PX,
            states=looks,
            max_components=1,
        )
    )
    assert set(sprites) == set(looks)
    assert [cell["state"] for cell in record["cells"]] == list(looks)
    inset = round(templates.SHEET_CELL_PX * gates.SHEET_CELL_INSET)
    for cell in record["cells"]:
        # A cell is its seam-to-seam crop plus transparent padding on its interior sides.
        assert cell["width"] == templates.SHEET_CELL_PX + inset
        assert cell["subject_height_px"] > 0
        assert cell["footprint_width_px"] > 0
        assert cell["bbox"]
        assert 0.0 < cell["center_x_normalized"] < 1.0
    # The short looks would fail the lone-sprite floors, and pass the sheet's.
    with Image.open(BytesIO(sprites["stump"])) as opened:
        assert opened.size == (templates.SHEET_CELL_PX + inset, templates.SHEET_CELL_PX + inset)
        assert opened.getchannel("A").getextrema() == (0, 255)


def test_a_look_that_reaches_its_cell_border_is_refused_by_name() -> None:
    with pytest.raises(gates.GateError) as error:
        _pair(
            gates.gate_prop_sheet(
                _prop_sheet(crossing=1),
                columns=2,
                rows=2,
                cell_px=templates.SHEET_CELL_PX,
                states=("a", "b", "c", "d"),
                max_components=1,
            )
        )
    assert any("cell 1 (b)" in reason for reason in error.value.reasons)


def test_an_empty_look_is_refused_and_the_others_still_report() -> None:
    with pytest.raises(gates.GateError) as error:
        _pair(
            gates.gate_prop_sheet(
                _prop_sheet(empty=2),
                columns=2,
                rows=2,
                cell_px=templates.SHEET_CELL_PX,
                states=("a", "b", "c", "d"),
                max_components=1,
            )
        )
    assert any("cell 2 (c)" in reason for reason in error.value.reasons)
    assert not any("cell 0" in reason for reason in error.value.reasons)


def test_the_sprite_gate_floors_are_unchanged_by_default() -> None:
    defaults = gates.gate_prop.__kwdefaults__
    assert defaults is not None
    assert defaults["ground_contact_min"] == gates.GROUND_CONTACT_MIN == 0.55
    assert defaults["visible_fraction_min"] == gates.VISIBLE_FRACTION_MIN == 0.01


# --- decals ---------------------------------------------------------------------------


def _blot(radius: float, wobble: float = 1.0, samples: int = 240) -> list[tuple[float, float]]:
    """A lopsided lumpy outline about the canvas centre; wobble 0 is a circle."""

    centre = CANVAS[0] / 2
    points: list[tuple[float, float]] = []
    for index in range(samples):
        t = 2 * math.pi * index / samples
        r = radius * (
            1
            + wobble
            * (0.18 * math.sin(3 * t + 0.4) + 0.12 * math.sin(5 * t) + 0.08 * math.sin(2 * t + 1))
        )
        points.append((centre + r * math.cos(t), centre + r * math.sin(t)))
    return points


def _feathered(points: list[tuple[float, float]], *, layers: int = 40) -> Image.Image:
    image = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    centre = CANVAS[0] / 2
    for layer in range(layers):
        shrink = 1.0 - layer / layers
        alpha = int(240 * (1.0 - shrink) ** 1.4) if layer else 6
        draw.polygon(
            [(centre + (x - centre) * shrink, centre + (y - centre) * shrink) for x, y in points],
            fill=(90, 70, 50, max(alpha, 6)),
        )
    return image


def test_a_feathered_lumpy_decal_passes() -> None:
    facts = _facts(
        gates.gate_decal(_png(_feathered(_blot(360))), width=CANVAS[0], height=CANVAS[1])
    )
    assert facts["soft_edge_share"] > gates.DECAL_SOFT_EDGE_SHARE_MIN
    assert facts["irregularity"] >= gates.DECAL_IRREGULARITY_MIN


def test_a_hard_cut_decal_is_refused() -> None:
    image = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    ImageDraw.Draw(image).polygon(_blot(330), fill=(90, 70, 50, 255))
    with pytest.raises(gates.GateError) as error:
        _facts(gates.gate_decal(_png(image), width=CANVAS[0], height=CANVAS[1]))
    assert any("hard-cut" in reason for reason in error.value.reasons)
    assert not any("disc" in reason for reason in error.value.reasons)


def test_a_round_decal_is_refused_however_well_it_feathers() -> None:
    """The v26 skirts fed every tree a disc, and the feather made no difference."""

    disc = _feathered(_blot(360, wobble=0.0))
    assert gates.decal_soft_edge_share(_png(disc)) > gates.DECAL_SOFT_EDGE_SHARE_MIN
    with pytest.raises(gates.GateError) as error:
        _facts(gates.gate_decal(_png(disc), width=CANVAS[0], height=CANVAS[1]))
    assert any("disc" in reason for reason in error.value.reasons)
    # Refused at generation time too, so a round attempt is retried, not published.
    with pytest.raises(gates.GateError):
        _facts(gates.gate_decal(_png(disc), width=CANVAS[0], height=CANVAS[1], soft_edge=False))
    assert gates.decal_irregularity(_png(disc)) < 0.02
    ellipse = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    ImageDraw.Draw(ellipse).ellipse([150, 250, 874, 774], fill=(90, 70, 50, 255))
    assert 0.05 < gates.decal_irregularity(_png(ellipse)) < gates.DECAL_IRREGULARITY_MIN


# --- the flame strip -------------------------------------------------------------------


def test_the_lattice_template_is_detectable() -> None:
    data = templates.lattice_template(4, 4)
    with Image.open(BytesIO(data)) as opened:
        assert opened.mode == "RGBA"
        # A clear pixel's colour is anything; the detector reads it over black.
        flat = Image.alpha_composite(Image.new("RGBA", opened.size, (0, 0, 0, 255)), opened)
        lattice = detect_guide_lattice(flat.convert("RGB"), expected_columns=4, expected_rows=4)
    assert len(lattice.x_lines) == 5
    assert len(lattice.y_lines) == 5
    assert lattice.x_maximum_residual_px < gates.LATTICE_RESIDUAL_MAX_PX


def test_a_closed_flame_cycle_passes() -> None:
    canonical, record = _pair(
        gates.gate_fx_strip(
            _flame_strip(), columns=4, rows=4, cell_px=templates.LATTICE_CELL_PX, native_alpha=True
        )
    )
    assert record["frames"] == 16
    assert record["mode"] == "loop"
    assert min(record["continuity_iou"]) >= gates.FLAME_CONTINUITY_IOU[0]
    with Image.open(BytesIO(canonical)) as opened:
        assert opened.mode == "RGBA"
        # The clear canvas must have stayed clear between the flames.
        assert opened.getchannel("A").getextrema()[0] == 0


def test_a_jump_cut_inside_the_strip_is_refused() -> None:
    with pytest.raises(gates.GateError) as error:
        _pair(
            gates.gate_fx_strip(
                _flame_strip(jump_at=7),
                columns=4,
                rows=4,
                cell_px=templates.LATTICE_CELL_PX,
                native_alpha=True,
            )
        )
    assert any("jump cut" in reason for reason in error.value.reasons)


def test_a_duplicated_frame_is_refused() -> None:
    with pytest.raises(gates.GateError) as error:
        _pair(
            gates.gate_fx_strip(
                _flame_strip(duplicate_at=5),
                columns=4,
                rows=4,
                cell_px=templates.LATTICE_CELL_PX,
                native_alpha=True,
            )
        )
    assert any("duplicated a frame" in reason for reason in error.value.reasons)


def test_a_missing_lattice_is_refused_as_a_gate_error() -> None:
    # An unruled sheet must come back as a refusal in our own words, not as a
    # bare ValueError from the shared detector.
    blank = Image.new("RGB", (1024, 1024), (255, 0, 255))
    with pytest.raises(gates.GateError) as error:
        _pair(
            gates.gate_fx_strip(
                _png(blank.convert("RGBA")),
                columns=4,
                rows=4,
                cell_px=templates.LATTICE_CELL_PX,
                native_alpha=True,
            )
        )
    assert any("guide lattice" in reason for reason in error.value.reasons)


def test_ping_pong_playback_walks_back_without_repeating_the_ends() -> None:
    assert gates.strip_playback_order(4, "loop") == [0, 1, 2, 3]
    assert gates.strip_playback_order(4, "ping_pong") == [0, 1, 2, 3, 2, 1]


# --- alpha canonicalisation -----------------------------------------------------------


def _soft_edged_sprite(
    *,
    body_rgb: tuple[int, int, int] = (200, 60, 40),
    exterior_rgb: tuple[int, int, int] = (9, 8, 5),
    top_alpha: int = 254,
) -> bytes:
    """A sprite shaped like what the provider actually returns.

    Body at alpha 254 rather than 255, a two-pixel soft rim, and an exterior
    that is almost clear but whose RGB is a dark olive rather than nothing.
    """

    image = Image.new("RGBA", CANVAS, (*exterior_rgb, 3))
    draw = ImageDraw.Draw(image)
    centre = CANVAS[0] // 2
    for step, alpha in ((210, 40), (206, 140), (202, top_alpha)):
        draw.ellipse(
            [centre - step, centre - step, centre + step, centre + step],
            fill=(*body_rgb, alpha),
        )
    return _png(image)


def test_the_body_is_lifted_to_full_opacity() -> None:
    data = _soft_edged_sprite()
    with Image.open(BytesIO(data)) as opened:
        assert opened.convert("RGBA").getchannel("A").getextrema()[1] == 254
    canonical, record = _pair(gates.canonicalize_sprite_alpha(data))
    assert record["source_alpha_extrema"][1] == 254
    assert record["canonical_alpha_extrema"][1] == 255
    with Image.open(BytesIO(canonical)) as opened:
        assert opened.convert("RGBA").getchannel("A").getextrema() == (0, 255)


def test_the_dark_exterior_is_cleared_in_colour_as_well_as_alpha() -> None:
    canonical, _record = _pair(gates.canonicalize_sprite_alpha(_soft_edged_sprite()))
    with Image.open(BytesIO(canonical)) as opened:
        image = opened.convert("RGBA")
    pixels = image.load()
    assert pixels is not None
    # A corner is far outside the disc, so it must be nothing at all -- not a
    # dark olive that a soft-edge renderer could surface.
    assert cast(tuple[int, int, int, int], pixels[4, 4]) == (0, 0, 0, 0)


def test_the_rim_takes_the_body_colour_not_the_exterior_colour() -> None:
    """This is the fringe that alpha-to-coverage would otherwise show."""

    canonical, _record = _pair(gates.canonicalize_sprite_alpha(_soft_edged_sprite()))
    with Image.open(BytesIO(canonical)) as opened:
        image = opened.convert("RGBA")
    pixels = image.load()
    assert pixels is not None
    rim = [
        (r, g, b)
        for y in range(0, image.height, 3)
        for x in range(0, image.width, 3)
        for (r, g, b, a) in (cast(tuple[int, int, int, int], pixels[x, y]),)
        if 9 <= a <= 200
    ]
    assert rim, "the fixture has no soft rim to measure"
    mean_red = sum(colour[0] for colour in rim) / len(rim)
    # The body is red at 200; the exterior olive is 9. The rim must have taken
    # the body's colour.
    assert mean_red > 120, mean_red


def test_canonicalisation_preserves_the_silhouette() -> None:
    data = _soft_edged_sprite()
    canonical, _record = _pair(gates.canonicalize_sprite_alpha(data))
    before = _facts(measure_alpha_ground_contact(data))
    after = _facts(measure_alpha_ground_contact(canonical))
    assert after["ground_contact_y_pixels"] == pytest.approx(
        before["ground_contact_y_pixels"], abs=2
    )


def test_the_feather_only_softens_inward() -> None:
    """A hard-cut decal gains an edge without the silhouette growing."""

    image = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((200, 200, 824, 824), fill=(90, 70, 50, 255))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    hard = buffer.getvalue()

    assert gates.decal_soft_edge_share(hard) < gates.DECAL_SOFT_EDGE_SHARE_MIN
    with pytest.raises(gates.GateError):
        _facts(gates.gate_decal(hard, width=1024, height=1024, irregularity_min=0.0))
    assert _facts(
        gates.gate_decal(hard, width=1024, height=1024, soft_edge=False, irregularity_min=0.0)
    )

    softened = gates.feather_decal_edge(hard)
    facts = _facts(gates.gate_decal(softened, width=1024, height=1024, irregularity_min=0.0))
    assert facts["soft_edge_share"] >= gates.DECAL_SOFT_EDGE_SHARE_MIN

    before = Image.open(BytesIO(hard)).getchannel("A")
    after = Image.open(BytesIO(softened)).getchannel("A")
    # never grows: no pixel is more opaque than it was drawn
    assert all(a <= b for a, b in zip(after.tobytes(), before.tobytes(), strict=True))


def _plate(*, contrast: int, spacing: int, radius: int) -> bytes:
    """A flat ground with a jittered grid of dots ``contrast`` levels away from it."""

    image = Image.new("RGB", CANVAS, (120, 108, 80))
    draw = ImageDraw.Draw(image)
    tone = (120 + contrast, 108 + contrast, 80 + contrast)
    index = 0
    for y in range(spacing // 2, CANVAS[1], spacing):
        for x in range(spacing // 2, CANVAS[0], spacing):
            index += 1
            jx, jy = (index * 37) % 23 - 11, (index * 53) % 23 - 11
            draw.ellipse(
                [x + jx - radius, y + jy - radius, x + jx + radius, y + jy + radius], fill=tone
            )
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


BUSY: Final[dict[str, int]] = {"contrast": 90, "spacing": 96, "radius": 30}
QUIET: Final[dict[str, int]] = {"contrast": 12, "spacing": 128, "radius": 24}


def test_a_busy_ground_plate_is_refused_and_a_quiet_one_passes() -> None:
    """Judged at play zoom: many high-contrast marks read as speckle, not ground."""

    with pytest.raises(gates.GateError) as error:
        _facts(
            gates.gate_ground_texture(
                _plate(**BUSY), width=CANVAS[0], height=CANVAS[1], texel_meters=2.0
            )
        )
    assert any("too busy" in reason for reason in error.value.reasons)
    facts = _facts(
        gates.gate_ground_texture(
            _plate(**QUIET), width=CANVAS[0], height=CANVAS[1], texel_meters=2.0
        )
    )
    assert facts["busyness_at_play"] < gates.GROUND_BUSYNESS_MAX
    # Without a texel there is no play scale, and no busy-ness verdict.
    facts = _facts(gates.gate_ground_texture(_plate(**BUSY), width=CANVAS[0], height=CANVAS[1]))
    assert "busyness_at_play" not in facts


def test_scaling_a_plate_up_does_not_make_it_quieter() -> None:
    """The A/B that settled it: a bigger texel doubles the marks, it does not calm them."""

    luma = gates._luma(gates._open(_plate(**BUSY)))
    at_two = gates.ground_busyness(luma, 2.0)
    at_four = gates.ground_busyness(luma, 4.0)
    assert at_four > at_two * 0.8


def test_contact_is_recorded_for_the_reviewer_and_refuses_nothing() -> None:
    """Two live runs showed the ratio reads colour and outline as light: a fact, not a gate."""

    contacts = ["pressed"] * 5 + ["fallen"] * 7 + ["growing"] * 4
    _canonical, record = _pair(
        gates.gate_piece_sheet(
            _litter_sheet(),
            columns=4,
            rows=4,
            cell_px=templates.LATTICE_CELL_PX,
            contacts=contacts,
            native_alpha=True,
        )
    )
    assert [cell["contact"] for cell in record["cells"]] == contacts
    plain = [cell["contact_ratio"] for cell in record["cells"]]
    assert all(ratio is not None for ratio in plain)
    _canonical, record = _pair(
        gates.gate_piece_sheet(
            _litter_sheet(contact=True),
            columns=4,
            rows=4,
            cell_px=templates.LATTICE_CELL_PX,
            contacts=contacts,
            native_alpha=True,
        )
    )
    shadowed = [cell["contact_ratio"] for cell in record["cells"]]
    # A crescent along the lower edge does move the number, which is why it is worth recording.
    assert all(after < before for after, before in zip(shadowed, plain, strict=True))
    assert gates.PIECE_CONTACT_GATED == ()


# --- weather --------------------------------------------------------------------------


def _quadrants(shapes: Sequence[tuple[float, float]]) -> bytes:
    """Four pieces, one per quarter; each shape is (width_share, height_share)."""

    image = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    half = CANVAS[0] // 2
    for index, (w, h) in enumerate(shapes):
        if w == 0 or h == 0:
            continue
        cx = (index % 2) * half + half // 2
        cy = (index // 2) * half + half // 2
        draw.rectangle(
            [
                cx - int(half * w / 2),
                cy - int(half * h / 2),
                cx + int(half * w / 2),
                cy + int(half * h / 2),
            ],
            fill=(240, 236, 220, 255),
        )
    return _png(image)


def test_the_quadrant_sheet_gate_wants_one_piece_per_quarter_and_can_ask_for_tall() -> None:
    kinds = ("a", "b", "c", "d")
    facts = _facts(
        gates.gate_quadrant_sheet(
            _quadrants([(0.4, 0.4)] * 4),
            width=CANVAS[0],
            height=CANVAS[1],
            kinds=kinds,
            coverage_range=gates.SPLASH_CELL_COVERAGE,
        )
    )
    assert [cell["kind"] for cell in facts["cells"]] == list(kinds)
    assert facts["cells"][3]["x"] == CANVAS[0] // 2 and facts["cells"][3]["y"] == CANVAS[1] // 2
    with pytest.raises(gates.GateError, match=r"cell 2 \(c\) is empty"):
        _facts(
            gates.gate_quadrant_sheet(
                _quadrants([(0.4, 0.4), (0.4, 0.4), (0.0, 0.0), (0.4, 0.4)]),
                width=CANVAS[0],
                height=CANVAS[1],
                kinds=kinds,
                coverage_range=gates.SPLASH_CELL_COVERAGE,
            )
        )
    with pytest.raises(gates.GateError, match="reaches a half line"):
        _facts(
            gates.gate_quadrant_sheet(
                _quadrants([(0.98, 0.4), (0.4, 0.4), (0.4, 0.4), (0.4, 0.4)]),
                width=CANVAS[0],
                height=CANVAS[1],
                kinds=kinds,
                coverage_range=gates.SPLASH_CELL_COVERAGE,
            )
        )
    # Bolts: tall and spanning most of the quarter; a splash-shaped sheet is refused.
    tall = _facts(
        gates.gate_quadrant_sheet(
            _quadrants([(0.12, 0.8)] * 4),
            width=CANVAS[0],
            height=CANVAS[1],
            kinds=kinds,
            coverage_range=gates.STRIKE_CELL_COVERAGE,
            tallness_min=gates.STRIKE_TALLNESS_MIN,
            span_min=gates.STRIKE_SPAN_MIN,
        )
    )
    assert all(cell["bbox"] for cell in tall["cells"])
    with pytest.raises(gates.GateError, match="not 2 times taller than wide"):
        _facts(
            gates.gate_quadrant_sheet(
                _quadrants([(0.4, 0.4)] * 4),
                width=CANVAS[0],
                height=CANVAS[1],
                kinds=kinds,
                coverage_range=gates.STRIKE_CELL_COVERAGE,
                tallness_min=gates.STRIKE_TALLNESS_MIN,
                span_min=gates.STRIKE_SPAN_MIN,
            )
        )


def test_a_two_cell_sheet_lays_its_cells_as_halves() -> None:
    image = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle([240, 80, 270, 940], fill=(236, 232, 220, 255))
    draw.ellipse([720, 470, 810, 560], fill=(196, 214, 222, 255))
    facts = _facts(
        gates.gate_quadrant_sheet(
            _png(image),
            width=CANVAS[0],
            height=CANVAS[1],
            kinds=("streak", "drop"),
            coverage_range=gates.DROPS_CELL_COVERAGE,
        )
    )
    assert [(c["kind"], c["x"], c["w"], c["h"]) for c in facts["cells"]] == [
        ("streak", 0, 512, 1024),
        ("drop", 512, 512, 1024),
    ]
    # A streak that runs to the canvas top is fine; one that crosses the middle is not.
    draw.rectangle([500, 300, 530, 700], fill=(236, 232, 220, 255))
    with pytest.raises(gates.GateError, match="reaches a half line"):
        _facts(
            gates.gate_quadrant_sheet(
                _png(image),
                width=CANVAS[0],
                height=CANVAS[1],
                kinds=("streak", "drop"),
                coverage_range=gates.DROPS_CELL_COVERAGE,
            )
        )


def test_a_sheet_is_cut_at_the_emptiest_seam_near_the_half_line() -> None:
    """The snag's roots sat under the midline eighteen times; the cut moves, not the tree."""

    size, half = 1024, 512
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    ink = (120, 110, 100, 255)
    # Top row: two tall trunks whose feet straddle the midline by 14 px.
    for cx in (256, 768):
        draw.rectangle([cx - 40, 90, cx + 40, half + 14], fill=ink)
        draw.rectangle([cx - 90, half - 6, cx + 90, half + 14], fill=ink)
    # Bottom row: two short stumps starting 40 px under the midline.
    for cx in (256, 768):
        draw.rectangle([cx - 60, half + 40, cx + 60, size - 60], fill=ink)
    sprites, record = _pair(
        gates.gate_prop_sheet(
            _png(image),
            columns=2,
            rows=2,
            cell_px=half,
            states=("standing", "leaning", "broken", "stump"),
            max_components=3,
        )
    )
    assert set(sprites) == {"standing", "leaning", "broken", "stump"}
    y0, seam, y1 = record["seams"]["y"]
    assert (y0, y1) == (0, size) and half + 14 < seam < half + 40
    inset = round(half * gates.SHEET_CELL_INSET)
    assert record["cells"][0]["h"] == seam + inset and record["cells"][2]["y"] == seam
    assert record["cells"][0]["padding"] == [0, 0, inset, inset]
    assert record["seams"]["x"] == [0, half, size]
    # A look that crosses every candidate line is still refused.
    draw.rectangle([256 - 20, half - 100, 256 + 20, half + 100], fill=ink)
    with pytest.raises(gates.GateError, match="crosses the seam"):
        _pair(
            gates.gate_prop_sheet(
                _png(image),
                columns=2,
                rows=2,
                cell_px=half,
                states=("standing", "leaning", "broken", "stump"),
                max_components=3,
            )
        )


def test_an_icon_sheet_may_fill_its_cells_fuller_than_litter() -> None:
    """A plump glyph at two thirds of its cell passes the icon band and fails the litter's."""

    columns = rows = 4
    cell = templates.LATTICE_CELL_PX
    image = Image.open(BytesIO(templates.lattice_template(columns, rows))).convert("RGBA")
    draw = ImageDraw.Draw(image)
    for index in range(columns * rows):
        cx = (index % columns) * cell + cell // 2
        cy = (index // columns) * cell + cell // 2
        radius = int(cell * 0.44)  # covers ~61 % of the cell, clear of the 3 % inset
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=(200, 120, 60, 255))
    data = _png(image)
    _canonical, record = _pair(
        gates.gate_piece_sheet(
            data,
            columns=4,
            rows=4,
            cell_px=cell,
            native_alpha=True,
            coverage=gates.ICON_CELL_COVERAGE,
        )
    )
    assert all(0.55 < c["coverage"] < 0.75 for c in record["cells"])
    with pytest.raises(gates.GateError) as error:
        _pair(gates.gate_piece_sheet(data, columns=4, rows=4, cell_px=cell, native_alpha=True))
    assert any("outside 2%-60%" in reason for reason in error.value.reasons)


def test_a_season_look_is_set_on_its_summer_canvas_at_the_summers_width_and_foot() -> None:
    """A 512 summer sprite and a 1024 paintover are one drawing at two pixel scales:
    the fraction drift is near one, the look is resized to the summer's width, its
    foot lands on the summer's, and a cap that passes the top grows the canvas."""

    def sprite(size: int, box: tuple[int, int, int, int], cap: int = 0) -> bytes:
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle(box, fill=(90, 120, 60, 255))
        if cap:
            draw.rectangle((box[0], box[1] - cap, box[2], box[1]), fill=(240, 244, 250, 255))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    summer = sprite(512, (200, 100, 300, 460))
    winter = sprite(1024, (400, 200, 600, 920), cap=40)
    drift, reasons = _look_drift(summer, winter)
    assert (
        reasons == []
        and abs(drift["width_ratio"] - 1.0) < 0.02
        and 0.9 < drift["aspect_ratio"] < 1.0
    )
    out, placement = _normalise_look(summer, winter)
    assert abs(placement["scale"] - 0.5) < 0.01 and placement["grown_top_px"] == 0
    box = _bbox(out)
    # Within a pixel: the resample's edge is soft.
    assert (
        abs((box[2] - box[0]) - 101) <= 1
        and abs(box[3] - 461) <= 1
        and abs((box[0] + box[2]) // 2 - 250) <= 1
    )
    with Image.open(BytesIO(out)) as opened:
        assert opened.size == (512, 512)
    # A cap past the top grows the canvas rather than losing the cap.
    tall = sprite(1024, (400, 100, 600, 920), cap=100)
    out, placement = _normalise_look(summer, tall)
    with Image.open(BytesIO(out)) as opened:
        assert (
            opened.size[0] == 512
            and opened.size[1] > 512
            and placement["grown_top_px"] == opened.size[1] - 512
        )
    box = _bbox(out)
    assert box[1] <= 1 and abs(box[3] - (461 + placement["grown_top_px"])) <= 1
    # A different shape is refused: twice as wide for its height is not the same drawing.
    squat = sprite(1024, (200, 600, 800, 920))
    _drift, reasons = _look_drift(summer, squat)
    assert reasons and "width-to-height" in reasons[0]


def test_a_fabric_plate_is_judged_against_the_reference_and_a_field_against_speckle() -> None:
    """Pass five: the reference turf measures 0.10 to 0.13 by the gate's own metric."""

    package = load_package(PACKAGE)
    forest = package.biome("forest_floor")
    assert forest.material == "fabric"
    assert plate_busyness_max(forest) == gates.FABRIC_BUSYNESS_MAX == 0.14
    field = replace(forest, material="field")
    assert plate_busyness_max(field) == gates.GROUND_BUSYNESS_MAX == 0.062
    assert plate_gate_kwargs(forest)["luma_range"] == gates.FABRIC_LUMA_RANGE == (0.20, 0.84)
    assert "luma_range" not in plate_gate_kwargs(field)


def test_a_guide_ghost_inside_a_cut_cell_is_the_lattice_and_not_the_piece() -> None:
    """The plant sheets came back with the cyan guides glowing a few pixels into
    every cell; a pixel in the guide's colour is cleared whatever its alpha, and a
    dark plant pixel in the same place is kept."""

    cell = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    for x in range(64):
        cell.putpixel((x, 0), (30, 165, 150, 157))
        cell.putpixel((x, 1), (19, 83, 77, 144))
    cell.putpixel((32, 32), (40, 70, 30, 255))
    cell.putpixel((32, 63), (40, 70, 30, 255))
    gates._clear_guide_ghost(cell)
    assert _alpha(cell, 10, 0) == 0
    assert _alpha(cell, 10, 1) == 144, "a dark teal blend is not the guide's colour and stays"
    assert _alpha(cell, 32, 32) == 255 and _alpha(cell, 32, 63) == 255


def test_a_sheet_cell_keeps_its_opaque_core_and_rim_and_loses_its_halo() -> None:
    """The plant draws paint a dark semi-transparent haze round every plant."""

    cell = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(cell)
    draw.ellipse((8, 8, 56, 56), fill=(20, 20, 20, 180))  # the halo
    draw.rectangle((24, 24, 40, 40), fill=(40, 90, 30, 255))  # the plant
    draw.rectangle((23, 23, 41, 41), outline=(40, 90, 30, 120))  # its antialiased rim
    draw.rectangle((10, 10, 12, 12), fill=(20, 20, 20, 255))  # an opaque fleck of the halo
    out, share = gates.strip_halo(cell)
    assert _alpha(out, 11, 11) == 0, "an opaque speck smaller than a leaf is halo"
    assert _alpha(out, 32, 32) == 255
    assert _alpha(out, 23, 32) == 120, "the rim within two pixels of the core stays"
    assert _alpha(out, 12, 32) == 0, "the halo goes"
    assert 0.5 < share < 0.95
