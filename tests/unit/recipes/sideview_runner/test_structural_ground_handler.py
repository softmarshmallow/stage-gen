"""The structural-ground handler requests native alpha and preserves lineage."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image, ImageDraw

from gnode import (
    AbortError,
    AtomicWriteError,
    BinaryArtifact,
    CacheDisposition,
    ImageGenerationRequest,
    NodeExecutionContext,
    NodeExecutionError,
    NodeExecutionResult,
    hash_input_reference,
)
from stage_gen.config import StageGenConfig
from stage_gen.recipes.sideview_runner.prepared_runner import SideviewRunnerNodeHandler
from stage_gen.recipes.sideview_runner.runner_executor import SideviewRunnerExecutor

from ..._runner_fixture import painted_over_guide, two_genre_package


def _provider_sidecar(*, request: ImageGenerationRequest, data: bytes) -> dict[str, object]:
    references = (
        request.input_references
        if request.mask_reference is None
        else (*request.input_references, request.mask_reference)
    )
    refs = [reference.provenance_ref or reference.url for reference in references]
    params: dict[str, object] = {
        "n": 1,
        "validated": request.validate is not None,
        "operation": "edit" if request.input_references else "generation",
        "output_format": request.output_format or "png",
    }
    for key in ("size", "quality", "background"):
        value = getattr(request, key)
        if value is not None:
            params[key] = value
    if request.metadata:
        params["metadata"] = dict(request.metadata)
    caller: dict[str, object] = {}
    if request.validate is not None:
        result = request.validate(BinaryArtifact(data=data, media_type="image/png"))
        assert isinstance(result, dict)
        caller = result
    return {
        "schema_version": 2,
        "provider": "openai",
        "model": "gpt-image-2",
        "seed": None,
        "prompt": request.prompt,
        "prompt_sha256": hashlib.sha256(request.prompt.encode("utf-8")).hexdigest(),
        "references": refs,
        "refs": refs,
        "inputs": [
            hash_input_reference(reference.url, reference.provenance_ref).model_dump(
                mode="json", exclude_none=True
            )
            for reference in references
        ],
        "params": params,
        "validation": {
            "output_nonempty": True,
            "base64": "strict",
            "media_type": "image/png",
            "signature": "matched",
            "caller": request.validate is not None,
            **caller,
        },
        "component": {"name": "@stage-gen/image-generation", "version": "0.0.0"},
        "tool": {"name": "stage-gen", "version": "0.0.0"},
        "artifact": {
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "media_type": "image/png",
        },
        "ts": "2026-09-02T00:00:00.000Z",
        "attempts": 1,
        "retries": 0,
    }


def _rewrite_cached_payload(cache_dir: Path, node: Any, ref: str, data: bytes) -> None:
    cache_key = node.cache_key
    root = cache_dir / "sideview-runner-nodes-v1" / cache_key[:2] / cache_key
    record_path = root / "record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    index = next(
        index
        for index, artifact in enumerate(record["artifacts"])
        if artifact["artifact_ref"] == ref
    )
    (root / "artifacts" / f"{index}.bin").write_bytes(data)
    record["artifacts"][index]["sha256"] = hashlib.sha256(data).hexdigest()
    record["artifacts"][index]["bytes"] = len(data)
    record_path.write_text(json.dumps(record), encoding="utf-8")


def _select_structural_ground(package: Path) -> Path:
    track = package / "runner" / "track.toml"
    source = track.read_text(encoding="utf-8")
    track.write_text(
        source.replace(
            'mode = "terrain-atlas-3x3-minimal-v1"',
            'mode = "runner-structural-ground-v1"',
            1,
        ),
        encoding="utf-8",
    )
    return package


def test_structural_graph_adds_one_shared_local_bridge_without_provider_fanout(
    tmp_path: Path,
) -> None:
    package = _select_structural_ground(two_genre_package(tmp_path / "package"))
    graph = SideviewRunnerExecutor(StageGenConfig()).plan(package).graph
    bridges = [
        node
        for node in graph.nodes
        if node.type_id == "2d/sideview/runner/structural_ground.seam_bridge"
    ]
    assert len(bridges) == 1
    bridge = bridges[0]
    assert bridge.operation == "local"
    assert bridge.depends_on == (
        "track-ground-warmup_flat-guide",
        "track-ground-warmup_flat-generate",
    )
    assert bridge.card is not None
    assert {(ref.node_id, ref.port_id) for ref in bridge.card.reference_inputs} == {
        ("track-ground-warmup_flat-guide", "image"),
        ("track-ground-warmup_flat-generate", "image"),
    }
    validations = [
        graph.node("track-ground-warmup_flat-validate"),
        graph.node("track-ground-first_gap-validate"),
    ]
    assert all(bridge.node_id in node.depends_on for node in validations)
    assert graph.operation_counts() == {
        "local": 18,
        "image_generation": 10,
        "structured_generation": 2,
        "tool_loop": 0,
        "music_generation": 2,
        "sound_effect_generation": 1,
    }


class _GuidePaintoverImages:
    """A provider that paints over its guide, which is the only admitted answer.

    It used to echo the conditioning image back verbatim. That is now refused:
    the guide's colours are registration rather than artwork, so a result still
    wearing them is a painting that went around the guide instead of over it.
    """

    def __init__(self) -> None:
        self.requests: list[ImageGenerationRequest] = []

    async def generate(self, request: ImageGenerationRequest) -> SimpleNamespace:
        self.requests.append(request)
        encoded = request.input_references[0].url.split(",", 1)[1]
        data = painted_over_guide(base64.b64decode(encoded))
        assert request.validate is not None
        assert request.validate(BinaryArtifact(data=data, media_type="image/png"))
        output = Path(request.artifact_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(output.write_bytes, data)
        sidecar = _provider_sidecar(request=request, data=data)
        await asyncio.to_thread(
            Path(f"{output}.meta.json").write_text,
            json.dumps(sidecar),
            encoding="utf-8",
        )
        return SimpleNamespace(attempts=1, provenance_path=f"{output}.meta.json")


class _ThreeAttemptFailure(RuntimeError):
    attempts = 3


class _FailingImages:
    async def generate(self, _request: ImageGenerationRequest) -> SimpleNamespace:
        raise _ThreeAttemptFailure("three invalid provider candidates")


class _NodeExecutionFailingImages:
    async def generate(self, _request: ImageGenerationRequest) -> SimpleNamespace:
        raise NodeExecutionError(
            "provider execution failed after mixed work",
            attempts=3,
            provider_operations=2,
        )


class _PostCallPersistenceFailingImages:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, _request: ImageGenerationRequest) -> SimpleNamespace:
        self.calls += 1
        raise AtomicWriteError("sidecar commit failed", provider_operations=1)


class _CanceledAfterProviderImages:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, _request: ImageGenerationRequest) -> SimpleNamespace:
        self.calls += 1
        raise AbortError("cancelled in retry backoff", provider_operations=1)


class _MisregisteredLoopImages:
    def __init__(self) -> None:
        self.requests: list[ImageGenerationRequest] = []

    async def generate(self, request: ImageGenerationRequest) -> SimpleNamespace:
        self.requests.append(request)
        encoded = request.input_references[0].url.split(",", 1)[1]
        conditioning = base64.b64decode(encoded)
        with Image.open(io.BytesIO(conditioning)) as opened:
            sent = opened.convert("RGBA")
        context_span = 384
        returned = Image.new("RGBA", sent.size, (8, 12, 20, 255))
        returned.paste(sent.crop((0, 0, context_span, sent.height)), (0, 16))
        returned.paste(sent.crop((context_span, 0, sent.width, sent.height)), (context_span, 0))
        returned.putalpha(255)
        stream = io.BytesIO()
        returned.save(stream, format="PNG")
        data = stream.getvalue()
        output = Path(request.artifact_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(output.write_bytes, data)
        await asyncio.to_thread(
            Path(f"{output}.meta.json").write_text,
            json.dumps(_provider_sidecar(request=request, data=data)),
            encoding="utf-8",
        )
        return SimpleNamespace(attempts=1, provenance_path=f"{output}.meta.json")


def _opaque_nonloop_layer() -> bytes:
    image = Image.new("RGBA", (1536, 1024), (20, 40, 80, 255))
    draw = ImageDraw.Draw(image)
    for y in range(image.height):
        level = round(y * 220 / (image.height - 1))
        draw.line((0, y, image.width - 1, y), fill=(level, 48, 232 - level, 255))
    draw.rectangle((0, 0, 95, image.height - 1), fill=(230, 60, 40, 255))
    draw.rectangle(
        (image.width - 96, 0, image.width - 1, image.height - 1),
        fill=(30, 190, 220, 255),
    )
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


@pytest.mark.asyncio
async def test_guide_generate_validate_chain_uses_native_alpha_and_exact_provenance(
    tmp_path: Path,
) -> None:
    package = _select_structural_ground(two_genre_package(tmp_path / "package"))
    plan = SideviewRunnerExecutor(StageGenConfig()).plan(package)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    images = _GuidePaintoverImages()
    handler = SideviewRunnerNodeHandler(
        plan.graph,
        plan.resolved,
        run_dir=run_dir,
        cache_dir=tmp_path / "cache",
        image_service=images,  # type: ignore[arg-type]
        structured_service=object(),  # type: ignore[arg-type]
    )

    guide = plan.graph.node("track-ground-warmup_flat-guide")
    generated = plan.graph.node("track-ground-warmup_flat-generate")
    second_guide = plan.graph.node("track-ground-first_gap-guide")
    second_generated = plan.graph.node("track-ground-first_gap-generate")
    seam_bridge = plan.graph.node("track-ground-shared-seam-bridge")
    validated = plan.graph.node("track-ground-warmup_flat-validate")
    second_validated = plan.graph.node("track-ground-first_gap-validate")
    await handler._guide_structural_ground(guide)
    await handler._generate_structural_ground(generated)
    await handler._guide_structural_ground(second_guide)
    await handler._generate_structural_ground(second_generated)
    await handler._build_structural_ground_seam_bridge(seam_bridge)
    await handler._validate_structural_ground(validated)
    await handler._validate_structural_ground(second_validated)

    request = images.requests[0]
    assert request.background == "transparent"
    assert request.output_format == "png"
    assert request.size == "1536x1024"
    assert request.metadata["native_alpha"] is True
    assert request.input_references[0].provenance_ref is not None
    assert request.input_references[0].provenance_ref.startswith("run://world/ground/")
    assert request.input_references[1].provenance_ref is not None
    assert request.input_references[1].provenance_ref.startswith(
        "package://bellweather/references/cover.png#sha256="
    )

    attempts = json.loads((run_dir / "attempts/track-ground-warmup_flat-generate.json").read_text())
    assert attempts["provider_operations"] == 1
    assert attempts["output_selection"] == "provider_output"
    assert attempts["attempts"][0]["outcome"] == "selected"

    guide_meta = json.loads((run_dir / "world/ground/warmup_flat.guide.png.meta.json").read_text())
    assert guide_meta["provider"] == "local"
    cover = (package / "references/cover.png").read_bytes()
    package_cover_ref = (
        "package://bellweather/references/cover.png#sha256=" + hashlib.sha256(cover).hexdigest()
    )
    assert guide_meta["refs"] == [package_cover_ref]
    assert guide_meta["validation"]["geometry_authority"] == "authored_occupancy"

    bridge_meta = json.loads(
        (run_dir / "world/ground/shared-seam-bridge.png.meta.json").read_text()
    )
    assert bridge_meta["model"] == ("runner-structural-ground-seam-bridge-canonicalization-v2")
    assert bridge_meta["refs"] == [
        "world/ground/warmup_flat.raw.png",
        "world/ground/warmup_flat.guide.png",
        package_cover_ref,
    ]
    assert bridge_meta["validation"]["source_segment_id"] == "warmup_flat"

    canonical_meta = json.loads((run_dir / "world/ground/warmup_flat.png.meta.json").read_text())
    assert canonical_meta["model"] == "runner-structural-ground-canonicalization-v3"
    assert canonical_meta["refs"] == [
        "world/ground/warmup_flat.raw.png",
        "world/ground/warmup_flat.guide.png",
        "world/ground/shared-seam-bridge.png",
        package_cover_ref,
    ]
    validation = json.loads((run_dir / "world/ground/warmup_flat.validation.json").read_text())
    assert validation["segment_id"] == "warmup_flat"
    assert validation["seam_bridge_ref"] == "world/ground/shared-seam-bridge.png"
    assert validation["canonical"]["width"] == 24 * 64
    assert validation["canonical"]["height"] == 8 * 64
    second_meta = json.loads((run_dir / "world/ground/first_gap.png.meta.json").read_text())
    assert "world/ground/shared-seam-bridge.png" in second_meta["refs"]
    second_validation = json.loads((run_dir / "world/ground/first_gap.validation.json").read_text())
    first_seam = validation["canonical"]["seam"]
    second_seam = second_validation["canonical"]["seam"]
    assert first_seam["bridge_sha256"] == second_seam["bridge_sha256"]
    assert first_seam["left"] == second_seam["left"]
    assert first_seam["right"] == second_seam["right"]


@pytest.mark.asyncio
async def test_provider_cache_hit_preserves_the_generation_attempt_ledger(tmp_path: Path) -> None:
    package = _select_structural_ground(two_genre_package(tmp_path / "package"))
    plan = SideviewRunnerExecutor(StageGenConfig()).plan(package)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    images = _GuidePaintoverImages()
    handler = SideviewRunnerNodeHandler(
        plan.graph,
        plan.resolved,
        run_dir=run_dir,
        cache_dir=tmp_path / "cache",
        image_service=images,  # type: ignore[arg-type]
        structured_service=object(),  # type: ignore[arg-type]
    )
    guide = plan.graph.node("track-ground-warmup_flat-guide")
    generated = plan.graph.node("track-ground-warmup_flat-generate")
    guide_result = await handler._guide_structural_ground(guide)
    context = NodeExecutionContext(
        invocation_id="attempt-ledger-cache",
        graph_sha256=plan.graph.graph_sha256,
        dependency_results={guide.node_id: guide_result},
    )

    first = await handler(generated, context)
    second = await handler(generated, context)

    assert first.cache is CacheDisposition.MISS
    assert second.cache is CacheDisposition.HIT
    assert second.provider_operations == 0
    assert [(item.artifact_ref, item.sha256) for item in second.artifacts] == [
        (item.artifact_ref, item.sha256) for item in first.artifacts
    ]
    assert len(images.requests) == 1
    ledger_path = run_dir / "attempts/track-ground-warmup_flat-generate.json"
    ledger = json.loads(ledger_path.read_text())
    assert ledger["cache_hit"] is False
    assert ledger["provider_operations"] == 1
    assert [entry["outcome"] for entry in ledger["attempts"]] == ["selected"]
    ledger_ref = ledger_path.relative_to(run_dir).as_posix()
    ledger_artifact = next(item for item in second.artifacts if item.artifact_ref == ledger_ref)
    assert ledger_artifact.sha256


async def _seed_structural_provider_cache(tmp_path: Path) -> dict[str, Any]:
    package = _select_structural_ground(two_genre_package(tmp_path / "package"))
    plan = SideviewRunnerExecutor(StageGenConfig()).plan(package)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    cache_dir = tmp_path / "cache"
    images = _GuidePaintoverImages()
    handler = SideviewRunnerNodeHandler(
        plan.graph,
        plan.resolved,
        run_dir=run_dir,
        cache_dir=cache_dir,
        image_service=images,  # type: ignore[arg-type]
        structured_service=object(),  # type: ignore[arg-type]
    )
    guide = plan.graph.node("track-ground-warmup_flat-guide")
    generated = plan.graph.node("track-ground-warmup_flat-generate")
    guide_result = await handler._guide_structural_ground(guide)
    context = NodeExecutionContext(
        invocation_id="adversarial-cache",
        graph_sha256=plan.graph.graph_sha256,
        dependency_results={guide.node_id: guide_result},
    )
    result = await handler(generated, context)
    assert result.cache is CacheDisposition.MISS
    return {
        "handler": handler,
        "node": generated,
        "context": context,
        "images": images,
        "run_dir": run_dir,
        "cache_dir": cache_dir,
    }


@pytest.mark.asyncio
async def test_cache_admission_rejects_a_self_consistent_arbitrary_structural_png(
    tmp_path: Path,
) -> None:
    case = await _seed_structural_provider_cache(tmp_path)
    node = case["node"]
    run_dir = case["run_dir"]
    cache_dir = case["cache_dir"]
    assert isinstance(run_dir, Path)
    assert isinstance(cache_dir, Path)

    stream = io.BytesIO()
    Image.new("RGBA", (16, 16), (0, 0, 0, 0)).save(stream, format="PNG")
    forged = stream.getvalue()
    image_ref = node.port("image").artifact_ref
    sidecar_ref = node.port("image").sidecar_ref
    assert sidecar_ref is not None
    ledger_ref = next(port.artifact_ref for port in node.ports if port.kind == "attempt-ledger-v2")
    ledger = json.loads((run_dir / ledger_ref).read_text(encoding="utf-8"))
    ledger["attempts"][-1]["artifact_sha256"] = hashlib.sha256(forged).hexdigest()
    sidecar = json.loads((run_dir / sidecar_ref).read_text(encoding="utf-8"))
    sidecar["artifact"] = {
        "sha256": hashlib.sha256(forged).hexdigest(),
        "bytes": len(forged),
        "media_type": "image/png",
    }
    _rewrite_cached_payload(cache_dir, node, image_ref, forged)
    _rewrite_cached_payload(
        cache_dir,
        node,
        sidecar_ref,
        json.dumps(sidecar).encode(),
    )
    _rewrite_cached_payload(cache_dir, node, ledger_ref, json.dumps(ledger).encode())

    result = await case["handler"](node, case["context"])

    assert result.cache is CacheDisposition.MISS
    assert len(case["images"].requests) == 2


@pytest.mark.asyncio
async def test_cache_admission_rejects_a_self_consistent_forged_provider_prompt(
    tmp_path: Path,
) -> None:
    case = await _seed_structural_provider_cache(tmp_path)
    node = case["node"]
    run_dir = case["run_dir"]
    cache_dir = case["cache_dir"]
    assert isinstance(run_dir, Path)
    assert isinstance(cache_dir, Path)
    sidecar_ref = node.port("image").sidecar_ref
    assert sidecar_ref is not None
    forged_prompt = "A different self-consistent request."
    forged_prompt_sha256 = hashlib.sha256(forged_prompt.encode()).hexdigest()
    sidecar = json.loads((run_dir / sidecar_ref).read_text(encoding="utf-8"))
    sidecar["prompt"] = forged_prompt
    sidecar["prompt_sha256"] = forged_prompt_sha256
    ledger_ref = next(port.artifact_ref for port in node.ports if port.kind == "attempt-ledger-v2")
    ledger = json.loads((run_dir / ledger_ref).read_text(encoding="utf-8"))
    ledger["prompt_sha256"] = forged_prompt_sha256
    for attempt in ledger["attempts"]:
        attempt["prompt_sha256"] = forged_prompt_sha256
    _rewrite_cached_payload(cache_dir, node, sidecar_ref, json.dumps(sidecar).encode())
    _rewrite_cached_payload(cache_dir, node, ledger_ref, json.dumps(ledger).encode())

    result = await case["handler"](node, case["context"])

    assert result.cache is CacheDisposition.MISS
    assert len(case["images"].requests) == 2


@pytest.mark.parametrize(
    "mutation",
    [
        "refs",
        "input_digest",
        "input_order",
        "input_mime",
        "native_alpha_param",
        "seed",
        "validation",
        "component",
    ],
)
@pytest.mark.asyncio
async def test_cache_admission_rejects_forged_provider_identity_fields(
    tmp_path: Path,
    mutation: str,
) -> None:
    case = await _seed_structural_provider_cache(tmp_path)
    node = case["node"]
    run_dir = case["run_dir"]
    cache_dir = case["cache_dir"]
    assert isinstance(run_dir, Path)
    assert isinstance(cache_dir, Path)
    sidecar_ref = node.port("image").sidecar_ref
    assert sidecar_ref is not None
    sidecar = json.loads((run_dir / sidecar_ref).read_text(encoding="utf-8"))
    if mutation == "refs":
        sidecar["references"] = sidecar["references"][:-1]
        sidecar["refs"] = sidecar["refs"][:-1]
    elif mutation == "input_digest":
        sidecar["inputs"][0]["sha256"] = "0" * 64
    elif mutation == "input_order":
        sidecar["inputs"] = list(reversed(sidecar["inputs"]))
        sidecar["references"] = list(reversed(sidecar["references"]))
        sidecar["refs"] = list(reversed(sidecar["refs"]))
    elif mutation == "input_mime":
        sidecar["inputs"][0]["media_type"] = "image/webp"
    elif mutation == "native_alpha_param":
        sidecar["params"]["metadata"]["native_alpha"] = False
    elif mutation == "seed":
        sidecar["seed"] = 7
    elif mutation == "validation":
        sidecar["validation"]["caller"] = False
    elif mutation == "component":
        sidecar["component"]["name"] = "@stage-gen/untrusted-generation"
    else:
        raise AssertionError(mutation)
    _rewrite_cached_payload(cache_dir, node, sidecar_ref, json.dumps(sidecar).encode())

    result = await case["handler"](node, case["context"])

    assert result.cache is CacheDisposition.MISS
    assert len(case["images"].requests) == 2


@pytest.mark.asyncio
async def test_cache_admission_preserves_a_truthful_generated_loop_fallback(
    tmp_path: Path,
) -> None:
    package = two_genre_package(tmp_path / "package")
    track = package / "runner" / "track.toml"
    track.write_text(
        track.read_text(encoding="utf-8").replace(
            'loop_construction = "mirror_repeat"',
            'loop_construction = "generated_bridge"',
            1,
        ),
        encoding="utf-8",
    )
    plan = SideviewRunnerExecutor(StageGenConfig()).plan(package)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    images = _MisregisteredLoopImages()
    handler = SideviewRunnerNodeHandler(
        plan.graph,
        plan.resolved,
        run_dir=run_dir,
        cache_dir=tmp_path / "cache",
        image_service=images,  # type: ignore[arg-type]
        structured_service=object(),  # type: ignore[arg-type]
    )
    node = plan.graph.node("layer-meadow_sky-loop")
    source_node = plan.graph.node("layer-meadow_sky-generate")
    source_ref = source_node.port("image").artifact_ref
    source_path = run_dir / source_ref
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(_opaque_nonloop_layer())
    dependency_result = NodeExecutionResult(
        cache=CacheDisposition.MISS,
        attempts=1,
        provider_operations=1,
    )
    context = NodeExecutionContext(
        invocation_id="fallback-cache",
        graph_sha256=plan.graph.graph_sha256,
        dependency_results={source_node.node_id: dependency_result},
    )

    first = await handler(node, context)
    second = await handler(node, context)

    assert first.cache is CacheDisposition.MISS
    assert second.cache is CacheDisposition.HIT
    assert len(images.requests) == 1
    ledger = json.loads((run_dir / "attempts/layer-meadow_sky-loop.json").read_text())
    assert ledger["output_selection"] == "fallback_output"
    assert [attempt["outcome"] for attempt in ledger["attempts"]] == ["not_selected"]
    report = json.loads((run_dir / "world/layers/meadow_sky.loop.json").read_text())
    assert report["construction"] == "mirror_repeat"
    assert report["rejected_construction"] == "generated_bridge"

    edit_sidecar_ref = node.port("edit_image").sidecar_ref
    assert edit_sidecar_ref is not None
    edit_sidecar = json.loads((run_dir / edit_sidecar_ref).read_text(encoding="utf-8"))
    assert edit_sidecar["refs"][-1] == "loop-mask"
    edit_sidecar["references"] = edit_sidecar["references"][:-1]
    edit_sidecar["refs"] = edit_sidecar["refs"][:-1]
    edit_sidecar["inputs"] = edit_sidecar["inputs"][:-1]
    _rewrite_cached_payload(
        tmp_path / "cache",
        node,
        edit_sidecar_ref,
        json.dumps(edit_sidecar).encode(),
    )

    rejected = await handler(node, context)

    assert rejected.cache is CacheDisposition.MISS
    assert len(images.requests) == 2


def test_layer_fallback_attempt_ledger_does_not_select_the_edit(tmp_path: Path) -> None:
    package = two_genre_package(tmp_path / "package")
    track = package / "runner" / "track.toml"
    track.write_text(
        track.read_text().replace(
            'loop_construction = "mirror_repeat"',
            'loop_construction = "generated_bridge"',
        )
    )
    plan = SideviewRunnerExecutor(StageGenConfig()).plan(package)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    handler = SideviewRunnerNodeHandler(
        plan.graph,
        plan.resolved,
        run_dir=run_dir,
        cache_dir=tmp_path / "cache",
        image_service=object(),  # type: ignore[arg-type]
        structured_service=object(),  # type: ignore[arg-type]
    )
    node = plan.graph.node("layer-meadow_sky-loop")
    for port in node.ports:
        if port.port_id == "attempts":
            continue
        path = run_dir / port.artifact_ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"{}" if path.suffix == ".json" else b"artifact")
        if port.sidecar_ref is not None:
            sidecar = run_dir / port.sidecar_ref
            sidecar.parent.mkdir(parents=True, exist_ok=True)
            sidecar.write_text("{}")

    handler._result(
        node,
        attempts=2,
        provider_operations=2,
        provider_output_selected=False,
    )

    ledger = json.loads((run_dir / "attempts/layer-meadow_sky-loop.json").read_text())
    assert ledger["schema_version"] == 2
    assert ledger["output_selection"] == "fallback_output"
    assert [entry["outcome"] for entry in ledger["attempts"]] == [
        "not_selected",
        "not_selected",
    ]
    assert all("artifact_ref" not in entry for entry in ledger["attempts"])


@pytest.mark.asyncio
async def test_provider_exhaustion_writes_a_neutral_unselected_attempt_ledger(
    tmp_path: Path,
) -> None:
    package = _select_structural_ground(two_genre_package(tmp_path / "package"))
    plan = SideviewRunnerExecutor(StageGenConfig()).plan(package)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    handler = SideviewRunnerNodeHandler(
        plan.graph,
        plan.resolved,
        run_dir=run_dir,
        cache_dir=tmp_path / "cache",
        image_service=_FailingImages(),  # type: ignore[arg-type]
        structured_service=object(),  # type: ignore[arg-type]
    )
    guide = plan.graph.node("track-ground-warmup_flat-guide")
    generated = plan.graph.node("track-ground-warmup_flat-generate")
    guide_result = await handler._guide_structural_ground(guide)
    context = NodeExecutionContext(
        invocation_id="attempt-ledger-failure",
        graph_sha256=plan.graph.graph_sha256,
        dependency_results={guide.node_id: guide_result},
    )

    with pytest.raises(NodeExecutionError, match="three invalid provider candidates") as raised:
        await handler(generated, context)

    assert raised.value.attempts == 3
    assert raised.value.provider_operations == 3
    ledger = json.loads((run_dir / "attempts/track-ground-warmup_flat-generate.json").read_text())
    assert ledger["provider_operations"] == 3
    assert ledger["output_selection"] == "none"
    assert [entry["outcome"] for entry in ledger["attempts"]] == [
        "not_selected",
        "not_selected",
        "not_selected",
    ]


@pytest.mark.asyncio
async def test_structural_request_failure_before_service_call_records_zero_operations(
    tmp_path: Path,
) -> None:
    package = _select_structural_ground(two_genre_package(tmp_path / "package"))
    plan = SideviewRunnerExecutor(StageGenConfig()).plan(package)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    images = _GuidePaintoverImages()
    handler = SideviewRunnerNodeHandler(
        plan.graph,
        plan.resolved,
        run_dir=run_dir,
        cache_dir=tmp_path / "cache",
        image_service=images,  # type: ignore[arg-type]
        structured_service=object(),  # type: ignore[arg-type]
    )
    guide = plan.graph.node("track-ground-warmup_flat-guide")
    generated = plan.graph.node("track-ground-warmup_flat-generate")
    guide_result = await handler._guide_structural_ground(guide)
    (run_dir / guide.port("image").artifact_ref).unlink()
    context = NodeExecutionContext(
        invocation_id="pre-provider-failure",
        graph_sha256=plan.graph.graph_sha256,
        dependency_results={guide.node_id: guide_result},
    )

    with pytest.raises(NodeExecutionError) as raised:
        await handler(generated, context)

    assert raised.value.attempts == 1
    assert raised.value.provider_operations == 0
    assert images.requests == []
    ledger = json.loads((run_dir / "attempts/track-ground-warmup_flat-generate.json").read_text())
    assert ledger["provider_operations"] == 0
    assert ledger["output_selection"] == "none"
    assert ledger["attempts"] == []


@pytest.mark.asyncio
async def test_incoming_node_error_ledger_uses_provider_operations_not_attempts(
    tmp_path: Path,
) -> None:
    package = _select_structural_ground(two_genre_package(tmp_path / "package"))
    plan = SideviewRunnerExecutor(StageGenConfig()).plan(package)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    handler = SideviewRunnerNodeHandler(
        plan.graph,
        plan.resolved,
        run_dir=run_dir,
        cache_dir=tmp_path / "cache",
        image_service=_NodeExecutionFailingImages(),  # type: ignore[arg-type]
        structured_service=object(),  # type: ignore[arg-type]
    )
    guide = plan.graph.node("track-ground-warmup_flat-guide")
    generated = plan.graph.node("track-ground-warmup_flat-generate")
    guide_result = await handler._guide_structural_ground(guide)
    context = NodeExecutionContext(
        invocation_id="node-error-provider-operations",
        graph_sha256=plan.graph.graph_sha256,
        dependency_results={guide.node_id: guide_result},
    )

    with pytest.raises(NodeExecutionError) as raised:
        await handler(generated, context)

    assert raised.value.attempts == 3
    assert raised.value.provider_operations == 2
    ledger = json.loads((run_dir / "attempts/track-ground-warmup_flat-generate.json").read_text())
    assert ledger["provider_operations"] == 2
    assert [entry["outcome"] for entry in ledger["attempts"]] == [
        "not_selected",
        "not_selected",
    ]


@pytest.mark.asyncio
async def test_post_provider_persistence_failure_preserves_the_paid_operation(
    tmp_path: Path,
) -> None:
    package = _select_structural_ground(two_genre_package(tmp_path / "package"))
    plan = SideviewRunnerExecutor(StageGenConfig()).plan(package)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    images = _PostCallPersistenceFailingImages()
    handler = SideviewRunnerNodeHandler(
        plan.graph,
        plan.resolved,
        run_dir=run_dir,
        cache_dir=tmp_path / "cache",
        image_service=images,  # type: ignore[arg-type]
        structured_service=object(),  # type: ignore[arg-type]
    )
    guide = plan.graph.node("track-ground-warmup_flat-guide")
    generated = plan.graph.node("track-ground-warmup_flat-generate")
    guide_result = await handler._guide_structural_ground(guide)
    context = NodeExecutionContext(
        invocation_id="post-provider-persistence-failure",
        graph_sha256=plan.graph.graph_sha256,
        dependency_results={guide.node_id: guide_result},
    )

    with pytest.raises(NodeExecutionError) as raised:
        await handler(generated, context)

    assert images.calls == 1
    assert raised.value.provider_operations == 1
    ledger = json.loads((run_dir / "attempts/track-ground-warmup_flat-generate.json").read_text())
    assert ledger["provider_operations"] == images.calls


@pytest.mark.asyncio
async def test_cancellation_after_a_provider_attempt_preserves_the_operation_ledger(
    tmp_path: Path,
) -> None:
    package = _select_structural_ground(two_genre_package(tmp_path / "package"))
    plan = SideviewRunnerExecutor(StageGenConfig()).plan(package)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    images = _CanceledAfterProviderImages()
    handler = SideviewRunnerNodeHandler(
        plan.graph,
        plan.resolved,
        run_dir=run_dir,
        cache_dir=tmp_path / "cache",
        image_service=images,  # type: ignore[arg-type]
        structured_service=object(),  # type: ignore[arg-type]
    )
    guide = plan.graph.node("track-ground-warmup_flat-guide")
    generated = plan.graph.node("track-ground-warmup_flat-generate")
    guide_result = await handler._guide_structural_ground(guide)
    context = NodeExecutionContext(
        invocation_id="provider-cancellation",
        graph_sha256=plan.graph.graph_sha256,
        dependency_results={guide.node_id: guide_result},
    )

    with pytest.raises(AbortError):
        await handler(generated, context)

    assert images.calls == 1
    ledger = json.loads((run_dir / "attempts/track-ground-warmup_flat-generate.json").read_text())
    assert ledger["provider_operations"] == images.calls
