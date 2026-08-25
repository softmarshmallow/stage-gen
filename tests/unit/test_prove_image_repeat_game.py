from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from scripts.prove_image_repeat_game import execute_proof, layer_policy, prepare_proof
from stage_gen.components.image_repeat import (
    ImageRepeatAdmissionRequest,
    ImageRepeatDeterministicValidationError,
    ImageRepeatRepairRequest,
    ImageRepeatResult,
    ImageRepeatSemanticReview,
    ImageRepeatSemanticValidationError,
    ImageRepeatValidationPolicy,
    IntendedLoopReview,
    validate_image_repeat,
)


class _RejectingProofService:
    def __init__(self, deterministic: ImageRepeatDeterministicValidationError) -> None:
        self.deterministic = deterministic
        self.calls: list[tuple[str, ImageRepeatAdmissionRequest | ImageRepeatRepairRequest]] = []

    async def admit(self, request: ImageRepeatAdmissionRequest) -> ImageRepeatResult:
        self.calls.append(("admit", request))
        raise self.deterministic

    async def repair(self, request: ImageRepeatRepairRequest) -> ImageRepeatResult:
        self.calls.append(("repair", request))
        raise ImageRepeatSemanticValidationError(
            IntendedLoopReview(
                verdict="reject",
                confidence=0.94,
                failure_codes=("salient_periodic_cadence",),
                evidence="The same bright motif repeats conspicuously at one-period intervals.",
            )
        )


class _FailingProofService:
    async def admit(self, request: ImageRepeatAdmissionRequest) -> ImageRepeatResult:
        del request
        raise RuntimeError("provider leaked proof-secret in an error")

    async def repair(self, request: ImageRepeatRepairRequest) -> ImageRepeatResult:
        del request
        raise AssertionError("repair must not run after an untyped admission failure")


class _AcceptingProofService:
    def __init__(self, result: ImageRepeatResult) -> None:
        self.result = result
        self.calls: list[tuple[str, ImageRepeatAdmissionRequest | ImageRepeatRepairRequest]] = []

    async def admit(self, request: ImageRepeatAdmissionRequest) -> ImageRepeatResult:
        self.calls.append(("admit", request))
        return self.result

    async def repair(self, request: ImageRepeatRepairRequest) -> ImageRepeatResult:
        self.calls.append(("repair", request))
        raise AssertionError("repair must not run after successful admission")


def _non_looping_png() -> bytes:
    image = Image.new("RGBA", (16, 8), (255, 255, 255, 255))
    image.paste((0, 0, 0, 255), (0, 0, 4, image.height))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _prepared_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "proof-run"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(json.dumps({"tag": "proof-v1"}), encoding="utf-8")
    for layer in ("playfield", "near_foreground"):
        source = run_dir / f"layer_proof-v1_{layer}.png"
        source.write_bytes(_non_looping_png())
        Path(f"{source}.meta.json").write_text("{}", encoding="utf-8")
    return run_dir


def test_regenerated_layer_policies_reject_salient_motifs() -> None:
    distant = layer_policy("far_vale")
    middle = layer_policy("middle_country")
    foreground = layer_policy("near_foreground")

    assert distant.coverage_policy == "sparse_allowed"
    assert "no recognizable landscape form" in distant.intended_behavior
    assert "hill, peak" in distant.repair_prompt
    assert middle.coverage_policy == "continuous"
    assert "no recognizable landmark" in middle.intended_behavior
    assert "hill peak" in middle.repair_prompt
    assert foreground.coverage_policy == "sparse_allowed"
    assert "no recognizable landmark" in foreground.intended_behavior
    assert "tall plant" in foreground.repair_prompt


@pytest.mark.asyncio
async def test_typed_admission_rejection_is_recorded_before_explicit_repair(
    tmp_path: Path,
) -> None:
    run_dir = _prepared_run_dir(tmp_path)

    deterministic_report = validate_image_repeat(
        _non_looping_png(),
        axis="x",
        alpha_policy="preserve",
        coverage_policy="continuous",
        validation_policy=ImageRepeatValidationPolicy(),
    )
    assert deterministic_report.verdict == "reject"
    service = _RejectingProofService(ImageRepeatDeterministicValidationError(deterministic_report))

    report = await execute_proof(
        prepare_proof(run_dir, ("playfield", "near_foreground")),
        service,
        repair_on_rejection=True,
    )

    assert report["ok"] is False
    assert [operation for operation, _request in service.calls] == [
        "admit",
        "repair",
        "admit",
        "repair",
    ]
    playfield_admission = service.calls[0][1]
    playfield_repair = service.calls[1][1]
    foreground_admission = service.calls[2][1]
    foreground_repair = service.calls[3][1]
    assert isinstance(playfield_admission, ImageRepeatAdmissionRequest)
    assert isinstance(playfield_repair, ImageRepeatRepairRequest)
    assert isinstance(foreground_admission, ImageRepeatAdmissionRequest)
    assert isinstance(foreground_repair, ImageRepeatRepairRequest)
    assert playfield_admission.artifact_name == "layer_proof-v1_playfield.repeat.png"
    assert playfield_admission.manifest_name == "layer_proof-v1_playfield.repeat.json"
    assert playfield_repair.artifact_name == "layer_proof-v1_playfield.repaired.repeat.png"
    assert playfield_repair.manifest_name == "layer_proof-v1_playfield.repaired.repeat.json"
    assert playfield_repair.context_span_px == 192
    assert playfield_repair.repair_span_px == 512
    assert playfield_admission.coverage_policy == "continuous"
    assert foreground_admission.coverage_policy == "sparse_allowed"
    assert foreground_repair.coverage_policy == "sparse_allowed"
    assert "camera" not in playfield_repair.prompt.lower()
    assert "runtime" not in foreground_repair.prompt.lower()
    layers = report["layers"]
    assert isinstance(layers, list)
    assert all(layer["repair_requested_explicitly"] is True for layer in layers)
    assert all(layer["admission"]["gate"] == "deterministic" for layer in layers)
    assert all(layer["repair"]["gate"] == "semantic" for layer in layers)


@pytest.mark.asyncio
async def test_admission_rejection_stops_without_explicit_repair(tmp_path: Path) -> None:
    run_dir = _prepared_run_dir(tmp_path)
    deterministic_report = validate_image_repeat(
        _non_looping_png(),
        axis="x",
        alpha_policy="preserve",
        coverage_policy="continuous",
        validation_policy=ImageRepeatValidationPolicy(),
    )
    service = _RejectingProofService(ImageRepeatDeterministicValidationError(deterministic_report))

    report = await execute_proof(
        prepare_proof(run_dir, ("playfield",)),
        service,
    )

    assert report["ok"] is False
    assert report["repair_on_rejection"] is False
    assert [operation for operation, _request in service.calls] == ["admit"]
    layers = report["layers"]
    assert isinstance(layers, list)
    assert layers[0]["repair_requested_explicitly"] is False
    assert layers[0]["repair"] == {
        "status": "not_run",
        "reason": "caller did not explicitly request repair after admission rejection",
    }


@pytest.mark.asyncio
async def test_successful_admission_is_final_and_does_not_request_repair(tmp_path: Path) -> None:
    plan = prepare_proof(_prepared_run_dir(tmp_path), ("playfield",))
    report_data = validate_image_repeat(
        _non_looping_png(),
        axis="x",
        alpha_policy="preserve",
        coverage_policy="continuous",
        validation_policy=ImageRepeatValidationPolicy(),
    )
    result = ImageRepeatResult(
        data=_non_looping_png(),
        media_type="image/png",
        axis="x",
        decision="admitted",
        artifact_path=str(plan.run_dir / "layer_proof-v1_playfield.repeat.png"),
        provenance_path=str(plan.run_dir / "layer_proof-v1_playfield.repeat.png.meta.json"),
        manifest_path=str(plan.run_dir / "layer_proof-v1_playfield.repeat.json"),
        manifest_provenance_path=str(
            plan.run_dir / "layer_proof-v1_playfield.repeat.json.meta.json"
        ),
        period_px=16,
        deterministic_report=report_data,
        semantic_review=ImageRepeatSemanticReview(
            verdict="accept",
            confidence=0.98,
            failure_codes=[],
            evidence="Both joins and the intended cadence are visually continuous.",
            judged_sha256="a" * 64,
            preview_sha256="b" * 64,
            criteria_sha256="c" * 64,
            reviewer_provider="proof-review",
            reviewer_model="proof-review-v1",
            independent=True,
        ),
    )
    service = _AcceptingProofService(result)

    report = await execute_proof(plan, service)

    assert report["ok"] is True
    assert [operation for operation, _request in service.calls] == ["admit"]
    layers = report["layers"]
    assert isinstance(layers, list)
    assert layers[0]["repair_requested_explicitly"] is False
    assert layers[0]["repair"]["status"] == "not_run"


@pytest.mark.asyncio
async def test_untyped_error_is_redacted_and_does_not_request_repair(tmp_path: Path) -> None:
    plan = prepare_proof(_prepared_run_dir(tmp_path), ("playfield",))

    report = await execute_proof(plan, _FailingProofService(), secrets=("proof-secret",))

    serialized = json.dumps(report)
    assert "proof-secret" not in serialized
    assert "[REDACTED]" in serialized
    layers = report["layers"]
    assert isinstance(layers, list)
    assert layers[0]["repair_requested_explicitly"] is False
    assert layers[0]["repair"]["status"] == "not_run"
