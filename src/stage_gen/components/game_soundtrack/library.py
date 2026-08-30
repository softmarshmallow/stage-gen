"""Secure resolution of game-owned soundtrack catalogs from an explicit root."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from gnode import InputProvenance
from stage_gen.components._secure_fs import (
    SecurePathError,
    open_absolute_directory,
    read_relative_regular_file,
)
from stage_gen.components.game_soundtrack.loader import (
    canonical_game_soundtrack_json,
    load_game_soundtrack_bytes,
)
from stage_gen.components.game_soundtrack.models import GameSoundtrack, GameSoundtrackBinding

GAME_SOUNDTRACK_LIBRARY_RESOLUTION_VERSION = "game-soundtrack-library-resolution-v1"

_REF_PREFIX = ("library", "games")
_REF_FILENAME = "soundtrack.toml"


@dataclass(frozen=True, slots=True)
class ResolvedGameSoundtrack:
    binding: GameSoundtrackBinding
    soundtrack: GameSoundtrack
    source_path: Path
    source_bytes: bytes
    canonical_bytes: bytes

    @property
    def source_sha256(self) -> str:
        return hashlib.sha256(self.source_bytes).hexdigest()

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    @property
    def source_provenance(self) -> InputProvenance:
        return InputProvenance(
            ref=self.binding.ref,
            sha256=self.source_sha256,
            source="content",
            bytes=len(self.source_bytes),
            media_type="application/toml",
        )

    def identity(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "kind": "resolved-game-soundtrack-v1",
            "resolution_version": GAME_SOUNDTRACK_LIBRARY_RESOLUTION_VERSION,
            "binding": self.binding.model_dump(mode="json"),
            "game_id": self.soundtrack.game_id,
            "revision": self.soundtrack.revision,
            "track_ids": list(self.soundtrack.track_ids),
            "playback": self.soundtrack.playback.model_dump(mode="json"),
            "source_sha256": self.source_sha256,
            "canonical_sha256": self.canonical_sha256,
            "canonical_bytes": len(self.canonical_bytes),
        }


def resolve_game_soundtrack_binding(
    value: object,
    *,
    game_library_root: str | Path,
) -> ResolvedGameSoundtrack:
    """Resolve ``library/games/<game_id>/soundtrack.toml`` without symlinks."""

    binding = GameSoundtrackBinding.model_validate(value)
    parts = PurePosixPath(binding.ref).parts
    if len(parts) != 4 or parts[:2] != _REF_PREFIX or parts[3] != _REF_FILENAME:
        raise ValueError("game soundtrack ref must equal library/games/<game_id>/soundtrack.toml")
    root = Path(game_library_root).absolute()
    try:
        with open_absolute_directory(root, label="game soundtrack library root") as root_fd:
            source_bytes = read_relative_regular_file(
                root_fd,
                parts,
                label="game soundtrack source",
            )
            if hashlib.sha256(source_bytes).hexdigest() != binding.source_sha256:
                raise ValueError("game soundtrack source_sha256 mismatch")
            soundtrack = load_game_soundtrack_bytes(source_bytes, source_suffix=".toml")
            if soundtrack.game_id != parts[2]:
                raise ValueError("game soundtrack game_id must match its library directory")
            return ResolvedGameSoundtrack(
                binding=binding,
                soundtrack=soundtrack,
                source_path=root.joinpath(*parts),
                source_bytes=source_bytes,
                canonical_bytes=canonical_game_soundtrack_json(soundtrack),
            )
    except SecurePathError as error:
        raise ValueError(str(error)) from error


__all__ = [
    "GAME_SOUNDTRACK_LIBRARY_RESOLUTION_VERSION",
    "ResolvedGameSoundtrack",
    "resolve_game_soundtrack_binding",
]
