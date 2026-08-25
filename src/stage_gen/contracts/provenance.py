"""Current provenance-v2 and artifact-rights models."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from .artifacts import PersistedContractModel

RightsStatus = Literal["unreviewed", "restricted", "redistribution-approved"]
InputSource = Literal["content", "reference"]
_UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


def _non_empty_trimmed(value: str, label: str) -> str:
    if not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")
    return value


def _utc_iso_timestamp(value: str, label: str) -> str:
    if not _UTC_TIMESTAMP.fullmatch(value):
        raise ValueError(f"{label} must be a UTC ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError(f"{label} must be a valid UTC ISO-8601 timestamp") from error
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise ValueError(f"{label} must be a UTC ISO-8601 timestamp")
    return value


class SoftwareIdentity(PersistedContractModel):
    name: str
    version: str

    @field_validator("name", "version")
    @classmethod
    def validate_identity(cls, value: str, info: Any) -> str:
        return _non_empty_trimmed(value, str(info.field_name))


class InputProvenance(PersistedContractModel):
    ref: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source: InputSource
    bytes: int | None = Field(default=None, ge=0)
    media_type: str | None = None

    @field_validator("ref")
    @classmethod
    def validate_ref(cls, value: str) -> str:
        return _non_empty_trimmed(value, "input ref")


class ArtifactDigest(PersistedContractModel):
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    bytes: int = Field(ge=0)
    media_type: str


class ArtifactRights(PersistedContractModel):
    """Explicit rights decision; the model never infers approval."""

    status: RightsStatus
    license_id: str | None
    notice: str
    attribution: list[str]
    basis: list[str]
    reviewed_at: str | None

    @field_validator("notice")
    @classmethod
    def validate_notice(cls, value: str) -> str:
        return _non_empty_trimmed(value, "artifact rights notice")

    @field_validator("license_id")
    @classmethod
    def validate_license(cls, value: str | None) -> str | None:
        return None if value is None else _non_empty_trimmed(value, "artifact rights license_id")

    @field_validator("attribution", "basis")
    @classmethod
    def validate_string_list(cls, value: list[str], info: Any) -> list[str]:
        return [_non_empty_trimmed(item, str(info.field_name)) for item in value]

    @field_validator("reviewed_at")
    @classmethod
    def validate_reviewed_at(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return _utc_iso_timestamp(value, "artifact rights reviewed_at")
        except ValueError as error:
            raise ValueError(
                "artifact rights reviewed_at must be a valid UTC ISO-8601 timestamp or null"
            ) from error

    @model_validator(mode="after")
    def validate_status_fields(self) -> ArtifactRights:
        if self.status == "unreviewed":
            if self.license_id is not None:
                raise ValueError("unreviewed artifact rights must not name a license")
            if self.reviewed_at is not None:
                raise ValueError("unreviewed artifact rights must have reviewed_at=null")
            return self
        if not self.basis:
            raise ValueError(f"{self.status} artifact rights must record at least one basis")
        if self.reviewed_at is None:
            raise ValueError(f"{self.status} artifact rights must record reviewed_at")
        if self.status == "redistribution-approved" and self.license_id is None:
            raise ValueError("redistribution-approved artifact rights must name a license")
        return self


class ArtifactProvenance(PersistedContractModel):
    """Persisted artifact sidecar using the exact current schema version."""

    schema_version: Literal[2]
    provider: str
    model: str
    seed: int | None
    prompt: str
    prompt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    references: list[str]
    refs: list[str]
    inputs: list[InputProvenance]
    params: dict[str, Any]
    validation: dict[str, Any]
    component: SoftwareIdentity
    tool: SoftwareIdentity
    artifact: ArtifactDigest | None = None
    rights: ArtifactRights | None = None
    ts: str
    attempts: int = Field(ge=1, le=6)
    retries: int = Field(ge=0, le=5)
    response: dict[str, Any] | None = None

    @field_validator("ts")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        return _utc_iso_timestamp(value, "provenance ts")

    @model_validator(mode="after")
    def validate_attempt_count(self) -> ArtifactProvenance:
        if self.retries != self.attempts - 1:
            raise ValueError("retries must equal attempts - 1")
        if self.references != self.refs:
            raise ValueError("references and refs must contain the same values")
        return self


class ProvenanceInput(PersistedContractModel):
    """Caller input used to construct a sanitized provenance-v2 sidecar."""

    schema_version: Literal[2] = 2
    provider: str
    model: str
    seed: int | None = None
    prompt: str
    refs: list[str] = Field(default_factory=list)
    inputs: list[InputProvenance] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    validation: dict[str, Any] = Field(default_factory=dict)
    component: SoftwareIdentity = Field(
        default_factory=lambda: SoftwareIdentity(name="@stage-gen/core", version="0.0.0")
    )
    tool: SoftwareIdentity = Field(
        default_factory=lambda: SoftwareIdentity(name="stage-gen", version="0.0.0")
    )
    timestamp: str | None = None
    attempts: int = Field(ge=1, le=6)
    response: dict[str, Any] | None = None
    rights: ArtifactRights | None = None

    @field_validator("provider", "model", "prompt")
    @classmethod
    def validate_required_text(cls, value: str, info: Any) -> str:
        if not value or not value.strip():
            raise ValueError(f"{info.field_name} must be a non-empty string")
        return value

    @field_validator("timestamp")
    @classmethod
    def validate_optional_timestamp(cls, value: str | None) -> str | None:
        return None if value is None else _utc_iso_timestamp(value, "provenance timestamp")
