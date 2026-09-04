"""The base handler's loop: cache first, then the method, failures onto the ledger."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

import pytest

from gnode import (
    Binding,
    BindingTable,
    CacheDisposition,
    GraphBuilder,
    ModelRef,
    Node,
    NodeExecutionContext,
    NodeExecutionError,
    NodeExecutionResult,
    NodePolicy,
    NodeType,
    Port,
    ViewArchetype,
)
from stage_gen.recipes.graph_document import RecipeGraph
from stage_gen.recipes.node_handler import NodeMethod, RecipeNodeHandler


class _Ops(StrEnum):
    LOCAL = "local"
    IMAGE_GENERATION = "image_generation"


class _Graph(RecipeGraph):
    OPERATIONS = _Ops

    schema_version: Literal[1]
    kind: Literal["substrate-test-graph-v1"]
    recipe: Literal["substrate-test"]


LOCAL = NodeType(
    type_id="test/local.write",
    title="Local write",
    archetype=ViewArchetype.SOURCE,
    operation="local",
    contract_version="test-local-v1",
)
PAID = NodeType(
    type_id="test/image.generate",
    title="Paid image",
    archetype=ViewArchetype.SOURCE,
    operation="image_generation",
    contract_version="test-image-v1",
    policy=NodePolicy(max_attempts=6),
)
PROFILE = BindingTable(
    [
        Binding(
            operation="image_generation",
            model=ModelRef(model="test-image", provider="openai"),
            features=frozenset(),
            resource_id="openai-image",
            estimated_duration_seconds=1.0,
            estimated_cost_low_usd=0.0,
            estimated_cost_high_usd=0.0,
            verified_on="2026-09-04",
        )
    ]
)


class _Exhausted(Exception):
    attempts = 3


class _Handler(RecipeNodeHandler):
    def __init__(self, graph: _Graph, *, run_dir: Path, cache_dir: Path) -> None:
        self.calls: list[str] = []
        self.failed: list[str] = []
        super().__init__(
            graph, run_dir=run_dir, cache_dir=cache_dir, namespace="test-v1", record_kind="test"
        )

    def _handlers(self) -> tuple[tuple[NodeType, NodeMethod], ...]:
        return ((LOCAL, self._local), (PAID, self._paid))

    async def _local(self, node: Node) -> NodeExecutionResult:
        self.calls.append(node.node_id)
        if node.params.get("fail") == "yes":
            raise KeyError("missing")
        (self._run_dir / "local.json").write_bytes(b"{}\n")
        return self._result(node)

    async def _paid(self, node: Node) -> NodeExecutionResult:
        self.calls.append(node.node_id)
        raise _Exhausted("three invalid candidates")

    def _failed(self, node: Node, error: NodeExecutionError) -> None:
        self.failed.append(f"{node.node_id}:{error.provider_operations}")


def _graph(*, fail_local: bool = False) -> _Graph:
    builder = GraphBuilder(profile=PROFILE)
    local = builder.add(
        LOCAL,
        "local",
        domain="test",
        description="a local node",
        params={"fail": "yes" if fail_local else "no"},
        ports=(Port(port_id="out", artifact_ref="local.json", kind="test-record-v1"),),
    )
    builder.add(
        PAID,
        "paid",
        domain="test",
        description="a paid node",
        depends_on=(local.node_id,),
        ports=(Port(port_id="image", artifact_ref="paid.png", kind="test-image-v1"),),
    )
    return _Graph.seal(resources=builder.resources(), nodes=builder.nodes, terminal_node_id="paid")


def _context(graph: _Graph) -> NodeExecutionContext:
    return NodeExecutionContext(
        invocation_id="inv-1", graph_sha256=graph.graph_sha256, dependency_results={}
    )


@pytest.mark.asyncio
async def test_a_local_result_lists_exactly_the_ports_that_carry_bytes(tmp_path: Path) -> None:
    graph = _graph()
    handler = _Handler(graph, run_dir=tmp_path / "run", cache_dir=tmp_path / "cache")
    (tmp_path / "run").mkdir()
    result = await handler(graph.node("local"), _context(graph))
    assert result.cache is CacheDisposition.MISS
    assert result.provider_operations == 0
    assert [artifact.artifact_ref for artifact in result.artifacts] == ["local.json"]
    assert handler.invocation_id == "inv-1"
    assert handler.registered_type_ids == {LOCAL.type_id, PAID.type_id}


@pytest.mark.asyncio
async def test_a_local_failure_spends_nothing_and_names_its_type(tmp_path: Path) -> None:
    graph = _graph(fail_local=True)
    handler = _Handler(graph, run_dir=tmp_path / "run", cache_dir=tmp_path / "cache")
    (tmp_path / "run").mkdir()
    with pytest.raises(NodeExecutionError, match="KeyError: 'missing'") as raised:
        await handler(graph.node("local"), _context(graph))
    assert raised.value.provider_operations == 0
    assert raised.value.attempts == 1
    assert handler.failed == ["local:0"]


@pytest.mark.asyncio
async def test_a_paid_failure_carries_the_retry_owners_attempts_as_spend(tmp_path: Path) -> None:
    graph = _graph()
    handler = _Handler(graph, run_dir=tmp_path / "run", cache_dir=tmp_path / "cache")
    (tmp_path / "run").mkdir()
    with pytest.raises(NodeExecutionError, match="_Exhausted: three invalid") as raised:
        await handler(graph.node("paid"), _context(graph))
    assert raised.value.attempts == 3
    assert raised.value.provider_operations == 3
    assert handler.failed == ["paid:3"]
    assert handler.restore(graph.node("paid"), _context(graph)) is None
