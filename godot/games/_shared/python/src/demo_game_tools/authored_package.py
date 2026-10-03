"""Read one member of an authored package, confined to it and bound to its digest.

Every authored package here has the same shape: an operator names a root directory
on the command line, and a document inside it names further members by relative
path. That is an author-controlled path pointing into an operator-controlled tree,
so the read is confined rather than trusted, and the bytes are matched against the
digest the author recorded before anything parses them.

This exists because three contracts needed exactly these rules. The dialogue scene
and the point-and-click room each grew their own near-identical copy, and both
copies were weaker than they read: `resolve_relative_path_within_root` is lexical,
so the `is_symlink()` guard that followed it only ever inspected the FINAL path
component - an intermediate symlinked directory was accepted - and there was a
window between that check and `read_bytes()` in which the file could be replaced.
Routing every member read through `read_relative_regular_file` opens each ancestor
with `O_NOFOLLOW` instead, so the check and the read are the same operation.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from stage_gen.components._game_input import portable_relative_path, sha256_bytes
from stage_gen.components._secure_fs import open_absolute_directory, read_relative_regular_file


def read_package_member(root: Path, source: str, *, label: str) -> bytes:
    """Read one package-relative member, following no symlink below the root.

    The root is resolved first, deliberately. An operator typed that path on the
    command line, so a symlink in it is their own - and refusing one would refuse
    `/tmp` on macOS, which is a symlink to `/private/tmp`. Everything *below* the
    root came out of an authored document and is confined: each segment is opened
    `O_NOFOLLOW`, so no member can point out of the package it belongs to.
    """

    relative = portable_relative_path(source, f"{label} source")
    parts = PurePosixPath(relative).parts
    with open_absolute_directory(Path(root).resolve(), label=label) as directory_fd:
        return read_relative_regular_file(directory_fd, parts, label=label)


def read_digest_bound_member(
    root: Path,
    source: str,
    *,
    expected_sha256: str,
    label: str,
) -> bytes:
    """Read one member and refuse bytes the author did not sign for.

    The digest is checked before any caller parses the bytes, so a member that has
    drifted is refused as a package error rather than surfacing later as a
    confusing schema failure over content nobody reviewed.
    """

    data = read_package_member(root, source, label=label)
    digest = sha256_bytes(data)
    if digest != expected_sha256:
        raise ValueError(
            f"{label} {source} does not match its authored digest: "
            f"declared {expected_sha256}, found {digest}"
        )
    return data


__all__ = [
    "read_digest_bound_member",
    "read_package_member",
]
