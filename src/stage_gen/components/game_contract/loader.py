"""Strict TOML/JSON loading and canonicalization for authored game contracts.

Deliberately the same shape as `character_profile.loader`, down to the duplicate-key and native-
date rejections. Two authored-contract loaders that behaved differently on the same malformed
file would be a trap for whoever wrote the second file, so the rules are copied on purpose and
the divergences are only the ones the contract itself forces: a game contract has no local media
references to digest, and it must additionally clear the closed vocabulary.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from stage_gen.components._secure_fs import (
    SecurePathError,
    read_absolute_regular_file,
)
from stage_gen.components.game_contract.models import GameContract
from stage_gen.components.game_contract.vocabulary import (
    LoadedGameVocabulary,
    load_game_vocabulary,
)


class GameContractLoadError(ValueError):
    """Raised when an authored game contract is unreadable, malformed, or unapproved."""


class _DuplicateKeyError(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_toml_temporal_values(value: object, location: str = "game") -> None:
    """Refuse TOML's native dates.

    They decode to Python datetimes, which a strict pydantic string field rejects with a message
    about types rather than about the file. Refusing them here names the field and says what to
    write instead.
    """

    if isinstance(value, (datetime, date, time)):
        raise GameContractLoadError(
            f"{location} must use a string instead of a TOML native date/time value"
        )
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_toml_temporal_values(item, f"{location}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_toml_temporal_values(item, f"{location}[{index}]")


def load_game_contract_mapping(data: bytes, *, source_suffix: str) -> dict[str, Any]:
    """Decode authored bytes into a plain mapping, refusing ambiguous documents."""

    try:
        text = data.decode("utf-8")
    except UnicodeError as error:
        raise GameContractLoadError(f"invalid game contract UTF-8: {error}") from error
    suffix = source_suffix.lower()
    try:
        if suffix == ".toml":
            parsed = tomllib.loads(text)
            _reject_toml_temporal_values(parsed)
        elif suffix == ".json":
            parsed = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
        else:
            raise GameContractLoadError("game contract must use .toml or .json")
    except (json.JSONDecodeError, tomllib.TOMLDecodeError, _DuplicateKeyError) as error:
        raise GameContractLoadError(f"invalid game contract syntax: {error}") from error
    if not isinstance(parsed, dict):
        raise GameContractLoadError("game contract root must be an object/table")
    return parsed


def load_game_contract_bytes(
    data: bytes,
    *,
    source_suffix: str,
    vocabulary: LoadedGameVocabulary | None = None,
) -> GameContract:
    """Parse captured contract bytes and hold every authored word to the vocabulary.

    Callers that bind a source digest should capture the source once, verify that exact byte
    string, and pass it here, so parsing cannot observe a second read of a file that changed in
    between.
    """

    mapping = load_game_contract_mapping(data, source_suffix=source_suffix)
    try:
        contract = GameContract.model_validate(mapping)
    except ValidationError as error:
        raise GameContractLoadError(f"invalid game contract: {error}") from error
    loaded = vocabulary or load_game_vocabulary()
    try:
        contract.validate_against(loaded.vocabulary)
    except ValueError as error:
        raise GameContractLoadError(f"game contract is not approved vocabulary: {error}") from (
            error
        )
    return contract


def load_game_contract(
    path: str | Path,
    *,
    vocabulary: LoadedGameVocabulary | None = None,
) -> GameContract:
    """Load one strict game contract from an absolute path with confined reads."""

    contract_path = Path(path).absolute()
    try:
        data = read_absolute_regular_file(contract_path, label="game contract source")
    except SecurePathError as error:
        raise GameContractLoadError(f"cannot read game contract: {error}") from error
    return load_game_contract_bytes(
        data,
        source_suffix=contract_path.suffix,
        vocabulary=vocabulary,
    )


def canonical_game_contract_json(contract: GameContract) -> bytes:
    """Serialize a contract as compact, sorted, NFC-normalized UTF-8 JSON bytes."""

    document = contract.model_dump(mode="json", exclude_none=True)
    return json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def game_contract_sha256(contract: GameContract) -> str:
    """Return the digest of the canonical contract JSON bytes."""

    return hashlib.sha256(canonical_game_contract_json(contract)).hexdigest()


__all__ = [
    "GameContractLoadError",
    "canonical_game_contract_json",
    "load_game_contract",
    "load_game_contract_bytes",
    "load_game_contract_mapping",
    "game_contract_sha256",
]
