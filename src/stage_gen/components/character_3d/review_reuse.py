"""Host-owned reuse of an earlier exact-artifact verdict inside one run."""

from __future__ import annotations

import copy
import re
from collections.abc import Sequence
from typing import Any, Protocol

from gnode import Node
from stage_gen.components.character_3d.io import canonical_digest

REUSE_FIELDS = {"review_reused_for_unchanged_hash", "review_reused_from_node"}
JsonObject = dict[str, Any]


class ReviewAssets(Protocol):
    def asset(self, asset_id: str) -> JsonObject: ...


class ReviewRun(Protocol):
    @property
    def records(self) -> dict[str, JsonObject]: ...

    @property
    def studio(self) -> ReviewAssets: ...


def review_context(
    stage: str,
    profile: JsonObject,
    criteria: Sequence[str],
    policy: str,
    *,
    route: str,
    schema: JsonObject,
    reference: JsonObject | None = None,
    blocking_facts: JsonObject | None = None,
    quality_bar: JsonObject,
) -> str:
    """Only the host supplies this identity; model output cannot select its key.

    The quality bar is part of the identity: a verdict decided at one height is
    never reused for another.
    """
    return canonical_digest(
        {
            "schema_version": 2,
            "stage": stage,
            "profile": profile,
            "required_criteria": criteria,
            "reviewer_policy": policy,
            "reviewer_route": route,
            "reviewer_schema": schema,
            "reference_sha256": reference["sha256"] if reference else None,
            "blocking_facts": blocking_facts,
            "quality_bar": {
                "level": quality_bar["level"],
                "verdict_character_height_pixels": quality_bar["verdict_character_height_pixels"],
            },
        }
    )


def previous_verdict(
    run: ReviewRun, node: Node, stage: str, asset: JsonObject, context_sha256: str
) -> JsonObject | None:
    """Return the first same-source/context verdict, whether it passed or failed.

    Refuse same-artifact legacy records without an attested context key rather
    than buy a new opinion. Keep the
    original reviewed asset identity/evidence when the producer submits a
    byte-identical alias. Never trust a producer's reuse flag.
    """
    round_number = int(node.params["round"])
    prefix = stage + "_review_"
    for name in sorted(run.records):
        match = re.fullmatch(re.escape(prefix) + "(\\d{2})", name)
        if match is None or not 0 < int(match[1]) < round_number:
            continue
        record = run.records[name]
        if record.get("source_sha256") != asset["source"]["sha256"]:
            continue
        prior_context = record.get("review_context_sha256")
        if not isinstance(prior_context, str) or not re.fullmatch("[0-9a-f]{64}", prior_context):
            raise ValueError("Earlier same-artifact review has no attested context; reroll refused")
        if prior_context != context_sha256:
            continue
        if type(record.get("accepted")) is not bool:
            raise ValueError("Reusable review lacks a boolean verdict")
        original = run.studio.asset(record["asset_id"])
        if original["source"]["sha256"] != asset["source"]["sha256"]:
            raise ValueError("Original reviewed asset changed before verdict reuse")
        return {
            **copy.deepcopy(record),
            "review_reused_for_unchanged_hash": True,
            "review_reused_from_node": name,
        }
    return None
