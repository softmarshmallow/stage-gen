"""A family's contact sheet, the reviewer's answer shape, its coherence judge and record.

A review is evidence, never a gate: the build goes on whatever it says. Only a review
that contradicts itself (a failed check naming no finding) is asked again.
"""

from __future__ import annotations

from typing import Any

from ember_hollow_pipeline.preparation_media import _contact_sheet
from ember_hollow_pipeline.reviews import FamilyReview, evaluate_review, family_review_schema
from gnode import Ctx, node


@node(
    "review_sheet",
    inputs={"pictures": "image[]"},
    params={"labels": {"type": "array", "items": {"type": "string"}}},
    outputs={"sheet": "image/png"},
    version=1,
)
def review_sheet(ctx: Ctx) -> dict[str, Any]:
    """Every asset of one family on one labelled sheet, in the order the reviewer is told."""

    pictures = [file.read_bytes() for file in ctx.inputs["pictures"]]
    labels = list(ctx.params["labels"])
    if len(labels) != len(pictures):
        raise ctx.fail(f"{len(labels)} labels for {len(pictures)} pictures")
    return {
        "sheet": ctx.out.bytes(
            _contact_sheet(list(zip(labels, pictures, strict=True))), "image/png"
        )
    }


@node("review_schema", outputs={"schema": "json"}, version=1)
def review_schema(ctx: Ctx) -> dict[str, Any]:
    """The review's answer shape."""

    return {"schema": ctx.out.json(family_review_schema())}


@node("admit_review", inputs={"review": "json"}, judge=True, version=1)
def admit_review(ctx: Ctx) -> dict[str, Any]:
    """The review is well formed and consistent with itself, or it is asked again."""

    try:
        problems = evaluate_review(FamilyReview.model_validate(ctx.read.json("review")))
    except ValueError as error:
        problems = [str(error)]
    if problems:
        ctx.fact("errors", problems)
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("verdict", "accept")
    return {}


@node("review_record", inputs={"review": "json"}, outputs={"review": "json"}, version=1)
def review_record(ctx: Ctx) -> dict[str, Any]:
    """The accepted review, as the evidence the manifest names."""

    review = FamilyReview.model_validate(ctx.read.json("review"))
    return {"review": ctx.out.json(review.model_dump(mode="json"))}


__all__ = ["admit_review", "review_record", "review_schema", "review_sheet"]
