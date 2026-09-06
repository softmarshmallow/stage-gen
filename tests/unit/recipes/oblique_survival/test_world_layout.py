"""The world layout: the recipe's binding of the world generator, on the authored package.

The layout decides where things stand, and it is seeded: the same package
must lay the same world twice, or a host that reads the record and a run that
drew the art would disagree about the ground. Beyond identity, these pin the
rules the generator was asked to keep: the camp is a set piece at the origin,
quotas and shares hold, nothing overlaps, the plates agree with the record,
an edit to one object moves only that object, and the component that lays
the world knows none of the package's words.

    uv run pytest tests/unit/recipes/oblique_survival/test_world_layout.py
"""

from __future__ import annotations

import hashlib
import math
import re
import shutil
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from typing import Any, Final, cast

import pytest
from PIL import Image

from stage_gen.components.worldgen import PointIndex, plate_cells
from stage_gen.recipes.oblique_survival import layout as layout_module
from stage_gen.recipes.oblique_survival.layout import Layout
from stage_gen.recipes.oblique_survival.manifest import manifest_bytes
from stage_gen.recipes.oblique_survival.models import ClusterRule, Package, SourceError
from stage_gen.recipes.oblique_survival.survival_request import load_package

PACKAGE: Final = Path("library/games/ember-hollow")
#: The card count the world is authored to, and the tolerance a density edit
#: may drift it by before the host sees a different game.
ENTITY_BUDGET: Final = 2471
BUDGET_TOLERANCE: Final = 0.10
COMPONENT: Final = Path("src/stage_gen/components/worldgen")


def _record(world: Layout) -> dict[str, Any]:
    return cast(dict[str, Any], world.as_record())


@pytest.fixture(scope="module")
def package() -> Package:
    return load_package(PACKAGE)


@pytest.fixture(scope="module")
def world(package: Package) -> Layout:
    return layout_module.build_layout(package)


def _entities(world: Layout, ref_id: str) -> list[layout_module.Placed]:
    return [entity for entity in world.entities if entity.ref_id == ref_id]


def test_the_layout_passes_its_own_checks(package: Package, world: Layout) -> None:
    assert world.refusals == ()
    assert layout_module.check_layout(package, world) == []


def test_the_same_seed_gives_byte_identical_output(package: Package, world: Layout) -> None:
    again = layout_module.build_layout(package)
    assert manifest_bytes(world.as_record()) == manifest_bytes(again.as_record())
    assert world.splat_png == again.splat_png
    assert world.biome_splat_png == again.biome_splat_png


def test_every_entity_resolves(package: Package, world: Layout) -> None:
    props = {prop.prop_id: prop for prop in package.props}
    record = _record(world)
    for entry in record["entities"]:
        if entry["kind"] == "prop":
            prop = props[entry["prop"]]
            assert entry["state"] in prop.states
        else:
            assert entry["actor"] == package.mob.actor_id
            assert "state" not in entry
        assert "id" in entry and "seed" in entry
    ids = [entry["id"] for entry in record["entities"]]
    assert len(set(ids)) == len(ids)
    assert record["counts"] == {
        ref: sum(1 for e in world.entities if e.ref_id == ref) for ref in record["counts"]
    }


def test_the_camp_is_a_set_piece_at_the_origin(package: Package, world: Layout) -> None:
    assert world.camp_position == (0.0, 0.0)
    camp = world.set_pieces[0]
    assert camp.instance_id == "camp/0" and (camp.x, camp.z) == (0.0, 0.0)
    members = [entity for entity in world.entities if entity.set_piece == "camp/0"]
    assert [(m.ref_id, m.state, m.x, m.z) for m in members] == [
        ("canvas_tent", "pitched", -2.2, -1.4),
        ("campfire", "unlit", 1.4, 0.9),
    ]
    assert math.hypot(*world.player_spawn) <= world.clear_radius_meters
    for entity in world.entities:
        inside = math.hypot(entity.x, entity.z) < world.clear_radius_meters
        assert not inside or entity.set_piece == "camp/0", entity
    rings = [piece for piece in world.set_pieces if piece.set_piece_id == "boulder_ring"]
    assert len(rings) == 2
    for ring in rings:
        assert 70.0 <= math.hypot(ring.x, ring.z) <= 140.0
        stones = [e for e in world.entities if e.set_piece == ring.instance_id]
        assert len(stones) == 5 and all(e.ref_id == "moss_boulder" for e in stones)
    pads = [decal for decal in world.decals if decal["decal"] == "path"]
    assert sorted(decal["under"] for decal in pads) == sorted(m.entity_id for m in members)


def test_the_world_budget_holds(package: Package, world: Layout) -> None:
    assert abs(world.land_share - package.world.landmass.land_share) < 0.02
    for biome in package.biomes[1:]:
        assert abs(world.biome_shares[biome.biome_id] - biome.share) < 0.02
    for prop in package.props:
        if prop.placement is None:
            continue
        count = len(_entities(world, prop.prop_id))
        assert count >= prop.placement.min_per_world, prop.prop_id
        if prop.placement.max_per_world is not None:
            assert count <= prop.placement.max_per_world, prop.prop_id
    hounds = _entities(world, package.mob.actor_id)
    assert package.mob.placement is not None
    assert package.mob.placement.min_per_world <= len(hounds)
    assert package.mob.placement.max_per_world is not None
    assert len(hounds) <= package.mob.placement.max_per_world
    total = len(world.entities)
    assert abs(total - ENTITY_BUDGET) <= ENTITY_BUDGET * BUDGET_TOLERANCE, total


def test_nothing_overlaps_and_nothing_leaves_the_square(world: Layout) -> None:
    half = world.size_meters / 2.0
    index = PointIndex(4.0)
    footprints: dict[str, float] = {}
    spacing: dict[str, float] = {}
    refs: dict[str, str] = {}
    pieces: dict[str, str | None] = {}
    for entity in world.entities:
        assert abs(entity.x) <= half and abs(entity.z) <= half
        index.add(entity.x, entity.z, entity.scatter_radius_meters, entity.entity_id)
        footprints[entity.entity_id] = entity.footprint_radius_meters
        spacing[entity.entity_id] = 2.0 * entity.scatter_radius_meters
        refs[entity.entity_id] = entity.ref_id
        pieces[entity.entity_id] = entity.set_piece

    def gap(a: str, b: str) -> float:
        if pieces[a] is not None and pieces[a] == pieces[b]:
            return 0.0
        if refs[a] == refs[b]:
            return min(spacing[a], spacing[b]) - 1e-6
        return footprints[a] + footprints[b] - 1e-6

    assert list(index.pairs_closer_than(gap)) == []


def test_the_plates_agree_with_the_record(package: Package, world: Layout) -> None:
    cells = plate_cells(world.size_meters)
    assert world.plate_cells == cells == 1024
    assert world.cell_meters == pytest.approx(0.5)
    with Image.open(BytesIO(world.splat_png)) as splat:
        assert splat.size == (cells, cells) and splat.mode == "RGBA"
        red, green, blue, alpha = splat.split()
        assert set(cast(list[int], alpha.getdata())) <= {0, 255}
        assert set(cast(list[int], blue.getdata())) == {0}
        assert set(cast(list[int], red.getdata())) == {0, 255}
        land = sum(1 for value in cast(list[int], alpha.getdata()) if value == 255)
        assert abs(land / (cells * cells) - world.land_share) < 0.02
        shade = green.load()
        assert shade is not None
    with Image.open(BytesIO(world.biome_splat_png)) as biomes:
        assert biomes.size == (cells, cells)
        r, g, b, a = biomes.split()
        assert set(cast(list[int], a.getdata())) == {255}
        one_hot = zip(
            cast(list[int], r.getdata()),
            cast(list[int], g.getdata()),
            cast(list[int], b.getdata()),
            strict=True,
        )
        assert all(sum(1 for v in trio if v == 255) <= 1 for trio in one_hot)
    half = world.size_meters / 2.0
    cell = world.cell_meters

    def at(x: float, z: float) -> int:
        value = shade[int((x + half) / cell), int((z + half) / cell)]
        assert isinstance(value, int)
        return value

    props = {prop.prop_id: prop for prop in package.props}
    shaded = [
        e
        for e in world.entities
        if e.kind == "prop"
        and props[e.ref_id].canopy_radius_meters > 0.0
        and e.state == props[e.ref_id].baseline_state
    ]
    assert shaded
    assert all(at(e.x, e.z) > 0 for e in shaded[:200])
    canopy_index = PointIndex(4.0)
    for e in world.entities:
        if props.get(e.ref_id) is not None and props[e.ref_id].canopy_radius_meters > 0.0:
            canopy_index.add(e.x, e.z, props[e.ref_id].canopy_radius_meters)
    bare = [e for e in _entities(world, "moss_boulder") if not canopy_index.hits(e.x, e.z, 0.5)]
    assert bare
    assert all(at(e.x, e.z) == 0 for e in bare)


def test_pieces_keep_off_the_road_out_of_footprints_and_out_of_the_clearing(
    package: Package, world: Layout
) -> None:
    assert package.road is not None
    # The keep-out is read off the 2 m analysis grid, so a piece may sit up to
    # a cell's error inside the authored margin; never on the road itself.
    keep_out = package.road.width_meters / 2.0 + layout_module.ROAD_PIECE_MARGIN - 1.0
    index = PointIndex(4.0)
    for entity in world.entities:
        if entity.kind == "prop":
            index.add(entity.x, entity.z, entity.footprint_radius_meters)
    for name in ("clutter", "forage", "plants"):
        pieces = getattr(world, name)
        assert pieces
        for piece in pieces:
            x, z = piece["x"], piece["z"]
            assert layout_module.polyline_distance(x, z, world.road) >= keep_out - 1e-6
            assert not index.hits(x, z, 0.0)
            if name != "clutter":
                assert math.hypot(x, z) >= world.clear_radius_meters
            assert abs(piece["rotation_degrees"]) <= package.look.ground_piece_jitter_degrees
            assert 0.8 <= piece["scale"] <= 1.15


def test_reeds_stand_at_the_water_and_ferns_under_pines(package: Package, world: Layout) -> None:
    with Image.open(BytesIO(world.splat_png)) as splat:
        alpha = splat.split()[3].load()
        assert alpha is not None
    cells = world.plate_cells
    half = world.size_meters / 2.0
    cell = world.cell_meters

    def water_within(x: float, z: float, radius: float) -> bool:
        cx, cz = int((x + half) / cell), int((z + half) / cell)
        reach = int(radius / cell) + 1
        for j in range(max(0, cz - reach), min(cells, cz + reach + 1)):
            for i in range(max(0, cx - reach), min(cells, cx + reach + 1)):
                if alpha[i, j] == 0 and math.hypot((i - cx) * cell, (j - cz) * cell) <= radius:
                    return True
        return False

    reeds = _entities(world, "reed_clump")
    assert len(reeds) >= 100
    assert all(water_within(e.x, e.z, 9.0) for e in reeds)
    pines = _entities(world, "pine")
    pine_index = PointIndex(4.0)
    for pine in pines:
        pine_index.add(pine.x, pine.z, 0.0)
    ferns = _entities(world, "fern_clump")
    assert ferns
    for fern in ferns:
        assert fern.cluster is not None and fern.cluster.startswith("host/")
        assert pine_index.hits(fern.x, fern.z, 0.0, reach_override=2.5 + 1e-6)
    groves = {e.cluster for e in pines if e.cluster is not None}
    assert 15 <= len(groves) <= len(pines) / 2
    hounds = _entities(world, package.mob.actor_id)
    fire = next(e for e in world.entities if e.ref_id == "campfire")
    assert all(math.hypot(h.x - fire.x, h.z - fire.z) >= 30.0 for h in hounds)


def test_the_record_carries_the_set_pieces_and_the_report(world: Layout) -> None:
    record = _record(world)
    assert [piece["id"] for piece in record["set_pieces"]] == [
        "camp/0",
        "boulder_ring/0",
        "boulder_ring/1",
    ]
    assert record["cell_meters"] == pytest.approx(0.5)
    report = record["report"]
    assert set(report) >= {"pine", "birch", "clutter", "forage", "plants", "grub_hound"}
    assert report["pine"]["verdict"] == "clustered"
    assert report["grass_tuft"]["verdict"] == "spaced"
    assert report["pine"]["r_mc"] < 0.7
    assert report["pine"]["placed"] == len(_entities(world, "pine"))
    entry = next(e for e in record["entities"] if e.get("prop") == "pine")
    assert entry["cluster"].startswith("pine/c")
    tent = next(e for e in record["entities"] if e.get("prop") == "canvas_tent")
    assert tent["set_piece"] == "camp/0" and "cluster" not in tent


def test_an_edit_to_one_object_moves_only_that_object(package: Package, world: Layout) -> None:
    snag = package.prop("dead_snag")
    assert snag.placement is not None
    edited = replace(
        package,
        props=tuple(
            replace(prop, placement=replace(prop.placement, density_per_100m2=0.32))
            if prop.prop_id == "dead_snag" and prop.placement is not None
            else prop
            for prop in package.props
        ),
    )
    other = layout_module.build_layout(edited)
    before = {(e.ref_id, e.x, e.z) for e in world.entities if e.ref_id == "dead_snag"}
    after = {(e.ref_id, e.x, e.z) for e in other.entities if e.ref_id == "dead_snag"}
    delta = [(x, z) for _ref, x, z in before ^ after]
    assert len(after) > len(before) and delta
    widest = max(e.footprint_radius_meters for e in world.entities)
    props = {prop.prop_id: prop for prop in package.props}

    def reach_of(ref: str) -> float:
        # One footprint of the edit, plus, for a thing attached to another,
        # its host's reach and the attachment radius: a fern follows its pine.
        own = max(
            [e.footprint_radius_meters for e in world.entities if e.ref_id == ref], default=0.0
        )
        total = own + widest
        placement = props[ref].placement if ref in props else package.mob.placement
        if placement is not None and placement.near is not None:
            total += reach_of(placement.near.host) + placement.near.radius_meters
        return total

    for ref in {e.ref_id for e in world.entities} - {"dead_snag"}:
        mine = {(e.x, e.z): e for e in world.entities if e.ref_id == ref}
        theirs = {(e.x, e.z): e for e in other.entities if e.ref_id == ref}
        reach = reach_of(ref)
        for x, z in set(mine) ^ set(theirs):
            assert min(math.hypot(x - dx, z - dz) for dx, dz in delta) <= reach + 1e-6, (
                ref,
                x,
                z,
            )
    assert other.biome_splat_png == world.biome_splat_png


def test_a_cluster_that_clusters_nothing_is_refused(package: Package) -> None:
    pine = package.prop("pine")
    assert pine.placement is not None and pine.placement.cluster is not None
    wide = replace(pine.placement, cluster=ClusterRule(0.002, 60.0, 60.0))
    doctored = replace(
        package,
        props=tuple(
            replace(prop, placement=wide) if prop.prop_id == "pine" else prop
            for prop in package.props
        ),
    )
    world = layout_module.build_layout(doctored)
    problems = layout_module.check_layout(doctored, world)
    assert any(problem.startswith("pine:") for problem in problems), problems


def test_the_generator_knows_no_domain_vocabulary(package: Package) -> None:
    words = {prop.prop_id for prop in package.props}
    words |= {prop.family for prop in package.props}
    words |= {biome.biome_id for biome in package.biomes}
    words |= {package.mob.actor_id, "camp", "campfire", "survival", "oblique"}
    for path in COMPONENT.glob("*.py"):
        text = path.read_text().lower()
        for word in words:
            assert re.search(rf"\b{re.escape(word)}\b", text) is None, (path.name, word)


def test_the_world_identity_is_pinned(world: Layout) -> None:
    """The library package lays this world. A change here is a world change and
    says so in its commit; a change that did not mean to be one is a defect."""

    digest = hashlib.sha256(manifest_bytes(world.as_record())).hexdigest()
    assert digest == WORLD_DIGEST


WORLD_DIGEST: Final = "7c761b93ad3842f95a554375d67aaa66ae361f86f45d1606b462aca1d7ebb3c6"


# --- the loader: world.toml and the placement block ------------------------------------


def _copy(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    shutil.copytree(PACKAGE, root)
    return root


def _refused(root: Path, needle: str) -> None:
    with pytest.raises(SourceError) as error:
        load_package(root)
    assert needle in str(error.value), str(error.value)


def _edit(root: Path, name: str, old: str, new: str) -> None:
    path = root / name
    text = path.read_text()
    assert text.count(old) == 1, (name, old)
    path.write_text(text.replace(old, new))


def test_the_old_world_keys_are_refused_by_name(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    _edit(root, "survival.toml", "[gameplay]\n", "[world]\nseed = 7\n\n[gameplay]\n")
    _refused(root, "survival.toml [world] moved to world.toml")
    root = _copy(tmp_path / "b")
    _edit(root, "survival.toml", 'pickup = "manual"\n', 'pickup = "manual"\nmob_count = 12\n')
    _refused(root, "gameplay.mob_count is not authored any more")
    root = _copy(tmp_path / "c")
    _edit(root, "props.toml", 'prop_id = "pine"\n', 'prop_id = "pine"\ndensity_share = 1.0\n')
    _refused(root, "pine.density_share is not authored any more")
    root = _copy(tmp_path / "d")
    (root / "world.toml").unlink()
    _refused(root, "missing source file: world.toml")


def test_world_toml_refuses_what_no_generator_could_lay(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    _edit(
        root,
        "world.toml",
        'kind = "oblique-survival-world-v1"',
        'kind = "oblique-survival-world-v0"',
    )
    _refused(root, "world.toml kind must be oblique-survival-world-v1")
    root = _copy(tmp_path / "b")
    _edit(root, "world.toml", "[population]\n", "[population]\ncamp_clear_radius_meters = 6.0\n")
    _refused(root, "[population] has unknown keys")
    root = _copy(tmp_path / "c")
    _edit(root, "world.toml", "at = { distance_meters = [70.0, 140.0] }", 'at = "origin"')
    _refused(root, "exactly one set piece at")
    root = _copy(tmp_path / "d")
    _edit(root, "world.toml", 'set_piece = "camp"', 'set_piece = "boulder_ring"')
    _refused(root, "spawn.set_piece must name the origin set piece")
    root = _copy(tmp_path / "e")
    _edit(root, "world.toml", 'biome = "dry_meadow"', 'biome = "salt_flat"')
    _refused(root, "names unknown biome 'salt_flat'")
    root = _copy(tmp_path / "f")
    _edit(
        root,
        "world.toml",
        '{ prop = "campfire", state = "unlit"',
        '{ prop = "campfire", state = "roaring"',
    )
    _refused(root, "has no state 'roaring'")
    root = _copy(tmp_path / "g")
    _edit(root, "world.toml", "order = []", 'order = ["pine", "nothing"]')
    _refused(root, "population.order names unknown object 'nothing'")


def _add_to_placement(root: Path, prop_id: str, line: str) -> None:
    """Append a key to one prop's [props.placement] block, whatever its numbers are."""

    path = root / "props.toml"
    text = path.read_text()
    start = text.index(f'prop_id = "{prop_id}"')
    header = text.index("[props.placement]\n", start) + len("[props.placement]\n")
    path.write_text(text[:header] + line + "\n" + text[header:])


def test_a_placement_block_is_one_process_on_known_ground(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    _add_to_placement(root, "pine", "density_per_100m2 = 0.4")
    _refused(root, "pine.placement declares more than one process")
    root = _copy(tmp_path / "b")
    _edit(
        root,
        "props.toml",
        "habitat = { mossy_bog = 1.0, grey_scree = 0.35, forest_floor = 0.3, dry_meadow = 0.2 }",
        "habitat = { mossy_bog = 1.0, tundra = 0.35 }",
    )
    _refused(root, "dead_snag.placement.habitat names unknown biome 'tundra'")
    root = _copy(tmp_path / "c")
    _edit(
        root,
        "props.toml",
        'near = { host = "pine", radius_meters = 2.5, mean = 0.8, chance = 0.6 }',
        'near = { host = "oak", radius_meters = 2.5, mean = 0.8, chance = 0.6 }',
    )
    _refused(root, "fern_clump.placement.near.host names unknown object 'oak'")
    root = _copy(tmp_path / "d")
    _edit(
        root,
        "actors.toml",
        'avoid = [ { target = "campfire", radius_meters = 30.0 } ]',
        'avoid = [ { target = "lighthouse", radius_meters = 30.0 } ]',
    )
    _refused(root, "grub_hound.placement.avoid names unknown object 'lighthouse'")
    root = _copy(tmp_path / "e")
    _add_to_placement(root, "grass_tuft", "wander = 2")
    _refused(root, "grass_tuft.placement has unknown keys ['wander']")
    root = _copy(tmp_path / "f")
    _add_to_placement(root, "thorn_bush", "max_per_world = 3")
    _refused(root, "thorn_bush.placement.max_per_world 3 is below min_per_world")
