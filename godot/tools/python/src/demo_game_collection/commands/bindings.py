"""Private collection adapter for bindings."""

from __future__ import annotations

import argparse
import hashlib
import json
import tomllib
from pathlib import Path
from typing import TextIO

from demo_game_tools.media.soundtrack import (
    ResolvedGameSoundtrack,
    resolve_game_soundtrack_binding,
)
from stage_gen.components._secure_fs import SecurePathError, read_absolute_regular_file
from stage_gen.components.character_profile import (
    ResolvedCharacterProfile,
    resolve_character_profile_binding,
)


def _parse_input_document(text: str, *, suffix: str) -> object:
    if suffix == ".toml":
        return tomllib.loads(text)
    return json.loads(text)


def _secure_cli_source_sha256(source: Path, *, label: str) -> str:
    """Digest one regular authored source without following any path symlink."""

    try:
        source_bytes = read_absolute_regular_file(source, label=label)
    except SecurePathError as error:
        raise ValueError(str(error)) from error
    return hashlib.sha256(source_bytes).hexdigest()


def _resolve_cli_game_soundtrack(
    *, input_path: Path, game_library_root: Path
) -> ResolvedGameSoundtrack:
    """Digest one authored soundtrack in place and resolve its exact source bytes."""

    root = game_library_root.absolute()
    source = input_path.absolute()
    try:
        relative = source.relative_to(root)
    except ValueError as error:
        raise ValueError("game soundtrack input must be inside game library root") from error
    if relative.name != "soundtrack.toml":
        raise ValueError("game soundtrack input must name soundtrack.toml")
    source_sha256 = _secure_cli_source_sha256(source, label="game soundtrack input")
    return resolve_game_soundtrack_binding(
        {
            "schema_version": 1,
            "kind": "game-soundtrack-binding-v1",
            "ref": relative.as_posix(),
            "source_sha256": source_sha256,
        },
        game_library_root=root,
    )


def _resolve_cli_character_profile(
    *, input_path: Path, package_root: Path
) -> ResolvedCharacterProfile:
    root = package_root.absolute()
    source = input_path.absolute()
    try:
        relative = source.relative_to(root)
    except ValueError as error:
        raise ValueError("character profile input must be inside the package root") from error
    if relative.suffix.lower() != ".toml":
        raise ValueError("character profile input must be a TOML member of the package")
    source_sha256 = _secure_cli_source_sha256(source, label="character profile input")
    return resolve_character_profile_binding(
        {
            "schema_version": 1,
            "kind": "character-profile-binding-v1",
            "ref": relative.as_posix(),
            "source_sha256": source_sha256,
        },
        package_root=root,
    )


def dispatch_character_profile(args: argparse.Namespace, *, stdout: TextIO) -> int:
    resolved = _resolve_cli_character_profile(
        input_path=Path(args.input_path),
        package_root=Path(args.package_root),
    )
    if args.character_profile_command == "digest":
        stdout.write(f"{resolved.source_sha256}\n")
    else:
        report = {"valid": True, **resolved.identity()}
        stdout.write(f"{json.dumps(report, sort_keys=True, separators=(',', ':'))}\n")
    return 0


def dispatch_soundtrack(args: argparse.Namespace, *, stdout: TextIO) -> int:
    resolved_soundtrack = _resolve_cli_game_soundtrack(
        input_path=Path(args.input_path),
        game_library_root=Path(args.game_library_root),
    )
    if args.soundtrack_command == "digest":
        stdout.write(f"{resolved_soundtrack.source_sha256}\n")
    else:
        soundtrack_report = {"valid": True, **resolved_soundtrack.identity()}
        stdout.write(f"{json.dumps(soundtrack_report, sort_keys=True, separators=(',', ':'))}\n")
    return 0
