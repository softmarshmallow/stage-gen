"""Each workflow's contract.md carries the checked shape of its offline sample plan.

The blocks live in src/stage_gen/workflows/looping_parallax/contract.md,
src/stage_gen/workflows/movie_sprite/contract.md and
src/stage_gen/workflows/universe/contract.md (two blocks, one per phase). The universe
vocabulary they implement is ratified in docs/spec/universe/taxonomy-v0.md, which links the
universe contract. `scripts/write_workflow_contracts.py --write` regenerates every block.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.graph_contracts import document_contract, render
from scripts.write_workflow_contracts import (
    BLOCKS,
    UNIVERSE_ADMITTED_REF,
    ContractBlock,
    build,
    contract_of,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_KEYS = {
    "topology_sha256",
    "node_count",
    "terminal_node_id",
    "operation_counts",
    "resources",
    "type_ids",
}


@pytest.mark.parametrize("block", BLOCKS, ids=lambda block: block.name)
def test_contract_block_matches_the_workflows_offline_plan(block: ContractBlock) -> None:
    built = build(block)
    assert set(built) == CONTRACT_KEYS
    assert document_contract(block.document(), label=block.label) == built


@pytest.mark.parametrize("block", BLOCKS, ids=lambda block: block.name)
def test_contract_block_is_rendered_canonically(block: ContractBlock) -> None:
    # A hand-edited block that happens to parse equal must still fail, or the document and the
    # regenerated output would differ byte for byte.
    source = block.document().read_text(encoding="utf-8")
    assert render(document_contract(block.document(), label=block.label), label=block.label) in (
        source
    )


def test_every_sample_plan_workflow_has_a_block() -> None:
    from stage_gen.workflows._registry import discover, load_code

    # A workflow without a sample plan says why (portrait-motion), or cannot be planned outside
    # its own launcher (character-3d); every other workflow has a block.
    planned = {
        workflow.id
        for workflow in discover()
        if load_code(workflow.id).no_sample_plan is None
        and load_code(workflow.id).plan_refusal is None
    }
    assert {block.workflow_id for block in BLOCKS} == planned


def test_a_block_carries_no_path_or_machine_fact() -> None:
    for block in BLOCKS:
        text = block.document().read_text(encoding="utf-8")
        contract = document_contract(block.document(), label=block.label)
        assert set(contract) == CONTRACT_KEYS
        assert "fixture_ref" not in contract and "kind" not in contract
        assert re.search(r"/(?:tmp|private|Users|home)/", str(contract)) is None, block.name
        assert contract["type_ids"] == sorted(set(contract["type_ids"]))
        assert "> **Checked by:** `tests/contract/test_workflow_contract_docs.py`" in text


def test_build_refuses_a_plan_that_differs_between_scratch_folders() -> None:
    from gnode import Graph

    graphs: list[Graph] = []
    original = BLOCKS[0]

    def plan_once(scratch: Path, repo: Path) -> Graph:
        graph = original.plan(scratch, repo)
        if graphs:
            graph = graph.model_copy(update={"terminal_node_id": "moved"})
        graphs.append(graph)
        return graph

    with pytest.raises(ValueError, match="plans differently"):
        build(ContractBlock(original.workflow_id, original.label, plan_once))
    assert contract_of(graphs[0])["terminal_node_id"] != "moved"


def test_universe_gallery_block_is_planned_from_the_committed_admission() -> None:
    # Universe is the one workflow that seals two graphs, because the size of its gallery is a
    # result of its semantic phase. The committed admission stands in for that paid run.
    assert (REPOSITORY_ROOT / UNIVERSE_ADMITTED_REF).is_file()
    semantic = document_contract(
        REPOSITORY_ROOT / "src/stage_gen/workflows/universe/contract.md", label="semantic"
    )
    gallery = document_contract(
        REPOSITORY_ROOT / "src/stage_gen/workflows/universe/contract.md", label="gallery"
    )
    assert semantic["terminal_node_id"] == "universe-admit"
    assert gallery["terminal_node_id"] == "gallery-close"
    assert gallery["operation_counts"]["image_generation"] > 0


def test_universe_contract_is_discoverable_from_its_taxonomy_and_the_docs_index() -> None:
    docs_index = (REPOSITORY_ROOT / "docs/README.md").read_text(encoding="utf-8")
    taxonomy = (REPOSITORY_ROOT / "docs/spec/universe/taxonomy-v0.md").read_text(encoding="utf-8")
    assert "src/stage_gen/workflows/universe/contract.md" in taxonomy
    assert "stage_gen/workflows/universe/contract.md" in docs_index
