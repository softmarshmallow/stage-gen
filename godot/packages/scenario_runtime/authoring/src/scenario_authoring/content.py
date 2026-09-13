"""Confined, immutable local content-package assembly; no network or generation."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from .catalog import read_catalog
from .compiler import canonical_json
from .program import admit_program
from .validation import ScenarioError, logical_id

MANIFEST_NAME = "scenario-package.json"
MAX_FILES = 4096
MAX_BYTES = 512 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
CONTENT_SUFFIXES = {
    ".json",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".wav",
    ".ogg",
    ".mp3",
    ".ogv",
    ".ttf",
    ".otf",
    ".scenario",
    ".txt",
    ".md",
}


def portable_path(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\\" in value
        or ":" in value
    ):
        raise ScenarioError("content member must be a portable relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value or any(part in {".", ".."} for part in path.parts):
        raise ScenarioError(f"content member {value!r} must not escape or alias its package")
    return value


def read_member(root: Path, member: str, *, limit: int = MAX_BYTES) -> bytes:
    """Open every authored component without following symlinks, including the file."""

    parts = PurePosixPath(portable_path(member)).parts
    directory = os.open(root.resolve(strict=True), os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise ScenarioError(f"content member {member!r} must be a regular file")
            if info.st_size > limit:
                raise ScenarioError(f"content member {member!r}: exceeds its {limit}-byte limit")
            chunks = []
            consumed = 0
            while chunk := os.read(descriptor, min(1024 * 1024, limit - consumed + 1)):
                consumed += len(chunk)
                if consumed > limit:
                    raise ScenarioError(
                        f"content member {member!r}: exceeds its {limit}-byte limit"
                    )
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise ScenarioError(
            f"content member {member!r}: cannot read a regular non-symlink file"
        ) from error
    finally:
        os.close(directory)


def read_json(data: bytes, location: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in items:
            if key in result:
                raise ScenarioError(f"{location}: duplicate JSON field {key!r}")
            result[key] = item
        return result

    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=_invalid_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ScenarioError(f"{location}: invalid UTF-8 JSON: {error}") from None


def _invalid_constant(value: str) -> Any:
    raise ScenarioError(f"JSON numbers must be finite, got {value}")


def build_content_package(
    source_root: Path,
    output: Path,
    *,
    package_id: str,
    revision: int,
    catalog_path: str,
    programs: dict[str, str],
    assets: list[str],
    capabilities: dict[str, Any],
) -> dict[str, Any]:
    """Copy an explicit admitted closure into a fresh directory atomically.

    A caller downloading content uses the same manifest validation before
    activation. This writer neither downloads nor loads executable Godot content.
    """

    logical_id(package_id, "package_id")
    if type(revision) is not int or revision < 1:
        raise ScenarioError("package revision must be a positive integer")
    if output.exists() or output.is_symlink():
        raise ScenarioError("content package output must be a fresh directory")
    portable_path(catalog_path)
    if not programs:
        raise ScenarioError("content package must contain at least one program")
    captured: dict[str, bytes] = {}
    paths = [catalog_path, *programs.values(), *assets]
    if len(paths) > MAX_FILES:
        raise ScenarioError(f"content package exceeds the {MAX_FILES}-file limit")
    if len(paths) != len(set(paths)):
        raise ScenarioError("content package repeats a member path")
    total_bytes = 0
    for member in paths:
        portable_path(member)
        if member == MANIFEST_NAME or PurePosixPath(member).suffix.lower() not in CONTENT_SUFFIXES:
            raise ScenarioError(
                f"content member {member!r}: executable or unsupported content type"
            )
        captured[member] = read_member(source_root, member)
        total_bytes += len(captured[member])
        if total_bytes > MAX_BYTES:
            raise ScenarioError("content package exceeds the 512 MiB byte limit")
    catalog = read_catalog(read_json(captured[catalog_path], catalog_path), capabilities)
    requirements: dict[str, int] = {}
    for scenario_id, path in programs.items():
        logical_id(scenario_id, "program scenario_id")
        admitted = admit_program(read_json(captured[path], path), catalog)
        if admitted["scenario_id"] != scenario_id:
            raise ScenarioError(f"program {path!r}: scenario identity disagrees with manifest")
        requirements.update(admitted["required_capabilities"])
    manifest = {
        "schema_version": 1,
        "kind": "scenario-content-package",
        "package_id": package_id,
        "revision": revision,
        "scenario_version": 3,
        "catalog": catalog_path,
        "programs": dict(sorted(programs.items())),
        "required_capabilities": dict(sorted(requirements.items())),
        "files": [
            {"path": path, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
            for path, data in sorted(captured.items())
        ],
    }
    manifest_bytes = canonical_json(manifest)
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise ScenarioError("content manifest exceeds the 2 MiB byte limit")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".scenario-content-", dir=output.parent))
    try:
        for path, data in captured.items():
            destination = staging / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        (staging / MANIFEST_NAME).write_bytes(manifest_bytes)
        verify_content_package(staging, capabilities=capabilities)
        # A concurrently appearing target must never be replaced. mkdir reserves
        # the fresh destination; os.rename replaces only this empty reservation.
        output.mkdir()
        try:
            os.replace(staging, output)
        except BaseException:
            output.rmdir()
            raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return manifest


def verify_content_package(root: Path, *, capabilities: dict[str, Any]) -> dict[str, Any]:
    manifest = read_json(read_member(root, MANIFEST_NAME, limit=MAX_MANIFEST_BYTES), MANIFEST_NAME)
    fields = {
        "schema_version",
        "kind",
        "package_id",
        "revision",
        "scenario_version",
        "catalog",
        "programs",
        "required_capabilities",
        "files",
    }
    if not isinstance(manifest, dict) or set(manifest) != fields:
        raise ScenarioError("content manifest has missing or unknown fields")
    if (
        manifest["kind"] != "scenario-content-package"
        or type(manifest["schema_version"]) is not int
        or manifest["schema_version"] != 1
    ):
        raise ScenarioError("unsupported content manifest identity")
    if type(manifest["scenario_version"]) is not int or manifest["scenario_version"] != 3:
        raise ScenarioError("unsupported content scenario version")
    logical_id(manifest["package_id"], "package_id")
    if type(manifest["revision"]) is not int or manifest["revision"] < 1:
        raise ScenarioError("package revision must be a positive integer")
    files = manifest["files"]
    if not isinstance(files, list) or not files or len(files) > MAX_FILES:
        raise ScenarioError("content manifest needs a nonempty file closure")
    captured: dict[str, bytes] = {}
    total_bytes = 0
    for record in files:
        if not isinstance(record, dict) or set(record) != {"path", "sha256", "bytes"}:
            raise ScenarioError("content file entry requires path, sha256 and bytes")
        path = portable_path(record["path"])
        if (
            path == MANIFEST_NAME
            or path in captured
            or PurePosixPath(path).suffix.lower() not in CONTENT_SUFFIXES
        ):
            raise ScenarioError(f"content member {path!r}: duplicate or unsupported member")
        data = read_member(root, path)
        if type(record["bytes"]) is not int or record["bytes"] < 0 or len(data) != record["bytes"]:
            raise ScenarioError(f"content member {path!r}: byte size disagrees with manifest")
        if (
            not isinstance(record["sha256"], str)
            or hashlib.sha256(data).hexdigest() != record["sha256"]
        ):
            raise ScenarioError(f"content member {path!r}: digest disagrees with manifest")
        captured[path] = data
        total_bytes += len(data)
        if total_bytes > MAX_BYTES:
            raise ScenarioError("content package exceeds the 512 MiB byte limit")
    actual: set[str] = set()
    for directory, children, leaves in os.walk(root, followlinks=False):
        for name in [*children, *leaves]:
            candidate = Path(directory) / name
            if candidate.is_symlink():
                raise ScenarioError("content package must not contain symlinks")
        actual.update((Path(directory) / name).relative_to(root).as_posix() for name in leaves)
    if actual != set(captured) | {MANIFEST_NAME}:
        raise ScenarioError("content package contains unlisted or missing files")
    catalog_path = portable_path(manifest["catalog"])
    if catalog_path not in captured:
        raise ScenarioError("content catalog is not in the verified file closure")
    catalog = read_catalog(read_json(captured[catalog_path], catalog_path), capabilities)
    if not isinstance(manifest["programs"], dict) or not manifest["programs"]:
        raise ScenarioError("content package must name at least one program")
    required: dict[str, int] = {}
    for scenario_id, path in manifest["programs"].items():
        logical_id(scenario_id, "program scenario_id")
        path = portable_path(path)
        if path not in captured:
            raise ScenarioError(f"program {path!r} is not in the verified file closure")
        program = admit_program(read_json(captured[path], path), catalog)
        if program["scenario_id"] != scenario_id:
            raise ScenarioError(f"program {path!r} identity disagrees with manifest")
        required.update(program["required_capabilities"])
    if manifest["required_capabilities"] != required:
        raise ScenarioError("manifest capabilities disagree with the admitted program closure")
    return manifest
