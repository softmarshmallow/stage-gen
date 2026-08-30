from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Literal, cast

import pytest
from PIL import Image

import stage_gen.recipes.scrolling_preview.manifest as scrolling_manifest
from gnode import BinaryArtifact, ProvenanceInput, RetryPolicy, write_artifact_with_provenance
from stage_gen.components._types import ProviderResponseMetadata
from stage_gen.components.image_repeat import (
    INTENDED_LOOP_REVIEW_PROMPT_VERSION,
    THREE_REPEAT_PREVIEW_VERSION,
    ImageRepeatAdmissionRequest,
    ImageRepeatManifest,
    ImageRepeatRepairRequest,
    ImageRepeatResult,
    ImageRepeatService,
    ImageRepeatValidationPolicy,
    MaskedImageEditRequest,
    ProviderImageRepeatEdit,
    canonical_intended_loop_criteria,
)
from stage_gen.components.structured_generation import (
    ProviderStructuredOutput,
    StructuredGenerationRequest,
    StructuredGenerationService,
)
from stage_gen.orchestration.image_repeat_reviewer import StructuredIntendedLoopReviewer
from stage_gen.recipes.scrolling_preview.manifest import write_scrolling_preview_manifest


class _AcceptingStructuredBackend:
    provider = "independent-reviewer"
    model = "vision-review-v1"
    secrets: tuple[str, ...] = ()

    async def generate_once(
        self,
        request: StructuredGenerationRequest[object],
    ) -> ProviderStructuredOutput:
        del request
        decoded = {
            "verdict": "accept",
            "confidence": 0.96,
            "failure_codes": [],
            "evidence": "Both joins continue naturally and cadence is not conspicuous.",
        }
        return ProviderStructuredOutput(
            decoded=decoded,
            raw_text=json.dumps(decoded),
            response_metadata=ProviderResponseMetadata(request_id="review-1"),
        )

    async def aclose(self) -> None:
        return None


class _PassingRepairBackend:
    provider = "independent-repair"
    model = "endpoint-fill-v1"
    capability: Literal["masked-image-edit"] = "masked-image-edit"
    secrets: tuple[str, ...] = ()

    async def edit_once(self, request: MaskedImageEditRequest) -> ProviderImageRepeatEdit:
        with Image.open(BytesIO(request.conditioning_image)) as decoded:
            conditioned = decoded.convert("RGBA")
        with Image.open(BytesIO(request.mask_image)) as decoded_mask:
            mask = decoded_mask.convert("L")
        for y in range(conditioned.height):
            for x in range(conditioned.width):
                if cast(int, mask.getpixel((x, y))) <= 0:
                    continue
                repair_offset = x - request.context_span_px
                color = (
                    (255, 0, 255, 255)
                    if repair_offset in {0, request.repair_span_px - 1}
                    else (200, 20, 20, 255)
                )
                conditioned.putpixel((x, y), color)
        return ProviderImageRepeatEdit(data=_png(conditioned), media_type="image/png")

    async def aclose(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _isolate_expanded_runtime_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        scrolling_manifest,
        "_collect_runtime_assets",
        lambda _run_dir, tag, *_args: (
            [],
            {
                "path": f"world_spec_{tag}.json",
                "provenancePath": f"world_spec_{tag}.json.meta.json",
            },
        ),
    )


@pytest.mark.asyncio
async def test_manifest_defaults_off_and_collects_verified_image_repeat(tmp_path: Path) -> None:
    deferred_result = await write_scrolling_preview_manifest(
        run_dir=tmp_path / "deferred",
        tag="deferred-ai",
    )
    deferred = json.loads(await _read_text(deferred_result.manifest_path))
    assert deferred["image_repeat"] == {
        "enabled": False,
        "status": "deferred",
        "artifacts": [],
    }

    run_dir, generated = await _generated_image_repeat_run(tmp_path)
    available_result = await write_scrolling_preview_manifest(
        run_dir=run_dir,
        tag="available-ai",
    )
    available = json.loads(await _read_text(available_result.manifest_path))
    assert available["image_repeat"]["enabled"] is True
    assert available["image_repeat"]["status"] == "available"
    artifact = available["image_repeat"]["artifacts"][0]
    assert artifact["decision"] == "admitted"
    assert artifact["axis"] == "x"
    assert artifact["period_px"] == 6
    canonical_paths = {entry["path"] for entry in available["canonical_artifacts"]}
    assert Path(generated.artifact_path).name not in canonical_paths
    assert "layer.png" in canonical_paths


@pytest.mark.asyncio
async def test_manifest_rejects_resigned_image_repeat_geometry(tmp_path: Path) -> None:
    run_dir, generated = await _generated_image_repeat_run(tmp_path)
    manifest_path = Path(generated.manifest_path)

    def mutate(record: dict[str, object]) -> None:
        cast(dict[str, object], record["source"])["width"] = 7
        cast(dict[str, object], record["repeat_unit"])["width"] = 7
        record["period_px"] = 7

    await _mutate_json_and_rebind(manifest_path, mutate)
    with pytest.raises(ValueError, match="image-repeat artifact binding mismatch"):
        await write_scrolling_preview_manifest(run_dir=run_dir, tag="resigned-geometry")


@pytest.mark.asyncio
async def test_manifest_rejects_resigned_legacy_semantic_preview_contract(
    tmp_path: Path,
) -> None:
    run_dir, generated = await _generated_image_repeat_run(tmp_path)
    manifest_path = Path(generated.manifest_path)
    manifest = ImageRepeatManifest.model_validate_json(await _read_text(manifest_path))
    criteria = json.loads(
        canonical_intended_loop_criteria(
            axis=manifest.axis,
            intended_behavior=manifest.intent.intended_behavior,
            alpha_policy=manifest.intent.alpha_policy,
            coverage_policy=manifest.intent.coverage_policy,
            validation_policy=manifest.validation.policy,
        )
    )
    assert criteria["preview_version"] == THREE_REPEAT_PREVIEW_VERSION
    assert criteria["prompt_version"] == INTENDED_LOOP_REVIEW_PROMPT_VERSION
    criteria["preview_version"] = "exact-three-repeat-v1"
    criteria["prompt_version"] = "intended-loop-rubric-v2"
    legacy_digest = hashlib.sha256(
        json.dumps(
            criteria,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()

    def mutate(record: dict[str, object]) -> None:
        cast(dict[str, object], record["intent"])["criteria_sha256"] = legacy_digest
        validation = cast(dict[str, object], record["validation"])
        cast(dict[str, object], validation["intended_loop"])["criteria_sha256"] = legacy_digest

    await _mutate_json_and_rebind(manifest_path, mutate)
    with pytest.raises(ValueError, match="image-repeat media derivation is invalid"):
        await write_scrolling_preview_manifest(
            run_dir=run_dir,
            tag="resigned-legacy-preview",
        )


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
async def test_manifest_rejects_resigned_image_repeat_provenance_lineage(
    tmp_path: Path,
    sidecar_role: str,
    field: str,
) -> None:
    run_dir, generated = await _generated_image_repeat_run(tmp_path)
    sidecar_path = Path(
        generated.provenance_path
        if sidecar_role == "repeat"
        else generated.manifest_provenance_path
    )

    def mutate(record: dict[str, object]) -> None:
        if field == "component":
            cast(dict[str, object], record["component"])["name"] = "attacker/re-signer"
            return
        cast(list[dict[str, object]], record["inputs"])[0]["ref"] = "attacker-rebound.png"

    await _mutate_json(sidecar_path, mutate)
    with pytest.raises(
        ValueError,
        match=r"image-repeat (?:output|manifest) provenance mismatch",
    ):
        await write_scrolling_preview_manifest(run_dir=run_dir, tag="resigned-provenance")


@pytest.mark.asyncio
async def test_manifest_reconstructs_and_rejects_resigned_repair_lineage(
    tmp_path: Path,
) -> None:
    run_dir, generated = await _generated_repaired_image_repeat_run(tmp_path)
    available_result = await write_scrolling_preview_manifest(
        run_dir=run_dir,
        tag="available-repaired-ai",
    )
    available = json.loads(await _read_text(available_result.manifest_path))
    artifact = available["image_repeat"]["artifacts"][0]
    assert artifact["decision"] == "repaired"
    construction = cast(dict[str, object], artifact["construction"])
    candidate = cast(dict[str, object], construction["provider_candidate"])
    candidate_name = cast(str, candidate["path"])
    assert construction["algorithm"] == "endpoint-alpha-reconstructed-anchored-repair-v4"
    assert construction["endpoint_anchor_algorithm"] == ("linear-light-premultiplied-smoothstep-v1")
    assert construction["endpoint_anchor_span_px"] == 1
    assert construction["endpoint_anchors_reimposed"] is True
    assert construction["alpha_reconstruction_algorithm"] == ("source-endpoint-alpha-smoothstep-v1")
    assert construction["alpha_topology_reconstructed"] is True
    assert construction["provider_rgb_interior_preserved"] is True
    assert construction["deterministically_reconstructible"] is True
    lineage = cast(dict[str, object], artifact["lineage"])
    assert len(cast(str, lineage["alpha_reconstructed_repair_sha256"])) == 64
    repeat_provenance_record = cast(
        dict[str, object],
        json.loads(await _read_text(generated.provenance_path)),
    )
    repeat_validation = cast(dict[str, object], repeat_provenance_record["validation"])
    assert cast(int, repeat_validation["alpha_reconstructed_changed_pixels"]) > 0
    assert candidate_name not in {entry["path"] for entry in available["canonical_artifacts"]}
    assert candidate_name not in {entry["path"] for entry in available["runtime_assets"]}

    manifest_path = Path(generated.manifest_path)
    manifest_record = cast(dict[str, object], json.loads(await _read_text(manifest_path)))
    forged_lineage = cast(dict[str, object], manifest_record["lineage"])
    forged_lineage.update(
        {
            "head_context_sha256": "a" * 64,
            "tail_context_sha256": "b" * 64,
            "conditioning_sha256": "c" * 64,
            "mask_sha256": "d" * 64,
            "raw_repair_sha256": "e" * 64,
            "provider_interior_sha256": "0" * 64,
            "alpha_reconstructed_repair_sha256": "2" * 64,
            "repair_sha256": "1" * 64,
        }
    )
    manifest_bytes = (json.dumps(manifest_record, indent=2, ensure_ascii=False) + "\n").encode()
    await asyncio.to_thread(manifest_path.write_bytes, manifest_bytes)

    repeat_provenance = Path(generated.provenance_path)

    def rebind_repeat(record: dict[str, object]) -> None:
        cast(dict[str, object], record["params"])["lineage"] = forged_lineage

    await _mutate_json(repeat_provenance, rebind_repeat)

    manifest_provenance = Path(generated.manifest_provenance_path)

    def rebind_manifest(record: dict[str, object]) -> None:
        cast(dict[str, object], record["params"])["lineage"] = forged_lineage
        record["artifact"] = {
            "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "bytes": len(manifest_bytes),
            "media_type": "application/json",
        }

    await _mutate_json(manifest_provenance, rebind_manifest)

    with pytest.raises(ValueError, match="image-repeat media derivation is invalid"):
        await write_scrolling_preview_manifest(run_dir=run_dir, tag="forged-repair-lineage")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("algorithm", "endpoint-conditioned-anchored-repair-v3"),
        ("alpha_reconstruction_algorithm", "provider-alpha-v0"),
        ("alpha_topology_reconstructed", False),
        ("provider_rgb_interior_preserved", False),
        ("deterministically_reconstructible", False),
        ("alpha_reconstruction_algorithm", None),
    ],
)
async def test_manifest_rejects_invalid_repair_alpha_ownership_contract(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    run_dir, generated = await _generated_repaired_image_repeat_run(tmp_path)
    manifest_path = Path(generated.manifest_path)

    def mutate(record: dict[str, object]) -> None:
        construction = cast(dict[str, object], record["construction"])
        if value is None:
            construction.pop(field)
        else:
            construction[field] = value

    await _mutate_json_and_rebind(manifest_path, mutate)
    with pytest.raises(ValueError, match="image-repeat manifest is invalid"):
        await write_scrolling_preview_manifest(
            run_dir=run_dir,
            tag=f"invalid-alpha-ownership-{field}",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tamper",
    [
        "context_span",
        "conditioning_input",
        "endpoint_anchor_algorithm",
        "endpoint_anchor_span",
        "endpoint_anchor_validation",
        "alpha_reconstruction_algorithm",
        "alpha_topology_param",
        "provider_rgb_interior_param",
        "deterministic_reconstruction_param",
        "alpha_topology_validation",
        "alpha_reconstructed_changed_pixels",
        "provider_rgb_interior_validation",
        "deterministic_reconstruction_validation",
        "anchored_changed_pixels",
        "provider_candidate_binding",
        "provider_candidate_input",
        "provider_candidate_sidecar_input",
    ],
)
async def test_manifest_rejects_incomplete_repair_branch_provenance(
    tmp_path: Path,
    tamper: str,
) -> None:
    run_dir, generated = await _generated_repaired_image_repeat_run(tmp_path)
    provenance_path = Path(generated.provenance_path)

    def mutate(record: dict[str, object]) -> None:
        params = cast(dict[str, object], record["params"])
        validation = cast(dict[str, object], record["validation"])
        if tamper == "context_span":
            params["context_span_px"] = 3
            return
        if tamper == "endpoint_anchor_algorithm":
            params["endpoint_anchor_algorithm"] = "unbound-anchor-v0"
            return
        if tamper == "endpoint_anchor_span":
            params["endpoint_anchor_span_px"] = 2
            return
        if tamper == "endpoint_anchor_validation":
            validation["endpoint_anchors_reimposed"] = False
            return
        if tamper == "alpha_reconstruction_algorithm":
            params["alpha_reconstruction_algorithm"] = "provider-alpha-v0"
            return
        if tamper == "alpha_topology_param":
            params["alpha_topology_reconstructed"] = False
            return
        if tamper == "provider_rgb_interior_param":
            params["provider_rgb_interior_preserved"] = False
            return
        if tamper == "deterministic_reconstruction_param":
            params["deterministically_reconstructible"] = False
            return
        if tamper == "alpha_topology_validation":
            validation["alpha_topology_reconstructed"] = False
            return
        if tamper == "alpha_reconstructed_changed_pixels":
            validation["alpha_reconstructed_changed_pixels"] = -1
            return
        if tamper == "provider_rgb_interior_validation":
            validation["provider_rgb_interior_preserved"] = False
            return
        if tamper == "deterministic_reconstruction_validation":
            validation["deterministically_reconstructible"] = False
            return
        if tamper == "anchored_changed_pixels":
            validation["anchored_repair_changed_pixels"] = -1
            return
        if tamper == "provider_candidate_binding":
            cast(dict[str, object], params["provider_candidate"])["sha256"] = "0" * 64
            return
        lineage = cast(
            dict[str, object],
            params["lineage"],
        )
        if tamper == "conditioning_input":
            removed_ref = f"sha256:{lineage['conditioning_sha256']}"
        else:
            provider_candidate = cast(dict[str, object], params["provider_candidate"])
            removed_ref = cast(
                str,
                provider_candidate[
                    "provenance_path" if tamper == "provider_candidate_sidecar_input" else "path"
                ],
            )
        record["inputs"] = [
            item
            for item in cast(list[dict[str, object]], record["inputs"])
            if item.get("ref") != removed_ref
        ]

    await _mutate_json(provenance_path, mutate)
    with pytest.raises(ValueError, match="image-repeat output provenance mismatch"):
        await write_scrolling_preview_manifest(run_dir=run_dir, tag=f"tampered-{tamper}")


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["candidate", "candidate_provenance"])
async def test_manifest_rejects_missing_provider_candidate_pair(
    tmp_path: Path,
    missing: str,
) -> None:
    run_dir, generated = await _generated_repaired_image_repeat_run(tmp_path)
    manifest = cast(dict[str, object], json.loads(await _read_text(generated.manifest_path)))
    construction = cast(dict[str, object], manifest["construction"])
    candidate = cast(dict[str, object], construction["provider_candidate"])
    candidate_path = run_dir / cast(str, candidate["path"])
    provenance_path = run_dir / cast(str, candidate["provenance_path"])
    await asyncio.to_thread((candidate_path if missing == "candidate" else provenance_path).unlink)

    with pytest.raises(ValueError, match="provider-candidate pair is incomplete"):
        await write_scrolling_preview_manifest(run_dir=run_dir, tag=f"missing-{missing}")


@pytest.mark.asyncio
async def test_manifest_rejects_tampered_provider_candidate_bytes(tmp_path: Path) -> None:
    run_dir, generated = await _generated_repaired_image_repeat_run(tmp_path)
    manifest = cast(dict[str, object], json.loads(await _read_text(generated.manifest_path)))
    construction = cast(dict[str, object], manifest["construction"])
    candidate = cast(dict[str, object], construction["provider_candidate"])
    candidate_path = run_dir / cast(str, candidate["path"])
    data = bytearray(await asyncio.to_thread(candidate_path.read_bytes))
    data[-1] ^= 1
    await asyncio.to_thread(candidate_path.write_bytes, bytes(data))

    with pytest.raises(ValueError, match="artifact binding mismatch"):
        await write_scrolling_preview_manifest(run_dir=run_dir, tag="tampered-candidate")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tamper",
    [
        "algorithm",
        "alpha_reconstruction_algorithm",
        "provider_responsibility",
        "component_responsibility",
        "candidate_role",
        "exact_preservation",
        "conditioning_input",
    ],
)
async def test_manifest_rejects_tampered_provider_candidate_provenance(
    tmp_path: Path,
    tamper: str,
) -> None:
    run_dir, generated = await _generated_repaired_image_repeat_run(tmp_path)
    manifest = cast(dict[str, object], json.loads(await _read_text(generated.manifest_path)))
    construction = cast(dict[str, object], manifest["construction"])
    candidate = cast(dict[str, object], construction["provider_candidate"])
    provenance_path = run_dir / cast(str, candidate["provenance_path"])

    def mutate(record: dict[str, object]) -> None:
        if tamper == "algorithm":
            cast(dict[str, object], record["params"])["algorithm"] = "legacy-repair-v2"
            return
        if tamper == "alpha_reconstruction_algorithm":
            cast(dict[str, object], record["params"])["alpha_reconstruction_algorithm"] = (
                "provider-alpha-v0"
            )
            return
        if tamper == "provider_responsibility":
            cast(dict[str, object], record["params"])["provider_responsibility"] = "alpha_topology"
            return
        if tamper == "component_responsibility":
            cast(dict[str, object], record["params"])["component_responsibility"] = "rgb_appearance"
            return
        if tamper == "candidate_role":
            cast(dict[str, object], record["validation"])["provider_candidate_role"] = (
                "final_repeat_unit"
            )
            return
        if tamper == "exact_preservation":
            cast(dict[str, object], record["validation"])["exact_provider_candidate_preserved"] = (
                False
            )
            return
        inputs = cast(list[dict[str, object]], record["inputs"])
        record["inputs"] = [
            item
            for item in inputs
            if item.get("ref")
            != f"sha256:{cast(dict[str, object], manifest['lineage'])['conditioning_sha256']}"
        ]

    await _mutate_json(provenance_path, mutate)
    with pytest.raises(ValueError, match="provider-candidate provenance mismatch"):
        await write_scrolling_preview_manifest(run_dir=run_dir, tag=f"candidate-{tamper}")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tamper",
    [
        "construction",
        "candidate_binding",
        "reconstruction_binding",
        "candidate_input",
        "candidate_sidecar_input",
    ],
)
async def test_manifest_rejects_incomplete_repair_manifest_provenance(
    tmp_path: Path,
    tamper: str,
) -> None:
    run_dir, generated = await _generated_repaired_image_repeat_run(tmp_path)
    manifest = cast(dict[str, object], json.loads(await _read_text(generated.manifest_path)))
    construction = cast(dict[str, object], manifest["construction"])
    candidate = cast(dict[str, object], construction["provider_candidate"])
    provenance_path = Path(generated.manifest_provenance_path)

    def mutate(record: dict[str, object]) -> None:
        if tamper == "construction":
            cast(dict[str, object], record["params"])["construction"] = {
                **construction,
                "endpoint_anchor_span_px": 2,
            }
            return
        if tamper == "candidate_binding":
            cast(dict[str, object], record["validation"])["provider_candidate_binding"] = False
            return
        if tamper == "reconstruction_binding":
            cast(dict[str, object], record["validation"])["repair_reconstruction_binding"] = False
            return
        removed_ref = cast(
            str,
            candidate["provenance_path" if tamper == "candidate_sidecar_input" else "path"],
        )
        record["inputs"] = [
            item
            for item in cast(list[dict[str, object]], record["inputs"])
            if item.get("ref") != removed_ref
        ]

    await _mutate_json(provenance_path, mutate)
    with pytest.raises(ValueError, match="image-repeat manifest provenance mismatch"):
        await write_scrolling_preview_manifest(run_dir=run_dir, tag=f"manifest-{tamper}")


async def _generated_image_repeat_run(tmp_path: Path) -> tuple[Path, ImageRepeatResult]:
    run_dir = tmp_path / "available"
    source = await asyncio.to_thread(_source_with_provenance, run_dir)
    backend = _AcceptingStructuredBackend()
    structured = StructuredGenerationService[object](
        backend,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    reviewer = StructuredIntendedLoopReviewer(
        structured,
        provider=backend.provider,
        model=backend.model,
        secrets=backend.secrets,
    )
    generated = await ImageRepeatService(reviewer).admit(
        ImageRepeatAdmissionRequest(
            source_path=source,
            source_ref=source.name,
            output_dir=run_dir,
            artifact_name="layer.repeat.png",
            manifest_name="layer.repeat.json",
            axis="x",
            intended_behavior="continuous_foreground_layer",
        )
    )
    return run_dir, generated


async def _generated_repaired_image_repeat_run(
    tmp_path: Path,
) -> tuple[Path, ImageRepeatResult]:
    run_dir = tmp_path / "available-repaired"
    source = await asyncio.to_thread(
        _source_with_provenance,
        run_dir,
        endpoint_alpha_transition=True,
    )
    backend = _AcceptingStructuredBackend()
    structured = StructuredGenerationService[object](
        backend,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    reviewer = StructuredIntendedLoopReviewer(
        structured,
        provider=backend.provider,
        model=backend.model,
        secrets=backend.secrets,
    )
    generated = await ImageRepeatService(
        reviewer,
        repair_backend=_PassingRepairBackend(),
    ).repair(
        ImageRepeatRepairRequest(
            source_path=source,
            source_ref=source.name,
            output_dir=run_dir,
            artifact_name="layer.repaired.repeat.png",
            manifest_name="layer.repaired.repeat.json",
            axis="x",
            intended_behavior="continuous generic decorative band",
            prompt="Continue the supplied endpoint contexts without a visible reset.",
            context_span_px=2,
            repair_span_px=4,
            alpha_policy="preserve",
            validation_policy=ImageRepeatValidationPolicy(
                alpha_mae=1.0,
                alpha_p95=1.0,
                alpha_max=1.0,
            ),
        )
    )
    return run_dir, generated


def _source_with_provenance(
    run_dir: Path,
    *,
    endpoint_alpha_transition: bool = False,
) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    source = run_dir / "layer.png"
    image = Image.new("RGBA", (6, 4))
    colors = (
        (200, 20, 20, 255),
        (200, 20, 20, 255),
        (30, 160, 70, 255),
        (30, 160, 70, 255),
        (200, 20, 20, 255),
        (200, 20, 20, 255),
    )
    for x, color in enumerate(colors):
        for y in range(image.height):
            image.putpixel(
                (x, y),
                (*color[:3], 0) if endpoint_alpha_transition and x >= image.width - 2 else color,
            )
    write_artifact_with_provenance(
        source,
        BinaryArtifact(data=_png(image), media_type="image/png"),
        ProvenanceInput(
            provider="local",
            model="test-fixture",
            prompt="construct a deterministic image-repeat source",
            refs=[],
            params={
                "metadata": {
                    "stage": "concept",
                    "opaque": not endpoint_alpha_transition,
                }
            },
            attempts=1,
        ),
    )
    return source


async def _mutate_json_and_rebind(
    artifact_path: Path,
    mutate: Callable[[dict[str, object]], None],
) -> None:
    await _mutate_json(artifact_path, mutate)
    artifact_data = await asyncio.to_thread(artifact_path.read_bytes)
    sidecar_path = Path(f"{artifact_path}.meta.json")

    def rebind(record: dict[str, object]) -> None:
        record["artifact"] = {
            "sha256": hashlib.sha256(artifact_data).hexdigest(),
            "bytes": len(artifact_data),
            "media_type": "application/json",
        }

    await _mutate_json(sidecar_path, rebind)


async def _mutate_json(
    path: Path,
    mutate: Callable[[dict[str, object]], None],
) -> None:
    record = cast(dict[str, object], json.loads(await _read_text(path)))
    mutate(record)
    payload = (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode()
    await asyncio.to_thread(path.write_bytes, payload)


async def _read_text(path: str | Path) -> str:
    return await asyncio.to_thread(Path(path).read_text, encoding="utf-8")


def _png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", compress_level=9, optimize=False)
    return output.getvalue()
