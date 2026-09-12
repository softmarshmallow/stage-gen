"""Capture an explicit game input closure using caller-owned member resolvers.

This reader knows the retained container format and secure capture rules. The
consuming game or collection tool supplies the supported member implementations.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from demo_game_tools.input_formats.game_contract import (
    GenreMember,
    PreparedGameContract,
    canonical_prepared_game_contract_json,
    load_prepared_game_contract_bytes,
)
from demo_game_tools.io.package_capture import (
    GAME_PACKAGE_VALIDATION_KIND,
    GAME_PACKAGE_VALIDATION_SCHEMA_VERSION,
    RESOLVED_GAME_PACKAGE_KIND,
    GamePackageValidationError,
    PackageCapture,
    ResolvedGenreMember,
    ResolvedPackageFile,
    ResolvedPreparedPackage,
    capture_package,
    closure_sha256,
    validate_json_object,
    validate_utf8_text,
)
from stage_gen.components._game_input import (
    AuthoredContractLoadError,
    sha256_bytes,
)
from stage_gen.components._secure_fs import (
    SecurePathError,
    open_absolute_directory,
    read_relative_regular_file,
)


@dataclass(frozen=True, slots=True)
class GenreResolver:
    """One genre's member resolution, keyed by the `genre` word `game.toml` declares."""

    genre: str
    member_type: type[GenreMember]
    #: `(capture, *, game, member) -> resolved member`; the member is proven `member_type`.
    resolve: Callable[..., ResolvedGenreMember]


def resolve_prepared_package(
    input_path: str | Path, *, resolvers: tuple[GenreResolver, ...]
) -> ResolvedPreparedPackage:
    """Resolve any declared prepared-package genre variant with identical closure semantics."""

    source = Path(input_path).absolute()
    try:
        capture, package_name, source_kind = capture_package(source)
        return _resolve_capture(
            capture, package_name=package_name, source_kind=source_kind, resolvers=resolvers
        )
    except GamePackageValidationError:
        raise
    except (AuthoredContractLoadError, SecurePathError, OSError, ValueError) as error:
        raise GamePackageValidationError("invalid_package", str(error)) from error


def validate_game_package(
    input_path: str | Path,
    *,
    resolvers: tuple[GenreResolver, ...],
    repository_root: str | Path | None = None,
    require_tracked: bool = False,
    require_committed: bool = False,
) -> dict[str, object]:
    """Validate an explicitly selected input closure, optionally against Git."""

    source = Path(input_path).absolute()
    resolved = resolve_prepared_package(source, resolvers=resolvers)
    repository: dict[str, object] = {
        "status": "not_checked",
        "untracked_refs": [],
        "modified_refs": [],
    }
    if repository_root is not None:
        root = Path(repository_root).absolute()
        try:
            relative = source.relative_to(root)
        except ValueError as error:
            raise GamePackageValidationError(
                "outside_repository", "input must be inside repository root"
            ) from error
        closure_refs = (
            [(relative / entry.path).as_posix() for entry in resolved.files]
            if resolved.source_kind == "directory"
            else [relative.as_posix()]
        )
        repository = _repository_report(
            root,
            closure_refs,
            require_tracked=require_tracked or require_committed,
            require_committed=require_committed,
        )
    elif require_tracked or require_committed:
        raise GamePackageValidationError(
            "repository_required", "repository_root is required for Git checks"
        )
    return {
        **resolved.identity(),
        "schema_version": GAME_PACKAGE_VALIDATION_SCHEMA_VERSION,
        "kind": GAME_PACKAGE_VALIDATION_KIND,
        "valid": True,
        "source_status": "current",
        "generated_status": "not_checked",
        "disposition": "generate_or_review",
        "closure": [entry.identity() for entry in resolved.files],
        "repository": repository,
    }


def invalid_game_package_report(error: GamePackageValidationError) -> dict[str, object]:
    source_is_current = error.code in {
        "untracked_game_package",
        "uncommitted_game_package",
    }
    disposition = (
        "commit_before_publish"
        if error.code == "uncommitted_game_package"
        else "track_before_publish"
        if error.code == "untracked_game_package"
        else "drop_or_repair_source"
    )
    return {
        "schema_version": GAME_PACKAGE_VALIDATION_SCHEMA_VERSION,
        "kind": GAME_PACKAGE_VALIDATION_KIND,
        "valid": False,
        "source_status": "current" if source_is_current else "invalid",
        "generated_status": "not_checked",
        "disposition": disposition,
        "errors": [{"code": error.code, "message": str(error)}],
    }


def _resolve_capture(
    capture: PackageCapture,
    *,
    package_name: str,
    source_kind: Literal["directory", "zip"],
    resolvers: tuple[GenreResolver, ...],
) -> ResolvedPreparedPackage:
    game_bytes = capture.member("game.toml")
    try:
        game = load_prepared_game_contract_bytes(game_bytes)
    except AuthoredContractLoadError as error:
        raise GamePackageValidationError("invalid_game_contract", str(error)) from error

    validate_utf8_text(capture.member(game.universe.source), "universe source")

    members: dict[str, ResolvedGenreMember] = {}
    for declared in game.genres:
        members[declared.genre] = _resolve_genre(
            capture, game=game, member=declared, resolvers=resolvers
        )

    for evidence_id, evidence in game.evidence.items():
        capture.image(
            evidence.artifact_source,
            evidence.artifact_sha256,
            f"evidence {evidence_id} artifact",
        )
        provenance = capture.locked(
            evidence.provenance_source,
            evidence.provenance_sha256,
            f"evidence {evidence_id} provenance",
        )
        validate_json_object(provenance, f"evidence {evidence_id} provenance")
        review = capture.locked(
            evidence.review_source,
            evidence.review_sha256,
            f"evidence {evidence_id} review",
        )
        validate_utf8_text(review, f"evidence {evidence_id} review")

    if not members:  # pragma: no cover - the game contract's min_length proves this
        raise GamePackageValidationError(
            "missing_genre_member", "prepared package declares no supported genre member"
        )
    resolved_files = capture.close()
    return ResolvedPreparedPackage(
        source_kind=source_kind,
        package_name=package_name,
        package_sha256=sha256_bytes(game_bytes),
        canonical_game_sha256=sha256_bytes(canonical_prepared_game_contract_json(game)),
        closure_sha256=closure_sha256(resolved_files),
        game=game,
        members=members,
        files=resolved_files,
    )


def _resolve_genre(
    capture: PackageCapture,
    *,
    game: PreparedGameContract,
    member: GenreMember,
    resolvers: tuple[GenreResolver, ...],
) -> ResolvedGenreMember:
    for resolver in resolvers:
        if resolver.genre != member.genre:
            continue
        if not isinstance(member, resolver.member_type):  # pragma: no cover - union guard
            raise GamePackageValidationError(
                "invalid_game_contract", f"{member.genre} genre member has an unexpected shape"
            )
        return resolver.resolve(capture, game=game, member=member)
    raise GamePackageValidationError(  # pragma: no cover - the genre Literal refuses first
        "invalid_game_contract", f"no recipe resolves the {member.genre} genre member"
    )


def _read_workspace_file(root: Path, relative: str, *, label: str) -> bytes:
    try:
        with open_absolute_directory(root, label="workspace root") as root_fd:
            return read_relative_regular_file(
                root_fd,
                tuple(PurePosixPath(relative).parts),
                label=label,
            )
    except SecurePathError as error:
        raise GamePackageValidationError("invalid_package", str(error)) from error


def _repository_report(
    root: Path,
    refs: list[str],
    *,
    require_tracked: bool,
    require_committed: bool,
) -> dict[str, object]:
    probe = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        if require_tracked or require_committed:
            raise GamePackageValidationError(
                "not_git_checkout", "repository verification requires a Git checkout"
            )
        return {"status": "not_git_checkout", "untracked_refs": [], "modified_refs": []}

    untracked: list[str] = []
    modified: list[str] = []
    for ref in refs:
        tracked = (
            subprocess.run(
                ["git", "-C", str(root), "ls-files", "--error-unmatch", "--", ref],
                check=False,
                capture_output=True,
            ).returncode
            == 0
        )
        if not tracked:
            untracked.append(ref)
            continue
        if require_committed:
            head = subprocess.run(
                ["git", "-C", str(root), "show", f"HEAD:{ref}"],
                check=False,
                capture_output=True,
            )
            if head.returncode != 0 or head.stdout != _read_workspace_file(
                root, ref, label=f"repository source {ref}"
            ):
                modified.append(ref)
    if require_tracked and untracked:
        raise GamePackageValidationError(
            "untracked_game_package", "package closure contains untracked files"
        )
    if require_committed and modified:
        raise GamePackageValidationError(
            "uncommitted_game_package", "package closure differs from Git HEAD"
        )
    return {
        "status": (
            "committed"
            if require_committed and not modified
            else "tracked"
            if not untracked
            else "mixed"
        ),
        "untracked_refs": untracked,
        "modified_refs": modified,
    }


__all__ = [
    "GAME_PACKAGE_VALIDATION_KIND",
    "GAME_PACKAGE_VALIDATION_SCHEMA_VERSION",
    "RESOLVED_GAME_PACKAGE_KIND",
    "GamePackageValidationError",
    "GenreResolver",
    "ResolvedPackageFile",
    "ResolvedPreparedPackage",
    "invalid_game_package_report",
    "resolve_prepared_package",
    "validate_game_package",
]
