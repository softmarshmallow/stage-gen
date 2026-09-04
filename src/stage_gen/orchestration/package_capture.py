"""Capture one prepared package's closure, genre-free.

This is the half of package resolution that knows nothing about any genre: the
directory and ZIP captures with their size and symlink discipline, the digest
registry that turns every authored `source` / `source_sha256` pair into a proof
over the captured bytes, the byte-level admissions (image, audio, provenance
sidecar, UTF-8 text, JSON object), and the closure digest. A genre's member
resolution lives with its recipe and speaks to the package only through
:class:`PackageCapture`; the composition root in ``game_package`` wires the two
together.
"""

from __future__ import annotations

import io
import json
import os
import stat
import zipfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol

from PIL import Image, UnidentifiedImageError

from gnode import ArtifactProvenance, assert_audio_signature
from stage_gen.components._game_input import (
    AuthoredContractLoadError,
    portable_relative_path,
    sha256_bytes,
)
from stage_gen.components._secure_fs import (
    SecurePathError,
    open_absolute_directory,
    read_absolute_regular_file,
    read_relative_regular_file,
)
from stage_gen.components.game_contract import PreparedGameContract

GAME_PACKAGE_VALIDATION_SCHEMA_VERSION = 6
#: The resolved package document and its validation report carry the same schema
#: version under two kinds; the identity table reads both from here.
RESOLVED_GAME_PACKAGE_KIND = f"resolved-game-package-v{GAME_PACKAGE_VALIDATION_SCHEMA_VERSION}"
GAME_PACKAGE_VALIDATION_KIND = f"game-package-validation-v{GAME_PACKAGE_VALIDATION_SCHEMA_VERSION}"

_MAX_PACKAGE_FILES = 512
_MAX_PACKAGE_FILE_BYTES = 64 * 1024 * 1024
_MAX_PACKAGE_BYTES = 512 * 1024 * 1024
_MAX_ZIP_COMPRESSION_RATIO = 200

SourceKind = Literal["directory", "zip"]


class GamePackageValidationError(ValueError):
    """Stable package rejection with a machine-readable category."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ResolvedPackageFile:
    path: str
    sha256: str
    data: bytes

    def identity(self) -> dict[str, object]:
        return {"path": self.path, "sha256": self.sha256, "bytes": len(self.data)}


class ResolvedGenreMember(Protocol):
    """What a genre's resolved member owes the package: its identity block."""

    def identity(self) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class ResolvedPreparedPackage:
    """The captured closure plus every genre member the game declares, by genre."""

    source_kind: SourceKind
    package_name: str
    package_sha256: str
    canonical_game_sha256: str
    closure_sha256: str
    game: PreparedGameContract
    #: Resolved genre members in the order `game.toml` declares them.
    members: Mapping[str, ResolvedGenreMember]
    files: tuple[ResolvedPackageFile, ...]

    def file(self, path: str) -> ResolvedPackageFile:
        for entry in self.files:
            if entry.path == path:
                return entry
        raise KeyError(path)

    def member[MemberT](self, genre: str, kind: type[MemberT]) -> MemberT | None:
        """The declared genre's resolved member, or None when the game declares no such genre."""

        member = self.members.get(genre)
        if member is None:
            return None
        if not isinstance(member, kind):  # pragma: no cover - the roster binds genre to type
            raise TypeError(f"genre {genre} resolved to {type(member).__name__}")
        return member

    def identity(self) -> dict[str, object]:
        return {
            "schema_version": GAME_PACKAGE_VALIDATION_SCHEMA_VERSION,
            "kind": RESOLVED_GAME_PACKAGE_KIND,
            "game_id": self.game.game_id,
            "revision": self.game.revision,
            "package_sha256": self.package_sha256,
            "canonical_game_sha256": self.canonical_game_sha256,
            "closure_sha256": self.closure_sha256,
            "source_kind": self.source_kind,
            "file_count": len(self.files),
            "genres": {genre: member.identity() for genre, member in self.members.items()},
        }


@dataclass(frozen=True, slots=True)
class PackageCapture:
    """The captured bytes and the digest each path is expected to carry.

    Every path a contract names is registered here at ingest - authored members
    by the digest of the bytes found, locked references by the digest the
    contract declares - so that when resolution ends the registry and the
    capture can be compared in both directions: a named path that is missing
    and a captured path nothing names are both refusals.
    """

    files: Mapping[str, bytes]
    expected: dict[str, str] = field(default_factory=dict)

    def required(self, path: str) -> bytes:
        try:
            return self.files[path]
        except KeyError as error:
            raise GamePackageValidationError(
                "missing_package_file", f"prepared package is missing {path}"
            ) from error

    def member(self, source: str) -> bytes:
        """Register one authored member and capture its digest at ingest."""

        data = self.required(source)
        self.expected.setdefault(source, sha256_bytes(data))
        return data

    def locked(self, source: str, digest: str, label: str) -> bytes:
        """Register one digest-locked reference and prove the captured bytes match."""

        previous = self.expected.setdefault(source, digest)
        if previous != digest:
            raise GamePackageValidationError(
                "conflicting_source_digest", f"{label} has conflicting locked digests"
            )
        data = self.required(source)
        actual = sha256_bytes(data)
        if actual != digest:
            raise GamePackageValidationError(
                "stale_source_digest",
                f"{label} source_sha256 mismatch for {source}: expected {digest}, got {actual}",
            )
        return data

    def image(self, source: str, digest: str, label: str) -> bytes:
        """A locked reference that must decode as an image."""

        data = self.locked(source, digest, label)
        validate_image(data, source)
        return data

    def audio_take(
        self,
        *,
        source: str,
        digest: str,
        provenance_source: str,
        provenance_digest: str,
        label: str,
    ) -> bytes:
        """A pinned take: the bytes and the sidecar that produced them, both locked.

        The sidecar must describe exactly the pinned bytes, so a reviewed audition
        cannot be swapped under its own provenance.
        """

        take_bytes = self.locked(source, digest, label)
        validate_audio(take_bytes, source)
        sidecar_bytes = self.locked(provenance_source, provenance_digest, f"{label} provenance")
        validate_take_provenance(sidecar_bytes, digest, source)
        return take_bytes

    def close(self) -> tuple[ResolvedPackageFile, ...]:
        """Compare the registry against the capture and return the exact closure."""

        actual_paths = set(self.files)
        expected_paths = set(self.expected)
        missing = sorted(expected_paths - actual_paths)
        if missing:
            raise GamePackageValidationError(
                "missing_package_file", "package is missing files: " + ", ".join(missing)
            )
        orphaned = sorted(actual_paths - expected_paths)
        if orphaned:
            raise GamePackageValidationError(
                "orphan_package_file",
                "package contains unreferenced files: " + ", ".join(orphaned),
            )
        return tuple(
            ResolvedPackageFile(
                path=path, sha256=sha256_bytes(self.files[path]), data=self.files[path]
            )
            for path in sorted(expected_paths)
        )


def capture_package(source: Path) -> tuple[PackageCapture, str, SourceKind]:
    """Capture a directory or ZIP into memory; returns the capture, its name and kind."""

    if source.suffix.lower() == ".zip":
        files, package_name = capture_zip(source)
        return PackageCapture(files), package_name, "zip"
    files, package_name = capture_directory(source)
    return PackageCapture(files), package_name, "directory"


def capture_directory(root: Path) -> tuple[dict[str, bytes], str]:
    try:
        with open_absolute_directory(root, label="prepared package root"):
            pass
    except SecurePathError as error:
        raise GamePackageValidationError("invalid_package_root", str(error)) from error

    relative_paths: list[str] = []
    total_bytes = 0
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in [*directory_names, *file_names]:
            candidate = current_path / name
            try:
                mode = os.lstat(candidate).st_mode
            except OSError as error:
                raise GamePackageValidationError(
                    "invalid_package_path", f"cannot inspect package path: {candidate.name}"
                ) from error
            if stat.S_ISLNK(mode):
                raise GamePackageValidationError(
                    "symlink_escape", "prepared packages must not contain symlinks"
                )
            if name in file_names and not stat.S_ISREG(mode):
                raise GamePackageValidationError(
                    "invalid_package_path", "prepared packages may contain only regular files"
                )
        for name in file_names:
            relative = (current_path / name).relative_to(root).as_posix()
            portable_relative_path(relative, "prepared package path")
            relative_paths.append(relative)

    if len(relative_paths) > _MAX_PACKAGE_FILES:
        raise GamePackageValidationError("package_too_large", "prepared package has too many files")

    captured: dict[str, bytes] = {}
    with open_absolute_directory(root, label="prepared package root") as root_fd:
        for relative in sorted(relative_paths):
            data = read_relative_regular_file(
                root_fd,
                tuple(PurePosixPath(relative).parts),
                label=f"prepared package file {relative}",
            )
            _validate_file_size(relative, len(data))
            total_bytes += len(data)
            if total_bytes > _MAX_PACKAGE_BYTES:
                raise GamePackageValidationError(
                    "package_too_large", "prepared package exceeds the total size limit"
                )
            captured[relative] = data
    return captured, root.name


def capture_zip(path: Path) -> tuple[dict[str, bytes], str]:
    try:
        archive_bytes = read_absolute_regular_file(path, label="prepared package ZIP")
    except SecurePathError as error:
        raise GamePackageValidationError("invalid_package_zip", str(error)) from error
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as error:
        raise GamePackageValidationError(
            "invalid_package_zip", "invalid prepared package ZIP"
        ) from error

    with archive:
        entries = archive.infolist()
        if len(entries) > _MAX_PACKAGE_FILES + 32:
            raise GamePackageValidationError(
                "package_too_large", "prepared package ZIP has too many entries"
            )
        normalized: dict[str, zipfile.ZipInfo] = {}
        for entry in entries:
            raw_name = entry.filename.rstrip("/") if entry.is_dir() else entry.filename
            if not raw_name:
                continue
            relative = portable_relative_path(raw_name, "prepared package ZIP entry")
            if relative in normalized:
                raise GamePackageValidationError(
                    "duplicate_archive_entry", f"duplicate ZIP entry: {relative}"
                )
            unix_mode = entry.external_attr >> 16
            if unix_mode and stat.S_ISLNK(unix_mode):
                raise GamePackageValidationError(
                    "symlink_escape", "prepared package ZIP must not contain symlinks"
                )
            if entry.flag_bits & 0x1:
                raise GamePackageValidationError(
                    "invalid_package_zip", "encrypted ZIP entries are not supported"
                )
            normalized[relative] = entry

        game_roots = []
        for relative, entry in normalized.items():
            if entry.is_dir():
                continue
            parts = PurePosixPath(relative).parts
            if parts[-1] == "game.toml" and len(parts) in {1, 2}:
                game_roots.append(parts[:-1])
        if len(game_roots) != 1:
            raise GamePackageValidationError(
                "ambiguous_package_root",
                "prepared package ZIP must contain exactly one root game.toml",
            )
        prefix = game_roots[0]
        captured: dict[str, bytes] = {}
        total_bytes = 0
        for relative, entry in sorted(normalized.items()):
            parts = PurePosixPath(relative).parts
            if entry.is_dir():
                continue
            if prefix and parts[: len(prefix)] != prefix:
                raise GamePackageValidationError(
                    "orphan_package_file", "ZIP contains files outside its package root"
                )
            stripped_parts = parts[len(prefix) :]
            if not stripped_parts:
                continue
            stripped = PurePosixPath(*stripped_parts).as_posix()
            _validate_file_size(stripped, entry.file_size)
            if (
                entry.file_size > 10 * 1024 * 1024
                and entry.compress_size > 0
                and entry.file_size > entry.compress_size * _MAX_ZIP_COMPRESSION_RATIO
            ):
                raise GamePackageValidationError(
                    "package_too_large", f"ZIP entry has an unsafe compression ratio: {stripped}"
                )
            total_bytes += entry.file_size
            if total_bytes > _MAX_PACKAGE_BYTES:
                raise GamePackageValidationError(
                    "package_too_large", "prepared package ZIP exceeds the total size limit"
                )
            data = archive.read(entry)
            if len(data) != entry.file_size:
                raise GamePackageValidationError(
                    "invalid_package_zip", f"ZIP entry size changed while reading: {stripped}"
                )
            captured[stripped] = data
        package_name = prefix[0] if prefix else path.stem
        return captured, package_name


def load_locked[ContractT](
    data: bytes,
    loader: Callable[[bytes], ContractT],
    code: str,
) -> ContractT:
    """Parse one authored member, translating a load failure into the genre's own code."""

    try:
        return loader(data)
    except (AuthoredContractLoadError, ValueError) as error:
        raise GamePackageValidationError(code, str(error)) from error


def assert_subset(values: Iterable[str], allowed: set[str], label: str) -> None:
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise GamePackageValidationError(
            "unresolved_cross_reference", f"{label} values do not resolve: {', '.join(unknown)}"
        )


def closure_sha256(files: Sequence[ResolvedPackageFile]) -> str:
    """Digest the exact captured closure: every member path, digest, and size."""

    payload = json.dumps(
        [entry.identity() for entry in files], sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(payload)


def _validate_file_size(path: str, size: int) -> None:
    if size > _MAX_PACKAGE_FILE_BYTES:
        raise GamePackageValidationError(
            "package_too_large", f"prepared package file exceeds the size limit: {path}"
        )


def validate_audio(data: bytes, path: str) -> None:
    try:
        assert_audio_signature(data, "audio/mpeg")
    except ValueError as error:
        raise GamePackageValidationError(
            "invalid_pinned_take", f"pinned take is not an mp3 stream: {path}"
        ) from error


def validate_take_provenance(data: bytes, artifact_sha256: str, path: str) -> None:
    """The committed sidecar must be a provenance record for exactly the pinned bytes."""

    try:
        record = ArtifactProvenance.model_validate_json(data)
    except ValueError as error:
        raise GamePackageValidationError(
            "invalid_pinned_take", f"pinned take provenance is not a provenance record: {path}"
        ) from error
    if record.artifact is None or record.artifact.sha256 != artifact_sha256:
        raise GamePackageValidationError(
            "invalid_pinned_take",
            f"pinned take provenance describes different bytes than the take: {path}",
        )


def validate_image(data: bytes, path: str) -> None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
    except (OSError, UnidentifiedImageError) as error:
        raise GamePackageValidationError(
            "invalid_reference_image", f"prepared reference image cannot be decoded: {path}"
        ) from error


def validate_utf8_text(data: bytes, label: str) -> None:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise GamePackageValidationError("invalid_text_source", f"{label} is not UTF-8") from error
    if not text.strip():
        raise GamePackageValidationError("invalid_text_source", f"{label} must not be empty")


def validate_json_object(data: bytes, label: str) -> None:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GamePackageValidationError(
            "invalid_evidence", f"{label} is not valid JSON"
        ) from error
    if not isinstance(value, dict):
        raise GamePackageValidationError("invalid_evidence", f"{label} must be a JSON object")


__all__ = [
    "GAME_PACKAGE_VALIDATION_KIND",
    "GAME_PACKAGE_VALIDATION_SCHEMA_VERSION",
    "RESOLVED_GAME_PACKAGE_KIND",
    "GamePackageValidationError",
    "PackageCapture",
    "ResolvedGenreMember",
    "ResolvedPackageFile",
    "ResolvedPreparedPackage",
    "SourceKind",
    "assert_subset",
    "capture_directory",
    "capture_package",
    "capture_zip",
    "closure_sha256",
    "load_locked",
    "validate_audio",
    "validate_image",
    "validate_json_object",
    "validate_take_provenance",
    "validate_utf8_text",
]
