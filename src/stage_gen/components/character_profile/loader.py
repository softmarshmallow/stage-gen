"""Strict JSON/TOML loading and canonicalization for character profiles."""

from __future__ import annotations

import hashlib
import json
import tomllib
from collections.abc import Callable
from datetime import date, datetime, time
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import ValidationError

from ._filesystem import (
    SecureCharacterProfilePathError,
    open_absolute_directory,
    read_absolute_regular_file,
    read_relative_regular_file,
)
from .models import CharacterProfile


class CharacterProfileLoadError(ValueError):
    """Raised when an authored profile or one of its references is invalid."""


class _DuplicateKeyError(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_toml_temporal_values(value: object, location: str = "profile") -> None:
    if isinstance(value, (datetime, date, time)):
        raise CharacterProfileLoadError(
            f"{location} must use a string instead of a TOML native date/time value"
        )
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_toml_temporal_values(item, f"{location}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_toml_temporal_values(item, f"{location}[{index}]")


def _load_mapping_bytes(data: bytes, *, source_suffix: str) -> dict[str, Any]:
    try:
        text = data.decode("utf-8")
    except UnicodeError as error:
        raise CharacterProfileLoadError(f"invalid character profile UTF-8: {error}") from error
    suffix = source_suffix.lower()
    try:
        if suffix == ".toml":
            parsed = tomllib.loads(text)
            _reject_toml_temporal_values(parsed)
        elif suffix == ".json":
            parsed = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
        else:
            raise CharacterProfileLoadError("character profile must use .toml or .json")
    except (json.JSONDecodeError, tomllib.TOMLDecodeError, _DuplicateKeyError) as error:
        raise CharacterProfileLoadError(f"invalid character profile syntax: {error}") from error
    if not isinstance(parsed, dict):
        raise CharacterProfileLoadError("character profile root must be an object/table")
    return parsed


CharacterProfileReferenceReader = Callable[[str], bytes]


def _validate_reference_files(
    profile: CharacterProfile,
    reference_root: Path | None,
    reference_reader: CharacterProfileReferenceReader | None,
) -> None:
    try:
        if reference_reader is not None:
            _validate_reference_digests(profile, reference_reader)
            return
        assert reference_root is not None
        with open_absolute_directory(reference_root, label="character reference_root") as root_fd:
            _validate_reference_digests(
                profile,
                lambda path: read_relative_regular_file(
                    root_fd,
                    PurePosixPath(path).parts,
                    label=f"character reference {path}",
                ),
            )
    except SecureCharacterProfilePathError as error:
        raise CharacterProfileLoadError(str(error)) from error


def _validate_reference_digests(
    profile: CharacterProfile,
    reader: CharacterProfileReferenceReader,
) -> None:
    for reference in profile.references:
        try:
            data = reader(reference.path)
        except SecureCharacterProfilePathError as error:
            raise CharacterProfileLoadError(str(error)) from error
        if hashlib.sha256(data).hexdigest() != reference.sha256:
            raise CharacterProfileLoadError(
                f"character reference digest mismatch: {reference.path}"
            )


def load_character_profile(path: str | Path) -> CharacterProfile:
    """Load one strict profile and validate all local reference bindings."""

    profile_path = Path(path).absolute()
    try:
        data = read_absolute_regular_file(profile_path, label="character profile source")
    except SecureCharacterProfilePathError as error:
        raise CharacterProfileLoadError(f"cannot read character profile: {error}") from error
    return load_character_profile_bytes(
        data,
        source_suffix=profile_path.suffix,
        reference_root=profile_path.parent,
    )


def load_character_profile_bytes(
    data: bytes,
    *,
    source_suffix: str,
    reference_root: str | Path | None = None,
    reference_reader: CharacterProfileReferenceReader | None = None,
) -> CharacterProfile:
    """Parse captured profile bytes and validate references relative to an authored root.

    Callers that bind a source digest should capture the source once, verify that
    exact byte string, and pass it here so parsing cannot observe a second read.
    """

    if (reference_root is None) == (reference_reader is None):
        raise CharacterProfileLoadError(
            "exactly one character profile reference source must be configured"
        )
    mapping = _load_mapping_bytes(data, source_suffix=source_suffix)
    try:
        profile = CharacterProfile.model_validate(mapping)
    except ValidationError as error:
        raise CharacterProfileLoadError(f"invalid character profile contract: {error}") from error
    _validate_reference_files(
        profile,
        Path(reference_root) if reference_root is not None else None,
        reference_reader,
    )
    return profile


def canonical_character_profile_json(profile: CharacterProfile) -> bytes:
    """Serialize a profile as compact, sorted, NFC-normalized UTF-8 JSON bytes."""

    document = profile.model_dump(mode="json", exclude_none=True)
    return json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def character_profile_sha256(profile: CharacterProfile) -> str:
    """Return the digest of the canonical profile JSON bytes."""

    return hashlib.sha256(canonical_character_profile_json(profile)).hexdigest()
