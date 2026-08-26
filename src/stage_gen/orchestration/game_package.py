"""Validation of one canonical, recipe-bound game source package.

The component contracts deliberately know nothing about one another.  A game package does: it
selects a recipe request, resolves every digest-bound source that request names, and proves that
the resulting game, soundtrack, and map catalog form one current closure.  That composition
belongs here rather than in any component or in ``web/``.

This validator is intentionally current-only.  It never upgrades, rewrites, or interprets an old
contract.  Optional recipe systems remain optional, but a selector can require the systems its
demo promises to ship.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tomllib
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Literal, cast

from pydantic import Field, field_validator, model_validator

from stage_gen.components._secure_fs import (
    SecurePathError,
    open_absolute_directory,
    read_relative_regular_file,
)
from stage_gen.components.game_contract import (
    GAME_CONTRACT_SCHEMA_VERSION,
    ResolvedGameContract,
    resolve_game_contract_binding,
)
from stage_gen.components.game_map import (
    GAME_MAP_BOOK_SCHEMA_VERSION,
    GAME_MAP_SCHEMA_VERSION,
    GameMapBook,
    ResolvedGameMapBook,
    resolve_game_map_book_binding,
)
from stage_gen.components.game_soundtrack import (
    GAME_SOUNDTRACK_SCHEMA_VERSION,
    ResolvedGameSoundtrack,
    resolve_game_soundtrack_binding,
)
from stage_gen.contracts.artifacts import PersistedContractModel
from stage_gen.recipes.scrolling_preview.recipe import parse_scrolling_preview_input

GAME_PACKAGE_SELECTOR_SCHEMA_VERSION = 1
GAME_PACKAGE_VALIDATION_SCHEMA_VERSION = 1
MAIN_GAME_SELECTOR_REF = "library/games/main.toml"

GamePackageFeature = Literal["game", "soundtrack", "map_book", "village"]
RepositoryStatus = Literal["committed", "modified", "untracked", "not_git_checkout"]

_FEATURE_ORDER: tuple[GamePackageFeature, ...] = (
    "game",
    "soundtrack",
    "map_book",
    "village",
)
_REQUEST_PREFIX = ("examples", "scrolling-preview")
_PACKAGE_REQUEST_FIELDS = frozenset({"prompt", *_FEATURE_ORDER})


class GamePackageValidationError(ValueError):
    """One actionable reason a selected source package is not current and complete."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class GamePackageSelector(PersistedContractModel):
    """The repository-level pointer to one canonical demo request."""

    schema_version: Literal[1]
    kind: Literal["game-package-v1"]
    game_id: str = Field(
        pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$",
        max_length=96,
    )
    recipe: Literal["scrolling-preview"]
    request_ref: str
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    transparency_mode: Literal["native", "ai", "chroma"]
    required_features: list[GamePackageFeature] = Field(min_length=1)

    @field_validator("request_ref")
    @classmethod
    def validate_request_ref(cls, value: str) -> str:
        parts = _portable_parts(value, label="game package request_ref")
        if len(parts) != 3 or parts[:2] != _REQUEST_PREFIX or not parts[2].endswith(".toml"):
            raise ValueError(
                "game package request_ref must equal examples/scrolling-preview/<request>.toml"
            )
        return value

    @field_validator("required_features")
    @classmethod
    def validate_required_features(
        cls, value: list[GamePackageFeature]
    ) -> list[GamePackageFeature]:
        if len(set(value)) != len(value):
            raise ValueError("required_features must be unique")
        if value != [feature for feature in _FEATURE_ORDER if feature in value]:
            raise ValueError("required_features must use canonical feature order")
        return value

    @model_validator(mode="after")
    def require_game(self) -> GamePackageSelector:
        if "game" not in self.required_features:
            raise ValueError("a game package must require the game feature")
        return self


def validate_game_package(
    workspace_root: str | Path,
    *,
    selector_ref: str = MAIN_GAME_SELECTOR_REF,
    require_tracked: bool = False,
    require_committed: bool = False,
) -> dict[str, object]:
    """Validate one exact-current source closure and return a JSON-ready report.

    Repository state is not part of source validity.  ``require_tracked`` checks Git membership;
    the stronger ``require_committed`` proves that ``HEAD`` contains the exact bytes validated.
    The default works in copied package forks and source archives.
    """

    root = Path(workspace_root).absolute()
    if selector_ref != MAIN_GAME_SELECTOR_REF:
        raise GamePackageValidationError(
            "invalid_selector_ref",
            f"selector_ref must equal {MAIN_GAME_SELECTOR_REF!r}",
        )

    selector_bytes, selector_document = _read_toml(
        root,
        selector_ref,
        label="game package selector",
        code="invalid_selector",
    )
    try:
        selector = GamePackageSelector.model_validate(selector_document)
    except ValueError as error:
        raise GamePackageValidationError(
            "invalid_selector", f"invalid game package selector: {error}"
        ) from error

    request_bytes, request_document = _read_toml(
        root,
        selector.request_ref,
        label="game package request",
        code="invalid_request",
    )
    if hashlib.sha256(request_bytes).hexdigest() != selector.request_sha256:
        raise GamePackageValidationError(
            "request_digest_mismatch",
            "game package request_sha256 does not match the selected request bytes",
        )
    request = _parse_exact_request(request_document)
    _require_selected_features(selector, request)

    game, applied_defaults = _resolve_game(root, request, selector.game_id)
    soundtrack = _resolve_soundtrack(root, request, selector.game_id)
    map_book = _resolve_map_book(root, request, selector.game_id)

    _validate_cross_contract_closure(game, soundtrack, map_book)
    expected_game_sources = _expected_game_sources(game, soundtrack, map_book)
    actual_game_sources = _list_game_toml_sources(root, selector.game_id)
    orphan_sources = sorted(actual_game_sources - expected_game_sources)
    if orphan_sources:
        raise GamePackageValidationError(
            "orphan_game_source",
            "selected game directory contains TOML sources outside the request closure: "
            + ", ".join(orphan_sources),
        )

    closure = _closure_entries(
        selector_ref=selector_ref,
        selector_bytes=selector_bytes,
        request_ref=selector.request_ref,
        request_bytes=request_bytes,
        game=game,
        soundtrack=soundtrack,
        map_book=map_book,
    )
    repository_status, untracked_refs, modified_refs = _repository_tracking(root, closure)
    if (require_tracked or require_committed) and repository_status in {
        "untracked",
        "not_git_checkout",
    }:
        detail = (
            ", ".join(untracked_refs) if untracked_refs else "workspace root is not a Git checkout"
        )
        raise GamePackageValidationError(
            "untracked_game_package",
            f"canonical game package must be Git-tracked: {detail}",
        )
    if require_committed and repository_status != "committed":
        detail_refs = untracked_refs or modified_refs
        detail = ", ".join(detail_refs) if detail_refs else "workspace root is not a Git checkout"
        raise GamePackageValidationError(
            "uncommitted_game_package",
            f"canonical game package bytes must match Git HEAD: {detail}",
        )

    identity: dict[str, object] = {
        "selector": selector.model_dump(mode="json"),
        "request": request,
        "game": game.identity(),
        **({"soundtrack": soundtrack.identity()} if soundtrack is not None else {}),
        **({"map_book": map_book.identity()} if map_book is not None else {}),
    }
    package_sha256 = _canonical_json_sha256(identity)
    features = [feature for feature in _FEATURE_ORDER if feature in request]

    schema_versions: dict[str, int] = {
        "game_contract": game.contract.schema_version,
    }
    if soundtrack is not None:
        schema_versions["game_soundtrack"] = soundtrack.soundtrack.schema_version
    if map_book is not None:
        schema_versions["game_map_book"] = map_book.book.schema_version
        schema_versions["game_map"] = map_book.document.schema_version

    return {
        "schema_version": GAME_PACKAGE_VALIDATION_SCHEMA_VERSION,
        "kind": "game-package-validation-v1",
        "valid": True,
        "source_status": "current",
        "generated_status": "not_checked",
        "disposition": (
            "track_before_publish"
            if repository_status == "untracked"
            else "commit_before_publish"
            if repository_status == "modified"
            else "keep_source"
        ),
        "game_id": selector.game_id,
        "recipe": selector.recipe,
        "transparency_mode": selector.transparency_mode,
        "request_ref": selector.request_ref,
        "features": features,
        "required_features": list(selector.required_features),
        "schema_versions": schema_versions,
        "applied_defaults": list(applied_defaults),
        "package_sha256": package_sha256,
        "closure": closure,
        "repository": {
            "status": repository_status,
            "untracked_refs": list(untracked_refs),
            "modified_refs": list(modified_refs),
        },
    }


def invalid_game_package_report(error: GamePackageValidationError) -> dict[str, object]:
    """Return the stable machine-readable rejection shape used by the standalone tool."""

    source_is_current = error.code in {
        "untracked_game_package",
        "uncommitted_game_package",
    }
    disposition = (
        "commit_before_publish"
        if error.code == "uncommitted_game_package"
        else "track_before_publish"
        if source_is_current
        else "drop_or_repair_source"
    )
    return {
        "schema_version": GAME_PACKAGE_VALIDATION_SCHEMA_VERSION,
        "kind": "game-package-validation-v1",
        "valid": False,
        "source_status": "current" if source_is_current else "invalid",
        "generated_status": "not_checked",
        "disposition": disposition,
        "errors": [{"code": error.code, "message": str(error)}],
    }


def _portable_parts(value: str, *, label: str) -> tuple[str, ...]:
    if not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")
    if "\\" in value or ":" in value or value.startswith("/"):
        raise ValueError(f"{label} must be a portable relative path")
    parts = tuple(value.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"{label} must not contain empty, dot, or parent segments")
    return parts


def _read_toml(
    root: Path,
    ref: str,
    *,
    label: str,
    code: str,
) -> tuple[bytes, dict[str, object]]:
    try:
        parts = _portable_parts(ref, label=label)
        with open_absolute_directory(root, label="game package workspace root") as root_fd:
            data = read_relative_regular_file(root_fd, parts, label=label)
        decoded = data.decode("utf-8")
        raw: object = tomllib.loads(decoded)
    except (
        OSError,
        SecurePathError,
        UnicodeDecodeError,
        ValueError,
        tomllib.TOMLDecodeError,
    ) as error:
        raise GamePackageValidationError(code, f"{label} is invalid: {error}") from error
    if not isinstance(raw, dict) or any(not isinstance(key, str) for key in raw):
        raise GamePackageValidationError(code, f"{label} must decode to a TOML table")
    return data, cast(dict[str, object], raw)


def _parse_exact_request(document: dict[str, object]) -> dict[str, object]:
    prompt = document.get("prompt")
    if not isinstance(prompt, str) or not prompt or prompt != prompt.strip():
        raise GamePackageValidationError(
            "invalid_request",
            "game package request prompt must be a non-empty trimmed string",
        )
    unsupported = sorted(set(document) - _PACKAGE_REQUEST_FIELDS)
    if unsupported:
        raise GamePackageValidationError(
            "unsupported_request_field",
            "game package request contains unsupported fields: " + ", ".join(unsupported),
        )
    try:
        parsed = parse_scrolling_preview_input(document)
    except ValueError as error:
        raise GamePackageValidationError(
            "invalid_request", f"game package request is invalid: {error}"
        ) from error
    unknown = sorted(set(document) - set(parsed))
    if unknown:
        raise GamePackageValidationError(
            "unsupported_request_field",
            "game package request contains unsupported fields: " + ", ".join(unknown),
        )
    if set(document) != set(parsed):
        missing = sorted(set(parsed) - set(document))
        raise GamePackageValidationError(
            "noncanonical_request",
            "game package request does not use the canonical authored shape: " + ", ".join(missing),
        )
    return cast(dict[str, object], parsed)


def _require_selected_features(
    selector: GamePackageSelector,
    request: Mapping[str, object],
) -> None:
    missing = [feature for feature in selector.required_features if feature not in request]
    if missing:
        raise GamePackageValidationError(
            "missing_required_feature",
            "game package request is missing required features: " + ", ".join(missing),
        )


def _resolve_game(
    root: Path,
    request: Mapping[str, object],
    game_id: str,
) -> tuple[ResolvedGameContract, tuple[str, ...]]:
    value = request.get("game")
    if value is None:
        raise GamePackageValidationError(
            "missing_required_feature", "game package request is missing required feature: game"
        )
    ref = _binding_ref(value, label="game contract")
    game_document = _preflight_current_document(
        root,
        ref,
        label="game contract",
        code="invalid_game_contract",
        schema_version=GAME_CONTRACT_SCHEMA_VERSION,
        kind=f"game-contract-v{GAME_CONTRACT_SCHEMA_VERSION}",
    )
    try:
        resolved = resolve_game_contract_binding(value, game_library_root=root)
    except ValueError as error:
        raise GamePackageValidationError(
            "invalid_game_contract", f"game contract is invalid: {error}"
        ) from error
    expected_ref = f"library/games/{game_id}/game.toml"
    if resolved.binding.ref != expected_ref or resolved.contract.game_id != game_id:
        raise GamePackageValidationError(
            "game_id_mismatch",
            "selector game_id must match the bound game contract and library directory",
        )
    if resolved.contract.schema_version != GAME_CONTRACT_SCHEMA_VERSION:
        raise GamePackageValidationError(
            "unsupported_schema_version",
            "game contract schema_version must equal current version "
            f"{GAME_CONTRACT_SCHEMA_VERSION}",
        )
    gameplay_document = game_document.get("gameplay")
    combat_text_was_declared = isinstance(gameplay_document, Mapping) and (
        "combat_text" in gameplay_document
    )
    applied_defaults = () if combat_text_was_declared else ("gameplay.combat_text",)
    return resolved, applied_defaults


def _resolve_soundtrack(
    root: Path,
    request: Mapping[str, object],
    game_id: str,
) -> ResolvedGameSoundtrack | None:
    value = request.get("soundtrack")
    if value is None:
        return None
    ref = _binding_ref(value, label="game soundtrack")
    _preflight_current_document(
        root,
        ref,
        label="game soundtrack",
        code="invalid_game_soundtrack",
        schema_version=GAME_SOUNDTRACK_SCHEMA_VERSION,
        kind=f"game-soundtrack-v{GAME_SOUNDTRACK_SCHEMA_VERSION}",
    )
    try:
        resolved = resolve_game_soundtrack_binding(value, game_library_root=root)
    except ValueError as error:
        raise GamePackageValidationError(
            "invalid_game_soundtrack", f"game soundtrack is invalid: {error}"
        ) from error
    expected_ref = f"library/games/{game_id}/soundtrack.toml"
    if resolved.binding.ref != expected_ref or resolved.soundtrack.game_id != game_id:
        raise GamePackageValidationError(
            "game_id_mismatch",
            "selector game_id must match the bound soundtrack and library directory",
        )
    if resolved.soundtrack.schema_version != GAME_SOUNDTRACK_SCHEMA_VERSION:
        raise GamePackageValidationError(
            "unsupported_schema_version",
            "game soundtrack schema_version must equal current version "
            f"{GAME_SOUNDTRACK_SCHEMA_VERSION}",
        )
    return resolved


def _resolve_map_book(
    root: Path,
    request: Mapping[str, object],
    game_id: str,
) -> ResolvedGameMapBook | None:
    value = request.get("map_book")
    if value is None:
        return None
    ref = _binding_ref(value, label="game map book")
    map_book_document = _preflight_current_document(
        root,
        ref,
        label="game map book",
        code="invalid_game_map_book",
        schema_version=GAME_MAP_BOOK_SCHEMA_VERSION,
        kind=f"game-map-book-v{GAME_MAP_BOOK_SCHEMA_VERSION}",
    )
    try:
        current_map_book = GameMapBook.model_validate(map_book_document)
    except ValueError as error:
        raise GamePackageValidationError(
            "invalid_game_map_book", f"game map book is invalid: {error}"
        ) from error
    for map_reference in current_map_book.maps:
        map_ref = f"library/games/{current_map_book.game_id}/maps/{map_reference.map_id}.toml"
        _preflight_current_document(
            root,
            map_ref,
            label=f"game map {map_reference.map_id}",
            code="invalid_game_map_book",
            schema_version=GAME_MAP_SCHEMA_VERSION,
            kind=f"game-map-v{GAME_MAP_SCHEMA_VERSION}",
        )
    try:
        resolved = resolve_game_map_book_binding(value, game_library_root=root)
    except ValueError as error:
        raise GamePackageValidationError(
            "invalid_game_map_book", f"game map book is invalid: {error}"
        ) from error
    expected_ref = f"library/games/{game_id}/maps/index.toml"
    if resolved.binding.ref != expected_ref or resolved.book.game_id != game_id:
        raise GamePackageValidationError(
            "game_id_mismatch",
            "selector game_id must match the bound map book and library directory",
        )
    if resolved.book.schema_version != GAME_MAP_BOOK_SCHEMA_VERSION:
        raise GamePackageValidationError(
            "unsupported_schema_version",
            "game map book schema_version must equal current version "
            f"{GAME_MAP_BOOK_SCHEMA_VERSION}",
        )
    if resolved.document.schema_version != GAME_MAP_SCHEMA_VERSION:
        raise GamePackageValidationError(
            "unsupported_schema_version",
            f"every game map schema_version must equal current version {GAME_MAP_SCHEMA_VERSION}",
        )
    return resolved


def _binding_ref(value: object, *, label: str) -> str:
    if not isinstance(value, Mapping) or not isinstance(value.get("ref"), str):
        raise GamePackageValidationError(
            f"invalid_{label.replace(' ', '_')}", f"{label} binding must contain a ref"
        )
    return cast(str, value["ref"])


def _preflight_current_document(
    root: Path,
    ref: str,
    *,
    label: str,
    code: str,
    schema_version: int,
    kind: str,
) -> dict[str, object]:
    _, document = _read_toml(root, ref, label=label, code=code)
    actual_version = document.get("schema_version")
    actual_kind = document.get("kind")
    if type(actual_version) is not int or actual_version != schema_version or actual_kind != kind:
        raise GamePackageValidationError(
            "unsupported_schema_version",
            f"{label} must use exact current identity schema_version={schema_version}, "
            f"kind={kind!r}",
        )
    return document


def _validate_cross_contract_closure(
    game: ResolvedGameContract,
    soundtrack: ResolvedGameSoundtrack | None,
    map_book: ResolvedGameMapBook | None,
) -> None:
    population = game.contract.gameplay.mob_population if game.contract.gameplay else None
    if map_book is None:
        if population is not None:
            raise GamePackageValidationError(
                "incomplete_game_closure",
                "gameplay.mob_population requires a map_book in the selected request",
            )
        return
    if soundtrack is None:
        raise GamePackageValidationError(
            "incomplete_game_closure",
            "map_book requires a soundtrack in the selected request",
        )

    known_track_ids = set(soundtrack.soundtrack.track_ids)
    unknown_track_ids = sorted(map_book.document.referenced_track_ids - known_track_ids)
    if unknown_track_ids:
        raise GamePackageValidationError(
            "unknown_soundtrack_track",
            "game maps reference track IDs absent from the game soundtrack: "
            + ", ".join(unknown_track_ids),
        )

    continuous_population_maps = {
        resolved.game_map.map_id
        for resolved in map_book.maps
        if resolved.game_map.level_profile is not None
        and resolved.game_map.level_profile.mechanisms.encounter_model == "continuous_population"
    }
    population_maps = (
        {population_map.map_id for population_map in population.maps}
        if population is not None
        else set()
    )
    if population_maps != continuous_population_maps:
        raise GamePackageValidationError(
            "population_map_mismatch",
            "gameplay.mob_population map IDs must exactly equal maps whose level profile "
            "declares continuous_population",
        )


def _expected_game_sources(
    game: ResolvedGameContract,
    soundtrack: ResolvedGameSoundtrack | None,
    map_book: ResolvedGameMapBook | None,
) -> set[str]:
    expected = {game.binding.ref}
    if soundtrack is not None:
        expected.add(soundtrack.binding.ref)
    if map_book is not None:
        expected.add(map_book.binding.ref)
        expected.update(resolved.source_ref for resolved in map_book.maps)
    return expected


def _list_game_toml_sources(root: Path, game_id: str) -> set[str]:
    base_parts = ("library", "games", game_id)
    sources: set[str] = set()
    try:
        with open_absolute_directory(
            root.joinpath(*base_parts), label="selected game directory"
        ) as game_fd:
            _walk_toml_sources(game_fd, base_parts, sources)
    except (OSError, SecurePathError) as error:
        raise GamePackageValidationError(
            "invalid_game_directory", f"selected game directory is invalid: {error}"
        ) from error
    return sources


def _walk_toml_sources(
    directory_fd: int,
    prefix: tuple[str, ...],
    sources: set[str],
) -> None:
    for name in sorted(os.listdir(directory_fd)):
        mode = os.stat(name, dir_fd=directory_fd, follow_symlinks=False).st_mode
        ref_parts = (*prefix, name)
        ref = PurePosixPath(*ref_parts).as_posix()
        if stat.S_ISLNK(mode):
            raise SecurePathError(f"selected game directory must not contain symlink: {ref}")
        if stat.S_ISDIR(mode):
            child_fd = os.open(
                name,
                os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_DIRECTORY,
                dir_fd=directory_fd,
            )
            try:
                _walk_toml_sources(child_fd, ref_parts, sources)
            finally:
                os.close(child_fd)
        elif stat.S_ISREG(mode) and name.endswith(".toml"):
            sources.add(ref)


def _closure_entries(
    *,
    selector_ref: str,
    selector_bytes: bytes,
    request_ref: str,
    request_bytes: bytes,
    game: ResolvedGameContract,
    soundtrack: ResolvedGameSoundtrack | None,
    map_book: ResolvedGameMapBook | None,
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = [
        _source_entry("selector", selector_ref, selector_bytes),
        _source_entry("request", request_ref, request_bytes),
        _source_entry(
            "game",
            game.binding.ref,
            game.source_bytes,
            canonical_sha256=game.canonical_sha256,
        ),
    ]
    if soundtrack is not None:
        entries.append(
            _source_entry(
                "soundtrack",
                soundtrack.binding.ref,
                soundtrack.source_bytes,
                canonical_sha256=soundtrack.canonical_sha256,
            )
        )
    if map_book is not None:
        entries.append(
            _source_entry(
                "map_book",
                map_book.binding.ref,
                map_book.source_bytes,
                canonical_sha256=map_book.canonical_sha256,
            )
        )
        entries.extend(
            _source_entry(
                "map",
                resolved.source_ref,
                resolved.source_bytes,
                canonical_sha256=resolved.canonical_sha256,
                source_id=resolved.game_map.map_id,
            )
            for resolved in map_book.maps
        )
    return entries


def _source_entry(
    role: str,
    ref: str,
    data: bytes,
    *,
    canonical_sha256: str | None = None,
    source_id: str | None = None,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "role": role,
        "ref": ref,
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }
    if source_id is not None:
        entry["source_id"] = source_id
    if canonical_sha256 is not None:
        entry["canonical_sha256"] = canonical_sha256
    return entry


def _repository_tracking(
    root: Path,
    closure: list[dict[str, object]],
) -> tuple[RepositoryStatus, tuple[str, ...], tuple[str, ...]]:
    refs = tuple(cast(str, entry["ref"]) for entry in closure)
    try:
        probe = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if probe.returncode != 0 or probe.stdout.strip() != b"true":
            return "not_git_checkout", (), ()
        top_level = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if Path(os.fsdecode(top_level.stdout.strip())).resolve() != root.resolve():
            return "not_git_checkout", (), ()
        listed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", *refs],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        cached = subprocess.run(
            ["git", "-C", str(root), "diff", "--cached", "--name-only", "-z", "--", *refs],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return "not_git_checkout", (), ()
    tracked = {value.decode("utf-8") for value in listed.stdout.split(b"\0") if value}
    untracked = tuple(ref for ref in refs if ref not in tracked)
    if untracked:
        return "untracked", untracked, ()

    modified = {value.decode("utf-8") for value in cached.stdout.split(b"\0") if value}
    for entry in closure:
        ref = cast(str, entry["ref"])
        source_sha256 = cast(str, entry["source_sha256"])
        try:
            committed = subprocess.run(
                ["git", "-C", str(root), "show", f"HEAD:{ref}"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.CalledProcessError):
            modified.add(ref)
            continue
        if hashlib.sha256(committed.stdout).hexdigest() != source_sha256:
            modified.add(ref)
    if modified:
        return "modified", (), tuple(ref for ref in refs if ref in modified)
    return "committed", (), ()


def _canonical_json_sha256(value: object) -> str:
    data = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


__all__ = [
    "GAME_PACKAGE_SELECTOR_SCHEMA_VERSION",
    "GAME_PACKAGE_VALIDATION_SCHEMA_VERSION",
    "MAIN_GAME_SELECTOR_REF",
    "GamePackageSelector",
    "GamePackageValidationError",
    "invalid_game_package_report",
    "validate_game_package",
]
