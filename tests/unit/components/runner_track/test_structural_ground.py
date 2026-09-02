"""Structural runner ground is painted freely but admitted to authored geometry."""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from typing import cast

import pytest
from PIL import Image, ImageDraw

from stage_gen.components._game_input import AuthoredContractLoadError
from stage_gen.components.runner_track import (
    STRUCTURAL_GROUND_CELL_PX,
    STRUCTURAL_GROUND_GUIDE_HEIGHT,
    STRUCTURAL_GROUND_GUIDE_WIDTH,
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

from ..._runner_fixture import WIDE_FLAT_ROWS, chunk_toml, runner_track_toml


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
    with Image.open(BytesIO(guide)) as opened:
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

    # The unmodified deterministic guide is itself a valid native-alpha
    # paintover source, which keeps the focused test provider-free.
    source = validate_structural_ground_source(
        first_guide,
        occupancy=PITTED_ROWS,
        walk_surface_row=5,
        guide=first_guide,
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
        second_guide,
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
        )


def test_source_admission_rejects_effectively_invisible_provider_paint() -> None:
    guide, _ = _guide()
    with Image.open(BytesIO(guide)) as opened:
        nearly_invisible = opened.convert("RGBA")
    alpha = nearly_invisible.getchannel("A").point(lambda value: 1 if value else 0)
    nearly_invisible.putalpha(alpha)

    with pytest.raises(ValueError, match="meaningful opacity"):
        validate_structural_ground_source(
            _png(nearly_invisible),
            occupancy=PITTED_ROWS,
            walk_surface_row=5,
            guide=guide,
        )


def test_source_admission_requires_each_common_apron_independently() -> None:
    guide, report = _guide()
    layout = cast(dict[str, int], report["layout"])
    with Image.open(BytesIO(guide)) as opened:
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
        )


def test_source_admission_requires_every_authored_solid_cell_to_be_painted() -> None:
    guide, report = _guide()
    layout = cast(dict[str, int], report["layout"])
    with Image.open(BytesIO(guide)) as opened:
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


def test_track_v3_closes_over_atlas_and_structural_modes_and_retires_v2() -> None:
    atlas = runner_track_toml(chunk_toml("flat", WIDE_FLAT_ROWS)).encode()
    loaded_atlas = load_runner_track_bytes(atlas)
    assert loaded_atlas.schema_version == 3
    assert loaded_atlas.kind == "runner-track-v3"
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
    assert loaded.schema_version == 3
    assert loaded.kind == "runner-track-v3"
    assert loaded.ground.mode == "runner-structural-ground-v1"

    retired = atlas.replace(b"schema_version = 3", b"schema_version = 2").replace(
        b'kind = "runner-track-v3"', b'kind = "runner-track-v2"'
    )
    with pytest.raises(AuthoredContractLoadError, match="Input should be 3"):
        load_runner_track_bytes(retired)
