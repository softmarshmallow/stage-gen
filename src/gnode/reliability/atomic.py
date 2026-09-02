"""Atomic JSON and artifact/provenance persistence with rollback."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from gnode.contracts.artifacts import BinaryArtifact
from gnode.contracts.provenance import (
    ArtifactDigest,
    ArtifactProvenance,
    ArtifactRights,
    InputProvenance,
    ProvenanceInput,
)

from .encoding import (
    assert_text_payload,
    is_portable_artifact_reference,
    normalize_artifact_media_type,
    sanitize_reference,
    sha256_hex,
)
from .redaction import redact_secrets, sanitize_for_persistence


class AtomicWriteError(OSError):
    """An atomic commit or its rollback failed."""

    def __init__(self, message: str, *, provider_operations: int | None = None) -> None:
        super().__init__(message)
        if provider_operations is None:
            return
        if (
            isinstance(provider_operations, bool)
            or not isinstance(provider_operations, int)
            or provider_operations < 0
        ):
            raise ValueError("provider_operations must be a non-negative integer")
        self.attempts = max(1, provider_operations)
        self.provider_operations = provider_operations


@dataclass(frozen=True, slots=True)
class AtomicBundleFile:
    """One ordered file in a same-directory atomic publication bundle."""

    path: str | os.PathLike[str]
    data: bytes
    mode: int = 0o600


@dataclass(frozen=True, slots=True)
class ArtifactBundleEntry:
    """One artifact/provenance pair in a larger atomic publication bundle."""

    path: str | os.PathLike[str]
    artifact: BinaryArtifact
    provenance: ProvenanceInput


@dataclass(slots=True)
class _AtomicBundleState:
    path: Path
    data: bytes
    mode: int
    temporary: Path
    backup: Path
    existed: bool
    backed_up: bool = False
    install_attempted: bool = False


class FileOperations(Protocol):
    def mkdir(self, path: Path) -> None: ...

    def exists(self, path: Path) -> bool: ...

    def read_bytes(self, path: Path) -> bytes: ...

    def write_exclusive(self, path: Path, data: bytes, mode: int = 0o600) -> None: ...

    def replace(self, source: Path, destination: Path) -> None: ...

    def remove(self, path: Path) -> None: ...

    def sync_directory(self, path: Path) -> None: ...


class LocalFileOperations:
    """Durable local filesystem operations; injectable for rollback tests."""

    def mkdir(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def exists(self, path: Path) -> bool:
        return os.path.lexists(path)

    def read_bytes(self, path: Path) -> bytes:
        return path.read_bytes()

    def write_exclusive(self, path: Path, data: bytes, mode: int = 0o600) -> None:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            os.close(descriptor)

    def replace(self, source: Path, destination: Path) -> None:
        os.replace(source, destination)

    def remove(self, path: Path) -> None:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()

    def sync_directory(self, path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


_LOCAL_FILES = LocalFileOperations()


def build_artifact_provenance(
    artifact: BinaryArtifact | None,
    provenance: ProvenanceInput,
    *,
    secrets: Sequence[str] = (),
    now: datetime | None = None,
) -> ArtifactProvenance:
    """Validate and sanitize a provenance-v2 record before any write."""

    references = [sanitize_reference(reference) for reference in provenance.refs]
    inputs = [
        InputProvenance(
            ref=sanitize_reference(item.ref),
            sha256=item.sha256,
            source=item.source,
            bytes=item.bytes,
            media_type=item.media_type,
        )
        for item in provenance.inputs
    ]
    rights = _sanitize_rights(provenance.rights, secrets) if provenance.rights is not None else None
    timestamp = provenance.timestamp or (now or datetime.now(UTC)).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")
    digest = None
    if artifact is not None:
        if not artifact.data:
            raise ValueError("artifact bytes must be non-empty")
        media_type = normalize_artifact_media_type(artifact.media_type)
        if media_type.startswith("text/"):
            assert_text_payload(artifact.data, media_type)
        digest = ArtifactDigest(
            sha256=sha256_hex(artifact.data), bytes=len(artifact.data), media_type=media_type
        )
    raw: dict[str, Any] = {
        "schema_version": provenance.schema_version,
        "provider": provenance.provider,
        "model": provenance.model,
        "seed": provenance.seed,
        "prompt": provenance.prompt,
        "prompt_sha256": sha256_hex(provenance.prompt),
        "references": references,
        "refs": references,
        "inputs": [item.model_dump(mode="json") for item in inputs],
        "params": provenance.params,
        "validation": provenance.validation,
        "component": provenance.component.model_dump(mode="json"),
        "tool": provenance.tool.model_dump(mode="json"),
        "artifact": digest.model_dump(mode="json") if digest is not None else None,
        "rights": rights.model_dump(mode="json") if rights is not None else None,
        "ts": timestamp,
        "attempts": provenance.attempts,
        "retries": provenance.attempts - 1,
        "response": provenance.response,
    }
    sanitized = sanitize_for_persistence(raw, secrets)
    if not isinstance(sanitized, dict):
        raise TypeError("artifact provenance must be an object")
    record = ArtifactProvenance.model_validate(sanitized)
    if record.rights is not None and record.rights.status == "redistribution-approved":
        _assert_portable_references(record.references, record.inputs)
    return record


def serialize_provenance(provenance: ArtifactProvenance) -> bytes:
    """Serialize using persisted aliases while keeping required null seed."""

    payload = provenance.model_dump(mode="json", by_alias=True, exclude_none=False)
    for optional in ("artifact", "rights", "response"):
        if payload[optional] is None:
            payload.pop(optional)
    for item in payload["inputs"]:
        for optional in ("bytes", "media_type"):
            if item[optional] is None:
                item.pop(optional)
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode()


def write_artifact_with_provenance(
    artifact_path: str | os.PathLike[str],
    artifact: BinaryArtifact,
    provenance: ProvenanceInput,
    *,
    secrets: Sequence[str] = (),
    now: datetime | None = None,
    operations: FileOperations | None = None,
) -> Path:
    """Commit artifact and adjacent sidecar as one rollback-protected pair."""

    raw_path = os.fspath(artifact_path)
    if not raw_path or not raw_path.strip():
        raise ValueError("artifact_path must be non-empty")
    path = Path(raw_path)
    sidecar_path = Path(f"{path}.meta.json")
    record = build_artifact_provenance(artifact, provenance, secrets=secrets, now=now)
    sidecar_bytes = serialize_provenance(record)
    files = operations or _LOCAL_FILES
    files.mkdir(path.parent)

    token = uuid.uuid4().hex
    artifact_temp = path.parent / f".{path.name}.{token}.tmp"
    sidecar_temp = sidecar_path.parent / f".{sidecar_path.name}.{token}.tmp"
    artifact_backup = Path(f"{artifact_temp}.backup")
    sidecar_backup = Path(f"{sidecar_temp}.backup")
    artifact_backed_up = False
    sidecar_backed_up = False
    artifact_installed = False
    sidecar_installed = False
    artifact_existed = files.exists(path)
    sidecar_existed = files.exists(sidecar_path)

    try:
        files.write_exclusive(artifact_temp, artifact.data)
        files.write_exclusive(sidecar_temp, sidecar_bytes)
        if artifact_existed:
            files.replace(path, artifact_backup)
            artifact_backed_up = True
        if sidecar_existed:
            files.replace(sidecar_path, sidecar_backup)
            sidecar_backed_up = True
        files.replace(artifact_temp, path)
        artifact_installed = True
        files.replace(sidecar_temp, sidecar_path)
        sidecar_installed = True
        files.sync_directory(path.parent)
    except Exception as error:
        rollback_errors = _rollback_artifact_pair(
            files,
            artifact_path=path,
            sidecar_path=sidecar_path,
            artifact_backup=artifact_backup,
            sidecar_backup=sidecar_backup,
            artifact_existed=artifact_existed,
            sidecar_existed=sidecar_existed,
            artifact_backed_up=artifact_backed_up,
            sidecar_backed_up=sidecar_backed_up,
            artifact_installed=artifact_installed,
            sidecar_installed=sidecar_installed,
        )
        _safe_remove(files, artifact_temp)
        _safe_remove(files, sidecar_temp)
        safe_message = redact_secrets(str(error), secrets)
        if rollback_errors:
            raise AtomicWriteError(
                "artifact pair persistence failed and rollback was incomplete; "
                f"recovery backups were retained: {safe_message}"
            ) from None
        raise AtomicWriteError(safe_message) from None

    _safe_remove(files, artifact_backup)
    _safe_remove(files, sidecar_backup)
    return sidecar_path


async def write_artifact_with_provenance_async(
    artifact_path: str | os.PathLike[str],
    artifact: BinaryArtifact,
    provenance: ProvenanceInput,
    *,
    secrets: Sequence[str] = (),
    now: datetime | None = None,
    operations: FileOperations | None = None,
) -> Path:
    try:
        return await asyncio.to_thread(
            write_artifact_with_provenance,
            artifact_path,
            artifact,
            provenance,
            secrets=secrets,
            now=now,
            operations=operations,
        )
    except asyncio.CancelledError:
        raise
    except Exception as error:
        # The provider result already exists when a modality enters artifact
        # persistence. Preserve that completed spend even when provenance
        # serialization, publication, or rollback fails afterward.
        raise AtomicWriteError(
            redact_secrets(str(error).strip() or type(error).__name__, secrets),
            provider_operations=provenance.attempts,
        ) from None


def atomic_write_bundle(
    entries: Sequence[AtomicBundleFile],
    *,
    secrets: Sequence[str] = (),
    operations: FileOperations | None = None,
) -> tuple[Path, ...]:
    """Publish ordered same-directory files or restore the complete prior bundle.

    Callers construct and validate every payload before entering this filesystem
    transaction. All existing destinations are moved to sibling recovery backups
    before the first new file is installed. A failure restores every prior file,
    removes newly introduced destinations, and retains only backups whose restore
    itself failed.
    """

    if not entries:
        raise ValueError("atomic bundle must contain at least one file")

    normalized: list[tuple[Path, bytes, int]] = []
    for entry in entries:
        raw_path = os.fspath(entry.path)
        if not raw_path or not raw_path.strip():
            raise ValueError("atomic bundle paths must be non-empty")
        path = Path(raw_path)
        if not path.name:
            raise ValueError("atomic bundle paths must name files")
        if not isinstance(entry.data, bytes):
            raise TypeError("atomic bundle payloads must be bytes")
        normalized.append((path, entry.data, entry.mode))

    paths = tuple(path for path, _data, _mode in normalized)
    if len(set(paths)) != len(paths):
        raise ValueError("atomic bundle paths must be unique")
    parent = paths[0].parent
    if any(path.parent != parent for path in paths[1:]):
        raise ValueError("atomic bundle files must share one directory")

    files = operations or _LOCAL_FILES
    files.mkdir(parent)
    token = uuid.uuid4().hex
    states = [
        _AtomicBundleState(
            path=path,
            data=data,
            mode=mode,
            temporary=parent / f".{path.name}.{token}.tmp",
            backup=parent / f".{path.name}.{token}.tmp.backup",
            existed=files.exists(path),
        )
        for path, data, mode in normalized
    ]

    try:
        for state in states:
            files.write_exclusive(state.temporary, state.data, state.mode)
        for state in states:
            if state.existed:
                files.replace(state.path, state.backup)
                state.backed_up = True
        for state in states:
            state.install_attempted = True
            files.replace(state.temporary, state.path)
        files.sync_directory(parent)
    except Exception as error:
        rollback_errors = _rollback_atomic_bundle(files, states, parent)
        for state in states:
            _safe_remove(files, state.temporary)
        safe_message = redact_secrets(str(error), secrets)
        if rollback_errors:
            raise AtomicWriteError(
                "artifact bundle persistence failed and rollback was incomplete; "
                f"recovery backups were retained: {safe_message}"
            ) from None
        raise AtomicWriteError(safe_message) from None

    for state in states:
        _safe_remove(files, state.backup)
    return paths


async def atomic_write_bundle_async(
    entries: Sequence[AtomicBundleFile],
    *,
    secrets: Sequence[str] = (),
    operations: FileOperations | None = None,
) -> tuple[Path, ...]:
    """Run :func:`atomic_write_bundle` without blocking the event loop."""

    return await asyncio.to_thread(
        atomic_write_bundle,
        entries,
        secrets=secrets,
        operations=operations,
    )


def write_artifact_bundle_with_provenance(
    entries: Sequence[ArtifactBundleEntry],
    *,
    secrets: Sequence[str] = (),
    now: datetime | None = None,
    operations: FileOperations | None = None,
) -> tuple[Path, ...]:
    """Build and publish multiple artifact/sidecar pairs as one transaction.

    The returned paths are the adjacent provenance sidecars in input order.
    Provenance validation and serialization for every entry completes before
    any destination is staged or replaced.
    """

    if not entries:
        raise ValueError("artifact bundle must contain at least one entry")
    bundle_now = now or datetime.now(UTC)
    publication: list[AtomicBundleFile] = []
    sidecars: list[Path] = []
    for entry in entries:
        raw_path = os.fspath(entry.path)
        if not raw_path or not raw_path.strip():
            raise ValueError("artifact bundle paths must be non-empty")
        path = Path(raw_path)
        sidecar = Path(f"{path}.meta.json")
        record = build_artifact_provenance(
            entry.artifact,
            entry.provenance,
            secrets=secrets,
            now=bundle_now,
        )
        publication.extend(
            (
                AtomicBundleFile(path, entry.artifact.data),
                AtomicBundleFile(sidecar, serialize_provenance(record)),
            )
        )
        sidecars.append(sidecar)
    atomic_write_bundle(publication, secrets=secrets, operations=operations)
    return tuple(sidecars)


async def write_artifact_bundle_with_provenance_async(
    entries: Sequence[ArtifactBundleEntry],
    *,
    secrets: Sequence[str] = (),
    now: datetime | None = None,
    operations: FileOperations | None = None,
) -> tuple[Path, ...]:
    """Run :func:`write_artifact_bundle_with_provenance` off the event loop."""

    return await asyncio.to_thread(
        write_artifact_bundle_with_provenance,
        entries,
        secrets=secrets,
        now=now,
        operations=operations,
    )


def atomic_write_bytes(
    path: str | os.PathLike[str],
    data: bytes,
    *,
    mode: int = 0o600,
    operations: FileOperations | None = None,
) -> Path:
    """Atomically replace one file from an exclusive, fsynced sibling temp."""

    target = Path(path)
    files = operations or _LOCAL_FILES
    files.mkdir(target.parent)
    temporary = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
    try:
        files.write_exclusive(temporary, data, mode)
        files.replace(temporary, target)
        files.sync_directory(target.parent)
    except Exception:
        _safe_remove(files, temporary)
        raise
    return target


def atomic_write_text(
    path: str | os.PathLike[str],
    text: str,
    *,
    mode: int = 0o600,
    operations: FileOperations | None = None,
) -> Path:
    return atomic_write_bytes(path, text.encode(), mode=mode, operations=operations)


def atomic_write_json(
    path: str | os.PathLike[str],
    value: Mapping[str, Any],
    *,
    mode: int = 0o600,
    operations: FileOperations | None = None,
) -> Path:
    payload = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()
    return atomic_write_bytes(path, payload, mode=mode, operations=operations)


def record_artifact_rights(
    artifact_path: str | os.PathLike[str],
    rights: ArtifactRights,
    *,
    provenance_path: str | os.PathLike[str] | None = None,
    secrets: Sequence[str] = (),
    operations: FileOperations | None = None,
) -> Path:
    """Verify binding and atomically attach an explicit rights decision."""

    path = Path(artifact_path)
    sidecar_path = Path(provenance_path) if provenance_path else Path(f"{path}.meta.json")
    files = operations or _LOCAL_FILES
    artifact_bytes = files.read_bytes(path)
    original_sidecar = files.read_bytes(sidecar_path)
    try:
        record = ArtifactProvenance.model_validate_json(original_sidecar)
    except Exception as error:
        raise ValueError("artifact provenance is not valid provenance-v2 JSON") from error
    _assert_artifact_binding(record, artifact_bytes)
    if rights.status == "redistribution-approved":
        _assert_portable_references(record.references, record.inputs)
    updated = record.model_copy(update={"rights": _sanitize_rights(rights, secrets)})
    serialized = serialize_provenance(updated)
    temporary = sidecar_path.parent / f".{sidecar_path.name}.{uuid.uuid4().hex}.tmp"
    files.mkdir(sidecar_path.parent)
    try:
        files.write_exclusive(temporary, serialized)
        _assert_artifact_binding(record, files.read_bytes(path))
        if sha256_hex(files.read_bytes(sidecar_path)) != sha256_hex(original_sidecar):
            raise ValueError("artifact provenance changed while recording rights")
        files.replace(temporary, sidecar_path)
        files.sync_directory(sidecar_path.parent)
    except Exception as error:
        _safe_remove(files, temporary)
        raise AtomicWriteError(redact_secrets(str(error), secrets)) from None
    return sidecar_path


async def record_artifact_rights_async(
    artifact_path: str | os.PathLike[str],
    rights: ArtifactRights,
    *,
    provenance_path: str | os.PathLike[str] | None = None,
    secrets: Sequence[str] = (),
    operations: FileOperations | None = None,
) -> Path:
    return await asyncio.to_thread(
        record_artifact_rights,
        artifact_path,
        rights,
        provenance_path=provenance_path,
        secrets=secrets,
        operations=operations,
    )


def _assert_artifact_binding(record: ArtifactProvenance, artifact_bytes: bytes) -> None:
    if record.artifact is None:
        raise ValueError("artifact provenance has no artifact digest")
    if record.artifact.bytes != len(artifact_bytes) or record.artifact.sha256 != sha256_hex(
        artifact_bytes
    ):
        raise ValueError("artifact bytes do not match provenance digest")


def _assert_portable_references(
    references: Sequence[str], inputs: Sequence[InputProvenance]
) -> None:
    if any(not is_portable_artifact_reference(reference) for reference in references):
        raise ValueError("redistribution-approved provenance contains an unsafe reference")
    if any(not is_portable_artifact_reference(item.ref) for item in inputs):
        raise ValueError("redistribution-approved provenance contains an unsafe input reference")


def _sanitize_rights(rights: ArtifactRights, secrets: Sequence[str]) -> ArtifactRights:
    value = sanitize_for_persistence(rights.model_dump(mode="json"), secrets)
    if not isinstance(value, dict):
        raise TypeError("artifact rights must be an object")
    return ArtifactRights.model_validate(value)


def _safe_remove(files: FileOperations, path: Path) -> None:
    with contextlib.suppress(Exception):
        files.remove(path)


def _rollback_atomic_bundle(
    files: FileOperations,
    states: Sequence[_AtomicBundleState],
    parent: Path,
) -> list[Exception]:
    """Restore an arbitrary publication bundle after staging or install failure."""

    errors: list[Exception] = []
    for state in reversed(states):
        backup_exists = state.backed_up or _safe_exists(files, state.backup)
        if backup_exists:
            restore_error: Exception | None = None
            for _attempt in range(2):
                try:
                    files.replace(state.backup, state.path)
                except Exception as error:
                    restore_error = error
                else:
                    restore_error = None
                    break
            if restore_error is not None:
                errors.append(restore_error)
                if state.install_attempted:
                    try:
                        files.remove(state.path)
                    except Exception as error:
                        errors.append(error)
            continue
        if not state.existed and state.install_attempted:
            try:
                files.remove(state.path)
            except Exception as error:
                errors.append(error)
    try:
        files.sync_directory(parent)
    except Exception as error:
        errors.append(error)
    return errors


def _rollback_artifact_pair(
    files: FileOperations,
    *,
    artifact_path: Path,
    sidecar_path: Path,
    artifact_backup: Path,
    sidecar_backup: Path,
    artifact_existed: bool,
    sidecar_existed: bool,
    artifact_backed_up: bool,
    sidecar_backed_up: bool,
    artifact_installed: bool,
    sidecar_installed: bool,
) -> list[Exception]:
    """Restore each old output independently, retaining any failed backup."""

    errors: list[Exception] = []
    pairs = (
        (
            artifact_path,
            artifact_backup,
            artifact_existed,
            artifact_backed_up,
            artifact_installed,
        ),
        (
            sidecar_path,
            sidecar_backup,
            sidecar_existed,
            sidecar_backed_up,
            sidecar_installed,
        ),
    )
    for destination, backup, existed, backed_up, installed in pairs:
        backup_exists = backed_up or _safe_exists(files, backup)
        if backup_exists:
            restore_error: Exception | None = None
            # A local rename can fail transiently (for example, interruption or
            # an injected fault). One immediate retry keeps the pair recoverable
            # without introducing AI-style backoff into filesystem recovery.
            for _attempt in range(2):
                try:
                    files.replace(backup, destination)
                except Exception as error:
                    restore_error = error
                else:
                    restore_error = None
                    break
            if restore_error is not None:
                errors.append(restore_error)
                if installed:
                    try:
                        files.remove(destination)
                    except Exception as error:
                        errors.append(error)
            continue
        if not existed and (installed or _safe_exists(files, destination)):
            try:
                files.remove(destination)
            except Exception as error:
                errors.append(error)
    try:
        files.sync_directory(artifact_path.parent)
    except Exception as error:
        errors.append(error)
    return errors


def _safe_exists(files: FileOperations, path: Path) -> bool:
    try:
        return files.exists(path)
    except Exception:
        return False
