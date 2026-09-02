"""The recipe cache tier: lineage honesty, barrier exemption, and confinement.

The don't-re-bill design leans entirely on this file: a barrier edge orders
execution without contributing identity, so its artifacts must not bind the
cache record — otherwise editing anything upstream of the barrier re-bills
every provider node, which is exactly what the barrier promises not to do.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

import stage_gen.recipes.node_cache as node_cache_module
from gnode import (
    CacheDisposition,
    Graph,
    Node,
    NodeArtifact,
    NodeExecutionContext,
    NodeExecutionResult,
    Port,
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
    ports: tuple[Port, ...] | None = None,
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
        ports=ports
        if ports is not None
        else (
            Port(
                port_id="output",
                artifact_ref=f"{node_id}.bin",
                kind="test-payload-v1",
            ),
        ),
    )


def _graph(
    *,
    root_ports: tuple[Port, ...] | None = None,
    leaf_ports: tuple[Port, ...] | None = None,
) -> Graph:
    root = _node("root", ports=root_ports)
    barrier = _node("barrier")
    return seal_graph(
        Graph,
        resources=[Resource(resource_id="local", rate_limit_owner="none")],
        nodes=[
            root,
            barrier,
            _node(
                "leaf",
                depends_on=("root", "barrier"),
                barrier_only=("barrier",),
                ports=leaf_ports,
            ),
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


def _result_for_bundle(
    run_dir: Path, artifacts: tuple[tuple[str, bytes], ...]
) -> NodeExecutionResult:
    node_artifacts: list[NodeArtifact] = []
    for ref, data in artifacts:
        (run_dir / ref).parent.mkdir(parents=True, exist_ok=True)
        (run_dir / ref).write_bytes(data)
        node_artifacts.append(
            NodeArtifact(
                artifact_ref=ref,
                sha256=hashlib.sha256(data).hexdigest(),
                bytes=len(data),
            )
        )
    return NodeExecutionResult(
        cache=CacheDisposition.MISS,
        attempts=1,
        provider_operations=1,
        artifacts=tuple(node_artifacts),
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


def _record_path(tmp_path: Path, node: Node) -> Path:
    return tmp_path / "cache" / "test-v1" / node.cache_key[:2] / node.cache_key / "record.json"


def _read_record(tmp_path: Path, node: Node) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(_record_path(tmp_path, node).read_text(encoding="utf-8")),
    )


def _write_record(tmp_path: Path, node: Node, record: dict[str, Any]) -> None:
    _record_path(tmp_path, node).write_text(json.dumps(record, sort_keys=True), encoding="utf-8")


def _provider_ports() -> tuple[Port, ...]:
    return (
        Port(
            port_id="image",
            artifact_ref="provider/image.png",
            kind="test-image-v1",
            sidecar_ref="provider/image.png.meta.json",
        ),
        Port(
            port_id="attempts",
            artifact_ref="attempts/leaf.json",
            kind="attempt-ledger-v2",
        ),
    )


def _dependency_ports() -> tuple[Port, ...]:
    return (
        Port(
            port_id="primary",
            artifact_ref="root.bin",
            kind="test-payload-v1",
            sidecar_ref="root.bin.meta.json",
        ),
        Port(
            port_id="validation",
            artifact_ref="validation/root.json",
            kind="test-validation-v1",
        ),
        Port(
            port_id="attempts",
            artifact_ref="attempts/root.json",
            kind="attempt-ledger-v2",
        ),
    )


def _dependency_result(
    *,
    primary_sha256: str,
    sidecar_sha256: str,
    validation_sha256: str = "c" * 64,
    attempts_sha256: str = "d" * 64,
) -> NodeExecutionResult:
    refs_and_digests = (
        ("root.bin", primary_sha256),
        ("root.bin.meta.json", sidecar_sha256),
        ("validation/root.json", validation_sha256),
        ("attempts/root.json", attempts_sha256),
    )
    return NodeExecutionResult(
        cache=CacheDisposition.MISS,
        attempts=1,
        provider_operations=0,
        artifacts=tuple(
            NodeArtifact(artifact_ref=ref, sha256=digest, bytes=1)
            for ref, digest in refs_and_digests
        ),
    )


def _context_with_dependency_bundle(
    graph: Graph, dependency_result: NodeExecutionResult
) -> NodeExecutionContext:
    return NodeExecutionContext(
        invocation_id="test",
        graph_sha256=graph.graph_sha256,
        dependency_results={
            "root": dependency_result,
            "barrier": NodeExecutionResult(
                cache=CacheDisposition.MISS,
                attempts=1,
                provider_operations=0,
                artifacts=(
                    NodeArtifact(
                        artifact_ref="barrier.json",
                        sha256="b" * 64,
                        bytes=1,
                    ),
                ),
            ),
        },
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


def test_dependency_provenance_sidecar_changes_do_not_invalidate_a_cache_hit(
    tmp_path: Path,
) -> None:
    graph = _graph(root_ports=_dependency_ports())
    run_dir = tmp_path / "run"
    cache = NodeArtifactCache(
        graph,
        run_dir=run_dir,
        cache_dir=tmp_path / "cache",
        namespace="test-v1",
        record_kind="test-cache-v1",
    )
    leaf = graph.node("leaf")
    first = _context_with_dependency_bundle(
        graph,
        _dependency_result(primary_sha256="a" * 64, sidecar_sha256="1" * 64),
    )
    sidecar_changed = _context_with_dependency_bundle(
        graph,
        _dependency_result(primary_sha256="a" * 64, sidecar_sha256="2" * 64),
    )
    cache.write(leaf, first, _result_for(run_dir, "leaf.bin", b"payload"))
    (run_dir / "leaf.bin").unlink()

    assert cache.lineage(leaf, first) == cache.lineage(leaf, sidecar_changed)
    assert cache.lineage(leaf, first)[0]["artifact_sha256"] == [
        "a" * 64,
        "c" * 64,
        "d" * 64,
    ]
    restored = cache.read(leaf, sidecar_changed)
    assert restored is not None and restored.cache is CacheDisposition.HIT
    assert (run_dir / "leaf.bin").read_bytes() == b"payload"


def test_dependency_primary_artifact_changes_still_invalidate_the_cache(
    tmp_path: Path,
) -> None:
    graph = _graph(root_ports=_dependency_ports())
    run_dir = tmp_path / "run"
    cache = NodeArtifactCache(
        graph,
        run_dir=run_dir,
        cache_dir=tmp_path / "cache",
        namespace="test-v1",
        record_kind="test-cache-v1",
    )
    leaf = graph.node("leaf")
    first = _context_with_dependency_bundle(
        graph,
        _dependency_result(primary_sha256="a" * 64, sidecar_sha256="1" * 64),
    )
    primary_changed = _context_with_dependency_bundle(
        graph,
        _dependency_result(primary_sha256="e" * 64, sidecar_sha256="1" * 64),
    )
    cache.write(leaf, first, _result_for(run_dir, "leaf.bin", b"payload"))

    assert cache.lineage(leaf, first) != cache.lineage(leaf, primary_changed)
    assert cache.read(leaf, primary_changed) is None


def test_a_crafted_record_cannot_write_outside_the_run_directory(tmp_path: Path) -> None:
    graph = _graph(
        leaf_ports=(
            Port(
                port_id="output",
                artifact_ref="../escape.bin",
                kind="test-payload-v1",
            ),
        )
    )
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
    record_path = _record_path(tmp_path, leaf)
    artifacts_dir = record_path.parent / "artifacts"
    artifacts_dir.mkdir(parents=True)
    payload = b"payload"
    (artifacts_dir / "0.bin").write_bytes(payload)
    _write_record(
        tmp_path,
        leaf,
        {
            "schema_version": 2,
            "kind": "test-cache-v1",
            "cache_key": leaf.cache_key,
            "node_id": leaf.node_id,
            "lineage": cache.lineage(leaf, context),
            "artifacts": [
                NodeArtifact(
                    artifact_ref="../escape.bin",
                    sha256=hashlib.sha256(payload).hexdigest(),
                    bytes=len(payload),
                ).model_dump(mode="json")
            ],
        },
    )

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


def test_a_valid_record_restores_the_exact_ordered_artifact_sidecar_and_attempt_bundle(
    tmp_path: Path,
) -> None:
    graph = _graph(leaf_ports=_provider_ports())
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
    expected = (
        ("provider/image.png", b"image"),
        ("provider/image.png.meta.json", b'{"provider":"test"}'),
        ("attempts/leaf.json", b'{"kind":"attempt-ledger-v2"}'),
    )
    cache.write(leaf, context, _result_for_bundle(run_dir, expected))
    for ref, _ in expected:
        (run_dir / ref).unlink()

    restored = cache.read(leaf, context)

    assert restored is not None
    assert tuple(artifact.artifact_ref for artifact in restored.artifacts) == tuple(
        ref for ref, _ in expected
    )
    assert tuple((run_dir / ref).read_bytes() for ref, _ in expected) == tuple(
        data for _, data in expected
    )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("schema_version", 1),
        ("schema_version", "2"),
        ("schema_version", 2.0),
        ("kind", "other-cache-v1"),
        ("node_id", "root"),
        ("cache_key", "f" * 64),
    ],
)
def test_cache_rejects_a_record_with_mismatched_identity_metadata(
    tmp_path: Path, field: str, replacement: object
) -> None:
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
    record = _read_record(tmp_path, leaf)
    record[field] = replacement
    _write_record(tmp_path, leaf, record)

    assert cache.read(leaf, context) is None


@pytest.mark.parametrize(
    "field", ["schema_version", "kind", "node_id", "cache_key", "lineage", "artifacts"]
)
def test_cache_rejects_a_record_missing_required_metadata(tmp_path: Path, field: str) -> None:
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
    record = _read_record(tmp_path, leaf)
    del record[field]
    _write_record(tmp_path, leaf, record)

    assert cache.read(leaf, context) is None


def test_cache_rejects_an_unknown_record_field(tmp_path: Path) -> None:
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
    record = _read_record(tmp_path, leaf)
    record["undeclared_metadata"] = True
    _write_record(tmp_path, leaf, record)

    assert cache.read(leaf, context) is None


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_artifact",
        "missing_sidecar",
        "missing_attempt_ledger",
        "extra_output",
        "duplicate_path",
        "undeclared_output",
        "non_string_path",
        "mismatched_order",
    ],
)
def test_cache_rejects_a_bundle_that_is_not_exactly_the_declared_order(
    tmp_path: Path, mutation: str
) -> None:
    graph = _graph(leaf_ports=_provider_ports())
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
    cache.write(
        leaf,
        context,
        _result_for_bundle(
            run_dir,
            (
                ("provider/image.png", b"image"),
                ("provider/image.png.meta.json", b"meta"),
                ("attempts/leaf.json", b"attempts"),
            ),
        ),
    )
    record = _read_record(tmp_path, leaf)
    outputs = record["artifacts"]
    assert isinstance(outputs, list)
    if mutation == "missing_artifact":
        record["artifacts"] = outputs[1:]
    elif mutation == "missing_sidecar":
        record["artifacts"] = [outputs[0], outputs[2]]
    elif mutation == "missing_attempt_ledger":
        record["artifacts"] = outputs[:2]
    elif mutation == "extra_output":
        extra = dict(outputs[2])
        extra["artifact_ref"] = "provider/undeclared.bin"
        record["artifacts"] = [*outputs, extra]
    elif mutation == "duplicate_path":
        record["artifacts"] = [outputs[0], outputs[1], outputs[1]]
    elif mutation == "undeclared_output":
        undeclared = dict(outputs[0])
        undeclared["artifact_ref"] = "provider/undeclared.png"
        record["artifacts"] = [undeclared, outputs[1], outputs[2]]
    elif mutation == "non_string_path":
        malformed = dict(outputs[0])
        malformed["artifact_ref"] = ["provider/image.png"]
        record["artifacts"] = [malformed, outputs[1], outputs[2]]
    elif mutation == "mismatched_order":
        record["artifacts"] = [outputs[1], outputs[0], outputs[2]]
    else:  # pragma: no cover - the parametrization above is exhaustive.
        raise AssertionError(mutation)
    _write_record(tmp_path, leaf, record)

    assert cache.read(leaf, context) is None


def test_cache_rejects_an_extra_payload_file(tmp_path: Path) -> None:
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
    (_record_path(tmp_path, leaf).parent / "artifacts" / "1.bin").write_bytes(b"extra")

    assert cache.read(leaf, context) is None


def test_a_missed_stale_bundle_can_be_rewritten_and_then_hit(tmp_path: Path) -> None:
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
    result = _result_for(run_dir, "leaf.bin", b"payload")
    cache.write(leaf, context, result)
    artifacts_dir = _record_path(tmp_path, leaf).parent / "artifacts"
    (artifacts_dir / "1.bin").write_bytes(b"stale")
    assert cache.read(leaf, context) is None

    cache.write(leaf, context, result)

    assert sorted(path.name for path in artifacts_dir.iterdir()) == ["0.bin"]
    (run_dir / "leaf.bin").unlink()
    restored = cache.read(leaf, context)
    assert restored is not None and restored.cache is CacheDisposition.HIT
    assert (run_dir / "leaf.bin").read_bytes() == b"payload"


def test_cache_write_rejects_a_non_exact_bundle_before_cache_mutation(tmp_path: Path) -> None:
    graph = _graph(leaf_ports=_provider_ports())
    run_dir = tmp_path / "run"
    cache_dir = tmp_path / "cache"
    cache = NodeArtifactCache(
        graph,
        run_dir=run_dir,
        cache_dir=cache_dir,
        namespace="test-v1",
        record_kind="test-cache-v1",
    )
    leaf = graph.node("leaf")
    context = _context(graph, root="a" * 64, barrier="b" * 64)
    valid = _result_for_bundle(
        run_dir,
        (
            ("provider/image.png", b"image"),
            ("provider/image.png.meta.json", b"meta"),
            ("attempts/leaf.json", b"attempts"),
        ),
    )
    reordered = NodeExecutionResult(
        cache=valid.cache,
        attempts=valid.attempts,
        provider_operations=valid.provider_operations,
        artifacts=(valid.artifacts[1], valid.artifacts[0], valid.artifacts[2]),
    )

    with pytest.raises(ValueError, match="exactly match"):
        cache.write(leaf, context, reordered)
    assert not cache_dir.exists()


def test_cache_write_rejects_source_bytes_that_do_not_match_the_result(
    tmp_path: Path,
) -> None:
    graph = _graph()
    run_dir = tmp_path / "run"
    cache_dir = tmp_path / "cache"
    cache = NodeArtifactCache(
        graph,
        run_dir=run_dir,
        cache_dir=cache_dir,
        namespace="test-v1",
        record_kind="test-cache-v1",
    )
    leaf = graph.node("leaf")
    context = _context(graph, root="a" * 64, barrier="b" * 64)
    valid = _result_for(run_dir, "leaf.bin", b"payload")
    bad_digest = NodeExecutionResult(
        cache=valid.cache,
        attempts=valid.attempts,
        provider_operations=valid.provider_operations,
        artifacts=(NodeArtifact(artifact_ref="leaf.bin", sha256="f" * 64, bytes=len(b"payload")),),
    )

    with pytest.raises(ValueError, match="does not match its digest"):
        cache.write(leaf, context, bad_digest)
    assert not cache_dir.exists()


def test_cache_write_rejects_a_symlinked_run_source(tmp_path: Path) -> None:
    graph = _graph()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    external = tmp_path / "external.bin"
    external.write_bytes(b"payload")
    (run_dir / "leaf.bin").symlink_to(external)
    cache_dir = tmp_path / "cache"
    cache = NodeArtifactCache(
        graph,
        run_dir=run_dir,
        cache_dir=cache_dir,
        namespace="test-v1",
        record_kind="test-cache-v1",
    )
    leaf = graph.node("leaf")
    context = _context(graph, root="a" * 64, barrier="b" * 64)
    result = NodeExecutionResult(
        cache=CacheDisposition.MISS,
        attempts=1,
        provider_operations=0,
        artifacts=(
            NodeArtifact(
                artifact_ref="leaf.bin",
                sha256=hashlib.sha256(b"payload").hexdigest(),
                bytes=len(b"payload"),
            ),
        ),
    )

    with pytest.raises(ValueError, match="must not be a symlink"):
        cache.write(leaf, context, result)
    assert external.read_bytes() == b"payload"
    assert not cache_dir.exists()


def test_cache_write_rejects_a_symlinked_run_root(tmp_path: Path) -> None:
    graph = _graph()
    external = tmp_path / "external"
    external.mkdir()
    (external / "leaf.bin").write_bytes(b"payload")
    run_dir = tmp_path / "run"
    run_dir.symlink_to(external, target_is_directory=True)
    cache_dir = tmp_path / "cache"
    cache = NodeArtifactCache(
        graph,
        run_dir=run_dir,
        cache_dir=cache_dir,
        namespace="test-v1",
        record_kind="test-cache-v1",
    )
    leaf = graph.node("leaf")
    context = _context(graph, root="a" * 64, barrier="b" * 64)
    result = NodeExecutionResult(
        cache=CacheDisposition.MISS,
        attempts=1,
        provider_operations=0,
        artifacts=(
            NodeArtifact(
                artifact_ref="leaf.bin",
                sha256=hashlib.sha256(b"payload").hexdigest(),
                bytes=len(b"payload"),
            ),
        ),
    )

    with pytest.raises(ValueError, match="run root has a symlink ancestor"):
        cache.write(leaf, context, result)
    assert (external / "leaf.bin").read_bytes() == b"payload"
    assert not cache_dir.exists()


def test_cache_write_rejects_a_symlinked_run_source_parent(tmp_path: Path) -> None:
    graph = _graph(
        leaf_ports=(
            Port(
                port_id="output",
                artifact_ref="nested/leaf.bin",
                kind="test-payload-v1",
            ),
        )
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (external / "leaf.bin").write_bytes(b"payload")
    (run_dir / "nested").symlink_to(external, target_is_directory=True)
    cache_dir = tmp_path / "cache"
    cache = NodeArtifactCache(
        graph,
        run_dir=run_dir,
        cache_dir=cache_dir,
        namespace="test-v1",
        record_kind="test-cache-v1",
    )
    leaf = graph.node("leaf")
    context = _context(graph, root="a" * 64, barrier="b" * 64)
    result = NodeExecutionResult(
        cache=CacheDisposition.MISS,
        attempts=1,
        provider_operations=0,
        artifacts=(
            NodeArtifact(
                artifact_ref="nested/leaf.bin",
                sha256=hashlib.sha256(b"payload").hexdigest(),
                bytes=len(b"payload"),
            ),
        ),
    )

    with pytest.raises(ValueError, match="symlinked parent"):
        cache.write(leaf, context, result)
    assert (external / "leaf.bin").read_bytes() == b"payload"
    assert not cache_dir.exists()


def test_failed_cache_bundle_install_rolls_back_to_the_readable_old_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    cache.write(leaf, context, _result_for(run_dir, "leaf.bin", b"old"))
    root = _record_path(tmp_path, leaf).parent
    replacement = _result_for(run_dir, "leaf.bin", b"new")
    original_replace = node_cache_module._replace_cache_path

    def fail_staging_install(source: Path, destination: Path) -> None:
        if "-staging-" in source.name and destination == root:
            raise OSError("injected staging install failure")
        original_replace(source, destination)

    monkeypatch.setattr(node_cache_module, "_replace_cache_path", fail_staging_install)
    with pytest.raises(OSError, match="injected staging install failure"):
        cache.write(leaf, context, replacement)

    (run_dir / "leaf.bin").unlink()
    restored = cache.read(leaf, context)
    assert restored is not None and restored.cache is CacheDisposition.HIT
    assert (run_dir / "leaf.bin").read_bytes() == b"old"
    assert not list(root.parent.glob(f"{root.name}-backup-*"))


def test_failed_cache_bundle_rollback_retains_the_recovery_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    cache.write(leaf, context, _result_for(run_dir, "leaf.bin", b"old"))
    root = _record_path(tmp_path, leaf).parent
    replacement = _result_for(run_dir, "leaf.bin", b"new")
    original_replace = node_cache_module._replace_cache_path

    def fail_install_and_rollback(source: Path, destination: Path) -> None:
        if "-staging-" in source.name or "-backup-" in source.name:
            raise OSError("injected cache swap failure")
        original_replace(source, destination)

    monkeypatch.setattr(node_cache_module, "_replace_cache_path", fail_install_and_rollback)
    with pytest.raises(OSError, match="recovery bundle was retained"):
        cache.write(leaf, context, replacement)

    recovery = list(root.parent.glob(f"{root.name}-backup-*"))
    assert not root.exists()
    assert len(recovery) == 1
    retained = json.loads((recovery[0] / "record.json").read_text())
    assert retained["cache_key"] == leaf.cache_key
    assert not list(root.parent.glob(f"{root.name}-staging-*"))


@pytest.mark.parametrize(
    "ancestor", ["cache_parent", "cache_root", "namespace", "prefix", "cache_key"]
)
def test_cache_rejects_symlinked_cache_ancestors_without_touching_the_target(
    tmp_path: Path, ancestor: str
) -> None:
    graph = _graph()
    run_dir = tmp_path / "run"
    external = tmp_path / "external"
    external.mkdir()
    marker = external / "marker.txt"
    marker.write_bytes(b"untouched")
    if ancestor == "cache_parent":
        cache_parent = tmp_path / "cache-parent"
        cache_parent.symlink_to(external, target_is_directory=True)
        cache_dir = cache_parent / "cache"
    else:
        cache_dir = tmp_path / "cache"
    leaf = graph.node("leaf")
    namespace = "test-v1"
    prefix = leaf.cache_key[:2]
    if ancestor == "cache_parent":
        pass
    elif ancestor == "cache_root":
        cache_dir.symlink_to(external, target_is_directory=True)
    else:
        cache_dir.mkdir()
        namespace_path = cache_dir / namespace
        if ancestor == "namespace":
            namespace_path.symlink_to(external, target_is_directory=True)
        else:
            namespace_path.mkdir()
            prefix_path = namespace_path / prefix
            if ancestor == "prefix":
                prefix_path.symlink_to(external, target_is_directory=True)
            else:
                prefix_path.mkdir()
                (prefix_path / leaf.cache_key).symlink_to(external, target_is_directory=True)
    cache = NodeArtifactCache(
        graph,
        run_dir=run_dir,
        cache_dir=cache_dir,
        namespace=namespace,
        record_kind="test-cache-v1",
    )
    context = _context(graph, root="a" * 64, barrier="b" * 64)
    result = _result_for(run_dir, "leaf.bin", b"payload")

    assert cache.read(leaf, context) is None
    with pytest.raises(ValueError, match=r"symlink|non-symlink"):
        cache.write(leaf, context, result)
    assert marker.read_bytes() == b"untouched"
    assert sorted(path.name for path in external.iterdir()) == ["marker.txt"]


def test_record_symlink_is_never_read_and_rewrite_does_not_touch_its_target(
    tmp_path: Path,
) -> None:
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
    result = _result_for(run_dir, "leaf.bin", b"payload")
    cache.write(leaf, context, result)
    record_path = _record_path(tmp_path, leaf)
    external_record = tmp_path / "external-record.json"
    external_record.write_bytes(record_path.read_bytes())
    external_bytes = external_record.read_bytes()
    record_path.unlink()
    record_path.symlink_to(external_record)

    assert cache.read(leaf, context) is None
    cache.write(leaf, context, result)

    assert not record_path.is_symlink()
    assert external_record.read_bytes() == external_bytes


def test_artifacts_symlink_is_never_read_and_rewrite_does_not_touch_its_target(
    tmp_path: Path,
) -> None:
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
    result = _result_for(run_dir, "leaf.bin", b"payload")
    cache.write(leaf, context, result)
    artifacts_dir = _record_path(tmp_path, leaf).parent / "artifacts"
    external_artifacts = tmp_path / "external-artifacts"
    artifacts_dir.rename(external_artifacts)
    artifacts_dir.symlink_to(external_artifacts, target_is_directory=True)
    external_payload = (external_artifacts / "0.bin").read_bytes()

    assert cache.read(leaf, context) is None
    cache.write(leaf, context, result)

    assert not artifacts_dir.is_symlink()
    assert (external_artifacts / "0.bin").read_bytes() == external_payload


def test_failed_multi_directory_restore_rolls_back_every_run_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph = _graph(leaf_ports=_provider_ports())
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
    refs = (
        "provider/image.png",
        "provider/image.png.meta.json",
        "attempts/leaf.json",
    )
    cache.write(
        leaf,
        context,
        _result_for_bundle(
            run_dir,
            (
                (refs[0], b"cached-image"),
                (refs[1], b"cached-meta"),
                (refs[2], b"cached-attempts"),
            ),
        ),
    )
    previous = (b"previous-image", b"previous-meta", b"previous-attempts")
    for ref, data in zip(refs, previous, strict=True):
        (run_dir / ref).write_bytes(data)
    original_replace = node_cache_module._replace_path
    installs = 0

    def fail_second_install(source: Path, destination: Path) -> None:
        nonlocal installs
        if source.name.endswith(".cache-restore"):
            installs += 1
            if installs == 2:
                raise OSError("injected restore failure")
        original_replace(source, destination)

    monkeypatch.setattr(node_cache_module, "_replace_path", fail_second_install)

    assert cache.read(leaf, context) is None
    assert tuple((run_dir / ref).read_bytes() for ref in refs) == previous
    assert not list(run_dir.rglob("*.cache-restore"))
    assert not list(run_dir.rglob("*.cache-backup"))


def test_failed_restore_rollback_retains_every_recovery_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph = _graph(leaf_ports=_provider_ports())
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
    refs = (
        "provider/image.png",
        "provider/image.png.meta.json",
        "attempts/leaf.json",
    )
    cache.write(
        leaf,
        context,
        _result_for_bundle(
            run_dir,
            (
                (refs[0], b"cached-image"),
                (refs[1], b"cached-meta"),
                (refs[2], b"cached-attempts"),
            ),
        ),
    )
    previous = (b"previous-image", b"previous-meta", b"previous-attempts")
    for ref, data in zip(refs, previous, strict=True):
        (run_dir / ref).write_bytes(data)
    original_replace = node_cache_module._replace_path
    installs = 0

    def fail_install_and_rollback(source: Path, destination: Path) -> None:
        nonlocal installs
        if source.name.endswith(".cache-restore"):
            installs += 1
            if installs == 2:
                raise OSError("injected restore install failure")
        if source.name.endswith(".cache-backup"):
            raise OSError("injected restore rollback failure")
        original_replace(source, destination)

    monkeypatch.setattr(node_cache_module, "_replace_path", fail_install_and_rollback)

    with pytest.raises(OSError, match="recovery backups were retained"):
        cache.read(leaf, context)
    backups = sorted(run_dir.rglob("*.cache-backup"))
    assert len(backups) == len(previous)
    assert sorted(path.read_bytes() for path in backups) == sorted(previous)
    assert not list(run_dir.rglob("*.cache-restore"))


def test_cache_treats_invalid_strict_artifact_metadata_as_a_miss(tmp_path: Path) -> None:
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
    cache.write(leaf, context, _result_for(run_dir, "leaf.bin", b"x"))
    record = _read_record(tmp_path, leaf)
    record["artifacts"][0]["bytes"] = True
    _write_record(tmp_path, leaf, record)

    assert cache.read(leaf, context) is None


def test_cache_treats_a_non_utf8_record_as_a_miss(tmp_path: Path) -> None:
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
    _record_path(tmp_path, leaf).write_bytes(b"\xff")

    assert cache.read(leaf, context) is None
