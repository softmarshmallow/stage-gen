from __future__ import annotations

import json
import re
import tomllib
from decimal import Decimal
from pathlib import Path
from typing import Any

from stage_gen.orchestration.game_package import validate_game_package
from stage_gen.recipes.scrolling_preview.recipe import (
    parse_scrolling_preview_input,
    scrolling_preview_recipe,
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


def _project_graph(input_value: object) -> dict[str, Any]:
    parsed = parse_scrolling_preview_input(input_value)
    return {
        "nodes": [
            {
                "id": stage.name,
                "wave": format(Decimal(str(stage.wave)).normalize(), "f"),
                "depends_on": sorted(stage.depends_on),
            }
            for stage in scrolling_preview_recipe.stages_for(parsed)
        ]
    }


def _canonical_game_input(selector_ref: str) -> object:
    report = validate_game_package(REPOSITORY_ROOT, selector_ref=selector_ref)
    assert report["valid"] is True
    assert report["recipe"] == "scrolling-preview"
    request_ref = report["request_ref"]
    assert isinstance(request_ref, str)
    return tomllib.loads((REPOSITORY_ROOT / request_ref).read_text(encoding="utf-8"))


def test_generation_pipeline_document_tracks_the_executable_stage_graphs() -> None:
    contract = _graph_contract()

    assert contract["kind"] == "scrolling-preview-stage-graphs-v1"
    assert contract["selector_ref"] == "library/games/main.toml"
    assert contract["graphs"] == {
        "minimal": _project_graph({"prompt": "graph contract"}),
        "canonical_game": _project_graph(_canonical_game_input(contract["selector_ref"])),
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
