"""The structured-generation designer loop that drives the chunk grammar.

The prompt is BUILT FROM THE PROFILE. There is no game constant in this file: no tile size, no
camera, no fixed climbable rise, no unassisted step height. Everything the model is told is read
out of the :class:`PlatformerProfile` it was handed, which is the only reason one designer can
serve two games.

The service is injected. Building it is the caller's job, because a component may not reach into
orchestration to construct a provider.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gnode import (
    StructuredGenerationRequest,
    StructuredGenerationService,
)
from stage_gen.components.platformer_map_design.capabilities import PlatformerProfile
from stage_gen.components.platformer_map_design.design import DesignedMap, check
from stage_gen.components.platformer_map_design.grammar import (
    build_chunk_prompt,
    build_chunk_schema,
    expand_chunks,
    translate,
)

#: Composition is a long single call; the transport timeout is generous on purpose.
DESIGN_TIMEOUT_SECONDS = 900.0
#: How many validator problems are quoted back to the model. More than this and the feedback
#: stops reading as a fix list.
MAX_QUOTED_PROBLEMS = 6


@dataclass(frozen=True)
class DesignBrief:
    """What the caller wants, as intent rather than instruction.

    Naming a reference beat every mechanical description this was measured against: prescribing
    cluster counts and platform lengths produced levels that executed the recipe, while naming a
    reference produced platform lengths varying 5..24 instead of a uniform 7. Say what the level
    should feel like and leave composition to the model; the profile already fences correctness.
    """

    intent: str
    #: Optional per-level shape, e.g. "a valley" or "two peaks".
    shape: str = ""
    columns: int | None = None


@dataclass
class DesignAttempt:
    designed: DesignedMap | None
    problems: list[str]
    attempt: int
    payload_chars: int


def _require_mapping(decoded: object) -> Mapping[str, object]:
    """Reject a payload that is not a JSON object, INSIDE the single retry owner.

    ``StructuredGenerationService`` calls ``parse`` within its retry budget and persists the
    artifact and its provenance only once ``parse`` has returned. Checking the payload shape
    after ``generate`` returns would therefore leave a successful artifact claiming
    ``schema: caller-validated`` on disk and burn one of the six permitted attempts instead of
    retrying, which is exactly what the repository's single-retry-owner rule forbids.
    """

    if not isinstance(decoded, Mapping):
        raise ValueError("a composed map payload must decode to a JSON object")
    return decoded


def _expand(
    value: Mapping[str, object], profile: PlatformerProfile, columns: int
) -> tuple[DesignedMap, list[str]]:
    """Compile one composition and judge it. Pure and deterministic, so it is safe to repeat."""

    designed, chunk_errors, spans = expand_chunks(value, profile, columns)
    return designed, chunk_errors + translate(check(designed, profile), spans)


async def design_chunks(
    service: StructuredGenerationService[Any],
    profile: PlatformerProfile,
    brief: DesignBrief,
    *,
    artifact_dir: Path,
    seed: int = 1,
    max_attempts: int = 3,
) -> list[DesignAttempt]:
    """Design one map, re-composing with the validator's own complaints as feedback.

    Each iteration here is a SEMANTIC REGENERATION: the previous composition was decoded and
    schema-valid but the game's own validator rejected the level it described, so the model is
    asked to compose again. These are not provider retries. Transport, decoding, and schema
    failures are owned entirely by ``StructuredGenerationService``, which is the single retry
    owner for one provider operation; this loop never nests inside that budget.

    ``artifact_dir`` is required and is the ONLY directory written: the caller owns it, and every
    composition artifact and provenance sidecar lands directly below it.

    Returns every attempt, so a caller can see what the map cost rather than only the winner.
    """

    columns = brief.columns or profile.geometry.columns
    system = build_chunk_prompt(profile, columns)
    schema = build_chunk_schema(profile)
    attempts: list[DesignAttempt] = []
    feedback = ""

    def facts(value: Mapping[str, object]) -> Mapping[str, object]:
        """What the provenance sidecar may honestly claim about this artifact.

        A level the validator rejects is NOT a failure here: raising on a semantic problem would
        re-roll the same request inside the provider's retry budget, and semantic regeneration is
        the loop below's job. Only a payload with no chunks at all is a malformed composition.
        """

        chunks = value.get("chunks")
        if not isinstance(chunks, list) or not chunks:
            raise ValueError("a composed map payload must carry a non-empty 'chunks' array")
        _, problems = _expand(value, profile, columns)
        return {"chunks": len(chunks), "problems": len(problems)}

    for attempt in range(1, max_attempts + 1):
        task = brief.intent
        if brief.shape:
            task += f"\n\nTHIS MAP'S SHAPE: {brief.shape}."
        task += feedback + "\n\nCompose the map."
        request: StructuredGenerationRequest[Mapping[str, object]] = StructuredGenerationRequest(
            prompt=task,
            system=system,
            artifact_path=artifact_dir / f"attempt-{attempt:02d}.json",
            schema=schema,
            parse=_require_mapping,
            validate=facts,
            seed=seed * 100 + attempt,
            timeout_seconds=DESIGN_TIMEOUT_SECONDS,
            metadata={"component": "platformer-map-design", "profile": profile.profile_id},
        )
        result = await service.generate(request)
        value: Mapping[str, object] = result.value
        designed, problems = _expand(value, profile, columns)
        payload_chars = len(json.dumps(value.get("chunks", [])))
        attempts.append(DesignAttempt(designed, problems, attempt, payload_chars))
        if not problems:
            return attempts
        # The validator's messages are already written for a reader; hand them back verbatim
        # rather than paraphrasing, so the model is corrected by the same authority that judges.
        listed = "\n".join(f"  - {problem}" for problem in problems[:MAX_QUOTED_PROBLEMS])
        feedback = (
            "\n\nYour previous attempt was rejected by the game's own validator:\n"
            f"{listed}\n\nFix exactly these and keep everything that was already good."
        )
    return attempts


__all__ = [
    "DESIGN_TIMEOUT_SECONDS",
    "MAX_QUOTED_PROBLEMS",
    "DesignAttempt",
    "DesignBrief",
    "design_chunks",
]
