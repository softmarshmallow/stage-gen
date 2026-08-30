from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Sequence
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from gnode import RetryExhaustedError, RetryPolicy
from stage_gen.components._types import ProviderResponseMetadata
from stage_gen.components.image_repeat import (
    IMAGE_REPEAT_FAILURE_CODES,
    INTENDED_LOOP_MIN_ACCEPT_CONFIDENCE,
    INTENDED_LOOP_REVIEW_PROMPT_VERSION,
    ImageRepeatDeterministicReport,
    ImageRepeatJoinReport,
    ImageRepeatScaleMetrics,
    IntendedLoopReviewRequest,
    build_three_repeat_preview,
)
from stage_gen.components.structured_generation import (
    ProviderStructuredOutput,
    StructuredGenerationRequest,
    StructuredGenerationService,
)
from stage_gen.orchestration.image_repeat_reviewer import (
    INTENDED_LOOP_REVIEW_SCHEMA_NAME,
    StructuredIntendedLoopReviewer,
)


class _ScriptedStructuredBackend:
    provider = "independent-reviewer"
    model = "vision-review-v1"
    secrets: tuple[str, ...] = ()

    def __init__(self, decoded: Sequence[object]) -> None:
        self._decoded = list(decoded)
        self.requests: list[StructuredGenerationRequest[object]] = []
        self.closed = False

    async def generate_once(
        self, request: StructuredGenerationRequest[object]
    ) -> ProviderStructuredOutput:
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self._decoded) - 1)
        decoded = self._decoded[index]
        return ProviderStructuredOutput(
            decoded=decoded,
            raw_text=json.dumps(decoded),
            response_metadata=ProviderResponseMetadata(request_id=f"review-{len(self.requests)}"),
        )

    async def aclose(self) -> None:
        self.closed = True


def _three_repeat_preview() -> bytes:
    repeat = Image.new("RGBA", (4, 3), (24, 48, 96, 255))
    repeat.putpixel((0, 1), (80, 120, 160, 192))
    buffer = BytesIO()
    repeat.save(buffer, format="PNG")
    return build_three_repeat_preview(buffer.getvalue(), axis="x")


def _deterministic_report() -> ImageRepeatDeterministicReport:
    scale = ImageRepeatScaleMetrics(
        scale=1.0,
        boundary_width_px=2,
        color_mae=0.0,
        color_p95=0.0,
        color_max=0.0,
        gradient_mae=0.0,
        gradient_p95=0.0,
        gradient_max=0.0,
        alpha_mae=0.0,
        alpha_p95=0.0,
        alpha_max=0.0,
        coverage_mismatch_ratio=0.0,
        internal_color_p95=0.0,
        color_limit=0.25,
        gradient_limit=0.35,
        alpha_limit=0.2,
        coverage_limit=0.1,
    )
    return ImageRepeatDeterministicReport(
        axis="x",
        verdict="pass",
        alpha_policy="preserve",
        coverage_policy="continuous",
        source_immutable=True,
        joins=[
            ImageRepeatJoinReport(
                name="wrap",
                verdict="pass",
                scales=[scale],
                failure_codes=[],
            )
        ],
        failure_codes=[],
    )


def _request(tmp_path: Path) -> IntendedLoopReviewRequest:
    preview = _three_repeat_preview()
    return IntendedLoopReviewRequest(
        preview_png=preview,
        preview_sha256=sha256(preview).hexdigest(),
        judged_sha256="a" * 64,
        criteria_sha256="b" * 64,
        axis="x",
        intended_behavior="continuous_opaque_background",
        deterministic_report=_deterministic_report(),
        review_artifact_path=tmp_path / "candidate.loop-review.json",
    )


def _reviewer(
    backend: _ScriptedStructuredBackend,
) -> StructuredIntendedLoopReviewer:
    service = StructuredGenerationService[object](
        backend,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    return StructuredIntendedLoopReviewer(
        service,
        provider=backend.provider,
        model=backend.model,
        secrets=backend.secrets,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "decoded",
    [
        {
            "verdict": "reject",
            "confidence": 0.98,
            "failure_codes": ["visible_boundary_pop"],
            "evidence": "A bright vertical edge appears at both joins.",
        },
        {
            "verdict": "uncertain",
            "confidence": 0.31,
            "failure_codes": ["insufficient_evidence"],
            "evidence": "The displayed scale does not resolve the alpha edge.",
        },
    ],
)
async def test_valid_negative_or_uncertain_verdict_returns_without_retry(
    tmp_path: Path, decoded: dict[str, object]
) -> None:
    backend = _ScriptedStructuredBackend([decoded])
    reviewer = _reviewer(backend)

    review = await reviewer.review(_request(tmp_path))

    assert review.verdict == decoded["verdict"]
    assert review.failure_codes == tuple(decoded["failure_codes"])  # type: ignore[arg-type]
    assert len(backend.requests) == 1
    sidecar = json.loads((tmp_path / "candidate.loop-review.json.meta.json").read_text())
    assert sidecar["attempts"] == 1
    assert sidecar["validation"]["semantic_verdict"] == decoded["verdict"]


@pytest.mark.asyncio
async def test_malformed_verdict_is_retried_by_structured_service(tmp_path: Path) -> None:
    backend = _ScriptedStructuredBackend(
        [
            {
                "verdict": "reject",
                "confidence": 0.9,
                "failure_codes": [],
                "evidence": "This reject is structurally inconsistent.",
            },
            {
                "verdict": "reject",
                "confidence": 0.9,
                "failure_codes": ["structure_or_horizon_reset"],
                "evidence": "The horizon jumps vertically at the join.",
            },
        ]
    )
    reviewer = _reviewer(backend)

    review = await reviewer.review(_request(tmp_path))

    assert review.verdict == "reject"
    assert review.failure_codes == ("structure_or_horizon_reset",)
    assert len(backend.requests) == 2
    sidecar = json.loads((tmp_path / "candidate.loop-review.json.meta.json").read_text())
    assert sidecar["attempts"] == 2


@pytest.mark.asyncio
async def test_repeated_low_confidence_accept_fails_closed_in_structured_retry_owner(
    tmp_path: Path,
) -> None:
    decoded = {
        "verdict": "accept",
        "confidence": INTENDED_LOOP_MIN_ACCEPT_CONFIDENCE - 0.01,
        "failure_codes": [],
        "evidence": "The joins look usable, but the evidence is not sufficiently confident.",
    }
    backend = _ScriptedStructuredBackend([decoded])
    reviewer = _reviewer(backend)
    request = _request(tmp_path)

    with pytest.raises(RetryExhaustedError, match="schema validation") as captured:
        await reviewer.review(request)

    assert captured.value.attempts == 6
    assert len(backend.requests) == 6
    assert not await asyncio.to_thread(Path(request.review_artifact_path).exists)
    assert not await asyncio.to_thread(Path(f"{request.review_artifact_path}.meta.json").exists)


@pytest.mark.asyncio
async def test_exact_preview_and_digest_bound_criteria_use_strict_snake_case_schema(
    tmp_path: Path,
) -> None:
    decoded = {
        "verdict": "accept",
        "confidence": 0.96,
        "failure_codes": [],
        "evidence": "Both joins continue naturally and cadence is not conspicuous.",
    }
    backend = _ScriptedStructuredBackend([decoded])
    reviewer = _reviewer(backend)
    request = _request(tmp_path)

    review = await reviewer.review(request)

    assert review.artifact_path == str(request.review_artifact_path)
    assert review.provenance_path == f"{request.review_artifact_path}.meta.json"
    assert review.response_metadata.request_id == "review-1"
    structured_request = backend.requests[0]
    assert structured_request.system is not None
    assert structured_request.prompt is not None
    assert structured_request.schema.name == INTENDED_LOOP_REVIEW_SCHEMA_NAME
    assert structured_request.schema.strict is True
    properties = structured_request.schema.json_schema["properties"]
    assert isinstance(properties, dict)
    assert set(properties) == {"verdict", "confidence", "failure_codes", "evidence"}
    verdict_property = properties["verdict"]
    assert isinstance(verdict_property, dict)
    assert set(verdict_property) == {"$ref"}
    assert structured_request.schema.json_schema["additionalProperties"] is False
    assert structured_request.schema.json_schema["required"] == [
        "verdict",
        "confidence",
        "failure_codes",
        "evidence",
    ]
    definitions = structured_request.schema.json_schema["$defs"]
    assert isinstance(definitions, dict)
    verdict_definition = definitions["ImageRepeatReviewVerdict"]
    failure_definition = definitions["ImageRepeatFailureCode"]
    assert isinstance(verdict_definition, dict)
    assert isinstance(failure_definition, dict)
    assert verdict_definition["enum"] == [
        "accept",
        "reject",
        "uncertain",
    ]
    assert failure_definition["enum"] == list(IMAGE_REPEAT_FAILURE_CODES)

    assert len(structured_request.references) == 1
    reference = structured_request.references[0]
    assert reference.provenance_ref == f"sha256:{request.preview_sha256}"
    prefix, encoded = reference.url.split(",", 1)
    assert prefix == "data:image/png;base64"
    assert base64.b64decode(encoded, validate=True) == request.preview_png
    assert "both joins" in structured_request.prompt
    assert "one complete period" in structured_request.prompt
    assert "continuous_opaque_background" in structured_request.prompt
    assert f"{INTENDED_LOOP_MIN_ACCEPT_CONFIDENCE:.2f}" in structured_request.prompt
    forbidden_generic_policy = ("game", "gameplay", "camera", "shader", "foreground")
    combined_instructions = f"{structured_request.system}\n{structured_request.prompt}".lower()
    assert all(word not in combined_instructions for word in forbidden_generic_policy)
    assert "only caller-specific semantic context" in structured_request.prompt
    assert "neutral checkerboard" in structured_request.system.lower()
    assert "neutral checkerboard" in structured_request.prompt.lower()
    assert "not candidate content" in structured_request.system.lower()
    assert "not candidate content" in structured_request.prompt.lower()
    assert "texture, cadence" in structured_request.system.lower()
    assert "texture, or cadence" in structured_request.prompt.lower()
    assert "Deterministic seam report" not in structured_request.prompt
    assert '"validator_version"' not in structured_request.prompt
    assert "single-axis-continuity-v2" not in structured_request.prompt
    assert '"verdict":"pass"' not in structured_request.prompt
    assert structured_request.metadata[
        "deterministic_report"
    ] == request.deterministic_report.model_dump(mode="json")

    assert json.loads((tmp_path / "candidate.loop-review.json").read_text()) == decoded
    sidecar = json.loads((tmp_path / "candidate.loop-review.json.meta.json").read_text())
    assert sidecar["schema_version"] == 2
    assert sidecar["refs"] == [f"sha256:{request.preview_sha256}"]
    assert sidecar["inputs"] == [
        {
            "ref": f"sha256:{request.preview_sha256}",
            "sha256": request.preview_sha256,
            "source": "content",
            "bytes": len(request.preview_png),
            "media_type": "image/png",
        }
    ]
    assert sidecar["validation"]["judged_sha256"] == request.judged_sha256
    assert sidecar["validation"]["criteria_sha256"] == request.criteria_sha256
    assert sidecar["validation"]["minimum_accept_confidence"] == (
        INTENDED_LOOP_MIN_ACCEPT_CONFIDENCE
    )
    assert sidecar["validation"]["review_prompt_version"] == (INTENDED_LOOP_REVIEW_PROMPT_VERSION)
    expected_report_sha256 = sha256(
        json.dumps(
            request.deterministic_report.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    assert sidecar["validation"]["deterministic_report_sha256"] == expected_report_sha256


@pytest.mark.asyncio
async def test_close_delegates_to_the_structured_retry_owner(tmp_path: Path) -> None:
    del tmp_path
    backend = _ScriptedStructuredBackend([])
    reviewer = _reviewer(backend)

    await reviewer.aclose()

    assert backend.closed is True
