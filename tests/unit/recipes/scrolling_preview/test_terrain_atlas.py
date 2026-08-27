from __future__ import annotations

import json
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Literal, cast

import pytest
from PIL import Image, ImageDraw

from stage_gen.recipes.scrolling_preview.prepared_world import (
    _canonicalize_map_presentation,
    _validate_map_presentation_source,
)
from stage_gen.recipes.scrolling_preview.terrain_atlas import (
    CANONICAL_CELL_PX,
    CAP_DEPTH_PX,
    MAXIMUM_CAP_SURFACE_START_PX,
    MAXIMUM_CONNECTOR_ALPHA_MISMATCH,
    assemble_terrain_atlas,
    cells_from_canonical_atlas,
    compose_canonical_terrain,
    load_terrain_atlas_lookup,
    peering_mask,
    require_terrain_material_source,
    terrain_atlas_generation_prompt,
)
from stage_gen.resources import terrain_atlas_lookup_path, terrain_atlas_template_path


def _template() -> bytes:
    return terrain_atlas_template_path().read_bytes()


def _png(image: Image.Image) -> bytes:
    stream = BytesIO()
    image.save(stream, format="PNG", optimize=False)
    return stream.getvalue()


def _material_source(
    *,
    cap: tuple[int, int, int] = (78, 142, 62),
    fill: tuple[int, int, int] = (132, 86, 50),
) -> bytes:
    image = Image.new("RGB", (1024, 768), fill)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1024, 240), fill=cap)
    for x in range(0, 1024, 32):
        draw.rectangle((x, 0, x + 12, 240), fill=tuple(min(255, value + 18) for value in cap))
    for y in range(330, 768, 40):
        draw.rectangle((0, y, 1024, y + 15), fill=tuple(max(0, value - 14) for value in fill))
    return _png(image)


def _presentation_source(asset: str) -> bytes:
    size = (1024, 1536) if asset == "ladder" else (1536, 1024)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if asset == "ladder":
        draw.rectangle((380, 220, 420, 1320), fill=(116, 74, 37, 255))
        draw.rectangle((604, 220, 644, 1320), fill=(116, 74, 37, 255))
        for y in range(300, 1260, 120):
            draw.rectangle((400, y, 624, y + 28), fill=(172, 122, 61, 255))
    else:
        for left in (150, 900):
            draw.rectangle((left, 180, left + 55, 850), fill=(202, 174, 117, 255))
            draw.rectangle((left + 330, 180, left + 385, 850), fill=(202, 174, 117, 255))
            draw.rectangle((left, 150, left + 385, 240), fill=(202, 174, 117, 255))
    return _png(image)


def test_lookup_has_47_unique_and_reachable_masks() -> None:
    lookup = load_terrain_atlas_lookup()
    assert len(lookup.by_mask) == 47
    assert len(set(lookup.by_mask.values())) == 47
    observed = set()
    for bits in range(256):
        occupied = [[False] * 3 for _ in range(3)]
        occupied[1][1] = True
        positions = ((0, 0), (1, 0), (2, 0), (0, 1), (2, 1), (0, 2), (1, 2), (2, 2))
        for index, (x, y) in enumerate(positions):
            occupied[y][x] = bool((bits >> index) & 1)
        frozen = tuple(tuple(row) for row in occupied)
        observed.add(peering_mask(frozen, 1, 1))
    assert observed == set(lookup.by_mask)


def test_web_consumer_lookup_matches_the_authoritative_packaged_contract() -> None:
    repository = Path(__file__).parents[4]
    consumer = json.loads(
        (repository / "web/lib/runtime/terrain-atlas-lookup.json").read_text(encoding="utf-8")
    )
    authoritative = json.loads(terrain_atlas_lookup_path().read_text(encoding="utf-8"))
    assert consumer == authoritative


@pytest.mark.parametrize("mutation", ("missing", "duplicate"))
def test_missing_or_duplicate_lookup_entries_fail_closed(mutation: str) -> None:
    payload = json.loads(terrain_atlas_lookup_path().read_text(encoding="utf-8"))
    keys = list(payload["lookup"])
    if mutation == "missing":
        del payload["lookup"][keys[0]]
    else:
        payload["lookup"][keys[1]] = payload["lookup"][keys[0]]
    with pytest.raises(ValueError):
        load_terrain_atlas_lookup(json.dumps(payload).encode("utf-8"))


@pytest.mark.parametrize(
    "rows",
    (
        ("00000000", "11111111", "11111111"),
        ("000000000", "011111110", "000000000"),
        ("000000111", "000011111", "001111111", "111111111"),
        ("111111111", "110000011", "110111011", "110101011", "111111111"),
    ),
)
def test_composes_solid_floating_steps_concavities_and_holes(rows: tuple[str, ...]) -> None:
    canonical, report = assemble_terrain_atlas(_material_source())
    assert report["classification"] == "direct_pass"
    composed, composition = compose_canonical_terrain(canonical, rows)
    with Image.open(BytesIO(composed)) as image:
        assert image.size == (len(rows[0]) * CANONICAL_CELL_PX, len(rows) * CANONICAL_CELL_PX)
    coordinates = cast(list[list[list[int] | None]], composition["coordinates"])
    assert sum(cell is not None for row in coordinates for cell in row) == sum(
        line.count("1") for line in rows
    )
    metrics = cast(dict[str, float], composition["connector_metrics"])
    assert metrics["connector_alpha_mismatch_fraction"] <= MAXIMUM_CONNECTOR_ALPHA_MISMATCH


def test_material_source_is_locally_assembled_into_locked_direct_pass_atlas() -> None:
    source = _material_source()
    source_report = require_terrain_material_source(source)
    canonical, report = assemble_terrain_atlas(source)

    assert source_report["contract"] == "terrain-material-source-v1"
    assert report["canonicalizer"] == "terrain-atlas-material-assembly-v2"
    assert report["classification"] == "direct_pass"
    assert report["exact_template_alpha_mismatch_fraction"] == 0.0
    assert report["maximum_direct_connector_alpha_mismatch"] == 0.0
    assert cast(float, report["maximum_direct_connector_rgb_mean"]) <= 3.0
    assert report["template_sha256"] == sha256(_template()).hexdigest()
    assert report["lookup_sha256"] == sha256(terrain_atlas_lookup_path().read_bytes()).hexdigest()
    cells = cells_from_canonical_atlas(canonical)
    assert cells[(10, 1)].getchannel("A").getextrema() == (0, 0)
    lookup = load_terrain_atlas_lookup()
    for mask, coordinate in lookup.by_mask.items():
        cell = cells[coordinate]
        alpha = cell.getchannel("A")
        rgb = cell.convert("RGB")
        cap_pixels = [
            (x, y)
            for y in range(CANONICAL_CELL_PX)
            for x in range(CANONICAL_CELL_PX)
            if cast(int, alpha.getpixel((x, y))) > 128
            and cast(tuple[int, int, int], rgb.getpixel((x, y)))[1]
            > max(
                cast(tuple[int, int, int], rgb.getpixel((x, y)))[0],
                cast(tuple[int, int, int], rgb.getpixel((x, y)))[2],
            )
        ]
        if mask[1] == 0:
            assert cap_pixels
            assert max(y for _, y in cap_pixels) <= (MAXIMUM_CAP_SURFACE_START_PX + CAP_DEPTH_PX)
        else:
            assert not cap_pixels


def test_material_appearance_changes_canonical_rgb_without_changing_locked_alpha() -> None:
    first, _ = assemble_terrain_atlas(_material_source())
    second, _ = assemble_terrain_atlas(_material_source(cap=(70, 100, 180), fill=(76, 62, 118)))
    with Image.open(BytesIO(first)) as opened:
        first_image = opened.convert("RGBA")
    with Image.open(BytesIO(second)) as opened:
        second_image = opened.convert("RGBA")

    assert first_image.getchannel("A").tobytes() == second_image.getchannel("A").tobytes()
    assert first_image.convert("RGB").tobytes() != second_image.convert("RGB").tobytes()


def test_material_source_rejects_transparency_uniformity_and_merged_regions() -> None:
    transparent = Image.new("RGBA", (1024, 768), (100, 80, 60, 200))
    with pytest.raises(ValueError, match="fully opaque"):
        require_terrain_material_source(_png(transparent))

    uniform = Image.new("RGB", (1024, 768), (100, 80, 60))
    with pytest.raises(ValueError, match="lacks usable material variation"):
        require_terrain_material_source(_png(uniform))

    merged_image = Image.new("RGB", (1024, 768), (100, 120, 80))
    merged_draw = ImageDraw.Draw(merged_image)
    for x in range(0, 1024, 32):
        merged_draw.rectangle((x, 0, x + 12, 768), fill=(118, 138, 98))
    with pytest.raises(ValueError, match="not visually distinct"):
        require_terrain_material_source(_png(merged_image))


@pytest.mark.parametrize("asset,subjects", (("ladder", 1), ("portal", 2)))
def test_map_traversal_presentations_are_repacked_from_native_alpha(
    asset: Literal["ladder", "portal"], subjects: int
) -> None:
    source = _presentation_source(asset)
    facts = _validate_map_presentation_source(source, asset=asset)
    canonical, report = _canonicalize_map_presentation(source, asset=asset)

    assert facts["required_subject_count"] == subjects
    assert report["selected_component_count"] == subjects
    with Image.open(BytesIO(canonical)) as image:
        assert image.mode == "RGBA"
        assert image.getchannel("A").getextrema()[0] == 0


def test_incomplete_single_rail_does_not_pass_as_a_ladder() -> None:
    image = Image.new("RGBA", (1024, 1536), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((490, 200, 530, 1330), fill=(120, 80, 40, 255))

    with pytest.raises(ValueError, match="complete tall functional silhouette"):
        _validate_map_presentation_source(_png(image), asset="ladder")


def test_validation_report_is_portable_and_prompt_is_material_neutral() -> None:
    _, report = assemble_terrain_atlas(_material_source())
    serialized = json.dumps(report, sort_keys=True)
    assert "/private/" not in serialized
    assert "/tmp/" not in serialized
    assert "authorization" not in serialized.lower()
    assert "signature=" not in serialized.lower()
    prompt = terrain_atlas_generation_prompt("thin mineral cap, layered crystalline fill")
    assert "GRASS CAP" in prompt
    assert "DIRT FILL" in prompt
    assert "Do not attempt tile topology" in prompt
    assert "template" not in prompt.lower()
