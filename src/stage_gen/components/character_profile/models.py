"""Provider-neutral authored character-profile contracts."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from stage_gen.contracts.artifacts import PersistedContractModel

CharacterProfileRightsStatus = Literal["unreviewed", "restricted", "redistribution-approved"]

_PROFILE_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_REFERENCE_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_MEDIA_TYPE = re.compile(r"^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$")
_UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


def _normalized_text(value: str, label: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    if not normalized or normalized != normalized.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")
    return normalized


def _portable_relative_path(value: str) -> str:
    value = _normalized_text(value, "reference path")
    if "\\" in value:
        raise ValueError("reference path must use portable forward slashes")
    if ":" in value or urlsplit(value).scheme:
        raise ValueError("reference path must not be a URL or URI")
    path = PurePosixPath(value)
    if path.is_absolute() or value != path.as_posix():
        raise ValueError("reference path must be a normalized relative path")
    if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("reference path must not contain empty, dot, or parent segments")
    return value


class CharacterProfileRights(PersistedContractModel):
    """An explicit rights statement that never implies publication approval."""

    status: CharacterProfileRightsStatus
    attribution: list[str] = Field(default_factory=list)
    basis: list[str] = Field(default_factory=list)
    reviewed_at: str | None = None

    @field_validator("attribution", "basis")
    @classmethod
    def validate_text_list(cls, value: list[str], info: Any) -> list[str]:
        return [_normalized_text(item, str(info.field_name)) for item in value]

    @field_validator("reviewed_at")
    @classmethod
    def validate_reviewed_at(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _UTC_TIMESTAMP.fullmatch(value):
            raise ValueError("rights reviewed_at must be a UTC ISO-8601 timestamp")
        try:
            parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError as error:
            raise ValueError("rights reviewed_at must be a valid timestamp") from error
        offset = parsed.utcoffset()
        if offset is None or offset.total_seconds() != 0:
            raise ValueError("rights reviewed_at must be a UTC ISO-8601 timestamp")
        return value

    @model_validator(mode="after")
    def validate_status(self) -> CharacterProfileRights:
        if self.status == "unreviewed":
            if self.reviewed_at is not None:
                raise ValueError("unreviewed rights must not claim a review time")
            return self
        if not self.basis or self.reviewed_at is None:
            raise ValueError(f"{self.status} rights require basis and reviewed_at")
        return self


class CharacterProfileReference(PersistedContractModel):
    """A local, digest-bound reference owned beside an authored profile."""

    reference_id: str = Field(pattern=_REFERENCE_ID.pattern)
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    media_type: str
    rights: CharacterProfileRights

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _portable_relative_path(value)

    @field_validator("media_type")
    @classmethod
    def validate_media_type(cls, value: str) -> str:
        if not _MEDIA_TYPE.fullmatch(value):
            raise ValueError("reference media_type must be a lowercase MIME type")
        return value


class CharacterProfileBinding(PersistedContractModel):
    """Versioned, digest-bound reference to one authored profile source."""

    schema_version: Literal[1]
    kind: Literal["character-profile-binding-v1"]
    ref: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("ref")
    @classmethod
    def validate_ref(cls, value: str) -> str:
        return _portable_relative_path(value)


class CharacterProfile(PersistedContractModel):
    """Stable authored identity and design facts, independent of any recipe."""

    schema_version: Literal[1]
    kind: Literal["character-profile-v1"]
    profile_id: str = Field(pattern=_PROFILE_ID.pattern, max_length=96)
    revision: int = Field(ge=1)
    display_name: str
    age_years: int | None = Field(default=None, ge=0)
    description: str
    visual_identity: str
    wardrobe: str
    invariants: list[str] = Field(min_length=1)
    rights: CharacterProfileRights
    references: list[CharacterProfileReference] = Field(default_factory=list)

    @field_validator("display_name", "description", "visual_identity", "wardrobe")
    @classmethod
    def validate_text(cls, value: str, info: Any) -> str:
        return _normalized_text(value, str(info.field_name))

    @field_validator("invariants")
    @classmethod
    def validate_invariants(cls, value: list[str]) -> list[str]:
        normalized = [_normalized_text(item, "invariant") for item in value]
        if len(set(normalized)) != len(normalized):
            raise ValueError("invariants must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_unique_references(self) -> CharacterProfile:
        ids = [reference.reference_id for reference in self.references]
        paths = [reference.path for reference in self.references]
        if len(set(ids)) != len(ids):
            raise ValueError("reference_id values must be unique")
        if len(set(paths)) != len(paths):
            raise ValueError("reference paths must be unique")
        return self
