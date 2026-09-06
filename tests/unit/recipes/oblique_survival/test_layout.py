"""Offline tests for the world layout and the manifest's scale arithmetic.

The layout is the one part of the recipe that decides where things stand, and it
is seeded: the same package must place the same world twice, or a consumer that
reads the manifest and a run that drew the art would disagree about the ground.

    uv run pytest tests/unit/recipes/oblique_survival/test_layout.py
"""

from __future__ import annotations

import math
import re
import shutil
from collections.abc import Callable, Sequence
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from typing import Any, Final, cast

import pytest
from PIL import Image, ImageDraw

from stage_gen.config import StageGenConfig
from stage_gen.recipes.oblique_survival import layout as layout_module
from stage_gen.recipes.oblique_survival import survival_request
from stage_gen.recipes.oblique_survival.layout import Layout
from stage_gen.recipes.oblique_survival.manifest import manifest_bytes, measure_sprite
from stage_gen.recipes.oblique_survival.models import (
    Clutter,
    ItemUse,
    Package,
    Road,
    SourceError,
)
from stage_gen.recipes.oblique_survival.survival_graph import build_graph
from stage_gen.recipes.oblique_survival.survival_prompts import actor_concept_prompt
from stage_gen.recipes.oblique_survival.survival_request import load_package
from tests.unit.recipes.oblique_survival._survival_fixture import write_fixture

PACKAGE: Final = Path("library/games/ember-hollow")


def _document(package: Package, run_dir: Path, world: Layout) -> dict[str, Any]:
    """The fixture manifest, read as the JSON a consumer receives."""

    return cast(dict[str, Any], write_fixture(package, run_dir, world))


def _record(world: Layout) -> dict[str, Any]:
    """The layout record, typed: it is JSON, so a test reads it as JSON."""

    return cast(dict[str, Any], world.as_record())


def _extrema(channel: Image.Image) -> tuple[int, int]:
    """A single-band image's (low, high). Pillow types it for every band at once."""

    return cast(tuple[int, int], channel.getextrema())


def _clutter_of(block: dict[str, Any], *, biomes: Sequence[str] = ("forest_floor",)) -> Clutter:
    sheet = survival_request._clutter(block, biome_ids=list(biomes))
    assert sheet is not None
    return sheet


def _use_of(package: Package, item_id: str) -> ItemUse:
    use = package.item(item_id).use
    assert use is not None, item_id
    return use


def _road_of(package: Package) -> Road:
    road = package.road
    assert road is not None
    return road


@pytest.fixture(scope="module")
def package() -> Package:
    return load_package(PACKAGE)


@pytest.fixture(scope="module")
def world(package: Package) -> Layout:
    return layout_module.build_layout(package)


def test_the_authored_package_loads(package: Package) -> None:
    assert package.package_id == "ember-hollow"
    assert package.profile == "elevated_oblique_perspective_ground_plane_v1"
    assert package.facing_authored == "right"
    assert len(package.dust.kinds) == 4
    assert package.biomes[0].share == 0.0
    assert all(biome.share > 0.0 for biome in package.biomes[1:])


def test_the_player_is_the_scale_unit(package: Package) -> None:
    assert package.player.height_units == 1.0
    assert package.meters(1.0) == package.player_height_meters
    assert package.meters(3.2) == pytest.approx(3.2 * package.player_height_meters)


def test_a_prop_may_not_be_shorter_than_the_declared_minimum(package: Package) -> None:
    # The floor exists so a sprite is never asked for at a size no measurement
    # could recover; every authored prop must respect it.
    for prop in package.props:
        assert prop.height_units >= package.minimum_height_units


def test_the_layout_passes_its_own_checks(package: Package, world: Layout) -> None:
    assert layout_module.check_layout(package, world) == []


def test_the_same_seed_gives_byte_identical_output(package: Package) -> None:
    first = layout_module.build_layout(package)
    second = layout_module.build_layout(package)
    assert manifest_bytes(first.as_record()) == manifest_bytes(second.as_record())
    assert first.splat_png == second.splat_png


def test_nothing_overlaps(world: Layout) -> None:
    entities = world.entities
    for index, first in enumerate(entities):
        for second in entities[index + 1 :]:
            reach = first.scatter_radius_meters + second.scatter_radius_meters
            distance = math.hypot(first.x - second.x, first.z - second.z)
            assert distance >= reach - 1e-6, f"{first.entity_id} overlaps {second.entity_id}"


def test_the_camp_clearing_holds_only_the_camp(world: Layout) -> None:
    camp_x, camp_z = world.camp_position
    for entity in world.entities:
        if math.hypot(entity.x - camp_x, entity.z - camp_z) < world.clear_radius_meters:
            assert entity.ref_id in {"campfire", "canvas_tent"}


def test_the_player_spawns_inside_the_clearing(world: Layout) -> None:
    camp_x, camp_z = world.camp_position
    spawn = world.player_spawn
    assert math.hypot(spawn[0] - camp_x, spawn[1] - camp_z) <= world.clear_radius_meters


def test_every_entity_stays_inside_the_world_square(world: Layout) -> None:
    half = world.size_meters / 2
    for entity in world.entities:
        assert abs(entity.x) <= half
        assert abs(entity.z) <= half


def test_density_ceilings_hold(package: Package, world: Layout) -> None:
    area_hundreds = (world.size_meters**2) / 100.0
    for prop in package.props:
        per_hundred = package.world.get("density", {}).get(prop.family)
        if per_hundred is None:
            continue
        ceiling = round(float(per_hundred) * area_hundreds)
        assert world.counts.get(prop.prop_id, 0) <= ceiling


def test_a_prop_that_never_suits_either_biome_is_never_placed(package: Package) -> None:
    # Biome weighting is the only thing keeping trees out of the meadow, so a
    # zero weight everywhere must mean zero placements.
    blocked = dict(package.world)
    blocked["biome_weights"] = {
        **blocked.get("biome_weights", {}),
        "tree": {biome.biome_id: 0.0 for biome in package.biomes},
    }
    variant = replace(package, world=blocked)
    world = layout_module.build_layout(variant)
    assert world.counts.get("pine", 0) == 0


def test_the_splat_plate_is_data_not_colour(world: Layout) -> None:
    with Image.open(BytesIO(world.splat_png)) as opened:
        cells = layout_module.splat_cells(world.size_meters)
        assert opened.size == (cells, cells)
        assert opened.mode == "RGBA"
        red, green, blue, alpha = opened.convert("RGBA").split()
    # R is the road, a hard mask the shader erodes, so only 0 and 255 may
    # appear. G is under-canopy shade and may be anything. B is reserved and
    # empty; the biomes live on their own plate.
    assert set(_extrema(red)) <= {0, 255}
    assert _extrema(green)[1] > 0, "no canopy shade was painted at all"
    assert _extrema(blue) == (0, 0)
    # A is the landmass, hard too; the coast is torn in the shader.
    assert _extrema(alpha) == (0, 255)


def test_the_layout_record_names_props_and_actors_distinctly(world: Layout) -> None:
    for entry in _record(world)["entities"]:
        if entry["kind"] == "prop":
            assert "prop" in entry and "state" in entry
        else:
            assert "actor" in entry


def test_a_pure_python_prng_matches_across_the_two_sides() -> None:
    # The viewer runs the same generator on the same seed, so drift here would
    # silently desynchronise anything seeded on both sides.
    rand = layout_module.mulberry32(7)
    values = [rand() for _ in range(4)]
    assert all(0.0 <= value < 1.0 for value in values)
    assert len(set(values)) == 4
    again = layout_module.mulberry32(7)
    assert [again() for _ in range(4)] == values


# --- the road, the pads, and the litter ------------------------------------------------


def test_the_road_leaves_the_clearing_and_stays_inside_the_world(
    package: Package, world: Layout
) -> None:
    assert package.road is not None
    assert world.road_id == package.road.road_id
    assert len(world.road) >= 6
    half = world.size_meters / 2.0
    first = world.road[0]
    assert math.hypot(first[0] - world.camp_position[0], first[1] - world.camp_position[1]) > 3.0
    assert all(abs(x) <= half - 3.0 and abs(z) <= half - 3.0 for x, z in world.road)


def test_the_camp_structures_stand_on_pads(world: Layout) -> None:
    pads = [decal for decal in world.decals if decal["decal"] == "path"]
    assert len(pads) == 2
    assert all(decal["scale"] >= 1.0 for decal in pads)


def test_litter_keeps_off_the_road_and_out_of_footprints(package: Package, world: Layout) -> None:
    clutter = package.clutter
    assert clutter is not None
    assert len(world.clutter) > 100
    keep_out = _road_of(package).width_meters / 2.0 + 0.25
    for entry in world.clutter:
        assert layout_module.polyline_distance(entry["x"], entry["z"], world.road) >= keep_out
        assert 0 <= entry["cell"] < clutter.cell_count
    for entity in world.entities:
        if entity.kind != "prop":
            continue
        for entry in world.clutter:
            assert (
                math.hypot(entry["x"] - entity.x, entry["z"] - entity.z)
                >= entity.footprint_radius_meters
            )


def test_the_splat_carries_the_road_in_red(package: Package, world: Layout) -> None:
    with Image.open(BytesIO(world.splat_png)) as opened:
        image = opened.convert("RGBA")
    cells = image.size[0]
    pixels = image.load()
    assert pixels is not None
    red = [
        (x, y)
        for y in range(cells)
        for x in range(cells)
        if cast(tuple[int, int, int, int], pixels[x, y])[0] > 0
    ]
    assert red, "the road never reached the splat"
    size = world.size_meters
    reach = _road_of(package).width_meters / 2.0 + size / cells
    for x, y in red[::37]:
        wx = (x + 0.5) / cells * size - size / 2.0
        wz = (y + 0.5) / cells * size - size / 2.0
        assert layout_module.polyline_distance(wx, wz, world.road) <= reach


def test_the_layout_record_carries_the_road_and_the_litter(world: Layout) -> None:
    record = _record(world)
    assert record["road"]["points"][0] == {"x": world.road[0][0], "z": world.road[0][1]}
    assert len(record["clutter"]) == len(world.clutter)


# --- the landmass -------------------------------------------------------------------------


def _land_mask(world: Layout) -> Callable[[float, float], bool]:
    with Image.open(BytesIO(world.splat_png)) as opened:
        alpha = opened.convert("RGBA").getchannel("A")
    cells = alpha.size[0]
    band = alpha.tobytes()
    size = world.size_meters

    def land(x: float, z: float) -> bool:
        column = min(cells - 1, max(0, int((x + size / 2) / size * cells)))
        row = min(cells - 1, max(0, int((z + size / 2) / size * cells)))
        return band[row * cells + column] > 127

    return land


def test_the_landmass_has_the_authored_share_and_holds_the_camp(
    package: Package, world: Layout
) -> None:
    share = float(package.world["landmass"]["land_share"])
    assert abs(world.land_share - share) < 0.03
    land = _land_mask(world)
    assert land(*world.camp_position)
    assert land(*world.player_spawn)
    radius = world.clear_radius_meters
    for angle in range(0, 360, 30):
        assert land(radius * math.cos(math.radians(angle)), radius * math.sin(math.radians(angle)))


def test_nothing_is_placed_in_the_water(world: Layout) -> None:
    land = _land_mask(world)
    for entity in world.entities:
        assert land(entity.x, entity.z), entity.entity_id
    for x, z in world.road:
        assert land(x, z)
    for entry in world.clutter:
        assert land(entry["x"], entry["z"])
    for decal in world.decals:
        assert land(decal["x"], decal["z"])


def test_the_coast_is_inside_the_square(world: Layout) -> None:
    """The player never reaches the square: every edge cell of the mask is water."""

    with Image.open(BytesIO(world.splat_png)) as opened:
        alpha = opened.convert("RGBA").getchannel("A")
    cells = alpha.size[0]
    edges = (
        alpha.crop((0, 0, cells, 1)),
        alpha.crop((0, cells - 1, cells, cells)),
        alpha.crop((0, 0, 1, cells)),
        alpha.crop((cells - 1, 0, cells, cells)),
    )
    assert max(_extrema(strip)[1] for strip in edges) == 0


# --- the seam is authored ------------------------------------------------------------------


def test_every_prop_of_a_skirted_family_stands_on_a_skirt(package: Package, world: Layout) -> None:
    assert package.ground_contact == "skirt_decal"
    skirted = {
        family for decal in package.decals if decal.use == "skirt" for family in decal.families
    }
    props = [
        e for e in world.entities if e.kind == "prop" and package.prop(e.ref_id).family in skirted
    ]
    skirt_ids = {decal.decal_id for decal in package.decals if decal.use == "skirt"}
    skirts = [d for d in world.decals if d["decal"] in skirt_ids]
    assert len(skirts) == len(props) > 0
    assert {d["under"] for d in skirts} == {e.entity_id for e in props}
    for decal in skirts:
        assert decal["scale"] > 0


def test_a_package_that_chooses_shadow_gets_no_skirts(package: Package) -> None:
    shadow_only = replace(package, ground_contact="shadow")
    world = layout_module.build_layout(shadow_only)
    skirt_ids = {decal.decal_id for decal in package.decals if decal.use == "skirt"}
    assert not [d for d in world.decals if d["decal"] in skirt_ids]
    # The pads are not a seam choice; they stay.
    assert len([d for d in world.decals if d["decal"] == "path"]) == 2


# --- the ground line ------------------------------------------------------------------------


def test_the_ground_line_ignores_a_root_tip_hanging_below_the_base() -> None:
    image = Image.new("RGBA", (400, 800), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle([170, 100, 230, 700], fill=(90, 60, 40, 255))  # trunk
    draw.polygon([(120, 700), (280, 700), (230, 640), (170, 640)], fill=(90, 60, 40, 255))  # flare
    draw.line([(270, 700), (285, 760)], fill=(90, 60, 40, 255), width=3)  # one root tip
    data = BytesIO()
    image.save(data, format="PNG")
    facts = measure_sprite(data.getvalue())
    assert facts["alpha_bottom_y_normalized"] > 0.94
    assert 0.86 <= facts["ground_contact_y_normalized"] <= 0.885


def test_a_family_budget_is_split_between_its_props_not_multiplied() -> None:
    """Adding a second conifer mixes the wood; it does not double it."""

    package = load_package(PACKAGE)
    world = layout_module.build_layout(package)
    trees = [prop for prop in package.props if prop.family == "tree"]
    assert len(trees) > 1, "this test needs more than one tree to mean anything"

    per_hundred = package.world["density"]["tree"]
    area_hundreds = (world.size_meters**2) / 100.0
    budget = per_hundred * area_hundreds
    planted = sum(world.counts.get(prop.prop_id, 0) for prop in trees)
    assert planted <= round(budget) + len(trees)

    # and the split follows the authored shares
    shares = {prop.prop_id: prop.density_share for prop in trees}
    biggest = max(shares, key=lambda key: shares[key])
    smallest = min(shares, key=lambda key: shares[key])
    assert world.counts.get(biggest, 0) > world.counts.get(smallest, 0)

    # a prop with no share of its own still gets the whole family budget alone
    solo = replace(
        package,
        props=tuple(
            prop for prop in package.props if prop.family != "tree" or prop.prop_id == "pine"
        ),
    )
    solo_world = layout_module.build_layout(solo)
    assert solo_world.counts.get("pine", 0) > world.counts.get("pine", 0)


# --- the biomes ---------------------------------------------------------------------------


def _biome_plate(world: Layout) -> Image.Image:
    with Image.open(BytesIO(world.biome_splat_png)) as opened:
        return opened.convert("RGBA")


def test_the_biome_plate_holds_the_authored_shares(package: Package, world: Layout) -> None:
    """Each non-base biome gets its share of the square, solved, not assumed."""

    plate = _biome_plate(world)
    cells = plate.size[0]
    pixels = plate.load()
    assert pixels is not None
    counts = [0, 0, 0]
    for y in range(cells):
        for x in range(cells):
            r, g, b, a = cast(tuple[int, int, int, int], pixels[x, y])
            assert a == 255, "the biome plate's alpha is not a channel"
            assert (r > 0) + (g > 0) + (b > 0) <= 1, "a cell belongs to one biome"
            for index, value in enumerate((r, g, b)):
                if value > 0:
                    counts[index] += 1
    total = cells * cells
    for index, biome in enumerate(package.biomes[1:]):
        actual = counts[index] / total
        assert abs(actual - biome.share) < 0.05, f"{biome.biome_id}: {actual:.3f} vs {biome.share}"
        assert abs(world.biome_shares[biome.biome_id] - actual) < 0.02
    base = 1.0 - sum(counts) / total
    assert abs(world.biome_shares[package.biomes[0].biome_id] - base) < 0.02
    assert base > 0.3


def test_every_biome_is_a_continent_not_speckle(package: Package, world: Layout) -> None:
    """A biome boundary crossed by a row should be crossed a few times, not fifty."""

    plate = _biome_plate(world)
    cells = plate.size[0]
    pixels = plate.load()
    assert pixels is not None
    for y in range(0, cells, 16):
        changes = 0
        previous = None
        for x in range(cells):
            r, g, b, _a = cast(tuple[int, int, int, int], pixels[x, y])
            current = (r > 0, g > 0, b > 0)
            if previous is not None and current != previous:
                changes += 1
            previous = current
        # Continents alone crossed a row a dozen times at most; the islets
        # add a patch every fifteen metres or so, three or four cuts to a
        # 25 m screen, which is the reference's patchwork. Sixty would be
        # speckle.
        assert changes <= 45, f"row {y} crosses {changes} boundaries"


def _components(grid: list[list[int]], index: int) -> list[int]:
    """Sizes of the 4-connected patches of biome ``index`` in a wrapped grid."""

    cells = len(grid)
    seen = [[False] * cells for _ in range(cells)]
    sizes: list[int] = []
    for row in range(cells):
        for column in range(cells):
            if seen[row][column] or grid[row][column] != index:
                continue
            stack = [(row, column)]
            seen[row][column] = True
            size = 0
            while stack:
                r, c = stack.pop()
                size += 1
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nr, nc = (r + dr) % cells, (c + dc) % cells
                    if not seen[nr][nc] and grid[nr][nc] == index:
                        seen[nr][nc] = True
                        stack.append((nr, nc))
            sizes.append(size)
    return sizes


def test_the_islets_make_each_biome_a_patchwork_and_keep_its_share(package: Package) -> None:
    """The second octave scatters patches a few metres across; the share is unchanged."""

    world = dict(package.world)
    assert int(world["biome_islet_lattice"]) > 0 and float(world["biome_islet_share"]) > 0
    continents_only = replace(
        package, world={**world, "biome_islet_lattice": 0, "biome_islet_share": 0.0}
    )
    plain = layout_module.BiomeField(continents_only, 7)
    patched = layout_module.BiomeField(package, 7)
    cells = 128
    size = float(world["size_meters"])
    meters_per_cell = size / cells
    plain_grid = plain.index_grid(cells)
    patched_grid = patched.index_grid(cells)
    for index, biome in enumerate(package.biomes[1:]):
        before = _components(plain_grid, index)
        after = _components(patched_grid, index)
        assert len(after) >= 2 * len(before), (
            f"{biome.biome_id}: {len(before)} -> {len(after)} patches"
        )
        # The islets are the reference's 4 to 12 m islands, not speckle: the
        # small patches (under the largest continent) have a typical span of
        # a few metres.
        small = sorted(after)[: max(1, len(after) - len(before))]
        spans = [math.sqrt(count) * meters_per_cell for count in small]
        typical = spans[len(spans) // 2]
        assert 3.0 <= typical <= 16.0, f"{biome.biome_id}: typical islet span {typical:.1f} m"
        assert abs(patched.shares[biome.biome_id] - biome.share) < 0.05
        assert abs(plain.shares[biome.biome_id] - biome.share) < 0.05


def test_the_plate_and_the_scatter_agree_about_where_a_biome_is(
    package: Package, world: Layout
) -> None:
    field = layout_module.BiomeField(package, world.seed)
    plate = _biome_plate(world)
    cells = plate.size[0]
    pixels = plate.load()
    assert pixels is not None
    size = world.size_meters
    order = [biome.biome_id for biome in package.biomes]
    for x, y in ((3, 3), (100, 40), (128, 128), (200, 230), (60, 190)):
        wx = (x + 0.5) / cells * size - size / 2.0
        wz = (y + 0.5) / cells * size - size / 2.0
        r, g, b, _a = cast(tuple[int, int, int, int], pixels[x, y])
        expected = order[0]
        for index, value in enumerate((r, g, b)):
            if value > 0:
                expected = order[index + 1]
        assert field.biome_at(wx, wz, size) == expected


def test_a_prop_can_prefer_a_biome_over_its_family(package: Package) -> None:
    snag = package.prop("dead_snag")
    pine = package.prop("pine")
    assert snag.biome_weights is not None and pine.biome_weights is None
    assert layout_module._biome_weight(package, snag, "mossy_bog") == 1.0
    assert layout_module._biome_weight(package, pine, "mossy_bog") < 1.0
    # Without a row of its own the snag would take the tree family's row.
    plain = replace(snag, biome_weights=None)
    assert layout_module._biome_weight(package, plain, "mossy_bog") == layout_module._biome_weight(
        package, pine, "mossy_bog"
    )
    # A row of its own is complete: an unnamed biome is a zero, not a fallback.
    assert layout_module._biome_weight(package, snag, "grey_scree") == 0.35


def test_a_fifth_biome_is_refused(package: Package) -> None:
    rows = [
        {"biome_id": f"b{i}", "texel_meters": 2.0, "prompt": "x", **({"share": 0.1} if i else {})}
        for i in range(5)
    ]
    with pytest.raises(SourceError, match="at most 4"):
        survival_request._biomes(rows)
    with pytest.raises(SourceError, match="splat_channel"):
        survival_request._biomes(
            [{"biome_id": "b", "texel_meters": 2.0, "prompt": "x", "splat_channel": "base"}]
        )
    with pytest.raises(SourceError, match="remainder"):
        survival_request._biomes(
            [{"biome_id": "b", "texel_meters": 2.0, "prompt": "x", "share": 0.2}]
        )


def test_litter_lands_only_where_its_cell_is_allowed_and_is_never_spun(
    package: Package, world: Layout
) -> None:
    clutter = package.clutter
    assert clutter is not None
    field = layout_module.BiomeField.for_layout(package, world)
    seen: set[str] = set()
    for entry in world.clutter:
        biome = field.biome_at(entry["x"], entry["z"], world.size_meters)
        seen.add(biome)
        assert biome in clutter.cells[entry["cell"]].biomes
        assert abs(entry["rotation_degrees"]) <= package.look.ground_piece_jitter_degrees
        assert "mirror" not in entry, "nothing is mirrored for variety"
    assert seen == set(clutter.density), "every biome with a density gets litter"


def test_a_ground_patch_is_a_ground_piece_too(package: Package, world: Layout) -> None:
    """A patch keeps its lower edge toward the camera, like the litter: never spun."""

    assert world.decals, "the fixture package lays patches"
    for decal in world.decals:
        assert abs(decal["rotation_degrees"]) <= package.look.ground_piece_jitter_degrees
        assert "mirror" not in decal
    # Jitter is a spread, not a constant: at least two distinct headings.
    assert len({decal["rotation_degrees"] for decal in world.decals}) > 1


def test_a_litter_cell_must_name_a_known_biome_and_a_contact() -> None:
    cell: dict[str, Any] = {"brief": "a stone", "contact": "pressed", "biomes": ["forest_floor"]}
    cells = [dict(cell) for _ in range(4)]
    good: dict[str, Any] = {"columns": 2, "rows": 2, "cell_meters": 0.4, "cells": cells}
    assert _clutter_of(good).cell_count == 4
    with pytest.raises(SourceError, match="exactly 4"):
        _clutter_of({**good, "cells": cells[:3]})
    with pytest.raises(SourceError, match="unknown biome"):
        _clutter_of(good, biomes=("dry_meadow",))
    with pytest.raises(SourceError, match="contact"):
        _clutter_of({**good, "cells": [{**cell, "contact": "floating"}] * 4})
    with pytest.raises(SourceError, match="no cell may land"):
        _clutter_of(
            {**good, "density_per_100m2": {"dry_meadow": 4.0}},
            biomes=("forest_floor", "dry_meadow"),
        )


# --- looks: sheets, variants, progress ----------------------------------------------------


def _props_toml_with(tmp_path: Path, patch: str) -> Path:
    """Copy the authored source and append a prop, so the loader's rules run."""

    root = tmp_path / "source"
    shutil.copytree(PACKAGE, root)
    with (root / "props.toml").open("a") as handle:
        handle.write(patch)
    return root


_EXTRA = """
[[props]]
prop_id = "test_prop"
family = "rock"
height_units = 0.6
footprint_radius_units = 0.3
shadow_width_units = 0.6
hit_reaction = "none"
prompt = "a test rock"
states = {states}
{extra}
[props.state_prompt]
"""


def _refused(tmp_path: Path, *, states: str, extra: str, needle: str) -> None:
    root = _props_toml_with(tmp_path, _EXTRA.format(states=states, extra=extra))
    with pytest.raises(SourceError) as error:
        load_package(root)
    assert needle in str(error.value), str(error.value)


def test_a_sheet_holds_exactly_one_look_per_cell(tmp_path: Path) -> None:
    _refused(
        tmp_path,
        states='["a", "b", "c"]',
        extra="sheet = { columns = 2, rows = 2 }",
        needle="4 cells but 3 states",
    )


def test_a_sheet_shape_must_fit_a_provider_canvas(tmp_path: Path) -> None:
    _refused(
        tmp_path,
        states='["a", "b", "c"]',
        extra="sheet = { columns = 3, rows = 1 }",
        needle="not a lattice",
    )


def test_the_baseline_must_be_a_declared_look(tmp_path: Path) -> None:
    _refused(tmp_path, states='["a", "b"]', extra='baseline_state = "z"', needle="baseline_state")


def test_a_look_may_not_be_called_sheet(tmp_path: Path) -> None:
    _refused(tmp_path, states='["sheet", "b"]', extra="", needle="reserved")


def test_a_placed_variant_may_not_start_spent(tmp_path: Path) -> None:
    _refused(
        tmp_path,
        states='["a", "b", "c"]',
        extra=(
            'variants = { states = ["a", "c"] }\n'
            '[props.interaction]\nverb = "mine"\nhits = 2\nnext_state = "c"\n'
        ),
        needle="outcomes of its interaction",
    )


def test_progress_fits_inside_the_hits(tmp_path: Path) -> None:
    _refused(
        tmp_path,
        states='["a", "b", "c", "d"]',
        extra=(
            '[props.interaction]\nverb = "mine"\n'
            'hits = 2\nprogress = ["b", "c"]\nnext_state = "d"\n'
        ),
        needle="only 1 hits",
    )


def test_a_sheet_cannot_carry_a_painted_base(tmp_path: Path) -> None:
    root = tmp_path / "source"
    shutil.copytree(PACKAGE, root)
    survival = root / "survival.toml"
    text = survival.read_text()
    assert 'ground_contact = "skirt_decal"' in text
    survival.write_text(
        text.replace('ground_contact = "skirt_decal"', 'ground_contact = "painted_base"')
    )
    with pytest.raises(SourceError) as error:
        load_package(root)
    assert "cannot carry a painted base" in str(error.value)


def test_a_variant_look_comes_from_the_seed_alone(package: Package) -> None:
    pine = package.prop("pine")
    assert pine.variants is not None
    first = [layout_module.variant_state(pine, seed) for seed in range(0, 100000, 997)]
    second = [layout_module.variant_state(pine, seed) for seed in range(0, 100000, 997)]
    assert first == second
    assert set(first) == set(pine.variants.states)


def test_placed_pines_carry_their_variants_in_their_authored_shares(
    package: Package, world: Layout
) -> None:
    pine = package.prop("pine")
    placed = [e for e in world.entities if e.kind == "prop" and e.ref_id == "pine"]
    assert placed
    variants = pine.variants
    assert variants is not None
    total = sum(variants.weights)
    for state, weight in zip(variants.states, variants.weights, strict=True):
        share = sum(1 for e in placed if e.state == state) / len(placed)
        assert abs(share - weight / total) < 0.15, (state, share)
    assert all(e.state != "stump" for e in placed)


def test_every_placed_look_is_a_declared_one(package: Package, world: Layout) -> None:
    for entity in world.entities:
        if entity.kind == "prop":
            assert entity.state in package.prop(entity.ref_id).states
    assert not [p for p in layout_module.check_layout(package, world) if "undeclared look" in p]


def test_the_manifest_publishes_how_the_looks_were_drawn_and_bound(
    package: Package, world: Layout, tmp_path: Path
) -> None:
    document = _document(package, tmp_path / "run", world)
    pine = document["props"]["pine"]
    assert pine["drawn"] == {"kind": "sheet", "columns": 2, "rows": 2}
    assert pine["baseline_state"] == "grown"
    assert pine["variants"] == {"states": ["sapling", "grown", "old"], "weights": [0.2, 0.6, 0.2]}
    rock = document["props"]["moss_boulder"]
    assert rock["interaction"]["progress"] == ["cracked", "split"]
    assert document["props"]["fern_clump"]["drawn"] == {"kind": "sprites"}


def test_every_look_has_a_canonical_size_and_keeps_the_drawing_s_opinion(
    package: Package, world: Layout, tmp_path: Path
) -> None:
    document = _document(package, tmp_path / "run", world)
    pine = document["props"]["pine"]
    grown, stump, old = (pine["states"][s] for s in ("grown", "stump", "old"))
    meters = package.player_height_meters
    assert grown["height_units_source"] == "authored"
    assert grown["height_meters"] == round(3.2 * meters, 4)
    # The stump is authored at 0.4 units and calibrated from its own pixels,
    # whatever fraction of the canvas the fixture drew it at.
    assert stump["height_units_source"] == "authored"
    assert stump["height_meters"] == round(0.4 * meters, 4)
    assert stump["drawn_height_meters"] != stump["height_meters"]
    assert stump["px_per_meter"] != grown["px_per_meter"]
    assert old["height_meters"] == round(3.0 * meters, 4)
    # An unsized look rides the baseline's ruler and is the size it was drawn.
    cracked = document["props"]["moss_boulder"]["states"]["cracked"]
    whole = document["props"]["moss_boulder"]["states"]["whole"]
    assert cracked["height_units_source"] == "baseline_ruler"
    assert cracked["px_per_meter"] == whole["px_per_meter"]
    assert cracked["height_meters"] == cracked["drawn_height_meters"]


def test_the_baseline_look_may_not_be_sized_twice(tmp_path: Path) -> None:
    _refused(
        tmp_path,
        states='["a", "b"]',
        extra="look_height_units = { a = 0.5 }",
        needle="two authorities",
    )


def test_a_look_size_must_name_a_declared_look(tmp_path: Path) -> None:
    _refused(
        tmp_path,
        states='["a", "b"]',
        extra="look_height_units = { z = 0.5 }",
        needle="undeclared state",
    )


def test_every_tree_is_chopable(package: Package) -> None:
    for prop in package.props:
        if prop.family == "tree":
            assert prop.interaction is not None and prop.interaction.verb == "chop", prop.prop_id
            assert prop.interaction.next_state == "stump"
            assert prop.authored_height_units("stump") is not None


# --- the wide world ------------------------------------------------------------------------


def test_the_world_is_wide_and_the_splat_keeps_its_cell_size(world: Layout) -> None:
    # 256 m a side, at a quarter metre per splat cell: the road's torn edge
    # needs more than four cells across it whatever the world's size.
    assert world.size_meters >= 200.0
    cells = layout_module.splat_cells(world.size_meters)
    assert cells == round(world.size_meters / layout_module.SPLAT_CELL_METERS)
    assert world.size_meters / cells <= 0.25 + 1e-9


def test_the_hoisted_noise_grid_agrees_with_the_point_sampler() -> None:
    noise = layout_module.ValueNoise(4242, 8)
    cells = 96
    grid = noise.grid(cells)
    for row in (0, 17, 48, 95):
        for column in (0, 3, 50, 95):
            u = (column + 0.5) / cells
            v = (row + 0.5) / cells
            assert abs(grid[row][column] - noise.at(u, v)) < 1e-9


def test_the_placement_hash_answers_like_the_full_scan() -> None:
    rand = layout_module.mulberry32(99)
    placed = [
        layout_module.Placed(
            entity_id=f"p{i:04d}",
            kind="prop",
            ref_id="pine",
            state=None,
            x=(rand() * 2 - 1) * 60,
            z=(rand() * 2 - 1) * 60,
            seed=i,
            footprint_radius_meters=0.4,
            scatter_radius_meters=0.3 + rand() * 1.4,
        )
        for i in range(300)
    ]
    widest = max(entry.scatter_radius_meters for entry in placed)
    hashed = layout_module.PlacementHash(2.0 * widest + 0.5)
    for entry in placed:
        hashed.add(entry)

    def scan(x: float, z: float, radius: float) -> bool:
        return any(
            (x - e.x) ** 2 + (z - e.z) ** 2 < (radius + e.scatter_radius_meters) ** 2
            for e in placed
        )

    hits = 0
    for _ in range(2000):
        x, z, radius = (rand() * 2 - 1) * 62, (rand() * 2 - 1) * 62, 0.2 + rand() * 1.5
        expected = scan(x, z, radius)
        hits += expected
        assert hashed.collides(x, z, radius) == expected
    assert 0 < hits < 2000


def test_the_wide_world_is_thinner_than_the_first_one(package: Package, world: Layout) -> None:
    # Entities per hundred square metres of LAND, the number the eye reads.
    # The 64 m world stood at about twelve; the wide one must stay under eight.
    land_area = world.size_meters**2 * world.land_share
    per_hundred = len(world.entities) / (land_area / 100.0)
    assert per_hundred < 8.0
    assert len(world.road) * 1.5 > 60.0, "a wide world wants a road worth following"
    assert world.counts.get(package.mob.actor_id, 0) >= 8


# --- weather: standing water is laid once, faded by the runtime ---------------------


def test_puddles_are_scattered_on_land_off_the_camp_and_clear_of_every_prop(
    package: Package, world: Layout
) -> None:
    rain = package.weather[0]
    assert rain.wet is not None
    puddles = [d for d in world.decals if d.get("condition") == "rain"]
    ceiling = rain.wet.per_100_sqm * (world.size_meters**2) / 100.0
    assert 0 < len(puddles) <= ceiling + 1
    assert all(d["decal"] == rain.wet.decal_id for d in puddles)
    land = _land_mask(world)
    camp_x, camp_z = world.camp_position
    for puddle in puddles:
        assert land(puddle["x"], puddle["z"])
        assert math.hypot(puddle["x"] - camp_x, puddle["z"] - camp_z) >= world.clear_radius_meters
        assert 0.8 <= puddle["scale"] <= 1.4
    # Clear of every prop's scatter radius, so no puddle sits under a trunk.
    for puddle in puddles[:40]:
        for entity in world.entities:
            if entity.kind != "prop":
                continue
            assert (
                math.hypot(puddle["x"] - entity.x, puddle["z"] - entity.z)
                >= entity.scatter_radius_meters - 1e-6
            )


def test_a_package_without_weather_lays_no_puddles(package: Package) -> None:
    dry = replace(package, weather=())
    world = layout_module.build_layout(dry)
    assert not [d for d in world.decals if d.get("condition")]


def test_an_actor_s_seam_is_the_shadow_whatever_the_props_chose(
    package: Package, world: Layout, tmp_path: Path
) -> None:
    """A moving billboard can be handed no skirt and no painted base.

    The props' seam is the package's choice; the actor's is not a choice at
    all. Every actor block says ``shadow`` under every prop policy, and the
    top-level field still carries the props' own.
    """

    for policy in ("shadow", "skirt_decal", "painted_base", "none"):
        document = _document(replace(package, ground_contact=policy), tmp_path / policy, world)
        assert document["ground_contact"] == policy
        assert document["actors"], policy
        for actor_id, block in document["actors"].items():
            assert block["ground_contact"] == "shadow", (policy, actor_id)
            assert block["shadow_width_meters"] > 0


def test_pickup_is_a_game_decision_and_friction_belongs_to_the_surface(
    package: Package, world: Layout, tmp_path: Path
) -> None:
    """The pickup mode is authored once; the surface, not the item, says how a drop stops."""

    document = _document(package, tmp_path / "run", world)
    assert document["gameplay"]["pickup"] == "manual"
    assert document["gameplay"]["approach_meters"] >= document["gameplay"]["interact_reach_meters"]
    frictions = {bid: block["friction"] for bid, block in document["ground"]["biomes"].items()}
    assert frictions["forest_floor"] == 0.7
    assert frictions["grey_scree"] < frictions["forest_floor"] < frictions["mossy_bog"]
    assert all(0.05 <= value <= 3.0 for value in frictions.values())
    assert not any("friction" in block for block in document["items"].values())


def test_an_unknown_pickup_mode_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "source"
    shutil.copytree(PACKAGE, root)
    survival = root / "survival.toml"
    text = survival.read_text()
    assert 'pickup = "manual"' in text
    survival.write_text(text.replace('pickup = "manual"', 'pickup = "vacuum"'))
    with pytest.raises(SourceError) as error:
        load_package(root)
    assert "gameplay.pickup" in str(error.value)


def test_a_hit_reaction_is_authored_per_prop_and_the_boulder_holds_still(
    package: Package, world: Layout, tmp_path: Path
) -> None:
    """What a blow does to a card is the author's word in props.toml, never the family's."""

    document = _document(package, tmp_path / "run", world)
    reactions = {pid: block["hit_reaction"] for pid, block in document["props"].items()}
    assert set(reactions.values()) <= {"shake", "none"}
    assert reactions["moss_boulder"] == "none"
    assert reactions["pine"] == "shake"
    assert reactions["dead_snag"] == "shake"  # no sway in the wind, but it shudders


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ('hit_reaction = "none"\n', 'hit_reaction = "wobble"\n'),
        ('hit_reaction = "none"\n', ""),
    ],
)
def test_a_hit_reaction_is_required_and_closed(tmp_path: Path, before: str, after: str) -> None:
    root = tmp_path / "source"
    shutil.copytree(PACKAGE, root)
    props = root / "props.toml"
    text = props.read_text()
    assert before in text
    props.write_text(text.replace(before, after, 1))
    with pytest.raises(SourceError) as error:
        load_package(root)
    assert "hit_reaction" in str(error.value)


def test_the_player_carries_an_authored_appearance_picture(package: Package) -> None:
    """A character is held by a picture; prose describes an outfit and the model invents a body."""

    player = package.player
    assert player.appearance_reference == "references/player-appearance.png"
    assert player.appearance_reference_digest
    assert package.digests[player.appearance_reference] == player.appearance_reference_digest
    prompt = actor_concept_prompt(package, player)
    # Reference 1 is the character and reference 2 is the plate; the shared
    # style clause, which claims image 1 for the plate, must stand down.
    assert "Reference image 1 is THIS CHARACTER" in prompt
    assert "Reference image 2 is a STYLE reference only" in prompt
    assert "Reference image 1 is a STYLE reference only" not in prompt
    # The mob has no picture and keeps the old shape exactly.
    assert package.mob.appearance_reference is None
    mob_prompt = actor_concept_prompt(package, package.mob)
    assert "Reference image 1 is a STYLE reference only" in mob_prompt
    assert "THIS CHARACTER" not in mob_prompt


def test_an_appearance_reference_is_confined_and_must_be_a_png(tmp_path: Path) -> None:
    root = tmp_path / "source"
    shutil.copytree(PACKAGE, root)
    actors = root / "actors.toml"
    text = actors.read_text()
    line = 'appearance_reference = "references/player-appearance.png"'
    assert line in text
    actors.write_text(text.replace(line, 'appearance_reference = "../../../etc/hosts.png"'))
    with pytest.raises(SourceError) as error:
        load_package(root)
    assert "player.appearance_reference" in str(error.value)


def test_swapping_the_appearance_picture_moves_the_concept_key(tmp_path: Path) -> None:
    """The picture is part of the answer, so it is part of the node identity."""

    def concept_key(root: Path) -> str:
        package = load_package(root)
        built = build_graph(StageGenConfig(), package, "actors")
        node = next(n for n in built.nodes if n.node_id == "actor-wren-concept")
        return node.cache_key

    root = tmp_path / "source"
    shutil.copytree(PACKAGE, root)
    before = concept_key(root)
    picture = root / "references" / "player-appearance.png"
    data = bytearray(picture.read_bytes())
    data[-1] = (data[-1] + 1) % 256  # a different picture, still a PNG
    picture.write_bytes(bytes(data))
    assert concept_key(root) != before


def test_the_approach_radius_never_falls_inside_the_reach(tmp_path: Path) -> None:
    root = tmp_path / "source"
    shutil.copytree(PACKAGE, root)
    survival = root / "survival.toml"
    text = survival.read_text()
    assert "approach_meters = 4.5" in text
    survival.write_text(text.replace("approach_meters = 4.5", "approach_meters = 0.5"))
    with pytest.raises(SourceError) as error:
        load_package(root)
    assert "gameplay.approach_meters" in str(error.value)


# --- the crafting table and the forage -------------------------------------------------


def _source_edit(tmp_path: Path, file: str, old: str, new: str, *, append: bool = False) -> Path:
    """Copy the authored source and change one file, so the loader's rules run."""

    root = tmp_path / "source"
    if not root.exists():
        shutil.copytree(PACKAGE, root)
    path = root / file
    text = path.read_text()
    if append:
        path.write_text(text + new)
    else:
        assert old in text, old
        path.write_text(text.replace(old, new))
    return root


def _load_refused(root: Path, needle: str) -> None:
    with pytest.raises(SourceError) as error:
        load_package(root)
    assert needle in str(error.value), str(error.value)


def test_the_authored_crafting_table_is_playable_from_nothing(package: Package) -> None:
    """The closure passes with an empty start: forage, then the axe, then wood."""

    assert package.crafting.start == {}
    ids = {recipe.recipe_id for recipe in package.crafting.recipes}
    assert {"axe", "campfire", "workbench", "pickaxe", "cooked_berry", "backpack"} <= ids
    assert {station.station_id for station in package.crafting.stations} == {
        "campfire",
        "workbench",
    }
    axe_tool = package.item("axe").tool
    assert axe_tool is not None and axe_tool.verb == "chop"
    chop = package.prop("pine").interaction
    assert chop is not None and chop.tool is not None
    assert chop.tool.required is True


def test_an_item_nothing_reaches_is_refused(tmp_path: Path) -> None:
    root = _source_edit(
        tmp_path,
        "items.toml",
        "",
        '\n[[items]]\nitem_id = "orphan"\nheight_units = 0.2\nprompt = "an orphan"\n',
        append=True,
    )
    # The icon lattice is full at twenty-four; drop a glyph so the closure is what refuses.
    _source_edit(
        tmp_path, "items.toml", '  { glyph = "moon", brief = "a crescent moon, pale cream" },\n', ""
    )
    _load_refused(root, "nothing yields, forages, starts with or crafts: ['orphan']")


def test_the_icon_lattice_must_be_filled_exactly(tmp_path: Path) -> None:
    root = _source_edit(tmp_path, "items.toml", "columns = 6\nrows = 4", "columns = 6\nrows = 5")
    _load_refused(root, "holds 30 cells but 18 items and 6 glyphs")


def test_an_unknown_item_key_is_refused(tmp_path: Path) -> None:
    root = _source_edit(
        tmp_path, "items.toml", 'item_id = "log"\n', 'item_id = "log"\nweight = 3\n'
    )
    _load_refused(root, "log has unknown keys ['weight']")


def test_a_recipe_names_exactly_one_product_and_a_declared_station(tmp_path: Path) -> None:
    root = _source_edit(
        tmp_path,
        "crafting.toml",
        'product = { item_id = "axe", count = 1 }',
        'product = { item_id = "axe", count = 1, prop_id = "campfire" }',
    )
    _load_refused(root, "axe.product names exactly one of item_id or prop_id")
    root = _source_edit(
        tmp_path / "b", "crafting.toml", 'station = "workbench"', 'station = "anvil"'
    )
    _load_refused(root, "wants undeclared station 'anvil'")


def test_a_recipe_chain_nothing_can_start_is_refused(tmp_path: Path) -> None:
    # Rope needs reeds; take the reeds away (the clump's yield) and rope, the
    # workbench, the pickaxe and the backpack all fall.
    root = _source_edit(
        tmp_path, "props.toml", 'yields = [{ item_id = "reed", count = 2 }]', "yields = []"
    )
    _load_refused(root, "recipes nothing can ever make: rope, workbench, pickaxe, backpack")


def test_the_old_campfire_recipe_and_berry_restore_are_refused(tmp_path: Path) -> None:
    root = _source_edit(
        tmp_path,
        "survival.toml",
        "burn_seconds = 90.0",
        "recipe = { log = 2 }\nburn_seconds = 90.0",
    )
    _load_refused(root, "gameplay.campfire.recipe is not authored any more")
    root = _source_edit(
        tmp_path / "b",
        "survival.toml",
        "drain_per_second = 0.6",
        "drain_per_second = 0.6\nberry_restore = 20.0",
    )
    _load_refused(root, "gameplay.hunger.berry_restore is not authored any more")


def test_items_no_longer_live_in_props_toml(tmp_path: Path) -> None:
    root = _source_edit(
        tmp_path,
        "props.toml",
        "",
        '\n[[items]]\nitem_id = "x"\nheight_units = 0.2\nprompt = "x"\n',
        append=True,
    )
    _load_refused(root, "props.toml [[items]] moved to items.toml")


def test_a_tool_must_serve_the_verb_that_wants_it(tmp_path: Path) -> None:
    root = _source_edit(
        tmp_path,
        "props.toml",
        'tool = { item_id = "pickaxe", hits = 3, required = true }',
        'tool = { item_id = "axe", hits = 3, required = true }',
    )
    _load_refused(root, "moss_boulder wants 'axe' to mine")
    root = _source_edit(
        tmp_path / "b",
        "items.toml",
        'stack_max = 1\nprompt = "A small hand axe',
        'stack_max = 5\nprompt = "A small hand axe',
    )
    _load_refused(root, "axe is a tool and wears; a tool's stack_max is 1")


def test_forage_lands_only_where_its_cell_is_allowed_and_off_the_camp(
    package: Package, world: Layout
) -> None:
    forage = package.forage
    assert forage is not None and world.forage
    field = layout_module.BiomeField.for_layout(package, world)
    camp_x, camp_z = world.camp_position
    seen: set[str] = set()
    for entry in world.forage:
        biome = field.biome_at(entry["x"], entry["z"], world.size_meters)
        seen.add(biome)
        assert biome in forage.cells[entry["cell"]].biomes
        assert abs(entry["rotation_degrees"]) <= package.look.ground_piece_jitter_degrees
        assert math.hypot(entry["x"] - camp_x, entry["z"] - camp_z) >= world.clear_radius_meters
    assert seen == set(forage.density), "every biome with a density gets forage"
    record = world.as_record()
    assert record["forage"] == [dict(entry) for entry in world.forage]
    # Sparser than the litter, by design.
    assert len(world.forage) < len(world.clutter) / 3


def test_plants_stand_only_where_their_cell_is_allowed_off_the_camp_and_off_the_road(
    package: Package, world: Layout
) -> None:
    """The mid-scale: scattered like the litter, out of the clearing, denser than forage."""

    plants = package.plants
    assert plants is not None and world.plants
    field = layout_module.BiomeField.for_layout(package, world)
    camp_x, camp_z = world.camp_position
    seen: set[str] = set()
    for entry in world.plants:
        biome = field.biome_at(entry["x"], entry["z"], world.size_meters)
        seen.add(biome)
        assert biome in plants.cells[entry["cell"]].biomes
        assert math.hypot(entry["x"] - camp_x, entry["z"] - camp_z) >= world.clear_radius_meters
        if world.road:
            assert (
                layout_module.polyline_distance(entry["x"], entry["z"], list(world.road))
                >= world.road_width_meters / 2
            )
    assert seen == set(plants.density), "every biome with a density gets plants"
    assert world.as_record()["plants"] == [dict(entry) for entry in world.plants]
    # A screen's worth of ground holds a few dozen: the densest biome asks
    # for seven per hundred square metres over the land.
    assert len(world.plants) > len(world.forage)


def test_the_camp_stands_on_the_base_biome(package: Package, world: Layout) -> None:
    """The islets fade out over the clearing, so the spawn is never on a patch of scree."""

    field = layout_module.BiomeField.for_layout(package, world)
    base = package.biomes[0].biome_id
    camp_x, camp_z = world.camp_position
    radius = world.clear_radius_meters
    for i in range(-4, 5):
        for j in range(-4, 5):
            x = camp_x + i * radius / 4
            z = camp_z + j * radius / 4
            if math.hypot(x - camp_x, z - camp_z) <= radius:
                assert field.biome_at(x, z, world.size_meters) == base, (x, z)
    # The rule is local: the shares still solve to the authored ones.
    for biome in package.biomes[1:]:
        assert abs(world.biome_shares[biome.biome_id] - biome.share) < 0.03, biome.biome_id


def test_plant_cells_must_grow_and_a_plant_sheet_is_not_litter_scale() -> None:
    cell = {"brief": "a fern", "contact": "growing", "biomes": ["forest_floor"]}
    block = {
        "columns": 2,
        "rows": 2,
        "cell_meters": 1.4,
        "density_per_100m2": {"forest_floor": 2.0},
        "cells": [dict(cell) for _ in range(4)],
    }
    assert survival_request._plants(block, biome_ids=["forest_floor"]) is not None
    fallen = {**block, "cells": [dict(cell) for _ in range(3)] + [{**cell, "contact": "fallen"}]}
    with pytest.raises(SourceError, match="must grow"):
        survival_request._plants(fallen, biome_ids=["forest_floor"])
    with pytest.raises(SourceError, match="half a metre"):
        survival_request._plants({**block, "cell_meters": 0.4}, biome_ids=["forest_floor"])


def test_a_forage_cell_yields_a_declared_item_and_regrows() -> None:
    cell = {
        "brief": "a twig",
        "contact": "fallen",
        "biomes": ["forest_floor"],
        "item_id": "twig",
        "count": 1,
        "regrow_seconds": 60.0,
    }
    good = {"columns": 2, "rows": 2, "cell_meters": 0.5, "cells": [dict(cell) for _ in range(4)]}
    sheet = survival_request._forage(good, biome_ids=["forest_floor"], item_ids=["twig"])
    assert sheet is not None
    assert sheet.cells[0].item_id == "twig" and sheet.cells_for("forest_floor") == (0, 1, 2, 3)
    with pytest.raises(SourceError, match="undeclared item"):
        survival_request._forage(good, biome_ids=["forest_floor"], item_ids=["log"])
    bad = {**good, "cells": [{**cell, "regrow_seconds": 0.0}] * 4}
    with pytest.raises(SourceError, match="regrow_seconds"):
        survival_request._forage(bad, biome_ids=["forest_floor"], item_ids=["twig"])


# --- seasons -------------------------------------------------------------------------


def test_a_season_names_only_what_the_world_has(tmp_path: Path) -> None:
    root = _source_edit(
        tmp_path, "seasons.toml", 'order = ["summer", "winter"]', 'order = ["summer", "autumn"]'
    )
    _load_refused(root, "calendar.order names undeclared season 'autumn'")
    root = _source_edit(
        tmp_path / "b", "seasons.toml", 'barren = ["thorn_bush"]', 'barren = ["canvas_tent"]'
    )
    _load_refused(root, "barren names 'canvas_tent', which has no interaction to refuse")
    root = _source_edit(
        tmp_path / "c",
        "seasons.toml",
        'hidden_forage = ["mushroom", "moss"]',
        'hidden_forage = ["truffle"]',
    )
    _load_refused(root, "hidden_forage names undeclared item 'truffle'")
    root = _source_edit(
        tmp_path / "d", "seasons.toml", "regrow_scale = 0.0\n", "regrow_scale = 0.0\nwind = 3\n"
    )
    _load_refused(root, "seasons.winter has unknown keys ['wind']")
    root = _source_edit(
        tmp_path / "e", "seasons.toml", "days_per_season = 4", "days_per_season = 0"
    )
    _load_refused(root, "days_per_season must be an integer within [1, 30]")


def test_a_cold_season_needs_a_fire_that_warms(tmp_path: Path) -> None:
    root = _source_edit(tmp_path, "survival.toml", "heat_radius_meters = 3.5\n", "")
    _load_refused(root, "a season is cold but gameplay.campfire has no heat_radius_meters")
    root = _source_edit(
        tmp_path / "b", "survival.toml", "drain_per_second = 0.5\n", "drain_per_second = 0.0\n"
    )
    _load_refused(root, "gameplay.warmth.drain_per_second is missing or zero")


def test_a_season_prompt_names_a_look_a_season_shows(tmp_path: Path) -> None:
    root = _source_edit(
        tmp_path,
        "props.toml",
        '[props.season_prompt.winter]\nfull = "bare of berries',
        '[props.season_prompt.autumn]\nfull = "bare of berries',
    )
    _load_refused(root, "thorn_bush.season_prompt.autumn names a look no season shows")
    root = _source_edit(
        tmp_path / "b",
        "props.toml",
        '[props.season_prompt.winter]\nfull = "bare of berries',
        '[props.season_prompt.winter]\nburnt = "ash"\nfull = "bare of berries',
    )
    _load_refused(root, "thorn_bush.season_prompt.winter names undeclared states: ['burnt']")


def test_the_calendar_may_hold_no_look_and_a_season_may_be_bare(tmp_path: Path) -> None:
    """A calendar with no art is complete: the world turns cold and green."""

    root = _source_edit(tmp_path, "seasons.toml", "\n[seasons.look]\n", "\n[seasons.nolook]\n")
    _load_refused(root, "seasons.winter has unknown keys ['nolook']")
    root = tmp_path / "source"
    text = (root / "seasons.toml").read_text()
    (root / "seasons.toml").write_text(text[: text.index("[seasons.nolook]")])
    props = (root / "props.toml").read_text()
    (root / "props.toml").write_text(
        re.sub(r"\[props\.season_prompt\.winter\]\n(?:[a-z_]+ = \"[^\"]*\"\n)+", "", props)
    )
    package = load_package(root)
    assert package.seasons is not None and package.seasons.looks == ()
    assert package.seasons.season("winter").look == ""


def test_wear_and_warm_are_use_kinds_that_do_something(tmp_path: Path) -> None:
    root = _source_edit(
        tmp_path,
        "items.toml",
        'use = { kind = "wear", insulation = 0.5 }',
        'use = { kind = "wear" }',
    )
    _load_refused(root, "grass_cloak.use wears for nothing: give it insulation in (0, 1]")
    root = _source_edit(
        tmp_path / "b",
        "items.toml",
        'use = { kind = "warm", heat_seconds = 120.0 }',
        'use = { kind = "warm" }',
    )
    _load_refused(root, "warm_stone.use warms for nothing: give it heat_seconds")
    root = _source_edit(
        tmp_path / "c",
        "items.toml",
        'use = { kind = "wear", insulation = 0.5 }',
        'use = { kind = "wear", insulation = 1.5 }',
    )
    _load_refused(root, "grass_cloak.use.insulation")


def test_ice_belongs_to_the_snow(tmp_path: Path) -> None:
    root = _source_edit(
        tmp_path,
        "weather.toml",
        "tint = [0.80, 0.88, 0.94]\ndesaturate = 0.30\n",
        (
            "tint = [0.80, 0.88, 0.94]\ndesaturate = 0.30\n\n"
            '[conditions.ice]\ntexel_meters = 6.0\nprompt = "ice"\n'
        ),
    )
    _load_refused(root, "only snow freezes the water; rain has no ice")


def test_a_snowy_season_needs_the_snow_condition(tmp_path: Path) -> None:
    root = _source_edit(tmp_path, "weather.toml", 'condition_id = "snow"', 'condition_id = "sleet"')
    _load_refused(root, "condition_id must be one of")


def test_the_winter_table_is_reachable_and_the_looks_cover_every_state() -> None:
    package = load_package(PACKAGE)
    assert package.seasons is not None
    winter = package.seasons.season("winter")
    assert (
        winter.look == "winter"
        and winter.barren == ("thorn_bush",)
        and winter.hidden_forage == ("mushroom", "moss")
    )
    assert package.seasons.order == ("summer", "winter")
    assert {item.item_id for item in package.items} >= {"grass_cloak", "warm_stone"}
    cloak, stone, berry = (
        _use_of(package, "grass_cloak"),
        _use_of(package, "warm_stone"),
        _use_of(package, "cooked_berry"),
    )
    assert cloak.kind == "wear" and cloak.insulation == 0.5
    assert stone.heat_seconds == 120.0
    assert berry.warmth == 10.0
    recipes = {recipe.recipe_id: recipe for recipe in package.crafting.recipes}
    assert (
        recipes["warm_stone"].station == "campfire"
        and recipes["grass_cloak"].station == "workbench"
    )
    # Every prop state has a winter brief: the shared clause or its own.
    look = package.seasons.look("winter")
    assert "snow lies on every upward-facing surface" in look.prompt
    for prop in package.props:
        for state in prop.states:
            assert prop.season_prompt.get("winter", {}).get(state, "") or look.prompt
