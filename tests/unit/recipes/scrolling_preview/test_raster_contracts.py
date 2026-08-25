from __future__ import annotations

import hashlib
import json
from io import BytesIO
from typing import Literal, cast

import pytest
from PIL import Image, ImageDraw

from stage_gen.recipes.scrolling_preview.raster_contracts import (
    GRID_EMPTY_CELL_ERROR_CODE,
    GRID_ISOLATION_ERROR_CODE,
    GRID_PAINTED_CELL_FRAME_ERROR_CODE,
    GRID_UNIFORM_SOURCE_ERROR_CODE,
    ISOLATED_ALPHA_CLEANUP_VERSION,
    ISOLATED_SUBJECT_FIT_VERSION,
    STRIP_CAMERA_DRIFT_ERROR_CODE,
    GridContract,
    GridSourceLayoutError,
    canonicalize_isolated_view_alpha,
    contract_for_runtime_role,
    contract_for_stage,
    fit_isolated_view_alpha,
    grid_semantic_contract,
    normalize_canonical_grid,
    remap_canonical_grid,
    validate_canonical_grid,
    validate_generated_source,
    validate_isolated_view_alpha,
    validate_isolated_view_source,
    validate_recoverable_isolated_view_alpha,
)


def test_generated_grid_source_requires_cells_but_allows_recoverable_gutter_contact() -> None:
    contract = GridContract(rows=2, columns=4, gutter=4)
    valid = _opaque_grid(160, 80, contract)

    facts = validate_generated_source(valid, width=160, height=80, contract=contract)

    assert facts["source_cells_nonempty"] == 8
    assert facts["source_boundaries_isolated"] is True

    with Image.open(BytesIO(valid)) as opened:
        missing = opened.convert("RGB")
    ImageDraw.Draw(missing).rectangle((120, 40, 159, 79), fill=(128, 128, 128))
    with pytest.raises(GridSourceLayoutError, match=r"grid cell \(1,3\) is empty") as caught:
        validate_generated_source(_png(missing), width=160, height=80, contract=contract)
    assert caught.value.code == GRID_EMPTY_CELL_ERROR_CODE
    assert caught.value.row == 1
    assert caught.value.column == 3
    assert isinstance(caught.value, ValueError)
    assert caught.value.as_dict() == {
        "code": GRID_EMPTY_CELL_ERROR_CODE,
        "message": f"{GRID_EMPTY_CELL_ERROR_CODE}: grid cell (1,3) is empty",
        "row": 1,
        "column": 3,
    }

    with Image.open(BytesIO(valid)) as opened:
        crossing = opened.convert("RGB")
    crossing.putpixel((40, 10), (220, 40, 20))
    crossing_facts = validate_generated_source(
        _png(crossing), width=160, height=80, contract=contract
    )
    assert crossing_facts["source_cells_recoverable"] is True
    assert crossing_facts["source_boundaries_isolated"] is False
    assert crossing_facts["source_gutter_pixels_painted"] == 1

    crossing.putpixel((39, 10), (220, 40, 20))
    with pytest.raises(GridSourceLayoutError, match="connected foreground component") as caught:
        validate_generated_source(_png(crossing), width=160, height=80, contract=contract)
    assert caught.value.code == GRID_ISOLATION_ERROR_CODE
    assert caught.value.row is None
    assert caught.value.column is None


def test_uniform_grid_source_has_narrow_typed_layout_failure() -> None:
    contract = GridContract(rows=1, columns=3, gutter=4)
    source = Image.new("RGB", (120, 40), (128, 128, 128))

    with pytest.raises(
        GridSourceLayoutError,
        match="grid source is a uniform background field",
    ) as caught:
        validate_generated_source(_png(source), width=120, height=40, contract=contract)

    assert caught.value.code == GRID_UNIFORM_SOURCE_ERROR_CODE
    assert caught.value.row is None
    assert caught.value.column is None
    assert caught.value.as_dict() == {
        "code": GRID_UNIFORM_SOURCE_ERROR_CODE,
        "message": (f"{GRID_UNIFORM_SOURCE_ERROR_CODE}: grid source is a uniform background field"),
    }


def test_continuous_tileset_source_is_not_recoverable_by_cell_slicing() -> None:
    contract = contract_for_stage("tileset")
    assert contract is not None
    source = Image.new("RGB", (240, 80), (128, 128, 128))
    draw = ImageDraw.Draw(source)
    for row in range(4):
        draw.rectangle((0, row * 20 + 5, 239, row * 20 + 14), fill=(40, 120, 180))

    with pytest.raises(ValueError, match="connected foreground component"):
        validate_generated_source(_png(source), width=240, height=80, contract=contract)


def test_tileset_source_must_match_each_documented_semantic_role() -> None:
    contract = contract_for_stage("tileset")
    assert contract is not None
    source = _tileset_template_source(contract)

    facts = validate_generated_source(_png(source), width=240, height=80, contract=contract)

    assert facts["tileset_roles_validated"] == 48
    assert facts["tileset_semantic_contract"] == grid_semantic_contract(contract, 240, 80)

    wrong_role = source.copy()
    draw = ImageDraw.Draw(wrong_role)
    draw.rectangle((0, 40, 19, 59), fill=(128, 128, 128))
    draw.rectangle((2, 42, 17, 57), fill=(40, 120, 180))
    with pytest.raises(ValueError, match="semantic role side-left"):
        validate_generated_source(_png(wrong_role), width=240, height=80, contract=contract)


def test_generic_grid_normalization_isolates_all_cells() -> None:
    contract = GridContract(rows=2, columns=4, gutter=3)
    source = Image.new("RGBA", (160, 80), (0, 0, 0, 0))
    draw = ImageDraw.Draw(source)
    for row in range(2):
        for column in range(4):
            left = column * 40
            top = row * 40
            draw.rectangle(
                (left, top, left + 24, top + 30),
                fill=(30 + column * 30, 80 + row * 50, 180, 255),
            )

    normalized, facts = normalize_canonical_grid(_png(source), contract)

    assert facts["cells_nonempty"] == 8
    assert facts["boundaries_isolated"] is True
    assert validate_canonical_grid(normalized, contract)["gutter_pixels"] == 3


def test_edge_touching_alpha_is_fitted_and_exact_gutters_are_cleared() -> None:
    contract = GridContract(rows=2, columns=4, gutter=3)
    source = Image.new("RGBA", (160, 80), (0, 0, 0, 0))
    draw = ImageDraw.Draw(source)
    for row in range(2):
        for column in range(4):
            draw.rectangle(
                (column * 40, row * 40, (column + 1) * 40 - 1, (row + 1) * 40 - 1),
                fill=(40 + column * 20, 80 + row * 20, 180, 255),
            )
    source_data = _png(source)

    normalized, facts = normalize_canonical_grid(source_data, contract)

    record = facts["grid_normalization"]
    assert isinstance(record, dict)
    assert record["version"] == "per-cell-isolation-v2"
    assert record["input_sha256"] == hashlib.sha256(source_data).hexdigest()
    assert record["input_bytes"] == len(source_data)
    assert record["output_sha256"] == hashlib.sha256(normalized).hexdigest()
    assert record["output_bytes"] == len(normalized)
    assert record["semantic_contract"] == grid_semantic_contract(contract, 160, 80)
    assert record["transform_count"] == 8
    assert record["transforms"][0]["semantic_role"] == "cell-0-0"
    assert facts["cross_cell_contamination"] is False
    with Image.open(BytesIO(normalized)) as opened:
        alpha = opened.convert("RGBA").getchannel("A")
    for row in range(2):
        for column in range(4):
            cell = alpha.crop((column * 40, row * 40, (column + 1) * 40, (row + 1) * 40))
            boundary = cell.copy()
            ImageDraw.Draw(boundary).rectangle((3, 3, 36, 36), fill=0)
            assert boundary.getbbox() is None


def test_tileset_normalization_imposes_exact_12x4_topology_and_opaque_fill() -> None:
    contract = contract_for_stage("tileset")
    assert contract is not None
    source = Image.new("RGBA", (240, 80), (80, 120, 60, 255))

    normalized, facts = normalize_canonical_grid(_png(source), contract)

    assert facts["layout_columns"] == 12
    assert facts["layout_rows"] == 4
    assert facts["cells_nonempty"] == 48
    assert facts["canonical_fill_opaque"] is True
    record = facts["grid_normalization"]
    assert isinstance(record, dict)
    assert record["semantic_mask"] == "tileset-12x4-v1"
    assert record["transform_count"] == 48

    with Image.open(BytesIO(normalized)) as opened:
        damaged = opened.convert("RGBA")
    damaged.putpixel((3, 63), (80, 120, 60, 254))
    with pytest.raises(ValueError, match="canonical 12x4 role topology"):
        validate_canonical_grid(_png(damaged), contract)


def test_character_strip_remap_preserves_four_isolated_cells() -> None:
    contract = GridContract(rows=1, columns=4, gutter=2, anchor="bottom")
    source = Image.new("RGBA", (160, 80), (0, 0, 0, 0))
    draw = ImageDraw.Draw(source)
    for column in range(4):
        draw.rectangle(
            (column * 40 + 4, 4, column * 40 + 30, 77),
            fill=(40 + column * 30, 90, 160, 255),
        )

    _remapped, facts = remap_canonical_grid(_png(source), width=160, height=68, contract=contract)

    assert facts["output_height"] == 68
    assert facts["cells_nonempty"] == 4
    assert facts["boundaries_isolated"] is True


def test_runtime_ladder_and_climb_contracts_are_exact() -> None:
    ladder = contract_for_stage("ladder")
    climb = contract_for_stage("character-climb")

    assert ladder is not None
    assert ladder.as_dict(256, 1024) == {
        "version": "scrolling-grid-v1",
        "topology": "grid",
        "rows": 1,
        "columns": 1,
        "cell_width": 256,
        "cell_height": 1024,
        "gutter": 2,
        "anchor": "bottom",
    }
    assert climb is not None
    assert climb.as_dict(256, 128)["cell_width"] == 64


def test_obstacle_sheet_contract_is_bottom_anchored() -> None:
    obstacles = contract_for_stage("obstacles-0")

    assert obstacles is not None
    assert obstacles.anchor == "bottom"


@pytest.mark.parametrize("anchor", ["center", "bottom"])
def test_isolated_oversize_subject_is_fitted_with_aspect_and_anchor_preserved(
    anchor: Literal["center", "bottom"],
) -> None:
    image = Image.new("RGBA", (600, 400), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((240, 50, 359, 351), fill=(80, 130, 210, 255))
    source = _png(image)

    output, record = fit_isolated_view_alpha(
        source,
        maximum_height_fraction=0.70,
        anchor=anchor,
    )

    validation = validate_isolated_view_alpha(output)
    target_bbox = validation["isolated_view_alpha_bbox"]
    assert isinstance(target_bbox, list)
    assert record["source_height_fraction"] == 0.755
    assert (target_bbox[3] - target_bbox[1]) / 400 <= 0.70
    assert record["input_sha256"] == hashlib.sha256(source).hexdigest()
    assert record["output_sha256"] == hashlib.sha256(output).hexdigest()
    assert record["version"] == ISOLATED_SUBJECT_FIT_VERSION
    cleanup = record["cleanup"]
    assert isinstance(cleanup, dict)
    assert cleanup["version"] == ISOLATED_ALPHA_CLEANUP_VERSION
    assert record["premultiplied_alpha"] is True
    assert record["aspect_preserved"] is True
    assert record["anchor"] == anchor
    source_bbox = record["source_bbox"]
    assert isinstance(source_bbox, list)
    source_ratio = (source_bbox[2] - source_bbox[0]) / (source_bbox[3] - source_bbox[1])
    target_ratio = (target_bbox[2] - target_bbox[0]) / (target_bbox[3] - target_bbox[1])
    assert target_ratio == pytest.approx(source_ratio, abs=0.01)
    if anchor == "center":
        assert (target_bbox[1] + target_bbox[3]) / 2 == pytest.approx(200, abs=1)
    else:
        assert target_bbox[3] == 380


def test_isolated_alpha_cleanup_removes_one_pixel_border_noise_then_fits() -> None:
    image = Image.new("RGBA", (600, 400), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((210, 5, 389, 394), fill=(80, 130, 210, 255))
    draw.point((0, 200), fill=(220, 80, 40, 255))
    source = _png(image)

    cleaned, cleanup = canonicalize_isolated_view_alpha(source)

    assert cleanup["version"] == ISOLATED_ALPHA_CLEANUP_VERSION
    assert cleanup["input_component_count"] == 2
    assert cleanup["output_component_count"] == 1
    assert cleanup["removed_component_count"] == 1
    assert cleanup["removed_pixels"] == 1
    assert cleanup["removed_coordinates"] == [[0, 200]]
    input_border_flags = cleanup["input_border_flags"]
    output_border_flags = cleanup["output_border_flags"]
    assert isinstance(input_border_flags, dict)
    assert isinstance(output_border_flags, dict)
    assert input_border_flags["left"] is True
    assert not any(output_border_flags.values())
    payload = {key: value for key, value in cleanup.items() if key != "sha256"}
    assert (
        cleanup["sha256"]
        == hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    relaxed = validate_recoverable_isolated_view_alpha(cleaned)
    assert relaxed["isolated_view_alpha_inset_intrusion_sides"] == ["top", "bottom"]

    fitted, fit = fit_isolated_view_alpha(
        source,
        maximum_height_fraction=0.70,
        anchor="center",
    )

    fit_cleanup = fit["cleanup"]
    original_margins = fit["original_margins"]
    source_margins = fit["source_margins"]
    assert isinstance(fit_cleanup, dict)
    assert isinstance(original_margins, dict)
    assert isinstance(source_margins, dict)
    assert fit_cleanup["removed_coordinates"] == [[0, 200]]
    assert original_margins["left"] == 0
    assert source_margins["left"] == 210
    assert validate_isolated_view_alpha(fitted)["isolated_view_alpha_nontrivial"] is True


def test_isolated_alpha_cleanup_preserves_disconnected_interior_components() -> None:
    image = Image.new("RGBA", (200, 160), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((55, 30, 144, 129), fill=(80, 130, 210, 255))
    draw.point((20, 20), fill=(220, 180, 40, 255))

    cleaned, cleanup = canonicalize_isolated_view_alpha(_png(image))

    assert cleanup["removed_pixels"] == 0
    assert cleanup["output_component_count"] == 2
    with Image.open(BytesIO(cleaned)) as opened:
        pixel = opened.convert("RGBA").getpixel((20, 20))
        assert isinstance(pixel, tuple) and pixel[3] == 255


@pytest.mark.parametrize("kind", ["dominant-border", "over-budget", "fraction-budget"])
def test_isolated_alpha_cleanup_hard_rejects_unsafe_border_content(kind: str) -> None:
    image = Image.new("RGBA", (600, 400), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if kind == "dominant-border":
        draw.rectangle((0, 40, 300, 350), fill=(80, 130, 210, 255))
    elif kind == "over-budget":
        draw.ellipse((210, 30, 389, 369), fill=(80, 130, 210, 255))
        draw.line((0, 10, 0, 26), fill=(220, 80, 40, 255))
    else:
        draw.rectangle((260, 160, 289, 189), fill=(80, 130, 210, 255))
        draw.point((0, 10), fill=(220, 80, 40, 255))

    with pytest.raises(ValueError, match=r"border|physical"):
        canonicalize_isolated_view_alpha(_png(image))


@pytest.mark.parametrize("side", ["left", "top", "right", "bottom"])
@pytest.mark.parametrize("anchor", ["center", "bottom"])
def test_isolated_inner_inset_intrusion_is_recoverably_fitted(
    side: str,
    anchor: Literal["center", "bottom"],
) -> None:
    boxes = {
        "left": (2, 35, 81, 124),
        "top": (60, 2, 139, 101),
        "right": (118, 35, 197, 124),
        "bottom": (60, 58, 139, 157),
    }
    image = Image.new("RGBA", (200, 160), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle(boxes[side], fill=(80, 130, 210, 255))
    source = _png(image)

    relaxed = validate_recoverable_isolated_view_alpha(source)
    assert relaxed["isolated_view_alpha_inset_intrusion_sides"] == [side]
    with pytest.raises(ValueError, match="required clear padding"):
        validate_isolated_view_alpha(source)

    output, record = fit_isolated_view_alpha(
        source,
        maximum_height_fraction=0.55,
        anchor=anchor,
    )

    final = validate_isolated_view_alpha(output)
    bbox = final["isolated_view_alpha_bbox"]
    assert isinstance(bbox, list)
    assert record["original_inset_intrusion_sides"] == [side]
    assert record["source_inset_intrusion_sides"] == [side]
    assert bbox[0] >= 8 and bbox[1] >= 8 and bbox[2] <= 192 and bbox[3] <= 152
    assert (bbox[0] + bbox[2]) / 2 == pytest.approx(100, abs=1)
    if anchor == "center":
        assert (bbox[1] + bbox[3]) / 2 == pytest.approx(80, abs=1)
    else:
        assert bbox[3] == 152


def test_opaque_isolated_source_can_defer_only_inner_inset_intrusion() -> None:
    image = Image.new("RGB", (200, 160), (255, 0, 255))
    ImageDraw.Draw(image).rectangle((2, 35, 81, 124), fill=(80, 130, 210))
    source = _png(image)

    with pytest.raises(ValueError, match="required clear padding"):
        validate_isolated_view_source(source, width=200, height=160)
    relaxed = validate_isolated_view_source(
        source,
        width=200,
        height=160,
        allow_recoverable_inset=True,
    )
    assert relaxed["isolated_view_inset_intrusion_sides"] == ["left"]
    assert relaxed["isolated_view_inset_recoverable"] is True

    ImageDraw.Draw(image).rectangle((0, 35, 81, 124), fill=(80, 130, 210))
    with pytest.raises(ValueError, match="physical canvas border"):
        validate_isolated_view_source(
            _png(image),
            width=200,
            height=160,
            allow_recoverable_inset=True,
        )


def test_isolated_fit_uses_premultiplied_alpha_without_hidden_colour_halo() -> None:
    image = Image.new("RGBA", (200, 160), (0, 0, 255, 0))
    ImageDraw.Draw(image).rectangle((3, 5, 196, 156), fill=(220, 40, 20, 255))

    output, _record = fit_isolated_view_alpha(
        _png(image),
        maximum_height_fraction=0.55,
        anchor="center",
    )

    with Image.open(BytesIO(output)) as opened:
        rgba = opened.convert("RGBA")
        pixels = (
            cast(tuple[int, int, int, int], rgba.getpixel((x, y)))
            for y in range(rgba.height)
            for x in range(rgba.width)
        )
        assert all(blue <= 20 for _red, _green, blue, alpha in pixels if alpha > 0)


@pytest.mark.parametrize("kind", ["empty", "clipped", "continuous"])
def test_isolated_subject_fit_rejects_unrecoverable_alpha(kind: str) -> None:
    image = Image.new("RGBA", (600, 400), (0, 0, 0, 0))
    if kind == "clipped":
        ImageDraw.Draw(image).rectangle((0, 40, 220, 350), fill=(80, 130, 210, 255))
    elif kind == "continuous":
        ImageDraw.Draw(image).rectangle((0, 0, 599, 399), fill=(80, 130, 210, 255))

    with pytest.raises(ValueError):
        fit_isolated_view_alpha(
            _png(image),
            maximum_height_fraction=0.70,
            anchor="center",
        )


def test_runtime_concept_turnarounds_use_three_cells_before_animation_rules() -> None:
    character = contract_for_runtime_role("character-concept")
    mob = contract_for_runtime_role("mob-concept-7")
    character_idle = contract_for_runtime_role("character-idle")
    mob_idle = contract_for_runtime_role("mob-7-idle")

    assert character is not None and character.columns == 3
    assert mob is not None and mob.columns == 3
    assert character_idle is not None and character_idle.columns == 4
    assert mob_idle is not None and mob_idle.columns == 4


def _opaque_grid(width: int, height: int, contract: GridContract) -> bytes:
    image = Image.new("RGB", (width, height), (128, 128, 128))
    draw = ImageDraw.Draw(image)
    cell_width, cell_height = contract.cell_size(width, height)
    for row in range(contract.rows):
        for column in range(contract.columns):
            left = column * cell_width + contract.gutter
            top = row * cell_height + contract.gutter
            draw.rectangle(
                (
                    left,
                    top,
                    (column + 1) * cell_width - contract.gutter - 1,
                    (row + 1) * cell_height - contract.gutter - 1,
                ),
                fill=(40 + column * 20, 80 + row * 40, 180),
            )
    return _png(image)


def _tileset_template_source(contract: GridContract) -> Image.Image:
    canonical, _facts = normalize_canonical_grid(
        _png(Image.new("RGBA", (240, 80), (40, 120, 180, 255))),
        contract,
    )
    with Image.open(BytesIO(canonical)) as opened:
        template = opened.convert("RGBA")
    source = Image.new("RGB", template.size, (128, 128, 128))
    source.paste(template.convert("RGB"), mask=template.getchannel("A"))
    return source


def _png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _side_view_strip(
    *,
    contract: GridContract,
    width: int = 480,
    height: int = 160,
    flip_frame: int | None = None,
    head_on_frame: int | None = None,
    painted_gutter: bool = False,
    painted_inner_frame: bool = False,
) -> bytes:
    """Build a four-frame strip of an asymmetric subject seen from one fixed camera."""

    image = Image.new("RGB", (width, height), (255, 0, 255))
    draw = ImageDraw.Draw(image)
    cell_width, cell_height = contract.cell_size(width, height)
    for column in range(contract.columns):
        left = column * cell_width + contract.gutter * 3
        right = (column + 1) * cell_width - contract.gutter * 3
        top = contract.gutter * 3
        bottom = cell_height - contract.gutter * 3
        # A right-pointing wedge: clearly asymmetric, so mirroring it is detectable.
        nose = (right, (top + bottom) // 2)
        body = [(left, top), (left, bottom), nose]
        if column == flip_frame:
            body = [(right, top), (right, bottom), (left, (top + bottom) // 2)]
        if column == head_on_frame:
            body = [(left, bottom), ((left + right) // 2, top), (right, bottom)]
        draw.polygon(body, fill=(30 + column, 90, 200))
        if painted_inner_frame:
            draw.rectangle(
                (
                    column * cell_width + contract.gutter,
                    contract.gutter,
                    (column + 1) * cell_width - contract.gutter - 1,
                    cell_height - contract.gutter - 1,
                ),
                outline=(250, 225, 10),
                width=2,
            )
        if painted_gutter:
            draw.rectangle(
                (
                    column * cell_width,
                    0,
                    (column + 1) * cell_width - 1,
                    cell_height - 1,
                ),
                outline=(250, 225, 10),
                width=contract.gutter,
            )
    return _png(image)


def test_mob_strip_contract_demands_one_fixed_side_view_camera() -> None:
    assert contract_for_stage("mob-idle-0") == GridContract(
        rows=1, columns=4, gutter=8, anchor="bottom", fixed_side_view_frames=True
    )
    assert contract_for_stage("mob-hurt-3") == contract_for_stage("mob-idle-0")
    # Character strips keep the plain contract; nothing about this change touches them.
    character = contract_for_stage("character-attack")
    assert character == GridContract(rows=1, columns=4, gutter=8, anchor="bottom")
    assert character is not None and character.fixed_side_view_frames is False
    with pytest.raises(ValueError, match="single row of at least two cells"):
        GridContract(rows=2, columns=4, gutter=8, fixed_side_view_frames=True)


def test_template_border_painted_into_a_strip_is_rejected_not_recorded() -> None:
    """The border walls each cell off, so isolation alone reads it as a clean sheet."""

    contract = contract_for_stage("mob-idle-0")
    assert contract is not None
    clean = _side_view_strip(contract=contract)
    facts = validate_generated_source(clean, width=480, height=160, contract=contract)
    assert facts["source_cell_frames_unpainted"] is True
    assert facts["strip_fixed_side_view_frames"] is True

    over_gutter = _side_view_strip(contract=contract, painted_gutter=True)
    with pytest.raises(GridSourceLayoutError, match="painted into the artwork") as caught:
        validate_generated_source(over_gutter, width=480, height=160, contract=contract)
    assert caught.value.code == GRID_PAINTED_CELL_FRAME_ERROR_CODE

    inside_cell = _side_view_strip(contract=contract, painted_inner_frame=True)
    with pytest.raises(GridSourceLayoutError, match="painted border on every edge") as caught:
        validate_generated_source(inside_cell, width=480, height=160, contract=contract)
    assert caught.value.code == GRID_PAINTED_CELL_FRAME_ERROR_CODE
    assert caught.value.row == 0
    assert caught.value.column == 0


def test_strip_camera_must_hold_facing_and_viewing_angle_across_frames() -> None:
    contract = contract_for_stage("mob-idle-0")
    assert contract is not None

    turned = _side_view_strip(contract=contract, flip_frame=2)
    with pytest.raises(GridSourceLayoutError, match="changed facing between frames") as caught:
        validate_generated_source(turned, width=480, height=160, contract=contract)
    assert caught.value.code == STRIP_CAMERA_DRIFT_ERROR_CODE

    head_on = _side_view_strip(contract=contract, head_on_frame=1)
    with pytest.raises(GridSourceLayoutError, match="head-on view") as caught:
        validate_generated_source(head_on, width=480, height=160, contract=contract)
    assert caught.value.code == STRIP_CAMERA_DRIFT_ERROR_CODE

    # The same frames under a contract that does not claim a fixed camera stay acceptable, so
    # the rejection comes from the declared contract and not from the shapes themselves.
    plain = GridContract(rows=1, columns=4, gutter=8, anchor="bottom")
    for sheet in (turned, head_on):
        facts = validate_generated_source(sheet, width=480, height=160, contract=plain)
        assert "strip_fixed_side_view_frames" not in facts
