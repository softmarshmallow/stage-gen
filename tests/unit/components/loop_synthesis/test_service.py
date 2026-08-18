from __future__ import annotations

import asyncio
import hashlib
import json
import threading
from collections.abc import Callable, Sequence
from io import BytesIO
from pathlib import Path
from typing import Literal, cast

import pytest
from PIL import Image

from stage_gen.components._types import ProviderResponseMetadata
from stage_gen.components.loop_synthesis import (
    LoopContinuityThresholds,
    LoopSynthesisManifest,
    LoopSynthesisRequest,
    LoopSynthesisResult,
    LoopSynthesisService,
    MaskedImageEditRequest,
    ProviderLoopEdit,
)
from stage_gen.components.loop_synthesis.processing import measure_loop_continuity
from stage_gen.contracts import ArtifactRights, BinaryArtifact, ProvenanceInput
from stage_gen.recipes.scrolling_preview.manifest import write_scrolling_preview_manifest
from stage_gen.reliability import (
    AbortError,
    CancellationToken,
    RetryExhaustedError,
    RetryPolicy,
    sha256_hex,
    write_artifact_with_provenance,
)

Color = tuple[int, int, int, int]


class FakeMaskedEditBackend:
    provider = "fake-edit"
    model = "fake-mask-v1"
    capability: Literal["masked-image-edit"] = "masked-image-edit"
    secrets: tuple[str, ...] = ("provider-secret",)

    def __init__(self, outcomes: Sequence[str] = ("good",), *, mutate_bands: bool = False) -> None:
        self.outcomes = tuple(outcomes)
        self.mutate_bands = mutate_bands
        self.calls = 0
        self.requests: list[MaskedImageEditRequest] = []
        self.closed = False

    async def edit_once(self, request: MaskedImageEditRequest) -> ProviderLoopEdit:
        self.calls += 1
        self.requests.append(request)
        outcome = self.outcomes[min(self.calls - 1, len(self.outcomes) - 1)]
        if outcome == "error":
            raise RuntimeError("transient provider-secret failure")
        data = _provider_candidate(request, outcome=outcome, mutate_bands=self.mutate_bands)
        return ProviderLoopEdit(
            data=data,
            media_type="image/png",
            response_metadata=ProviderResponseMetadata(request_id=f"fake-{self.calls}"),
        )

    async def aclose(self) -> None:
        self.closed = True


class BlockingMaskedEditBackend(FakeMaskedEditBackend):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.cancelled = 0

    async def edit_once(self, request: MaskedImageEditRequest) -> ProviderLoopEdit:
        self.calls += 1
        self.requests.append(request)
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        raise AssertionError("unreachable")


@pytest.mark.asyncio
async def test_loop_synthesis_conditions_mask_reimposes_bands_and_emits_manifest(
    tmp_path: Path,
) -> None:
    source = _source_pair(tmp_path)
    backend = FakeMaskedEditBackend(mutate_bands=True)
    output_dir = tmp_path / "out"
    result = await LoopSynthesisService(
        backend,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    ).synthesize(_request(source, output_dir, metadata={"token": "provider-secret"}))

    assert backend.calls == result.attempts == 1
    captured = backend.requests[0]
    assert captured.width == 8
    assert captured.height == 3
    assert captured.metadata["algorithm"] == "endpoint-conditioned-bridge-v1"
    assert captured.metadata["token"] == "[REDACTED]"
    conditioning = _decode(captured.conditioning_image)
    mask = _decode(captured.mask_image).convert("L")
    source_image = _decode(source.read_bytes()).convert("RGBA")
    assert conditioning.crop((0, 0, 2, 3)).tobytes() == source_image.crop((4, 0, 6, 3)).tobytes()
    assert conditioning.crop((6, 0, 8, 3)).tobytes() == source_image.crop((0, 0, 2, 3)).tobytes()
    assert set(mask.crop((0, 0, 2, 3)).tobytes()) == {0}
    assert set(mask.crop((2, 0, 6, 3)).tobytes()) == {255}
    assert set(mask.crop((6, 0, 8, 3)).tobytes()) == {0}

    repeat = _decode(await _read_bytes(result.artifact_path)).convert("RGBA")
    assert repeat.size == (10, 3)
    assert repeat.crop((0, 0, 6, 3)).tobytes() == source_image.tobytes()
    sidecar_text = await _read_text(result.provenance_path)
    sidecar = json.loads(sidecar_text)
    assert sidecar["validation"]["immutable_bands_reimposed"] is True
    assert sidecar["validation"]["provider_band_changed_pixels"] == 12
    assert sidecar["validation"]["seam_thresholds_passed"] is True
    assert sidecar["rights"]["status"] == "unreviewed"
    assert "provider-secret" not in sidecar_text

    manifest = LoopSynthesisManifest.model_validate_json(await _read_text(result.manifest_path))
    assert manifest.algorithm == "endpoint-conditioned-bridge-v1"
    assert manifest.period_px == 10
    assert manifest.source_width_px == 6
    assert manifest.bridge_width_px == 4
    assert manifest.immutable_bands_reimposed is True
    assert manifest.repeat_unit.sha256 == sha256_hex(result.data)
    assert manifest.metrics == result.metrics


@pytest.mark.asyncio
async def test_caller_metadata_cannot_spoof_trusted_provider_contract_fields(
    tmp_path: Path,
) -> None:
    source = _source_pair(tmp_path)
    backend = FakeMaskedEditBackend()
    result = await LoopSynthesisService(
        backend,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    ).synthesize(
        _request(
            source,
            tmp_path / "out",
            metadata={
                "algorithm": "caller-spoof",
                "mask_semantics": "caller-spoof",
                "conditioning_sha256": "0" * 64,
                "mask_sha256": "0" * 64,
            },
        )
    )

    captured = backend.requests[0]
    assert captured.metadata["algorithm"] == "endpoint-conditioned-bridge-v1"
    assert captured.metadata["mask_semantics"] == "white-edit-black-preserve"
    assert (
        captured.metadata["conditioning_sha256"]
        == hashlib.sha256(captured.conditioning_image).hexdigest()
    )
    assert captured.metadata["mask_sha256"] == hashlib.sha256(captured.mask_image).hexdigest()

    sidecar = json.loads(await _read_text(result.provenance_path))
    assert sidecar["params"]["algorithm"] == "endpoint-conditioned-bridge-v1"
    assert sidecar["params"]["mask_semantics"] == "white-edit-black-preserve"


@pytest.mark.asyncio
async def test_loop_synthesis_retries_provider_and_seam_failures(tmp_path: Path) -> None:
    source = _source_pair(tmp_path)
    backend = FakeMaskedEditBackend(("error", "bad", "good"))
    output_dir = tmp_path / "out"
    result = await LoopSynthesisService(
        backend,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    ).synthesize(_request(source, output_dir))

    assert backend.calls == result.attempts == 3
    sidecar_text = await _read_text(result.provenance_path)
    sidecar = json.loads(sidecar_text)
    assert sidecar["attempts"] == 3
    assert sidecar["retries"] == 2
    assert "provider-secret" not in sidecar_text


@pytest.mark.asyncio
async def test_loop_synthesis_exhausts_rejected_seams_without_success_marker(
    tmp_path: Path,
) -> None:
    source = _source_pair(tmp_path)
    backend = FakeMaskedEditBackend(("bad",))
    output_dir = tmp_path / "out"
    with pytest.raises(RetryExhaustedError, match="loop candidate rejected") as captured:
        await LoopSynthesisService(
            backend,
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        ).synthesize(_request(source, output_dir))

    assert backend.calls == captured.value.attempts == 6
    assert not (output_dir / "layer.loop.png").exists()
    assert not (output_dir / "layer.loop.json").exists()


@pytest.mark.asyncio
async def test_loop_synthesis_cancellation_stops_active_provider_and_writes_nothing(
    tmp_path: Path,
) -> None:
    source = _source_pair(tmp_path)
    backend = BlockingMaskedEditBackend()
    cancellation = CancellationToken()
    output_dir = tmp_path / "out"
    task = asyncio.create_task(
        LoopSynthesisService(
            backend,
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        ).synthesize(_request(source, output_dir, cancellation=cancellation))
    )
    await asyncio.wait_for(backend.started.wait(), timeout=1)
    cancellation.cancel("caller stopped")
    with pytest.raises(AbortError, match="caller stopped"):
        await asyncio.wait_for(task, timeout=1)

    assert backend.calls == backend.cancelled == 1
    assert not (output_dir / "layer.loop.png").exists()
    assert not (output_dir / "layer.loop.json").exists()


@pytest.mark.asyncio
async def test_loop_rights_require_explicit_review_and_never_broaden_source(
    tmp_path: Path,
) -> None:
    approved = _approved_rights()
    source = _source_pair(tmp_path, rights=approved)
    output_dir = tmp_path / "default"
    result = await LoopSynthesisService(
        FakeMaskedEditBackend(),
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    ).synthesize(_request(source, output_dir))
    sidecar = json.loads(await _read_text(result.provenance_path))
    assert sidecar["rights"]["status"] == "unreviewed"

    reviewed_dir = tmp_path / "reviewed"
    reviewed = await LoopSynthesisService(
        FakeMaskedEditBackend(),
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    ).synthesize(_request(source, reviewed_dir, output_rights=approved))
    reviewed_sidecar = json.loads(await _read_text(reviewed.provenance_path))
    assert reviewed_sidecar["rights"] == approved.model_dump(mode="json")

    unreviewed_source = _source_pair(tmp_path / "unreviewed")
    refusing_backend = FakeMaskedEditBackend()
    with pytest.raises(ValueError, match="requires an approved source"):
        await LoopSynthesisService(refusing_backend).synthesize(
            _request(unreviewed_source, tmp_path / "refused", output_rights=approved)
        )
    assert refusing_backend.calls == 0


@pytest.mark.asyncio
async def test_loop_rejects_unsafe_paths_symlinks_large_dimensions_and_digest_mismatch(
    tmp_path: Path,
) -> None:
    source = _source_pair(tmp_path)
    with pytest.raises(ValueError, match="safe path segment"):
        _request(source, tmp_path / "out", artifact_name="../escape.png")

    symlink = tmp_path / "source-link.png"
    symlink.symlink_to(source)
    with pytest.raises(ValueError, match="regular non-symlink"):
        await LoopSynthesisService(FakeMaskedEditBackend()).synthesize(
            _request(
                symlink,
                tmp_path / "symlink-out",
                source_provenance_path=Path(f"{source}.meta.json"),
            )
        )

    large = _source_pair(tmp_path / "large", size=(8193, 1))
    dimension_backend = FakeMaskedEditBackend()
    with pytest.raises(ValueError, match="must not exceed 8192px"):
        await LoopSynthesisService(dimension_backend).synthesize(
            _request(large, tmp_path / "large-out", context_band_px=2)
        )
    assert dimension_backend.calls == 0

    mismatch = _source_pair(tmp_path / "mismatch")
    mismatch.write_bytes(_png_from_columns([(1, 2, 3, 255), (1, 2, 3, 255)]))
    digest_backend = FakeMaskedEditBackend()
    with pytest.raises(ValueError, match="do not match provenance digest"):
        await LoopSynthesisService(digest_backend).synthesize(
            _request(mismatch, tmp_path / "mismatch-out", context_band_px=2)
        )
    assert digest_backend.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("artifact_name", "manifest_name"),
    [
        ("layer.loop.png", "layer.loop.png.meta.json"),
        ("Layer.loop.png", "layer.loop.png.meta.json"),
    ],
)
async def test_loop_rejects_exact_and_casefolded_output_aliases_before_provider_call(
    tmp_path: Path,
    artifact_name: str,
    manifest_name: str,
) -> None:
    source = _source_pair(tmp_path)
    backend = FakeMaskedEditBackend()
    request = _request(source, tmp_path / "out")
    # Preserve a defense-in-depth regression for callers that bypass the
    # frozen request constructor (for example, corrupted deserialization).
    object.__setattr__(request, "artifact_name", artifact_name)
    object.__setattr__(request, "manifest_name", manifest_name)
    with pytest.raises(ValueError, match="targets must be distinct"):
        await LoopSynthesisService(backend).synthesize(request)
    assert backend.calls == 0
    assert await asyncio.to_thread(lambda: list((tmp_path / "out").iterdir())) == []


@pytest.mark.asyncio
async def test_manifest_name_requires_exact_loop_json_suffix_before_provider_call(
    tmp_path: Path,
) -> None:
    source = _source_pair(tmp_path)
    backend = FakeMaskedEditBackend()
    with pytest.raises(ValueError, match=r"exact \.loop\.json suffix"):
        await LoopSynthesisService(backend).synthesize(
            _request(source, tmp_path / "invalid", manifest_name="layer.json")
        )
    assert backend.calls == 0

    result = await LoopSynthesisService(
        backend,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    ).synthesize(_request(source, tmp_path / "valid", manifest_name="layer.loop.json"))
    assert backend.calls == 1
    assert Path(result.manifest_path).name == "layer.loop.json"


@pytest.mark.asyncio
async def test_backend_labels_reject_secrets_and_urls_and_are_frozen_after_validation(
    tmp_path: Path,
) -> None:
    source = _source_pair(tmp_path)
    secret_backend = FakeMaskedEditBackend()
    secret_backend.model = "provider-secret"
    with pytest.raises(ValueError) as secret_error:
        LoopSynthesisService(secret_backend)
    assert "provider-secret" not in str(secret_error.value)

    url_backend = FakeMaskedEditBackend()
    url_backend.provider = "https://provider-secret.example/edit"
    with pytest.raises(ValueError) as url_error:
        LoopSynthesisService(url_backend)
    assert "provider-secret" not in str(url_error.value)
    assert "https://" not in str(url_error.value)

    dynamic_backend = FakeMaskedEditBackend()
    service = LoopSynthesisService(
        dynamic_backend,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    dynamic_backend.provider = "https://provider-secret.example/changed"
    dynamic_backend.model = "provider-secret"
    result = await service.synthesize(_request(source, tmp_path / "frozen"))
    manifest_text = await _read_text(result.manifest_path)
    assert result.provider == "fake-edit"
    assert result.model == "fake-mask-v1"
    assert "provider-secret" not in manifest_text
    assert "https://" not in manifest_text


@pytest.mark.asyncio
async def test_distribution_gate_rejects_localized_full_contrast_seam_then_accepts_valid(
    tmp_path: Path,
) -> None:
    source = _source_pair(tmp_path, size=(6, 10))
    backend = FakeMaskedEditBackend(("localized", "good"))
    request = _request(
        source,
        tmp_path / "out",
        thresholds=LoopContinuityThresholds(),
    )
    result = await LoopSynthesisService(
        backend,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    ).synthesize(request)
    assert result.attempts == backend.calls == 2

    localized = _decode(
        _provider_candidate(
            backend.requests[0],
            outcome="localized",
            mutate_bands=False,
        )
    )
    source_image = _decode(await _read_bytes(source)).convert("RGBA")
    bridge = localized.crop((2, 0, 6, 10))
    metrics = measure_loop_continuity(source_image, bridge).source_to_bridge
    assert metrics.pixel_mae < request.thresholds.pixel_mae
    assert metrics.pixel_max > request.thresholds.pixel_max


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "checkpoint",
    [
        "staged:artifact",
        "staged:artifact-provenance",
        "staged:manifest",
        "staged:manifest-provenance",
        "installed:artifact",
        "installed:artifact-provenance",
        "installed:manifest",
        "installed:manifest-provenance",
        "synced",
    ],
)
async def test_cancellation_at_every_persistence_checkpoint_rolls_back_all_outputs(
    tmp_path: Path,
    checkpoint: str,
) -> None:
    source = _source_pair(tmp_path)
    cancellation = CancellationToken()
    loop = asyncio.get_running_loop()

    def cancel_at(name: str) -> None:
        if name != checkpoint:
            return
        acknowledged = threading.Event()

        def cancel() -> None:
            cancellation.cancel(f"cancel at {checkpoint}")
            acknowledged.set()

        loop.call_soon_threadsafe(cancel)
        assert acknowledged.wait(timeout=2)

    output_dir = tmp_path / "out"
    with pytest.raises(AbortError, match="cancel at"):
        await LoopSynthesisService(
            FakeMaskedEditBackend(),
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
            persistence_checkpoint=cancel_at,
        ).synthesize(_request(source, output_dir, cancellation=cancellation))
    assert await _directory_names(output_dir) == []


@pytest.mark.asyncio
async def test_task_cancellation_during_persistence_rolls_back_all_outputs(tmp_path: Path) -> None:
    source = _source_pair(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    def block_after_artifact(name: str) -> None:
        if name == "installed:artifact":
            entered.set()
            assert release.wait(timeout=2)

    output_dir = tmp_path / "out"
    task = asyncio.create_task(
        LoopSynthesisService(
            FakeMaskedEditBackend(),
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
            persistence_checkpoint=block_after_artifact,
        ).synthesize(_request(source, output_dir))
    )
    assert await asyncio.to_thread(entered.wait, 2)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await _directory_names(output_dir) == []


@pytest.mark.asyncio
async def test_scrolling_manifest_declares_default_off_and_collects_verified_loop_artifacts(
    tmp_path: Path,
) -> None:
    deferred_result = await write_scrolling_preview_manifest(
        run_dir=tmp_path / "deferred",
        tag="deferred-ai",
    )
    deferred = json.loads(await _read_text(deferred_result.manifest_path))
    assert deferred["loopSynthesis"] == {
        "enabled": False,
        "status": "deferred",
        "axis": "x",
        "algorithm": "endpoint-conditioned-bridge-v1",
        "requiresCapability": "masked-image-edit",
        "artifacts": [],
    }

    run_dir = tmp_path / "available"
    source = _source_pair(run_dir)
    generated = await LoopSynthesisService(
        FakeMaskedEditBackend(),
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    ).synthesize(_request(source, run_dir))
    available_result = await write_scrolling_preview_manifest(
        run_dir=run_dir,
        tag="available-ai",
    )
    available = json.loads(await _read_text(available_result.manifest_path))
    assert available["loopSynthesis"]["enabled"] is True
    assert available["loopSynthesis"]["status"] == "available"
    assert available["loopSynthesis"]["artifacts"][0]["periodPx"] == 10
    canonical_paths = {entry["path"] for entry in available["canonicalArtifacts"]}
    assert Path(generated.artifact_path).name not in canonical_paths
    assert source.name in canonical_paths


@pytest.mark.asyncio
async def test_scrolling_manifest_rejects_resigned_loop_geometry_claims(tmp_path: Path) -> None:
    run_dir, generated = await _generated_loop_run(tmp_path)
    manifest_path = Path(generated.manifest_path)

    def mutate(record: dict[str, object]) -> None:
        source = cast(dict[str, object], record["source"])
        repeat = cast(dict[str, object], record["repeatUnit"])
        source["width"] = 7
        record["sourceWidthPx"] = 7
        repeat["width"] = 11
        record["periodPx"] = 11

    await _mutate_json_and_rebind(manifest_path, mutate)
    with pytest.raises(ValueError, match="decoded geometry or lineage mismatch"):
        await write_scrolling_preview_manifest(run_dir=run_dir, tag="resigned-geometry")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "lineage_field",
    [
        "sourceSha256",
        "leftContextSha256",
        "rightContextSha256",
        "conditioningSha256",
        "maskSha256",
        "bridgeSha256",
        "repeatUnitSha256",
    ],
)
async def test_scrolling_manifest_rejects_resigned_loop_lineage_claims(
    tmp_path: Path,
    lineage_field: str,
) -> None:
    run_dir, generated = await _generated_loop_run(tmp_path)
    manifest_path = Path(generated.manifest_path)

    def mutate(record: dict[str, object]) -> None:
        lineage = cast(dict[str, object], record["lineage"])
        lineage[lineage_field] = "0" * 64
        if lineage_field == "sourceSha256":
            cast(dict[str, object], record["source"])["sha256"] = "0" * 64
        elif lineage_field == "repeatUnitSha256":
            cast(dict[str, object], record["repeatUnit"])["sha256"] = "0" * 64

    await _mutate_json_and_rebind(manifest_path, mutate)
    with pytest.raises(ValueError, match=r"binding mismatch|lineage mismatch"):
        await write_scrolling_preview_manifest(run_dir=run_dir, tag="resigned-lineage")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sidecar_role", "field"),
    [
        ("repeat", "component"),
        ("repeat", "input"),
        ("manifest", "component"),
        ("manifest", "input"),
    ],
)
async def test_scrolling_manifest_rejects_resigned_provenance_lineage(
    tmp_path: Path,
    sidecar_role: str,
    field: str,
) -> None:
    run_dir, generated = await _generated_loop_run(tmp_path)
    sidecar_path = Path(
        generated.provenance_path
        if sidecar_role == "repeat"
        else generated.manifest_provenance_path
    )

    def mutate(record: dict[str, object]) -> None:
        if field == "component":
            cast(dict[str, object], record["component"])["name"] = "attacker/re-signer"
            return
        inputs = cast(list[dict[str, object]], record["inputs"])
        inputs[0]["ref"] = "attacker-rebound.png"

    await _mutate_json(sidecar_path, mutate)
    with pytest.raises(ValueError, match="provenance lineage mismatch"):
        await write_scrolling_preview_manifest(run_dir=run_dir, tag="resigned-provenance")


def _request(
    source: Path,
    output_dir: Path,
    *,
    artifact_name: str = "layer.loop.png",
    manifest_name: str = "layer.loop.json",
    source_provenance_path: Path | None = None,
    context_band_px: int = 2,
    bridge_width_px: int = 4,
    metadata: dict[str, object] | None = None,
    output_rights: ArtifactRights | None = None,
    cancellation: CancellationToken | None = None,
    thresholds: LoopContinuityThresholds | None = None,
) -> LoopSynthesisRequest:
    return LoopSynthesisRequest(
        source_path=source,
        source_provenance_path=source_provenance_path,
        source_ref=source.name,
        output_dir=output_dir,
        artifact_name=artifact_name,
        manifest_name=manifest_name,
        prompt="continue the original terrain structures between both supplied endpoints",
        context_band_px=context_band_px,
        bridge_width_px=bridge_width_px,
        thresholds=thresholds
        or LoopContinuityThresholds(
            pixel_mae=8,
            gradient_mae=12,
            perceptual_delta_e=8,
        ),
        metadata=metadata or {},
        output_rights=output_rights,
        cancellation=cancellation,
    )


def _source_pair(
    root: Path,
    *,
    size: tuple[int, int] = (6, 3),
    rights: ArtifactRights | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    source = root / "layer.png"
    if size == (6, 3):
        data = _png_from_columns(
            [
                (200, 20, 20, 255),
                (200, 20, 20, 255),
                (30, 160, 70, 255),
                (30, 160, 70, 255),
                (20, 40, 210, 255),
                (20, 40, 210, 255),
            ],
            height=3,
        )
    else:
        data = _png(Image.new("RGBA", size, (40, 50, 60, 255)))
    write_artifact_with_provenance(
        source,
        BinaryArtifact(data=data, media_type="image/png"),
        ProvenanceInput(
            provider="local",
            model="test-fixture",
            prompt="construct deterministic source strip",
            refs=[],
            params={"metadata": {"stage": "concept", "opaque": True}},
            attempts=1,
            rights=rights,
        ),
    )
    return source


def _approved_rights() -> ArtifactRights:
    return ArtifactRights(
        status="redistribution-approved",
        license_id="LicenseRef-Synthetic-Test",
        notice="Synthetic test fixture.",
        attribution=[],
        basis=["sha256:" + "a" * 64],
        reviewed_at="2026-08-17T00:00:00Z",
    )


def _provider_candidate(
    request: MaskedImageEditRequest,
    *,
    outcome: str,
    mutate_bands: bool,
) -> bytes:
    image = _decode(request.conditioning_image).convert("RGBA")
    pixels = image.load()
    assert pixels is not None
    left_x = request.context_band_px - 1
    right_x = request.context_band_px + request.bridge_width_px
    for y in range(request.height):
        left = cast(Color, pixels[left_x, y])
        right = cast(Color, pixels[right_x, y])
        for offset in range(request.bridge_width_px):
            x = request.context_band_px + offset
            if outcome in {"good", "localized"}:
                amount = min(
                    1.0,
                    max(0.0, (offset - 1) / max(1, request.bridge_width_px - 3)),
                )
                pixels[x, y] = tuple(
                    round(left[channel] * (1 - amount) + right[channel] * amount)
                    for channel in range(4)
                )
            else:
                pixels[x, y] = (255, 0, 255, 255)
    if outcome == "localized":
        for y in range(max(1, request.height // 10)):
            pixels[request.context_band_px, y] = (255, 255, 255, 255)
    if mutate_bands:
        for y in range(request.height):
            for x in (*range(request.context_band_px), *range(right_x, request.width)):
                pixels[x, y] = (250, 240, 10, 255)
    return _png(image)


def _png_from_columns(columns: Sequence[Color], *, height: int = 1) -> bytes:
    image = Image.new("RGBA", (len(columns), height))
    pixels = image.load()
    assert pixels is not None
    for x, color in enumerate(columns):
        for y in range(height):
            pixels[x, y] = color
    return _png(image)


def _png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", compress_level=9, optimize=False)
    return output.getvalue()


def _decode(data: bytes) -> Image.Image:
    with Image.open(BytesIO(data)) as image:
        image.load()
        return image.copy()


async def _read_bytes(path: str | Path) -> bytes:
    return await asyncio.to_thread(Path(path).read_bytes)


async def _read_text(path: str | Path) -> str:
    return await asyncio.to_thread(Path(path).read_text, encoding="utf-8")


async def _directory_names(path: Path) -> list[str]:
    if not await asyncio.to_thread(path.exists):
        return []
    return await asyncio.to_thread(lambda: sorted(item.name for item in path.iterdir()))


async def _generated_loop_run(tmp_path: Path) -> tuple[Path, LoopSynthesisResult]:
    run_dir = tmp_path / "run"
    source = _source_pair(run_dir)
    generated = await LoopSynthesisService(
        FakeMaskedEditBackend(),
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    ).synthesize(_request(source, run_dir))
    return run_dir, generated


async def _mutate_json_and_rebind(
    artifact_path: Path,
    mutate: Callable[[dict[str, object]], None],
) -> None:
    await _mutate_json(artifact_path, mutate)
    artifact_data = await _read_bytes(artifact_path)
    sidecar_path = Path(f"{artifact_path}.meta.json")

    def rebind(record: dict[str, object]) -> None:
        record["artifact"] = {
            "sha256": hashlib.sha256(artifact_data).hexdigest(),
            "bytes": len(artifact_data),
            "media_type": "application/json",
        }

    await _mutate_json(sidecar_path, rebind)


async def _mutate_json(path: Path, mutate: Callable[[dict[str, object]], None]) -> None:
    record = cast(dict[str, object], json.loads(await _read_text(path)))
    mutate(record)
    payload = (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode()
    await asyncio.to_thread(path.write_bytes, payload)
