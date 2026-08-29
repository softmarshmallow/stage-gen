from __future__ import annotations

import hashlib
import shutil
from dataclasses import replace
from itertools import pairwise
from pathlib import Path

import pytest

from stage_gen.components.game_map import PreparedGameMap, PreparedMapClimbable
from stage_gen.config import StageGenConfig
from stage_gen.media import LOOP_METHODS, LoopConstruction
from stage_gen.orchestration.execution_graph import (
    ExecutionGraph,
    OperationKind,
    project_execution,
)
from stage_gen.orchestration.game_package import ResolvedGamePackage, resolve_game_package
from stage_gen.recipes.scrolling_preview import layer_contract
from stage_gen.recipes.scrolling_preview.package_graph import (
    build_package_execution_graph,
    package_graph_profile,
)
from stage_gen.resources import (
    terrain_atlas_template_path,
    terrain_atlas_topology_reference_path,
)

REPOSITORY_ROOT = Path(__file__).parents[4]
BELLWEATHER = REPOSITORY_ROOT / "library/games/bellweather"
#: The only Bellweather map that declares a climbable atlas.
CROWNCRAG = "crowncrag-road"


def _graph() -> ExecutionGraph:
    package = resolve_game_package(BELLWEATHER)
    return build_package_execution_graph(
        package,
        profile=package_graph_profile(StageGenConfig()),
    )


def test_bellweather_package_expands_to_the_complete_asset_level_graph() -> None:
    graph = _graph()

    # Eight loop nodes, one per layer. Sunpetal declares `generated_bridge` so its four are image
    # operations; Crowncrag declares `mirror_repeat` so its four are local. The image count is a
    # worst case: each loop node admits the generated raster first and only constructs when that
    # fails, so a layer the model already returned as a clean repeat unit spends nothing.
    # Two motion-rebase nodes per actor with published motion: the player. The first judges
    # every atlas against the baseline on a locally composited plate; the second applies that
    # reading and judges the residual on a plate composed with it. Two structured operations,
    # no image generation - both plates are assembled locally from shipped bytes.
    assert len(graph.nodes) == 217
    assert graph.operation_counts() == {
        "local": 102,
        "image_generation": 92,
        "structured_generation": 20,
        "music_generation": 3,
    }
    assert graph.terminal_node_id == "manifest-assemble"
    assert graph.node("package-resolve").depends_on == ()
    assert graph.node("manifest-assemble").operation is OperationKind.LOCAL

    generated = graph.node("player-wayfarer-state-run-generate")
    validated = graph.node("player-wayfarer-state-run-validate")
    assert generated.outputs == ("content/players/wayfarer/states/run.source.png",)
    assert validated.outputs == (
        "content/players/wayfarer/states/run.png",
        "content/players/wayfarer/states/run.validation.json",
    )
    crouch_generated = graph.node("player-wayfarer-state-crouch-generate")
    assert crouch_generated.depends_on == ("player-wayfarer-concept-generate",)
    assert crouch_generated.outputs == ("content/players/wayfarer/states/crouch.source.png",)
    assert graph.node("player-wayfarer-state-crouch-validate").outputs == (
        "content/players/wayfarer/states/crouch.png",
        "content/players/wayfarer/states/crouch.validation.json",
    )
    # Climb is one movement with one strip per climbable role. The map declares whether a
    # climbable is a ladder or a rope, so each role owes its own rear-facing strip and neither is
    # derived from the other.
    for role_state in ("climb_ladder", "climb_rope"):
        climb_generated = graph.node(f"player-wayfarer-state-{role_state}-generate")
        assert climb_generated.depends_on == ("player-wayfarer-concept-generate",)
        assert climb_generated.outputs == (
            f"content/players/wayfarer/states/{role_state}.source.png",
        )
    assert graph.node("ui-inventory-panel-generate").depends_on == ("package-resolve",)
    assert graph.node("ui-inventory-panel-review").depends_on == ("ui-inventory-panel-validate",)
    assert graph.node("map-crowncrag-road-climbable-validate").depends_on == (
        "map-crowncrag-road-climbable-generate",
    )
    assert graph.node("map-sunpetal-crossing-portal-validate").outputs == (
        "maps/sunpetal-crossing/portal.png",
        "maps/sunpetal-crossing/portal.validation.json",
    )
    template_digest = hashlib.sha256(terrain_atlas_template_path().read_bytes()).hexdigest()
    topology_reference_digest = hashlib.sha256(
        terrain_atlas_topology_reference_path().read_bytes()
    ).hexdigest()
    assert template_digest in graph.node("map-sunpetal-crossing-ground-generate").input_sha256
    assert (
        topology_reference_digest
        in graph.node("map-sunpetal-crossing-ground-generate").input_sha256
    )
    assert template_digest in graph.node("map-sunpetal-crossing-ground-validate").input_sha256

    outputs = [output for node in graph.nodes for output in node.outputs]
    assert len(outputs) == len(set(outputs))
    assert all(node.cache_key for node in graph.nodes)
    assert all(node.input_sha256 for node in graph.nodes)


def test_authored_anchor_reruns_only_the_motion_whose_registration_changed() -> None:
    """Changing where one motion registers must not re-repack every other strip."""

    package = resolve_game_package(BELLWEATHER)
    player = package.player.players[0]
    flipped = [
        motion.model_copy(update={"anchor": "bottom"}) if motion.state == "climb_rope" else motion
        for motion in player.motions
    ]
    changed_package = replace(
        package,
        package_sha256="f" * 64,
        canonical_game_sha256="e" * 64,
        closure_sha256="d" * 64,
        player=package.player.model_copy(
            update={"players": [player.model_copy(update={"motions": flipped})]}
        ),
    )
    profile = package_graph_profile(StageGenConfig())
    original = build_package_execution_graph(package, profile=profile)
    changed = build_package_execution_graph(changed_package, profile=profile)

    def validate_keys(graph: ExecutionGraph) -> dict[str, str]:
        return {
            node.node_id: node.cache_key
            for node in graph.nodes
            if node.node_id.endswith("-validate") and "-state-" in node.node_id
        }

    before, after = validate_keys(original), validate_keys(changed)
    differing = {key for key in before if before[key] != after[key]}
    assert differing == {"player-wayfarer-state-climb_rope-validate"}

    # Registration is consumed after generation, so flipping it must not re-bill a provider image.
    generation = {
        node.node_id: node.cache_key
        for node in original.nodes
        if node.operation is OperationKind.IMAGE_GENERATION
    }
    assert generation == {
        node.node_id: node.cache_key
        for node in changed.nodes
        if node.operation is OperationKind.IMAGE_GENERATION
    }


def test_package_graph_encodes_leaf_dependencies_without_coarse_wave_barriers() -> None:
    graph = _graph()

    player_state = graph.node("player-wayfarer-state-run-generate")
    assert player_state.depends_on == ("player-wayfarer-concept-generate",)
    mob_state = graph.node("mob-petal_puff-state-attack-generate")
    assert mob_state.depends_on == ("mob-petal_puff-concept-generate",)
    composite = graph.node("map-sunpetal-crossing-composite")
    assert set(composite.depends_on) == {
        "map-sunpetal-crossing-layer-clear_sky-validate",
        "map-sunpetal-crossing-layer-clouds_and_far_valley-validate",
        "map-sunpetal-crossing-layer-sunpetal_village-validate",
        "map-sunpetal-crossing-layer-near_garden_frame-validate",
        "map-sunpetal-crossing-ground-validate",
        "map-sunpetal-crossing-terrain-generate",
    }
    assert "map-crowncrag-road-review" not in composite.depends_on
    assert set(graph.node("map-crowncrag-road-review").depends_on) == {
        "map-crowncrag-road-composite",
        "map-crowncrag-road-climbable-validate",
        "map-crowncrag-road-portal-validate",
    }


def test_playback_only_change_does_not_invalidate_provider_cache_identity() -> None:
    package = resolve_game_package(BELLWEATHER)
    player = package.player.players[0]
    idle = player.motions[0]
    changed_idle = idle.model_copy(
        update={
            "playback_mode": "loop",
            "canonical_frame_indices": [0, 1, 2, 3],
            "frames_per_second": 4,
        }
    )
    changed_player = player.model_copy(update={"motions": [changed_idle, *player.motions[1:]]})
    changed_catalog = package.player.model_copy(update={"players": [changed_player]})
    changed_package = replace(
        package,
        package_sha256="f" * 64,
        canonical_game_sha256="e" * 64,
        closure_sha256="d" * 64,
        player=changed_catalog,
    )
    profile = package_graph_profile(StageGenConfig())
    original = build_package_execution_graph(package, profile=profile)
    changed = build_package_execution_graph(changed_package, profile=profile)

    provider_operations = {
        OperationKind.IMAGE_GENERATION,
        OperationKind.STRUCTURED_GENERATION,
        OperationKind.MUSIC_GENERATION,
    }
    assert {
        node.node_id: node.cache_key
        for node in original.nodes
        if node.operation in provider_operations
    } == {
        node.node_id: node.cache_key
        for node in changed.nodes
        if node.operation in provider_operations
    }
    assert original.node("package-resolve").cache_key != changed.node("package-resolve").cache_key
    assert (
        original.node("manifest-assemble").cache_key != changed.node("manifest-assemble").cache_key
    )


def test_runtime_presentation_changes_only_invalidate_runtime_integration() -> None:
    package = resolve_game_package(BELLWEATHER)
    contact_shadows = package.game.presentation.contact_shadows.model_copy(update={"opacity": 0.24})
    changed_game = package.game.model_copy(
        update={
            "presentation": package.game.presentation.model_copy(
                update={"contact_shadows": contact_shadows}
            )
        }
    )
    first_map = package.maps[0]
    changed_layer = first_map.layers[2].model_copy(
        update={
            "presentation": first_map.layers[2].presentation.model_copy(
                update={"detail_blur_screen_pixels": 0.9}
            )
        }
    )
    changed_map = first_map.model_copy(
        update={"layers": [*first_map.layers[:2], changed_layer, *first_map.layers[3:]]}
    )
    changed_package = replace(
        package,
        package_sha256="f" * 64,
        canonical_game_sha256="e" * 64,
        closure_sha256="d" * 64,
        game=changed_game,
        maps=(changed_map, *package.maps[1:]),
    )
    profile = package_graph_profile(StageGenConfig())
    original = build_package_execution_graph(package, profile=profile)
    changed = build_package_execution_graph(changed_package, profile=profile)

    assert original.node("map-sunpetal-crossing-layer-sunpetal_village-generate").cache_key == (
        changed.node("map-sunpetal-crossing-layer-sunpetal_village-generate").cache_key
    )
    assert original.node("map-sunpetal-crossing-layer-sunpetal_village-validate").cache_key == (
        changed.node("map-sunpetal-crossing-layer-sunpetal_village-validate").cache_key
    )
    assert (
        original.node("map-sunpetal-crossing-composite").cache_key
        == changed.node("map-sunpetal-crossing-composite").cache_key
    )
    assert {
        node.node_id: node.cache_key
        for node in original.nodes
        if node.operation is not OperationKind.LOCAL
    } == {
        node.node_id: node.cache_key
        for node in changed.nodes
        if node.operation is not OperationKind.LOCAL
    }
    assert (
        original.node("manifest-assemble").cache_key != changed.node("manifest-assemble").cache_key
    )


def _crowncrag_climbable(package: ResolvedGamePackage) -> PreparedMapClimbable:
    crowncrag = next(entry for entry in package.maps if entry.map_id == CROWNCRAG)
    assert crowncrag.climbable is not None
    return crowncrag.climbable


def _crowncrag_climbable_package(**update: object) -> ResolvedGamePackage:
    """Rebuild Bellweather with only the Crowncrag climbable block edited.

    The package sha values move with it because any authored edit changes them; leaving them
    fixed would let a node look unchanged for the wrong reason.
    """

    package = resolve_game_package(BELLWEATHER)
    changed_climbable = _crowncrag_climbable(package).model_copy(update=update)
    maps = tuple(
        entry.model_copy(update={"climbable": changed_climbable})
        if entry.map_id == CROWNCRAG
        else entry
        for entry in package.maps
    )
    return replace(
        package,
        package_sha256="f" * 64,
        canonical_game_sha256="e" * 64,
        closure_sha256="d" * 64,
        maps=maps,
    )


def _crowncrag_terrain_package(**update: object) -> ResolvedGamePackage:
    """Rebuild Bellweather with only the Crowncrag terrain REQUEST edited."""

    package = resolve_game_package(BELLWEATHER)
    crowncrag = next(entry for entry in package.maps if entry.map_id == CROWNCRAG)
    changed = crowncrag.terrain.model_copy(update=update)
    maps = tuple(
        entry.model_copy(update={"terrain": changed}) if entry.map_id == CROWNCRAG else entry
        for entry in package.maps
    )
    return replace(
        package,
        package_sha256="f" * 64,
        canonical_game_sha256="e" * 64,
        closure_sha256="d" * 64,
        maps=maps,
    )


def test_reshaping_terrain_does_not_re_bill_any_artwork() -> None:
    """Artwork cannot depend on terrain shape, because the map no longer carries any.

    This used to need an explicit exclusion list. Now the material atlas and the climbable atlas
    simply have nothing geometric to read, so asking for a different level cannot redraw them.
    """

    profile = package_graph_profile(StageGenConfig())
    original = build_package_execution_graph(resolve_game_package(BELLWEATHER), profile=profile)
    changed = build_package_execution_graph(
        _crowncrag_terrain_package(brief="A single flat street with nothing on it at all."),
        profile=profile,
    )

    paid = {
        node.node_id: node.cache_key
        for node in original.nodes
        if node.operation is OperationKind.IMAGE_GENERATION
    }
    assert paid == {
        node.node_id: node.cache_key
        for node in changed.nodes
        if node.operation is OperationKind.IMAGE_GENERATION
    }
    # The terrain node itself must react, or nothing would ever recompose the level.
    generate = f"map-{CROWNCRAG}-terrain-generate"
    assert original.node(generate).cache_key != changed.node(generate).cache_key


def test_a_changed_terrain_request_reaches_every_node_that_consumes_geometry() -> None:
    """Geometry is generated, so nothing that reads it may be served a stale artifact."""

    profile = package_graph_profile(StageGenConfig())
    original = build_package_execution_graph(resolve_game_package(BELLWEATHER), profile=profile)
    changed = build_package_execution_graph(
        _crowncrag_terrain_package(brief="A single flat street with nothing on it at all."),
        profile=profile,
    )

    for node_id in (
        f"map-{CROWNCRAG}-terrain-generate",
        f"map-{CROWNCRAG}-composite",
        f"map-{CROWNCRAG}-review",
        "package-resolve",
        "manifest-assemble",
    ):
        assert original.node(node_id).cache_key != changed.node(node_id).cache_key, node_id


def test_declared_climbable_variants_and_prompts_remain_atlas_generation_identity() -> None:
    """The declared roster sets the cell count and the request, so it must stay in the key."""

    package = resolve_game_package(BELLWEATHER)
    climbable = _crowncrag_climbable(package)
    assert climbable.ladders and climbable.ropes
    profile = package_graph_profile(StageGenConfig())
    original = build_package_execution_graph(package, profile=profile)
    generate = f"map-{CROWNCRAG}-climbable-generate"

    reworded_ladders = [
        climbable.ladders[0].model_copy(
            update={"prompt": "A plain untreated pine climbing ladder with flat rungs."}
        ),
        *climbable.ladders[1:],
    ]
    reworded = build_package_execution_graph(
        _crowncrag_climbable_package(ladders=reworded_ladders), profile=profile
    )
    assert original.node(generate).cache_key != reworded.node(generate).cache_key

    # Dropping a variant changes how many cells the sheet is asked for, so the atlas cannot reuse
    # art drawn for the larger roster.
    smaller = build_package_execution_graph(
        _crowncrag_climbable_package(ropes=[]),
        profile=profile,
    )
    assert original.node(generate).cache_key != smaller.node(generate).cache_key


def test_projection_applies_the_adapter_owned_image_start_rate() -> None:
    graph = _graph()
    projection = project_execution(graph)

    assert projection.duration_ms == 311_050
    assert projection.operation_counts == graph.operation_counts()
    assert projection.estimated_cost_low_usd == 4.08
    assert projection.estimated_cost_high_usd == 22.4
    assert projection.critical_path[0] == "package-resolve"
    assert projection.critical_path[-1] == "manifest-assemble"

    image_starts = sorted(
        span.started_offset_ms
        for span in projection.spans
        if span.operation is OperationKind.IMAGE_GENERATION
    )
    assert all(current - previous >= 400 for previous, current in pairwise(image_starts))


def test_remote_provider_resources_have_no_scheduler_concurrency_ceiling() -> None:
    resources = {resource.resource_id: resource for resource in _graph().resources}

    assert resources["local"].max_in_flight == 32
    assert resources["openai-image"].max_in_flight is None
    assert resources["openrouter-structured"].max_in_flight is None
    assert resources["openrouter-music"].max_in_flight is None
    assert resources["openai-image"].requests_per_minute == 150


def _with_layer_construction(
    package: ResolvedGamePackage,
    map_id: str,
    layer_id: str,
    construction: LoopConstruction,
) -> ResolvedGamePackage:
    """Override one layer's loop construction, leaving every other authored value alone."""

    maps: list[PreparedGameMap] = []
    for game_map in package.maps:
        if game_map.map_id != map_id:
            maps.append(game_map)
            continue
        layers = [
            layer.model_copy(update={"loop_construction": construction})
            if layer.layer_id == layer_id
            else layer
            for layer in game_map.layers
        ]
        maps.append(game_map.model_copy(update={"layers": layers}))
    return replace(
        package,
        maps=tuple(maps),
        package_sha256="a" * 64,
        canonical_game_sha256="b" * 64,
        closure_sha256="c" * 64,
    )


def test_loop_node_kind_follows_the_construction_not_its_name() -> None:
    """A deterministic construction must be a local node and a generative one an image node.

    This is the property that used to be a string comparison against a single construction name,
    which silently classified every construction added after it as local.
    """

    package = resolve_game_package(BELLWEATHER)
    profile = package_graph_profile(StageGenConfig())
    # Crowncrag authors `mirror_repeat`, so its loop nodes are local until a layer says otherwise.
    crowncrag = next(item for item in package.maps if item.map_id == CROWNCRAG)
    layer_id = crowncrag.layers[0].layer_id
    node_id = f"map-{CROWNCRAG}-layer-{layer_id}-loop"

    baseline = build_package_execution_graph(package, profile=profile)
    assert baseline.node(node_id).operation is OperationKind.LOCAL

    for construction in ("generated_bridge", "seam_repaint", "fold_repaint"):
        overridden = build_package_execution_graph(
            _with_layer_construction(package, CROWNCRAG, layer_id, construction),
            profile=profile,
        )
        assert overridden.node(node_id).operation is OperationKind.IMAGE_GENERATION, construction


def test_a_layer_construction_override_reruns_only_that_layer_loop() -> None:
    """Selection is per-layer, so it must not disturb any sibling's identity."""

    package = resolve_game_package(BELLWEATHER)
    profile = package_graph_profile(StageGenConfig())
    crowncrag = next(item for item in package.maps if item.map_id == CROWNCRAG)
    changed_layer, *other_layers = crowncrag.layers

    original = build_package_execution_graph(package, profile=profile)
    changed = build_package_execution_graph(
        _with_layer_construction(package, CROWNCRAG, changed_layer.layer_id, "seam_repaint"),
        profile=profile,
    )

    changed_node = f"map-{CROWNCRAG}-layer-{changed_layer.layer_id}-loop"
    assert original.node(changed_node).cache_key != changed.node(changed_node).cache_key
    # The layer's own artwork is generated before the loop is constructed, so choosing a different
    # construction must never re-bill the image.
    generate = f"map-{CROWNCRAG}-layer-{changed_layer.layer_id}-generate"
    assert original.node(generate).cache_key == changed.node(generate).cache_key
    for sibling in other_layers:
        sibling_node = f"map-{CROWNCRAG}-layer-{sibling.layer_id}-loop"
        assert original.node(sibling_node).cache_key == changed.node(sibling_node).cache_key


def test_revising_one_construction_leaves_the_others_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cache identity is scoped to the construction a layer selected.

    The digest used to carry every construction's version at once, so revising any one of them
    re-ran the loop node for every layer in every map whichever construction it actually used.
    """

    package = resolve_game_package(BELLWEATHER)
    profile = package_graph_profile(StageGenConfig())
    crowncrag = next(item for item in package.maps if item.map_id == CROWNCRAG)
    # Crowncrag is authored `mirror_repeat`; point one layer at a generative construction so the
    # map holds both kinds at once and the isolation claim is actually exercised.
    mixed = _with_layer_construction(
        package, CROWNCRAG, crowncrag.layers[0].layer_id, "seam_repaint"
    )
    original = build_package_execution_graph(mixed, profile=profile)

    # The registry is immutable by design, so revise a copy and patch the name the recipe's
    # identity function actually reads.
    revised = dict(LOOP_METHODS)
    revised["generated_bridge"] = replace(
        LOOP_METHODS["generated_bridge"], version="generated-bridge-v99"
    )
    monkeypatch.setattr(layer_contract, "LOOP_METHODS", revised)
    changed = build_package_execution_graph(mixed, profile=profile)

    # Crowncrag selects `mirror_repeat` with one layer on `seam_repaint`; neither reads the
    # bridge's version, so revising it must leave every one of its loop nodes alone.
    for layer in crowncrag.layers:
        node_id = f"map-{CROWNCRAG}-layer-{layer.layer_id}-loop"
        assert original.node(node_id).cache_key == changed.node(node_id).cache_key, node_id

    # Asserting the other half matters as much: an identity that isolated everything would also
    # fail to invalidate. Derive the expectation from each layer's resolved construction rather
    # than from the map's default, because a layer may override it.
    sunpetal = next(item for item in mixed.maps if item.map_id != CROWNCRAG)
    bridged = [
        layer
        for layer in sunpetal.layers
        if (layer.loop_construction or sunpetal.continuity.loop_construction) == "generated_bridge"
    ]
    assert bridged, "the fixture must retain at least one bridged layer to prove invalidation"
    for layer in bridged:
        node_id = f"map-{sunpetal.map_id}-layer-{layer.layer_id}-loop"
        assert original.node(node_id).cache_key != changed.node(node_id).cache_key, node_id
    for layer in sunpetal.layers:
        if layer in bridged:
            continue
        node_id = f"map-{sunpetal.map_id}-layer-{layer.layer_id}-loop"
        assert original.node(node_id).cache_key == changed.node(node_id).cache_key, node_id


def test_changing_the_fallback_does_not_re_bill_any_layer_image() -> None:
    """The fallback is consumed after generation, so it must not reach a generation digest."""

    package = resolve_game_package(BELLWEATHER)
    profile = package_graph_profile(StageGenConfig())
    maps = tuple(
        game_map.model_copy(
            update={
                "continuity": game_map.continuity.model_copy(
                    update={"loop_fallback": "mirror_repeat"}
                )
            }
        )
        for game_map in package.maps
    )
    changed_package = replace(
        package,
        maps=maps,
        package_sha256="c" * 64,
        canonical_game_sha256="d" * 64,
        closure_sha256="e" * 64,
    )
    original = build_package_execution_graph(package, profile=profile)
    changed = build_package_execution_graph(changed_package, profile=profile)

    for game_map in package.maps:
        for layer in game_map.layers:
            node_id = f"map-{game_map.map_id}-layer-{layer.layer_id}-generate"
            assert original.node(node_id).cache_key == changed.node(node_id).cache_key, node_id


def _package_copy(tmp_path: Path) -> Path:
    target = tmp_path / "bellweather"
    shutil.copytree(BELLWEATHER, target)
    return target


@pytest.mark.parametrize(
    ("member", "before", "after"),
    [
        ("content/player.toml", "frames_per_second = 6", "frames_per_second = 8"),
        ("content/player.toml", 'playback_mode = "loop"', 'playback_mode = "once"'),
        ("soundtrack.toml", "revision = 2", "revision = 3"),
    ],
)
def test_editing_an_authored_member_reaches_the_nodes_that_capture_and_assemble_it(
    tmp_path: Path, member: str, before: str, after: str
) -> None:
    """Package identity must be derived from member bytes, not from a digest authored beside them.

    The root contract used to carry a digest of every member, so the canonical projection covered
    the whole closure by transitivity. Nothing authored covers it now, so both nodes that read the
    captured package have to key on the closure itself. Each edit below lands verbatim in
    `manifest.json`, which is what makes a stale `manifest-assemble` key a wrong artifact rather
    than a wasted rebuild.
    """

    package_root = _package_copy(tmp_path)
    source = package_root / member
    text = source.read_text(encoding="utf-8")
    assert before in text
    profile = package_graph_profile(StageGenConfig())
    original = build_package_execution_graph(resolve_game_package(package_root), profile=profile)

    source.write_text(text.replace(before, after, 1), encoding="utf-8")
    changed = build_package_execution_graph(resolve_game_package(package_root), profile=profile)

    for node_id in ("package-resolve", "manifest-assemble"):
        assert original.node(node_id).cache_key != changed.node(node_id).cache_key, node_id
    assert {
        node.node_id: node.cache_key
        for node in original.nodes
        if node.operation is not OperationKind.LOCAL
    } == {
        node.node_id: node.cache_key
        for node in changed.nodes
        if node.operation is not OperationKind.LOCAL
    }
