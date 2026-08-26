from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from stage_gen.config import StageGenConfig
from stage_gen.orchestration.game_package import resolve_game_package
from stage_gen.recipes.scrolling_preview.package_graph import (
    build_package_execution_graph,
    package_graph_profile,
)

REPOSITORY_ROOT = Path(__file__).parents[2]
PIPELINE_DOCUMENT = REPOSITORY_ROOT / "docs/spec/game/generation-pipeline.md"
GRAPH_CONTRACT_START = "<!-- pipeline-graph-contract:start -->"
GRAPH_CONTRACT_END = "<!-- pipeline-graph-contract:end -->"
GRAPH_CONTRACT_PATTERN = re.compile(
    rf"{re.escape(GRAPH_CONTRACT_START)}\s*```json\s*(.*?)\s*```\s*"
    rf"{re.escape(GRAPH_CONTRACT_END)}",
    re.DOTALL,
)


def _graph_contract() -> dict[str, Any]:
    source = PIPELINE_DOCUMENT.read_text(encoding="utf-8")
    assert source.count(GRAPH_CONTRACT_START) == 1
    assert source.count(GRAPH_CONTRACT_END) == 1
    matches = GRAPH_CONTRACT_PATTERN.findall(source)
    assert len(matches) == 1
    value = json.loads(matches[0])
    assert isinstance(value, dict)
    return value


def test_generation_pipeline_document_tracks_the_executable_stage_graphs() -> None:
    contract = _graph_contract()
    fixture_ref = contract["fixture_ref"]
    assert isinstance(fixture_ref, str)
    package = resolve_game_package(REPOSITORY_ROOT / fixture_ref)
    graph = build_package_execution_graph(
        package,
        profile=package_graph_profile(StageGenConfig()),
    )

    assert contract == {
        "kind": "prepared-game-execution-graph-contract-v1",
        "fixture_ref": "library/games/bellweather",
        "graph_schema_version": graph.schema_version,
        "topology_sha256": graph.topology_sha256,
        "node_count": len(graph.nodes),
        "terminal_node_id": graph.terminal_node_id,
        "operation_counts": graph.operation_counts(),
        "resources": [resource.model_dump(mode="json") for resource in graph.resources],
    }


def test_generation_pipeline_document_is_discoverable_from_game_authorities() -> None:
    required_link = "generation-pipeline.md"
    same_directory_authority = (
        REPOSITORY_ROOT / "docs/spec/game/authored-contract-schema.md"
    ).read_text(encoding="utf-8")
    docs_index = (REPOSITORY_ROOT / "docs/README.md").read_text(encoding="utf-8")
    game_contract = (REPOSITORY_ROOT / "docs/game-contract.md").read_text(encoding="utf-8")
    game_package = (REPOSITORY_ROOT / "docs/game-package.md").read_text(encoding="utf-8")

    assert required_link in same_directory_authority
    assert "spec/game/generation-pipeline.md" in docs_index
    assert "spec/game/generation-pipeline.md" in game_contract
    assert "spec/game/generation-pipeline.md" in game_package
