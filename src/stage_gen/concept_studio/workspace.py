"""Filesystem contract for ignored game concept workspaces."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import os
import re
import stat
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from gnode import ArtifactProvenance, AtomicWriteError
from stage_gen.media import ImageFacts, inspect_image

CONCEPT_STUDIO_DIR = "concept-studio"
WORKSPACES_DIR = "workspaces"
_CONCEPT_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_IMAGE_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
_LOCK_NAME = ".concept-studio.lock"


@dataclass(frozen=True, slots=True)
class _ArtifactSnapshot:
    data: bytes
    provenance_bytes: bytes
    provenance: ArtifactProvenance
    facts: ImageFacts


@dataclass(frozen=True, slots=True)
class _WorkspaceHandle:
    path: Path
    directory_fd: int
    images_fd: int
    _directory_chain: tuple[tuple[Path, tuple[int, int]], ...]

    @property
    def images_path(self) -> Path:
        return self.path / "images"

    def assert_current(self) -> None:
        for path, identity in self._directory_chain:
            _assert_path_identity(path, identity, "concept workspace")


def find_repository_root(start: str | Path) -> Path:
    candidate = Path(start)
    if candidate.is_file():
        candidate = candidate.parent
    candidate = candidate.resolve()
    for path in (candidate, *candidate.parents):
        if (
            (path / "pyproject.toml").is_file()
            and (path / "src/stage_gen").is_dir()
            and (path / CONCEPT_STUDIO_DIR / "AGENTS.md").is_file()
        ):
            return path
    raise ValueError("stage-gen repository root could not be found from the current directory")


def validate_concept_id(value: str) -> str:
    if len(value) > 80 or _CONCEPT_ID.fullmatch(value) is None:
        raise ValueError("concept id must be lowercase hyphen-case with at most 80 characters")
    return value


def validate_image_name(value: str) -> str:
    if len(value) > 80 or _IMAGE_NAME.fullmatch(value) is None:
        raise ValueError("image name must be lowercase hyphen-case with at most 80 characters")
    return value


def workspace_root(repository_root: str | Path) -> Path:
    with _open_workspaces_directory(repository_root, create=True) as (root, _directory_fd):
        return root


def resolve_workspace(repository_root: str | Path, concept_id: str) -> Path:
    with _open_workspace_handle(repository_root, concept_id) as workspace:
        workspace.assert_current()
        return workspace.path


def create_workspace(
    repository_root: str | Path,
    *,
    concept_id: str,
    title: str,
    brief: str,
) -> dict[str, object]:
    identifier = validate_concept_id(concept_id)
    clean_title = title.strip()
    clean_brief = brief.strip()
    if not clean_title:
        raise ValueError("concept title must be non-empty")
    if not clean_brief:
        raise ValueError("concept brief must be non-empty")
    concept = (
        f"# {clean_title}\n\n"
        "> Status: exploratory game concept only; not a game package or implementation plan.\n\n"
        "## Short brief\n\n"
        f"{clean_brief}\n"
    ).encode()
    with (
        _open_workspaces_directory(repository_root, create=True) as (root, workspaces_fd),
        _locked_directory(workspaces_fd),
    ):
        try:
            os.mkdir(identifier, mode=0o700, dir_fd=workspaces_fd)
        except FileExistsError as error:
            raise ValueError(f"concept workspace already exists: {identifier}") from error
        workspace_fd = _open_directory_at(
            workspaces_fd,
            identifier,
            f"concept workspace {identifier}",
        )
        try:
            os.mkdir("images", mode=0o700, dir_fd=workspace_fd)
            os.mkdir("prompts", mode=0o700, dir_fd=workspace_fd)
            _publish_files_at(
                workspace_fd,
                (("concept.md", concept),),
                replace=False,
                conflict_message=f"concept workspace already exists: {identifier}",
                check_location=lambda: _assert_path_identity(
                    root / identifier,
                    _identity_from_fd(workspace_fd),
                    "concept workspace",
                ),
            )
        finally:
            os.close(workspace_fd)
    workspace = root / identifier
    return {
        "schema_version": 1,
        "kind": "game_concept_workspace_v1",
        "concept_id": identifier,
        "workspace": str(workspace),
        "concept_path": str(workspace / "concept.md"),
        "images_path": str(workspace / "images"),
    }


def image_paths(
    workspace: Path,
    image_name: str,
) -> tuple[Path, Path]:
    """Return display paths; availability is rechecked by the atomic publisher."""

    name = validate_image_name(image_name)
    artifact = workspace / "images" / f"{name}.png"
    return artifact, Path(f"{artifact}.meta.json")


def select_candidate(
    repository_root: str | Path,
    *,
    concept_id: str,
    candidate: str,
    replace: bool = False,
) -> dict[str, object]:
    candidate_name = validate_image_name(candidate)
    if candidate_name == "cover":
        raise ValueError("candidate must name an exploratory image, not cover")
    with (
        _open_workspace_handle(repository_root, concept_id) as workspace,
        _locked_directory(workspace.images_fd),
    ):
        workspace.assert_current()
        snapshot = _read_artifact_pair_at(
            workspace.images_fd,
            f"{candidate_name}.png",
            f"{candidate_name}.png.meta.json",
        )
        cover, cover_sidecar = image_paths(workspace.path, "cover")
        _publish_files_at(
            workspace.images_fd,
            (
                (cover.name, snapshot.data),
                (cover_sidecar.name, snapshot.provenance_bytes),
            ),
            replace=replace,
            conflict_message="concept image already exists: cover",
            check_location=workspace.assert_current,
        )
    return {
        "schema_version": 1,
        "kind": "game_concept_cover_selection_v1",
        "concept_id": concept_id,
        "candidate": candidate_name,
        "cover_path": str(cover),
        "provenance_path": str(cover_sidecar),
        "sha256": hashlib.sha256(snapshot.data).hexdigest(),
        "bytes": len(snapshot.data),
    }


def check_workspace(
    repository_root: str | Path,
    *,
    concept_id: str,
    draft: bool = False,
) -> dict[str, object]:
    with _open_workspace_handle(repository_root, concept_id) as workspace:
        workspace.assert_current()
        concept_data = _read_regular_file_at(
            workspace.directory_fd,
            "concept.md",
            "concept.md",
        )
        if not concept_data.decode("utf-8").strip():
            raise ValueError("concept.md must be non-empty")
        _validate_workspace_tree(workspace.directory_fd)
        cover = workspace.images_path / "cover.png"
        cover_sidecar = Path(f"{cover}.meta.json")
        cover_facts: dict[str, object] | None = None
        with _locked_directory(workspace.images_fd):
            workspace.assert_current()
            artifact_exists = _entry_exists_at(workspace.images_fd, cover.name)
            sidecar_exists = _entry_exists_at(workspace.images_fd, cover_sidecar.name)
            if artifact_exists or sidecar_exists:
                snapshot = _read_artifact_pair_at(
                    workspace.images_fd,
                    cover.name,
                    cover_sidecar.name,
                )
                artifact = snapshot.provenance.artifact
                assert artifact is not None
                cover_facts = {
                    "path": str(cover),
                    "provenance_path": str(cover_sidecar),
                    "sha256": artifact.sha256,
                    "bytes": artifact.bytes,
                    "width": snapshot.facts.width,
                    "height": snapshot.facts.height,
                    "model": snapshot.provenance.model,
                }
            elif not draft:
                raise ValueError(
                    "concept workspace requires images/cover.png and its provenance sidecar"
                )
    return {
        "valid": True,
        "schema_version": 1,
        "kind": "game_concept_workspace_check_v1",
        "concept_id": concept_id,
        "workspace": str(workspace.path),
        "concept_path": str(workspace.path / "concept.md"),
        "cover": cover_facts,
        "draft": draft,
    }


@contextmanager
def _open_workspace_handle(
    repository_root: str | Path,
    concept_id: str,
) -> Iterator[_WorkspaceHandle]:
    identifier = validate_concept_id(concept_id)
    with _open_workspaces_directory(repository_root, create=True) as (
        workspaces_path,
        workspaces_fd,
    ):
        workspace_path = workspaces_path / identifier
        try:
            workspace_fd = _open_directory_at(
                workspaces_fd,
                identifier,
                f"concept workspace {identifier}",
            )
        except ValueError as error:
            raise ValueError(f"concept workspace does not exist: {identifier}") from error
        try:
            images_fd = _open_directory_at(workspace_fd, "images", "concept images directory")
        except Exception:
            os.close(workspace_fd)
            raise
        chain = (
            (workspaces_path, _identity_from_fd(workspaces_fd)),
            (workspace_path, _identity_from_fd(workspace_fd)),
            (workspace_path / "images", _identity_from_fd(images_fd)),
        )
        handle = _WorkspaceHandle(
            path=workspace_path,
            directory_fd=workspace_fd,
            images_fd=images_fd,
            _directory_chain=chain,
        )
        try:
            handle.assert_current()
            yield handle
        finally:
            os.close(images_fd)
            os.close(workspace_fd)


def _assert_image_output_available(
    workspace: _WorkspaceHandle,
    image_name: str,
    *,
    replace: bool,
) -> tuple[Path, Path]:
    artifact, sidecar = image_paths(workspace.path, image_name)
    if replace:
        return artifact, sidecar
    with _locked_directory(workspace.images_fd):
        workspace.assert_current()
        if _entry_exists_at(workspace.images_fd, artifact.name) or _entry_exists_at(
            workspace.images_fd, sidecar.name
        ):
            raise ValueError(f"concept image already exists: {validate_image_name(image_name)}")
    return artifact, sidecar


def _publish_image_pair(
    workspace: _WorkspaceHandle,
    image_name: str,
    artifact_data: bytes,
    provenance_data: bytes,
    *,
    replace: bool,
) -> tuple[Path, Path]:
    artifact, sidecar = image_paths(workspace.path, image_name)
    with _locked_directory(workspace.images_fd):
        workspace.assert_current()
        _publish_files_at(
            workspace.images_fd,
            ((artifact.name, artifact_data), (sidecar.name, provenance_data)),
            replace=replace,
            conflict_message=f"concept image already exists: {validate_image_name(image_name)}",
            check_location=workspace.assert_current,
        )
    return artifact, sidecar


def read_regular_file_snapshot(path: str | Path, label: str) -> bytes:
    try:
        descriptor = os.open(os.fspath(path), _FILE_FLAGS)
    except OSError as error:
        raise ValueError(f"{label} must be a regular non-symlink file") from error
    try:
        return _read_open_regular_file(descriptor, label)
    finally:
        os.close(descriptor)


@contextmanager
def _open_workspaces_directory(
    repository_root: str | Path,
    *,
    create: bool,
) -> Iterator[tuple[Path, int]]:
    root_path = Path(repository_root).absolute()
    repository_fd = _open_directory_path(root_path, "stage-gen repository root")
    studio_fd = -1
    workspaces_fd = -1
    try:
        studio_fd = _open_directory_at(repository_fd, CONCEPT_STUDIO_DIR, "concept-studio root")
        if create:
            with contextlib.suppress(FileExistsError):
                os.mkdir(WORKSPACES_DIR, mode=0o700, dir_fd=studio_fd)
        workspaces_fd = _open_directory_at(
            studio_fd,
            WORKSPACES_DIR,
            "concept workspaces root",
        )
        path = root_path / CONCEPT_STUDIO_DIR / WORKSPACES_DIR
        _assert_path_identity(path, _identity_from_fd(workspaces_fd), "concept workspaces root")
        yield path, workspaces_fd
    finally:
        if workspaces_fd >= 0:
            os.close(workspaces_fd)
        if studio_fd >= 0:
            os.close(studio_fd)
        os.close(repository_fd)


def _open_directory_path(path: Path, label: str) -> int:
    try:
        descriptor = os.open(os.fspath(path), _DIRECTORY_FLAGS)
    except OSError as error:
        raise ValueError(f"{label} must be a non-symlink directory") from error
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise ValueError(f"{label} must be a non-symlink directory")
    return descriptor


def _open_directory_at(parent_fd: int, name: str, label: str) -> int:
    try:
        descriptor = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    except OSError as error:
        raise ValueError(f"{label} must be a non-symlink directory") from error
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise ValueError(f"{label} must be a non-symlink directory")
    return descriptor


@contextmanager
def _locked_directory(directory_fd: int) -> Iterator[None]:
    try:
        lock_fd = os.open(
            _LOCK_NAME,
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=directory_fd,
        )
    except OSError as error:
        raise ValueError("concept workspace lock must be a regular non-symlink file") from error
    try:
        if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
            raise ValueError("concept workspace lock must be a regular non-symlink file")
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def _publish_files_at(
    directory_fd: int,
    entries: tuple[tuple[str, bytes], ...],
    *,
    replace: bool,
    conflict_message: str,
    check_location: Callable[[], None],
) -> None:
    if not entries or len({name for name, _data in entries}) != len(entries):
        raise ValueError("concept publication entries must be non-empty and unique")
    if any(
        not name or name in {".", ".."} or "/" in name or "\\" in name or "\x00" in name
        for name, _data in entries
    ):
        raise ValueError("concept publication entries must use safe file names")
    token = uuid.uuid4().hex
    temporaries: dict[str, tuple[str, tuple[int, int]]] = {}
    backups: dict[str, str] = {}
    installed: dict[str, tuple[int, int]] = {}
    try:
        check_location()
        for name, data in entries:
            temporary = f".{name}.{token}.tmp"
            identity = _write_exclusive_file_at(directory_fd, temporary, data)
            temporaries[name] = (temporary, identity)
        if replace:
            for name, _data in entries:
                existing = _entry_stat_at(directory_fd, name)
                if existing is None:
                    continue
                if not stat.S_ISREG(existing.st_mode):
                    raise ValueError("concept image destinations must be regular files")
                backup = f".{name}.{token}.backup"
                os.replace(name, backup, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
                backups[name] = backup
            for name, _data in entries:
                temporary, identity = temporaries[name]
                os.replace(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
                installed[name] = identity
                del temporaries[name]
        else:
            for name, _data in entries:
                temporary, identity = temporaries[name]
                try:
                    os.link(
                        temporary,
                        name,
                        src_dir_fd=directory_fd,
                        dst_dir_fd=directory_fd,
                        follow_symlinks=False,
                    )
                except FileExistsError as error:
                    raise ValueError(conflict_message) from error
                installed[name] = identity
        check_location()
        os.fsync(directory_fd)
    except Exception as error:
        rollback_failed = _rollback_publication_at(
            directory_fd,
            installed=installed,
            backups=backups,
        )
        if rollback_failed:
            raise AtomicWriteError(
                "concept publication failed and rollback was incomplete; recovery backups remain"
            ) from error
        raise
    finally:
        for temporary, _identity in temporaries.values():
            _safe_unlink_at(directory_fd, temporary)
        with contextlib.suppress(OSError):
            os.fsync(directory_fd)
    for backup in backups.values():
        _safe_unlink_at(directory_fd, backup)
    with contextlib.suppress(OSError):
        os.fsync(directory_fd)


def _rollback_publication_at(
    directory_fd: int,
    *,
    installed: dict[str, tuple[int, int]],
    backups: dict[str, str],
) -> bool:
    failed = False
    for name, identity in reversed(tuple(installed.items())):
        if _entry_identity_at(directory_fd, name) == identity:
            try:
                os.unlink(name, dir_fd=directory_fd)
            except OSError:
                failed = True
        elif _entry_exists_at(directory_fd, name):
            failed = True
    for name, backup in reversed(tuple(backups.items())):
        if _entry_exists_at(directory_fd, name):
            failed = True
            continue
        try:
            os.replace(backup, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        except OSError:
            failed = True
    with contextlib.suppress(OSError):
        os.fsync(directory_fd)
    return failed


def _write_exclusive_file_at(directory_fd: int, name: str, data: bytes) -> tuple[int, int]:
    descriptor = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
        dir_fd=directory_fd,
    )
    try:
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("concept publication write made no progress")
            view = view[written:]
        os.fsync(descriptor)
        return _identity_from_fd(descriptor)
    finally:
        os.close(descriptor)


def _read_artifact_pair_at(
    directory_fd: int,
    artifact_name: str,
    sidecar_name: str,
) -> _ArtifactSnapshot:
    artifact_data = _read_regular_file_at(directory_fd, artifact_name, "concept image")
    provenance_data = _read_regular_file_at(
        directory_fd,
        sidecar_name,
        "concept image provenance",
    )
    try:
        record = ArtifactProvenance.model_validate_json(provenance_data)
    except Exception as error:
        raise ValueError("concept image provenance is invalid") from error
    if record.artifact is None:
        raise ValueError("concept image provenance has no artifact digest")
    if (
        record.artifact.bytes != len(artifact_data)
        or record.artifact.sha256 != hashlib.sha256(artifact_data).hexdigest()
    ):
        raise ValueError("concept image bytes do not match provenance")
    if record.artifact.media_type != "image/png":
        raise ValueError("concept images must use image/png provenance")
    facts = inspect_image(artifact_data, expected_media_type="image/png")
    return _ArtifactSnapshot(
        data=artifact_data,
        provenance_bytes=provenance_data,
        provenance=record,
        facts=facts,
    )


def _read_regular_file_at(directory_fd: int, name: str, label: str) -> bytes:
    try:
        descriptor = os.open(name, _FILE_FLAGS, dir_fd=directory_fd)
    except OSError as error:
        raise ValueError(f"{label} must be a regular non-symlink file") from error
    try:
        return _read_open_regular_file(descriptor, label)
    finally:
        os.close(descriptor)


def _read_open_regular_file(descriptor: int, label: str) -> bytes:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"{label} must be a regular non-symlink file")
    chunks: list[bytes] = []
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        chunks.append(chunk)
    after = os.fstat(descriptor)
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if before_identity != after_identity:
        raise ValueError(f"{label} changed while it was being read")
    return b"".join(chunks)


def _validate_workspace_tree(directory_fd: int) -> None:
    for name in os.listdir(directory_fd):
        if name == "game.toml":
            raise ValueError("concept workspaces must not contain game.toml")
        entry = _entry_stat_at(directory_fd, name)
        if entry is None:
            raise ValueError("concept workspace changed during validation")
        if stat.S_ISLNK(entry.st_mode):
            raise ValueError("concept workspaces must not contain symlinks")
        if stat.S_ISDIR(entry.st_mode):
            child_fd = _open_directory_at(directory_fd, name, "concept workspace directory")
            try:
                _validate_workspace_tree(child_fd)
            finally:
                os.close(child_fd)
        elif not stat.S_ISREG(entry.st_mode):
            raise ValueError("concept workspaces may contain only regular files and directories")


def _entry_stat_at(directory_fd: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _entry_exists_at(directory_fd: int, name: str) -> bool:
    return _entry_stat_at(directory_fd, name) is not None


def _entry_identity_at(directory_fd: int, name: str) -> tuple[int, int] | None:
    observed = _entry_stat_at(directory_fd, name)
    return None if observed is None else (observed.st_dev, observed.st_ino)


def _identity_from_fd(descriptor: int) -> tuple[int, int]:
    observed = os.fstat(descriptor)
    return observed.st_dev, observed.st_ino


def _assert_path_identity(path: Path, identity: tuple[int, int], label: str) -> None:
    try:
        observed = os.stat(path, follow_symlinks=False)
    except OSError as error:
        raise ValueError(f"{label} changed while in use") from error
    if not stat.S_ISDIR(observed.st_mode) or (observed.st_dev, observed.st_ino) != identity:
        raise ValueError(f"{label} changed while in use")


def _safe_unlink_at(directory_fd: int, name: str) -> None:
    with contextlib.suppress(OSError):
        os.unlink(name, dir_fd=directory_fd)
