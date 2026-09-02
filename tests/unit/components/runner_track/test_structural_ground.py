"""Structural runner ground is painted freely but admitted to authored geometry."""

from __future__ import annotations

import math
from hashlib import sha256
from io import BytesIO
from typing import cast

import pytest
from PIL import Image, ImageChops, ImageDraw

from stage_gen.components._game_input import AuthoredContractLoadError
from stage_gen.components.runner_track import (
    DEFAULT_GROUND_PROJECTION,
    STRUCTURAL_GROUND_CELL_PX,
    STRUCTURAL_GROUND_GUIDE_HEIGHT,
    STRUCTURAL_GROUND_GUIDE_WIDTH,
    GroundProjection,
    RunnerStructuralGround,
    build_structural_ground_guide,
    canonicalize_structural_ground,
    canonicalize_structural_ground_seam_bridge,
    load_runner_track_bytes,
    structural_ground_material_identity,
    validate_structural_ground_canonical,
    validate_structural_ground_material_references,
    validate_structural_ground_seam_bridge,
    validate_structural_ground_source,
)
from stage_gen.components.runner_track.structural_ground import (
    diagonal_family_lean_degrees,
)

from ..._runner_fixture import (
    WIDE_FLAT_ROWS,
    chunk_toml,
    painted_over_guide,
    runner_track_toml,
)


def _png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


def _reference() -> bytes:
    image = Image.new("RGBA", (96, 96), (84, 65, 106, 255))
    for y in range(48):
        for x in range(96):
            image.putpixel((x, y), (146 + x // 8, 118 + y // 8, 94, 255))
    return _png(image)


REFERENCE = _reference()
REFERENCE_SHA256 = sha256(REFERENCE).hexdigest()
DIRECTION_SHA256 = sha256(b"structural-ground-test-direction").hexdigest()
MATERIAL_IDENTITY = structural_ground_material_identity(
    prompt="Pale mineral cap over dark greenhouse loam.",
    visual_direction_sha256=DIRECTION_SHA256,
    reference_sha256=[REFERENCE_SHA256],
)


PITTED_ROWS = [
    "000000000000",
    "000000000000",
    "000000000000",
    "000000000000",
    "000000001100",
    "111100001111",
    "111100001111",
    "111100001111",
]


def _guide(rows: list[str] = PITTED_ROWS) -> tuple[bytes, dict[str, object]]:
    return build_structural_ground_guide(
        rows,
        walk_surface_row=5,
        material_identity=MATERIAL_IDENTITY,
        material_references=[REFERENCE],
    )


def _source_with_distinct_right_apron(
    guide: bytes,
    report: dict[str, object],
) -> bytes:
    layout = cast(dict[str, int], report["layout"])
    with Image.open(BytesIO(painted_over_guide(guide))) as opened:
        source = opened.convert("RGBA")
    draw = ImageDraw.Draw(source)
    right_apron_left = (
        layout["left"] + (layout["apron_columns"] + layout["columns"]) * layout["cell_px"]
    )
    colours = ((246, 220, 172, 255), (224, 91, 67, 255))
    for apron_column, colour in enumerate(colours):
        left = right_apron_left + apron_column * layout["cell_px"]
        right = left + layout["cell_px"] - 1
        for row in range(5, layout["rows"]):
            top = layout["top"] + row * layout["cell_px"]
            bottom = top + layout["cell_px"] - 1
            draw.rectangle((left, top, right, bottom), fill=colour)
            accent = colours[1 - apron_column]
            draw.line((left, top, right, bottom), fill=accent, width=5)
            draw.line((left, bottom, right, top), fill=accent, width=3)
    return _png(source)


def _bridge(
    rows: list[str] = PITTED_ROWS,
) -> tuple[bytes, dict[str, object], bytes, bytes]:
    guide, guide_report = _guide(rows)
    source = _source_with_distinct_right_apron(guide, guide_report)
    bridge, report = canonicalize_structural_ground_seam_bridge(
        source,
        occupancy=rows,
        walk_surface_row=5,
        material_identity=MATERIAL_IDENTITY,
        material_references=[REFERENCE],
        guide=guide,
    )
    return bridge, report, source, guide


def test_guide_and_canonicalization_are_deterministic_and_geometry_exact() -> None:
    first_guide, first_report = _guide()
    second_guide, second_report = _guide()
    assert first_guide == second_guide
    assert first_report == second_report
    assert first_report["geometry_authority"] == "authored_occupancy"
    assert first_report["layout"] == {
        "canvas_width": 1536,
        "canvas_height": 1024,
        "cell_px": 92,
        "left": 32,
        "top": 144,
        "columns": 12,
        "rows": 8,
        "apron_columns": 2,
    }
    layout = cast(dict[str, int], first_report["layout"])
    with Image.open(BytesIO(first_guide)) as guide_image:
        cell_px = layout["cell_px"]
        left = layout["left"]
        top = layout["top"]
        apron_width = layout["apron_columns"] * cell_px
        grid_height = layout["rows"] * cell_px
        central_width = layout["columns"] * cell_px
        left_apron = guide_image.crop((left, top, left + apron_width, top + grid_height))
        right_left = left + apron_width + central_width
        right_apron = guide_image.crop(
            (right_left, top, right_left + apron_width, top + grid_height)
        )
        assert left_apron.tobytes() == right_apron.tobytes()

    # A painted-over guide keeps this focused test provider-free. The guide
    # itself no longer qualifies, and that reversal is the point: its colours
    # are registration, so a source still wearing them is a painting that went
    # around the guide rather than over it.
    source = validate_structural_ground_source(
        painted_over_guide(first_guide),
        occupancy=PITTED_ROWS,
        walk_surface_row=5,
        guide=first_guide,
        material_identity=MATERIAL_IDENTITY,
        material_references=[REFERENCE],
    )
    assert source["alpha_min"] == 0
    assert source["alpha_max"] == 255

    bridge, bridge_report, painted_source, _bridge_guide = _bridge()
    bridge_facts = validate_structural_ground_seam_bridge(
        bridge, rows=len(PITTED_ROWS), walk_surface_row=5
    )
    assert bridge_facts["width"] == 2 * STRUCTURAL_GROUND_CELL_PX
    assert bridge_facts["height"] == len(PITTED_ROWS) * STRUCTURAL_GROUND_CELL_PX
    assert bridge_facts["alpha_geometry_exact"] is True
    assert bridge_report["canonical"] == bridge_facts
    assert bridge_report["source_apron"] == {
        "side": "right",
        "columns": 2,
        "solid_coverage": 1.0,
    }

    canonical, report = canonicalize_structural_ground(
        painted_source,
        occupancy=PITTED_ROWS,
        walk_surface_row=5,
        material_identity=MATERIAL_IDENTITY,
        material_references=[REFERENCE],
        guide=first_guide,
        seam_bridge=bridge,
    )
    facts = validate_structural_ground_canonical(
        canonical,
        occupancy=PITTED_ROWS,
        walk_surface_row=5,
        seam_bridge=bridge,
    )
    assert facts["width"] == len(PITTED_ROWS[0]) * STRUCTURAL_GROUND_CELL_PX
    assert facts["height"] == len(PITTED_ROWS) * STRUCTURAL_GROUND_CELL_PX
    assert facts["alpha_geometry_exact"] is True
    assert report["geometry_authority"] == "authored_occupancy"
    assert report["canonical"] == facts


def test_material_reference_admission_rejects_a_fully_transparent_image() -> None:
    transparent = _png(Image.new("RGBA", (96, 96), (80, 70, 60, 0)))
    with pytest.raises(ValueError, match="have no visible pixels"):
        validate_structural_ground_material_references([transparent])


def test_every_pair_reconstructs_one_shared_generated_two_column_bridge() -> None:
    bridge, bridge_report, first_source, first_guide = _bridge(PITTED_ROWS)
    first, first_report = canonicalize_structural_ground(
        first_source,
        occupancy=PITTED_ROWS,
        walk_surface_row=5,
        material_identity=MATERIAL_IDENTITY,
        material_references=[REFERENCE],
        guide=first_guide,
        seam_bridge=bridge,
    )
    second_guide, _ = _guide(WIDE_FLAT_ROWS)
    second, second_report = canonicalize_structural_ground(
        painted_over_guide(second_guide),
        occupancy=WIDE_FLAT_ROWS,
        walk_surface_row=5,
        material_identity=MATERIAL_IDENTITY,
        material_references=[REFERENCE],
        guide=second_guide,
        seam_bridge=bridge,
    )
    first_canonical = cast(dict[str, object], first_report["canonical"])
    second_canonical = cast(dict[str, object], second_report["canonical"])
    first_seam = cast(dict[str, object], first_canonical["seam"])
    second_seam = cast(dict[str, object], second_canonical["seam"])
    bridge_canonical = cast(dict[str, object], bridge_report["canonical"])
    bridge_roles = cast(dict[str, object], bridge_canonical["roles"])
    expected_left = cast(dict[str, object], bridge_roles["left"])
    expected_right = cast(dict[str, object], bridge_roles["right"])
    for seam in (first_seam, second_seam):
        assert seam["bridge_sha256"] == bridge_canonical["sha256"]
        assert seam["complementary_bridge_roles"] is True
        assert seam["left"] == expected_left
        assert seam["right"] == expected_right
    assert expected_left["sha256"] != expected_right["sha256"]

    with Image.open(BytesIO(bridge)) as opened:
        bridge_pixels = opened.convert("RGBA").tobytes()
    images = []
    for data in (first, second):
        with Image.open(BytesIO(data)) as opened:
            images.append(opened.convert("RGBA"))
    for left_chunk in images:
        for right_chunk in images:
            joined = Image.new(
                "RGBA",
                (2 * STRUCTURAL_GROUND_CELL_PX, left_chunk.height),
                (0, 0, 0, 0),
            )
            joined.paste(
                left_chunk.crop(
                    (
                        left_chunk.width - STRUCTURAL_GROUND_CELL_PX,
                        0,
                        left_chunk.width,
                        left_chunk.height,
                    )
                ),
                (0, 0),
            )
            joined.paste(
                right_chunk.crop((0, 0, STRUCTURAL_GROUND_CELL_PX, right_chunk.height)),
                (STRUCTURAL_GROUND_CELL_PX, 0),
            )
            assert joined.tobytes() == bridge_pixels


def test_source_admission_requires_real_native_transparency() -> None:
    guide, _ = _guide()
    opaque = _png(
        Image.new(
            "RGBA",
            (STRUCTURAL_GROUND_GUIDE_WIDTH, STRUCTURAL_GROUND_GUIDE_HEIGHT),
            (80, 70, 60, 255),
        )
    )
    with pytest.raises(ValueError, match="transparent and visible"):
        validate_structural_ground_source(
            opaque,
            occupancy=PITTED_ROWS,
            walk_surface_row=5,
            guide=guide,
            material_identity=MATERIAL_IDENTITY,
            material_references=[REFERENCE],
        )


def test_source_admission_rejects_effectively_invisible_provider_paint() -> None:
    guide, _ = _guide()
    with Image.open(BytesIO(painted_over_guide(guide))) as opened:
        nearly_invisible = opened.convert("RGBA")
    alpha = nearly_invisible.getchannel("A").point(lambda value: 1 if value else 0)
    nearly_invisible.putalpha(alpha)

    with pytest.raises(ValueError, match="meaningful opacity"):
        validate_structural_ground_source(
            _png(nearly_invisible),
            occupancy=PITTED_ROWS,
            walk_surface_row=5,
            guide=guide,
            material_identity=MATERIAL_IDENTITY,
            material_references=[REFERENCE],
        )


def test_source_admission_requires_each_common_apron_independently() -> None:
    guide, report = _guide()
    layout = cast(dict[str, int], report["layout"])
    with Image.open(BytesIO(painted_over_guide(guide))) as opened:
        missing_right = opened.convert("RGBA")
    right_apron_left = (
        layout["left"] + (layout["apron_columns"] + layout["columns"]) * layout["cell_px"]
    )
    ImageDraw.Draw(missing_right).rectangle(
        (
            right_apron_left,
            layout["top"],
            right_apron_left + layout["apron_columns"] * layout["cell_px"] - 1,
            layout["top"] + layout["rows"] * layout["cell_px"] - 1,
        ),
        fill=(0, 0, 0, 0),
    )

    with pytest.raises(ValueError, match="common seam aprons"):
        validate_structural_ground_source(
            _png(missing_right),
            occupancy=PITTED_ROWS,
            walk_surface_row=5,
            guide=guide,
            material_identity=MATERIAL_IDENTITY,
            material_references=[REFERENCE],
        )


def test_source_admission_requires_every_authored_solid_cell_to_be_painted() -> None:
    guide, report = _guide()
    layout = cast(dict[str, int], report["layout"])
    with Image.open(BytesIO(painted_over_guide(guide))) as opened:
        missing_cell = opened.convert("RGBA")
    column = 2
    row = 5
    extended_column = layout["apron_columns"] + column
    left = layout["left"] + extended_column * layout["cell_px"]
    top = layout["top"] + row * layout["cell_px"]
    ImageDraw.Draw(missing_cell).rectangle(
        (
            left,
            top,
            left + layout["cell_px"] - 1,
            top + layout["cell_px"] - 1,
        ),
        fill=(0, 0, 0, 0),
    )

    with pytest.raises(ValueError, match="authored terrain cell unpainted"):
        validate_structural_ground_source(
            _png(missing_cell),
            occupancy=PITTED_ROWS,
            walk_surface_row=5,
            guide=guide,
            material_identity=MATERIAL_IDENTITY,
            material_references=[REFERENCE],
        )


def test_canonicalization_refuses_a_stale_or_unrelated_guide() -> None:
    guide, _ = _guide()
    bridge, _bridge_report, _source, _bridge_guide = _bridge()
    stale, _ = build_structural_ground_guide(
        PITTED_ROWS,
        walk_surface_row=5,
        material_identity=sha256(b"other material").hexdigest(),
        material_references=[REFERENCE],
    )
    with pytest.raises(ValueError, match="does not match its authored material and occupancy"):
        canonicalize_structural_ground(
            guide,
            occupancy=PITTED_ROWS,
            walk_surface_row=5,
            material_identity=MATERIAL_IDENTITY,
            material_references=[REFERENCE],
            guide=stale,
            seam_bridge=bridge,
        )


def test_seam_bridge_refuses_a_weak_selected_right_apron() -> None:
    guide, report = _guide()
    layout = cast(dict[str, int], report["layout"])
    with Image.open(BytesIO(guide)) as opened:
        weak = opened.convert("RGBA")
    right_apron_left = (
        layout["left"] + (layout["apron_columns"] + layout["columns"]) * layout["cell_px"]
    )
    ImageDraw.Draw(weak).rectangle(
        (
            right_apron_left,
            layout["top"],
            right_apron_left + layout["apron_columns"] * layout["cell_px"] - 1,
            layout["top"] + layout["rows"] * layout["cell_px"] - 1,
        ),
        fill=(0, 0, 0, 0),
    )
    with pytest.raises(ValueError, match="common seam aprons"):
        canonicalize_structural_ground_seam_bridge(
            _png(weak),
            occupancy=PITTED_ROWS,
            walk_surface_row=5,
            material_identity=MATERIAL_IDENTITY,
            material_references=[REFERENCE],
            guide=guide,
        )


def test_seam_bridge_validation_refuses_wrong_dimensions_and_alpha() -> None:
    wrong_width = _png(
        Image.new(
            "RGBA",
            (STRUCTURAL_GROUND_CELL_PX, len(PITTED_ROWS) * STRUCTURAL_GROUND_CELL_PX),
            (0, 0, 0, 0),
        )
    )
    with pytest.raises(ValueError, match="must be exactly 128x512"):
        validate_structural_ground_seam_bridge(
            wrong_width,
            rows=len(PITTED_ROWS),
            walk_surface_row=5,
        )
    wrong_alpha = _png(
        Image.new(
            "RGBA",
            (2 * STRUCTURAL_GROUND_CELL_PX, len(PITTED_ROWS) * STRUCTURAL_GROUND_CELL_PX),
            (255, 255, 255, 255),
        )
    )
    with pytest.raises(ValueError, match="alpha differs from authored occupancy"):
        validate_structural_ground_seam_bridge(
            wrong_alpha,
            rows=len(PITTED_ROWS),
            walk_surface_row=5,
        )


def test_track_v4_closes_over_atlas_and_structural_modes_and_retires_v3() -> None:
    atlas = runner_track_toml(chunk_toml("flat", WIDE_FLAT_ROWS)).encode()
    loaded_atlas = load_runner_track_bytes(atlas)
    assert loaded_atlas.schema_version == 4
    assert loaded_atlas.kind == "runner-track-v4"
    assert loaded_atlas.ground.mode == "terrain-atlas-3x3-minimal-v1"

    structural = (
        atlas.decode()
        .replace(
            'mode = "terrain-atlas-3x3-minimal-v1"',
            'mode = "runner-structural-ground-v1"',
            1,
        )
        .encode()
    )
    loaded = load_runner_track_bytes(structural)
    assert loaded.schema_version == 4
    assert loaded.kind == "runner-track-v4"
    assert loaded.ground.mode == "runner-structural-ground-v1"

    retired = atlas.replace(b"schema_version = 4", b"schema_version = 3").replace(
        b'kind = "runner-track-v4"', b'kind = "runner-track-v3"'
    )
    with pytest.raises(AuthoredContractLoadError, match="Input should be 4"):
        load_runner_track_bytes(retired)


def test_an_absent_projection_block_means_orthographic() -> None:
    """Field presence is not identity: a track written before the block still means something."""

    ground = RunnerStructuralGround(
        mode="runner-structural-ground-v1",
        reference_ids=["material"],
        vertical_fit="floor_to_screen_bottom",
        prompt="Pale mineral cap over dark greenhouse loam.",
    )
    assert ground.projection is None
    assert ground.projection_mode() == DEFAULT_GROUND_PROJECTION

    declared = ground.model_copy(update={"projection": GroundProjection(mode="orthographic_v1")})
    assert declared.projection_mode() == DEFAULT_GROUND_PROJECTION


def test_the_default_projection_does_not_move_material_identity() -> None:
    """An orthographic package must keep the guides and paintings it already paid for."""

    prompt = "Pale mineral cap over dark greenhouse loam."
    assert structural_ground_material_identity(
        prompt=prompt,
        visual_direction_sha256=DIRECTION_SHA256,
        reference_sha256=[REFERENCE_SHA256],
    ) == structural_ground_material_identity(
        prompt=prompt,
        visual_direction_sha256=DIRECTION_SHA256,
        reference_sha256=[REFERENCE_SHA256],
        projection=DEFAULT_GROUND_PROJECTION,
    )


def test_source_admission_refuses_guide_paint_left_on_the_walk_surface() -> None:
    """The defect that shipped: the guide's cap band surviving as artwork.

    Every coverage check passes here, because guide pixels are opaque and the
    cell is fully covered. Only an authorship check can see it.
    """

    guide, report = _guide()
    layout = cast(dict[str, int], report["layout"])
    palette = cast(dict[str, list[int]], report["palette"])
    with Image.open(BytesIO(painted_over_guide(guide))) as opened:
        residual = opened.convert("RGBA")
    draw = ImageDraw.Draw(residual)
    cap = tuple(palette["cap_rgb"])
    for column in range(layout["apron_columns"] * 2 + layout["columns"]):
        left = layout["left"] + column * layout["cell_px"]
        top = layout["top"] + 5 * layout["cell_px"]
        draw.rectangle(
            (left, top, left + layout["cell_px"] - 1, top + layout["cell_px"] // 4),
            fill=(*cap, 255),
        )

    with pytest.raises(ValueError, match="guide colour visible"):
        validate_structural_ground_source(
            _png(residual),
            occupancy=PITTED_ROWS,
            walk_surface_row=5,
            guide=guide,
            material_identity=MATERIAL_IDENTITY,
            material_references=[REFERENCE],
        )


def test_source_admission_refuses_a_tile_that_mixes_projections() -> None:
    """Receding edges that lean opposite ways are two projection systems in one tile."""

    guide, report = _guide()
    layout = cast(dict[str, int], report["layout"])
    with Image.open(BytesIO(painted_over_guide(guide))) as opened:
        splayed = opened.convert("RGBA")
    body_left = layout["left"] + layout["apron_columns"] * layout["cell_px"]
    body_right = body_left + layout["columns"] * layout["cell_px"]
    body_top = layout["top"] + 5 * layout["cell_px"]
    body_bottom = layout["top"] + layout["rows"] * layout["cell_px"]
    middle = (body_left + body_right) // 2
    height = body_bottom - body_top

    def _hatch(descending_right: bool) -> Image.Image:
        layer = Image.new("RGBA", splayed.size, (0, 0, 0, 0))
        pen = ImageDraw.Draw(layer)
        for offset in range(-height * 2, (body_right - body_left) + height * 2, 24):
            near = body_left + offset
            far = near + height
            ends = (near, body_top, far, body_bottom)
            pen.line(
                ends if descending_right else (far, body_top, near, body_bottom),
                fill=(240, 236, 220, 255),
                width=5,
            )
        return layer

    # Each half carries one lean, so the thirds disagree: the `\|/` splay.
    for layer, span in (
        (_hatch(True), (body_left, body_top, middle, body_bottom)),
        (_hatch(False), (middle, body_top, body_right, body_bottom)),
    ):
        patch = layer.crop(span)
        splayed.paste(patch, (span[0], span[1]), patch)

    with pytest.raises(ValueError, match="mixes projections"):
        validate_structural_ground_source(
            _png(splayed),
            occupancy=PITTED_ROWS,
            walk_surface_row=5,
            guide=guide,
            material_identity=MATERIAL_IDENTITY,
            material_references=[REFERENCE],
        )


def test_a_feathered_edge_publishes_material_rather_than_the_guide_palette() -> None:
    """The hairline on the row the avatar stands on was never the model's doing.

    A returned painting ramps its alpha over the first few pixels of every
    slab. The deterministic base under it is built from the guide's own cap and
    fill colours, so that ramp published a guide-coloured line along the
    walking surface - 0.805 of the first opaque scanline, while the whole tile
    measured 0.0075, which is why a share over an area never saw it.
    """

    bridge, _bridge_report, painted_source, guide = _bridge(PITTED_ROWS)
    _guide_bytes, guide_report = _guide()
    layout = cast(dict[str, int], guide_report["layout"])
    palette = cast(dict[str, list[int]], guide_report["palette"])
    cap = tuple(palette["cap_rgb"])

    with Image.open(BytesIO(painted_source)) as opened:
        feathered = opened.convert("RGBA")
    alpha = feathered.getchannel("A")
    surface_top = layout["top"] + 5 * layout["cell_px"]
    ramp = Image.new("L", feathered.size, 255)
    pen = ImageDraw.Draw(ramp)
    for step in range(4):
        pen.line(
            (0, surface_top + step, feathered.width, surface_top + step),
            fill=(step + 1) * 12,
        )
    feathered.putalpha(ImageChops.darker(alpha, ramp))

    canonical, _report = canonicalize_structural_ground(
        _png(feathered),
        occupancy=PITTED_ROWS,
        walk_surface_row=5,
        material_identity=MATERIAL_IDENTITY,
        material_references=[REFERENCE],
        guide=guide,
        seam_bridge=bridge,
    )
    with Image.open(BytesIO(canonical)) as opened:
        published = opened.convert("RGBA")
    row = 5 * STRUCTURAL_GROUND_CELL_PX
    pixels = published.load()
    assert pixels is not None
    opaque = [
        cast(tuple[int, int, int, int], pixels[x, row])
        for x in range(published.width)
        if cast(tuple[int, int, int, int], pixels[x, row])[3] >= 128
    ]
    assert opaque
    wearing_the_guide = [
        colour
        for colour in opaque
        if max(abs(colour[index] - cap[index]) for index in range(3)) <= 10
    ]
    assert not wearing_the_guide, f"{len(wearing_the_guide)} of {len(opaque)} still wear the cap"


def test_a_rim_wider_than_publication_can_underlay_is_refused() -> None:
    """The other side of the same rule, and the reason it is measured published.

    A feathered edge is covered by growing the painting's own colour under it.
    A rim wider than that reach is not a feathered edge, and no amount of
    reach fixes it: the nearest paint at a slab's top is its dark ink contour,
    so widening only trades a lilac band for a dark one. It has to be refused,
    and refused on what the raster would publish rather than on a coverage
    proxy over the source.
    """

    bridge, _bridge_report, painted_source, guide = _bridge(PITTED_ROWS)
    _guide_bytes, guide_report = _guide()
    layout = cast(dict[str, int], guide_report["layout"])
    with Image.open(BytesIO(painted_source)) as opened:
        stripped = opened.convert("RGBA")
    alpha = stripped.getchannel("A")
    surface_top = layout["top"] + 5 * layout["cell_px"]
    # Twelve per cent of a cell: past the six published pixels publication can
    # underlay, and still inside the gross coverage floor, so this refusal is
    # the published-raster one rather than the coverage one.
    bare = Image.new("L", stripped.size, 255)
    ImageDraw.Draw(bare).rectangle(
        (0, surface_top, stripped.width, surface_top + int(layout["cell_px"] * 0.12)),
        fill=0,
    )
    stripped.putalpha(ImageChops.darker(alpha, bare))

    with pytest.raises(ValueError, match="line of guide material in the published raster"):
        validate_structural_ground_source(
            _png(stripped),
            occupancy=PITTED_ROWS,
            walk_surface_row=5,
            guide=guide,
            material_identity=MATERIAL_IDENTITY,
            material_references=[REFERENCE],
        )
    assert bridge


def test_the_lean_estimator_resolves_the_angle_it_is_given() -> None:
    """The instrument the projection check reads used to answer 45 to everything.

    Pillow's kernel filter clamps into the source image's own range, so the
    8-bit Sobel pair this began with saturated on every strong edge. Families
    drawn at 20, 30, 45, 60 and 70 degrees all measured 45.0, every shipped
    tile reported a spread of exactly zero, and the tolerance above it could
    never refuse anything.
    """

    for drawn in (-60.0, -30.0, 20.0, 30.0, 45.0, 60.0, 70.0):
        canvas = Image.new("RGB", (300, 300), (240, 240, 240))
        pen = ImageDraw.Draw(canvas)
        run = 300.0 / math.tan(math.radians(drawn))
        for index in range(-12, 18):
            near = index * 40
            pen.line([(near, 300), (near + run, 0)], fill=(30, 30, 30), width=5)
        measured = diagonal_family_lean_degrees(canvas)
        assert measured is not None
        assert abs(measured - drawn) < 2.0, f"drawn {drawn}, measured {measured}"


def test_source_admission_admits_one_consistent_receding_family() -> None:
    """The refusal is two projections in one tile, never a diagonal as such.

    Its false-positive side is the one that costs provider attempts: greenhouse
    ground is full of honest diagonals - pipe bends, hanging vines, bracket
    chamfers - and a tile whose receding edges all run the same way is a
    parallel projection, which is the whole point.
    """

    guide, report = _guide()
    layout = cast(dict[str, int], report["layout"])
    with Image.open(BytesIO(painted_over_guide(guide))) as opened:
        hatched = opened.convert("RGBA")
    body_left = layout["left"] + layout["apron_columns"] * layout["cell_px"]
    body_right = body_left + layout["columns"] * layout["cell_px"]
    body_top = layout["top"] + 5 * layout["cell_px"]
    body_bottom = layout["top"] + layout["rows"] * layout["cell_px"]
    height = body_bottom - body_top

    layer = Image.new("RGBA", hatched.size, (0, 0, 0, 0))
    pen = ImageDraw.Draw(layer)
    for offset in range(-height * 2, (body_right - body_left) + height * 2, 24):
        near = body_left + offset
        pen.line((near, body_top, near + height, body_bottom), fill=(240, 236, 220, 255), width=5)
    patch = layer.crop((body_left, body_top, body_right, body_bottom))
    hatched.paste(patch, (body_left, body_top), patch)

    admitted = validate_structural_ground_source(
        _png(hatched),
        occupancy=PITTED_ROWS,
        walk_surface_row=5,
        guide=guide,
        material_identity=MATERIAL_IDENTITY,
        material_references=[REFERENCE],
    )
    spread = admitted["projection_lean_spread_degrees"]
    assert spread is not None
    assert cast(float, spread) < 20.0


def test_source_admission_refuses_a_part_painted_walking_surface() -> None:
    """The defect that shipped, at its real cause: an under-painted top row.

    The provider left the top of the walk-surface row transparent, and the
    canonicalizer's deterministic fallback filled it - with the guide's own cap
    and fill colours, so unpainted ground published AS guide material. The old
    0.20 per-cell floor admitted a cell four fifths made of fallback.
    """

    guide, report = _guide()
    layout = cast(dict[str, int], report["layout"])
    with Image.open(BytesIO(painted_over_guide(guide))) as opened:
        thin = opened.convert("RGBA")
    alpha = thin.getchannel("A")
    clear = Image.new("L", (thin.width, layout["cell_px"] // 3), 0)
    # Erase the top third of the walking surface, as the measured run did.
    alpha.paste(clear, (0, layout["top"] + 5 * layout["cell_px"]))
    thin.putalpha(alpha)

    with pytest.raises(ValueError, match="walking surface part-painted"):
        validate_structural_ground_source(
            _png(thin),
            occupancy=PITTED_ROWS,
            walk_surface_row=5,
            guide=guide,
            material_identity=MATERIAL_IDENTITY,
            material_references=[REFERENCE],
        )
