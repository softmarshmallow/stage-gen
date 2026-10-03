"""Each workflow's contract.md carries the checked shape of its offline sample plan.

The blocks live in src/stage_gen/workflows/looping_parallax/contract.md,
src/stage_gen/workflows/movie_sprite/contract.md,
src/stage_gen/workflows/portrait_motion/contract.md and
src/stage_gen/workflows/universe/contract.md. The universe
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
#: A workflow file's plan has no terminal node or resource table; it declares its outputs.
WORKFLOW_FILE_KEYS = {
    "graph_kind",
    "topology_sha256",
    "node_count",
    "operation_counts",
    "outputs",
    "type_ids",
}


def _keys(contract: dict[str, object]) -> set[str]:
    return WORKFLOW_FILE_KEYS if "graph_kind" in contract else CONTRACT_KEYS


@pytest.mark.parametrize("block", BLOCKS, ids=lambda block: block.name)
def test_contract_block_matches_the_workflows_offline_plan(block: ContractBlock) -> None:
    built = build(block)
    assert set(built) == _keys(built)
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

    # A workflow without a sample plan says why: character-3d cannot be planned outside its
    # own launcher. Every other workflow has a block.
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
        assert set(contract) == _keys(contract)
        assert "fixture_ref" not in contract and "kind" not in contract
        assert re.search(r"/(?:tmp|private|Users|home)/", str(contract)) is None, block.name
        assert contract["type_ids"] == sorted(set(contract["type_ids"]))
        assert "> **Checked by:** `tests/contract/test_workflow_contract_docs.py`" in text


def test_build_refuses_a_plan_that_differs_between_scratch_folders() -> None:
    import dataclasses

    from stage_gen.workflows._gnode import SamplePlan

    plans: list[SamplePlan] = []
    original = next(block for block in BLOCKS if block.workflow_id == "universe")

    def plan_once(scratch: Path, repo: Path) -> SamplePlan:
        planned = original.plan(scratch, repo)
        assert isinstance(planned, SamplePlan)
        if plans:
            planned = dataclasses.replace(planned, topology_sha256="moved")
        plans.append(planned)
        return planned

    with pytest.raises(ValueError, match="plans differently"):
        build(ContractBlock(original.workflow_id, original.label, plan_once))
    assert contract_of(plans[0])["topology_sha256"] != "moved"


def test_universe_block_holds_the_world_phase_the_plan_can_count() -> None:
    # The gallery's size is a result of the world phase, so it is priced when its list exists.
    block = document_contract(REPOSITORY_ROOT / "src/stage_gen/workflows/universe/contract.md")
    assert "universe/world/propose" in block["type_ids"]
    assert "universe/entity/draw" not in block["type_ids"]


def test_universe_contract_is_discoverable_from_its_taxonomy_and_the_docs_index() -> None:
    docs_index = (REPOSITORY_ROOT / "docs/README.md").read_text(encoding="utf-8")
    taxonomy = (REPOSITORY_ROOT / "docs/spec/universe/taxonomy-v0.md").read_text(encoding="utf-8")
    assert "src/stage_gen/workflows/universe/contract.md" in taxonomy
    assert "stage_gen/workflows/universe/contract.md" in docs_index
