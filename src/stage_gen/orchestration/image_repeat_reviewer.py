"""Structured-vision adapter for provider-neutral image-repeat review."""

from __future__ import annotations

import base64
import json
import math
from collections.abc import Mapping
from hashlib import sha256
from typing import Self, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from stage_gen.components.image_repeat import (
    INTENDED_LOOP_MIN_ACCEPT_CONFIDENCE,
    INTENDED_LOOP_REVIEW_CONTRACT_VERSION,
    INTENDED_LOOP_REVIEW_PROMPT_VERSION,
    ImageRepeatFailureCode,
    ImageRepeatReviewVerdict,
    IntendedLoopReview,
    IntendedLoopReviewer,
    IntendedLoopReviewRequest,
    validate_backend_label,
)
from stage_gen.components.structured_generation import (
    StructuredGenerationRequest,
    StructuredGenerationService,
    StructuredOutputSchema,
    StructuredReference,
)

INTENDED_LOOP_REVIEW_SCHEMA_NAME = "image_repeat_intended_loop_review_v1"

_FAILURE_CODE_GUIDANCE = """\
- visible_boundary_pop: a join is visibly abrupt or would pop during repeated traversal.
- clipped_or_disconnected_form: a form is cut off or fails to continue across a join.
- unintended_transparent_gap: a gap appears that the declared intended behavior does not allow.
- structure_or_horizon_reset: a horizon, ridge, cloud bank, treeline, ribbon, or other
  structure resets.
- lighting_or_texture_reset: lighting, color, density, grain, or texture changes abruptly.
- mirror_or_reverse_shortcut: a join or repeat uses conspicuous reflection or reversal.
- salient_periodic_cadence: repeated motifs make the one-period cadence conspicuous.
- orientation_or_gravity_break: orientation, flow, or gravity changes implausibly.
- alpha_halo_or_matte_contamination: clipping, fringe, halo, spill, or matte residue is visible.
- intended_behavior_mismatch: the image repeats technically but not as declared.
- insufficient_evidence: the preview does not support a confident accept or reject.
"""


class _StructuredIntendedLoopVerdict(BaseModel):
    """Strict transport schema; semantic rejection is still a valid response."""

    model_config = ConfigDict(extra="forbid", strict=True)

    verdict: ImageRepeatReviewVerdict
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    failure_codes: list[ImageRepeatFailureCode] = Field(max_length=11)
    evidence: str = Field(min_length=1, max_length=600)

    @field_validator("evidence")
    @classmethod
    def validate_evidence(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("evidence must be a non-empty trimmed string")
        return value

    @model_validator(mode="after")
    def validate_verdict_relationships(self) -> Self:
        if len(set(self.failure_codes)) != len(self.failure_codes):
            raise ValueError("failure_codes must not contain duplicates")
        if self.verdict == "accept" and self.failure_codes:
            raise ValueError("an accept verdict must have no failure_codes")
        if self.verdict == "accept" and self.confidence < INTENDED_LOOP_MIN_ACCEPT_CONFIDENCE:
            raise ValueError("an accept verdict must meet the minimum confidence")
        if self.verdict == "reject" and not self.failure_codes:
            raise ValueError("a reject verdict must have at least one failure_code")
        if self.verdict == "uncertain" and "insufficient_evidence" not in self.failure_codes:
            raise ValueError("an uncertain verdict must include insufficient_evidence")
        return self


class StructuredIntendedLoopReviewer(IntendedLoopReviewer):
    """Use strict structured generation as the sole VLM review retry owner.

    ``provider``, ``model``, and ``secrets`` are declared explicitly because the
    existing structured-generation service intentionally does not expose its
    backend. The adapter verifies the declared provider and model against the
    completed structured result before returning an admissible review record.
    """

    def __init__(
        self,
        structured_service: StructuredGenerationService[object],
        *,
        provider: str,
        model: str,
        secrets: tuple[str, ...] = (),
        timeout_seconds: float | None = None,
    ) -> None:
        if not isinstance(secrets, tuple) or any(not isinstance(item, str) for item in secrets):
            raise ValueError("review secrets must be a tuple of strings")
        if timeout_seconds is not None and (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int | float)
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("review timeout_seconds must be positive")
        self._structured = structured_service
        self.provider = validate_backend_label(provider, "provider", secrets=secrets)
        self.model = validate_backend_label(model, "model", secrets=secrets)
        self.secrets = secrets
        self._timeout_seconds = timeout_seconds

    async def review(self, request: IntendedLoopReviewRequest) -> IntendedLoopReview:
        if sha256(request.preview_png).hexdigest() != request.preview_sha256:
            raise ValueError("three-repeat preview bytes do not match preview_sha256")
        report = cast(
            dict[str, object],
            request.deterministic_report.model_dump(mode="json", by_alias=False),
        )
        report_sha256 = _canonical_json_sha256(report)
        prompt = _review_prompt(
            axis=request.axis,
            intended_behavior=request.intended_behavior,
            criteria_sha256=request.criteria_sha256,
        )
        preview_data_url = "data:image/png;base64," + base64.b64encode(request.preview_png).decode(
            "ascii"
        )

        generated = await self._structured.generate(
            StructuredGenerationRequest(
                system=(
                    "You are an independent, fail-closed visual quality gate for single-axis "
                    "image repeat units. Judge only visible evidence in the attached preview "
                    "and the caller-declared intended behavior. Return the strict structured "
                    "verdict and never propose or perform a repair. The deterministic neutral "
                    "checkerboard visualizes transparency and is not candidate content; never "
                    "treat its squares or pattern as candidate texture, cadence, or a defect."
                ),
                prompt=prompt,
                artifact_path=request.review_artifact_path,
                references=(
                    StructuredReference(
                        url=preview_data_url,
                        provenance_ref=f"sha256:{request.preview_sha256}",
                    ),
                ),
                schema=StructuredOutputSchema(
                    name=INTENDED_LOOP_REVIEW_SCHEMA_NAME,
                    description=(
                        "Fail-closed semantic verdict for an exact three-repeat image preview"
                    ),
                    json_schema=_StructuredIntendedLoopVerdict.model_json_schema(),
                    strict=True,
                ),
                parse=_parse_structured_verdict,
                artifact_value=_structured_verdict_value,
                validate=lambda verdict: {
                    "review_contract_version": INTENDED_LOOP_REVIEW_CONTRACT_VERSION,
                    "review_prompt_version": INTENDED_LOOP_REVIEW_PROMPT_VERSION,
                    "verdict_schema": "validated",
                    "preview_sha256": request.preview_sha256,
                    "judged_sha256": request.judged_sha256,
                    "criteria_sha256": request.criteria_sha256,
                    "deterministic_report_sha256": report_sha256,
                    "minimum_accept_confidence": INTENDED_LOOP_MIN_ACCEPT_CONFIDENCE,
                    "semantic_verdict": cast(_StructuredIntendedLoopVerdict, verdict).verdict,
                },
                metadata={
                    "review_contract_version": INTENDED_LOOP_REVIEW_CONTRACT_VERSION,
                    "review_prompt_version": INTENDED_LOOP_REVIEW_PROMPT_VERSION,
                    "axis": request.axis,
                    "intended_behavior": request.intended_behavior,
                    "preview_sha256": request.preview_sha256,
                    "judged_sha256": request.judged_sha256,
                    "criteria_sha256": request.criteria_sha256,
                    "deterministic_report": report,
                    "deterministic_report_sha256": report_sha256,
                    "minimum_accept_confidence": INTENDED_LOOP_MIN_ACCEPT_CONFIDENCE,
                },
                timeout_seconds=self._timeout_seconds,
                cancellation=request.cancellation,
                provenance_schema_version=2,
            )
        )
        if generated.provider != self.provider or generated.model != self.model:
            raise ValueError("structured reviewer identity did not match its declared identity")
        verdict = cast(_StructuredIntendedLoopVerdict, generated.value)
        return IntendedLoopReview(
            verdict=verdict.verdict,
            confidence=verdict.confidence,
            failure_codes=tuple(verdict.failure_codes),
            evidence=verdict.evidence,
            response_metadata=generated.response_metadata,
            artifact_path=str(request.review_artifact_path),
            provenance_path=generated.provenance_path,
        )

    async def aclose(self) -> None:
        await self._structured.aclose()


def _parse_structured_verdict(decoded: object) -> object:
    return _StructuredIntendedLoopVerdict.model_validate(decoded)


def _structured_verdict_value(value: object) -> object:
    verdict = cast(_StructuredIntendedLoopVerdict, value)
    return verdict.model_dump(mode="json")


def _canonical_json_sha256(value: Mapping[str, object]) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _review_prompt(
    *,
    axis: str,
    intended_behavior: str,
    criteria_sha256: str,
) -> str:
    return f"""\
The attached PNG is a deterministic visualization of exactly three adjacent repeats of one
candidate image. Candidate alpha is composited over a neutral checkerboard. The checkerboard is
not candidate content: ignore its squares, phase, and repeated pattern when evaluating joins,
texture, or cadence. It exists only to make transparent and partially transparent pixels visible.
Declared repeat axis: {axis}
Intended behavior: {intended_behavior}
Criteria digest: sha256:{criteria_sha256}

Judge the repeated image itself at the displayed scale. Treat the declared intended behavior as
the only caller-specific semantic context. Do not infer an unstated consumer or assume external
cropping, masking, compositing, or post-processing will hide a defect. Inspect both joins between
the three repeats along the declared axis and consider the visual change over one complete period.

Reject any visible seam or pop, clipped or disconnected structure, unintended transparency,
horizon/structure reset, texture or lighting reset, mirror shortcut, orientation break, alpha
removal artifact, intended-behavior mismatch, or conspicuous one-period cadence. Transparency or
separated forms may be valid only when the declared intended behavior says so. If that behavior
does not provide enough context to decide whether transparency, separation, or structural
continuity is intended, return an uncertain verdict.

Use verdict "accept" only when the intended repeat is visibly usable, confidence is at least
{INTENDED_LOOP_MIN_ACCEPT_CONFIDENCE:.2f}, and failure_codes is an empty list. Below that
confidence, use "uncertain" with insufficient_evidence. Use "reject" with one or more
failure_codes when a defect is visible. Use "uncertain" with insufficient_evidence whenever the
preview does not justify acceptance. A negative or uncertain verdict is final for this review
call; do not suggest a repair.

Failure code meanings:
{_FAILURE_CODE_GUIDANCE}"""


__all__ = [
    "INTENDED_LOOP_REVIEW_SCHEMA_NAME",
    "StructuredIntendedLoopReviewer",
]
