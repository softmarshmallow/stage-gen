"""Offline tests for graph identity, the scope ladder, and what a rehearsal writes.

The one thing these must prove is the claim the scope ladder rests on: a node
that appears in two scopes has the same id AND the same cache key in both, or a
narrow run's artifacts are paid for twice. Everything else here is the same
question asked of one part of the package at a time -- edit this brief, and
exactly these keys move.

    uv run pytest tests/unit/recipes/oblique_survival/test_graph.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import subprocess
from collections import Counter
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, Final, cast

import pytest

from gnode import LOCAL_OPERATION, BinaryArtifact, Node
from stage_gen.config import StageGenConfig
from stage_gen.recipes.oblique_survival import survival_prompts, survival_request
from stage_gen.recipes.oblique_survival.layout import build_layout
from stage_gen.recipes.oblique_survival.manifest import (
    MANIFEST_KIND,
    Manifest,
    _music_block,
    build_manifest,
    music_ref,
    prop_ref,
    state_ref,
)
from stage_gen.recipes.oblique_survival.models import (
    DEFAULT_MUSIC_TRANSITION,
    FOUR_WAY_FACINGS,
    SOUND_CUES,
    BiomeRules,
    Clutter,
    ItemUse,
    Look,
    Package,
    SheetSpec,
    SoundEffect,
    SourceError,
    Track,
)
from stage_gen.recipes.oblique_survival.prepared_survival import ObliqueSurvivalNodeHandler
from stage_gen.recipes.oblique_survival.survival_executor import ObliqueSurvivalExecutor
from stage_gen.recipes.oblique_survival.survival_graph import (
    MINIMAL_PROPS,
    ObliqueSurvivalGraph,
    _safe,
    build_graph,
)
from stage_gen.recipes.oblique_survival.survival_request import DigestLedger, load_package
from stage_gen.recipes.oblique_survival.survival_types import (
    REVIEW_FAMILIES,
    SCOPES,
    STRIKE_CELL_KINDS,
    TYPE_PREFIX,
)
from tests.unit.recipes.oblique_survival._survival_fixture import (
    _fixture_drops,
    _fixture_splash,
    _fixture_strike,
    write_fixture,
)

PACKAGE: Final = Path("library/games/ember-hollow")


def _clutter(package: Package) -> Clutter:
    """The authored litter sheet, which the fixture package has."""

    assert package.clutter is not None
    return package.clutter


def _prompt(node: Node) -> str:
    """The brief a node carries. Every generative node has one, by construction."""

    assert node.card is not None and node.card.prompt is not None
    return node.card.prompt


def _manifest(document: Manifest) -> dict[str, Any]:
    """The manifest read as the JSON a consumer receives.

    It is a TypedDict in the recipe so a producer cannot misspell a block. A
    test asserts about the document a consumer parses, and narrowing every
    nested block would say less about the claim than the claim does.
    """

    return cast(dict[str, Any], document)


@pytest.fixture(scope="module")
def package() -> Package:
    return load_package(PACKAGE)


@pytest.fixture(scope="module")
def config() -> StageGenConfig:
    # A graph is built from configuration, not credentials; an empty config must
    # be enough to plan, or planning could not be free.
    return StageGenConfig()


def _graph(config: StageGenConfig, package: Package, scope: str) -> ObliqueSurvivalGraph:
    return build_graph(config, package, scope)


def test_every_scope_builds(config: StageGenConfig, package: Package) -> None:
    for scope in SCOPES:
        graph = _graph(config, package, scope)
        assert graph.scope == scope
        assert graph.kind == "oblique-survival-execution-graph-v1"
        assert graph.presentation_profile == "elevated_oblique_perspective_ground_plane_v1"
        assert graph.publication_authorized is False


def test_building_twice_gives_the_same_digests(config: StageGenConfig, package: Package) -> None:
    first = _graph(config, package, "full")
    second = _graph(config, package, "full")
    assert first.graph_sha256 == second.graph_sha256
    assert first.topology_sha256 == second.topology_sha256


def test_the_ladder_only_ever_adds_nodes(config: StageGenConfig, package: Package) -> None:
    previous: set[str] = set()
    for scope in SCOPES:
        ids = {node.node_id for node in _graph(config, package, scope).nodes}
        assert previous <= ids, f"{scope} dropped nodes a narrower scope had"
        previous = ids


def test_a_shared_node_keeps_its_cache_key_across_scopes(
    config: StageGenConfig, package: Package
) -> None:
    """This is what makes --reuse-from pay rather than redraw."""

    keys: dict[str, dict[str, str]] = {}
    for scope in SCOPES:
        keys[scope] = {
            node.node_id: node.cache_key for node in _graph(config, package, scope).nodes
        }
    narrow = keys["minimal"]
    for scope in ("props", "actors", "full"):
        for node_id, cache_key in narrow.items():
            # The terminal manifest node depends on every node in its own graph,
            # so a wider scope legitimately changes it; nothing else may move.
            if node_id == "package-manifest":
                continue
            assert keys[scope][node_id] == cache_key, f"{node_id} moved in {scope}"


def test_the_minimal_scope_draws_what_a_played_demo_needs(
    config: StageGenConfig, package: Package
) -> None:
    graph = _graph(config, package, "minimal")
    generated = [node for node in graph.nodes if node.type_id.endswith("prop_sprite.generate")]
    sheets = [node for node in graph.nodes if node.type_id.endswith("prop_sheet.generate")]
    drawn_ids = {node.params["prop_id"] for node in generated} | {
        node.params["prop_id"] for node in sheets
    }
    assert drawn_ids == set(MINIMAL_PROPS)
    # A sprite prop draws its baseline plus the look its interaction leaves
    # behind: a picked thorn bush is bare. A sheet prop draws every look in
    # one op; there is no narrower way to draw a sheet.
    drawn = {(node.params["prop_id"], node.params["state"]) for node in generated}
    assert ("thorn_bush", "full") in drawn
    assert ("thorn_bush", "picked") in drawn
    assert {node.params["prop_id"] for node in sheets} == {
        "pine",
        "moss_boulder",
        "birch",
        "dead_snag",
    }
    assert len(generated) == 3
    assert len(sheets) == 4
    # And the items those interactions yield, so a pickup has a sprite to be.
    items = {
        node.params["item_id"]
        for node in graph.nodes
        if node.type_id.endswith("item_sprite.generate")
    }
    # The forage's items join them: what lies on the ground is played in a
    # minimal run, and once dropped again it needs a pickup sprite to be.
    assert package.forage is not None
    forage_items = {cell.item_id for cell in package.forage.cells}
    assert items == {"log", "berry", "stone"} | forage_items
    assert forage_items == {"twig", "flint", "stone", "mushroom", "moss"}
    grounds = [
        node
        for node in graph.nodes
        if node.type_id.endswith(("ground_texture.generate", "ground_texture.adopt"))
    ]
    assert len(grounds) == len(package.biomes)
    # The ground verdict is the whole ground: material, macro field, track, litter.
    for step in (
        "ground_macro.generate",
        "ground_road.generate",
        ("ground_clutter.generate", "ground_clutter.adopt"),
        "ground_water.generate",
    ):
        assert len([node for node in graph.nodes if node.type_id.endswith(step)]) == 1, step
    assert not [node for node in graph.nodes if node.type_id.endswith("motion_atlas.generate")]
    assert not [node for node in graph.nodes if node.type_id.endswith("fx_strip.generate")]


def test_the_full_scope_covers_every_authored_asset(
    config: StageGenConfig, package: Package
) -> None:
    graph = _graph(config, package, "full")
    by_type: dict[str, int] = {}
    for node in graph.nodes:
        by_type[node.type_id] = by_type.get(node.type_id, 0) + 1
    prefix = TYPE_PREFIX
    assert by_type[f"{prefix}/prop_sprite.generate"] == sum(
        len(prop.states) for prop in package.props if prop.sheet is None
    )
    assert by_type[f"{prefix}/prop_sheet.generate"] == sum(
        1 for prop in package.props if prop.sheet is not None
    )
    assert by_type[f"{prefix}/prop_sprite.anchor"] == len(package.props)
    assert by_type[f"{prefix}/item_sprite.generate"] == len(package.items)
    plate_types = (f"{prefix}/ground_texture.generate", f"{prefix}/ground_texture.adopt")
    assert sum(by_type.get(t, 0) for t in plate_types) == len(package.biomes)
    assert by_type.get(f"{prefix}/ground_texture.generate", 0) == sum(
        1 for biome in package.biomes if biome.take is None
    )
    # Every scope draws every biome; a one-material ground is no ground at all.
    minimal = _graph(config, package, "minimal")
    plates = [n for n in minimal.nodes if n.type_id in plate_types]
    assert len(plates) == len(package.biomes) >= 4
    assert by_type[f"{prefix}/ground_decal.generate"] == len(package.decals)
    assert by_type[f"{prefix}/ground_macro.generate"] == 1
    assert by_type[f"{prefix}/ground_road.generate"] == 1
    assert (
        by_type.get(f"{prefix}/ground_clutter.generate", 0)
        + by_type.get(f"{prefix}/ground_clutter.adopt", 0)
        == 1
    )
    assert (
        by_type.get(f"{prefix}/ground_forage.generate", 0)
        + by_type.get(f"{prefix}/ground_forage.adopt", 0)
        == 1
    )
    assert (
        by_type.get(f"{prefix}/item_icons.generate", 0)
        + by_type.get(f"{prefix}/item_icons.adopt", 0)
        == 1
    )
    assert by_type[f"{prefix}/ground_forage.validate"] == 1
    assert by_type[f"{prefix}/item_icons.validate"] == 1
    assert by_type[f"{prefix}/ground_water.generate"] == 1
    assert by_type[f"{prefix}/motion_atlas.generate"] == sum(
        len(actor.strips) for actor in package.actors
    )
    # The player draws four facings per state; the hound draws one card.
    assert len(package.player.strips) == 4 * len(package.player.states)
    assert len(package.mob.strips) == len(package.mob.states)
    assert by_type[f"{prefix}/actor_concept.generate"] == len(package.actors)
    assert by_type[f"{prefix}/fx_strip.generate"] == 1
    assert by_type[f"{prefix}/fx_dust.generate"] == 1
    assert by_type[f"{prefix}/family_review.judge"] == len(REVIEW_FAMILIES)


def test_every_operation_has_a_declared_route(config: StageGenConfig, package: Package) -> None:
    graph = _graph(config, package, "full")
    vocabulary = set(graph.operation_vocabulary())
    for node in graph.nodes:
        assert node.operation in vocabulary
    counts = graph.operation_counts()
    assert counts[LOCAL_OPERATION] > 0
    assert counts["image_generation"] > 0
    assert counts["tool_loop"] == len(package.props)


def test_no_provider_node_exceeds_the_attempt_ceiling(
    config: StageGenConfig, package: Package
) -> None:
    for node in _graph(config, package, "full").nodes:
        assert 1 <= node.max_attempts <= 6
        if node.operation == LOCAL_OPERATION:
            assert node.max_attempts == 1


def test_the_prompt_is_bound_into_node_identity(config: StageGenConfig, package: Package) -> None:
    """A prompt edit must invalidate its node, or a fix would never be redrawn."""

    def generates(graph: ObliqueSurvivalGraph) -> dict[str, str]:
        return {
            node.node_id: node.cache_key
            for node in graph.nodes
            if node.type_id.endswith(("prop_sprite.generate", "prop_sheet.generate"))
        }

    baseline = generates(_graph(config, package, "full"))
    # Twice: once for a sprite prop and once for a sheet prop, because the
    # sheet's prompt is a different function and must be bound the same way.
    for prop_id in ("fern_clump", "pine"):
        tweaked_props = list(package.props)
        index = next(i for i, p in enumerate(tweaked_props) if p.prop_id == prop_id)
        first = tweaked_props[index]
        tweaked_props[index] = replace(first, prompt=first.prompt + " Slightly different.")
        variant = replace(package, props=tuple(tweaked_props))
        changed = generates(_graph(config, variant, "full"))
        moved = [key for key in baseline if baseline[key] != changed.get(key)]
        assert moved, f"editing {prop_id}'s prompt changed no node's cache key"
        assert all(first.prop_id.replace("_", "-") in node_id for node_id in moved), (
            "editing one prop's prompt invalidated another prop's node"
        )


def test_editing_one_source_file_does_not_invalidate_unrelated_nodes(
    config: StageGenConfig, package: Package
) -> None:
    """Every generate node hangs off ``source-lock`` for ordering only.

    ``source-lock``'s own digest covers all four authored files. When nodes
    inherited its cache lineage, editing ``ground.toml`` invalidated every prop
    too: one live run reused 0 of 15 nodes and paid 7 provider operations for a
    one-file edit. The lock is a barrier edge now, so a node's identity comes
    from the source it actually reads.
    """

    def keys(pkg: Package, suffix: str | tuple[str, ...]) -> dict[str, str]:
        return {
            node.node_id: node.cache_key
            for node in _graph(config, pkg, "full").nodes
            if node.type_id.endswith(suffix)
        }

    # A plate is drawn or adopted; either way its brief is its identity.
    plates = ("ground_texture.generate", "ground_texture.adopt")
    props_before = keys(package, "prop_sprite.generate")
    ground_before = keys(package, plates)

    biomes = list(package.biomes)
    biomes[0] = replace(biomes[0], prompt=biomes[0].prompt + " Brighter.")
    variant = replace(package, biomes=tuple(biomes))

    assert keys(variant, "prop_sprite.generate") == props_before, (
        "editing a biome prompt moved a prop's cache key"
    )
    ground_after = keys(variant, plates)
    moved = [key for key in ground_before if ground_before[key] != ground_after[key]]
    assert len(moved) == 1, moved
    assert biomes[0].biome_id.replace("_", "-") in moved[0]


def test_the_lock_is_a_barrier_not_a_lineage_edge(config: StageGenConfig, package: Package) -> None:
    graph = _graph(config, package, "full")
    for node in graph.nodes:
        # The terminal manifest measures every published asset, so it genuinely
        # does depend on everything and must inherit all of it.
        if node.node_id == graph.terminal_node_id:
            continue
        if "source-lock" in node.depends_on:
            assert "source-lock" in node.barrier_only, (
                f"{node.node_id} inherits the whole package digest through the lock"
            )


def test_the_terminal_node_is_the_manifest(config: StageGenConfig, package: Package) -> None:
    graph = _graph(config, package, "full")
    assert graph.terminal_node_id == "package-manifest"
    terminal = next(node for node in graph.nodes if node.node_id == "package-manifest")
    assert len(terminal.depends_on) == len(graph.nodes) - 1


def test_a_dry_run_schedules_every_node_and_still_writes_a_manifest(
    package: Package, tmp_path: Path
) -> None:
    executor = ObliqueSurvivalExecutor(StageGenConfig(), scope="full")
    run_dir = tmp_path / "run"
    run = asyncio.run(
        executor.dry_run(
            PACKAGE,
            run_dir=run_dir,
            cache_dir=tmp_path / "cache",
            invocation_id="test-dry",
        )
    )
    graph = run.plan.graph
    plan = json.loads((run_dir / "execution-plan.json").read_bytes())
    assert len(plan["nodes"]) == len(graph.nodes)

    # The run report reads node status off the summary. Reading a field the
    # summary does not have printed a clean success over three failed nodes
    # once, so the shape the report depends on is pinned here.
    summary = run.summary
    assert summary.ok is True
    assert len(summary.nodes) == len(graph.nodes)
    statuses = {entry.status for entry in summary.nodes}
    assert statuses == {"succeeded"}, statuses
    assert all(entry.attempts >= 1 for entry in summary.nodes)
    # A rehearsal publishes placeholders, so the run holds no manifest at all.
    assert run.manifest is None

    # A dry run writes stubs at synthetic paths, never at the declared ports,
    # so a rebuilt manifest must come back complete in shape and honest in status.
    document = _manifest(executor.finalize(run_dir, input_path=PACKAGE))
    assert document["kind"] == MANIFEST_KIND
    # The look contract travels with the manifest, for the consumer that lays
    # the art down.
    assert document["look"] == {
        "light": "overhead",
        "mirror": "facing_only",
        "ground_pieces": {"orientation": "camera_facing", "jitter_degrees": 15.0},
    }
    assert set(document["status"]) == {
        "actors",
        "props",
        "ground",
        "ground_layers",
        "fx",
        "items",
        "music",
        "weather",
        "sounds",
        "seasons",
        "ui",
        "layout",
    }
    # The package authors an interface and the rehearsal drew none of it.
    assert document["status"]["ui"] == "missing"
    assert document["ui"] is None
    # A dry run composes nothing, and the manifest says so rather than guessing.
    assert document["status"]["music"] == "missing"
    assert document["music"] == {}
    assert document["status"]["weather"] == "missing"
    # The condition's clock and wash are authored, so they are published even
    # before a picture arrives: a consumer can drive the factor with no art.
    assert document["weather"]["rain"]["drops"] is None
    assert document["weather"]["rain"]["onset_seconds"] == package.weather[0].onset_seconds
    assert all(value == "missing" for value in document["status"].values())
    assert document["publication_authorized"] is False
    assert (run_dir / "manifest.json").is_file()


def test_an_invocation_id_may_not_escape_the_run_it_names(tmp_path: Path) -> None:
    """The spike confined a run directory it chose itself.

    The recipe is handed its run directory by the CLI, so what a caller still
    names is the invocation id, and the same refusal guards it.
    """

    executor = ObliqueSurvivalExecutor(StageGenConfig(), scope="minimal")
    for bad in ("../../etc", "/tmp/elsewhere"):
        with pytest.raises(ValueError, match="one safe path segment"):
            asyncio.run(
                executor.dry_run(
                    PACKAGE,
                    run_dir=tmp_path / "run",
                    cache_dir=tmp_path / "cache",
                    invocation_id=bad,
                )
            )
    assert not (tmp_path / "run").exists(), "a refused invocation left a run behind"


def test_the_seam_policy_rewrites_the_prop_prompt_and_the_review(package: Package) -> None:
    prop = package.prop("pine")
    banned = survival_prompts.prop_prompt(package, prop, "standing")
    assert "no ground patch" in banned and "fading softly" not in banned
    painted = survival_prompts.prop_prompt(
        replace(package, ground_contact="painted_base"), prop, "standing"
    )
    assert "fading softly to fully transparent" in painted and "no ground patch" not in painted
    assert (
        "no ground patch" in survival_prompts.family_review_prompt("props", ["pine"], "shadow")
        or True
    )
    assert "feathered patch of ground at its base" in survival_prompts.family_review_prompt(
        "props", ["pine"], "painted_base"
    )


def test_an_unknown_seam_policy_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "source"
    shutil.copytree(PACKAGE, root)
    survival = root / "survival.toml"
    survival.write_text(
        survival.read_text().replace('ground_contact = "skirt_decal"', 'ground_contact = "glue"')
    )
    with pytest.raises(SourceError):
        load_package(root)


def test_the_layout_node_changes_identity_with_the_seam_policy(
    config: StageGenConfig, package: Package
) -> None:
    """The layout lays skirts only under skirt_decal, so the policy is its identity."""

    def layout_key(pkg: Package) -> str:
        graph = build_graph(config, pkg, "minimal")
        return next(node.cache_key for node in graph.nodes if node.node_id == "world-layout")

    assert layout_key(package) != layout_key(replace(package, ground_contact="shadow"))


# --- the look contract -----------------------------------------------------------------


def test_every_generative_prompt_states_the_one_light(package: Package) -> None:
    """A 2.5D scene has no runtime light, so every drawing must agree on one."""

    clause = survival_prompts.light_clause(package)
    assert clause == survival_prompts.LIGHT_CLAUSES["overhead"]
    carriers = [
        survival_prompts.prop_prompt(package, package.prop("thorn_bush"), "full"),
        survival_prompts.prop_sheet_prompt(package, package.prop("pine")),
        survival_prompts.item_prompt(package, "log", "a log"),
        survival_prompts.actor_concept_prompt(package, package.player),
        survival_prompts.actor_motion_prompt(
            package, package.player, package.player.states[0].state
        ),
        *(survival_prompts.decal_prompt(package, decal) for decal in package.decals),
    ]
    if package.clutter is not None:
        carriers.append(survival_prompts.clutter_prompt(package, package.clutter))
    for prompt in carriers:
        assert clause in prompt
    # The review asks the same question of the finished set.
    assert "lit from directly overhead" in survival_prompts.family_review_prompt("props", ["pine"])


def test_a_patch_prompt_asks_for_a_shape_and_never_a_ring(package: Package) -> None:
    for decal in package.decals:
        prompt = survival_prompts.decal_prompt(package, decal)
        assert survival_prompts.PATCH_SHAPE_CLAUSE in prompt
        assert "ring" not in decal.prompt.lower(), decal.decal_id
        assert "circle" not in decal.prompt.lower(), decal.decal_id


def test_the_layout_identity_carries_the_look(config: StageGenConfig, package: Package) -> None:
    def layout_key(pkg: Package) -> str:
        graph = build_graph(config, pkg, "minimal")
        return next(node.cache_key for node in graph.nodes if node.node_id == "world-layout")

    jittered = replace(package, look=Look(light="overhead", ground_piece_jitter_degrees=5.0))
    assert layout_key(package) != layout_key(jittered)


def test_the_look_refuses_a_light_it_has_no_clause_for(tmp_path: Path) -> None:
    root = tmp_path / "source"
    shutil.copytree(PACKAGE, root)
    survival = root / "survival.toml"
    text = survival.read_text()
    survival.write_text(text.replace('light = "overhead"', 'light = "upper_left"'))
    with pytest.raises(SourceError, match=r"look\.light"):
        load_package(root)
    survival.write_text(text.replace('light = "overhead"', 'light = "overhead"\nmirror = true'))
    with pytest.raises(SourceError, match="not a choice"):
        load_package(root)


# --- the style plate -------------------------------------------------------------------


def test_the_style_plate_is_declared_and_digested(package: Package) -> None:
    assert package.style_reference == "references/style-plate.png"
    assert package.style_reference_digest
    # The plate is part of the package digest, so redrawing it re-locks the source.
    assert package.digests["references/style-plate.png"] == package.style_reference_digest


def test_the_plate_rides_on_generative_prompts_and_not_on_paintovers(package: Package) -> None:
    carried = survival_prompts.prop_prompt(package, package.prop("birch"), "standing")
    assert survival_prompts.STYLE_PLATE_CLAUSE in carried

    clutter = package.clutter
    assert clutter is not None
    paintover = survival_prompts.clutter_prompt(package, clutter)
    assert survival_prompts.STYLE_PLATE_CLAUSE not in paintover
    # Reference image 1 is the lattice there, and the prompt says so.
    assert "Edit reference image 1" in paintover

    fire = survival_prompts.fire_strip_prompt(package, package.fire.columns, package.fire.rows)
    assert survival_prompts.STYLE_PLATE_CLAUSE not in fire


def test_a_package_without_a_plate_says_nothing_about_one(package: Package) -> None:
    bare = replace(package, style_reference=None, style_reference_digest=None)
    assert survival_prompts.STYLE_PLATE_CLAUSE not in survival_prompts.prop_prompt(
        bare, bare.prop("birch"), "standing"
    )


def test_redrawing_the_plate_rebills_the_nodes_that_carry_it(
    config: StageGenConfig, package: Package, tmp_path: Path
) -> None:
    """The prompt text does not change when the picture does, so the bytes must."""

    root = tmp_path / "source"
    shutil.copytree(PACKAGE, root)
    plate = root / "references" / "style-plate.png"
    plate.write_bytes(plate.read_bytes() + b"\x00")  # a different picture, same words
    # ui.toml binds the same plate by digest, so redrawing it is re-declared there.
    assert package.style_reference_digest is not None
    ui_document = root / "ui.toml"
    ui_document.write_text(
        ui_document.read_text().replace(
            package.style_reference_digest, hashlib.sha256(plate.read_bytes()).hexdigest()
        )
    )
    redrawn = load_package(root)
    assert redrawn.style_reference_digest != package.style_reference_digest

    def keys(pkg: Package) -> dict[str, str]:
        graph = build_graph(config, pkg, "full")
        return {node.node_id: node.cache_key for node in graph.nodes}

    before, after = keys(package), keys(redrawn)
    moved = {node_id for node_id in before if before[node_id] != after[node_id]}
    # every carrier moved ...
    assert "prop-fern-clump-full-generate" in moved
    # An adopted plate carries the plate too: the take answered a brief drawn
    # against it, so a new plate re-adopts (0 ops) rather than staying put.
    floor = package.biome("forest_floor")
    assert f"ground-forest-floor-{'adopt' if floor.take else 'generate'}" in moved
    # A sheet is drawn on the sprite route and carries the plate like a sprite.
    assert "prop-pine-sheet-generate" in moved
    assert "actor-wren-concept" in moved
    # The interface sheets are drawn against the plate too, through ui.toml.
    assert "ui-panel_frame-generate" in moved
    # ... and the paintovers, which never see the plate, did not.
    assert "fx-fire-generate" not in moved
    assert "ground-macro-generate" not in moved


def test_a_plate_outside_the_package_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "source"
    shutil.copytree(PACKAGE, root)
    survival = root / "survival.toml"
    original = survival.read_text()
    for bad in ('"../style-plate.png"', '"/etc/passwd.png"', '"references/missing.png"'):
        survival.write_text(original.replace('"references/style-plate.png"', bad))
        with pytest.raises(SourceError):
            load_package(root)


# --- the prop sheet ----------------------------------------------------------------------


def test_a_sheet_prop_splits_into_the_same_per_look_ports_a_sprite_prop_has(
    config: StageGenConfig, package: Package
) -> None:
    graph = _graph(config, package, "minimal")
    by_id = {node.node_id: node for node in graph.nodes}
    validate = by_id["prop-pine-sheet-validate"]
    pine = package.prop("pine")
    for state in pine.states:
        assert validate.port(f"image_{state}").artifact_ref == prop_ref("pine", state)
        assert validate.port(f"validation_{state}").artifact_ref == (
            f"production/validation/props/pine-{state}.json"
        )
    assert validate.port("sheet").artifact_ref == "production/props/pine.sheet.png"
    # The anchor loop hangs off the sheet's validate node and keeps its id.
    anchor = by_id["prop-pine-anchor"]
    assert "prop-pine-sheet-validate" in anchor.depends_on
    # No lattice: the sheet is drawn with true alpha on the sprite route and
    # split by arithmetic, so the only template node is the litter's 4x4.
    assert "templates-draw-2x2-512px" not in by_id
    assert "templates-draw-4x4-alpha" in by_id
    assert "prop-pine-standing-generate" not in by_id
    generate = by_id["prop-pine-sheet-generate"]
    assert not any("templates" in dep for dep in generate.depends_on)


def test_turning_one_prop_into_a_sheet_moves_no_other_prop(
    config: StageGenConfig, package: Package
) -> None:
    before = {node.node_id: node.cache_key for node in _graph(config, package, "full").nodes}
    bush = package.prop("thorn_bush")
    sheeted = replace(
        bush,
        states=("full", "picked", "bare", "burnt"),
        state_prompt={**bush.state_prompt, "bare": "no leaves", "burnt": "charred"},
        sheet=SheetSpec(columns=2, rows=2),
    )
    variant = replace(
        package, props=tuple(sheeted if p.prop_id == "thorn_bush" else p for p in package.props)
    )
    after = {node.node_id: node.cache_key for node in _graph(config, variant, "full").nodes}
    assert "prop-thorn-bush-sheet-generate" in after
    for node_id, key in before.items():
        if "thorn-bush" in node_id or node_id in {"package-manifest", "world-layout"}:
            continue
        # The bush's season looks hang off its summer sprites, and the seasons
        # review judges them beside their twins, so both move with it.
        if node_id.startswith(("review-props", "review-seasons")):
            continue
        assert after[node_id] == key, f"{node_id} moved"
    assert after["templates-draw-4x4-alpha"] == before["templates-draw-4x4-alpha"]


def test_the_sheet_prompt_lists_the_looks_in_reading_order_at_one_scale(package: Package) -> None:
    pine = package.prop("pine")
    prompt = survival_prompts.prop_sheet_prompt(package, pine)
    positions = [prompt.index(f"{state} (") for state in pine.states]
    assert positions == sorted(positions)
    # The authored sizes travel as words the model can act on.
    assert "grown (the reference, full height)" in prompt
    assert "stump (about a sixth the height of the grown look (12%))" in prompt
    assert "ONE shared drawing scale" in prompt
    assert "grown look is the reference" in prompt
    assert "never enlarged to fill" in prompt
    assert survival_prompts.light_clause(package) in prompt
    # Native alpha on the sprite route, the plate riding as reference image 1;
    # never a paintover, never magenta.
    assert survival_prompts.STYLE_PLATE_CLAUSE in prompt
    assert survival_prompts.NO_FLOOR_CLAUSE in prompt
    assert "Edit reference image 1" not in prompt
    assert "magenta" not in prompt
    assert "do not draw the grid" in prompt
    assert "cell 1" not in prompt


def test_a_sized_sprite_look_may_fill_its_canvas_and_an_unsized_one_may_not(
    package: Package,
) -> None:
    bush = package.prop("thorn_bush")
    # picked is unsized: it rides the baseline's ruler and must keep its scale.
    assert "exactly the same drawing scale" in survival_prompts.prop_prompt(package, bush, "picked")
    sized = replace(bush, look_height_units={"picked": 0.3})
    prompt = survival_prompts.prop_prompt(package, sized, "picked")
    assert "filling the canvas" in prompt
    assert "about half the height of the full look (55%)" in prompt
    assert "exactly the same drawing scale" not in prompt


# --- facings ------------------------------------------------------------------------------


def test_the_player_always_carries_the_four_way_facing_set(package: Package) -> None:
    assert package.player.facings.set == "four_way"
    assert package.player.facings.facings == FOUR_WAY_FACINGS
    assert package.mob.facings.set == "single_mirrored"
    assert package.mob.facings.facings == ()
    assert package.player.baseline_key == "idle.front"
    assert package.mob.baseline_key == "idle"
    with pytest.raises(SourceError, match="always carries the four_way"):
        survival_request._facings({"set": "single_mirrored"}, role="player", key="player")
    with pytest.raises(SourceError, match="side_view"):
        survival_request._facings(
            {"set": "four_way", "side_view": "isometric"}, role="player", key="player"
        )
    assert survival_request._facings(None, role="mob", key="mob").set == "single_mirrored"
    assert survival_request._facings(None, role="player", key="player").side_view == "quarter"


def test_a_facing_prompt_names_its_view_and_the_front_reference(package: Package) -> None:
    player = package.player
    front = survival_prompts.actor_motion_prompt(package, player, "walk", facing="front")
    back = survival_prompts.actor_motion_prompt(package, player, "walk", facing="back")
    left = survival_prompts.actor_motion_prompt(package, player, "walk", facing="left")
    single = survival_prompts.actor_motion_prompt(package, package.mob, "walk")
    assert "seen squarely from the front" in front
    assert "Reference image 2" not in front
    assert "facing directly away from the viewer" in back
    assert "Reference image 2 is the same action seen from the front" in back
    assert "turned toward the viewer's left" in left
    assert "three-quarter-front view" in single and "four-facing set" not in single
    assert len({front, back, left}) == 3
    # The light contract holds on every facing.
    for prompt in (front, back, left):
        assert survival_prompts.light_clause(package) in prompt


def test_the_four_way_strips_hang_off_the_front_and_the_hound_keeps_its_ids(
    config: StageGenConfig, package: Package
) -> None:
    graph = _graph(config, package, "actors")
    by_id = {node.node_id: node for node in graph.nodes}
    assert "actor-wren-state-walk-front-generate" in by_id
    assert "actor-wren-state-walk-left-generate" in by_id
    assert "actor-wren-state-walk-generate" not in by_id
    left = by_id["actor-wren-state-walk-left-generate"]
    assert "actor-wren-state-walk-front-validate" in left.depends_on
    assert "actor-wren-concept" in left.depends_on
    front = by_id["actor-wren-state-walk-front-generate"]
    assert front.depends_on == ("actor-wren-concept",) or list(front.depends_on) == [
        "actor-wren-concept"
    ]
    # The single mirrored hound is untouched: same ids, same ports.
    hound = by_id["actor-grub-hound-state-walk-validate"]
    assert hound.port("image").artifact_ref == state_ref("grub_hound", "walk")
    assert by_id["actor-wren-state-walk-left-validate"].port("image").artifact_ref == (
        "package/actors/wren/states/walk.left.png"
    )


def test_music_is_two_loops_in_full_scope_and_nothing_below(
    config: StageGenConfig, package: Package
) -> None:
    prefix = TYPE_PREFIX
    full = _graph(config, package, "full")
    by_type = Counter(node.type_id for node in full.nodes)
    assert len(package.music) == 2
    drawn = [track for track in package.music if track.take is None]
    adopted = [track for track in package.music if track.take is not None]
    assert by_type[f"{prefix}/music_track.generate"] == len(drawn)
    assert by_type[f"{prefix}/music_track.adopt"] == len(adopted)
    assert by_type[f"{prefix}/music_track.validate"] == len(package.music)
    assert full.operation_counts()["music_generation"] == len(drawn)
    assert "music_generation" in full.operation_vocabulary()
    for scope in ("minimal", "props", "actors"):
        assert _graph(config, package, scope).operation_counts()["music_generation"] == 0
    day = package.music[0]
    day_id = _safe("day_theme")
    step = "adopt" if day.take is not None else "generate"
    generate = full.node(f"music-{day_id}-{step}")
    validate = full.node(f"music-{day_id}-validate")
    assert generate.depends_on == ("source-lock",)
    assert validate.depends_on == (generate.node_id,)
    assert validate.port("audio").artifact_ref == "package/music/day_theme.mp3"
    # The brief is verbatim; only the originality clause follows it.
    assert _prompt(generate).startswith(day.prompt)
    assert "Do not quote an existing melody" in _prompt(generate)


def test_a_music_brief_edit_rebills_only_its_own_track(
    config: StageGenConfig, package: Package
) -> None:
    def keys(graph: ObliqueSurvivalGraph) -> dict[str, str]:
        return {
            node.node_id: node.cache_key
            for node in graph.nodes
            if node.node_id.startswith("music-") or node.type_id.endswith("fx_strip.generate")
        }

    def step(track: Track) -> str:
        return "adopt" if track.take is not None else "generate"

    baseline = keys(_graph(config, package, "full"))
    night = next(track for track in package.music if track.cue == "night")
    day = next(track for track in package.music if track.cue == "day")
    tweaked = tuple(
        replace(track, prompt=track.prompt + " Slower still.") if track is night else track
        for track in package.music
    )
    changed = keys(_graph(config, replace(package, music=tweaked), "full"))
    night_id, day_id = _safe("night_theme"), _safe("day_theme")
    assert changed[f"music-{night_id}-{step(night)}"] != baseline[f"music-{night_id}-{step(night)}"]
    assert changed[f"music-{night_id}-validate"] != baseline[f"music-{night_id}-validate"]
    assert changed[f"music-{day_id}-{step(day)}"] == baseline[f"music-{day_id}-{step(day)}"]
    assert changed["fx-fire-generate"] == baseline["fx-fire-generate"]
    # Dropping a take re-bills that track as a provider draw and nothing else.
    if day.take is not None:
        redrawn = keys(
            _graph(config, replace(package, music=(replace(day, take=None), night)), "full")
        )
        assert f"music-{day_id}-generate" in redrawn and f"music-{day_id}-adopt" not in redrawn
        assert (
            redrawn[f"music-{night_id}-{step(night)}"]
            == baseline[f"music-{night_id}-{step(night)}"]
        )


def test_the_music_loader_wants_exactly_one_track_per_cue() -> None:
    def track(track_id: str, cue: str) -> dict[str, object]:
        return {
            "track_id": track_id,
            "cue": cue,
            "target_duration_seconds": 90,
            "prompt": "A loop.",
        }

    with pytest.raises(SourceError, match="needs a package root"):
        survival_request._music(
            {"tracks": [{**track("a", "day"), "take": "music/x.mp3"}, track("b", "night")]}
        )
    with pytest.raises(SourceError, match="not a file inside the package"):
        survival_request._music(
            {"tracks": [{**track("a", "day"), "take": "music/missing.mp3"}, track("b", "night")]},
            root=PACKAGE,
            digests=DigestLedger(),
        )
    with pytest.raises(SourceError, match=r"relative \.mp3 path"):
        survival_request._music(
            {"tracks": [{**track("a", "day"), "take": "../music.toml"}, track("b", "night")]},
            root=PACKAGE,
            digests=DigestLedger(),
        )

    assert survival_request._music(None) == ()
    loaded = survival_request._music({"tracks": [track("a", "day"), track("b", "night")]})
    assert [t.cue for t in loaded] == ["day", "night"]
    with pytest.raises(SourceError, match="two tracks for the 'day' cue"):
        survival_request._music({"tracks": [track("a", "day"), track("b", "day")]})
    with pytest.raises(SourceError, match="no track for the 'night' cue"):
        survival_request._music({"tracks": [track("a", "day")]})
    with pytest.raises(SourceError, match="cue must be one of"):
        survival_request._music({"tracks": [track("a", "dusk"), track("b", "night")]})
    with pytest.raises(SourceError, match="repeats track_id"):
        survival_request._music({"tracks": [track("a", "day"), track("a", "night")]})


def test_the_music_transition_is_mixing_that_no_provider_node_reads(
    config: StageGenConfig, package: Package, tmp_path: Path
) -> None:
    """[transition] says how a consumer changes loops. It is mixing, so the
    loader reads it, the manifest publishes it, and retuning it must not cost
    a single provider operation."""

    assert survival_request._music_transition(None) == DEFAULT_MUSIC_TRANSITION
    assert survival_request._music_transition({}) == DEFAULT_MUSIC_TRANSITION
    tuned = survival_request._music_transition(
        {"transition": {"crossfade_seconds": 1.5, "curve": "linear", "overlap": 0.0}}
    )
    assert (tuned.crossfade_seconds, tuned.curve, tuned.overlap) == (1.5, "linear", 0.0)
    assert tuned.switch_at == DEFAULT_MUSIC_TRANSITION.switch_at
    with pytest.raises(SourceError, match="curve must be one of"):
        survival_request._music_transition({"transition": {"curve": "s_curve"}})
    with pytest.raises(SourceError, match="unknown keys"):
        survival_request._music_transition({"transition": {"fade_seconds": 2}})
    with pytest.raises(SourceError, match=r"transition\.overlap"):
        survival_request._music_transition({"transition": {"overlap": 1.4}})
    with pytest.raises(SourceError, match="must be a table"):
        survival_request._music_transition({"transition": 2.5})

    # Through the real file, so the source digests move exactly as they would.
    edited = tmp_path / "source"
    shutil.copytree(PACKAGE, edited)
    music = edited / "music.toml"
    music.write_text(
        music.read_text()
        .replace("crossfade_seconds = 2.5", "crossfade_seconds = 0.9")
        .replace('curve = "equal_power"', 'curve = "linear"')
    )
    retuned = load_package(edited)
    assert retuned.music_transition.crossfade_seconds == 0.9
    before = {node.node_id: node for node in _graph(config, package, "full").nodes}
    after = {node.node_id: node for node in _graph(config, retuned, "full").nodes}
    assert set(before) == set(after)
    moved = {node_id for node_id in before if before[node_id].cache_key != after[node_id].cache_key}
    # The lock ledgers every source byte and the manifest publishes the fade;
    # both are local. Nothing that spends moves.
    assert moved == {"source-lock", "package-manifest"}
    assert all(before[node_id].operation == LOCAL_OPERATION for node_id in moved)


def test_the_manifest_publishes_the_transition_beside_the_cues(
    package: Package, tmp_path: Path
) -> None:
    block = _music_block(package, tmp_path)
    assert block == {}, "no audio on disk is no block at all, transition included"
    for track in package.music:
        path = tmp_path / music_ref(track.track_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not really an mp3")
    block = _music_block(package, tmp_path)
    assert set(block) == {"day", "night", "transition"}
    assert block["transition"] == {
        "crossfade_seconds": package.music_transition.crossfade_seconds,
        "curve": package.music_transition.curve,
        "overlap": package.music_transition.overlap,
        "switch_at": package.music_transition.switch_at,
    }


def test_the_music_gate_refuses_a_short_or_silent_loop(tmp_path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed")

    def tone(seconds: float, volume: str) -> bytes:
        out = tmp_path / f"tone-{seconds}-{volume}.mp3"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency=220:duration={seconds}",
                "-af",
                f"volume={volume}",
                "-b:a",
                "128k",
                str(out),
            ],
            check=True,
        )
        return out.read_bytes()

    # Called exactly the way the music service calls every validator: with
    # the artifact, never bare bytes. The first live run paid for that gap.
    def gate(data: bytes) -> dict[str, Any]:
        return dict(
            ObliqueSurvivalNodeHandler._gate_music(
                BinaryArtifact(data=data, media_type="audio/mpeg")
            )
        )

    record = gate(tone(50, "1.0"))
    assert record["duration_seconds"] == pytest.approx(50, abs=0.2)
    assert -30 < record["peak_dbfs"] < 0
    with pytest.raises(ValueError, match="under the 45 s floor"):
        gate(tone(20, "1.0"))
    with pytest.raises(ValueError, match="under the -30 dBFS floor"):
        gate(tone(50, "0.001"))


# --- weather --------------------------------------------------------------------------


def test_weather_is_full_scope_only_and_each_layer_is_its_own_op(
    config: StageGenConfig, package: Package
) -> None:
    prefix = TYPE_PREFIX
    full = _graph(config, package, "full")
    by_type = Counter(node.type_id for node in full.nodes)
    rain = package.weather[0]
    assert rain.condition_id == "rain"
    snow = next(c for c in package.weather if c.condition_id == "snow")
    assert snow.cover is not None and snow.drops is not None and snow.drops.shape == "blob"
    # Two drops sheets (rain, snow), one cover plate, one splash sheet, one bolt sheet.
    assert by_type[f"{prefix}/weather_drops.generate"] == 2
    assert by_type[f"{prefix}/weather_cover.generate"] == 1
    assert by_type[f"{prefix}/weather_ground.generate"] == 1
    cover = full.node("weather-snow-cover-canonicalize")
    assert cover.port("image").artifact_ref == "package/weather/snow/cover.png"
    assert full.node("weather-snow-cover-generate").depends_on == ("source-lock",)
    # The snow sheet's clause is round; the rain sheet's prompt is what it always was.
    assert "rounded shape" in _prompt(full.node("weather-snow-drops-generate"))
    assert "The streak fills most of its half" in _prompt(full.node("weather-rain-drops-generate"))
    assert by_type[f"{prefix}/weather_strike.generate"] == 1
    snow = next(c for c in package.weather if c.condition_id == "snow")
    assert (
        by_type[f"{prefix}/weather_sound.generate"]
        == len(rain.sound_cues) + len(snow.sound_cues)
        == 3
    )
    # The interaction clips (sounds.toml) share the route; the weather's are these three.
    drawn_clips = sum(1 for clip in package.sounds if clip.take is None)
    assert full.operation_counts()["sound_effect_generation"] == 3 + drawn_clips
    assert "sound_effect_generation" in full.operation_vocabulary()
    # The wet layer is an ordinary decal, drawn in every scope with the ground.
    for scope in ("minimal", "props", "actors"):
        graph = _graph(config, package, scope)
        assert not [n for n in graph.nodes if n.node_id.startswith("weather-")]
        assert graph.node("decal-puddle-generate") is not None
        assert graph.operation_counts()["sound_effect_generation"] == 0
    # Every picture hangs off the lock; a bolt re-brief never re-bills the drops.
    for layer in ("drops", "ground", "strike"):
        generate = full.node(f"weather-rain-{layer}-generate")
        assert generate.depends_on == ("source-lock",)
        validate = full.node(f"weather-rain-{layer}-validate")
        assert validate.depends_on == (generate.node_id,)
        assert validate.port("image").artifact_ref == f"package/weather/rain/{layer}.png"
    ambience = full.node("weather-rain-sound-ambience-generate")
    assert rain.sound is not None and rain.sound.ambience is not None
    assert _prompt(ambience) == rain.sound.ambience.prompt
    assert full.node("weather-rain-sound-ambience-validate").port("audio").artifact_ref == (
        "package/weather/rain/sound-ambience.mp3"
    )
    # The drops carry no style plate and none of the world's keywords: a
    # model given "a conifer is stacked ragged masses" draws a conifer.
    drops = full.node("weather-rain-drops-generate")
    assert "LEFT half" in _prompt(drops) and "RIGHT half" in _prompt(drops)
    assert "conifer" not in _prompt(drops)
    assert "Reference image 1" not in _prompt(drops)
    # The bolt and splash sheets are objects, and objects carry the plate.
    assert "Reference image 1" in _prompt(full.node("weather-rain-strike-generate"))


def test_a_weather_brief_edit_rebills_only_its_own_layer(
    config: StageGenConfig, package: Package
) -> None:
    def keys(graph: ObliqueSurvivalGraph) -> dict[str, str]:
        return {
            node.node_id: node.cache_key
            for node in graph.nodes
            if node.node_id.startswith(("weather-", "fx-", "decal-puddle", "world-layout"))
        }

    baseline = keys(_graph(config, package, "full"))
    rain = package.weather[0]
    assert rain.strike is not None and rain.wet is not None
    tweaked = replace(rain, strike=replace(rain.strike, prompt=rain.strike.prompt + " Thicker."))
    changed = keys(_graph(config, replace(package, weather=(tweaked,)), "full"))
    assert changed["weather-rain-strike-generate"] != baseline["weather-rain-strike-generate"]
    assert changed["weather-rain-strike-validate"] != baseline["weather-rain-strike-validate"]
    for node_id in (
        "weather-rain-drops-generate",
        "weather-rain-ground-generate",
        "weather-rain-sound-ambience-generate",
        "fx-fire-generate",
        "decal-puddle-generate",
        "world-layout",
    ):
        assert changed[node_id] == baseline[node_id], node_id
    # The puddle density is the layout's business and nobody else's.
    denser = replace(rain, wet=replace(rain.wet, per_100_sqm=2.0))
    relaid = keys(_graph(config, replace(package, weather=(denser,)), "full"))
    assert relaid["world-layout"] != baseline["world-layout"]
    assert relaid["weather-rain-drops-generate"] == baseline["weather-rain-drops-generate"]


def test_the_weather_loader_refuses_what_no_consumer_could_play(package: Package) -> None:
    def doc(**overrides: object) -> dict[str, object]:
        rain = {
            "condition_id": "rain",
            "onset_seconds": 10.0,
            "decay_seconds": 10.0,
            "dry_spell_seconds": [10.0, 20.0],
            "wet_spell_seconds": [10.0, 20.0],
            "drops": {
                "kinds": ["streak", "drop"],
                "count_per_screen": 100,
                "fall_speed_meters_per_second": 10.0,
                "height_units": 0.3,
                "prompt": "a streak and a drop",
            },
        }
        rain.update(overrides)
        return {"kind": "oblique-survival-weather-v1", "conditions": [rain]}

    assert survival_request._weather(None, decals=package.decals) == ()
    loaded = survival_request._weather(doc(), decals=package.decals)
    assert loaded[0].drops is not None and loaded[0].ground is None
    with pytest.raises(SourceError, match="condition_id must be one of"):
        survival_request._weather(doc(condition_id="hail"), decals=package.decals)
    # Snow with only a cover is a condition; the cover's band is pale.
    snowy = survival_request._weather(
        doc(condition_id="snow", drops=None, cover={"texel_meters": 2.0, "prompt": "snow"}),
        decals=package.decals,
    )
    assert snowy[0].cover is not None and snowy[0].cover.value_target == 0.82
    with pytest.raises(SourceError, match=r"drops\.shape must be one of"):
        survival_request._weather(
            doc(
                drops={
                    "kinds": ["a", "b"],
                    "count_per_screen": 10,
                    "fall_speed_meters_per_second": 1.0,
                    "height_units": 0.1,
                    "prompt": "x",
                    "shape": "star",
                }
            ),
            decals=package.decals,
        )
    with pytest.raises(SourceError, match='does not declare with use = "wet"'):
        survival_request._weather(
            doc(wet={"decal_id": "path", "per_100_sqm": 1.0, "dry_seconds": 30.0}),
            decals=package.decals,
        )
    with pytest.raises(SourceError, match="exactly four distinct quadrant cells"):
        survival_request._weather(
            doc(
                ground={
                    "kinds": ["a", "b"],
                    "height_units": 0.1,
                    "rate_per_100_sqm_per_second": 1.0,
                    "prompt": "x",
                }
            ),
            decals=package.decals,
        )
    with pytest.raises(SourceError, match="ordered low then high"):
        survival_request._weather(doc(dry_spell_seconds=[30.0, 10.0]), decals=package.decals)
    with pytest.raises(SourceError, match=r"needs a \[conditions\.strike\] layer"):
        survival_request._weather(
            doc(sound={"strike": {"prompt": "thunder", "duration_seconds": 3.0}}),
            decals=package.decals,
        )
    with pytest.raises(SourceError, match="declares no layer at all"):
        survival_request._weather(doc(drops=None), decals=package.decals)


def test_the_sound_gate_takes_the_artifact_and_refuses_a_short_clip(tmp_path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed")

    def tone(seconds: float, volume: str) -> bytes:
        out = tmp_path / f"tone-{seconds}-{volume}.mp3"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency=220:duration={seconds}",
                "-af",
                f"volume={volume}",
                "-b:a",
                "128k",
                str(out),
            ],
            check=True,
        )
        return out.read_bytes()

    def gate(data: bytes, seconds: float) -> dict[str, Any]:
        return dict(
            ObliqueSurvivalNodeHandler._gate_sound(
                BinaryArtifact(data=data, media_type="audio/mpeg"), duration_seconds=seconds
            )
        )

    record = gate(tone(5, "0.5"), 5.0)
    assert record["duration_seconds"] == pytest.approx(5, abs=0.2)
    assert -30 < record["peak_dbfs"] < -0.1
    with pytest.raises(ValueError, match=r"short of the 5\.0 s asked"):
        gate(tone(3, "0.5"), 5.0)
    with pytest.raises(ValueError, match="effectively silent"):
        gate(tone(5, "0.0001"), 5.0)


def test_sound_effects_are_one_op_per_cue_in_full_scope_and_nothing_below(
    config: StageGenConfig, package: Package
) -> None:
    prefix = TYPE_PREFIX
    full = _graph(config, package, "full")
    by_type = Counter(node.type_id for node in full.nodes)
    assert [clip.cue for clip in package.sounds] == list(SOUND_CUES)
    drawn = [clip for clip in package.sounds if clip.take is None]
    adopted = [clip for clip in package.sounds if clip.take is not None]
    assert by_type[f"{prefix}/sound_effect.generate"] == len(drawn)
    assert by_type[f"{prefix}/sound_effect.adopt"] == len(adopted)
    assert by_type[f"{prefix}/sound_effect.validate"] == len(package.sounds)
    weather_ops = sum(len(condition.sound_cues) for condition in package.weather)
    assert full.operation_counts()["sound_effect_generation"] == weather_ops + len(drawn)
    for scope in ("minimal", "props", "actors"):
        assert not [
            n for n in _graph(config, package, scope).nodes if n.node_id.startswith("sound-")
        ]
    for clip in package.sounds:
        step = "adopt" if clip.take is not None else "generate"
        generate = full.node(f"sound-{clip.cue.replace('_', '-')}-{step}")
        validate = full.node(f"sound-{clip.cue.replace('_', '-')}-validate")
        assert generate.depends_on == ("source-lock",)
        assert validate.depends_on == (generate.node_id,)
        assert validate.port("audio").artifact_ref == f"package/sounds/{clip.cue}.mp3"
        # The brief is the whole prompt: the route is a foley engine and
        # decoration is a measured null.
        assert _prompt(generate) == clip.prompt


def test_a_sound_brief_edit_rebills_only_its_own_cue_and_mixing_rebills_nothing(
    config: StageGenConfig, package: Package
) -> None:
    def keys(graph: ObliqueSurvivalGraph) -> dict[str, str]:
        return {
            node.node_id: node.cache_key
            for node in graph.nodes
            if node.node_id.startswith(("sound-", "weather-", "music-", "fx-"))
        }

    def step(clip: SoundEffect) -> str:
        return "adopt" if clip.take is not None else "generate"

    def with_sounds(sounds: Sequence[SoundEffect]) -> dict[str, str]:
        return keys(_graph(config, replace(package, sounds=tuple(sounds)), "full"))

    baseline = keys(_graph(config, package, "full"))
    chop = next(clip for clip in package.sounds if clip.cue == "chop")
    others = [clip for clip in package.sounds if clip is not chop]
    rebriefed = with_sounds([replace(chop, prompt=chop.prompt + " Wetter wood."), *others])
    assert rebriefed[f"sound-chop-{step(chop)}"] != baseline[f"sound-chop-{step(chop)}"]
    assert rebriefed["sound-chop-validate"] != baseline["sound-chop-validate"]
    for node_id, key in baseline.items():
        if not node_id.startswith("sound-chop-"):
            assert rebriefed[node_id] == key, node_id
    # A longer clip is a different answer; a louder or detuned play is not.
    longer = with_sounds([replace(chop, duration_seconds=1.2), *others])
    assert longer[f"sound-chop-{step(chop)}"] != baseline[f"sound-chop-{step(chop)}"]
    remixed = with_sounds([replace(chop, gain=0.1, pitch_jitter=6.0, onsets=True), *others])
    assert remixed == baseline
    # Dropping a take re-bills that cue as a provider draw and nothing else.
    if chop.take is not None:
        redrawn = with_sounds([replace(chop, take=None), *others])
        assert "sound-chop-generate" in redrawn and "sound-chop-adopt" not in redrawn
        for node_id, key in baseline.items():
            if not node_id.startswith("sound-chop-"):
                assert redrawn[node_id] == key, node_id


def test_a_plate_take_adopts_through_the_gate_and_moves_nothing_else(
    config: StageGenConfig, package: Package
) -> None:
    """A biome or the litter sheet may adopt an auditioned file: 0 ops, its own identity."""

    def keys(graph: ObliqueSurvivalGraph) -> dict[str, str]:
        return {node.node_id: node.cache_key for node in graph.nodes}

    baseline = keys(_graph(config, package, "full"))
    meadow = package.biomes[1]
    with_take = replace(
        package,
        biomes=(
            package.biomes[0],
            replace(meadow, take="ground/meadow.take.png"),
            *package.biomes[2:],
        ),
        digests={**package.digests, "ground/meadow.take.png": "a" * 64},
    )
    adopted = keys(_graph(config, with_take, "full"))
    bid = _safe(meadow.biome_id)
    assert f"ground-{bid}-adopt" in adopted and f"ground-{bid}-generate" not in adopted
    assert adopted[f"ground-{bid}-canonicalize"] != baseline[f"ground-{bid}-canonicalize"]
    for node_id, key in baseline.items():
        # The lock digests every source file, the new take included; it is a
        # barrier, not a lineage edge, so nothing downstream moves with it.
        if not node_id.startswith(
            (f"ground-{bid}-", "review-ground", "package-manifest", "source-lock")
        ):
            assert adopted[node_id] == key, node_id
    # A different file is a different plate; the adopt node has no provider op.
    other = replace(with_take, digests={**with_take.digests, "ground/meadow.take.png": "b" * 64})
    assert (
        keys(_graph(config, other, "full"))[f"ground-{bid}-adopt"] != adopted[f"ground-{bid}-adopt"]
    )
    graph = _graph(config, with_take, "full")
    assert graph.node(f"ground-{bid}-adopt").operation == LOCAL_OPERATION
    assert graph.operation_counts().get("image_generation", 0) == (
        _graph(config, package, "full").operation_counts()["image_generation"]
        - (1 if meadow.take is None else 0)
    )
    # The litter sheet the same way.
    assert package.clutter is not None
    sheet = replace(
        package,
        clutter=replace(package.clutter, take="ground/clutter.take.png"),
        digests={**package.digests, "ground/clutter.take.png": "c" * 64},
    )
    sheet_keys = keys(_graph(config, sheet, "full"))
    assert "ground-clutter-adopt" in sheet_keys and "ground-clutter-generate" not in sheet_keys
    assert (
        _graph(config, sheet, "full")
        .node("ground-clutter-adopt")
        .depends_on[0]
        .startswith("templates-")
    )


def test_the_ground_blend_and_the_field_period_are_mixing_that_no_node_reads(
    config: StageGenConfig, package: Package
) -> None:
    """ground.toml [blend] and [macro] period_meters retune the picture and re-bill nothing."""

    assert package.blend, "the authored package declares a [blend] table"
    assert set(package.blend) <= set(survival_request.BLEND_KEYS)
    assert package.macro is not None and package.macro.period_meters is not None

    def keys(graph: ObliqueSurvivalGraph) -> dict[str, str]:
        return {node.node_id: node.cache_key for node in graph.nodes}

    baseline = keys(_graph(config, package, "full"))
    retuned = replace(
        package,
        blend={key: high for key, (_low, high) in survival_request.BLEND_KEYS.items()},
        macro=replace(package.macro, period_meters=7.0),
    )
    assert keys(_graph(config, retuned, "full")) == baseline
    # The islets, by contrast, change where things stand: the layout re-lays.
    islets = replace(
        package, world=replace(package.world, biomes=BiomeRules(islet_lattice=0, islet_share=0.0))
    )
    changed = keys(_graph(config, islets, "full"))
    assert changed["world-layout"] != baseline["world-layout"]
    for node_id, key in baseline.items():
        if node_id.startswith(("ground-", "prop-", "actor-", "sound-", "music-", "weather-")):
            assert changed[node_id] == key, node_id


def test_the_sounds_loader_refuses_what_no_consumer_could_play() -> None:
    good = {"cue": "chop", "prompt": "heavy axe chop into a tree trunk", "duration_seconds": 0.6}
    assert survival_request._sounds(None) == ()
    clips = survival_request._sounds({"cues": [good]})
    assert clips[0].gain == 1.0 and clips[0].pitch_jitter == 0.0 and clips[0].loop is False
    for bad, reason in (
        ({"cues": []}, "at least one"),
        ({"cues": [{**good, "cue": "jump"}]}, "must be one of"),
        ({"cues": [good, good]}, "twice"),
        ({"cues": [{**good, "duration_seconds": 0.2}]}, "duration_seconds"),
        ({"cues": [{**good, "prompt": "x" * 451}]}, "450-character"),
        ({"cues": [{**good, "loop": "yes"}]}, "loop must be a boolean"),
        ({"cues": [{**good, "gain": 4.5}]}, "gain"),
        ({"cues": [{**good, "volume": 1.0}]}, "unknown keys"),
        ({"cues": [{**good, "onsets": 1}]}, "onsets must be a boolean"),
        ({"cues": [{**good, "onsets": True, "loop": True}]}, "cannot both loop"),
        ({"cues": [{**good, "take": "sounds/chop.take.mp3"}]}, "package root"),
    ):
        with pytest.raises(SourceError, match=reason):
            survival_request._sounds(bad)


def test_the_sound_handlers_publish_a_clip_and_the_manifest_reads_it_back(
    config: StageGenConfig, package: Package, tmp_path: Path
) -> None:
    """The adopt and validate paths, exercised offline over a synthesized tone
    before any spend, and the manifest publishing the cue with its mixing."""

    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is needed to synthesize a clip")
    tone = tmp_path / "tone.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:duration=0.6",
            "-af",
            "volume=0.5",
            "-b:a",
            "128k",
            str(tone),
        ],
        check=True,
    )
    # A package whose chop adopts that tone: the take is declared by digest, so
    # swapping the bytes means swapping the declaration with them.
    root = tmp_path / "source"
    shutil.copytree(PACKAGE, root)
    (root / "sounds").mkdir(exist_ok=True)
    shutil.copy(tone, root / "sounds" / "chop.take.mp3")
    declared = load_package(PACKAGE).digests["sounds/chop.take.mp3"]
    swapped = hashlib.sha256(tone.read_bytes()).hexdigest()
    sounds_toml = root / "sounds.toml"
    sounds_toml.write_text(sounds_toml.read_text(encoding="utf-8").replace(declared, swapped))
    taken = load_package(root)
    chop = next(clip for clip in taken.sounds if clip.cue == "chop")
    assert chop.take == "sounds/chop.take.mp3" and chop.take in taken.digests

    graph = _graph(config, taken, "full")
    run_dir = tmp_path / "run"
    cache_dir = tmp_path / "cache"
    if True:
        handler = ObliqueSurvivalNodeHandler(graph, taken, run_dir=run_dir, cache_dir=cache_dir)
        adopt = graph.node("sound-chop-adopt")
        result = asyncio.run(handler._sound_adopt(adopt))
        assert result.provider_operations == 0
        assert (run_dir / "production/sounds/chop.source.mp3").read_bytes() == tone.read_bytes()
        validate = graph.node("sound-chop-validate")
        asyncio.run(handler._sound_validate(validate))
        record = json.loads((run_dir / validate.port("validation").artifact_ref).read_bytes())
        assert record["cue"] == "chop" and record["loop"] is False
        assert record["duration_seconds"] == pytest.approx(0.6, abs=0.1)
        assert (run_dir / "package/sounds/chop.mp3").read_bytes() == tone.read_bytes()
        document = _manifest(
            build_manifest(taken, run_dir, run_id="test", graph_sha256=None, scope="full")
        )
        entry = document["sounds"]["chop"]
        assert entry["audio"] == "package/sounds/chop.mp3"
        assert entry["take"] == "sounds/chop.take.mp3"
        assert entry["gain"] == chop.gain and entry["pitch_jitter"] == chop.pitch_jitter
        assert entry["onsets"] is False
        assert entry["peak_dbfs"] == record["peak_dbfs"]
        assert set(document["sounds"]) == {"chop"}
        assert document["status"]["sounds"] == "partial"
        # A short take is refused by the gate, not repaired.
        short = replace(chop, duration_seconds=3.0)
        shorter = replace(taken, sounds=tuple(short if c is chop else c for c in taken.sounds))
        with pytest.raises(ValueError, match="short of"):
            asyncio.run(
                ObliqueSurvivalNodeHandler(
                    graph, shorter, run_dir=run_dir, cache_dir=cache_dir
                )._sound_adopt(adopt)
            )
    # No sounds.toml at all is silence by design.
    (root / "sounds.toml").unlink()
    silent = load_package(root)
    assert silent.sounds == ()
    empty = _manifest(
        build_manifest(silent, tmp_path / "empty", run_id="test", graph_sha256=None, scope="full")
    )
    assert empty["sounds"] == {} and empty["status"]["sounds"] == "none"


def test_the_weather_validate_handlers_publish_the_fixture_art(
    config: StageGenConfig, package: Package, tmp_path: Path
) -> None:
    """The publish path, exercised offline over the fixture drawings before any spend.

    The music gate's bytes-versus-artifact bug lived exactly here, in code no
    offline test ran; every weather validate handler runs end to end now.
    """

    graph = _graph(config, package, "full")
    run_dir = tmp_path / "run"
    handler = ObliqueSurvivalNodeHandler(
        graph, package, run_dir=run_dir, cache_dir=tmp_path / "cache"
    )
    rain = package.weather[0]
    assert rain.drops is not None and rain.ground is not None and rain.strike is not None

    def write(ref: str, data: bytes) -> None:
        path = run_dir / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    write("production/weather/rain-drops.source.png", _fixture_drops())
    write("production/weather/rain-ground.source.png", _fixture_splash(rain.ground.kinds))
    write("production/weather/rain-strike.source.png", _fixture_strike())
    records: dict[str, dict[str, Any]] = {}
    for layer, method in (
        ("drops", handler._weather_drops_validate),
        ("ground", handler._weather_ground_validate),
        ("strike", handler._weather_strike_validate),
    ):
        node = graph.node(f"weather-rain-{layer}-validate")
        result = asyncio.run(method(node))
        assert result.provider_operations == 0
        assert (run_dir / node.port("image").artifact_ref).is_file()
        records[layer] = json.loads((run_dir / node.port("validation").artifact_ref).read_bytes())
    assert [cell["kind"] for cell in records["drops"]["cells"]] == list(rain.drops.kinds)
    assert records["drops"]["cells"][1]["x"] == 512 and records["drops"]["cells"][1]["h"] == 1024
    assert [cell["kind"] for cell in records["ground"]["cells"]] == list(rain.ground.kinds)
    assert [cell["kind"] for cell in records["strike"]["cells"]] == list(STRIKE_CELL_KINDS)
    assert all(cell["bbox"] for cell in records["strike"]["cells"])
    if shutil.which("ffmpeg") is not None:
        out = run_dir / "tone.mp3"
        subprocess.run(
            [
                *("ffmpeg", "-v", "error", "-y", "-f", "lavfi"),
                *("-i", "sine=frequency=110:duration=20"),
                *("-af", "volume=0.5", "-b:a", "128k", str(out)),
            ],
            check=True,
        )
        write("production/weather/rain-sound-ambience.source.mp3", out.read_bytes())
        node = graph.node("weather-rain-sound-ambience-validate")
        asyncio.run(handler._weather_sound_validate(node))
        record = json.loads((run_dir / node.port("validation").artifact_ref).read_bytes())
        assert record["loop"] is True and record["seam_measured"] is False
        assert record["duration_seconds"] == pytest.approx(20, abs=0.2)
    # And the manifest reads every layer back under its condition.
    document = _manifest(
        build_manifest(package, run_dir, run_id="test", graph_sha256=None, scope="full")
    )
    weather = document["weather"]["rain"]
    assert weather["drops"]["atlas"] == "package/weather/rain/drops.png"
    assert weather["drops"]["count_per_screen"] == rain.drops.count_per_screen
    assert [cell["kind"] for cell in weather["ground"]["cells"]] == list(rain.ground.kinds)
    assert weather["strike"]["height_meters"] == package.meters(rain.strike.height_units)
    assert weather["strike"]["interval_seconds"] == list(rain.strike.interval_seconds)
    if shutil.which("ffmpeg") is not None:
        assert weather["sound"]["ambience"]["loop"] is True
    assert document["status"]["weather"] == "partial"  # no thunder, no puddle decal here


def test_still_prompts_are_timeless_and_motion_prompts_are_not(package: Package) -> None:
    """A sprite that is not a motion atlas never moves, so its brief says so once."""

    clause = survival_prompts.STILL_CLAUSE
    stills = [
        survival_prompts.prop_prompt(package, package.prop("thorn_bush"), "full"),
        survival_prompts.prop_sheet_prompt(package, package.prop("pine")),
        survival_prompts.item_prompt(package, "log", "a log"),
        survival_prompts.actor_concept_prompt(package, package.player),
        survival_prompts.ground_prompt(package, package.biomes[0]),
        survival_prompts.clutter_prompt(package, _clutter(package)),
        *(survival_prompts.decal_prompt(package, decal) for decal in package.decals),
    ]
    for prompt in stills:
        assert prompt.count(clause) == 1
    rain = package.weather[0]
    assert package.water is not None
    assert rain.ground is not None and rain.strike is not None and rain.drops is not None
    moving = [
        survival_prompts.actor_motion_prompt(
            package, package.player, package.player.states[0].state
        ),
        survival_prompts.fire_strip_prompt(package, 4, 4),
        survival_prompts.dust_prompt(package),
        survival_prompts.water_prompt(package, package.water),
        survival_prompts.splash_sheet_prompt(package, rain.ground),
        survival_prompts.strike_sheet_prompt(package, rain.strike),
        survival_prompts.drops_sheet_prompt(package, rain.drops),
    ]
    for prompt in moving:
        assert clause not in prompt
    # The puddle's own brief no longer asks for the wave the clause forbids.
    puddle = next(decal for decal in package.decals if decal.decal_id == "puddle")
    assert "ripple" not in puddle.prompt


def test_the_level_override_is_mixing_the_manifest_carries_and_no_node_reads(
    config: StageGenConfig, package: Package, tmp_path: Path
) -> None:
    """ground.toml [blend] level pushes neighbours apart; the briefs and every key stay."""

    assert package.level, "the authored package levels its biomes"
    assert set(package.level) <= {biome.biome_id for biome in package.biomes}

    def keys(graph: ObliqueSurvivalGraph) -> dict[str, str]:
        return {node.node_id: node.cache_key for node in graph.nodes}

    baseline = keys(_graph(config, package, "full"))
    relevelled = replace(package, level={biome.biome_id: 0.5 for biome in package.biomes})
    assert keys(_graph(config, relevelled, "full")) == baseline
    # A biome the package does not have, or a value outside the display band, is refused.
    with pytest.raises(SourceError):
        survival_request._level(
            {"level": {"lava": 0.5}}, [biome.biome_id for biome in package.biomes]
        )
    with pytest.raises(SourceError):
        survival_request._level({"level": {"forest_floor": 0.05}}, ["forest_floor"])
    assert survival_request._level(
        {"level": {"forest_floor": 0.42}}, ["forest_floor", "dry_meadow"]
    ) == {"forest_floor": 0.42}
    assert survival_request._level({}, ["forest_floor"]) == {}


def test_the_forage_and_icon_sheets_adopt_takes_and_move_nothing_else(
    config: StageGenConfig, package: Package
) -> None:
    """The litter's twins: a take is 0 ops and its own identity; the rest of the graph holds."""

    def keys(graph: ObliqueSurvivalGraph) -> dict[str, str]:
        return {node.node_id: node.cache_key for node in graph.nodes}

    # The authored package adopts both; the test walks the other way too.
    assert package.forage is not None
    drawn = replace(
        package,
        forage=replace(package.forage, take=None),
        icons=replace(package.icons, take=None),
    )
    baseline = keys(_graph(config, drawn, "full"))
    assert "ground-forage-generate" in baseline and "items-icons-generate" in baseline
    foraged = replace(
        drawn,
        forage=replace(package.forage, take="ground/forage.take.png"),
        digests={**package.digests, "ground/forage.take.png": "f" * 64},
    )
    adopted = keys(_graph(config, foraged, "full"))
    assert "ground-forage-adopt" in adopted and "ground-forage-generate" not in adopted
    for node_id, key in baseline.items():
        if not node_id.startswith(
            ("ground-forage-", "review-ground", "package-manifest", "source-lock")
        ):
            assert adopted[node_id] == key, node_id
    iconed = replace(
        drawn,
        icons=replace(package.icons, take="items/icons.take.png"),
        digests={**package.digests, "items/icons.take.png": "i" * 64},
    )
    adopted = keys(_graph(config, iconed, "full"))
    assert "items-icons-adopt" in adopted and "items-icons-generate" not in adopted
    for node_id, key in baseline.items():
        if not node_id.startswith(
            ("items-icons-", "review-props", "package-manifest", "source-lock")
        ):
            assert adopted[node_id] == key, node_id
    # Both are lattice paintovers on the shared template node, drawn or adopted.
    graph = _graph(config, drawn, "full")
    assert graph.node("ground-forage-generate").depends_on[0] == "templates-draw-4x4-alpha"
    assert graph.node("items-icons-generate").depends_on[0] == "templates-draw-6x4-alpha"
    authored = _graph(config, package, "full")
    assert authored.node("ground-forage-adopt").operation == LOCAL_OPERATION
    assert _graph(config, iconed, "full").node("items-icons-adopt").operation == LOCAL_OPERATION


def test_the_crafting_table_and_the_item_gameplay_are_mixing_that_no_node_reads(
    config: StageGenConfig, package: Package
) -> None:
    """crafting.toml, an item's use, tool or stack, and an interaction's tool re-bill nothing."""

    def keys(graph: ObliqueSurvivalGraph) -> dict[str, str]:
        return {node.node_id: node.cache_key for node in graph.nodes}

    baseline = keys(_graph(config, package, "full"))
    recipes = tuple(replace(recipe, ingredients={"log": 9}) for recipe in package.crafting.recipes)
    retabled = replace(
        package,
        crafting=replace(package.crafting, slots=40, start={"axe": 1}, recipes=recipes),
        items=tuple(
            replace(
                item,
                stack_max=1,
                use=ItemUse(kind="consume", hunger=1.0),
                tool=None,
            )
            for item in package.items
        ),
    )
    assert keys(_graph(config, retabled, "full")) == baseline
    # The display name is painted into the icon sheet's listing, so it moves
    # the icons and nothing else: the pickups are named by id.
    renamed = replace(
        package, items=tuple(replace(item, display_name="X") for item in package.items)
    )
    moved = {k for k, v in keys(_graph(config, renamed, "full")).items() if baseline.get(k) != v}
    icons_node = "items-icons-adopt" if package.icons.take else "items-icons-generate"
    assert moved == {
        icons_node,
        "items-icons-validate",
        "review-props-sheet",
        "review-props-judge",
        "package-manifest",
    }
    pine = package.prop("pine")
    assert pine.interactions[0].tool is not None
    bare = replace(
        package,
        props=tuple(
            replace(prop, interactions=(replace(pine.interactions[0], tool=None),))
            if prop.prop_id == "pine"
            else prop
            for prop in package.props
        ),
    )
    assert keys(_graph(config, bare, "full")) == baseline
    # The icon brief IS identity: it is painted.
    briefed = replace(
        package,
        items=tuple(replace(item, icon_brief="a different glyph") for item in package.items),
    )
    moved = {k for k, v in keys(_graph(config, briefed, "full")).items() if baseline.get(k) != v}
    assert ("items-icons-adopt" if package.icons.take else "items-icons-generate") in moved
    assert not [k for k in moved if k.startswith("item-") and k.endswith("-generate")]


def test_the_manifest_carries_the_crafting_table_and_every_item_s_gameplay(
    package: Package, tmp_path: Path
) -> None:
    world = build_layout(package)
    document = _manifest(write_fixture(package, tmp_path / "run", world))
    crafting = document["crafting"]
    assert crafting["slots"] == package.crafting.slots
    assert crafting["start"] == dict(package.crafting.start)
    assert crafting["stations"]["campfire"] == {
        "prop_id": "campfire",
        "state": "lit",
        "reach_meters": 3.0,
    }
    by_id = {recipe["recipe_id"]: recipe for recipe in crafting["recipes"]}
    # A built prop names the look it is built in: the fire is built lit, the
    # bench in its baseline look when the author said nothing.
    assert by_id["campfire"]["product"] == {"prop_id": "campfire", "state": "lit"}
    assert by_id["workbench"]["product"] == {
        "prop_id": "workbench",
        "state": package.prop("workbench").baseline_state,
    }
    assert by_id["axe"]["product"] == {"item_id": "axe", "count": 1}
    assert by_id["pickaxe"]["station"] == "workbench"
    axe = document["items"]["axe"]
    assert axe["tool"] == {"verb": "chop", "uses": 25}
    assert axe["stack_max"] == 1
    assert (
        axe["icon"] == {"x": 2560 % 1024, "y": (10 // 4) * 256, "w": 256, "h": 256}
        or axe["icon"]["w"] == 256
    )
    berry = document["items"]["berry"]
    assert berry["use"]["kind"] == "consume" and berry["use"]["hunger"] == 20.0
    assert berry["display_name"] == "Berries"
    icons = document["icons"]
    assert [cell["item_id"] for cell in icons["cells"] if "item_id" in cell] == [
        item.item_id for item in package.items
    ]
    assert [cell["glyph"] for cell in icons["cells"] if "glyph" in cell] == [
        glyph.glyph for glyph in package.icons.glyphs
    ]
    assert document["props"]["pine"]["interactions"][0]["tool"] == {
        "item_id": "axe",
        "hits": 2,
        "required": True,
    }
    assert document["props"]["pine"]["interactions"][0]["from"] == ["sapling", "grown", "old"]
    assert document["props"]["thorn_bush"]["interactions"][0]["tool"] is None
    assert [i["verb"] for i in document["props"]["dead_snag"]["interactions"]] == ["chop", "gather"]
    assert "recipe" not in document["gameplay"]["campfire"]
    forage = document["ground"]["forage"]
    assert package.forage is not None
    assert forage["cell_meters"] == package.forage.cell_meters
    assert forage["cells"][0]["item_id"] == "twig" and forage["cells"][0]["count"] == 2
    assert forage["cells"][0]["regrow_seconds"] == 240.0
    assert document["status"]["ground_layers"] == "ok"


# --- seasons -------------------------------------------------------------------------


def _keys(graph: ObliqueSurvivalGraph) -> dict[str, str]:
    return {node.node_id: node.cache_key for node in graph.nodes}


def test_a_season_look_is_one_paintover_per_prop_state_off_its_summer_twin(
    config: StageGenConfig, package: Package
) -> None:
    prefix = TYPE_PREFIX
    assert package.seasons is not None
    states = sum(len(prop.states) for prop in package.props)
    assert states == 29
    for scope in ("props", "actors", "full"):
        graph = _graph(config, package, scope)
        by_type = Counter(node.type_id for node in graph.nodes)
        assert by_type[f"{prefix}/season_look.generate"] == states
        assert by_type[f"{prefix}/season_look.validate"] == states
        assert graph.node("review-seasons-judge") is not None
    minimal = _graph(config, package, "minimal")
    assert not [n for n in minimal.nodes if "-winter-" in n.node_id]
    full = _graph(config, package, "full")
    for prop in package.props:
        for state in prop.states:
            stem = f"prop-{prop.prop_id.replace('_', '-')}-{state.replace('_', '-')}"
            generate = full.node(f"{stem}-winter-generate")
            # Off the summer sprite, so the summer's digest is in the key
            # (the sheet's validate when the prop is drawn as a sheet).
            summer = (
                f"prop-{prop.prop_id.replace('_', '-')}-sheet-validate"
                if prop.sheet
                else f"{stem}-validate"
            )
            assert generate.depends_on == (summer,)
            assert "image 1" in _prompt(generate)
            validate = full.node(f"{stem}-winter-validate")
            assert (
                validate.port("image").artifact_ref
                == f"package/props/{prop.prop_id}/{state}.winter.png"
            )
    # The override replaces the clause for that one state; the clause stands elsewhere.
    bush = _prompt(full.node("prop-thorn-bush-full-winter-generate"))
    assert "bare of berries" in bush and "snow lies on every upward-facing surface" not in bush
    pine = _prompt(full.node("prop-pine-grown-winter-generate"))
    assert "snow banked thick" in pine
    twig = _prompt(full.node("prop-twig-bush-full-winter-generate"))
    assert "snow lies on every upward-facing surface" in twig
    # The seasons review pairs each look with its twin, the summer first.
    judge = _prompt(full.node("review-seasons-judge"))
    assert "pine grown, pine grown winter" in judge
    # A plate is judged with the plates, not with the sprites.
    assert "snow ice plate" not in judge and "snow ice plate" in _prompt(
        full.node("review-ground-judge")
    )
    snow = next(c for c in package.weather if c.condition_id == "snow")
    assert snow.ice is not None
    ice_step = "adopt" if snow.ice.take is not None else "generate"
    assert full.node(f"weather-snow-ice-{ice_step}").depends_on == ("source-lock",)
    assert (
        full.node("weather-snow-ice-canonicalize").port("image").artifact_ref
        == "package/weather/snow/ice.png"
    )


def test_a_look_clause_edit_moves_the_looks_alone_and_a_number_edit_moves_only_the_manifest(
    config: StageGenConfig, package: Package
) -> None:
    before = _keys(_graph(config, package, "full"))
    seasons = package.seasons
    assert seasons is not None
    look = seasons.looks[0]
    reworded = replace(
        package,
        seasons=replace(seasons, looks=(replace(look, prompt=look.prompt + " Heavier."),)),
    )
    after = _keys(_graph(config, reworded, "full"))
    moved = {node_id for node_id, key in before.items() if after[node_id] != key}
    # Only the looks that read the clause move: a state with its own
    # season_prompt override holds. Each validate moves with its generate.
    reading = set()
    for prop in package.props:
        for state in prop.states:
            if not prop.season_prompt.get("winter", {}).get(state):
                stem = f"prop-{prop.prop_id.replace('_', '-')}-{state.replace('_', '-')}-winter"
                reading |= {f"{stem}-generate", f"{stem}-validate"}
    assert 0 < len(reading) < 58
    assert (
        "prop-pine-grown-winter-generate" not in reading
        and "prop-twig-bush-full-winter-generate" in reading
    )
    # The plant sheet's look reads the clause too: one paintover, not sixteen.
    assert moved == reading | {
        "ground-plants-winter-generate",
        "ground-plants-winter-validate",
        "review-seasons-sheet",
        "review-seasons-judge",
        "package-manifest",
    }, sorted(moved ^ reading)
    winter_season = seasons.season("winter")
    colder = replace(
        package,
        seasons=replace(
            seasons,
            days_per_season=6,
            seasons=tuple(
                replace(s, cold=0.5, night_share=0.7) if s.season_id == "winter" else s
                for s in seasons.seasons
            ),
        ),
    )
    after = _keys(_graph(config, colder, "full"))
    moved = {node_id for node_id, key in before.items() if after[node_id] != key}
    # No node digests the numbers: on disk the file's digest moves the lock,
    # and the manifest is rebuilt behind it; in memory nothing moves at all.
    assert moved == set(), sorted(moved)
    assert winter_season.cold == 1.0


def test_the_plant_sheet_is_one_lattice_op_with_one_look_op_judged_on_the_ground_and_the_seasons(
    config: StageGenConfig, package: Package
) -> None:
    """The mid-scale: one sheet (or an adopted take), one winter paintover off it, the
    summer sheet judged with the ground and the pair judged with the seasons."""

    # The authored package adopts a take; the test walks the drawn road too.
    plants = package.plants
    assert plants is not None
    drawn = replace(package, plants=replace(plants, take=None))
    graph = _graph(config, drawn, "full")
    generate = graph.node("ground-plants-generate")
    assert generate.depends_on[0] == "templates-draw-4x4-alpha"
    assert generate.operation != LOCAL_OPERATION
    look = graph.node("ground-plants-winter-generate")
    assert look.depends_on == ("ground-plants-validate",)
    assert look.operation != LOCAL_OPERATION
    validate = graph.node("ground-plants-winter-validate")
    assert validate.operation == LOCAL_OPERATION
    assert validate.port("image").artifact_ref == "package/ground/plants.winter.png"
    ground_inputs = graph.node("review-ground-sheet").depends_on
    assert (
        "ground-plants-validate" in ground_inputs
        and "ground-plants-winter-validate" not in ground_inputs
    )
    seasons_inputs = graph.node("review-seasons-sheet").depends_on
    assert (
        "ground-plants-validate" in seasons_inputs
        and "ground-plants-winter-validate" in seasons_inputs
    )
    # The look waits for the props scope, like the prop looks; the summer sheet
    # is in the lowest scope with the litter it stands among.
    lowest = _graph(config, package, SCOPES[0])
    assert "ground-plants-validate" in {node.node_id for node in lowest.nodes}
    assert "ground-plants-winter-generate" not in {node.node_id for node in lowest.nodes}
    # A take adopts through the gate at 0 ops and moves the look off the take's digest alone.
    adopted = _graph(config, package, "full")
    assert adopted.node("ground-plants-adopt").operation == LOCAL_OPERATION
    keys = _keys(graph)
    for node_id, key in _keys(adopted).items():
        if not node_id.startswith(
            ("ground-plants-", "review-ground", "review-seasons", "package-manifest", "source-lock")
        ):
            assert keys[node_id] == key, node_id


def test_the_manifest_carries_the_seasons_and_every_look(package: Package, tmp_path: Path) -> None:
    world = build_layout(package)
    document = _manifest(write_fixture(package, tmp_path / "run", world))
    seasons = document["seasons"]
    assert seasons["calendar"] == {"order": ["summer", "winter"], "days_per_season": 4}
    winter = next(s for s in seasons["seasons"] if s["season_id"] == "winter")
    assert winter["snow"] == 1.0 and winter["cold"] == 1.0 and winter["look"] == "winter"
    assert winter["hidden_forage"] == ["mushroom", "moss"] and winter["barren"] == ["thorn_bush"]
    assert seasons["looks"] == ["winter"]
    assert document["status"]["seasons"] == "ok"
    grown = document["props"]["pine"]["states"]["grown"]
    look = grown["looks"]["winter"]
    assert look["image"] == "package/props/pine/grown.winter.png"
    # The state's own ruler and the same anchor; its own contact row.
    assert look["px_per_meter"] == grown["px_per_meter"]
    assert look["anchor"] == grown["anchor"]
    assert 0.0 < look["ground_contact_y_normalized"] <= 1.0
    for prop_id, block in document["props"].items():
        for state, spec in block["states"].items():
            assert "winter" in spec["looks"], (prop_id, state)
    plants = document["ground"]["plants"]
    assert plants["atlas"] == "package/ground/plants.png" and plants["cell_meters"] == 1.4
    assert len(plants["cells"]) == 16 and all(
        cell["contact"] == "growing" for cell in plants["cells"]
    )
    assert plants["looks"]["winter"]["atlas"] == "package/ground/plants.winter.png"
    assert len(plants["looks"]["winter"]["cells"]) == 16
    assert len(document["layout"]["plants"]) > 0
    ice = document["weather"]["snow"]["ice"]
    assert ice["texture"] == "package/weather/snow/ice.png" and ice["tiling"] == "mirror_repeat_2d"
    assert document["gameplay"]["warmth"]["drain_per_second"] == 0.5
    assert document["gameplay"]["campfire"]["heat_radius_meters"] == 3.5
    assert document["gameplay"]["torch"]["heat_scale"] == 0.7
    cloak = document["items"]["grass_cloak"]["use"]
    assert cloak["kind"] == "wear" and cloak["insulation"] == 0.5
    assert document["items"]["warm_stone"]["use"]["heat_seconds"] == 120.0
    assert document["items"]["cooked_berry"]["use"]["warmth"] == 10.0
    assert [cell["glyph"] for cell in document["icons"]["cells"] if "glyph" in cell] == [
        "heart",
        "bowl",
        "flame",
        "snowflake",
        "sun",
        "moon",
    ]


def test_the_interface_is_dressed_from_the_shared_triplet(
    config: StageGenConfig, package: Package
) -> None:
    """Panels and buttons are the one thing every genre draws the same way, so
    the recipe plans the game_ui triplet over its ui.toml instead of a private
    copy: the three sheets every document carries and the cursor set this one
    declares, each generated, gated and reviewed, from the props scope up,
    hanging off the source lock like every other drawn thing."""

    assert package.ui is not None
    minimal = _graph(config, package, "minimal")
    assert not [node for node in minimal.nodes if node.type_id.startswith("2d/ui/")]
    graph = _graph(config, package, "props")
    ui_nodes = {node.node_id: node for node in graph.nodes if node.type_id.startswith("2d/ui/")}
    assert set(ui_nodes) == {
        f"ui-{role}-{step}"
        for role in ("panel_frame", "button_rect", "preview_icons", "cursor_set")
        for step in ("generate", "validate", "review")
    }
    cursors = ui_nodes["ui-cursor_set-generate"]
    assert cursors.card is not None and cursors.card.prompt is not None
    assert "1 arrow (a classic pointer arrow" in cursors.card.prompt
    assert cursors.card.template_ref == "cursor_grid_3x3_1024_v1_template"
    generate = ui_nodes["ui-panel_frame-generate"]
    assert generate.depends_on == ("source-lock",)
    assert generate.operation == "image_generation"
    assert generate.card is not None and generate.card.prompt is not None
    # The package's own art direction wraps the shared task, and the plate rides
    # as reference image 1 exactly as it does on every other picture.
    assert package.style_label in generate.card.prompt
    assert "Reference image 1 is a STYLE reference only" in generate.card.prompt
    assert "Nine-slice rule" in generate.card.prompt
    assert "Static:" not in generate.card.prompt
    assert [entry.ref for entry in generate.card.authored_inputs] == ["references/style-plate.png"]
    # Every provider node in this recipe carries its attempts ledger, the
    # shared ones included; the local gate carries none.
    assert any(port.port_id == "attempts" for port in generate.ports)
    assert any(port.port_id == "attempts" for port in ui_nodes["ui-panel_frame-review"].ports)
    assert not any(port.port_id == "attempts" for port in ui_nodes["ui-panel_frame-validate"].ports)
    assert ui_nodes["ui-panel_frame-validate"].operation == LOCAL_OPERATION
    assert ui_nodes["ui-panel_frame-review"].operation == "structured_generation"
    assert ui_nodes["ui-panel_frame-review"].depends_on == ("ui-panel_frame-validate",)
    # The wrapper's words are identity: re-briefing the package's style moves the sheets.
    restyled = replace(package, style_label="a different look")
    moved = {
        node.node_id
        for node in _graph(config, restyled, "props").nodes
        if node.type_id.startswith("2d/ui/atlas.generate")
        and node.cache_key != ui_nodes[node.node_id].cache_key
    }
    assert moved == {node_id for node_id in ui_nodes if node_id.endswith("-generate")}


def test_a_package_without_an_interface_document_plans_no_interface(
    config: StageGenConfig, package: Package
) -> None:
    bare = replace(package, ui=None, ui_references={})
    graph = _graph(config, bare, "full")
    assert not [node for node in graph.nodes if node.type_id.startswith("2d/ui/")]
    assert len(graph.nodes) == len(_graph(config, package, "full").nodes) - 12
