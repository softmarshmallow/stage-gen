"""Private source-copy mechanics; each owner selects its payload and dependencies."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

EXCLUDED = {".godot", ".git", "__pycache__", ".DS_Store", ".gdignore"}


def files(root: Path, skip: frozenset[Path] = frozenset()) -> list[Path]:
    if not root.is_dir() or root.is_symlink():
        raise ValueError(f"Source must be a real directory: {root}")
    result: list[Path] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in EXCLUDED for part in relative.parts):
            continue
        if any(relative == entry or entry in relative.parents for entry in skip):
            continue
        if path.is_symlink():
            raise ValueError(f"Source contains a symbolic link: {relative}")
        if path.is_file():
            result.append(relative)
    if not result:
        raise ValueError(f"Source contains no files: {root}")
    return result


def copy_files(root: Path, destination: Path, selected: list[Path]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in selected:
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Copy reference must remain relative: {relative}")
        source = root / relative
        if source.is_symlink() or not source.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Copy source leaves its owner: {relative}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Copied file differs from source: {relative}")
        hashes[relative.as_posix()] = digest
    return hashes


def addon_dependencies(payload: Path) -> tuple[str, ...]:
    """Only dependencies explicitly declared by the addon are traversed."""
    manifest = payload / "sdk.json"
    if not manifest.exists():
        return ()
    document = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"Addon metadata must be an object: {payload.name}")
    dependencies = document.get("dependencies", [])
    if not isinstance(dependencies, list) or any(
        not isinstance(name, str)
        or not name
        or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_" for character in name)
        for name in dependencies
    ):
        raise ValueError(f"Invalid addon dependency declaration: {payload.name}")
    if len(dependencies) != len(set(dependencies)):
        raise ValueError(f"Duplicate addon dependency declaration: {payload.name}")
    return tuple(dependencies)


def addon_closure(payload: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    visiting: set[str] = set()

    def visit(candidate: Path) -> None:
        name = candidate.name
        source = candidate.resolve(strict=True)
        if name in visiting:
            raise ValueError(f"Cyclic addon dependency: {name}")
        if name in result:
            if result[name] != source:
                raise ValueError(f"Conflicting addon dependency: {name}")
            return
        visiting.add(name)
        # Resolve dependencies beside the declaring install, before following
        # its approved development link to the actual package payload.
        for dependency in addon_dependencies(source):
            visit(candidate.parent / dependency)
        visiting.remove(name)
        result[name] = source

    visit(payload)
    return result


@contextmanager
def staged_destination(destination: Path) -> Iterator[Path]:
    """Publish only a complete fresh source tree; failed copying leaves no output."""
    if destination.exists() or destination.is_symlink():
        raise ValueError("Destination already exists; choose a new directory.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        yield temporary
        if destination.exists() or destination.is_symlink():
            raise ValueError("Destination appeared during assembly; refusing to replace it.")
        temporary.rename(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
