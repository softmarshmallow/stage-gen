"""Path confinement helpers for public filesystem boundaries."""

from __future__ import annotations

import os
import re
import stat as stat_module
from pathlib import Path

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_WINDOWS_ABSOLUTE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")


def assert_safe_path_segment(value: str, label: str) -> str:
    if not _SAFE_SEGMENT.fullmatch(value) or value in {".", ".."}:
        raise ValueError(f"{label} must be one safe path segment")
    return value


def resolve_relative_path_within_root(
    root_path: str | os.PathLike[str],
    requested_path: str,
    label: str,
) -> Path:
    if (
        not requested_path
        or "\x00" in requested_path
        or Path(requested_path).is_absolute()
        or _WINDOWS_ABSOLUTE.match(requested_path)
    ):
        raise ValueError(f"{label} must be relative")
    if "\\" in requested_path:
        raise ValueError(f"{label} contains an invalid path separator")
    segments = requested_path.split("/")
    if any(not segment or segment in {".", ".."} for segment in segments):
        raise ValueError(f"{label} contains an unsafe path segment")
    root = Path(root_path).absolute()
    output = root.joinpath(*segments).absolute()
    try:
        output.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{label} escapes its root") from error
    return output


def resolve_writable_path_within_root(
    root_path: str | os.PathLike[str],
    requested_path: str,
    label: str,
) -> Path:
    resolve_relative_path_within_root(root_path, requested_path, label)
    root_unresolved = Path(root_path)
    root_unresolved.mkdir(parents=True, exist_ok=True)
    root = root_unresolved.resolve(strict=True)
    segments = requested_path.split("/")
    parent = root
    for segment in segments[:-1]:
        parent = parent / segment
        try:
            stat = parent.lstat()
        except FileNotFoundError:
            break
        if parent.is_symlink():
            raise ValueError(f"{label} has a symlinked parent")
        if not stat_module.S_ISDIR(stat.st_mode):
            raise ValueError(f"{label} parent is not a directory")
    return resolve_relative_path_within_root(root, requested_path, label)
