from __future__ import annotations

import hashlib
from dataclasses import replace
from itertools import pairwise
from pathlib import Path

from stage_gen.config import StageGenConfig
from stage_gen.orchestration.execution_graph import (
    ExecutionGraph,
    OperationKind,
    project_execution,
)
from stage_gen.orchestration.game_package import resolve_game_package
from stage_gen.recipes.scrolling_preview.package_graph import (
    build_package_execution_graph,
    package_graph_profile,
)
from stage_gen.resources import terrain_atlas_template_path

REPOSITORY_ROOT = Path(__file__).parents[4]
BELLWEATHER = REPOSITORY_ROOT / "library/games/bellweather"


def _graph() -> ExecutionGraph:
    package = resolve_game_package(BELLWEATHER)
    return build_package_execution_graph(
        package,
        profile=package_graph_profile(StageGenConfig()),
    )


def test_bellweather_package_expands_to_the_complete_asset_level_graph() -> None:
    graph = _graph()

    assert len(graph.nodes) == 203
    assert graph.operation_counts() == {
        "local": 97,
        "image_generation": 87,
        "structured_generation": 16,
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
    assert graph.node("ui-inventory-panel-generate").depends_on == ("package-resolve",)
    assert graph.node("ui-inventory-panel-review").depends_on == ("ui-inventory-panel-validate",)
    assert graph.node("map-crowncrag-road-ladder-validate").depends_on == (
        "map-crowncrag-road-ladder-generate",
    )
    assert graph.node("map-sunpetal-crossing-portal-validate").outputs == (
        "maps/sunpetal-crossing/portal.png",
        "maps/sunpetal-crossing/portal.validation.json",
    )
    template_digest = hashlib.sha256(terrain_atlas_template_path().read_bytes()).hexdigest()
    assert template_digest not in graph.node("map-sunpetal-crossing-ground-generate").input_sha256
    assert template_digest in graph.node("map-sunpetal-crossing-ground-validate").input_sha256

    outputs = [output for node in graph.nodes for output in node.outputs]
    assert len(outputs) == len(set(outputs))
    assert all(node.cache_key for node in graph.nodes)
    assert all(node.input_sha256 for node in graph.nodes)


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
    }
    assert "map-crowncrag-road-review" not in composite.depends_on
    assert set(graph.node("map-crowncrag-road-review").depends_on) == {
        "map-crowncrag-road-composite",
        "map-crowncrag-road-ladder-validate",
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


def test_projection_applies_the_adapter_owned_image_start_rate() -> None:
    graph = _graph()
    projection = project_execution(graph)

    assert projection.duration_ms == 297_250
    assert projection.operation_counts == graph.operation_counts()
    assert projection.estimated_cost_low_usd == 3.86
    assert projection.estimated_cost_high_usd == 21.08
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
