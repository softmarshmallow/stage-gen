"""Resolve one exact-current prepared game directory or ZIP before provider work."""

from __future__ import annotations

import io
import json
import os
import stat
import subprocess
import zipfile
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path, PurePosixPath
from typing import Literal

from PIL import Image, UnidentifiedImageError
from pydantic import Field, field_validator, model_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import (
    GAME_ID_PATTERN,
    AuthoredContractLoadError,
    parse_toml_contract,
    portable_relative_path,
    sha256_bytes,
)
from stage_gen.components._secure_fs import (
    SecurePathError,
    open_absolute_directory,
    read_absolute_regular_file,
    read_relative_regular_file,
)
from stage_gen.components.game_contract import (
    PlatformerGenreMember,
    PreparedGameContract,
    RunnerGenreMember,
    canonical_prepared_game_contract_json,
    load_prepared_game_contract_bytes,
)
from stage_gen.components.game_soundtrack import GameSoundtrack, load_game_soundtrack_bytes
from stage_gen.components.game_ui import GameUi, load_game_ui_bytes
from stage_gen.components.platformer_content import (
    PLAYER_CLIMB_STATE_BY_CLIMBABLE_ROLE,
    WEAPON_CLASSES_BY_PLAYER_EQUIPMENT,
    ItemContentCatalog,
    MobContentCatalog,
    NpcContentCatalog,
    PlayerContentCatalog,
    ProjectileContentCatalog,
    PropContentCatalog,
    load_item_content_bytes,
    load_mob_content_bytes,
    load_npc_content_bytes,
    load_player_content_bytes,
    load_projectile_content_bytes,
    load_prop_content_bytes,
)
from stage_gen.components.platformer_gameplay import (
    GameplayContract,
    GrantItemEffect,
    SetQuestStateEffect,
    load_gameplay_contract_bytes,
)
from stage_gen.components.platformer_map import (
    PreparedGameMap,
    bottom_contiguous_surface_row,
    load_prepared_game_map_bytes,
)
from stage_gen.components.runner_audio import RunnerAudioContract, load_runner_audio_bytes
from stage_gen.components.runner_content import (
    RunnerAvatarCatalog,
    declared_motion_states,
    load_runner_avatar_bytes,
)
from stage_gen.components.runner_gameplay import (
    PLACEMENT_PROFILES,
    RUNNER_PLACEMENT_PROFILE,
    CollisionProfile,
    DuckProfile,
    JumpArc,
    PlacementProfile,
    RunnerGameplayContract,
    SpeedProfile,
    apron_columns,
    arc_height_rows,
    clearable_span_columns,
    drop_scatter_columns,
    hazard_press_window_seconds,
    jump_arc,
    load_runner_gameplay_bytes,
)
from stage_gen.components.runner_track import (
    RunnerHazard,
    RunnerSegmentChunk,
    RunnerSegments,
    RunnerTrack,
    load_runner_track_bytes,
)
from stage_gen.components.scenario import (
    ResolvedScenario,
    ScenarioCatalog,
    load_scenario_catalog_bytes,
    resolve_scenario_bytes,
)

MAIN_GAME_SELECTOR_REF = "library/games/main.toml"
GAME_PACKAGE_VALIDATION_SCHEMA_VERSION = 5
GAME_PACKAGE_SELECTOR_SCHEMA_VERSION = 4

_MAX_PACKAGE_FILES = 512
_MAX_PACKAGE_FILE_BYTES = 64 * 1024 * 1024
_MAX_PACKAGE_BYTES = 512 * 1024 * 1024
_MAX_ZIP_COMPRESSION_RATIO = 200


class GamePackageValidationError(ValueError):
    """Stable package rejection with a machine-readable category."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class GamePackageSelector(PersistedContractModel):
    schema_version: Literal[4]
    kind: Literal["game-package-v4"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    package_ref: str

    @field_validator("package_ref")
    @classmethod
    def validate_package_ref(cls, value: str) -> str:
        return portable_relative_path(value, "package_ref")

    @model_validator(mode="after")
    def validate_layout(self) -> GamePackageSelector:
        expected = f"library/games/{self.game_id}/game.toml"
        if self.package_ref != expected:
            raise ValueError(f"package_ref must equal {expected}")
        return self


@dataclass(frozen=True, slots=True)
class ResolvedPackageFile:
    path: str
    sha256: str
    data: bytes

    def identity(self) -> dict[str, object]:
        return {"path": self.path, "sha256": self.sha256, "bytes": len(self.data)}


@dataclass(frozen=True, slots=True)
class ResolvedRunnerMember:
    """The runner genre member's resolved contracts, when the game declares one."""

    member: RunnerGenreMember
    gameplay: RunnerGameplayContract
    track: RunnerTrack
    avatar: RunnerAvatarCatalog
    props: PropContentCatalog
    items: ItemContentCatalog
    audio: RunnerAudioContract
    soundtrack: GameSoundtrack | None


@dataclass(frozen=True, slots=True)
class ResolvedGamePackage:
    """Fully captured and cross-validated prepared input."""

    source_kind: Literal["directory", "zip"]
    package_name: str
    package_sha256: str
    canonical_game_sha256: str
    closure_sha256: str
    game: PreparedGameContract
    #: The resolved platformer genre member: the camera, cast, and member table
    #: this family's recipe reads.
    platformer: PlatformerGenreMember
    #: The runner genre member, resolved when the game declares one.
    runner: ResolvedRunnerMember | None
    gameplay: GameplayContract
    ui: GameUi
    soundtrack: GameSoundtrack
    maps: tuple[PreparedGameMap, ...]
    player: PlayerContentCatalog
    mobs: MobContentCatalog
    npcs: NpcContentCatalog
    props: PropContentCatalog
    items: ItemContentCatalog
    #: None for a package whose weapons throw nothing, which is most of them.
    projectiles: ProjectileContentCatalog | None
    scenario_catalog: ScenarioCatalog
    scenarios: tuple[ResolvedScenario, ...]
    files: tuple[ResolvedPackageFile, ...]

    def file(self, path: str) -> ResolvedPackageFile:
        for entry in self.files:
            if entry.path == path:
                return entry
        raise KeyError(path)

    def identity(self) -> dict[str, object]:
        return {
            "schema_version": GAME_PACKAGE_VALIDATION_SCHEMA_VERSION,
            "kind": "resolved-game-package-v5",
            "game_id": self.game.game_id,
            "revision": self.game.revision,
            "package_sha256": self.package_sha256,
            "canonical_game_sha256": self.canonical_game_sha256,
            "closure_sha256": self.closure_sha256,
            "source_kind": self.source_kind,
            "file_count": len(self.files),
            "genres": {
                "platformer": {
                    "map_ids": [entry.map_id for entry in self.maps],
                    "player_ids": [entry.player_id for entry in self.player.players],
                    "mob_ids": [entry.mob_id for entry in self.mobs.mobs],
                    "npc_ids": [entry.npc_id for entry in self.npcs.npcs],
                    "prop_ids": [entry.prop_id for entry in self.props.props],
                    "item_ids": [entry.item_id for entry in self.items.items],
                    "projectile_ids": (
                        []
                        if self.projectiles is None
                        else [entry.projectile_id for entry in self.projectiles.projectiles]
                    ),
                    "scenario_ids": [entry.declarations.scenario_id for entry in self.scenarios],
                    "track_ids": list(self.soundtrack.track_ids),
                },
                **(
                    {}
                    if self.runner is None
                    else {
                        "runner": {
                            "track_id": self.runner.track.track_id,
                            "avatar_id": self.runner.avatar.avatar.avatar_id,
                            "segment_ids": [
                                entry.segment_id for entry in self.runner.track.segments.chunks
                            ],
                            "prop_ids": [entry.prop_id for entry in self.runner.props.props],
                            "item_ids": [entry.item_id for entry in self.runner.items.items],
                            "effect_ids": [entry.effect_id for entry in self.runner.audio.effects],
                            "track_ids": (
                                []
                                if self.runner.soundtrack is None
                                else list(self.runner.soundtrack.track_ids)
                            ),
                        }
                    }
                ),
            },
        }


def resolve_game_package(input_path: str | Path) -> ResolvedGamePackage:
    """Resolve a prepared directory or ZIP with identical closure semantics."""

    source = Path(input_path).absolute()
    try:
        if source.suffix.lower() == ".zip":
            files, package_name = _capture_zip(source)
            source_kind: Literal["directory", "zip"] = "zip"
        else:
            files, package_name = _capture_directory(source)
            source_kind = "directory"
        return _resolve_captured_package(
            files,
            package_name=package_name,
            source_kind=source_kind,
        )
    except GamePackageValidationError:
        raise
    except (AuthoredContractLoadError, SecurePathError, OSError, ValueError) as error:
        raise GamePackageValidationError("invalid_package", str(error)) from error


def validate_game_package(
    workspace_root: str | Path,
    *,
    selector_ref: str = MAIN_GAME_SELECTOR_REF,
    require_tracked: bool = False,
    require_committed: bool = False,
) -> dict[str, object]:
    """Validate the repository-selected exact-current prepared package."""

    root = Path(workspace_root).absolute()
    if selector_ref != MAIN_GAME_SELECTOR_REF:
        raise GamePackageValidationError(
            "invalid_selector", f"selector must equal {MAIN_GAME_SELECTOR_REF}"
        )
    selector_bytes = _read_workspace_file(root, selector_ref, label="game package selector")
    try:
        selector = parse_toml_contract(
            selector_bytes,
            model=GamePackageSelector,
            label="game package selector",
        )
    except AuthoredContractLoadError as error:
        raise GamePackageValidationError("invalid_selector", str(error)) from error

    package_root = root.joinpath(*PurePosixPath(selector.package_ref).parts).parent
    resolved = resolve_game_package(package_root)
    if resolved.game.game_id != selector.game_id:
        raise GamePackageValidationError(
            "cross_game_identity", "selector game_id does not match prepared package"
        )

    closure_refs = [
        selector_ref,
        *[f"library/games/{selector.game_id}/{entry.path}" for entry in resolved.files],
    ]
    repository = _repository_report(
        root,
        closure_refs,
        require_tracked=require_tracked or require_committed,
        require_committed=require_committed,
    )
    return {
        **resolved.identity(),
        "schema_version": GAME_PACKAGE_VALIDATION_SCHEMA_VERSION,
        "kind": "game-package-validation-v5",
        "valid": True,
        "source_status": "current",
        "generated_status": "not_checked",
        "disposition": "generate_or_review",
        "selector": {
            "path": MAIN_GAME_SELECTOR_REF,
            "sha256": sha256_bytes(selector_bytes),
            "package_ref": selector.package_ref,
        },
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
        "kind": "game-package-validation-v5",
        "valid": False,
        "source_status": "current" if source_is_current else "invalid",
        "generated_status": "not_checked",
        "disposition": disposition,
        "errors": [{"code": error.code, "message": str(error)}],
    }


def _capture_directory(root: Path) -> tuple[dict[str, bytes], str]:
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


def _capture_zip(path: Path) -> tuple[dict[str, bytes], str]:
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


def _resolve_captured_package(
    files: dict[str, bytes],
    *,
    package_name: str,
    source_kind: Literal["directory", "zip"],
) -> ResolvedGamePackage:
    game_bytes = _required_file(files, "game.toml")
    try:
        game = load_prepared_game_contract_bytes(game_bytes)
    except AuthoredContractLoadError as error:
        raise GamePackageValidationError("invalid_game_contract", str(error)) from error
    platformer = game.platformer_member()
    if platformer is None:
        raise GamePackageValidationError(
            "missing_genre_member", "prepared package declares no platformer genre member"
        )
    expected: dict[str, str] = {"game.toml": sha256_bytes(game_bytes)}

    def member(source: str) -> bytes:
        """Register one authored member and capture its digest at ingest."""

        data = _required_file(files, source)
        expected.setdefault(source, sha256_bytes(data))
        return data

    def locked(source: str, digest: str, label: str) -> bytes:
        previous = expected.setdefault(source, digest)
        if previous != digest:
            raise GamePackageValidationError(
                "conflicting_source_digest", f"{label} has conflicting locked digests"
            )
        data = _required_file(files, source)
        actual = sha256_bytes(data)
        if actual != digest:
            raise GamePackageValidationError(
                "stale_source_digest",
                f"{label} source_sha256 mismatch for {source}: expected {digest}, got {actual}",
            )
        return data

    universe_bytes = member(game.universe.source)
    _validate_utf8_text(universe_bytes, "universe source")

    gameplay = _load_locked(
        member(platformer.gameplay.source),
        load_gameplay_contract_bytes,
        "invalid_gameplay_contract",
    )
    ui = _load_locked(
        member(platformer.ui.source),
        load_game_ui_bytes,
        "invalid_game_ui_contract",
    )
    soundtrack = _load_locked(
        member(platformer.soundtrack.source),
        lambda data: load_game_soundtrack_bytes(data, source_suffix=".toml"),
        "invalid_soundtrack_contract",
    )
    maps = tuple(
        _load_locked(
            member(binding.source),
            load_prepared_game_map_bytes,
            "invalid_map_contract",
        )
        for binding in platformer.maps
    )
    player = _load_locked(
        member(platformer.content.player.source),
        load_player_content_bytes,
        "invalid_player_content",
    )
    mobs = _load_locked(
        member(platformer.content.mobs.source),
        load_mob_content_bytes,
        "invalid_mob_content",
    )
    npcs = _load_locked(
        member(platformer.content.npcs.source),
        load_npc_content_bytes,
        "invalid_npc_content",
    )
    props = _load_locked(
        member(platformer.content.props.source),
        load_prop_content_bytes,
        "invalid_prop_content",
    )
    items = _load_locked(
        member(platformer.content.items.source),
        load_item_content_bytes,
        "invalid_item_content",
    )
    projectiles = (
        None
        if platformer.content.projectiles is None
        else _load_locked(
            member(platformer.content.projectiles.source),
            load_projectile_content_bytes,
            "invalid_projectile_content",
        )
    )
    scenario_catalog = _load_locked(
        member(platformer.scenarios.index_source),
        load_scenario_catalog_bytes,
        "invalid_scenario_catalog",
    )
    scenarios = tuple(
        _resolve_scenario_member(member, scenario_id)
        for scenario_id in scenario_catalog.scenario_ids
    )

    runner_member = game.member("runner")
    runner: ResolvedRunnerMember | None = None
    if runner_member is not None:
        if not isinstance(runner_member, RunnerGenreMember):  # pragma: no cover - union guard
            raise GamePackageValidationError(
                "invalid_game_contract", "runner genre member has an unexpected shape"
            )
        runner = _resolve_runner_member(member, locked, runner_member=runner_member)

    for evidence_id, evidence in game.evidence.items():
        artifact = locked(
            evidence.artifact_source,
            evidence.artifact_sha256,
            f"evidence {evidence_id} artifact",
        )
        _validate_image(artifact, evidence.artifact_source)
        provenance = locked(
            evidence.provenance_source,
            evidence.provenance_sha256,
            f"evidence {evidence_id} provenance",
        )
        _validate_json_object(provenance, f"evidence {evidence_id} provenance")
        review = locked(
            evidence.review_source,
            evidence.review_sha256,
            f"evidence {evidence_id} review",
        )
        _validate_utf8_text(review, f"evidence {evidence_id} review")

    for game_map in maps:
        for map_reference in game_map.references:
            data = locked(
                map_reference.source,
                map_reference.source_sha256,
                f"map {game_map.map_id} reference {map_reference.reference_id}",
            )
            _validate_image(data, map_reference.source)
    for label, catalog in (
        ("player", player),
        ("mob", mobs),
        ("NPC", npcs),
        ("prop", props),
        ("item", items),
        *(() if projectiles is None else (("projectile", projectiles),)),
    ):
        for content_reference in catalog.references:
            data = locked(
                content_reference.source,
                content_reference.source_sha256,
                f"{label} reference {content_reference.reference_id}",
            )
            _validate_image(data, content_reference.source)
    for ui_reference in ui.references:
        data = locked(
            ui_reference.source,
            ui_reference.source_sha256,
            f"UI reference {ui_reference.reference_id}",
        )
        _validate_image(data, ui_reference.source)

    _validate_cross_contracts(
        game=game,
        platformer=platformer,
        gameplay=gameplay,
        soundtrack=soundtrack,
        maps=maps,
        player=player,
        mobs=mobs,
        npcs=npcs,
        props=props,
        items=items,
        projectiles=projectiles,
        ui=ui,
        scenario_catalog=scenario_catalog,
        scenarios=scenarios,
    )
    if runner is not None:
        _validate_runner_member(game=game, runner=runner)

    actual_paths = set(files)
    expected_paths = set(expected)
    missing = sorted(expected_paths - actual_paths)
    if missing:
        raise GamePackageValidationError(
            "missing_package_file", "package is missing files: " + ", ".join(missing)
        )
    orphaned = sorted(actual_paths - expected_paths)
    if orphaned:
        raise GamePackageValidationError(
            "orphan_package_file", "package contains unreferenced files: " + ", ".join(orphaned)
        )

    resolved_files = tuple(
        ResolvedPackageFile(path=path, sha256=sha256_bytes(files[path]), data=files[path])
        for path in sorted(expected_paths)
    )
    return ResolvedGamePackage(
        source_kind=source_kind,
        package_name=package_name,
        package_sha256=sha256_bytes(game_bytes),
        canonical_game_sha256=sha256_bytes(canonical_prepared_game_contract_json(game)),
        closure_sha256=_closure_sha256(resolved_files),
        game=game,
        platformer=platformer,
        runner=runner,
        gameplay=gameplay,
        ui=ui,
        soundtrack=soundtrack,
        maps=maps,
        player=player,
        mobs=mobs,
        npcs=npcs,
        props=props,
        items=items,
        projectiles=projectiles,
        scenario_catalog=scenario_catalog,
        scenarios=scenarios,
        files=resolved_files,
    )


def _resolve_scenario_member(member: Callable[[str], bytes], scenario_id: str) -> ResolvedScenario:
    """Admit one scenario out of the captured package, failing with its own code."""

    try:
        return resolve_scenario_bytes(
            member(f"scenarios/{scenario_id}.toml"),
            member(f"scenarios/{scenario_id}.scenario"),
            scenario_id=scenario_id,
        )
    except (AuthoredContractLoadError, ValueError) as error:
        raise GamePackageValidationError("invalid_scenario_contract", str(error)) from error


def _resolve_runner_member(
    member: Callable[[str], bytes],
    locked: Callable[[str, str, str], bytes],
    *,
    runner_member: RunnerGenreMember,
) -> ResolvedRunnerMember:
    """Resolve the runner family's members out of the captured package."""

    gameplay = _load_locked(
        member(runner_member.gameplay.source),
        load_runner_gameplay_bytes,
        "invalid_runner_gameplay",
    )
    track = _load_locked(
        member(runner_member.track.source),
        load_runner_track_bytes,
        "invalid_runner_track",
    )
    avatar = _load_locked(
        member(runner_member.content.avatar.source),
        load_runner_avatar_bytes,
        "invalid_runner_avatar",
    )
    props = _load_locked(
        member(runner_member.content.props.source),
        load_prop_content_bytes,
        "invalid_prop_content",
    )
    items = _load_locked(
        member(runner_member.content.items.source),
        load_item_content_bytes,
        "invalid_item_content",
    )
    audio = _load_locked(
        member(runner_member.audio.source),
        load_runner_audio_bytes,
        "invalid_runner_audio",
    )
    soundtrack = (
        None
        if runner_member.soundtrack is None
        else _load_locked(
            member(runner_member.soundtrack.source),
            lambda data: load_game_soundtrack_bytes(data, source_suffix=".toml"),
            "invalid_soundtrack_contract",
        )
    )
    for track_reference in track.references:
        data = locked(
            track_reference.source,
            track_reference.source_sha256,
            f"track {track.track_id} reference {track_reference.reference_id}",
        )
        _validate_image(data, track_reference.source)
    for label, catalog in (("avatar", avatar), ("prop", props), ("item", items)):
        for content_reference in catalog.references:
            data = locked(
                content_reference.source,
                content_reference.source_sha256,
                f"runner {label} reference {content_reference.reference_id}",
            )
            _validate_image(data, content_reference.source)
    return ResolvedRunnerMember(
        member=runner_member,
        gameplay=gameplay,
        track=track,
        avatar=avatar,
        props=props,
        items=items,
        audio=audio,
        soundtrack=soundtrack,
    )


def _validate_runner_member(*, game: PreparedGameContract, runner: ResolvedRunnerMember) -> None:
    """Cross-validate the runner family: identity, bindings, seams, and clearable layouts.

    Every geometric refusal below is proved from the SDK's declared arithmetic
    (`jump_arc` and friends) against the placement discipline selected by
    `RUNNER_PLACEMENT_PROFILE`, at base speed - the worst case, since airtime
    is fixed by construction. This runs credential-free, before any spend.
    """

    owned = [
        runner.gameplay.game_id,
        runner.track.game_id,
        runner.avatar.game_id,
        runner.props.game_id,
        runner.items.game_id,
        runner.audio.game_id,
        *(() if runner.soundtrack is None else (runner.soundtrack.game_id,)),
    ]
    if any(game_id != game.game_id for game_id in owned):
        raise GamePackageValidationError(
            "cross_game_identity", "every package contract must share game.toml game_id"
        )
    if runner.member.cast.avatar_id != runner.avatar.avatar.avatar_id:
        raise GamePackageValidationError(
            "unresolved_cross_reference",
            "runner cast avatar_id must equal the avatar catalog's avatar",
        )
    if runner.gameplay.track_id != runner.track.track_id:
        raise GamePackageValidationError(
            "unresolved_cross_reference",
            "runner gameplay track_id must equal the track member's track_id",
        )
    prop_ids = {entry.prop_id for entry in runner.props.props}
    item_ids = {entry.item_id for entry in runner.items.items}
    _assert_subset(
        {hazard.prop_id for chunk in runner.track.segments.chunks for hazard in chunk.hazards},
        prop_ids,
        "segment hazard prop_id",
    )
    _assert_subset(
        {pickup.item_id for chunk in runner.track.segments.chunks for pickup in chunk.pickups},
        item_ids,
        "segment pickup item_id",
    )

    gameplay = runner.gameplay
    jump = gameplay.jump_profile()
    speed = gameplay.speed_profile()
    collision = gameplay.collision_profile()
    duck = gameplay.duck_profile()
    placement = PLACEMENT_PROFILES[RUNNER_PLACEMENT_PROFILE]
    arc = jump_arc(jump, speed)
    apron = apron_columns(jump, placement, speed)
    player_height_rows = game.scale.player_height_tiles
    prop_height_rows: dict[str, float | None] = {
        entry.prop_id: (
            None if entry.height_units is None else entry.height_units * player_height_rows
        )
        for entry in runner.props.props
    }

    declares_overhead = any(
        hazard.anchor == "overhead"
        for chunk in runner.track.segments.chunks
        for hazard in chunk.hazards
    )
    if declares_overhead and duck is None:
        raise GamePackageValidationError(
            "invalid_runner_gameplay",
            "track hangs overhead hazards; gameplay declares no duck_profile to clear them",
        )
    declared_states = declared_motion_states(runner.avatar.avatar)
    if duck is not None and "slide" not in declared_states:
        raise GamePackageValidationError(
            "invalid_runner_avatar",
            "gameplay declares a duck_profile; the avatar declares no slide motion to wear",
        )
    if duck is None and "slide" in declared_states:
        # The coupling holds in both directions: the recipe fans out and pays
        # for every declared strip, so a slide no duck profile can ever
        # trigger would be silent dead spend, not staged art.
        raise GamePackageValidationError(
            "invalid_runner_avatar",
            "avatar declares a slide motion but gameplay declares no duck_profile to trigger it",
        )

    segments = runner.track.segments
    for chunk in segments.chunks:
        _validate_runner_chunk(
            chunk=chunk,
            segments=segments,
            gameplay=gameplay,
            arc=arc,
            apron=apron,
            placement=placement,
            speed=speed,
            collision=collision,
            duck=duck,
            player_height_rows=player_height_rows,
            prop_height_rows=prop_height_rows,
        )


def _validate_runner_chunk(
    *,
    chunk: RunnerSegmentChunk,
    segments: RunnerSegments,
    gameplay: RunnerGameplayContract,
    arc: JumpArc,
    apron: int,
    placement: PlacementProfile,
    speed: SpeedProfile,
    collision: CollisionProfile,
    duck: DuckProfile | None,
    player_height_rows: float,
    prop_height_rows: dict[str, float | None],
) -> None:
    """Prove one chunk against the seam rule, the arc, and the placement discipline."""

    jump = gameplay.jump_profile()
    width = len(chunk.occupancy[0])
    heights = [bottom_contiguous_surface_row(chunk.occupancy, column) for column in range(width)]

    # The seam rule: any chunk may follow any chunk, so both seam columns must
    # present the shared walk surface. Checked before the gap rule because an
    # unsupported seam column would read as a pit against it.
    for label, column in (("first", 0), ("last", width - 1)):
        if heights[column] != segments.walk_surface_row:
            raise GamePackageValidationError(
                "segment_seam_mismatch",
                f"segment {chunk.segment_id} {label} column must be supported with its "
                f"surface at walk_surface_row {segments.walk_surface_row}",
            )

    widest = chunk.max_pit_run()
    if widest > jump.max_clear_gap_columns:
        raise GamePackageValidationError(
            "segment_gap_unclearable",
            f"segment {chunk.segment_id} has a {widest}-column pit; "
            f"{gameplay.run.jump_profile} clears at most {jump.max_clear_gap_columns}",
        )

    # The apron: one flat jump span of calm walk-surface ground at each end,
    # which is the price of keeping the seam rule cross-chunk-check-free - a
    # landing or a demand near a seam would otherwise meet the next chunk's
    # opening obstacle with no surviving launch frame.
    hazard_columns = {hazard.column for hazard in chunk.hazards}
    for column in (*range(min(apron, width)), *range(max(0, width - apron), width)):
        if heights[column] != segments.walk_surface_row:
            raise GamePackageValidationError(
                "segment_placement_violation",
                f"segment {chunk.segment_id} column {column} sits inside the {apron}-column "
                "apron and must present the shared walk surface",
            )
        if column in hazard_columns:
            raise GamePackageValidationError(
                "segment_placement_violation",
                f"segment {chunk.segment_id} places a hazard at column {column}, inside the "
                f"{apron}-column apron",
            )

    # Jump features: every consecutive supported pair, adjacent or across a
    # pit, must be within the arc - a rise steals airtime, so the span and the
    # rise are proved together rather than as two independent bounds.
    supported = [(column, surface) for column, surface in enumerate(heights) if surface is not None]
    jump_landings: list[int] = []
    feature_columns: set[int] = set()
    for (left_column, left_surface), (right_column, right_surface) in pairwise(supported):
        rise = left_surface - right_surface  # positive is up
        if rise > jump.max_rise_tiles:
            raise GamePackageValidationError(
                "invalid_runner_track",
                f"segment {chunk.segment_id} rises more than {jump.max_rise_tiles} tiles "
                f"at column {right_column}",
            )
        gap = right_column - left_column - 1
        if gap > 0:
            span = clearable_span_columns(arc, speed, rise)
            if span is None or gap + 1 > span:
                raise GamePackageValidationError(
                    "segment_gap_unclearable",
                    f"segment {chunk.segment_id} pairs a {gap}-column pit with a {rise}-tile "
                    f"rise at column {right_column}; {gameplay.run.jump_profile} spans "
                    f"{0.0 if span is None else round(span, 2)} columns at that rise",
                )
            jump_landings.append(right_column)
            feature_columns.update(range(left_column + 1, right_column))
        elif rise > 0:
            jump_landings.append(right_column)
            feature_columns.add(right_column)
        elif rise < 0:
            # A drop-off is a landing with no launch: the run leaves the ledge
            # at full speed and touches down inside a scatter zone no verb can
            # shorten. The whole zone must be level and calm at the cap speed,
            # and the drop edge is a terrain feature like any other demand.
            feature_columns.add(right_column)
            scatter = drop_scatter_columns(arc, speed, float(-rise))
            zone_end = min(width, right_column + scatter + placement.min_landing_clear_columns)
            for column in range(right_column, zone_end):
                if heights[column] != right_surface:
                    raise GamePackageValidationError(
                        "segment_placement_violation",
                        f"segment {chunk.segment_id} drop at column {right_column} lands on "
                        f"unlevel or missing ground at column {column}; its scatter zone "
                        f"spans {scatter} columns plus clearance",
                    )

    # Landing clearance: calm, level, hazard-free ground after every landing.
    # A window that runs off the chunk's edge is already proven calm by the
    # end apron, which the placement profile guarantees is at least as wide.
    for landing in jump_landings:
        for column in range(landing, min(width, landing + placement.min_landing_clear_columns)):
            if heights[column] != heights[landing]:
                raise GamePackageValidationError(
                    "segment_placement_violation",
                    f"segment {chunk.segment_id} landing at column {landing} lacks "
                    f"{placement.min_landing_clear_columns} level columns of clearance",
                )
            if column in hazard_columns:
                raise GamePackageValidationError(
                    "segment_placement_violation",
                    f"segment {chunk.segment_id} places a hazard at column {column}, inside "
                    f"the landing clearance of the jump landing at column {landing}",
                )

    # Hazard clusters: adjacent same-anchor hazards read as one silhouette and
    # are proved as one demand; everything else must stand a full separation
    # apart, from each other and from every terrain feature, so no two demands
    # ever share one arc uninvited.
    ordered = sorted(chunk.hazards, key=lambda hazard: hazard.column)
    clusters: list[list[RunnerHazard]] = []
    for hazard in ordered:
        if (
            clusters
            and hazard.anchor == clusters[-1][-1].anchor
            and hazard.column - clusters[-1][-1].column <= 1
        ):
            clusters[-1].append(hazard)
        else:
            clusters.append([hazard])
    for previous, current in pairwise(clusters):
        distance = current[0].column - previous[-1].column
        if distance < placement.min_hazard_separation_columns:
            raise GamePackageValidationError(
                "segment_placement_violation",
                f"segment {chunk.segment_id} places hazards {distance} columns apart at "
                f"columns {previous[-1].column} and {current[0].column}; the placement "
                f"discipline demands {placement.min_hazard_separation_columns}",
            )
    for cluster in clusters:
        for feature in sorted(feature_columns):
            distance = min(abs(feature - cluster[0].column), abs(feature - cluster[-1].column))
            if distance < placement.min_hazard_separation_columns:
                raise GamePackageValidationError(
                    "segment_placement_violation",
                    f"segment {chunk.segment_id} places a hazard {distance} columns from the "
                    f"terrain feature at column {feature}; the placement discipline demands "
                    f"{placement.min_hazard_separation_columns}",
                )

    # Terrain demands answer to the same separation as hazards: two features
    # closer than one flown-at-cap arc share a jump uninvited - the pit whose
    # late launches carry into the next rise's face at ramped speed.
    feature_groups: list[list[int]] = []
    for feature in sorted(feature_columns):
        if feature_groups and feature - feature_groups[-1][-1] <= 1:
            feature_groups[-1].append(feature)
        else:
            feature_groups.append([feature])
    for previous_group, current_group in pairwise(feature_groups):
        distance = current_group[0] - previous_group[-1]
        if distance < placement.min_hazard_separation_columns:
            raise GamePackageValidationError(
                "segment_placement_violation",
                f"segment {chunk.segment_id} places terrain features {distance} columns "
                f"apart at columns {previous_group[-1]} and {current_group[0]}; the "
                f"placement discipline demands {placement.min_hazard_separation_columns}",
            )

    # The press-window proof: a surface cluster must leave at least the
    # discipline's clear seconds of launch-timing slack over its tallest
    # member. If the silhouette is wanted at full height, the correct fix is
    # a taller jump profile, not a lowered threshold.
    for cluster in clusters:
        if cluster[0].anchor != "surface":
            continue
        declared = [prop_height_rows[hazard.prop_id] for hazard in cluster]
        if any(height is None for height in declared):
            undeclared = ", ".join(
                hazard.prop_id
                for hazard, height in zip(cluster, declared, strict=True)
                if height is None
            )
            raise GamePackageValidationError(
                "segment_hazard_unclearable",
                f"segment {chunk.segment_id} hazard [{undeclared}] declares no height_units; "
                "the press-window proof needs one",
            )
        tallest = max(height for height in declared if height is not None)
        span_columns = cluster[-1].column - cluster[0].column + 1
        window = hazard_press_window_seconds(
            arc,
            speed,
            collision,
            hazard_height_rows=tallest,
            span_columns=span_columns,
        )
        if window < placement.min_hazard_clear_seconds:
            names = ", ".join(hazard.prop_id for hazard in cluster)
            raise GamePackageValidationError(
                "segment_hazard_unclearable",
                f"segment {chunk.segment_id} hazard cluster [{names}] leaves a "
                f"{max(0.0, round(window, 3))}s press window at base speed; the placement "
                f"discipline demands {placement.min_hazard_clear_seconds}s",
            )

    # The overhead proof: the ground proof with the anchor flipped. A ducked
    # avatar plus daylight must fit beneath the clearance, and the clearance
    # must still refuse a standing run, or the placement is dead art.
    for hazard in chunk.hazards:
        if hazard.anchor != "overhead":
            continue
        assert duck is not None  # refused member-wide before any chunk
        clearance = hazard.clearance_rows
        assert clearance is not None  # refused by the hazard model
        ducked_rows = player_height_rows * duck.ducked_height_fraction
        if clearance < ducked_rows + duck.min_overhead_clearance_rows:
            raise GamePackageValidationError(
                "segment_hazard_unclearable",
                f"segment {chunk.segment_id} hangs {hazard.prop_id} with {clearance} rows of "
                f"clearance; a ducked avatar needs "
                f"{ducked_rows + duck.min_overhead_clearance_rows}",
            )
        if clearance > player_height_rows - duck.min_overhead_clearance_rows:
            raise GamePackageValidationError(
                "invalid_runner_track",
                f"segment {chunk.segment_id} hangs {hazard.prop_id} with {clearance} rows of "
                "clearance, which admits a standing run and obstructs nothing",
            )

    # The telegraph: under `pickup_arc_v1`, every jump demand carries its own
    # trail - at least three pickups on the arc the clearance proof flew, so
    # greed walks the player down the safe line on first sight.
    if placement.telegraph == "pickup_arc_v1":

        def pickups_on_arc(launch: int) -> int:
            launch_surface = heights[launch]
            if launch_surface is None:
                return 0
            span = clearable_span_columns(arc, speed, 0)
            assert span is not None
            on_arc = 0
            for pickup in chunk.pickups:
                offset = pickup.column - launch
                if offset < 0 or offset > span:
                    continue
                pickup_height = launch_surface - (pickup.row + 0.5)
                expected = arc_height_rows(arc, speed, offset)
                if abs(pickup_height - expected) <= 0.9:
                    on_arc += 1
            return on_arc

        for (left_column, left_surface), (right_column, right_surface) in pairwise(supported):
            rise = left_surface - right_surface
            gap = right_column - left_column - 1
            if gap <= 0 and rise <= 0:
                continue
            launch = left_column if gap > 0 else right_column - 1
            if pickups_on_arc(launch) < 3:
                raise GamePackageValidationError(
                    "segment_untelegraphed",
                    f"segment {chunk.segment_id} demands a jump at column {launch} but "
                    f"places fewer than 3 pickups on its arc; pickup_arc_v1 demands 3",
                )
        # A surface hazard is a jump demand too, and its trail is the only
        # channel that teaches it on first sight. The launch is wherever the
        # authored arc leaves the ground, one to three columns before the
        # cluster - any of those telling the truth satisfies the telegraph.
        for cluster in clusters:
            if cluster[0].anchor != "surface":
                continue
            candidates = range(max(0, cluster[0].column - 3), cluster[0].column)
            if all(pickups_on_arc(launch) < 3 for launch in candidates):
                raise GamePackageValidationError(
                    "segment_untelegraphed",
                    f"segment {chunk.segment_id} demands a jump over the hazard at column "
                    f"{cluster[0].column} but no launch carries 3 pickups on its arc; "
                    "pickup_arc_v1 demands the trail",
                )


def _load_locked[ContractT](
    data: bytes,
    loader: Callable[[bytes], ContractT],
    code: str,
) -> ContractT:
    try:
        return loader(data)
    except (AuthoredContractLoadError, ValueError) as error:
        raise GamePackageValidationError(code, str(error)) from error


def _validate_cross_contracts(
    *,
    game: PreparedGameContract,
    platformer: PlatformerGenreMember,
    gameplay: GameplayContract,
    ui: GameUi,
    soundtrack: GameSoundtrack,
    maps: tuple[PreparedGameMap, ...],
    player: PlayerContentCatalog,
    mobs: MobContentCatalog,
    npcs: NpcContentCatalog,
    props: PropContentCatalog,
    items: ItemContentCatalog,
    projectiles: ProjectileContentCatalog | None,
    scenario_catalog: ScenarioCatalog,
    scenarios: tuple[ResolvedScenario, ...],
) -> None:
    owned = [
        gameplay.game_id,
        ui.game_id,
        soundtrack.game_id,
        *(entry.game_id for entry in maps),
        player.game_id,
        mobs.game_id,
        npcs.game_id,
        props.game_id,
        items.game_id,
        *(() if projectiles is None else (projectiles.game_id,)),
        scenario_catalog.game_id,
        *(entry.declarations.game_id for entry in scenarios),
    ]
    if any(game_id != game.game_id for game_id in owned):
        raise GamePackageValidationError(
            "cross_game_identity", "every package contract must share game.toml game_id"
        )

    map_ids = {entry.map_id for entry in maps}
    if [entry.map_id for entry in maps] != [entry.map_id for entry in platformer.maps]:
        raise GamePackageValidationError(
            "map_identity_mismatch", "resolved map order and IDs must match game.toml"
        )
    if {entry.map_id for entry in gameplay.map_uses} != map_ids:
        raise GamePackageValidationError(
            "gameplay_map_mismatch", "gameplay map_uses must cover every package map exactly"
        )
    gameplay_map_refs = {
        gameplay.entry_map_id,
        *(entry.map_id for entry in gameplay.spawns),
        *(entry.from_map_id for entry in gameplay.transitions),
        *(entry.to_map_id for entry in gameplay.transitions),
        *(entry.map_id for entry in gameplay.mob_population.maps),
        *(entry.map_id for entry in gameplay.boss_encounters),
        *(entry.map_id for entry in gameplay.npc_placements),
        *(entry.map_id for entry in gameplay.prop_placements),
        *(entry.map_id for entry in gameplay.interactions),
    }
    _assert_subset(gameplay_map_refs, map_ids, "gameplay map_id")
    maps_by_id = {entry.map_id: entry for entry in maps}
    for spawn in gameplay.spawns:
        game_map = maps_by_id[spawn.map_id]
        endpoints = {
            endpoint.anchor: endpoint
            for endpoint in (() if game_map.portal is None else game_map.portal.endpoints)
        }
        endpoint = endpoints.get(spawn.anchor)
        if endpoint is None:
            raise GamePackageValidationError(
                "spawn_portal_mismatch",
                f"spawn {spawn.spawn_id} anchor does not resolve a portal endpoint on "
                f"{spawn.map_id}",
            )
        if abs(endpoint.normalized_x - spawn.normalized_x) > 1e-9:
            raise GamePackageValidationError(
                "spawn_portal_position_mismatch",
                f"spawn {spawn.spawn_id} normalized_x must equal its map-owned portal endpoint",
            )
    for transition in gameplay.transitions:
        game_map = maps_by_id[transition.from_map_id]
        endpoint_anchors = {
            endpoint.anchor
            for endpoint in (() if game_map.portal is None else game_map.portal.endpoints)
        }
        if transition.from_anchor not in endpoint_anchors:
            raise GamePackageValidationError(
                "transition_portal_mismatch",
                f"transition {transition.transition_id} source does not resolve a map portal "
                "endpoint",
            )
    if any(game_map.climbable is not None for game_map in maps) and (
        "climb" not in gameplay.navigation.allowed_movements
    ):
        raise GamePackageValidationError(
            "climbable_movement_mismatch",
            "a map declares climbables but gameplay does not allow climb",
        )
    hostile_map_ids = {
        entry.map_id for entry in gameplay.map_uses if entry.hostile_population_enabled
    }
    population_map_ids = {entry.map_id for entry in gameplay.mob_population.maps}
    if hostile_map_ids != population_map_ids:
        raise GamePackageValidationError(
            "population_map_mismatch",
            "hostile map uses and mob-population maps must match exactly",
        )
    reachable_maps = {gameplay.entry_map_id}
    changed = True
    while changed:
        changed = False
        for transition in gameplay.transitions:
            if (
                transition.from_map_id in reachable_maps
                and transition.to_map_id not in reachable_maps
            ):
                reachable_maps.add(transition.to_map_id)
                changed = True
    if reachable_maps != map_ids:
        raise GamePackageValidationError(
            "unreachable_gameplay_map",
            "every package map must be reachable from entry_map_id through transitions",
        )

    player_ids = {entry.player_id for entry in player.players}
    mob_ids = {entry.mob_id for entry in mobs.mobs}
    npc_ids = {entry.npc_id for entry in npcs.npcs}
    prop_ids = {entry.prop_id for entry in props.props}
    item_ids = {entry.item_id for entry in items.items}
    track_ids = set(soundtrack.track_ids)
    scenario_ids = {entry.declarations.scenario_id for entry in scenarios}

    cast = platformer.cast
    if player_ids != {cast.player_id} or gameplay.player.player_id != cast.player_id:
        raise GamePackageValidationError(
            "player_identity_mismatch", "game, gameplay, and player content must name one player"
        )
    if mob_ids != set(cast.mob_ids):
        raise GamePackageValidationError(
            "mob_identity_mismatch", "game cast mob_ids must equal the mob catalog"
        )
    if npc_ids != set(cast.npc_ids):
        raise GamePackageValidationError(
            "npc_identity_mismatch", "game cast npc_ids must equal the NPC catalog"
        )
    if scenario_ids != set(scenario_catalog.scenario_ids):
        raise GamePackageValidationError(
            "scenario_identity_mismatch", "scenario catalog and resolved scenarios disagree"
        )
    for source, scenario in zip(scenario_catalog.scenarios, scenarios, strict=True):
        if source.scenario_id != scenario.declarations.scenario_id:
            raise GamePackageValidationError(
                "scenario_identity_mismatch", "scenario source ID does not match its contract"
            )

    required_player_states = {"idle", "walk"}
    movement_states = {"jump": "jump", "crouch": "crouch"}
    for movement, state in movement_states.items():
        if movement in gameplay.navigation.allowed_movements:
            required_player_states.add(state)
    if "climb" in gameplay.navigation.allowed_movements:
        # Climb is one movement with one pose per climbable role, so the states a package owes
        # are decided by what its maps actually place rather than by the movement alone. Without
        # this a package could place ropes and ship only the ladder strip, and the runtime would
        # draw a rope climb as a ladder climb with nothing rejecting it.
        required_player_states.update(_placed_climbable_roles(maps))
    if gameplay.combat.enabled:
        required_player_states.update(
            {
                gameplay.combat.basic_action,
                gameplay.combat.secondary_action,
                "hurt",
                "death",
            }
        )
        # Artwork obligation, in the same shape as the states above: the drawn character and the
        # kit they fight with are one fact authored in two files, and until this check existed a
        # package could ship a sword-carrying figure that throws darts with nothing objecting.
        #
        # Both sides are closed names, so this reads no prose and makes no judgement about whether
        # the weapon suits the character - that stays the author's business. It only refuses two
        # declarations that cannot both be true. What the picture actually shows is judged by the
        # actor review, which can see it, exactly as mob facing is.
        for entry in player.players:
            allowed = WEAPON_CLASSES_BY_PLAYER_EQUIPMENT[entry.equipment]
            if gameplay.combat.weapon_class not in allowed:
                raise GamePackageValidationError(
                    "player_equipment_mismatch",
                    f"player {entry.player_id} is drawn as {entry.equipment}, which cannot fight "
                    f"as {gameplay.combat.weapon_class}",
                )
    _assert_subset(
        required_player_states,
        {motion.state for motion in player.players[0].motions},
        "required player motion state",
    )
    required_mob_states = {"idle", "move", "attack", "hurt", "death"}
    for mob in mobs.mobs:
        _assert_subset(
            required_mob_states,
            {motion.state for motion in mob.motions},
            f"required motion state for mob {mob.mob_id}",
        )

    _assert_subset(gameplay.player.starting_item_ids, item_ids, "starting item_id")
    _assert_subset({gameplay.inventory.currency_item_id}, item_ids, "currency item_id")
    # Guarded rather than folded into the calls above: the field is optional, and `_assert_subset`
    # takes an iterable of names, so an unset projectile would be reported as the id `None`.
    #
    # A package that names a round it did not draw has published a world that does not hold
    # together, so the reference is resolved here. The converse is deliberately not an error: a
    # catalog holding something no weapon currently fires is unspent art, not a broken package,
    # and a game with a second weapon class would make that reading wrong.
    projectile_ids = (
        set() if projectiles is None else {entry.projectile_id for entry in projectiles.projectiles}
    )
    if gameplay.combat.projectile_id is not None:
        if projectiles is None:
            raise GamePackageValidationError(
                "unresolved_cross_reference",
                "gameplay names a projectile but the package declares no projectile catalog",
            )
        _assert_subset({gameplay.combat.projectile_id}, projectile_ids, "projectile_id")
    _assert_subset(
        {
            entry.mob_id
            for map_entry in gameplay.mob_population.maps
            for zone in map_entry.zones
            for entry in zone.spawn_table
        },
        mob_ids,
        "population mob_id",
    )
    _assert_subset({entry.mob_id for entry in gameplay.boss_encounters}, mob_ids, "boss mob_id")
    _assert_subset(
        {entry.track_id for entry in gameplay.boss_encounters}, track_ids, "boss track_id"
    )
    _assert_subset(
        {track_id for entry in gameplay.map_uses for track_id in entry.track_ids},
        track_ids,
        "map-use track_id",
    )
    _assert_subset({entry.mob_id for entry in gameplay.loot_rules}, mob_ids, "loot mob_id")
    _assert_subset({entry.item_id for entry in gameplay.loot_rules}, item_ids, "loot item_id")
    _assert_subset({entry.npc_id for entry in gameplay.npc_placements}, npc_ids, "placed npc_id")
    _assert_subset(
        {entry.prop_id for entry in gameplay.prop_placements}, prop_ids, "placed prop_id"
    )
    _assert_subset(
        {entry.actor_id for entry in gameplay.interactions}, npc_ids, "interaction actor_id"
    )
    _assert_subset(
        {entry.scenario_id for entry in gameplay.interactions},
        scenario_ids,
        "interaction scenario_id",
    )
    _assert_subset(
        {entry.completion_item_id for entry in gameplay.quests}, item_ids, "quest item_id"
    )

    quest_ids = {entry.quest_id for entry in gameplay.quests}
    effect_ids = {entry.effect_id for entry in gameplay.effects}
    for effect in gameplay.effects:
        if isinstance(effect, SetQuestStateEffect):
            _assert_subset({effect.quest_id}, quest_ids, "effect quest_id")
        elif isinstance(effect, GrantItemEffect):
            _assert_subset({effect.item_id}, item_ids, "effect item_id")

    npc_by_id = {entry.npc_id: entry for entry in npcs.npcs}
    player_entry = player.players[0]
    actor_ids = player_ids | npc_ids
    # The scenario proved itself finishable on its own. What it cannot know is
    # whether this game can draw the people it names, so that is checked here.
    by_scenario = {entry.declarations.scenario_id: entry for entry in scenarios}
    for scenario in scenarios:
        for member_entry in scenario.declarations.cast:
            _assert_subset({member_entry.actor_id}, actor_ids, "scenario actor_id")
            if member_entry.actor_id == player_entry.player_id:
                expressions = set(player_entry.dialogue_art.expressions)
            else:
                expressions = set(npc_by_id[member_entry.actor_id].dialogue_expressions)
            _assert_subset(set(member_entry.expressions), expressions, "scenario expression")

    # And an interaction binds consequences to endings, so both halves must
    # resolve: an outcome the scenario never reaches would be dead authoring,
    # and an effect gameplay does not declare would fire nothing.
    for interaction in gameplay.interactions:
        bound = by_scenario[interaction.scenario_id]
        outcomes = {ending.outcome_id for ending in bound.declarations.endings}
        _assert_subset(
            {outcome.outcome_id for outcome in interaction.outcomes},
            outcomes,
            "interaction outcome_id",
        )
        for outcome in interaction.outcomes:
            _assert_subset(set(outcome.effect_ids), effect_ids, "interaction effect_id")


def _placed_climbable_roles(maps: Sequence[PreparedGameMap]) -> set[str]:
    """Return the player climb states the maps' placed climbables require.

    Keyed on placements rather than on the declared variant lists: a map may declare a rope
    appearance it never places, and an unplaced appearance owes the player no artwork.
    """

    required: set[str] = set()
    for game_map in maps:
        climbable = game_map.climbable
        if climbable is None:
            continue
        # Which climb states the player needs follows from the roster a map can DRAW, not from
        # where instances stand. Placement is generated terrain and does not exist yet at
        # package resolution; a declared rope variant already means the player must be able to
        # climb a rope, whatever the generator later does with it.
        for role, variants in (("ladder", climbable.ladders), ("rope", climbable.ropes)):
            if variants:
                required.add(PLAYER_CLIMB_STATE_BY_CLIMBABLE_ROLE[role])
    return required


def _assert_subset(values: Iterable[str], allowed: set[str], label: str) -> None:
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise GamePackageValidationError(
            "unresolved_cross_reference", f"{label} values do not resolve: {', '.join(unknown)}"
        )


def _closure_sha256(files: Sequence[ResolvedPackageFile]) -> str:
    """Digest the exact captured closure: every member path, digest, and size."""

    payload = json.dumps(
        [entry.identity() for entry in files], sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(payload)


def _required_file(files: dict[str, bytes], path: str) -> bytes:
    try:
        return files[path]
    except KeyError as error:
        raise GamePackageValidationError(
            "missing_package_file", f"prepared package is missing {path}"
        ) from error


def _validate_file_size(path: str, size: int) -> None:
    if size > _MAX_PACKAGE_FILE_BYTES:
        raise GamePackageValidationError(
            "package_too_large", f"prepared package file exceeds the size limit: {path}"
        )


def _validate_image(data: bytes, path: str) -> None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
    except (OSError, UnidentifiedImageError) as error:
        raise GamePackageValidationError(
            "invalid_reference_image", f"prepared reference image cannot be decoded: {path}"
        ) from error


def _validate_utf8_text(data: bytes, label: str) -> None:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise GamePackageValidationError("invalid_text_source", f"{label} is not UTF-8") from error
    if not text.strip():
        raise GamePackageValidationError("invalid_text_source", f"{label} must not be empty")


def _validate_json_object(data: bytes, label: str) -> None:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GamePackageValidationError(
            "invalid_evidence", f"{label} is not valid JSON"
        ) from error
    if not isinstance(value, dict):
        raise GamePackageValidationError("invalid_evidence", f"{label} must be a JSON object")


def _read_workspace_file(root: Path, relative: str, *, label: str) -> bytes:
    try:
        with open_absolute_directory(root, label="workspace root") as root_fd:
            return read_relative_regular_file(
                root_fd,
                tuple(PurePosixPath(relative).parts),
                label=label,
            )
    except SecurePathError as error:
        raise GamePackageValidationError("invalid_selector", str(error)) from error


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
    "GAME_PACKAGE_VALIDATION_SCHEMA_VERSION",
    "GAME_PACKAGE_SELECTOR_SCHEMA_VERSION",
    "MAIN_GAME_SELECTOR_REF",
    "GamePackageSelector",
    "GamePackageValidationError",
    "ResolvedGamePackage",
    "ResolvedRunnerMember",
    "ResolvedPackageFile",
    "invalid_game_package_report",
    "resolve_game_package",
    "validate_game_package",
]
