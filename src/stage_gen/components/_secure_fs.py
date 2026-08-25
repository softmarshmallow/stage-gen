"""Descriptor-confined filesystem reads for authored contract sources.

Authored contracts - character profiles and game contracts alike - are read from a root the
operator names on the command line, at a relative path the request document supplies. That is
a path an author controls pointing into a tree an operator controls, so the read is confined
here rather than trusted: every ancestor is opened by descriptor with `O_NOFOLLOW`, so a
symlink anywhere along the way fails instead of escaping, and the final open must land on a
regular file.

This lives at the components root rather than inside either contract package because both
need exactly these rules and a second copy would drift from this one - the same reason
`ANATOMICAL_NOUNS` is shared rather than duplicated.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class SecurePathError(ValueError):
    """Raised when an authored contract path is missing, non-regular, or symlinked."""


@contextmanager
def open_absolute_directory(path: str | Path, *, label: str) -> Iterator[int]:
    absolute = Path(path).absolute()
    current = _open_directory(absolute.anchor, label=label)
    try:
        for part in absolute.parts[1:]:
            following = _open_directory(part, dir_fd=current, label=label)
            os.close(current)
            current = following
        yield current
    finally:
        os.close(current)


def read_absolute_regular_file(path: str | Path, *, label: str) -> bytes:
    absolute = Path(path).absolute()
    if any(part in {".", ".."} for part in absolute.parts[1:]):
        raise SecurePathError(f"{label} must not contain dot or parent path segments")
    with open_absolute_directory(absolute.parent, label=label) as directory_fd:
        return read_relative_regular_file(
            directory_fd,
            (absolute.name,),
            label=label,
        )


def read_relative_regular_file(
    directory_fd: int,
    parts: tuple[str, ...],
    *,
    label: str,
) -> bytes:
    _validate_portable_relative_parts(parts, label=label)
    descriptors: list[int] = []
    current_fd = directory_fd
    try:
        for part in parts[:-1]:
            current_fd = _open_directory(part, dir_fd=current_fd, label=label)
            descriptors.append(current_fd)
        descriptor = _open_regular_file(parts[-1], dir_fd=current_fd, label=label)
        try:
            return _read_all(descriptor)
        finally:
            os.close(descriptor)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _open_directory(path: str | Path, *, label: str, dir_fd: int | None = None) -> int:
    try:
        mode = os.stat(path, dir_fd=dir_fd, follow_symlinks=False).st_mode
        if stat.S_ISLNK(mode):
            raise SecurePathError(f"{label} must not traverse a symlink")
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_DIRECTORY,
            dir_fd=dir_fd,
        )
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            raise SecurePathError(f"{label} must remain inside directories")
        return descriptor
    except SecurePathError:
        raise
    except OSError as error:
        raise SecurePathError(
            f"{label} must be an existing directory with non-symlink ancestors"
        ) from error


def _open_regular_file(path: str | Path, *, dir_fd: int, label: str) -> int:
    try:
        mode = os.stat(path, dir_fd=dir_fd, follow_symlinks=False).st_mode
        if stat.S_ISLNK(mode):
            raise SecurePathError(
                f"{label} must be a regular non-symlink file; path must not traverse a symlink"
            )
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=dir_fd,
        )
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            raise SecurePathError(f"{label} must be a regular non-symlink file")
        return descriptor
    except SecurePathError:
        raise
    except OSError as error:
        raise SecurePathError(f"{label} must be an existing regular non-symlink file") from error


def _read_all(descriptor: int) -> bytes:
    chunks: list[bytes] = []
    while chunk := os.read(descriptor, 1024 * 1024):
        chunks.append(chunk)
    return b"".join(chunks)


def _validate_portable_relative_parts(parts: tuple[str, ...], *, label: str) -> None:
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise SecurePathError(
            f"{label} must use non-empty portable relative path segments without dot or parent"
        )
    if any("/" in part or "\\" in part or ":" in part or "\x00" in part for part in parts):
        raise SecurePathError(f"{label} must use portable relative path segments")
