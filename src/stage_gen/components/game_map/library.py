"""Secure resolution of per-map files through one digest-bound ordered index."""

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
from stage_gen.components.game_map.loader import (
    canonical_game_map_json,
    canonical_resolved_game_map_book_json,
    load_game_map_book_bytes,
    load_game_map_bytes,
)
from stage_gen.components.game_map.models import (
    GameMap,
    GameMapBook,
    GameMapBookBinding,
    ResolvedGameMapBookDocument,
)

GAME_MAP_LIBRARY_RESOLUTION_VERSION = "game-map-library-resolution-v1"

_BOOK_PREFIX = ("library", "games")
_BOOK_SUFFIX = ("maps", "index.toml")


@dataclass(frozen=True, slots=True)
class ResolvedGameMap:
    game_map: GameMap
    source_ref: str
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
            ref=self.source_ref,
            sha256=self.source_sha256,
            source="content",
            bytes=len(self.source_bytes),
            media_type="application/toml",
        )

    def identity(self) -> dict[str, object]:
        return {
            "schema_version": 2,
            "kind": "resolved-game-map-v2",
            "resolution_version": GAME_MAP_LIBRARY_RESOLUTION_VERSION,
            "game_id": self.game_map.game_id,
            "map_id": self.game_map.map_id,
            "revision": self.game_map.revision,
            "soundtrack_track_ids": list(self.game_map.soundtrack_track_ids),
            "source_ref": self.source_ref,
            "source_sha256": self.source_sha256,
            "canonical_sha256": self.canonical_sha256,
            "canonical_bytes": len(self.canonical_bytes),
            "level_profile": self.game_map.level_profile.model_dump(mode="json"),
        }


@dataclass(frozen=True, slots=True)
class ResolvedGameMapBook:
    binding: GameMapBookBinding
    book: GameMapBook
    maps: tuple[ResolvedGameMap, ...]
    source_path: Path
    source_bytes: bytes
    document: ResolvedGameMapBookDocument
    canonical_bytes: bytes

    @property
    def source_sha256(self) -> str:
        return hashlib.sha256(self.source_bytes).hexdigest()

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    @property
    def source_provenance(self) -> tuple[InputProvenance, ...]:
        book = InputProvenance(
            ref=self.binding.ref,
            sha256=self.source_sha256,
            source="content",
            bytes=len(self.source_bytes),
            media_type="application/toml",
        )
        return (book, *(resolved.source_provenance for resolved in self.maps))

    def identity(self) -> dict[str, object]:
        return {
            "schema_version": 2,
            "kind": "resolved-game-map-book-v2",
            "resolution_version": GAME_MAP_LIBRARY_RESOLUTION_VERSION,
            "binding": self.binding.model_dump(mode="json"),
            "game_id": self.book.game_id,
            "revision": self.book.revision,
            "entry_map_id": self.book.entry_map_id,
            "map_ids": list(self.book.map_ids),
            "source_sha256": self.source_sha256,
            "canonical_sha256": self.canonical_sha256,
            "canonical_bytes": len(self.canonical_bytes),
            "map_sources": [resolved.identity() for resolved in self.maps],
        }


def _book_parts(ref: str) -> tuple[str, ...]:
    parts = PurePosixPath(ref).parts
    if len(parts) != 5 or parts[:2] != _BOOK_PREFIX or parts[3:] != _BOOK_SUFFIX:
        raise ValueError("game map book ref must equal library/games/<game_id>/maps/index.toml")
    return parts


def _map_parts(game_id: str, map_id: str) -> tuple[str, ...]:
    return ("library", "games", game_id, "maps", f"{map_id}.toml")


def resolve_game_map_source(
    input_path: str | Path, *, game_library_root: str | Path
) -> ResolvedGameMap:
    """Resolve one map at its fixed path for authoring-time validation."""

    root = Path(game_library_root).absolute()
    source = Path(input_path).absolute()
    try:
        relative = source.relative_to(root)
    except ValueError as error:
        raise ValueError("game map input must be inside game library root") from error
    parts = relative.parts
    if (
        len(parts) != 5
        or parts[:2] != _BOOK_PREFIX
        or parts[3] != "maps"
        or not parts[4].endswith(".toml")
        or parts[4] == "index.toml"
    ):
        raise ValueError(
            "game map input must equal ROOT/library/games/<game_id>/maps/<map_id>.toml"
        )
    try:
        with open_absolute_directory(root, label="game map library root") as root_fd:
            source_bytes = read_relative_regular_file(root_fd, parts, label="game map source")
    except SecurePathError as error:
        raise ValueError(str(error)) from error
    game_map = load_game_map_bytes(source_bytes, source_suffix=".toml")
    if game_map.game_id != parts[2]:
        raise ValueError("game map game_id must match its library directory")
    if f"{game_map.map_id}.toml" != parts[4]:
        raise ValueError("game map map_id must match its source filename")
    return ResolvedGameMap(
        game_map=game_map,
        source_ref=PurePosixPath(*parts).as_posix(),
        source_path=root.joinpath(*parts),
        source_bytes=source_bytes,
        canonical_bytes=canonical_game_map_json(game_map),
    )


def resolve_game_map_book_binding(
    value: object, *, game_library_root: str | Path
) -> ResolvedGameMapBook:
    """Resolve an index and every locked ``maps/<map_id>.toml`` without symlinks."""

    binding = GameMapBookBinding.model_validate(value)
    parts = _book_parts(binding.ref)
    root = Path(game_library_root).absolute()
    try:
        with open_absolute_directory(root, label="game map library root") as root_fd:
            source_bytes = read_relative_regular_file(root_fd, parts, label="game map book source")
            if hashlib.sha256(source_bytes).hexdigest() != binding.source_sha256:
                raise ValueError("game map book source_sha256 mismatch")
            book = load_game_map_book_bytes(source_bytes, source_suffix=".toml")
            if book.game_id != parts[2]:
                raise ValueError("game map book game_id must match its library directory")

            resolved_maps: list[ResolvedGameMap] = []
            for entry in book.maps:
                map_parts = _map_parts(book.game_id, entry.map_id)
                map_bytes = read_relative_regular_file(
                    root_fd, map_parts, label=f"game map source {entry.map_id}"
                )
                if hashlib.sha256(map_bytes).hexdigest() != entry.source_sha256:
                    raise ValueError(f"game map source_sha256 mismatch for map_id {entry.map_id}")
                game_map = load_game_map_bytes(map_bytes, source_suffix=".toml")
                if game_map.game_id != book.game_id:
                    raise ValueError(f"game map {entry.map_id} game_id must match its map book")
                if game_map.map_id != entry.map_id:
                    raise ValueError(
                        f"game map map_id must match its source filename: {entry.map_id}"
                    )
                resolved_maps.append(
                    ResolvedGameMap(
                        game_map=game_map,
                        source_ref=PurePosixPath(*map_parts).as_posix(),
                        source_path=root.joinpath(*map_parts),
                        source_bytes=map_bytes,
                        canonical_bytes=canonical_game_map_json(game_map),
                    )
                )

            document = ResolvedGameMapBookDocument(
                schema_version=2,
                kind="resolved-game-map-book-v2",
                game_id=book.game_id,
                revision=book.revision,
                entry_map_id=book.entry_map_id,
                maps=[resolved.game_map for resolved in resolved_maps],
            )
            return ResolvedGameMapBook(
                binding=binding,
                book=book,
                maps=tuple(resolved_maps),
                source_path=root.joinpath(*parts),
                source_bytes=source_bytes,
                document=document,
                canonical_bytes=canonical_resolved_game_map_book_json(document),
            )
    except SecurePathError as error:
        raise ValueError(str(error)) from error


__all__ = [
    "GAME_MAP_LIBRARY_RESOLUTION_VERSION",
    "ResolvedGameMap",
    "ResolvedGameMapBook",
    "resolve_game_map_book_binding",
    "resolve_game_map_source",
]
