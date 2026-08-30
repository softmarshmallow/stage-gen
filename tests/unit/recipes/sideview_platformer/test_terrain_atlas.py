from __future__ import annotations

import json
from collections.abc import Sequence
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import cast

import pytest
from PIL import Image, ImageDraw

from stage_gen.recipes.sideview_platformer.climbable_atlas import (
    ClimbableRole,
    nominal_cell_box,
    plan_climbable_atlas,
)
from stage_gen.recipes.sideview_platformer.prepared_world import (
    _canonicalize_map_presentation,
    _validate_map_presentation_source,
)
from stage_gen.recipes.sideview_platformer.terrain_atlas import (
    CANONICAL_CELL_PX,
    MAXIMUM_CONNECTOR_ALPHA_MISMATCH,
    assemble_terrain_atlas,
    cells_from_canonical_atlas,
    compose_canonical_terrain,
    load_terrain_atlas_lookup,
    peering_mask,
    require_terrain_atlas_source,
    terrain_atlas_generation_prompt,
)
from stage_gen.resources import terrain_atlas_lookup_path, terrain_atlas_template_path


def _template() -> bytes:
    return terrain_atlas_template_path().read_bytes()


def _png(image: Image.Image) -> bytes:
    stream = BytesIO()
    image.save(stream, format="PNG", optimize=False)
    return stream.getvalue()


def _paintover_source(
    *,
    base: tuple[int, int, int] = (132, 86, 50),
    coordinate_variation: bool = True,
) -> bytes:
    with Image.open(BytesIO(_template())) as opened:
        image = opened.convert("RGB")
    pixels = image.load()
    assert pixels is not None
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue = cast(tuple[int, int, int], pixels[x, y])
            is_magenta = red > 180 and blue > 180 and green < 80
            is_cyan = red < 80 and green > 170 and blue > 170
            if is_magenta or is_cyan:
                continue
            variation = ((x // 19 + y // 23) % 9) - 4 if coordinate_variation else 0
            pixels[x, y] = tuple(max(0, min(255, channel + variation)) for channel in base)
    return _png(image)


def _climbable_source(roles: Sequence[str]) -> tuple[bytes, tuple[int, int]]:
    """One synthetic atlas column per declared role, at the plan's own request size."""

    plan = plan_climbable_atlas(len(roles))
    image = Image.new("RGBA", (plan.width_px, plan.height_px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for index, role in enumerate(roles):
        left, top, right, bottom = nominal_cell_box(plan, index)
        centre = (left + right) // 2
        if role == "ladder":
            # Two rails plus rungs: wide enough to land inside the ladder aspect envelope.
            draw.rectangle(
                (centre - 90, top + 40, centre - 50, bottom - 40), fill=(116, 74, 37, 255)
            )
            draw.rectangle(
                (centre + 50, top + 40, centre + 90, bottom - 40), fill=(116, 74, 37, 255)
            )
            for y in range(top + 120, bottom - 80, 120):
                draw.rectangle((centre - 50, y, centre + 50, y + 28), fill=(172, 122, 61, 255))
        else:
            # A single narrow strand, which only the rope envelope admits.
            draw.rectangle(
                (centre - 16, top + 40, centre + 16, bottom - 40), fill=(202, 174, 117, 255)
            )
    return _png(image), (plan.width_px, plan.height_px)


def _presentation_source(asset: str) -> bytes:
    assert asset == "portal"
    image = Image.new("RGBA", (1536, 1024), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if True:
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
    canonical, report = assemble_terrain_atlas(_paintover_source())
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


def test_paintover_is_locally_canonicalized_into_locked_direct_pass_atlas() -> None:
    source = _paintover_source()
    source_report = require_terrain_atlas_source(source)
    canonical, report = assemble_terrain_atlas(source)

    assert source_report["contract"] == "terrain-atlas-paintover-source-v3"
    assert report["canonicalizer"] == "terrain-atlas-paintover-canonicalization-v3"
    assert report["classification"] == "direct_pass"
    assert cast(float, report["template_alpha_mismatch_fraction"]) <= 0.10
    assert report["maximum_direct_connector_alpha_mismatch"] == 0.0
    assert cast(float, report["maximum_direct_connector_rgb_mean"]) <= 3.0
    assert report["template_sha256"] == sha256(_template()).hexdigest()
    assert report["lookup_sha256"] == sha256(terrain_atlas_lookup_path().read_bytes()).hexdigest()
    cells = cells_from_canonical_atlas(canonical)
    assert cells[(10, 1)].getchannel("A").getextrema() == (0, 0)
    lookup = load_terrain_atlas_lookup()
    for coordinate in lookup.by_mask.values():
        cell = cells[coordinate]
        assert cell.getchannel("A").getextrema()[1] == 255


def test_material_appearance_changes_canonical_rgb_without_changing_locked_alpha() -> None:
    first, _ = assemble_terrain_atlas(_paintover_source())
    second, _ = assemble_terrain_atlas(_paintover_source(base=(76, 62, 118)))
    with Image.open(BytesIO(first)) as opened:
        first_image = opened.convert("RGBA")
    with Image.open(BytesIO(second)) as opened:
        second_image = opened.convert("RGBA")

    assert first_image.getchannel("A").tobytes() == second_image.getchannel("A").tobytes()
    assert first_image.convert("RGB").tobytes() != second_image.convert("RGB").tobytes()


def test_paintover_source_rejects_missing_lattice_topology_drift_and_uniformity() -> None:
    missing_lattice = Image.new("RGB", (1600, 900), (100, 80, 60))
    with pytest.raises(ValueError, match="guide lattice count mismatch"):
        require_terrain_atlas_source(_png(missing_lattice))

    with Image.open(BytesIO(_paintover_source())) as opened:
        topology_drift = opened.convert("RGB")
    drift_pixels = topology_drift.load()
    assert drift_pixels is not None
    for y in range(topology_drift.height):
        for x in range(topology_drift.width):
            red, green, blue = cast(tuple[int, int, int], drift_pixels[x, y])
            if red < 80 and green > 170 and blue > 170:
                continue
            if not (red > 180 and blue > 180 and green < 80):
                drift_pixels[x, y] = (255, 0, 255)
    with pytest.raises(ValueError, match="changed too much locked topology"):
        require_terrain_atlas_source(_png(topology_drift))

    uniform = _paintover_source(base=(100, 80, 60), coordinate_variation=False)
    with pytest.raises(ValueError, match="lacks usable painted material variation"):
        require_terrain_atlas_source(uniform)


def test_portal_presentation_is_repacked_from_native_alpha() -> None:
    source = _presentation_source("portal")
    facts = _validate_map_presentation_source(source, asset="portal", expected_size=(1536, 1024))
    canonical, report = _canonicalize_map_presentation(source, asset="portal")

    assert facts["required_subject_count"] == 2
    assert report["selected_component_count"] == 2
    with Image.open(BytesIO(canonical)) as image:
        assert image.mode == "RGBA"
        assert image.getchannel("A").getextrema()[0] == 0


@pytest.mark.parametrize(
    "roles",
    (
        ("ladder",),
        ("ladder", "rope"),
        ("ladder", "ladder", "ladder", "rope", "rope", "rope"),
    ),
)
def test_climbable_atlas_is_repacked_one_cell_per_declared_variant(
    roles: tuple[ClimbableRole, ...],
) -> None:
    source, size = _climbable_source(roles)
    facts = _validate_map_presentation_source(
        source, asset="climbable", expected_size=size, roles=roles
    )
    canonical, report = _canonicalize_map_presentation(source, asset="climbable", roles=roles)

    assert facts["required_subject_count"] == len(roles)
    assert facts["index_order"] == "left_to_right"
    assert report["selected_component_count"] == len(roles)
    assert report["atlas_roles"] == list(roles)
    with Image.open(BytesIO(canonical)) as image:
        assert image.mode == "RGBA"
        assert image.getchannel("A").getextrema()[0] == 0


def test_climbable_rejects_a_column_whose_silhouette_is_not_its_declared_role() -> None:
    # A sheet of two ladders, declared as one ladder and one rope. The rope column is far too
    # wide for a strand, which is exactly what the per-role envelope exists to catch.
    source, size = _climbable_source(("ladder", "ladder"))

    with pytest.raises(ValueError, match="does not hold a rope silhouette"):
        _validate_map_presentation_source(
            source, asset="climbable", expected_size=size, roles=("ladder", "rope")
        )


def test_climbable_rejects_a_sheet_carrying_more_subjects_than_declared() -> None:
    # Three drawn columns, two declared. The extra component must fail admission rather than be
    # silently dropped in favour of whichever two happened to have the most area.
    source, _ = _climbable_source(("ladder", "ladder", "ladder"))
    two = plan_climbable_atlas(2)

    with pytest.raises(ValueError):
        _validate_map_presentation_source(
            source,
            asset="climbable",
            expected_size=(two.width_px, two.height_px),
            roles=("ladder", "ladder"),
        )


def test_validation_report_is_portable_and_prompt_is_material_neutral() -> None:
    _, report = assemble_terrain_atlas(_paintover_source())
    serialized = json.dumps(report, sort_keys=True)
    assert "/private/" not in serialized
    assert "/tmp/" not in serialized
    assert "authorization" not in serialized.lower()
    assert "signature=" not in serialized.lower()
    prompt = terrain_atlas_generation_prompt("thin mineral cap, layered crystalline fill")
    assert "reference image 1 as a strict production terrain-atlas paintover" in prompt
    assert "image 2 redundantly defines the exact 3x3-minimal" in prompt
    assert "cap and fill" in prompt
    assert "GRASS CAP" not in prompt
    assert "DIRT FILL" not in prompt
    assert "mirrored repetition" in prompt
