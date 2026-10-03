"""The hand-authored wire fixtures in web/ui/contracts are documents the product would write.

The TypeScript parsers in ``web/ui`` read these fixtures in their Bun tests. Here the same
files are held to the Python side of each contract, so neither half can drift unseen: the run
view against the SDK's ``PipelineRunView`` (gnode's ``RunView``, schema 3), the example and its
ledger against ``stage_gen.examples``, and the catalog against the structure
``scripts/catalog.py`` actually writes, built here over a store holding the fixture's
game example.
"""

# test-owner: web
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from gnode import RunView
from stage_gen.examples import (
    ENTRY_FILE,
    EXAMPLE_FILE,
    FIGURES_FILE,
    FiguresLedger,
    GameExampleEntry,
    WorkflowExample,
)
from stage_gen.pipeline import PipelineRunView
from stage_gen.workflows._catalog import CATALOG_KIND, build
from stage_gen.workflows._registry import ExampleEntry, WorkflowManifest

CONTRACTS = Path(__file__).resolve().parents[2] / "web" / "ui" / "contracts"


def _fixture(name: str) -> Any:
    return json.loads((CONTRACTS / f"{name}.fixture.json").read_text(encoding="utf-8"))


def _keys(document: dict[str, Any]) -> set[str]:
    return set(document)


@pytest.fixture(scope="module")
def exported(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """A real catalog, built over a store that holds the fixture's game example."""
    fixture = _fixture("catalog")
    game = fixture["game_examples"][0]
    directory = tmp_path_factory.mktemp("store") / game["owner"] / game["id"]
    directory.mkdir(parents=True)
    for name, document in (
        (EXAMPLE_FILE, game["example"]),
        (FIGURES_FILE, game["figures"]),
        (ENTRY_FILE, game["entry"]),
    ):
        (directory / name).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    catalog, _problems = build(examples_dir=directory.parent.parent, allow_missing_examples=True)
    return catalog


def test_run_view_fixture_is_an_sdk_run_view() -> None:
    raw = (CONTRACTS / "run-view.fixture.json").read_bytes()
    view = PipelineRunView.model_validate_json(raw)
    assert isinstance(view, RunView)
    assert view.schema_version == 3
    assert view.kind.endswith("-execution-view-v1")
    # Every edge and card reference names a node the document declares.
    declared = {node.node_id for node in view.nodes}
    for node in view.nodes:
        assert set(node.depends_on) <= declared
        if node.card is not None:
            assert {ref.node_id for ref in node.card.reference_inputs} <= declared
    assert view.model_dump(mode="json") == json.loads(raw)


def test_example_fixture_is_a_workflow_example() -> None:
    document = _fixture("example")
    example = WorkflowExample.model_validate(document)
    assert example.model_dump(mode="json") == document
    assert example.run_type_ids() == {"swatch.brief", "swatch.draw", "swatch.check"}
    # The catalog fixture shows the same example its workflow pins.
    catalog = _fixture("catalog")
    assert catalog["workflows"][0]["examples"][0]["example"] == document


def test_catalog_fixture_has_the_shape_the_export_writes(exported: dict[str, Any]) -> None:
    fixture = _fixture("catalog")
    assert fixture["kind"] == exported["kind"] == CATALOG_KIND
    assert fixture["schema_version"] == exported["schema_version"]
    assert _keys(fixture) == _keys(exported)

    real_workflow = exported["workflows"][0]
    real_plan = next(w["sample_plan"] for w in exported["workflows"] if w["sample_plan"])
    real_step = real_workflow["steps"][0]
    real_example = next(e for w in exported["workflows"] for e in w["examples"])
    for workflow in fixture["workflows"]:
        assert _keys(workflow) == _keys(real_workflow)
        manifest = WorkflowManifest.model_validate(workflow["manifest"])
        assert manifest.model_dump(mode="json", by_alias=True) == workflow["manifest"]
        assert manifest.id == workflow["id"]
        assert isinstance(workflow["identity"]["graph_kinds"], list)
        for step in workflow["steps"]:
            assert _keys(step) == _keys(real_step)
            for member in step["members"]:
                assert _keys(member) == _keys(real_step["members"][0])
        plan = workflow["sample_plan"]
        assert _keys(plan) == _keys(real_plan)
        for node in plan["nodes"]:
            assert _keys(node) == _keys(real_plan["nodes"][0])
        for example in workflow["examples"]:
            assert _keys(example) == _keys(real_example)
            entry = {key: example[key] for key in ExampleEntry.model_fields}
            assert ExampleEntry.model_validate(entry).model_dump(mode="json") == entry
            WorkflowExample.model_validate(example["example"])
            ledger = FiguresLedger.model_validate(example["figures"])
            assert ledger.model_dump(mode="json", exclude_none=True) == example["figures"]


def test_catalog_fixture_game_examples_and_cards_match_the_export(
    exported: dict[str, Any],
) -> None:
    fixture = _fixture("catalog")
    [real_game] = exported["game_examples"]
    [game] = fixture["game_examples"]
    assert _keys(game) == _keys(real_game)
    entry = GameExampleEntry.model_validate(game["entry"])
    assert entry.model_dump(mode="json") == game["entry"]
    assert real_game["entry"] == game["entry"]
    assert real_game["example"] == WorkflowExample.model_validate(game["example"]).model_dump(
        mode="json"
    )
    FiguresLedger.model_validate(game["figures"])

    real_cards = exported["cards"]
    game_card = next(card for card in real_cards if card["workflow"] is None)
    workflow_card = next(card for card in real_cards if card["workflow"] is not None)
    for card in fixture["cards"]:
        assert _keys(card) == _keys(workflow_card)
    # The export makes the game's card from its entry exactly as the fixture shows it.
    assert game_card == next(card for card in fixture["cards"] if card["workflow"] is None)
    for names in ("model_names", "provider_names"):
        assert all(isinstance(value, str) for value in fixture[names].values())
