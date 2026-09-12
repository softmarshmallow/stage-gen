"""Filesystem admission, spent-operation reporting, and dependency cache honesty."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from gnode import (
    Binding,
    BindingTable,
    CacheDisposition,
    Graph,
    GraphBuilder,
    ModelRef,
    Node,
    NodeExecutionContext,
    NodeExecutionResult,
    NodeType,
    ProvenanceInput,
    SoftwareIdentity,
    ViewArchetype,
    seal_graph,
)
from stage_gen.pipeline import (
    InputFiles,
    NodeBinding,
    PipelineContext,
    PipelineDefinition,
    artifact_port,
    define,
    inspect,
    plan,
    run,
)
from stage_gen.pipeline.node_cache import NodeArtifactCache


def _provider_definition(calls: list[str]) -> PipelineDefinition:
    node_type = NodeType("test/provider", "Synthetic provider", ViewArchetype.IMAGE, "image", "1")

    def build(_inputs: InputFiles) -> Graph:
        builder = GraphBuilder(
            profile=BindingTable(
                [Binding("image", ModelRef("synthetic", "test"), "provider", 1.0, 0.25, 0.25)]
            )
        )
        builder.add(
            node_type,
            "provider",
            domain="test",
            description="Synthetic operation without network access",
            ports=(artifact_port("output", "result.json", "synthetic-v1"),),
        )
        return seal_graph(
            Graph,
            schema_version=1,
            kind="synthetic-v1",
            resources=builder.resources(),
            nodes=builder.nodes,
            terminal_node_id="provider",
        )

    async def handler(node: Node, context: PipelineContext) -> NodeExecutionResult:
        calls.append(node.node_id)
        identity = SoftwareIdentity(name="synthetic-test", version="1")
        return await context.publish(
            node,
            {"output": b'{"synthetic":true}'},
            provider_operations=1,
            known_cost_usd=0.25,
            provenance={
                "output": ProvenanceInput(
                    attempts=1,
                    provider="test",
                    model="synthetic",
                    prompt="Synthetic fixture without a provider request",
                    component=identity,
                    tool=identity,
                )
            },
        )

    return define(
        "synthetic-provider",
        title="Synthetic provider",
        build=build,
        bindings=[NodeBinding(node_type, handler)],
    )


@pytest.mark.parametrize("root_name", ["cache", "output"])
@pytest.mark.parametrize("file_parent", [False, True])
async def test_non_directory_roots_are_refused_before_work_or_run_publication(
    tmp_path: Path, root_name: str, file_parent: bool
) -> None:
    calls: list[str] = []
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    roots = {"cache": tmp_path / "cache", "output": tmp_path / "output"}
    roots[root_name].write_text("existing file")
    if file_parent:
        roots[root_name] /= "nested"
    with pytest.raises(ValueError, match="must be directories"):
        await run(
            plan(_provider_definition(calls), input_root=inputs),
            output_root=roots["output"],
            cache_root=roots["cache"],
            allow_provider_calls=True,
        )
    assert calls == []
    assert (tmp_path / root_name).read_text() == "existing file"
    assert not (tmp_path / ("output" if root_name == "cache" else "cache")).exists()


async def test_cache_store_failure_retains_spent_operations_cost_and_failure_inspection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    inputs = tmp_path / "inputs"
    inputs.mkdir()

    def fail_cache_write(
        self: NodeArtifactCache,
        node: Node,
        context: NodeExecutionContext,
        result: NodeExecutionResult,
    ) -> None:
        assert result.provider_operations == 1 and result.known_cost_usd == 0.25
        raise OSError(28, "injected cache storage failure", str(tmp_path / "private-cache-name"))

    monkeypatch.setattr(NodeArtifactCache, "write", fail_cache_write)
    result = await run(
        plan(_provider_definition(calls), input_root=inputs),
        output_root=tmp_path / "run",
        cache_root=tmp_path / "cache",
        allow_provider_calls=True,
    )
    assert calls == ["provider"]
    assert (result.run_dir / "result.json").read_bytes() == b'{"synthetic":true}'
    assert not result.summary.ok
    assert result.summary.provider_operation_counts == {"image": 1}
    assert result.summary.known_cost_usd == 0.25
    node = result.summary.nodes[0]
    assert node.attempts == 1 and node.provider_operations == 1 and node.known_cost_usd == 0.25
    assert "injected cache storage failure" in (node.error or "")
    assert str(tmp_path) not in result.summary.model_dump_json()
    assert "private-cache-name" not in (result.run_dir / "execution-trace.jsonl").read_text()
    view = inspect(result.run_dir)
    assert view.run_state == "failed"
    assert view.nodes[0].provider_operations == 1
    assert view.nodes[0].known_cost_usd == 0.25


def _dependency_definition(
    handler: Callable[[Node, PipelineContext], Awaitable[NodeExecutionResult]], *, barrier: bool
) -> PipelineDefinition:
    node_type = NodeType("test/copy", "Copy", ViewArchetype.TRANSFORM, "local", "1")

    def build(inputs: InputFiles) -> Graph:
        builder = GraphBuilder(profile=BindingTable(()))
        builder.add(
            node_type,
            "source",
            domain="test",
            description="Read authored input",
            input_digests=(inputs.digest("value.txt"),),
            ports=(artifact_port("output", "source.txt", "text-v1"),),
        )
        builder.add(
            node_type,
            "copy",
            domain="test",
            description="Material or ordering dependency",
            depends_on=("source",),
            cache_depends_on=() if barrier else ("source",),
            ports=(artifact_port("output", "copy.txt", "text-v1"),),
        )
        return seal_graph(
            Graph,
            schema_version=1,
            kind="dependency-v1",
            resources=builder.resources(),
            nodes=builder.nodes,
            terminal_node_id="copy",
        )

    return define(
        "dependency", title="Dependency", build=build, bindings=[NodeBinding(node_type, handler)]
    )


@pytest.mark.parametrize("barrier", [False, True])
async def test_only_material_dependency_artifacts_are_readable(
    tmp_path: Path, barrier: bool
) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()

    async def handler(node: Node, context: PipelineContext) -> NodeExecutionResult:
        data = (
            context.read_input("value.txt")
            if node.node_id == "source"
            else context.read_artifact("source.txt")
        )
        return await context.publish(node, {"output": data})

    definition = _dependency_definition(handler, barrier=barrier)
    for value in ("first", "second"):
        (inputs / "value.txt").write_text(value)
        result = await run(
            plan(definition, input_root=inputs),
            output_root=tmp_path / value,
            cache_root=tmp_path / "cache",
        )
        assert result.summary.ok is not barrier
        if barrier:
            assert "material dependency" in (result.summary.nodes[1].error or "")
            assert not (result.run_dir / "copy.txt").exists()
        else:
            assert (result.run_dir / "copy.txt").read_text() == value
            assert all(item.cache is CacheDisposition.MISS for item in result.summary.nodes)


async def test_ordering_barriers_remain_reusable_and_do_not_claim_content_provenance(
    tmp_path: Path,
) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    calls: list[str] = []

    async def handler(node: Node, context: PipelineContext) -> NodeExecutionResult:
        calls.append(node.node_id)
        data = context.read_input("value.txt") if node.node_id == "source" else b"independent"
        return await context.publish(node, {"output": data})

    definition = _dependency_definition(handler, barrier=True)
    for value in ("first", "second"):
        (inputs / "value.txt").write_text(value)
        result = await run(
            plan(definition, input_root=inputs),
            output_root=tmp_path / value,
            cache_root=tmp_path / "cache",
        )
        assert result.summary.ok
        metadata = json.loads((result.run_dir / "copy.txt.meta.json").read_text())
        assert "source.txt" not in json.dumps(metadata)
    assert calls == ["source", "copy", "source"]
    assert result.summary.nodes[1].cache is CacheDisposition.HIT
