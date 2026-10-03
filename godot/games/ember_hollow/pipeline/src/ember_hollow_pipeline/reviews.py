"""A family review: one judgement over a whole family's contact sheet, not per image.

A review is evidence, never a gate: a rejection is recorded and the build goes on. What is
held to a rule is only the review's own coherence: a failed check must name a finding.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, Field

from stage_gen.orchestration.structured_transport import inline_local_schema_refs

#: The families a build reviews, each over its own contact sheet.
REVIEW_FAMILIES: Final = ("props", "ground", "actors", "fx", "seasons")
REVIEW_MAX_TOKENS: Final = 12_000


class ReviewFinding(BaseModel):
    subject: str = Field(description="the labelled sprite the finding is about")
    problem: str = Field(description="what is wrong with it, in one sentence")
    blocking: bool = Field(description="true when this makes the sprite unusable in the scene")


class FamilyReview(BaseModel):
    consistent_pitch: bool
    consistent_style: bool
    clean_cutouts: bool
    consistent_state_pairs: bool
    readable_at_play_size: bool
    findings: list[ReviewFinding] = Field(default_factory=list, max_length=24)
    summary: str = Field(min_length=1, max_length=1200)

    @property
    def blocking(self) -> list[ReviewFinding]:
        return [finding for finding in self.findings if finding.blocking]


def evaluate_review(review: FamilyReview) -> list[str]:
    """What makes a review incoherent: a finding with no subject, a failed check with none."""

    problems: list[str] = []
    for finding in review.findings:
        if not finding.subject.strip() or not finding.problem.strip():
            problems.append("every finding needs a subject and a problem")
            break
    flags = (
        review.consistent_pitch,
        review.consistent_style,
        review.clean_cutouts,
        review.consistent_state_pairs,
        review.readable_at_play_size,
    )
    if not all(flags) and not review.findings:
        problems.append("a review that reports a failed check must name at least one finding")
    return problems


def family_review_schema() -> dict[str, Any]:
    """The review's answer shape, with its definitions inlined as the structured route reads."""

    return inline_local_schema_refs(FamilyReview.model_json_schema())


__all__ = [
    "REVIEW_FAMILIES",
    "REVIEW_MAX_TOKENS",
    "FamilyReview",
    "ReviewFinding",
    "evaluate_review",
    "family_review_schema",
]
