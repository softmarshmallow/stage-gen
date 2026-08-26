from __future__ import annotations

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

    assert len(graph.nodes) == 192
    assert graph.operation_counts() == {
        "local": 92,
        "image_generation": 82,
        "structured_generation": 15,
        "music_generation": 3,
    }
    assert graph.terminal_node_id == "manifest-assemble"
    assert graph.node("package-resolve").depends_on == ()
    assert graph.node("manifest-assemble").operation is OperationKind.LOCAL

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


def test_projection_applies_the_adapter_owned_image_start_rate() -> None:
    graph = _graph()
    projection = project_execution(graph)

    assert projection.duration_ms == 295_650
    assert projection.operation_counts == graph.operation_counts()
    assert projection.estimated_cost_low_usd == 3.655
    assert projection.estimated_cost_high_usd == 20.0
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
