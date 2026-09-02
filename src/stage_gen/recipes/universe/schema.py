"""Structured-generation helper: strict schema, wrapper decoding, caller validation.

Caller-side schema validation and the deterministic semantic validator both run
inside the service's single retry owner, so a rejected attempt is retried under
the same six-attempt budget without a nested loop.

Two things here are recipe-local for now and want a better home. The strict
transport cannot carry ``$defs``, so local references are inlined before the
schema is sent; the dialogue recipe solves the same problem its own way, and
one shared canonicalizer should eventually replace both. And OpenRouter
sometimes returns a ``completionState`` envelope around the object it was asked
for; unwrapping that is a transport concern which belongs in the provider
adapter rather than in every caller that might meet it.
"""

from __future__ import annotations

# The system prompt below is tuned prose carried over verbatim from fifteen
# recorded runs. Rewrapping it to satisfy the line limit would risk changing
# the bytes a model is sent, which is a correctness question, not a style one.
# ruff: noqa: E501
import copy
import json
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
from stage_gen.recipes.universe.universe_types import ATTEMPT_LEDGER_KIND

SYSTEM_PROMPT = """You ratify an original storyworld for visual explanation.

Keep source authorities distinct. The synopsis states explicit world facts. An attached poster, when present, supplies literal visual evidence and art grammar only; its typography, layout, and marketing hierarchy are not world facts. The expansion direction controls how the world is expanded; it is rationale, never evidence. Do not hide unsupported assumptions. Return only the strict JSON object requested."""


def inline_local_schema_refs(schema: Mapping[str, object]) -> dict[str, object]:
    definitions = schema.get("$defs")
    if not isinstance(definitions, dict):
        return dict(schema)

    def expand(value: object) -> object:
        if isinstance(value, list):
            return [expand(item) for item in value]
        if not isinstance(value, dict):
            return value
        reference = value.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/$defs/"):
            target = definitions.get(reference.removeprefix("#/$defs/"))
            if not isinstance(target, dict):
                raise ValueError(f"unknown local schema reference: {reference}")
            siblings = {key: item for key, item in value.items() if key != "$ref"}
            return expand({**copy.deepcopy(target), **siblings})
        return {str(key): expand(item) for key, item in value.items() if key != "$defs"}

    expanded = expand(dict(schema))
    if not isinstance(expanded, dict):
        raise TypeError("expanded schema root must remain an object")
    return expanded


def decode_completion_wrapper(value: object, stats: Counter[str]) -> object:
    """Unwrap the provider's occasional ``completionState`` envelope."""

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped.startswith("{"):
            return value
        try:
            parsed = json.loads(stripped)
        except ValueError:
            return value
        if not isinstance(parsed, dict) or "completionState" not in parsed:
            return value
        stats["wrapper_strings"] += 1
        return decode_completion_wrapper(parsed, stats)
    if isinstance(value, list):
        return [decode_completion_wrapper(item, stats) for item in value]
    if not isinstance(value, dict):
        return value
    if "completionState" not in value:
        return {str(key): decode_completion_wrapper(item, stats) for key, item in value.items()}
    if value.get("completionState") != "complete":
        stats["incomplete_wrappers"] += 1
        return value
    stats["wrapper_nodes"] += 1
    entries = value.get("entries")
    if isinstance(entries, list):
        decoded: dict[str, object] = {}
        for entry in entries:
            if not isinstance(entry, list) or len(entry) != 2 or not isinstance(entry[0], str):
                stats["malformed_wrappers"] += 1
                return value
            decoded[entry[0]] = decode_completion_wrapper(entry[1], stats)
        return decoded
    items = value.get("items")
    if isinstance(items, list):
        return [decode_completion_wrapper(item, stats) for item in items]
    if "value" in value:
        return decode_completion_wrapper(value["value"], stats)
    stats["malformed_wrappers"] += 1
    return value


def known_cost(usage: object) -> float | None:
    if not isinstance(usage, Mapping):
        return None
    cost = usage.get("cost")
    return float(cost) if isinstance(cost, int | float) and not isinstance(cost, bool) else None


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
    actually said*. The spike wrote these beside the artifact as undeclared
    files; here they ride a declared port instead, so they survive a cache
    restore and appear in the run view like any other output.
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

    def document(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "kind": ATTEMPT_LEDGER_KIND,
            "operation_id": self.operation_id,
            "rejected_attempts": len(self.records),
            "attempts": self.records,
        }

    def encoded(self) -> bytes:
        return (
            json.dumps(self.document(), indent=2, sort_keys=True, ensure_ascii=False, default=str)
            + "\n"
        ).encode("utf-8")


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
                description=f"universe structured output for {operation_id}",
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
    "decode_completion_wrapper",
    "generate_structured",
    "inline_local_schema_refs",
    "known_cost",
]
