"""Public authoring boundaries exercised through caller-defined local node types."""

from __future__ import annotations

import asyncio
import io
import json
import wave
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from PIL import Image

from gnode import (
    BindingTable,
    CacheDisposition,
    Graph,
    GraphBuilder,
    Node,
    NodeExecutionResult,
    NodeType,
    ViewArchetype,
    seal_graph,
)
from stage_gen.pipeline import (
    InputFiles,
    NodeBinding,
    PipelineContext,
    PipelineDefinition,
    define,
    inspect,
    load_definition,
    plan,
    record_port,
    run,
)

EXAMPLE = Path(__file__).resolve().parents[3] / "examples/pipelines/local_media.py"


def _input(tmp_path: Path) -> Path:
    root = tmp_path / "input"
    root.mkdir()
    (root / "palette.json").write_text('{"color": [48, 132, 184]}')
    return root


async def test_real_media_fanout_cache_reuse_and_portable_inspection(tmp_path: Path) -> None:
    definition = load_definition(f"{EXAMPLE}:pipeline")
    planned = plan(definition, input_root=_input(tmp_path))
    result = await run(planned, output_root=tmp_path / "first", cache_root=tmp_path / "cache")
    assert result.summary.ok
    assert result.view.kind == "pipeline-execution-view-v1"
    assert result.view.pipeline_id == "local-media"
    with Image.open(result.run_dir / "swatch.png") as image:
        assert image.size == (64, 64)
        assert image.getpixel((0, 0)) == (48, 132, 184)
    with wave.open(str(result.run_dir / "tone.wav")) as audio:
        assert audio.getnframes() == 4_000
    portable = json.loads((result.run_dir / "pipeline.json").read_text())
    assert str(tmp_path) not in json.dumps(portable)
    second = await run(planned, output_root=tmp_path / "second", cache_root=tmp_path / "cache")
    assert all(node.cache is CacheDisposition.HIT for node in second.summary.nodes)
    assert (result.run_dir / "swatch.png.meta.json").read_bytes() == (
        second.run_dir / "swatch.png.meta.json"
    ).read_bytes()
    assert inspect(second.run_dir) == second.view


async def test_partial_targets_do_not_execute_other_branches(tmp_path: Path) -> None:
    definition = load_definition(str(EXAMPLE))
    planned = plan(definition, input_root=_input(tmp_path), targets=["swatch"])
    assert [span.node_id for span in planned.projection.spans] == ["swatch"]
    result = await run(planned, output_root=tmp_path / "run", cache_root=tmp_path / "cache")
    assert result.summary.ok
    assert [node.node_id for node in result.summary.nodes] == ["swatch"]
    assert not (result.run_dir / "tone.wav").exists()


async def test_changed_input_is_refused_before_writes_and_replan_reuses_other_branch(
    tmp_path: Path,
) -> None:
    inputs = _input(tmp_path)
    definition = load_definition(str(EXAMPLE))
    original = plan(definition, input_root=inputs)
    await run(original, output_root=tmp_path / "first", cache_root=tmp_path / "cache")
    (inputs / "palette.json").write_text('{"color": [1, 2, 3]}')
    with pytest.raises(ValueError, match="input changed"):
        await run(original, output_root=tmp_path / "refused", cache_root=tmp_path / "cache")
    assert not (tmp_path / "refused").exists()
    revised = plan(definition, input_root=inputs)
    assert original.graph.node("tone").cache_key == revised.graph.node("tone").cache_key
    result = await run(revised, output_root=tmp_path / "second", cache_root=tmp_path / "cache")
    assert {node.node_id: node.cache for node in result.summary.nodes} == {
        "swatch": CacheDisposition.MISS,
        "tone": CacheDisposition.HIT,
        "catalog": CacheDisposition.MISS,
    }


async def test_failed_custom_node_is_inspectable_with_independent_success(tmp_path: Path) -> None:
    inputs = _input(tmp_path)
    (inputs / "palette.json").write_text('{"color": [999, 0, 0]}')
    result = await run(
        plan(load_definition(str(EXAMPLE)), input_root=inputs),
        output_root=tmp_path / "run",
        cache_root=tmp_path / "cache",
    )
    assert not result.summary.ok
    statuses = {node.node_id: node.status.value for node in result.summary.nodes}
    assert statuses == {"swatch": "failed", "tone": "succeeded", "catalog": "skipped"}
    view = inspect(result.run_dir)
    assert view.run_state == "failed"
    failed = next(node for node in view.nodes if node.node_id == "swatch")
    assert "three integer channels" in (failed.error or "")


def _custom_definition(
    handler: Callable[[Node, PipelineContext], Awaitable[NodeExecutionResult]],
    *,
    ref: str = "result.json",
    admit: Callable[[Node, tuple[bytes, ...]], bool] | None = None,
) -> PipelineDefinition:
    node_type = NodeType(
        "consumer/custom.run", "Custom node", ViewArchetype.TRANSFORM, "local", "1"
    )

    def build(_inputs: InputFiles) -> Graph:
        graph = GraphBuilder(profile=BindingTable(()))
        graph.add(
            node_type,
            "custom",
            domain="consumer",
            description="Call injected application logic",
            ports=(record_port("output", ref, "custom-v1"),),
        )
        return seal_graph(
            Graph,
            schema_version=1,
            kind="custom-v1",
            resources=graph.resources(),
            nodes=graph.nodes,
            terminal_node_id="custom",
        )

    return define(
        "custom",
        title="Consumer definition",
        build=build,
        bindings=[NodeBinding(node_type, handler, admit)],
    )


async def test_services_are_injected_and_node_keys_are_preserved(tmp_path: Path) -> None:
    calls = []

    async def handler(node: Node, context: PipelineContext) -> NodeExecutionResult:
        calls.append(context.services["answer"])
        return await context.publish(node, {"output": b'{"answer":42}'})

    definition = _custom_definition(handler)
    input_root = _input(tmp_path)
    original = definition.build(InputFiles(input_root))
    planned = plan(definition, input_root=input_root)
    assert planned.graph.nodes == original.nodes
    result = await run(
        planned,
        output_root=tmp_path / "run",
        cache_root=tmp_path / "cache",
        services={"answer": 42},
    )
    assert result.summary.ok
    assert calls == [42]


async def test_fresh_and_cached_admission_share_validator(tmp_path: Path) -> None:
    calls = []
    accepted = True

    async def handler(node: Node, context: PipelineContext) -> NodeExecutionResult:
        calls.append(node.node_id)
        return await context.publish(node, {"output": b"{}"})

    def admit(_node: Node, payloads: tuple[bytes, ...]) -> bool:
        return accepted and payloads == (b"{}",)

    planned = plan(_custom_definition(handler, admit=admit), input_root=_input(tmp_path))
    first = await run(planned, output_root=tmp_path / "first", cache_root=tmp_path / "cache")
    assert first.summary.ok
    accepted = False
    second = await run(planned, output_root=tmp_path / "second", cache_root=tmp_path / "cache")
    assert not second.summary.ok
    assert calls == ["custom", "custom"]


async def test_cancellation_leaves_inspectable_trace(tmp_path: Path) -> None:
    entered = asyncio.Event()
    cleaning = asyncio.Event()
    release = asyncio.Event()
    cleaned = asyncio.Event()

    async def handler(_node: Node, _context: PipelineContext) -> NodeExecutionResult:
        entered.set()
        try:
            return await asyncio.Future[NodeExecutionResult]()
        finally:
            cleaning.set()
            await release.wait()
            cleaned.set()

    planned = plan(_custom_definition(handler), input_root=_input(tmp_path))
    task = asyncio.create_task(
        run(planned, output_root=tmp_path / "run", cache_root=tmp_path / "cache")
    )
    await entered.wait()
    task.cancel()
    try:
        await cleaning.wait()
        await asyncio.sleep(0)
        assert not task.done()
        assert not (tmp_path / "run/execution-view.json").exists()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned.is_set()
    assert inspect(tmp_path / "run").run_state == "canceled"
    assert (tmp_path / "run/execution-view.json").exists()


@pytest.mark.parametrize(
    "ref", ["../escape.json", "execution-plan.json", "execution-trace.jsonl/child"]
)
def test_output_traversal_and_control_collisions_are_refused(tmp_path: Path, ref: str) -> None:
    async def handler(node: Node, context: PipelineContext) -> NodeExecutionResult:
        return await context.publish(node, {"output": b"{}"})

    with pytest.raises(ValueError):
        plan(_custom_definition(handler, ref=ref), input_root=_input(tmp_path))


def test_symlink_input_is_refused(tmp_path: Path) -> None:
    inputs = _input(tmp_path)
    (inputs / "linked.json").symlink_to(inputs / "palette.json")
    with pytest.raises(ValueError, match="symlink"):
        InputFiles(inputs).read("linked.json")


async def test_output_symlink_is_refused(tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"original")

    async def handler(node: Node, context: PipelineContext) -> NodeExecutionResult:
        (context.output_root / "result.json").symlink_to(outside)
        return await context.publish(node, {"output": b"changed"})

    result = await run(
        plan(_custom_definition(handler), input_root=_input(tmp_path)),
        output_root=tmp_path / "run",
        cache_root=tmp_path / "cache",
    )
    assert not result.summary.ok
    assert outside.read_bytes() == b"original"


async def test_provider_opt_in_is_refused_before_any_writes_and_scoped_to_targets(
    tmp_path: Path,
) -> None:
    from gnode import Binding, ModelRef

    local = NodeType("test/local.run", "Local", ViewArchetype.SOURCE, "local", "1")
    provider = NodeType("test/provider.run", "Provider", ViewArchetype.IMAGE, "image", "1")
    terminal = NodeType("test/terminal.run", "Terminal", ViewArchetype.PACKAGE, "local", "1")
    calls = []

    def build(_inputs: InputFiles) -> Graph:
        builder = GraphBuilder(
            profile=BindingTable(
                [Binding("image", ModelRef("synthetic", "test"), "provider", 1.0, 0.25, 0.5)]
            )
        )
        builder.add(local, "local", domain="test", description="Local work")
        builder.add(provider, "provider", domain="test", description="Opt-in provider work")
        builder.add(
            terminal,
            "terminal",
            domain="test",
            description="Join",
            depends_on=("local", "provider"),
        )
        return seal_graph(
            Graph,
            schema_version=1,
            kind="test-v1",
            resources=builder.resources(),
            nodes=builder.nodes,
            terminal_node_id="terminal",
        )

    async def handler(node: Node, context: PipelineContext) -> NodeExecutionResult:
        calls.append(node.node_id)
        return await context.publish(node, {})

    definition = define(
        "opt-in",
        title="Provider opt-in",
        build=build,
        bindings=[NodeBinding(item, handler) for item in (local, provider, terminal)],
    )
    inputs = _input(tmp_path)
    with pytest.raises(ValueError, match="allow_provider_calls"):
        await run(
            plan(definition, input_root=inputs),
            output_root=tmp_path / "refused",
            cache_root=tmp_path / "cache",
        )
    assert not (tmp_path / "refused").exists()
    assert not (tmp_path / "cache").exists()
    result = await run(
        plan(definition, input_root=inputs, targets=["local"]),
        output_root=tmp_path / "local",
        cache_root=tmp_path / "cache",
    )
    assert result.summary.ok
    assert calls == ["local"]
    assert result.plan.projection.estimated_cost_high_usd == 0.0
    projected = plan(definition, input_root=inputs, targets=["local", "provider"]).projection
    assert {span.node_id for span in projected.spans} == {"local", "provider"}
    assert projected.operation_counts == {"image": 1, "local": 1}
    assert projected.estimated_cost_low_usd == 0.25
    assert projected.critical_path == ("provider",)


def test_core_pipeline_does_not_import_application_composition_or_game_contracts() -> None:
    import ast

    import stage_gen.pipeline

    root = Path(stage_gen.pipeline.__file__).parent
    forbidden = (
        "stage_gen.orchestration",
        "stage_gen.recipes",
        "stage_gen.components",
        "demo_game_tools",
        "demo_game_collection",
        "bellweather_pipeline",
        "iron_petal_unit_pipeline",
        "ember_hollow_pipeline",
        "the_grain_pipeline",
    )
    for source in root.glob("*.py"):
        for node in ast.walk(ast.parse(source.read_text())):
            names = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            assert not any(name.startswith(forbidden) for name in names), source.name


async def test_custom_mime_and_preview_survive_portable_inspection(tmp_path: Path) -> None:
    from stage_gen.pipeline import artifact_port

    node_type = NodeType(
        "test/custom_media.run", "Custom media", ViewArchetype.TRANSFORM, "local", "1"
    )

    def build(_inputs: InputFiles) -> Graph:
        builder = GraphBuilder(profile=BindingTable(()))
        builder.add(
            node_type,
            "asset",
            domain="assets",
            description="Original synthetic test image",
            ports=[artifact_port("image", "asset.bin", "custom-image-v1")],
        )
        return seal_graph(
            Graph,
            schema_version=1,
            kind="custom-v1",
            resources=builder.resources(),
            nodes=builder.nodes,
            terminal_node_id="asset",
        )

    async def handler(node: Node, context: PipelineContext) -> NodeExecutionResult:
        buffer = io.BytesIO()
        Image.new("RGB", (4, 4), "blue").save(buffer, format="PNG")
        return await context.publish(
            node,
            {"image": buffer.getvalue()},
            media_types={"image": "image/png"},
            previews={"image": {"kind": "consumer-grid-v1", "columns": 2}},
        )

    definition = define(
        "custom-media",
        title="Custom preview",
        build=build,
        bindings=[NodeBinding(node_type, handler)],
    )
    result = await run(
        plan(definition, input_root=_input(tmp_path)),
        output_root=tmp_path / "run",
        cache_root=tmp_path / "cache",
    )
    assert result.summary.ok
    artifact = next(
        item
        for item in inspect(result.run_dir).nodes[0].artifacts
        if item.artifact_ref == "asset.bin"
    )
    assert artifact.media_type == "image/png"
    assert artifact.display == "image"
    assert artifact.preview == {"kind": "consumer-grid-v1", "columns": 2}


async def test_deterministic_portrait_processing_preserves_exterior_and_reuses_stages(
    tmp_path: Path,
) -> None:
    import importlib.util

    example = EXAMPLE.with_name("portrait_processing.py")
    spec = importlib.util.spec_from_file_location("portrait_processing_example", example)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    inputs = tmp_path / "portrait-inputs"
    module.write_example_inputs(inputs)
    definition = load_definition(str(example))
    planned = plan(definition, input_root=inputs)
    first = await run(planned, output_root=tmp_path / "first", cache_root=tmp_path / "cache")
    assert first.summary.ok
    checks = json.loads((first.run_dir / "checks.json").read_text())
    assert checks["outside_mask_identical"] and checks["alpha_identical"]
    assert checks["changed_pixels"] > 0
    with Image.open(first.run_dir / "preview.webp") as preview:
        assert getattr(preview, "n_frames", 1) == 2
        assert preview.size == (192, 256)
    second = await run(planned, output_root=tmp_path / "second", cache_root=tmp_path / "cache")
    assert second.summary.ok and all(
        node.cache is CacheDisposition.HIT for node in second.summary.nodes
    )
