"""Structured-generation helper: strict schema, wrapper decoding, caller validation.

Caller-side schema validation and the deterministic semantic validator both run
inside the service's single retry owner, so a rejected attempt is retried under
the same six-attempt budget without a nested loop.

What this module owns is the recipe's own voice -- the system prompt the judge
reads -- and the shape of one accepted call. The transport repairs it needs are
shared with the other recipes and live in ``recipes/structured_transport.py``.
"""

from __future__ import annotations

# The system prompt below is tuned prose carried over verbatim from the runs
# that paid for it. Rewrapping it to satisfy the line limit would change the
# bytes a model is sent, which is a correctness question, not a style one.
# ruff: noqa: E501
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

from pydantic import BaseModel, ValidationError

from gnode import (
    StructuredGenerationRequest,
    StructuredGenerationService,
    StructuredOutputSchema,
    StructuredReference,
)
from stage_gen.recipes.structured_transport import (
    decode_completion_wrapper,
    inline_local_schema_refs,
    known_cost,
)

SYSTEM_PROMPT = """You review generated 2D game art for an oblique-camera survival game.

The art is a set of flat billboard sprites that stand upright in a 3D world under a fixed camera pitched about fifty-five degrees down, over a textured ground plane. Every sprite is drawn as if seen from about thirty degrees above horizontal, so a little of each object's top surface reads and its base is a shallow ellipse. Judge whether the set holds one consistent drawing pitch, one consistent drawing scale, and one consistent style, and whether each sprite is a clean isolated cutout with no painted ground under it. Do not hide unsupported assumptions. Return only the strict JSON object requested."""


class StructuredOperation(TypedDict):
    """What one accepted structured call reports back to its node handler.

    Typed because the handler turns ``attempts`` into the node's provider
    operation count and ``usage`` into its cost; a loose mapping there hides a
    wrong key until a run's accounting is already wrong.
    """

    operation_id: str
    elapsed_seconds: float
    attempts: int
    request_id: str | None
    usage: object
    known_cost_usd: float | None
    normalization: dict[str, int]


@dataclass(slots=True)
class AttemptLedger:
    """Every caller-rejected attempt, kept so a failure is diagnosable.

    The service reports that an attempt failed but discards what came back, and
    the interesting question after six burnt attempts is always *what the model
    actually said*. The spike wrote these into an undeclared ``.attempts``
    directory beside the artifact, so a cache restore lost them and the run view
    never saw them; the handler now writes these records to a declared
    ``attempts`` port instead, whether or not anything was refused.
    """

    operation_id: str
    records: list[dict[str, object]] = field(default_factory=list)

    def record(self, value: object, *, stage: str, errors: object) -> None:
        self.records.append(
            {
                "attempt": len(self.records) + 1,
                "failure_stage": stage,
                "errors": errors,
                "decoded": value,
            }
        )


async def generate_structured[T: BaseModel](
    service: StructuredGenerationService[object],
    *,
    model_type: type[T],
    operation_id: str,
    prompt: str,
    artifact_path: Path,
    ledger: AttemptLedger,
    references: tuple[StructuredReference, ...] = (),
    max_tokens: int,
    timeout_seconds: float,
    semantic_validate: Callable[[T], list[str]] | None = None,
    system: str = SYSTEM_PROMPT,
    metadata: Mapping[str, object] | None = None,
) -> tuple[T, StructuredOperation]:
    schema = inline_local_schema_refs(
        StructuredOutputSchema(
            name=operation_id.replace(".", "_"), json_schema=model_type.model_json_schema()
        ).json_schema
    )
    state: dict[str, object] = {"schema_status": "not_run", "semantic_errors": []}

    def record_attempt(value: object, *, stage: str, errors: object) -> None:
        ledger.record(value, stage=stage, errors=errors)

    def parse_once(value: object) -> T:
        stats: Counter[str] = Counter()
        normalized = decode_completion_wrapper(value, stats)
        state["normalization"] = dict(stats)
        try:
            parsed = model_type.model_validate(normalized)
        except ValidationError as error:
            state["schema_status"] = "fail"
            schema_errors = error.errors(
                include_url=False, include_context=False, include_input=False
            )
            state["schema_errors"] = schema_errors
            record_attempt(normalized, stage="caller_schema_validation", errors=schema_errors)
            raise
        state["schema_status"] = "pass"
        if semantic_validate is not None:
            errors = semantic_validate(parsed)
            state["semantic_errors"] = errors
            if errors:
                record_attempt(normalized, stage="deterministic_acceptance", errors=errors)
                raise ValueError(
                    "structured output failed deterministic acceptance: " + "; ".join(errors[:8])
                )
        return parsed

    def artifact_value(value: object) -> object:
        """What gets persisted is the parsed contract, not the raw envelope."""

        if not isinstance(value, BaseModel):
            raise TypeError("structured artifact value must be the parsed contract model")
        return value.model_dump(mode="json")

    started = time.monotonic()
    result = await service.generate(
        StructuredGenerationRequest(
            prompt=prompt,
            system=system,
            references=references,
            artifact_path=artifact_path,
            schema=StructuredOutputSchema(
                name=operation_id.replace(".", "_"),
                json_schema=schema,
                description=f"oblique survival v0 structured output for {operation_id}",
            ),
            parse=parse_once,
            artifact_value=artifact_value,
            validate=lambda _value: {
                "caller_schema": str(state["schema_status"]),
                "deterministic_acceptance": "pass" if semantic_validate else "not_requested",
                "semantic_revision_loop": False,
            },
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
            metadata={
                "operation_id": operation_id,
                "publication_authorized": False,
                **(dict(metadata) if metadata else {}),
            },
        )
    )
    normalization = state.get("normalization")
    operation: StructuredOperation = {
        "operation_id": operation_id,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "attempts": result.attempts,
        "request_id": result.response_metadata.request_id,
        "usage": result.response_metadata.usage,
        "known_cost_usd": known_cost(result.response_metadata.usage),
        "normalization": normalization if isinstance(normalization, dict) else {},
    }
    return model_type.model_validate(result.value), operation


__all__ = [
    "SYSTEM_PROMPT",
    "AttemptLedger",
    "StructuredOperation",
    "generate_structured",
    "known_cost",
]
