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
from pathlib import Path, PurePosixPath
from typing import Literal

from PIL import Image, UnidentifiedImageError
from pydantic import Field, field_validator, model_validator

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
from stage_gen.components.game_content import (
    PLAYER_CLIMB_STATE_BY_CLIMBABLE_ROLE,
    ItemContentCatalog,
    MobContentCatalog,
    NpcContentCatalog,
    PlayerContentCatalog,
    PropContentCatalog,
    load_item_content_bytes,
    load_mob_content_bytes,
    load_npc_content_bytes,
    load_player_content_bytes,
    load_prop_content_bytes,
)
from stage_gen.components.game_contract import (
    PreparedGameContract,
    canonical_prepared_game_contract_json,
    load_prepared_game_contract_bytes,
)
from stage_gen.components.game_map import PreparedGameMap, load_prepared_game_map_bytes
from stage_gen.components.game_sequence import (
    DialogueNode,
    GameSequence,
    GameSequenceCatalog,
    OutcomeNode,
    load_game_sequence_bytes,
    load_game_sequence_catalog_bytes,
)
from stage_gen.components.game_soundtrack import GameSoundtrack, load_game_soundtrack_bytes
from stage_gen.components.game_ui import GameUi, load_game_ui_bytes
from stage_gen.components.gameplay_contract import (
    GameplayContract,
    GrantItemEffect,
    SetQuestStateEffect,
    load_gameplay_contract_bytes,
)
from stage_gen.contracts.artifacts import PersistedContractModel

MAIN_GAME_SELECTOR_REF = "library/games/main.toml"
GAME_PACKAGE_VALIDATION_SCHEMA_VERSION = 4
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
class ResolvedGamePackage:
    """Fully captured and cross-validated prepared input."""

    source_kind: Literal["directory", "zip"]
    package_name: str
    package_sha256: str
    canonical_game_sha256: str
    closure_sha256: str
    game: PreparedGameContract
    gameplay: GameplayContract
    ui: GameUi
    soundtrack: GameSoundtrack
    maps: tuple[PreparedGameMap, ...]
    player: PlayerContentCatalog
    mobs: MobContentCatalog
    npcs: NpcContentCatalog
    props: PropContentCatalog
    items: ItemContentCatalog
    sequence_catalog: GameSequenceCatalog
    sequences: tuple[GameSequence, ...]
    files: tuple[ResolvedPackageFile, ...]

    def file(self, path: str) -> ResolvedPackageFile:
        for entry in self.files:
            if entry.path == path:
                return entry
        raise KeyError(path)

    def identity(self) -> dict[str, object]:
        return {
            "schema_version": GAME_PACKAGE_VALIDATION_SCHEMA_VERSION,
            "kind": "resolved-game-package-v4",
            "game_id": self.game.game_id,
            "revision": self.game.revision,
            "package_sha256": self.package_sha256,
            "canonical_game_sha256": self.canonical_game_sha256,
            "closure_sha256": self.closure_sha256,
            "source_kind": self.source_kind,
            "file_count": len(self.files),
            "map_ids": [entry.map_id for entry in self.maps],
            "player_ids": [entry.player_id for entry in self.player.players],
            "mob_ids": [entry.mob_id for entry in self.mobs.mobs],
            "npc_ids": [entry.npc_id for entry in self.npcs.npcs],
            "prop_ids": [entry.prop_id for entry in self.props.props],
            "item_ids": [entry.item_id for entry in self.items.items],
            "sequence_ids": [entry.sequence_id for entry in self.sequences],
            "track_ids": list(self.soundtrack.track_ids),
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
        "kind": "game-package-validation-v4",
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
        "kind": "game-package-validation-v4",
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
        member(game.gameplay.source),
        load_gameplay_contract_bytes,
        "invalid_gameplay_contract",
    )
    ui = _load_locked(
        member(game.ui.source),
        load_game_ui_bytes,
        "invalid_game_ui_contract",
    )
    soundtrack = _load_locked(
        member(game.soundtrack.source),
        lambda data: load_game_soundtrack_bytes(data, source_suffix=".toml"),
        "invalid_soundtrack_contract",
    )
    maps = tuple(
        _load_locked(
            member(binding.source),
            load_prepared_game_map_bytes,
            "invalid_map_contract",
        )
        for binding in game.maps
    )
    player = _load_locked(
        member(game.content.player.source),
        load_player_content_bytes,
        "invalid_player_content",
    )
    mobs = _load_locked(
        member(game.content.mobs.source),
        load_mob_content_bytes,
        "invalid_mob_content",
    )
    npcs = _load_locked(
        member(game.content.npcs.source),
        load_npc_content_bytes,
        "invalid_npc_content",
    )
    props = _load_locked(
        member(game.content.props.source),
        load_prop_content_bytes,
        "invalid_prop_content",
    )
    items = _load_locked(
        member(game.content.items.source),
        load_item_content_bytes,
        "invalid_item_content",
    )
    sequence_catalog = _load_locked(
        member(game.sequences.index_source),
        load_game_sequence_catalog_bytes,
        "invalid_sequence_catalog",
    )
    sequences = tuple(
        _load_locked(
            member(binding.source),
            load_game_sequence_bytes,
            "invalid_sequence_contract",
        )
        for binding in sequence_catalog.sequences
    )

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
        gameplay=gameplay,
        soundtrack=soundtrack,
        maps=maps,
        player=player,
        mobs=mobs,
        npcs=npcs,
        props=props,
        items=items,
        ui=ui,
        sequence_catalog=sequence_catalog,
        sequences=sequences,
    )

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
        gameplay=gameplay,
        ui=ui,
        soundtrack=soundtrack,
        maps=maps,
        player=player,
        mobs=mobs,
        npcs=npcs,
        props=props,
        items=items,
        sequence_catalog=sequence_catalog,
        sequences=sequences,
        files=resolved_files,
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
    gameplay: GameplayContract,
    ui: GameUi,
    soundtrack: GameSoundtrack,
    maps: tuple[PreparedGameMap, ...],
    player: PlayerContentCatalog,
    mobs: MobContentCatalog,
    npcs: NpcContentCatalog,
    props: PropContentCatalog,
    items: ItemContentCatalog,
    sequence_catalog: GameSequenceCatalog,
    sequences: tuple[GameSequence, ...],
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
        sequence_catalog.game_id,
        *(entry.game_id for entry in sequences),
    ]
    if any(game_id != game.game_id for game_id in owned):
        raise GamePackageValidationError(
            "cross_game_identity", "every package contract must share game.toml game_id"
        )

    map_ids = {entry.map_id for entry in maps}
    if [entry.map_id for entry in maps] != [entry.map_id for entry in game.maps]:
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
    sequence_ids = {entry.sequence_id for entry in sequences}

    if player_ids != {game.cast.player_id} or gameplay.player.player_id != game.cast.player_id:
        raise GamePackageValidationError(
            "player_identity_mismatch", "game, gameplay, and player content must name one player"
        )
    if mob_ids != set(game.cast.mob_ids):
        raise GamePackageValidationError(
            "mob_identity_mismatch", "game cast mob_ids must equal the mob catalog"
        )
    if npc_ids != set(game.cast.npc_ids):
        raise GamePackageValidationError(
            "npc_identity_mismatch", "game cast npc_ids must equal the NPC catalog"
        )
    if sequence_ids != {entry.sequence_id for entry in sequence_catalog.sequences}:
        raise GamePackageValidationError(
            "sequence_identity_mismatch", "sequence catalog and resolved sequences disagree"
        )
    for source, sequence in zip(sequence_catalog.sequences, sequences, strict=True):
        if source.sequence_id != sequence.sequence_id:
            raise GamePackageValidationError(
                "sequence_identity_mismatch", "sequence source ID does not match its contract"
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
        {entry.sequence_id for entry in gameplay.interactions},
        sequence_ids,
        "interaction sequence_id",
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
    for sequence in sequences:
        _assert_subset({sequence.presentation.map_id}, map_ids, "sequence map_id")
        for node in sequence.nodes:
            if isinstance(node, DialogueNode):
                _assert_subset(
                    {
                        node.speaker_id,
                        node.listener_id,
                        node.focus_subject_id,
                        *node.visible_subject_ids,
                    },
                    actor_ids,
                    "sequence actor_id",
                )
                if node.speaker_id == player_entry.player_id:
                    expressions = set(player_entry.dialogue_art.expressions)
                else:
                    expressions = set(npc_by_id[node.speaker_id].dialogue_expressions)
                _assert_subset({node.expression}, expressions, "sequence expression")
            elif isinstance(node, OutcomeNode):
                _assert_subset(node.effect_ids, effect_ids, "sequence effect_id")


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
    "ResolvedPackageFile",
    "invalid_game_package_report",
    "resolve_game_package",
    "validate_game_package",
]
