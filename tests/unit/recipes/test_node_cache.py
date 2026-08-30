"""The recipe cache tier: lineage honesty, barrier exemption, and confinement.

The don't-re-bill design leans entirely on this file: a barrier edge orders
execution without contributing identity, so its artifacts must not bind the
cache record — otherwise editing anything upstream of the barrier re-bills
every provider node, which is exactly what the barrier promises not to do.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from gnode import (
    CacheDisposition,
    Graph,
    Node,
    NodeArtifact,
    NodeExecutionContext,
    NodeExecutionResult,
    Resource,
    RetryOwner,
    build_node_cache_key,
    seal_graph,
)
from stage_gen.recipes.node_cache import NodeArtifactCache


def _node(
    node_id: str,
    *,
    depends_on: tuple[str, ...] = (),
    barrier_only: tuple[str, ...] = (),
    cache_key_seed: str = "seed",
) -> Node:
    return Node(
        node_id=node_id,
        type_id="test/step.run",
        domain="test",
        description=node_id,
        depends_on=depends_on,
        barrier_only=barrier_only,
        operation="local",
        resource_id="local",
        retry_owner=RetryOwner.NONE,
        max_attempts=1,
        cache_key=build_node_cache_key(
            node_id=node_id,
            type_id="test/step.run",
            operation="local",
            provider=None,
            model=None,
            input_sha256=(),
            dependency_cache_keys=(),
            contract_version=cache_key_seed,
        ),
        estimated_duration_seconds=0.0,
        estimated_cost_low_usd=0.0,
        estimated_cost_high_usd=0.0,
    )


def _graph() -> Graph:
    root = _node("root")
    barrier = _node("barrier")
    return seal_graph(
        Graph,
        resources=[Resource(resource_id="local", rate_limit_owner="none")],
        nodes=[
            root,
            barrier,
            _node("leaf", depends_on=("root", "barrier"), barrier_only=("barrier",)),
        ],
        terminal_node_id="leaf",
        schema_version=1,
        kind="test-graph-v1",
    )


def _result_for(run_dir: Path, ref: str, data: bytes) -> NodeExecutionResult:
    (run_dir / ref).parent.mkdir(parents=True, exist_ok=True)
    (run_dir / ref).write_bytes(data)
    return NodeExecutionResult(
        cache=CacheDisposition.MISS,
        attempts=1,
        provider_operations=0,
        artifacts=(
            NodeArtifact(
                artifact_ref=ref, sha256=hashlib.sha256(data).hexdigest(), bytes=len(data)
            ),
        ),
    )


def _context(graph: Graph, **artifact_digests: str) -> NodeExecutionContext:
    results = {
        dependency: NodeExecutionResult(
            cache=CacheDisposition.MISS,
            attempts=1,
            provider_operations=0,
            artifacts=(NodeArtifact(artifact_ref=f"{dependency}.json", sha256=digest, bytes=1),),
        )
        for dependency, digest in artifact_digests.items()
    }
    return NodeExecutionContext(
        invocation_id="test", graph_sha256=graph.graph_sha256, dependency_results=results
    )


def test_a_barrier_dependency_never_binds_the_cache_record(tmp_path: Path) -> None:
    graph = _graph()
    cache = NodeArtifactCache(
        graph,
        run_dir=tmp_path / "run",
        cache_dir=tmp_path / "cache",
        namespace="test-v1",
        record_kind="test-cache-v1",
    )
    leaf = graph.node("leaf")
    first = _context(graph, root="a" * 64, barrier="b" * 64)
    cache.write(leaf, first, _result_for(tmp_path / "run", "leaf.bin", b"payload"))

    # The barrier's artifacts changed — a package edit upstream of the barrier.
    barrier_changed = _context(graph, root="a" * 64, barrier="c" * 64)
    hit = cache.read(leaf, barrier_changed)
    assert hit is not None and hit.cache is CacheDisposition.HIT

    # A lineage dependency changed — that IS identity; the record must not serve.
    lineage_changed = _context(graph, root="d" * 64, barrier="b" * 64)
    assert cache.read(leaf, lineage_changed) is None


def test_a_crafted_record_cannot_write_outside_the_run_directory(tmp_path: Path) -> None:
    graph = _graph()
    run_dir = tmp_path / "run"
    cache = NodeArtifactCache(
        graph,
        run_dir=run_dir,
        cache_dir=tmp_path / "cache",
        namespace="test-v1",
        record_kind="test-cache-v1",
    )
    leaf = graph.node("leaf")
    context = _context(graph, root="a" * 64, barrier="b" * 64)
    cache.write(leaf, context, _result_for(run_dir, "leaf.bin", b"payload"))

    record_path = (
        tmp_path / "cache" / "test-v1" / leaf.cache_key[:2] / leaf.cache_key / "record.json"
    )
    corrupted = record_path.read_text(encoding="utf-8").replace("leaf.bin", "../escape.bin")
    record_path.write_text(corrupted, encoding="utf-8")

    assert cache.read(leaf, context) is None
    assert not (tmp_path / "escape.bin").exists()


@pytest.mark.parametrize("ref", ["leaf.bin"])
def test_a_valid_record_restores_bytes_and_reports_a_free_hit(tmp_path: Path, ref: str) -> None:
    graph = _graph()
    run_dir = tmp_path / "run"
    cache = NodeArtifactCache(
        graph,
        run_dir=run_dir,
        cache_dir=tmp_path / "cache",
        namespace="test-v1",
        record_kind="test-cache-v1",
    )
    leaf = graph.node("leaf")
    context = _context(graph, root="a" * 64, barrier="b" * 64)
    cache.write(leaf, context, _result_for(run_dir, ref, b"payload"))
    (run_dir / ref).unlink()

    restored = cache.read(leaf, context)
    assert restored is not None
    assert restored.cache is CacheDisposition.HIT
    assert restored.provider_operations == 0
    assert restored.known_cost_usd == 0.0
    assert (run_dir / ref).read_bytes() == b"payload"
