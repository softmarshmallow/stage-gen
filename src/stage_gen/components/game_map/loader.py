"""Strict TOML/JSON loading for authored game maps and map books."""

from __future__ import annotations

import json
import tomllib
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from stage_gen.components._secure_fs import SecurePathError, read_absolute_regular_file
from stage_gen.components.game_map.models import (
    GameMap,
    GameMapBook,
    ResolvedGameMapBookDocument,
)
from stage_gen.contracts.artifacts import PersistedContractModel


class GameMapLoadError(ValueError):
    """Raised when authored map content cannot be accepted."""


class _DuplicateKeyError(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_toml_temporal_values(value: object, location: str) -> None:
    if isinstance(value, (datetime, date, time)):
        raise GameMapLoadError(
            f"{location} must use a string instead of a TOML native date/time value"
        )
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_toml_temporal_values(item, f"{location}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_toml_temporal_values(item, f"{location}[{index}]")


def load_game_map_mapping(
    data: bytes, *, source_suffix: str, label: str = "game map"
) -> dict[str, Any]:
    try:
        text = data.decode("utf-8")
    except UnicodeError as error:
        raise GameMapLoadError(f"invalid {label} UTF-8: {error}") from error
    suffix = source_suffix.lower()
    try:
        if suffix == ".toml":
            parsed = tomllib.loads(text)
            _reject_toml_temporal_values(parsed, label)
        elif suffix == ".json":
            parsed = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
        else:
            raise GameMapLoadError(f"{label} must use .toml or .json")
    except (json.JSONDecodeError, tomllib.TOMLDecodeError, _DuplicateKeyError) as error:
        raise GameMapLoadError(f"invalid {label} syntax: {error}") from error
    if not isinstance(parsed, dict):
        raise GameMapLoadError(f"{label} root must be an object/table")
    return parsed


def _validate_contract[ContractT: PersistedContractModel](
    model: type[ContractT], data: bytes, *, source_suffix: str, label: str
) -> ContractT:
    mapping = load_game_map_mapping(data, source_suffix=source_suffix, label=label)
    try:
        return model.model_validate(mapping)
    except ValidationError as error:
        raise GameMapLoadError(f"invalid {label} contract: {error}") from error


def load_game_map_bytes(data: bytes, *, source_suffix: str) -> GameMap:
    return _validate_contract(GameMap, data, source_suffix=source_suffix, label="game map")


def load_game_map_book_bytes(data: bytes, *, source_suffix: str) -> GameMapBook:
    return _validate_contract(GameMapBook, data, source_suffix=source_suffix, label="game map book")


def load_resolved_game_map_book_bytes(data: bytes) -> ResolvedGameMapBookDocument:
    return _validate_contract(
        ResolvedGameMapBookDocument,
        data,
        source_suffix=".json",
        label="resolved game map book",
    )


def load_game_map(path: str | Path) -> GameMap:
    map_path = Path(path).absolute()
    try:
        data = read_absolute_regular_file(map_path, label="game map source")
    except SecurePathError as error:
        raise GameMapLoadError(f"cannot read game map: {error}") from error
    return load_game_map_bytes(data, source_suffix=map_path.suffix)


def load_game_map_book(path: str | Path) -> GameMapBook:
    book_path = Path(path).absolute()
    try:
        data = read_absolute_regular_file(book_path, label="game map book source")
    except SecurePathError as error:
        raise GameMapLoadError(f"cannot read game map book: {error}") from error
    return load_game_map_book_bytes(data, source_suffix=book_path.suffix)


def canonical_contract_json(contract: PersistedContractModel) -> bytes:
    return json.dumps(
        contract.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_game_map_json(game_map: GameMap) -> bytes:
    return canonical_contract_json(game_map)


def canonical_game_map_book_json(book: GameMapBook) -> bytes:
    return canonical_contract_json(book)


def canonical_resolved_game_map_book_json(book: ResolvedGameMapBookDocument) -> bytes:
    return canonical_contract_json(book)


__all__ = [
    "GameMapLoadError",
    "canonical_game_map_book_json",
    "canonical_game_map_json",
    "canonical_resolved_game_map_book_json",
    "load_game_map",
    "load_game_map_book",
    "load_game_map_book_bytes",
    "load_game_map_bytes",
    "load_game_map_mapping",
    "load_resolved_game_map_book_bytes",
]
