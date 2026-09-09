"""Offline graph integration with synthetic media and ordinary retry-owning services.

These cases prove orchestration and retained-artifact behavior, not visual model
judgment, real character generalization, or temporal acceptance.
"""

from __future__ import annotations

import base64
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Literal

import numpy as np
import pytest
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter

from gnode import (
    ArtifactProvenance,
    ArtifactRights,
    BinaryArtifact,
    ImageGenerationRequest,
    ImageGenerationService,
    ProvenanceInput,
    ProviderImage,
    ProviderResponseMetadata,
    ProviderStructuredOutput,
    RetryPolicy,
    StructuredGenerationRequest,
    StructuredGenerationService,
    write_artifact_with_provenance,
)
from stage_gen.components.portrait_motion import PortraitMotionSpec
from stage_gen.components.portrait_motion.models import PortraitMotionResult
from stage_gen.components.portrait_motion.nodes import STAGES
from stage_gen.components.portrait_motion.processing import png_bytes
from stage_gen.components.portrait_motion.storage import COMPONENT
from stage_gen.orchestration.portrait_motion import (
    TOOL,
    RuntimeProfile,
    load_plan,
    prepare_run,
    run_pipeline,
    verify_run,
)

FEATURES = ["canvas_left_eye", "canvas_right_eye", "mouth"]
CANVAS_SIZE = 1024
PANEL_SIZE = CANVAS_SIZE // 2
BOXES = {
    "canvas_left_eye": (128, 168, 176, 208),
    "canvas_right_eye": (336, 168, 384, 208),
    "mouth": (232, 328, 280, 368),
}


def specification() -> PortraitMotionSpec:
    return PortraitMotionSpec.model_validate(
        {
            "width": CANVAS_SIZE,
            "height": CANVAS_SIZE,
            "columns": 2,
            "rows": 2,
            "requested_features": FEATURES,
            "states": [
                {"state_id": "eyes_half", "feature_group": "eyes", "instruction": "Half blink."},
                {"state_id": "eyes_closed", "feature_group": "eyes", "instruction": "Close eyes."},
                {
                    "state_id": "mouth_smile",
                    "feature_group": "mouth",
                    "instruction": "Small smile.",
                },
                {"state_id": "mouth_a", "feature_group": "mouth", "instruction": "Open A drawing."},
            ],
            "playback": [
                {"eyes": "rest", "mouth": "rest", "duration_ms": 100},
                {"eyes": "eyes_half", "mouth": "rest", "duration_ms": 60},
                {"eyes": "eyes_closed", "mouth": "mouth_a", "duration_ms": 80},
                {"eyes": "rest", "mouth": "mouth_smile", "duration_ms": 80},
                {"eyes": "rest", "mouth": "rest", "duration_ms": 100},
            ],
        }
    )


def admission_document(mode: str) -> dict[str, Any]:
    records: list[dict[str, Any]] = [
        {
            "feature_id": feature,
            "route": "direct",
            "source_state": "rest" if feature == "mouth" else "open",
            "reason": "clear_feature",
            "evidence": "Synthetic fixture has observable feature boundaries.",
            "confidence": "high",
        }
        for feature in FEATURES
    ]
    ambiguous = mode == "ambiguous"
    readable = mode != "unreadable"
    if ambiguous or not readable:
        for record in records:
            record.update(
                route="unsupported",
                source_state="unknown",
                reason="ambiguous_subject" if ambiguous else "insufficient_resolution",
            )
    elif mode == "one_eye":
        records[0].update(route="hidden", source_state="unknown", reason="opaque_fully_hidden")
        records[2].update(route="unsupported", source_state="unknown", reason="partial_occlusion")
    return {
        "schema_version": 1,
        "subject_count": 2 if ambiguous else 1,
        "subject_unambiguous": not ambiguous,
        "image_readable": readable,
        "features": records,
    }


class ImageBackend:
    spec_version: ClassVar[Literal[1]] = 1
    provider = "openai"
    supports_native_alpha = False
    secrets: tuple[str, ...] = ()

    def __init__(self, profile: RuntimeProfile, eligible: list[str]) -> None:
        self.model: str = profile.image_model
        self.eligible = eligible
        self.calls = 0

    async def generate_once(self, request: ImageGenerationRequest) -> ProviderImage:
        self.calls += 1
        assert len(request.input_references) == 1
        encoded = request.input_references[0].url.partition(",")[2]
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as supplied:
            atlas = supplied.convert("RGB")
        draw = ImageDraw.Draw(atlas)
        for index in range(4):
            offset_x, offset_y = index % 2 * PANEL_SIZE, index // 2 * PANEL_SIZE
            for feature in self.eligible:
                if (feature == "mouth") != (index >= 2):
                    continue
                left, top, right, bottom = BOXES[feature]
                draw.rectangle(
                    (
                        left + 12 + offset_x,
                        top + 12 + offset_y,
                        right - 12 + offset_x,
                        bottom - 12 + offset_y,
                    ),
                    fill=(40 + index * 25, 70 + index * 20, 100 + index * 15),
                )
        return ProviderImage(
            data=png_bytes(atlas),
            media_type="image/png",
            response_metadata=ProviderResponseMetadata(
                request_id="offline-image", usage={"cost": 0}
            ),
        )

    async def aclose(self) -> None:
        return None


class StructuredBackend:
    spec_version: ClassVar[Literal[1]] = 1
    provider = "openrouter"
    secrets: tuple[str, ...] = ()

    def __init__(self, profile: RuntimeProfile, mode: str) -> None:
        self.model: str = profile.structured_model
        self.mode = mode
        self.admission = admission_document(mode)
        self.eligible = [
            record["feature_id"]
            for record in self.admission["features"]
            if record["route"] == "direct"
        ]
        self.calls: list[str] = []

    async def generate_once(
        self, request: StructuredGenerationRequest[object]
    ) -> ProviderStructuredOutput:
        stage = request.schema.name.removeprefix("portrait_motion_")
        self.calls.append(stage)
        if stage == "admission":
            value = self.admission
            if self.mode == "malformed_admission":
                value = {**value, "schema_version": "invalid"}
        elif stage == "geometry":
            assert len(request.references) == 10
            features = []
            for feature in self.eligible:
                left, top, right, bottom = BOXES[feature]
                features.append(
                    {
                        "feature_id": feature,
                        "points": [
                            [left, top],
                            [right, top],
                            [right, bottom],
                            [left, bottom],
                        ],
                    }
                )
            value = {
                "schema_version": 1,
                "status": "cannot_segment" if self.mode == "geometry_refusal" else "pass",
                "coordinate_space": "registered_panel_pixels",
                "canvas_size": [PANEL_SIZE, PANEL_SIZE],
                "features": [] if self.mode == "geometry_refusal" else features,
                "reason": "Synthetic refusal."
                if self.mode == "geometry_refusal"
                else "Bounded cores.",
            }
        elif stage == "quality":
            assert len(request.references) == 9
            failed = self.mode == "quality_failure"
            value = {
                "schema_version": 1,
                "status": "fail" if failed else "pass",
                "features": [
                    {
                        "feature_id": feature,
                        "status": "fail" if failed and index == 0 else "pass",
                        "reason": "Old lash remains."
                        if failed and index == 0
                        else "Synthetic pass.",
                    }
                    for index, feature in enumerate(self.eligible)
                ],
                "reason": "Synthetic semantic failure." if failed else "Synthetic semantic pass.",
                "temporal_review": "not_performed",
            }
        else:
            raise AssertionError(f"Unexpected structured stage {stage}")
        return ProviderStructuredOutput(
            decoded=value,
            raw_text=json.dumps(value),
            response_metadata=ProviderResponseMetadata(
                request_id=f"offline-{stage}", usage={"cost": 0}
            ),
        )

    async def aclose(self) -> None:
        return None


@dataclass
class Case:
    run_dir: Path
    image_backend: ImageBackend
    structured_backend: StructuredBackend
    image_service: ImageGenerationService
    structured_service: StructuredGenerationService[dict[str, Any]]

    async def run(self) -> dict[str, Any]:
        return await run_pipeline(
            self.run_dir,
            image_service=self.image_service,
            structured_service=self.structured_service,
        )


def prepare_case(tmp_path: Path, mode: str = "complete") -> Case:
    profile = RuntimeProfile()
    noise = gaussian_filter(np.random.default_rng(901).normal(size=(CANVAS_SIZE, CANVAS_SIZE)), 1.4)
    plane = np.clip(np.rint(128 + noise / noise.std() * 32), 0, 255).astype(np.uint8)
    picture = Image.fromarray(np.repeat(plane[..., None], 3, axis=2))
    source = tmp_path / "source.png"
    write_artifact_with_provenance(
        source,
        BinaryArtifact(png_bytes(picture), "image/png"),
        ProvenanceInput(
            provider="local",
            model="synthetic-test",
            prompt="Original seeded test texture.",
            component=COMPONENT,
            tool=TOOL,
            attempts=1,
        ),
    )
    run_dir = tmp_path / "run"
    prepare_run(source, run_dir, specification(), profile)
    structured = StructuredBackend(profile, mode)
    image = ImageBackend(profile, structured.eligible)
    retry = RetryPolicy(initial_delay_s=0, max_delay_s=0)
    return Case(
        run_dir,
        image,
        structured,
        ImageGenerationService(image, component=COMPONENT, tool=TOOL, retry_policy=retry),
        StructuredGenerationService(structured, component=COMPONENT, tool=TOOL, retry_policy=retry),
    )


def test_source_import_preserves_rights_and_attribution_on_unchanged_image(tmp_path: Path) -> None:
    prepare_case(tmp_path)
    source = tmp_path / "source.png"
    sidecar = tmp_path / "source.png.meta.json"
    original = ArtifactProvenance.model_validate_json(sidecar.read_bytes())
    rights = ArtifactRights(
        status="unreviewed",
        attribution=["Original synthetic test author"],
        basis=["Original procedural test texture"],
        reviewed_at=None,
    )
    sidecar.write_text(original.model_copy(update={"rights": rights}).model_dump_json())
    run_dir = tmp_path / "rights-preserved-run"
    prepare_run(source, run_dir, specification())
    copied = ArtifactProvenance.model_validate_json(
        (run_dir / "inputs/source.png.meta.json").read_bytes()
    )
    assert copied.rights == rights
    assert (run_dir / "inputs/source.png").read_bytes() == source.read_bytes()
    assert json.loads((run_dir / "inputs/source-origin.json").read_bytes())["rights"] == (
        rights.model_dump(mode="json")
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("modality", ["image", "structured"])
@pytest.mark.parametrize("identity", ["provider", "model"])
async def test_injected_route_mismatch_refuses_before_any_submission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, modality: str, identity: str
) -> None:
    case = prepare_case(tmp_path)
    backend = case.image_backend if modality == "image" else case.structured_backend
    monkeypatch.setattr(backend, identity, "unexpected")
    with pytest.raises(ValueError, match="service route must match the prepared binding"):
        await case.run()
    assert case.image_backend.calls == 0
    assert case.structured_backend.calls == []
    assert not list(case.run_dir.rglob("submission.json"))


@pytest.mark.asyncio
async def test_complete_graph_and_offline_cache_resume(tmp_path: Path) -> None:
    case = prepare_case(tmp_path)
    result = await case.run()
    assert result["status"] == "complete", result
    assert result["accepted_features"] == FEATURES
    assert result["verified_stages"] == list(STAGES)
    assert result["provider_operations_this_invocation"] == 4
    assert result["provider_operations_total"] == 4
    assert case.image_backend.calls == 1
    assert case.structured_backend.calls == ["admission", "geometry", "quality"]
    assert result["temporal_review"] == "not_performed"
    assert result["publication_authorized"] is False
    assert (case.run_dir / result["preview_ref"]).is_file()
    assert (case.run_dir / (result["preview_ref"] + ".meta.json")).is_file()
    assert "eligible_features" not in json.loads(
        (case.run_dir / "admission/decision.json").read_text()
    )
    replay = await run_pipeline(case.run_dir)
    assert replay["status"] == "complete"
    assert replay["provider_operations_this_invocation"] == 0
    assert replay["provider_operations_total"] == 4
    assert case.image_backend.calls == 1
    assert case.structured_backend.calls == ["admission", "geometry", "quality"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["ambiguous", "unreadable"])
async def test_admission_refusal_makes_no_image_calls(tmp_path: Path, mode: str) -> None:
    case = prepare_case(tmp_path, mode)
    result = await case.run()
    assert result["status"] == "refused", result
    assert result["accepted_features"] == []
    assert result["preview_ref"] is None
    assert result["verified_stages"] == list(STAGES)
    assert result["provider_operations_total"] == 1
    assert case.image_backend.calls == 0
    assert case.structured_backend.calls == ["admission"]
    assert not (case.run_dir / "atlas/atlas.png").exists()


@pytest.mark.asyncio
async def test_malformed_response_exhausts_one_six_attempt_owner(tmp_path: Path) -> None:
    case = prepare_case(tmp_path, "malformed_admission")
    result = await case.run()
    assert result["status"] == "failed", result
    assert result["accepted_features"] == []
    assert result["provider_operations_this_invocation"] == 6
    assert case.structured_backend.calls == ["admission"] * 6
    assert case.image_backend.calls == 0
    resumed = await case.run()
    assert resumed["status"] == "failed"
    assert resumed["provider_operations_this_invocation"] == 0
    assert case.structured_backend.calls == ["admission"] * 6


@pytest.mark.asyncio
async def test_one_eye_remains_independent_of_excluded_eye_and_mouth(tmp_path: Path) -> None:
    case = prepare_case(tmp_path, "one_eye")
    result = await case.run()
    assert result["status"] == "partial", result
    assert result["accepted_features"] == ["canvas_right_eye"]
    assert not (case.run_dir / "composition/mask-canvas_left_eye.png").exists()
    assert not (case.run_dir / "composition/mask-mouth.png").exists()
    with Image.open(case.run_dir / "inputs/source.png") as image:
        source = np.array(image.convert("RGB"))
    with Image.open(case.run_dir / "composition/mask-canvas_right_eye.png") as image:
        mask = np.array(image.convert("L")) > 0
    with Image.open(case.run_dir / "composition/eyes_closed--mouth_a.png") as image:
        composite = np.array(image.convert("RGB"))
    assert np.array_equal(composite[~mask], source[~mask])
    assert np.any(composite[mask] != source[mask])


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,operations", [("geometry_refusal", 3), ("quality_failure", 4)])
async def test_valid_semantic_refusal_never_accepts_output(
    tmp_path: Path, mode: str, operations: int
) -> None:
    case = prepare_case(tmp_path, mode)
    result = await case.run()
    assert result["status"] == "refused", result
    assert result["accepted_features"] == []
    assert result["preview_ref"] is None
    assert result["provider_operations_total"] == operations
    assert case.image_backend.calls == 1
    assert case.structured_backend.calls.count("geometry") == 1
    assert case.structured_backend.calls.count("quality") == int(mode == "quality_failure")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "removed",
    [
        ("atlas/atlas.png",),
        ("quality/result.json",),
        ("geometry/result.json", "geometry/result.json.meta.json"),
    ],
)
async def test_missing_artifact_or_receipt_fails_closed_without_resubmission(
    tmp_path: Path, removed: tuple[str, ...]
) -> None:
    case = prepare_case(tmp_path)
    assert (await case.run())["status"] == "complete"
    for ref in removed:
        (case.run_dir / ref).unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        verify_run(case.run_dir)
    result = await case.run()
    assert result["status"] == "failed", result
    assert result["accepted_features"] == []
    assert result["preview_ref"] is None
    assert result["provider_operations_this_invocation"] == 0
    assert case.image_backend.calls == 1
    assert case.structured_backend.calls == ["admission", "geometry", "quality"]


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "complete"},
        {"status": "partial", "accepted_features": ["canvas_left_eye"]},
        {"accepted_features": ["canvas_left_eye"]},
        {"preview_ref": "composition/preview.webp"},
        {"admitted_features": ["canvas_left_eye", "canvas_left_eye"]},
    ],
)
def test_terminal_contract_rejects_incoherent_acceptance(changes: dict[str, Any]) -> None:
    value: dict[str, Any] = {
        "status": "refused",
        "reason": "Synthetic terminal contract fixture.",
        "admitted_features": [],
        "accepted_features": [],
        "preview_ref": None,
        "manifest_ref": None,
        "required_stages": list(STAGES),
    }
    value.update(changes)
    with pytest.raises(ValueError):
        PortraitMotionResult.model_validate(value)


@pytest.mark.asyncio
async def test_rehashed_terminal_cannot_override_retained_refusal(tmp_path: Path) -> None:
    case = prepare_case(tmp_path, "ambiguous")
    assert (await case.run())["status"] == "refused"
    store, plan, graph = load_plan(case.run_dir)
    node = next(item for item in graph.nodes if item.node_id == "terminal")
    value = store.read("terminal/manifest.json")
    value.update(
        status="complete",
        admitted_features=["canvas_left_eye"],
        accepted_features=["canvas_left_eye"],
        preview_ref="composition/preview.webp",
        manifest_ref="composition/manifest.json",
        reason="Deliberately contradictory but structurally coherent audit fixture.",
    )
    PortraitMotionResult.model_validate(value)
    # Canonical sidecars and a complete receipt isolate the semantic check from
    # ordinary byte-corruption detection. All earlier stage records stay intact.
    store.write_json(
        "terminal/manifest.json",
        value,
        inputs=[f"{stage}/result.json" for stage in plan["required_stages"][:-1]],
        params={"node_cache_key": node.cache_key},
        prompt="Create a contradictory terminal fixture for verification.",
    )
    store.finish(
        node, status="passed", reason="Audit checkpoint.", files=["terminal/manifest.json"]
    )
    assert store.read("admission/result.json")["status"] == "refused"
    assert store.read("quality/result.json")["status"] == "skipped"
    with pytest.raises(ValueError):
        verify_run(case.run_dir)
    resumed = await case.run()
    assert resumed["status"] == "failed"
    assert resumed["provider_operations_this_invocation"] == 0
    assert case.image_backend.calls == 0
    assert case.structured_backend.calls == ["admission"]
