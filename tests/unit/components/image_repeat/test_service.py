from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from typing import Literal, cast

import pytest
from PIL import Image
from pydantic import ValidationError

from gnode import (
    ArtifactProvenance,
    BinaryArtifact,
    ProvenanceInput,
    RetryPolicy,
    write_artifact_with_provenance,
)
from stage_gen.components._types import ProviderResponseMetadata
from stage_gen.components.image_repeat import (
    INTENDED_LOOP_MIN_ACCEPT_CONFIDENCE,
    INTENDED_LOOP_REVIEW_PROMPT_VERSION,
    THREE_REPEAT_PREVIEW_VERSION,
    ImageRepeatAdmissionRequest,
    ImageRepeatDeterministicValidationError,
    ImageRepeatFailureCode,
    ImageRepeatManifest,
    ImageRepeatRepairConstruction,
    ImageRepeatRepairLineage,
    ImageRepeatRepairRequest,
    ImageRepeatReviewerUnavailableError,
    ImageRepeatSemanticValidationError,
    ImageRepeatService,
    ImageRepeatValidationPolicy,
    IntendedLoopReview,
    IntendedLoopReviewRequest,
    MaskedImageEditRequest,
    ProviderImageRepeatEdit,
    build_three_repeat_preview,
    canonical_intended_loop_criteria,
    validate_image_repeat,
    verify_image_repeat_artifact,
)

type Color = tuple[int, int, int, int]
type Outcome = Literal["good", "bad", "error"]

_RED: Color = (200, 20, 20, 255)
_GREEN: Color = (30, 160, 70, 255)
_BLUE: Color = (20, 40, 210, 255)


class FakeIntendedLoopReviewer:
    provider = "fake-review"
    model = "fake-review-v1"
    secrets: tuple[str, ...] = ("review-secret",)

    def __init__(
        self,
        *,
        verdict: Literal["accept", "reject", "uncertain"] = "accept",
        failure_codes: tuple[ImageRepeatFailureCode, ...] = (),
        confidence: float | None = None,
        error: Exception | None = None,
        persist_evidence: bool = False,
    ) -> None:
        self.verdict = verdict
        self.failure_codes = failure_codes
        self.confidence = confidence
        self.error = error
        self.persist_evidence = persist_evidence
        self.calls = 0
        self.requests: list[IntendedLoopReviewRequest] = []
        self.closed = False

    async def review(self, request: IntendedLoopReviewRequest) -> IntendedLoopReview:
        self.calls += 1
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        artifact_path: str | None = None
        provenance_path: str | None = None
        if self.persist_evidence:
            artifact = Path(request.review_artifact_path)
            payload = (
                json.dumps(
                    {
                        "verdict": self.verdict,
                        "confidence": self._confidence(),
                        "failure_codes": list(self.failure_codes),
                        "evidence": f"fake {self.verdict} evidence",
                    },
                    sort_keys=True,
                )
                + "\n"
            ).encode()
            sidecar = await asyncio.to_thread(
                write_artifact_with_provenance,
                artifact,
                BinaryArtifact(data=payload, media_type="application/json"),
                ProvenanceInput(
                    provider=self.provider,
                    model=self.model,
                    prompt="judge exact three-repeat preview",
                    refs=[f"sha256:{request.preview_sha256}"],
                    attempts=1,
                ),
            )
            artifact_path = str(artifact)
            provenance_path = str(sidecar)
        return IntendedLoopReview(
            verdict=self.verdict,
            confidence=self._confidence(),
            failure_codes=self.failure_codes,
            evidence=f"fake {self.verdict} evidence",
            response_metadata=ProviderResponseMetadata(request_id=f"review-{self.calls}"),
            artifact_path=artifact_path,
            provenance_path=provenance_path,
        )

    async def aclose(self) -> None:
        self.closed = True

    def _confidence(self) -> float:
        if self.confidence is not None:
            return self.confidence
        return 0.96 if self.verdict == "accept" else 0.72


class FakeMaskedImageEditBackend:
    provider = "fake-edit"
    model = "fake-mask-v2"
    capability: Literal["masked-image-edit"] = "masked-image-edit"
    secrets: tuple[str, ...] = ("edit-secret",)

    def __init__(
        self,
        outcomes: Sequence[Outcome] = ("good",),
        *,
        mutate_context: bool = True,
    ) -> None:
        self.outcomes = tuple(outcomes)
        self.mutate_context = mutate_context
        self.calls = 0
        self.requests: list[MaskedImageEditRequest] = []
        self.outputs: list[bytes] = []
        self.closed = False

    async def edit_once(self, request: MaskedImageEditRequest) -> ProviderImageRepeatEdit:
        self.calls += 1
        self.requests.append(request)
        outcome = self.outcomes[min(self.calls - 1, len(self.outcomes) - 1)]
        if outcome == "error":
            raise RuntimeError("transient edit-secret failure")
        data = _provider_candidate(
            request,
            outcome=outcome,
            mutate_context=self.mutate_context,
        )
        self.outputs.append(data)
        return ProviderImageRepeatEdit(
            data=data,
            media_type="image/png",
            response_metadata=ProviderResponseMetadata(request_id=f"edit-{self.calls}"),
        )

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
@pytest.mark.parametrize("axis", ["x", "y"])
async def test_admit_passes_through_exact_bytes_and_reviews_exact_three_repeats(
    tmp_path: Path,
    axis: Literal["x", "y"],
) -> None:
    source = _source_with_provenance(tmp_path / "source", axis=axis, seamless=True)
    reviewer = FakeIntendedLoopReviewer()
    result = await ImageRepeatService(reviewer).admit(
        _admission_request(source, tmp_path / "out", axis=axis)
    )

    assert result.decision == "admitted"
    assert result.axis == axis
    assert result.data == source.read_bytes()
    assert await _read_bytes(result.artifact_path) == source.read_bytes()
    assert reviewer.calls == 1
    review_request = reviewer.requests[0]
    assert review_request.deterministic_report.verdict == "pass"
    source_image = _decode(source.read_bytes()).convert("RGBA")
    preview = _decode(review_request.preview_png).convert("RGBA")
    expected_size = (
        (source_image.width * 3, source_image.height)
        if axis == "x"
        else (source_image.width, source_image.height * 3)
    )
    assert preview.size == expected_size
    for index in range(3):
        box = (
            (
                index * source_image.width,
                0,
                (index + 1) * source_image.width,
                source_image.height,
            )
            if axis == "x"
            else (
                0,
                index * source_image.height,
                source_image.width,
                (index + 1) * source_image.height,
            )
        )
        assert preview.crop(box).tobytes() == source_image.tobytes()

    manifest_text = await _read_text(result.manifest_path)
    manifest_payload = cast(dict[str, object], json.loads(manifest_text))
    _assert_lower_snake_keys(manifest_payload)
    manifest = ImageRepeatManifest.model_validate_json(manifest_text)
    assert manifest.schema_version == 2
    assert manifest.kind == "single_axis_repeat_unit"
    assert manifest.axis == axis
    assert manifest.decision == "admitted"
    assert manifest.source.sha256 == manifest.repeat_unit.sha256
    assert manifest.construction.mode == "admitted"
    assert manifest.validation.deterministic.verdict == "pass"
    assert manifest.validation.intended_loop.verdict == "accept"
    assert manifest.validation.intended_loop.independent is True
    assert manifest.validation.other_axis_status == "not_evaluated"
    criteria = canonical_intended_loop_criteria(
        axis=manifest.axis,
        intended_behavior=manifest.intent.intended_behavior,
        alpha_policy=manifest.intent.alpha_policy,
        coverage_policy=manifest.intent.coverage_policy,
        validation_policy=manifest.validation.policy,
    )
    criteria_payload = json.loads(criteria)
    assert criteria_payload["minimum_accept_confidence"] == (INTENDED_LOOP_MIN_ACCEPT_CONFIDENCE)
    assert criteria_payload["below_threshold_policy"] == "fail_closed"
    assert criteria_payload["preview_version"] == THREE_REPEAT_PREVIEW_VERSION
    assert criteria_payload["prompt_version"] == INTENDED_LOOP_REVIEW_PROMPT_VERSION
    assert manifest.intent.criteria_sha256 == hashlib.sha256(criteria).hexdigest()
    assert await asyncio.to_thread(Path(result.provenance_path).is_file)
    assert await asyncio.to_thread(Path(result.manifest_provenance_path).is_file)
    assert result.provider_candidate_path is None
    assert result.provider_candidate_provenance_path is None
    assert "layer.repeat.provider-candidate.png" not in _directory_names(tmp_path / "out")
    manifest_record = ArtifactProvenance.model_validate_json(
        await _read_bytes(result.manifest_provenance_path)
    )
    assert manifest_record.params["construction"] == manifest.construction.model_dump(mode="json")
    assert "provider_candidate_binding" not in manifest_record.validation


@pytest.mark.asyncio
async def test_admit_rejects_bad_wrap_without_reviewer_or_automatic_repair(
    tmp_path: Path,
) -> None:
    source = _source_with_provenance(tmp_path / "source", axis="x", seamless=False)
    reviewer = FakeIntendedLoopReviewer()
    repair_backend = FakeMaskedImageEditBackend()
    output_dir = tmp_path / "out"
    with pytest.raises(ImageRepeatDeterministicValidationError) as captured:
        await ImageRepeatService(reviewer, repair_backend=repair_backend).admit(
            _admission_request(source, output_dir, axis="x")
        )

    assert "visible_boundary_pop" in captured.value.report.failure_codes
    assert reviewer.calls == 0
    assert repair_backend.calls == 0
    assert _directory_names(output_dir) == []


@pytest.mark.asyncio
async def test_admission_digest_binds_persisted_reviewer_evidence(tmp_path: Path) -> None:
    source = _source_with_provenance(tmp_path / "source", axis="x", seamless=True)
    reviewer = FakeIntendedLoopReviewer(persist_evidence=True)
    result = await ImageRepeatService(reviewer).admit(
        _admission_request(source, tmp_path / "out", axis="x")
    )

    manifest = ImageRepeatManifest.model_validate_json(await _read_text(result.manifest_path))
    binding = manifest.validation.intended_loop.review_artifact
    assert binding is not None
    review_path = Path(result.manifest_path).parent / binding.path
    review_provenance = Path(result.manifest_path).parent / binding.provenance_path
    review_bytes = await _read_bytes(review_path)
    provenance_bytes = await _read_bytes(review_provenance)
    assert binding.sha256 == hashlib.sha256(review_bytes).hexdigest()
    assert binding.provenance_sha256 == hashlib.sha256(provenance_bytes).hexdigest()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("verdict", "codes"),
    [
        ("reject", ("structure_or_horizon_reset",)),
        ("uncertain", ("insufficient_evidence",)),
    ],
)
async def test_semantic_reject_and_uncertain_fail_closed_without_success_files(
    tmp_path: Path,
    verdict: Literal["reject", "uncertain"],
    codes: tuple[ImageRepeatFailureCode, ...],
) -> None:
    source = _source_with_provenance(tmp_path / "source", axis="x", seamless=True)
    reviewer = FakeIntendedLoopReviewer(verdict=verdict, failure_codes=codes)
    output_dir = tmp_path / "out"
    with pytest.raises(ImageRepeatSemanticValidationError, match=verdict):
        await ImageRepeatService(reviewer).admit(_admission_request(source, output_dir, axis="x"))

    assert reviewer.calls == 1
    assert _directory_names(output_dir) == []


@pytest.mark.asyncio
async def test_low_confidence_accept_from_alternate_reviewer_fails_component_closed(
    tmp_path: Path,
) -> None:
    source = _source_with_provenance(tmp_path / "source", axis="x", seamless=True)
    reviewer = FakeIntendedLoopReviewer(confidence=INTENDED_LOOP_MIN_ACCEPT_CONFIDENCE - 0.01)
    output_dir = tmp_path / "out"

    with pytest.raises(
        ImageRepeatSemanticValidationError,
        match="accept_below_minimum_confidence",
    ):
        await ImageRepeatService(reviewer).admit(_admission_request(source, output_dir, axis="x"))

    assert reviewer.calls == 1
    assert _directory_names(output_dir) == []


@pytest.mark.asyncio
async def test_reviewer_operation_is_called_once_and_is_not_nested_in_component_retry(
    tmp_path: Path,
) -> None:
    source = _source_with_provenance(tmp_path / "source", axis="x", seamless=True)
    reviewer = FakeIntendedLoopReviewer(error=RuntimeError("review transport failed"))
    with pytest.raises(RuntimeError, match="review transport failed"):
        await ImageRepeatService(
            reviewer,
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        ).admit(_admission_request(source, tmp_path / "out", axis="x"))
    assert reviewer.calls == 1


@pytest.mark.asyncio
async def test_missing_or_nonindependent_reviewer_fails_before_any_success_marker(
    tmp_path: Path,
) -> None:
    source = _source_with_provenance(tmp_path / "source", axis="x", seamless=True)
    with pytest.raises(ImageRepeatReviewerUnavailableError, match="independent"):
        await ImageRepeatService().admit(_admission_request(source, tmp_path / "missing", axis="x"))

    reviewer = FakeIntendedLoopReviewer()
    reviewer.provider = "local"
    reviewer.model = "test-fixture"
    with pytest.raises(ImageRepeatReviewerUnavailableError, match="independent"):
        await ImageRepeatService(reviewer).admit(
            _admission_request(source, tmp_path / "same", axis="x")
        )
    assert reviewer.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("axis", ["x", "y"])
async def test_explicit_repair_retries_deterministic_failure_preserves_source_and_reviews_once(
    tmp_path: Path,
    axis: Literal["x", "y"],
) -> None:
    source = _source_with_provenance(tmp_path / "source", axis=axis, seamless=False)
    reviewer = FakeIntendedLoopReviewer()
    backend = FakeMaskedImageEditBackend(("bad", "good"), mutate_context=True)
    result = await ImageRepeatService(
        reviewer,
        repair_backend=backend,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    ).repair(_repair_request(source, tmp_path / "out", axis=axis))

    assert result.decision == "repaired"
    assert result.provider == "fake-edit"
    assert result.model == "fake-mask-v2"
    assert result.attempts == backend.calls == 2
    assert reviewer.calls == 1
    request = backend.requests[-1]
    expected_size = (8, 4) if axis == "x" else (4, 8)
    assert (request.width, request.height) == expected_size
    assert request.axis == axis
    assert request.metadata["algorithm"] == "endpoint-alpha-reconstructed-anchored-repair-v4"
    assert request.metadata["mask_semantics"] == "white_edit_black_preserve"
    assert request.metadata["alpha_reconstruction_algorithm"] == (
        "source-endpoint-alpha-smoothstep-v1"
    )
    assert request.metadata["provider_responsibility"] == "rgb_appearance"
    assert request.metadata["component_responsibility"] == (
        "alpha_topology_and_endpoint_continuity"
    )

    source_image = _decode(source.read_bytes()).convert("RGBA")
    repeat = _decode(result.data).convert("RGBA")
    source_box = (
        (0, 0, source_image.width, repeat.height)
        if axis == "x"
        else (0, 0, repeat.width, source_image.height)
    )
    assert repeat.crop(source_box).tobytes() == source_image.tobytes()
    assert repeat.size == (
        (source_image.width + 4, source_image.height)
        if axis == "x"
        else (source_image.width, source_image.height + 4)
    )
    manifest = ImageRepeatManifest.model_validate_json(await _read_text(result.manifest_path))
    assert manifest.axis == axis
    assert manifest.decision == "repaired"
    construction = manifest.construction
    lineage = manifest.lineage
    assert isinstance(construction, ImageRepeatRepairConstruction)
    assert isinstance(lineage, ImageRepeatRepairLineage)
    assert construction.algorithm == "endpoint-alpha-reconstructed-anchored-repair-v4"
    assert construction.endpoint_anchor_algorithm == ("linear-light-premultiplied-smoothstep-v1")
    assert construction.endpoint_anchor_span_px == 1
    assert construction.endpoint_anchors_reimposed is True
    assert construction.alpha_reconstruction_algorithm == ("source-endpoint-alpha-smoothstep-v1")
    assert construction.alpha_topology_reconstructed is True
    assert construction.provider_rgb_interior_preserved is True
    assert construction.deterministically_reconstructible is True
    assert manifest.validation.deterministic.verdict == "pass"

    candidate_path = Path(cast(str, result.provider_candidate_path))
    candidate_provenance_path = Path(cast(str, result.provider_candidate_provenance_path))
    assert candidate_path.name == "layer.repeat.provider-candidate.png"
    assert candidate_provenance_path.name == "layer.repeat.provider-candidate.png.meta.json"
    candidate_data = await _read_bytes(candidate_path)
    candidate_sidecar = await _read_bytes(candidate_provenance_path)
    assert candidate_data == backend.outputs[-1]
    assert construction.provider_candidate.path == candidate_path.name
    assert construction.provider_candidate.provenance_path == candidate_provenance_path.name
    assert construction.provider_candidate.sha256 == hashlib.sha256(candidate_data).hexdigest()
    assert construction.provider_candidate.bytes == len(candidate_data)
    assert lineage.provider_candidate_sha256 == hashlib.sha256(candidate_data).hexdigest()

    verified = verify_image_repeat_artifact(
        source.read_bytes(),
        result.data,
        manifest,
        provider_candidate_data=candidate_data,
    )
    assert verified.raw_repair_png is not None
    assert verified.alpha_reconstructed_repair_png is not None
    assert verified.provider_interior_png is not None
    assert verified.repair_png is not None
    assert verified.endpoint_anchor_span_px == construction.endpoint_anchor_span_px
    assert verified.anchored_repair_changed_pixels is not None
    assert verified.anchored_repair_changed_pixels > 0
    assert verified.alpha_reconstructed_changed_pixels is not None
    assert lineage.raw_repair_sha256 == hashlib.sha256(verified.raw_repair_png).hexdigest()
    assert (
        lineage.alpha_reconstructed_repair_sha256
        == hashlib.sha256(verified.alpha_reconstructed_repair_png).hexdigest()
    )
    assert (
        lineage.provider_interior_sha256
        == hashlib.sha256(verified.provider_interior_png).hexdigest()
    )
    assert lineage.repair_sha256 == hashlib.sha256(verified.repair_png).hexdigest()

    candidate_record = ArtifactProvenance.model_validate_json(candidate_sidecar)
    assert candidate_record.provider == construction.provider
    assert candidate_record.model == construction.model
    assert candidate_record.attempts == construction.attempts
    assert candidate_record.component.name == "@stage-gen/image-repeat"
    assert candidate_record.component.version == "0.0.0"
    assert candidate_record.artifact is not None
    assert candidate_record.artifact.sha256 == construction.provider_candidate.sha256
    assert candidate_record.artifact.bytes == construction.provider_candidate.bytes
    assert candidate_record.artifact.media_type == "image/png"
    assert candidate_record.params == {
        "algorithm": construction.algorithm,
        "axis": axis,
        "context_span_px": construction.context_span_px,
        "repair_span_px": construction.repair_span_px,
        "mask_semantics": construction.mask_semantics,
        "alpha_reconstruction_algorithm": construction.alpha_reconstruction_algorithm,
        "provider_responsibility": "rgb_appearance",
        "component_responsibility": "alpha_topology_and_endpoint_continuity",
        "metadata": {"token": "[REDACTED]"},
    }
    assert candidate_record.validation == {
        "provider_dimensions": [request.width, request.height],
        "provider_media_type": "image/png",
        "exact_provider_candidate_preserved": True,
        "provider_candidate_role": "rgb_appearance_input",
    }
    assert candidate_record.response == {
        "media_type": "image/png",
        "bytes": len(candidate_data),
        "request_id": "edit-2",
    }

    repeat_record = ArtifactProvenance.model_validate_json(
        await _read_bytes(result.provenance_path)
    )
    assert candidate_record.rights == repeat_record.rights
    assert repeat_record.response == candidate_record.response
    assert repeat_record.params["endpoint_anchor_algorithm"] == (
        construction.endpoint_anchor_algorithm
    )
    assert repeat_record.params["endpoint_anchor_span_px"] == 1
    assert repeat_record.params["endpoint_anchors_reimposed"] is True
    assert repeat_record.params["alpha_reconstruction_algorithm"] == (
        construction.alpha_reconstruction_algorithm
    )
    assert repeat_record.params["alpha_topology_reconstructed"] is True
    assert repeat_record.params["provider_rgb_interior_preserved"] is True
    assert repeat_record.params["deterministically_reconstructible"] is True
    assert repeat_record.params["provider_candidate"] == construction.provider_candidate.model_dump(
        mode="json"
    )
    assert repeat_record.validation["immutable_regions_reimposed"] is True
    assert repeat_record.validation["provider_context_changed_pixels"] > 0
    assert repeat_record.validation["endpoint_anchors_reimposed"] is True
    assert repeat_record.validation["alpha_topology_reconstructed"] is True
    assert repeat_record.validation["alpha_reconstructed_changed_pixels"] == (
        verified.alpha_reconstructed_changed_pixels
    )
    assert repeat_record.validation["provider_rgb_interior_preserved"] is True
    assert repeat_record.validation["deterministically_reconstructible"] is True
    assert repeat_record.validation["anchored_repair_changed_pixels"] == (
        verified.anchored_repair_changed_pixels
    )
    _assert_content_input(repeat_record, candidate_path.name, candidate_data, "image/png")
    _assert_content_input(
        repeat_record,
        candidate_provenance_path.name,
        candidate_sidecar,
        "application/json",
    )

    manifest_record = ArtifactProvenance.model_validate_json(
        await _read_bytes(result.manifest_provenance_path)
    )
    assert manifest_record.params["construction"] == construction.model_dump(mode="json")
    assert manifest_record.validation["provider_candidate_binding"] is True
    assert manifest_record.validation["repair_reconstruction_binding"] is True
    _assert_content_input(manifest_record, candidate_path.name, candidate_data, "image/png")
    _assert_content_input(
        manifest_record,
        candidate_provenance_path.name,
        candidate_sidecar,
        "application/json",
    )

    legacy_v3 = construction.model_dump(mode="json")
    legacy_v3["algorithm"] = "endpoint-conditioned-anchored-repair-v3"
    legacy_v3["provider_interior_preserved"] = legacy_v3.pop("provider_rgb_interior_preserved")
    legacy_v3.pop("alpha_reconstruction_algorithm")
    legacy_v3.pop("alpha_topology_reconstructed")
    legacy_v3.pop("deterministically_reconstructible")
    with pytest.raises(ValidationError):
        ImageRepeatRepairConstruction.model_validate(legacy_v3)


def test_deterministic_alpha_and_coverage_policies_reject_transparent_discontinuity() -> None:
    image = Image.new("RGBA", (6, 4), _GREEN)
    for y in range(image.height):
        image.putpixel((0, y), (40, 50, 60, 255))
        image.putpixel((1, y), (40, 50, 60, 255))
        image.putpixel((4, y), (40, 50, 60, 0))
        image.putpixel((5, y), (40, 50, 60, 0))
    data = _png(image)
    report = validate_image_repeat(
        data,
        axis="x",
        alpha_policy="preserve",
        coverage_policy="continuous",
        validation_policy=ImageRepeatValidationPolicy(),
    )
    assert report.verdict == "reject"
    assert "unintended_transparent_gap" in report.failure_codes
    assert "alpha_halo_or_matte_contamination" in report.failure_codes

    opaque_report = validate_image_repeat(
        data,
        axis="x",
        alpha_policy="require_opaque",
        coverage_policy="sparse_allowed",
        validation_policy=ImageRepeatValidationPolicy(),
    )
    assert opaque_report.verdict == "reject"
    assert "alpha_halo_or_matte_contamination" in opaque_report.failure_codes


@pytest.mark.parametrize(
    ("axis", "size", "expected_size"),
    [
        ("x", (6, 4), (18, 4)),
        ("y", (4, 6), (4, 18)),
    ],
)
def test_three_repeat_preview_is_opaque_and_hidden_rgb_invariant(
    axis: Literal["x", "y"],
    size: tuple[int, int],
    expected_size: tuple[int, int],
) -> None:
    neutral_hidden_rgb = Image.new("RGBA", size, (0, 0, 0, 0))
    magenta_hidden_rgb = Image.new("RGBA", size, (255, 0, 255, 0))

    neutral_preview = build_three_repeat_preview(_png(neutral_hidden_rgb), axis=axis)
    magenta_preview = build_three_repeat_preview(_png(magenta_hidden_rgb), axis=axis)

    assert neutral_preview == magenta_preview
    decoded = _decode(neutral_preview)
    assert decoded.mode == "RGB"
    assert decoded.size == expected_size


@pytest.mark.parametrize("axis", ["x", "y"])
def test_three_repeat_preview_preserves_opaque_pixels_in_all_three_copies(
    axis: Literal["x", "y"],
) -> None:
    size = (6, 4) if axis == "x" else (4, 6)
    source = Image.new("RGBA", size)
    for y in range(source.height):
        for x in range(source.width):
            source.putpixel((x, y), (x * 30, y * 40, 120, 255))

    preview = _decode(build_three_repeat_preview(_png(source), axis=axis))
    expected = source.convert("RGB").tobytes()
    for index in range(3):
        box = (
            (index * source.width, 0, (index + 1) * source.width, source.height)
            if axis == "x"
            else (0, index * source.height, source.width, (index + 1) * source.height)
        )
        assert preview.crop(box).tobytes() == expected


def test_three_repeat_preview_makes_partial_alpha_visible_against_checkerboard() -> None:
    size = (4, 2)
    transparent = Image.new("RGBA", size, (30, 90, 210, 0))
    partial = Image.new("RGBA", size, (30, 90, 210, 128))
    opaque = Image.new("RGBA", size, (30, 90, 210, 255))

    background = _decode(build_three_repeat_preview(_png(transparent), axis="x"))
    blended = _decode(build_three_repeat_preview(_png(partial), axis="x"))
    foreground = _decode(build_three_repeat_preview(_png(opaque), axis="x"))

    for y in range(size[1]):
        for x in range(size[0]):
            background_pixel = cast(tuple[int, int, int], background.getpixel((x, y)))
            blended_pixel = cast(tuple[int, int, int], blended.getpixel((x, y)))
            foreground_pixel = cast(tuple[int, int, int], foreground.getpixel((x, y)))
            assert blended_pixel not in (background_pixel, foreground_pixel)
            assert all(
                min(background_channel, foreground_channel)
                < blended_channel
                < max(background_channel, foreground_channel)
                for background_channel, blended_channel, foreground_channel in zip(
                    background_pixel,
                    blended_pixel,
                    foreground_pixel,
                    strict=True,
                )
            )


@pytest.mark.asyncio
async def test_success_bundle_rolls_back_when_persistence_checkpoint_fails(tmp_path: Path) -> None:
    source = _source_with_provenance(tmp_path / "source", axis="x", seamless=True)
    output_dir = tmp_path / "out"

    def fail_after_manifest(name: str) -> None:
        if name == "installed:manifest":
            raise RuntimeError("injected persistence failure")

    with pytest.raises(RuntimeError, match="injected persistence failure"):
        await ImageRepeatService(
            FakeIntendedLoopReviewer(),
            persistence_checkpoint=fail_after_manifest,
        ).admit(_admission_request(source, output_dir, axis="x"))

    assert _directory_names(output_dir) == []


@pytest.mark.asyncio
async def test_repaired_bundle_rolls_back_provider_candidate_and_all_success_files(
    tmp_path: Path,
) -> None:
    source = _source_with_provenance(tmp_path / "source", axis="x", seamless=False)
    output_dir = tmp_path / "out"

    def fail_after_provider_candidate_provenance(name: str) -> None:
        if name == "installed:provider-candidate-provenance":
            raise RuntimeError("injected provider-candidate persistence failure")

    with pytest.raises(RuntimeError, match="provider-candidate persistence failure"):
        await ImageRepeatService(
            FakeIntendedLoopReviewer(),
            repair_backend=FakeMaskedImageEditBackend(),
            persistence_checkpoint=fail_after_provider_candidate_provenance,
        ).repair(_repair_request(source, output_dir, axis="x"))

    assert _directory_names(output_dir) == []


@pytest.mark.asyncio
async def test_repair_bounds_derived_provider_candidate_name(tmp_path: Path) -> None:
    source = _source_with_provenance(tmp_path / "source", axis="x", seamless=False)
    request = ImageRepeatRepairRequest(
        source_path=source,
        source_ref=source.name,
        output_dir=tmp_path / "out",
        artifact_name=f"{'a' * 114}.png",
        manifest_name="long-name.repeat.json",
        axis="x",
        intended_behavior="continuous_foreground_layer",
        prompt="continue the terrain structure between the supplied endpoints",
        context_span_px=2,
        repair_span_px=4,
        alpha_policy="require_opaque",
    )

    result = await ImageRepeatService(
        FakeIntendedLoopReviewer(),
        repair_backend=FakeMaskedImageEditBackend(),
    ).repair(request)

    candidate = Path(cast(str, result.provider_candidate_path))
    candidate_provenance = Path(cast(str, result.provider_candidate_provenance_path))
    assert candidate.name.startswith("image-repeat-provider-")
    assert candidate.name.endswith(".png")
    assert candidate_provenance.name == f"{candidate.name}.meta.json"
    assert len(candidate_provenance.name) <= 128


@pytest.mark.asyncio
async def test_admission_bounds_derived_review_evidence_name(tmp_path: Path) -> None:
    source = _source_with_provenance(tmp_path / "source", axis="x", seamless=True)
    request = ImageRepeatAdmissionRequest(
        source_path=source,
        source_ref=source.name,
        output_dir=tmp_path / "out",
        artifact_name="short.repeat.png",
        manifest_name=f"{'m' * 106}.repeat.json",
        axis="x",
        intended_behavior="continuous_foreground_layer",
    )

    result = await ImageRepeatService(
        FakeIntendedLoopReviewer(persist_evidence=True),
    ).admit(request)

    manifest = ImageRepeatManifest.model_validate_json(await _read_text(result.manifest_path))
    review = manifest.validation.intended_loop.review_artifact
    assert review is not None
    assert review.path.startswith("image-repeat-review-")
    assert review.path.endswith(".json")
    assert review.provenance_path == f"{review.path}.meta.json"
    assert len(review.provenance_path) <= 128


def test_repair_contract_rejects_span_too_short_for_endpoint_anchors() -> None:
    with pytest.raises(ValueError, match="from 4 to"):
        ImageRepeatRepairRequest(
            source_path="source.png",
            output_dir="out",
            artifact_name="layer.repeat.png",
            manifest_name="layer.repeat.json",
            axis="x",
            intended_behavior="continuous abstract pattern",
            prompt="bridge the supplied endpoints",
            context_span_px=2,
            repair_span_px=3,
        )


@pytest.mark.asyncio
async def test_v2_manifest_rejects_camel_case_aliases(tmp_path: Path) -> None:
    source = _source_with_provenance(tmp_path / "source", axis="x", seamless=True)
    result = await ImageRepeatService(FakeIntendedLoopReviewer()).admit(
        _admission_request(source, tmp_path / "out", axis="x")
    )
    payload = cast(
        dict[str, object],
        json.loads(await _read_text(result.manifest_path)),
    )
    payload["schemaVersion"] = payload.pop("schema_version")
    with pytest.raises(ValidationError):
        ImageRepeatManifest.model_validate(payload)

    canonical_payload = cast(dict[str, object], json.loads(await _read_text(result.manifest_path)))
    validation = cast(dict[str, object], canonical_payload["validation"])
    intended_loop = cast(dict[str, object], validation["intended_loop"])
    intended_loop["confidence"] = INTENDED_LOOP_MIN_ACCEPT_CONFIDENCE - 0.01
    with pytest.raises(ValidationError, match="fail-closed minimum"):
        ImageRepeatManifest.model_validate(canonical_payload)


def _admission_request(
    source: Path,
    output_dir: Path,
    *,
    axis: Literal["x", "y"],
) -> ImageRepeatAdmissionRequest:
    return ImageRepeatAdmissionRequest(
        source_path=source,
        source_ref=source.name,
        output_dir=output_dir,
        artifact_name="layer.repeat.png",
        manifest_name="layer.repeat.json",
        axis=axis,
        intended_behavior="continuous_foreground_layer",
        metadata={"token": "review-secret", "caller": "focused-test"},
    )


def _repair_request(
    source: Path,
    output_dir: Path,
    *,
    axis: Literal["x", "y"],
) -> ImageRepeatRepairRequest:
    return ImageRepeatRepairRequest(
        source_path=source,
        source_ref=source.name,
        output_dir=output_dir,
        artifact_name="layer.repeat.png",
        manifest_name="layer.repeat.json",
        axis=axis,
        intended_behavior="continuous_foreground_layer",
        prompt="continue the terrain structure between the supplied endpoints",
        context_span_px=2,
        repair_span_px=4,
        alpha_policy="require_opaque",
        metadata={"token": "edit-secret"},
    )


def _source_with_provenance(
    root: Path,
    *,
    axis: Literal["x", "y"],
    seamless: bool,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    source = root / "layer.png"
    colors = (
        [_RED, _RED, _GREEN, _GREEN, _RED, _RED]
        if seamless
        else [_RED, _RED, _RED, _BLUE, _BLUE, _BLUE]
    )
    if axis == "x":
        image = Image.new("RGBA", (6, 4))
        for x, color in enumerate(colors):
            for y in range(image.height):
                image.putpixel((x, y), color)
    else:
        image = Image.new("RGBA", (4, 6))
        for y, color in enumerate(colors):
            for x in range(image.width):
                image.putpixel((x, y), color)
    write_artifact_with_provenance(
        source,
        BinaryArtifact(data=_png(image), media_type="image/png"),
        ProvenanceInput(
            provider="local",
            model="test-fixture",
            prompt="construct a deterministic image-repeat source",
            refs=[],
            attempts=1,
        ),
    )
    return source


def _provider_candidate(
    request: MaskedImageEditRequest,
    *,
    outcome: Literal["good", "bad"],
    mutate_context: bool,
) -> bytes:
    image = _decode(request.conditioning_image).convert("RGBA")
    pixels = image.load()
    assert pixels is not None
    if request.axis == "x":
        tail = cast(Color, pixels[request.context_span_px - 1, 0])
        head = cast(Color, pixels[request.context_span_px + request.repair_span_px, 0])
        for offset in range(request.repair_span_px):
            color = _provider_repair_color(
                tail,
                head,
                offset=offset,
                repair_span_px=request.repair_span_px,
                outcome=outcome,
            )
            for y in range(request.height):
                pixels[request.context_span_px + offset, y] = color
        if mutate_context:
            for x in (
                *range(request.context_span_px),
                *range(
                    request.context_span_px + request.repair_span_px,
                    request.width,
                ),
            ):
                for y in range(request.height):
                    pixels[x, y] = (250, 240, 10, 255)
    else:
        tail = cast(Color, pixels[0, request.context_span_px - 1])
        head = cast(Color, pixels[0, request.context_span_px + request.repair_span_px])
        for offset in range(request.repair_span_px):
            color = _provider_repair_color(
                tail,
                head,
                offset=offset,
                repair_span_px=request.repair_span_px,
                outcome=outcome,
            )
            for x in range(request.width):
                pixels[x, request.context_span_px + offset] = color
        if mutate_context:
            for y in (
                *range(request.context_span_px),
                *range(
                    request.context_span_px + request.repair_span_px,
                    request.height,
                ),
            ):
                for x in range(request.width):
                    pixels[x, y] = (250, 240, 10, 255)
    if outcome == "bad":
        image = image.crop((0, 0, image.width - 1, image.height))
    return _png(image)


def _provider_repair_color(
    tail: Color,
    head: Color,
    *,
    offset: int,
    repair_span_px: int,
    outcome: Literal["good", "bad"],
) -> Color:
    if outcome == "bad":
        return (255, 0, 255, 0)
    color = tail if offset < repair_span_px // 2 else head
    if offset not in {0, repair_span_px - 1}:
        return color
    return (
        min(255, color[0] + 11),
        min(255, color[1] + 7),
        max(0, color[2] - 9),
        color[3],
    )


def _assert_content_input(
    provenance: ArtifactProvenance,
    ref: str,
    data: bytes,
    media_type: str,
) -> None:
    assert any(
        item.ref == ref
        and item.sha256 == hashlib.sha256(data).hexdigest()
        and item.bytes == len(data)
        and item.media_type == media_type
        and item.source == "content"
        for item in provenance.inputs
    )


def _assert_lower_snake_keys(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            assert isinstance(key, str)
            assert key == key.lower()
            assert "-" not in key
            _assert_lower_snake_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_lower_snake_keys(nested)


def _directory_names(path: Path) -> list[str]:
    if not path.exists():
        return []
    return sorted(item.name for item in path.iterdir())


async def _read_bytes(path: str | Path) -> bytes:
    return await asyncio.to_thread(Path(path).read_bytes)


async def _read_text(path: str | Path) -> str:
    return await asyncio.to_thread(Path(path).read_text, encoding="utf-8")


def _png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", compress_level=9, optimize=False)
    return output.getvalue()


def _decode(data: bytes) -> Image.Image:
    with Image.open(BytesIO(data)) as image:
        image.load()
        return image.copy()
