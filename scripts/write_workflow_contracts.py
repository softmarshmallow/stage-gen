#!/usr/bin/env python3
"""Check or rewrite the graph-contract blocks in each workflow's contract.md.

Each block is the shape of a workflow's offline sample plan, ``CODE.sample_plan`` in its
``workflow.py``: topology digest, node count, terminal node, operation counts, resources and
the type ids it places. Universe carries a second block for its gallery phase, planned from
the committed admitted-universe fixture, because a gallery plan needs an admitted world that
only a paid semantic run makes. Game graph contracts have their own writer under
``godot/tools``; shared block formatting belongs to ``scripts.graph_contracts``.

Every block is built twice, each time in a fresh scratch folder, and a block whose two builds
differ is refused, so a block holds only what any machine plans the same way.

    uv run python scripts/write_workflow_contracts.py --check
    uv run python scripts/write_workflow_contracts.py --write
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scripts.graph_contracts import document_contract, write_contract

if TYPE_CHECKING:
    from gnode import Graph

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_ADMITTED_REF = "tests/contract/fixtures/universe/lantern_ferry.admitted-universe.json"


@dataclass(frozen=True, slots=True)
class ContractBlock:
    """One block: the workflow whose contract.md holds it, its label, and how it plans."""

    workflow_id: str
    label: str | None
    plan: Callable[[Path, Path], Graph]

    @property
    def name(self) -> str:
        return self.workflow_id if self.label is None else f"{self.workflow_id}:{self.label}"

    def document(self, repo: Path = REPOSITORY_ROOT) -> Path:
        return repo / "src/stage_gen/workflows" / self.workflow_id.replace("-", "_") / "contract.md"


def _sample_plan(workflow_id: str) -> Callable[[Path, Path], Graph]:
    def planned(scratch: Path, repo: Path) -> Graph:
        del repo
        from stage_gen.workflows._registry import load_code

        graph = load_code(workflow_id).sample_plan(scratch)
        if graph is None:
            raise ValueError(f"{workflow_id} has no offline sample plan")
        return graph

    return planned


def _universe_gallery(scratch: Path, repo: Path) -> Graph:
    """The gallery fan-out over lantern_ferry and its committed admitted-universe fixture."""
    del scratch
    from stage_gen.config import load_config
    from stage_gen.workflows.universe.universe_graph import (
        build_universe_gallery_graph,
        universe_graph_profile,
    )
    from stage_gen.workflows.universe.universe_request import (
        admitted_universe_from_document,
        read_universe_document,
        resolve_sample_ledger,
        resolve_universe_source,
    )
    from stage_gen.workflows.universe.workflow import SAMPLE_INPUT

    config = load_config(env={})
    source = resolve_universe_source(read_universe_document(SAMPLE_INPUT), root=SAMPLE_INPUT)
    admitted = admitted_universe_from_document(
        repo / UNIVERSE_ADMITTED_REF, poster_sha256=source.poster_sha256
    )
    samples = resolve_sample_ledger(
        universe_id=admitted.universe_id, entity_ids=admitted.entity_ids()
    )
    return build_universe_gallery_graph(
        source,
        admitted,
        samples=samples,
        profile=universe_graph_profile(config, images=True),
        config=config,
    )


BLOCKS: tuple[ContractBlock, ...] = (
    ContractBlock("looping-parallax", None, _sample_plan("looping-parallax")),
    ContractBlock("movie-sprite", None, _sample_plan("movie-sprite")),
    ContractBlock("storefront", None, _sample_plan("storefront")),
    ContractBlock("universe", "semantic", _sample_plan("universe")),
    ContractBlock("universe", "gallery", _universe_gallery),
)


def contract_of(graph: Graph) -> dict[str, Any]:
    """The machine-independent shape of one planned graph."""
    return {
        "topology_sha256": graph.topology_sha256,
        "node_count": len(graph.nodes),
        "terminal_node_id": graph.terminal_node_id,
        "operation_counts": graph.operation_counts(),
        "resources": [resource.model_dump(mode="json") for resource in graph.resources],
        "type_ids": sorted({node.type_id for node in graph.nodes}),
    }


def build(block: ContractBlock, repo: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    """Plan the block twice, each in a fresh scratch folder, and refuse when they differ."""
    built: list[dict[str, Any]] = []
    for _ in range(2):
        with TemporaryDirectory(prefix="workflow-contract-") as directory:
            built.append(contract_of(block.plan(Path(directory), repo)))
    first, second = built
    if first != second:
        differing = sorted(key for key in first if first[key] != second.get(key))
        raise ValueError(f"{block.name} plans differently in two scratch folders: {differing}")
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="report stale blocks and exit 1 when any is stale (the default)",
    )
    mode.add_argument(
        "--write", action="store_true", help="rewrite stale blocks instead of reporting them"
    )
    args = parser.parse_args(argv)

    status = 0
    for block in BLOCKS:
        built = build(block)
        document = block.document()
        current = document_contract(document, label=block.label)
        if built == current:
            print(
                f"{block.name} graph contract is current: {built['node_count']} nodes, "
                f"{built['topology_sha256']}"
            )
            continue
        differing = sorted(
            key for key in set(built) | set(current) if built.get(key) != current.get(key)
        )
        if not args.write:
            print(f"{block.name} graph contract is STALE. Differing keys: " + ", ".join(differing))
            status = 1
            continue
        write_contract(built, document, label=block.label)
        print(
            f"{block.name} graph contract rewritten. Differing keys were: " + ", ".join(differing)
        )
    if status:
        print("Run with --write to regenerate.")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
