"""Exact current persisted recipe-run summary contract."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import Field, ValidationError, field_validator, model_validator

from gnode import PersistedContractModel

RUN_SUMMARY_SCHEMA_VERSION = 3
RUN_SUMMARY_KIND = "recipe_run_v3"
MAX_JSON_SAFE_INTEGER = 9_007_199_254_740_991

_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_LOWER_SNAKE_FIELD = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_SAFE_TAG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ARTIFACT_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")


class RecipeRunStage(PersistedContractModel):
    """One executed stage; stages skipped after failure are not serialized."""

    stage: str
    ok: bool
    duration_ms: int = Field(ge=0, le=MAX_JSON_SAFE_INTEGER)
    artifacts: list[str]
    error: str | None = None

    @field_validator("duration_ms", mode="before")
    @classmethod
    def normalize_duration(cls, value: object) -> object:
        return _normalize_semantic_integer(value)

    @field_validator("stage")
    @classmethod
    def validate_stage(cls, value: str) -> str:
        if _IDENTIFIER.fullmatch(value) is None:
            raise ValueError("stage must be a lower-kebab-case identifier")
        return value

    @field_validator("artifacts")
    @classmethod
    def validate_artifacts(cls, value: list[str]) -> list[str]:
        for item in value:
            validate_run_artifact_ref(item)
        if len(value) != len(set(value)):
            raise ValueError("stage artifacts must be unique")
        return value

    @field_validator("error")
    @classmethod
    def validate_error(cls, value: str | None) -> str | None:
        if value is not None and (not value or value != value.strip()):
            raise ValueError("stage error must be a non-empty trimmed string")
        if value is not None and "\x00" in value:
            raise ValueError("stage error must not contain NUL")
        return value

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        error_was_serialized = "error" in self.model_fields_set
        if self.ok:
            if error_was_serialized:
                raise ValueError("successful stage must omit error")
            return self
        if not error_was_serialized or self.error is None:
            raise ValueError("failed stage must declare error")
        if self.artifacts:
            raise ValueError("failed stage must not publish artifacts")
        return self


class RecipeRunSummary(PersistedContractModel):
    """Strict, closed recipe-run document written to ``run.json``."""

    schema_version: Literal[3]
    kind: Literal["recipe_run_v3"]
    recipe: str
    input: dict[str, Any]
    tag: str
    run_dir: str
    started_at: str
    ended_at: str
    duration_ms: int = Field(ge=0, le=MAX_JSON_SAFE_INTEGER)
    ok: bool
    stages: list[RecipeRunStage] = Field(min_length=1)
    failed_stage: str | None = None

    @field_validator("duration_ms", mode="before")
    @classmethod
    def normalize_duration(cls, value: object) -> object:
        return _normalize_semantic_integer(value)

    @field_validator("recipe")
    @classmethod
    def validate_recipe(cls, value: str) -> str:
        if _IDENTIFIER.fullmatch(value) is None:
            raise ValueError("recipe must be a lower-kebab-case identifier")
        return value

    @field_validator("tag")
    @classmethod
    def validate_tag(cls, value: str) -> str:
        if _SAFE_TAG.fullmatch(value) is None or value in {".", ".."}:
            raise ValueError("tag must be one safe path segment")
        return value

    @field_validator("run_dir")
    @classmethod
    def validate_run_dir(cls, value: str) -> str:
        if _SAFE_TAG.fullmatch(value) is None or value in {".", ".."}:
            raise ValueError("run_dir must be one portable safe path segment")
        return value

    @field_validator("started_at", "ended_at")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        if _UTC_TIMESTAMP.fullmatch(value) is None:
            raise ValueError(
                "run timestamp must be UTC ISO-8601 ending in Z with at most six fractional digits"
            )
        try:
            datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError as error:
            raise ValueError("run timestamp must be a valid UTC ISO-8601 timestamp") from error
        return value

    @field_validator("input")
    @classmethod
    def validate_input_json(cls, value: dict[str, Any]) -> dict[str, Any]:
        _assert_json_value(value, "input")
        if "transparencyMode" in value:
            raise ValueError("input must not declare legacy transparencyMode")
        invalid_fields = sorted(key for key in value if _LOWER_SNAKE_FIELD.fullmatch(key) is None)
        if invalid_fields:
            raise ValueError("input fields must use lower_snake_case: " + ", ".join(invalid_fields))
        if value.get("transparency_mode") not in {"native", "ai", "chroma"}:
            raise ValueError("input.transparency_mode must be native, ai, or chroma")
        return value

    @field_validator("failed_stage")
    @classmethod
    def validate_failed_stage(cls, value: str | None) -> str | None:
        if value is not None and _IDENTIFIER.fullmatch(value) is None:
            raise ValueError("failed_stage must be a lower-kebab-case identifier")
        return value

    @model_validator(mode="after")
    def validate_run_outcome(self) -> Self:
        if self.run_dir != self.tag:
            raise ValueError("run_dir must equal tag")
        started = datetime.fromisoformat(self.started_at[:-1] + "+00:00")
        ended = datetime.fromisoformat(self.ended_at[:-1] + "+00:00")
        if ended < started:
            raise ValueError("ended_at must not precede started_at")

        stage_names = [stage.stage for stage in self.stages]
        if len(stage_names) != len(set(stage_names)):
            raise ValueError("run stages must have unique stage identifiers")

        failed = [stage for stage in self.stages if not stage.ok]
        failed_stage_was_serialized = "failed_stage" in self.model_fields_set
        if self.ok:
            if failed_stage_was_serialized:
                raise ValueError("successful run must omit failed_stage")
            if failed:
                raise ValueError("successful run must contain only successful stages")
            return self

        if not failed_stage_was_serialized or self.failed_stage is None:
            raise ValueError("failed run must declare failed_stage")
        if len(failed) != 1:
            raise ValueError("failed run must contain exactly one failed stage")
        if not self.stages or self.stages[-1].stage != self.failed_stage:
            raise ValueError("failed_stage must identify the final executed stage")
        if failed[0].stage != self.failed_stage:
            raise ValueError("failed_stage must identify the failed stage")
        return self

    def to_dict(self) -> dict[str, Any]:
        """Return the exact persisted shape, omitting outcome-only optional fields."""

        return self.model_dump(mode="json", exclude_none=True)


class RecipeRunSummaryLoadError(ValueError):
    """Raised when a run summary is not the exact current contract."""


class _DuplicateKeyError(ValueError):
    pass


def parse_recipe_run_summary(
    value: object,
    *,
    label: str = "run summary",
) -> RecipeRunSummary:
    """Validate one decoded value as the exact current run-summary contract."""

    try:
        return RecipeRunSummary.model_validate(value)
    except ValidationError as error:
        raise RecipeRunSummaryLoadError(
            f"{label} is not a valid {RUN_SUMMARY_KIND}: {error}"
        ) from error


def load_recipe_run_summary(
    path: str | Path,
    *,
    label: str = "run summary",
) -> RecipeRunSummary:
    """Read UTF-8 JSON, reject ambiguous syntax, and validate the current contract."""

    try:
        text = Path(path).read_text(encoding="utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, ValueError) as error:
        raise RecipeRunSummaryLoadError(f"{label} is not valid JSON: {error}") from error
    return parse_recipe_run_summary(value, label=label)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _assert_json_value(value: object, label: str) -> None:
    if value is None or isinstance(value, (bool, str)):
        return
    if isinstance(value, int):
        if not -MAX_JSON_SAFE_INTEGER <= value <= MAX_JSON_SAFE_INTEGER:
            raise ValueError(f"{label} contains an integer outside the JSON safe range")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{label} contains a non-finite number")
        if value.is_integer() and abs(value) > MAX_JSON_SAFE_INTEGER:
            raise ValueError(f"{label} contains an integer outside the JSON safe range")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_json_value(item, f"{label}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{label} contains a non-string object key")
            _assert_json_value(item, f"{label}.{key}")
        return
    raise ValueError(f"{label} contains a non-JSON value")


def validate_run_artifact_ref(value: str) -> str:
    """Validate one run-local artifact reference as portable relative POSIX syntax."""

    if not value or value != value.strip() or "\x00" in value:
        raise ValueError("stage artifact must be a non-empty trimmed portable reference")
    if value.startswith(("/", "~")) or any(mark in value for mark in ("\\", ":", "?", "#")):
        raise ValueError("stage artifact must be a portable relative POSIX reference")
    segments = value.split("/")
    if any(_ARTIFACT_SEGMENT.fullmatch(segment) is None for segment in segments):
        raise ValueError("stage artifact must be a portable relative POSIX reference")
    return value


def _normalize_semantic_integer(value: object) -> object:
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return value


__all__ = [
    "RUN_SUMMARY_KIND",
    "RUN_SUMMARY_SCHEMA_VERSION",
    "MAX_JSON_SAFE_INTEGER",
    "RecipeRunStage",
    "RecipeRunSummary",
    "RecipeRunSummaryLoadError",
    "load_recipe_run_summary",
    "parse_recipe_run_summary",
    "validate_run_artifact_ref",
]
