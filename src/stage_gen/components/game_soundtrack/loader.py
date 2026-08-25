"""Strict TOML/JSON loading and canonicalization for game soundtracks."""

from __future__ import annotations

import hashlib
import json
import tomllib
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from stage_gen.components._secure_fs import SecurePathError, read_absolute_regular_file
from stage_gen.components.game_soundtrack.models import GameSoundtrack


class GameSoundtrackLoadError(ValueError):
    """Raised when an authored soundtrack catalog cannot be accepted."""


class _DuplicateKeyError(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_toml_temporal_values(value: object, location: str = "soundtrack") -> None:
    if isinstance(value, (datetime, date, time)):
        raise GameSoundtrackLoadError(
            f"{location} must use a string instead of a TOML native date/time value"
        )
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_toml_temporal_values(item, f"{location}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_toml_temporal_values(item, f"{location}[{index}]")


def load_game_soundtrack_mapping(data: bytes, *, source_suffix: str) -> dict[str, Any]:
    """Decode authored bytes without accepting ambiguous or native-time values."""

    try:
        text = data.decode("utf-8")
    except UnicodeError as error:
        raise GameSoundtrackLoadError(f"invalid game soundtrack UTF-8: {error}") from error
    suffix = source_suffix.lower()
    try:
        if suffix == ".toml":
            parsed = tomllib.loads(text)
            _reject_toml_temporal_values(parsed)
        elif suffix == ".json":
            parsed = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
        else:
            raise GameSoundtrackLoadError("game soundtrack must use .toml or .json")
    except (json.JSONDecodeError, tomllib.TOMLDecodeError, _DuplicateKeyError) as error:
        raise GameSoundtrackLoadError(f"invalid game soundtrack syntax: {error}") from error
    if not isinstance(parsed, dict):
        raise GameSoundtrackLoadError("game soundtrack root must be an object/table")
    return parsed


def load_game_soundtrack_bytes(data: bytes, *, source_suffix: str) -> GameSoundtrack:
    mapping = load_game_soundtrack_mapping(data, source_suffix=source_suffix)
    try:
        return GameSoundtrack.model_validate(mapping)
    except ValidationError as error:
        raise GameSoundtrackLoadError(f"invalid game soundtrack contract: {error}") from error


def load_game_soundtrack(path: str | Path) -> GameSoundtrack:
    """Load one strict soundtrack source without following filesystem symlinks."""

    soundtrack_path = Path(path).absolute()
    try:
        data = read_absolute_regular_file(soundtrack_path, label="game soundtrack source")
    except SecurePathError as error:
        raise GameSoundtrackLoadError(f"cannot read game soundtrack: {error}") from error
    return load_game_soundtrack_bytes(data, source_suffix=soundtrack_path.suffix)


def canonical_game_soundtrack_json(soundtrack: GameSoundtrack) -> bytes:
    """Serialize a soundtrack as compact, sorted, NFC-normalized UTF-8 JSON."""

    document = soundtrack.model_dump(mode="json", exclude_none=True)
    return json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def game_soundtrack_sha256(soundtrack: GameSoundtrack) -> str:
    return hashlib.sha256(canonical_game_soundtrack_json(soundtrack)).hexdigest()


__all__ = [
    "GameSoundtrackLoadError",
    "canonical_game_soundtrack_json",
    "game_soundtrack_sha256",
    "load_game_soundtrack",
    "load_game_soundtrack_bytes",
    "load_game_soundtrack_mapping",
]
