"""Scrolling-preview versioned manifest and music publication gate."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Literal, cast

from PIL import Image

from gnode import (
    ArtifactProvenance,
    ArtifactRights,
    BinaryArtifact,
    ProvenanceInput,
    SoftwareIdentity,
    build_artifact_provenance,
    is_portable_artifact_reference,
    write_artifact_with_provenance,
)
from stage_gen.components.character_profile import (
    CharacterProfile,
    CharacterProfileBinding,
    canonical_character_profile_json,
)
from stage_gen.components.game_contract import (
    GAME_LIBRARY_RESOLUTION_VERSION,
    GameContract,
    GameContractBinding,
    MobPopulationDirection,
    canonical_game_contract_json,
)
from stage_gen.components.image_repeat import (
    DIRECT_WRAP_ADMISSION_ALGORITHM,
    ENDPOINT_CONDITIONED_REPAIR_ALGORITHM,
    ImageRepeatAssetBinding,
    ImageRepeatManifest,
    ImageRepeatRepairConstruction,
    ImageRepeatRepairLineage,
    VerifiedImageRepeatArtifact,
    canonical_intended_loop_criteria,
    verify_image_repeat_artifact,
)
from stage_gen.config import TransparencyMode
from stage_gen.manifests import to_canonical_manifest_entry
from stage_gen.media import inspect_image
from stage_gen.recipes.scrolling_preview.game import (
    GAME_RESOLUTION_VERSION,
    game_art_direction_prompt,
)
from stage_gen.recipes.scrolling_preview.map_book import (
    CollectedMapBook,
    collect_scrolling_map_book,
)
from stage_gen.recipes.scrolling_preview.mob_states import (
    BASE_MOB_STRIP_STATES,
    MOB_STRIP_STATES,
    is_mob_strip_runtime_role,
    mob_strip_artifact,
    mob_strip_runtime_role,
    mob_strip_stage,
)
from stage_gen.recipes.scrolling_preview.models import WorldSpec
from stage_gen.recipes.scrolling_preview.profile import PROFILE_RESOLUTION_VERSION
from stage_gen.recipes.scrolling_preview.raster_contracts import (
    RESIDENT_STILL_HEIGHT,
    RESIDENT_STILL_WIDTH,
    GridContract,
    contract_for_runtime_role,
    validate_canonical_grid,
)
from stage_gen.recipes.scrolling_preview.resident import village_spec_shape
from stage_gen.recipes.scrolling_preview.scale_reference import (
    evaluate_actor_scale_reference,
    measures_scale_reference,
    parse_actor_scale_reference,
    scale_reference_artifact_name,
    scale_reference_frame,
)
from stage_gen.recipes.scrolling_preview.soundtrack import collect_scrolling_soundtrack
from stage_gen.recipes.scrolling_preview.village import (
    STRIP_RESIDENT_RENDER,
    VillageRenderProfile,
    VillageSpec,
    village_manifest_block,
)
from stage_gen.resources import bundled_music_path

MusicRightsStatus = Literal["unreviewed", "restricted", "redistribution-approved", "unrecorded"]

_NON_CANONICAL_EVIDENCE = frozenset({"gameplay-verification.png"})
_IMAGE_REPEAT_PROVIDER_CANDIDATE_SUFFIX = ".provider-candidate.png"
_ISOLATED_VIEW_FALLBACK_VERSION = "isolated-view-fallback-v1"
_PER_CELL_GENERATION_VERSION = "per-cell-generation-v1"
_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")
# The optional browser adapter builds every scrolling stage over a fixed 200-column terrain grid.
# Population zones are authored in those same half-open column coordinates, so the producer
# validates the consumer limit before publishing rather than clipping a malformed zone at runtime.
_SCROLLING_PREVIEW_STAGE_COLUMN_COUNT = 200
_POST_SPLIT_SCALE_REFERENCE_ROLES = frozenset(
    f"character-{state}" for state in ("idle", "walk", "run", "jump", "crawl")
)


def _lower_snake_case_manifest(value: Any) -> Any:
    """Normalize the current public envelope and all nested producer-owned keys."""

    if isinstance(value, list):
        return [_lower_snake_case_manifest(item) for item in value]
    if not isinstance(value, dict):
        return value
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        snake = _CAMEL_BOUNDARY.sub("_", key).lower()
        if snake in normalized:
            raise ValueError(f"manifest key normalization collision: {key}")
        normalized[snake] = _lower_snake_case_manifest(item)
    return normalized


def _mob_population_hunting_map_ids(
    map_book: CollectedMapBook,
) -> frozenset[str]:
    """Derive population-bearing map identities from current explicit mechanisms."""

    entry_map_id = map_book.manifest.get("entry_map_id")
    raw_maps = map_book.manifest.get("maps")
    if not isinstance(entry_map_id, str) or not isinstance(raw_maps, list):
        raise ValueError("collected map book cannot derive hunting map identities")

    if (
        map_book.manifest.get("schema_version") != 2
        or map_book.manifest.get("kind") != "game-map-book-manifest-v2"
    ):
        raise ValueError("collected map book must use the current schema")

    map_ids: list[str] = []
    explicit_hunting_map_ids: set[str] = set()
    for raw_map in raw_maps:
        map_id = raw_map.get("map_id") if isinstance(raw_map, Mapping) else None
        if not isinstance(map_id, str) or map_id in map_ids:
            raise ValueError("collected map book contains invalid map identities")
        map_ids.append(map_id)
        level_profile = raw_map.get("level_profile")
        mechanisms = level_profile.get("mechanisms") if isinstance(level_profile, Mapping) else None
        encounter_model = (
            mechanisms.get("encounter_model") if isinstance(mechanisms, Mapping) else None
        )
        if encounter_model == "continuous_population":
            explicit_hunting_map_ids.add(map_id)
        elif encounter_model != "none":
            raise ValueError("collected map book contains an invalid encounter_model")
    if entry_map_id not in map_ids:
        raise ValueError("collected map book entry map identity is missing")

    return frozenset(explicit_hunting_map_ids)


def _validate_mob_population_coverage(
    map_book: CollectedMapBook,
    population: MobPopulationDirection | None,
) -> frozenset[str]:
    """Bind every map-book-v2 encounter declaration to exactly one population policy."""

    required = _mob_population_hunting_map_ids(map_book)
    actual = (
        frozenset(population_map.map_id for population_map in population.maps)
        if population is not None
        else frozenset()
    )
    if actual != required:
        missing = ", ".join(sorted(required - actual)) or "none"
        unexpected = ", ".join(sorted(actual - required)) or "none"
        raise ValueError(
            "gameplay.mob_population maps must exactly cover map-book-v2 "
            "continuous_population maps; "
            f"missing: {missing}; unexpected: {unexpected}"
        )
    return required


@dataclass(frozen=True, slots=True)
class _RuntimeRequirement:
    role: str
    path: str
    width: int
    height: int
    alpha: Literal["opaque", "transparent"]
    metadata: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class _CollectedGameContract:
    contract: GameContract
    manifest_binding: dict[str, object]


@dataclass(frozen=True, slots=True)
class _CollectedImageRepeatProviderCandidate:
    name: str
    provenance_name: str
    data: bytes
    provenance_data: bytes
    provenance: ArtifactProvenance


@dataclass(frozen=True, slots=True)
class ManifestWriteResult:
    manifest_path: str
    manifest_provenance_path: str
    music_path: str
    music_provenance_path: str
    music_source: Literal["per-run", "generated-fallback"]
    music_rights_status: MusicRightsStatus
    soundtrack_paths: tuple[str, ...] = ()
    map_book_paths: tuple[str, ...] = ()

    @property
    def artifacts(self) -> tuple[str, ...]:
        paths = [
            self.manifest_path,
            self.manifest_provenance_path,
            self.music_path,
            self.music_provenance_path,
            *self.soundtrack_paths,
            *self.map_book_paths,
        ]
        return tuple(dict.fromkeys(paths))


def _default_fallback() -> Path:
    return bundled_music_path()


async def write_scrolling_preview_manifest(
    *,
    run_dir: str | Path,
    tag: str,
    transparency_mode: TransparencyMode = TransparencyMode.NATIVE,
    fallback_music_path: str | Path | None = None,
    character_profile: bool = False,
    village: bool = False,
    resident_render: VillageRenderProfile | None = None,
    mob_states: frozenset[str] | None = None,
    soundtrack: bool = False,
    map_book: bool = False,
    game_contract: bool = False,
) -> ManifestWriteResult:
    return await asyncio.to_thread(
        _write_scrolling_preview_manifest,
        Path(run_dir),
        tag,
        transparency_mode,
        Path(fallback_music_path) if fallback_music_path is not None else _default_fallback(),
        character_profile,
        village,
        resident_render or STRIP_RESIDENT_RENDER,
        mob_states or frozenset(BASE_MOB_STRIP_STATES),
        soundtrack,
        map_book,
        game_contract,
    )


def _write_scrolling_preview_manifest(
    run_dir: Path,
    tag: str,
    mode: TransparencyMode,
    fallback_music: Path,
    character_profile: bool,
    village: bool,
    resident_render: VillageRenderProfile,
    mob_states: frozenset[str],
    soundtrack: bool,
    map_book: bool,
    game_contract: bool,
) -> ManifestWriteResult:
    run_dir.mkdir(parents=True, exist_ok=True)
    if soundtrack != map_book:
        raise ValueError("scrolling-preview soundtrack and map_book must be declared together")
    if map_book and not game_contract:
        raise ValueError("a declared map book requires a game contract")
    collected_soundtrack = collect_scrolling_soundtrack(run_dir, tag) if soundtrack else None
    if collected_soundtrack is None:
        music_path = run_dir / f"music_{tag}.mp3"
        music = _ensure_run_music_pair(music_path, fallback_music)
        soundtrack_paths: tuple[str, ...] = ()
    else:
        music_path = run_dir / str(collected_soundtrack.default_music["path"])
        music = collected_soundtrack.default_music
        soundtrack_paths = collected_soundtrack.artifact_paths
    collected_map_book = (
        collect_scrolling_map_book(
            run_dir,
            tag,
            soundtrack_manifest=collected_soundtrack.manifest,
        )
        if map_book and collected_soundtrack is not None
        else None
    )
    map_book_paths = collected_map_book.artifact_paths if collected_map_book is not None else ()
    projected_soundtrack = (
        collected_soundtrack.manifest if collected_soundtrack is not None else None
    )

    music_meta = Path(f"{music_path}.meta.json")
    manifest_path = run_dir / f"manifest_{tag}.json"
    names = sorted(path.name for path in run_dir.iterdir())
    active_music_paths = {
        music_path.name,
        music_meta.name,
        *soundtrack_paths,
    }
    active_map_book_paths = set(map_book_paths)
    artifacts = [
        name
        for name in names
        if not name.startswith(".")
        and name not in _NON_CANONICAL_EVIDENCE
        and name not in {manifest_path.name, f"{manifest_path.name}.meta.json"}
        and ".raw.png" not in name
        and not _is_inactive_music_artifact(name, active_music_paths)
        and not _is_inactive_map_book_artifact(name, active_map_book_paths)
    ]
    image_repeat_records = _collect_image_repeat(run_dir, set(names))
    image_repeat_evidence = {
        cast(str, cast(dict[str, object], record["repeat_unit"])["path"])
        for record in image_repeat_records
    }
    for record in image_repeat_records:
        construction = cast(dict[str, object], record["construction"])
        if construction.get("mode") != "repaired":
            continue
        candidate = cast(dict[str, object], construction["provider_candidate"])
        image_repeat_evidence.add(cast(str, candidate["path"]))
    canonical = _collect_canonical_images(run_dir, set(names), mode, image_repeat_evidence)
    # The village is read once and drives both halves of its publication: a run either declares
    # a valid `village` block and demands the sheets that block describes, or declares neither.
    # Optionality belongs to the authored opt-in. Once declared, a missing or invalid bible is a
    # failed run rather than permission to publish a silently village-less result.
    village_spec = _read_village_spec(run_dir, tag, directed=game_contract) if village else None
    runtime_assets, world_spec_binding = (
        _collect_runtime_assets(
            run_dir, tag, set(names), canonical, None, resident_render, mob_states
        )
        if village_spec is None
        else _collect_runtime_assets(
            run_dir, tag, set(names), canonical, village_spec, resident_render, mob_states
        )
    )
    profile_binding = (
        _collect_character_profile_binding(run_dir, tag, set(names)) if character_profile else None
    )
    collected_game = _collect_game_contract(run_dir, tag, set(names)) if game_contract else None
    population_map_ids: frozenset[str] | None = None
    if collected_map_book is not None:
        gameplay_direction = (
            collected_game.contract.gameplay if collected_game is not None else None
        )
        population_map_ids = _validate_mob_population_coverage(
            collected_map_book,
            gameplay_direction.mob_population if gameplay_direction is not None else None,
        )
    gameplay_projection: dict[str, object] | None = None
    mob_population_map_count = 0
    combat_text_enabled: bool | None = None
    projected_game_binding: dict[str, object] | None = None
    if collected_game is not None:
        projected_game_binding = dict(collected_game.manifest_binding)
        if collected_game.contract.schema_version != 3:
            raise ValueError("resolved game contract must use schema version 3")
        projected_game_binding["contract_schema_version"] = 3
        gameplay = collected_game.contract.gameplay
        if gameplay is not None:
            gameplay_projection = {}
            combat_text = collected_game.contract.combat_text_manifest()
            if combat_text is not None:
                gameplay_projection["combat_text"] = combat_text
                combat_text_enabled = gameplay.combat_text.enabled if gameplay.combat_text else None
            if gameplay.mob_population is not None:
                try:
                    world_spec = WorldSpec.model_validate_json(
                        (run_dir / f"world_spec_{tag}.json").read_bytes()
                    )
                except (OSError, ValueError) as error:
                    raise ValueError("runtime world spec is invalid for game projection") from error
                allowed_map_ids = (
                    population_map_ids
                    if population_map_ids is not None
                    else _mob_population_hunting_map_ids(collected_map_book)
                    if collected_map_book is not None
                    else None
                )
                mob_population = gameplay.mob_population.manifest_projection(
                    mob_count=len(world_spec.mobs),
                    allowed_map_ids=allowed_map_ids,
                    stage_column_count=_SCROLLING_PREVIEW_STAGE_COLUMN_COUNT,
                )
                gameplay_projection["mob_population"] = mob_population
                mob_population_map_count = len(gameplay.mob_population.maps)
    manifest: dict[str, Any] = {
        "schema_version": 7,
        "recipe": "scrolling-preview",
        "tag": tag,
        "transparencyMode": mode,
        "artifacts": artifacts,
        "canonicalArtifacts": canonical,
        "worldSpec": world_spec_binding,
        "runtimeAssets": runtime_assets,
        **({"character_profile": profile_binding} if profile_binding is not None else {}),
        **({"game_contract": projected_game_binding} if projected_game_binding is not None else {}),
        **({"gameplay": gameplay_projection} if gameplay_projection is not None else {}),
        # Already `lower_snake_case` at the source, so it survives manifest normalization.
        **(
            {"village": village_manifest_block(village_spec, resident_render)}
            if village_spec is not None
            else {}
        ),
        "image_repeat": {
            "enabled": bool(image_repeat_records),
            "status": "available" if image_repeat_records else "deferred",
            "artifacts": image_repeat_records,
        },
        **({"soundtrack": projected_soundtrack} if projected_soundtrack is not None else {}),
        **({"map_book": collected_map_book.manifest} if collected_map_book is not None else {}),
    }
    manifest = _lower_snake_case_manifest(manifest)
    payload = f"{json.dumps(manifest, indent=2, ensure_ascii=False)}\n".encode()
    provenance_path = _write_local_artifact_pair(
        manifest_path,
        payload,
        media_type="application/json",
        prompt="assemble scrolling-preview run manifest",
        refs=list(
            dict.fromkeys(
                [
                    music_path.name,
                    music_meta.name,
                    *soundtrack_paths,
                    *map_book_paths,
                    *(
                        [
                            str(profile_binding["path"]),
                            str(profile_binding["provenance_path"]),
                        ]
                        if profile_binding is not None
                        else []
                    ),
                    *(
                        [
                            str(collected_game.manifest_binding["path"]),
                            str(collected_game.manifest_binding["provenance_path"]),
                        ]
                        if collected_game is not None
                        else []
                    ),
                    # The published `village` block is copied out of this artifact, so the bible
                    # is a genuine input to the manifest's bytes and not merely another file.
                    *([f"village_spec_{tag}.json"] if village_spec is not None else []),
                ]
            )
        ),
        params={
            "recipe": "scrolling-preview",
            "tag": tag,
            "transparency_mode": mode,
            "music_source": music["source"],
            "music_rights_status": music["rights_status"],
            "fallback_policy": (
                "disabled when a game soundtrack is declared"
                if collected_soundtrack is not None
                else "copy only when per-run music is absent and publication-approved"
            ),
            **(
                {
                    "soundtrack_declared": True,
                    "soundtrack_track_count": len(
                        cast(list[object], collected_soundtrack.manifest["tracks"])
                    ),
                }
                if collected_soundtrack is not None
                else {}
            ),
            **(
                {
                    "map_book_declared": True,
                    "map_count": len(cast(list[object], collected_map_book.manifest["maps"])),
                }
                if collected_map_book is not None
                else {}
            ),
            **(
                {
                    "character_profile_source_sha256": profile_binding["source_sha256"],
                    "character_profile_canonical_sha256": profile_binding["canonical_sha256"],
                }
                if profile_binding is not None
                else {}
            ),
            **(
                {
                    "game_contract_source_sha256": collected_game.manifest_binding["source_sha256"],
                    "game_contract_canonical_sha256": collected_game.manifest_binding[
                        "canonical_sha256"
                    ],
                    "mob_population_maps": mob_population_map_count,
                    **(
                        {"combat_text_enabled": combat_text_enabled}
                        if combat_text_enabled is not None
                        else {}
                    ),
                }
                if collected_game is not None
                else {}
            ),
        },
        validation={
            "music_artifact_present": True,
            "music_provenance_present": True,
            "music_rights_status": music["rights_status"],
            **({"soundtrack_complete": True} if collected_soundtrack is not None else {}),
            **({"map_book_complete": True} if collected_map_book is not None else {}),
            "retained_raw_excluded_from_top_level": all(
                ".raw.png" not in path for path in artifacts
            ),
            "canonical_transparency_entries": sum(
                1 for entry in canonical if "transparency" in entry
            ),
            "runtime_assets_complete": True,
            "runtime_asset_roles": len(runtime_assets),
            "image_repeat_default_off": not image_repeat_records,
            "image_repeat_artifacts": len(image_repeat_records),
            **({"character_profile_binding_verified": True} if profile_binding is not None else {}),
            **(
                {
                    "game_contract_binding_verified": True,
                    **(
                        {"mob_population_projection_verified": True}
                        if mob_population_map_count
                        else {}
                    ),
                    **(
                        {"combat_text_projection_verified": True}
                        if combat_text_enabled is not None
                        else {}
                    ),
                }
                if collected_game is not None
                else {}
            ),
        },
    )
    return ManifestWriteResult(
        manifest_path=str(manifest_path),
        manifest_provenance_path=str(provenance_path),
        music_path=str(music_path),
        music_provenance_path=str(music_meta),
        music_source=music["source"],
        music_rights_status=music["rights_status"],
        soundtrack_paths=tuple(str(run_dir / path) for path in soundtrack_paths),
        map_book_paths=tuple(str(run_dir / path) for path in map_book_paths),
    )


def _is_inactive_music_artifact(name: str, active: set[str]) -> bool:
    if name in active:
        return False
    return (
        name.startswith("music_") and (name.endswith(".mp3") or name.endswith(".mp3.meta.json"))
    ) or (
        name.startswith("soundtrack_")
        and (name.endswith(".json") or name.endswith(".json.meta.json"))
    )


def _is_inactive_map_book_artifact(name: str, active: set[str]) -> bool:
    if name in active:
        return False
    return name.startswith("map_book_") and (
        name.endswith(".json") or name.endswith(".json.meta.json")
    )


def _collect_canonical_images(
    run_dir: Path,
    names: set[str],
    mode: TransparencyMode,
    excluded: set[str] | None = None,
) -> list[dict[str, Any]]:
    excluded_names = excluded or set()
    results: list[dict[str, Any]] = []
    canonical_names = sorted(
        name
        for name in names
        if name.endswith(".png")
        and not name.startswith(".")
        and not name.endswith(".raw.png")
        and not name.endswith(_IMAGE_REPEAT_PROVIDER_CANDIDATE_SUFFIX)
        and name not in _NON_CANONICAL_EVIDENCE
        and name not in excluded_names
    )
    for canonical_name in canonical_names:
        provenance_name = f"{canonical_name}.meta.json"
        if provenance_name not in names:
            raise ValueError(f"canonical artifact provenance is missing for {canonical_name}")
        sidecar = _read_sidecar(run_dir / provenance_name, canonical_name)
        _verify_artifact_binding(run_dir / canonical_name, sidecar, canonical_name)
        raw_name = re.sub(r"\.png$", ".raw.png", canonical_name, flags=re.IGNORECASE)
        if raw_name in names:
            raw_provenance = f"{raw_name}.meta.json"
            if raw_provenance not in names:
                raise ValueError(f"transparent artifact pair is incomplete for {canonical_name}")
            raw_sidecar = _read_sidecar(run_dir / raw_provenance, raw_name)
            _verify_artifact_binding(run_dir / raw_name, raw_sidecar, raw_name)
            transparency = _generated_transparency(
                run_dir,
                sidecar,
                raw_sidecar,
                mode,
                canonical_name,
                raw_name,
                provenance_name,
                raw_provenance,
            )
            results.append(
                to_canonical_manifest_entry(
                    {
                        "path": raw_name,
                        "provenancePath": raw_provenance,
                        "transparency": transparency,
                    }
                )
            )
            continue
        params = sidecar["params"]
        transparency = params.get("transparency")
        if isinstance(transparency, dict):
            results.append(
                {
                    "path": canonical_name,
                    "provenancePath": provenance_name,
                    "transparency": _derived_transparency(
                        run_dir,
                        names,
                        sidecar,
                        transparency,
                        mode,
                        canonical_name,
                        provenance_name,
                    ),
                }
            )
            continue
        metadata = params.get("metadata")
        opaque = isinstance(metadata, dict) and (
            metadata.get("stage") == "concept" or metadata.get("opaque") is True
        )
        if not opaque:
            raise ValueError(
                f"artifact {canonical_name} has neither transparency derivation "
                "nor opaque provenance"
            )
        results.append({"path": canonical_name, "provenancePath": provenance_name})
    return results


def _collect_character_profile_binding(
    run_dir: Path,
    tag: str,
    names: set[str],
) -> dict[str, object]:
    artifact_name = f"character_profile_{tag}.json"
    provenance_name = f"{artifact_name}.meta.json"
    if artifact_name not in names or provenance_name not in names:
        raise ValueError("resolved character profile artifact pair is missing")
    artifact_path = run_dir / artifact_name
    sidecar = _read_sidecar(run_dir / provenance_name, artifact_name)
    _verify_artifact_binding(artifact_path, sidecar, artifact_name)
    try:
        artifact_bytes = artifact_path.read_bytes()
        profile = CharacterProfile.model_validate_json(artifact_bytes)
    except (OSError, ValueError) as error:
        raise ValueError("resolved character profile artifact is invalid") from error
    if canonical_character_profile_json(profile) != artifact_bytes:
        raise ValueError("resolved character profile artifact is not canonical JSON")
    params = sidecar.get("params")
    identity = params.get("character_profile") if isinstance(params, dict) else None
    inputs = sidecar.get("inputs")
    if not isinstance(identity, dict) or not isinstance(inputs, list) or len(inputs) != 1:
        raise ValueError("resolved character profile provenance is invalid")
    try:
        binding = CharacterProfileBinding.model_validate(identity.get("binding"))
    except ValueError as error:
        raise ValueError("resolved character profile binding is invalid") from error
    canonical_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
    source_input = inputs[0]
    identity_keys = {
        "schema_version",
        "kind",
        "resolution_version",
        "binding",
        "profile_id",
        "revision",
        "source_sha256",
        "canonical_sha256",
        "canonical_bytes",
        "rights_status",
        "artifact_ref",
        "artifact_sha256",
        "artifact_bytes",
    }
    expected_source_media_type = (
        "application/toml" if binding.ref.endswith(".toml") else "application/json"
    )
    if (
        set(identity) != identity_keys
        or identity.get("schema_version") != 1
        or identity.get("kind") != "resolved-character-profile-v1"
        or identity.get("resolution_version") != PROFILE_RESOLUTION_VERSION
        or identity.get("profile_id") != profile.profile_id
        or identity.get("revision") != profile.revision
        or identity.get("source_sha256") != binding.source_sha256
        or identity.get("canonical_sha256") != canonical_sha256
        or identity.get("canonical_bytes") != len(artifact_bytes)
        or identity.get("artifact_ref") != f"sha256:{canonical_sha256}"
        or identity.get("artifact_sha256") != canonical_sha256
        or identity.get("artifact_bytes") != len(artifact_bytes)
        or identity.get("rights_status") != profile.rights.status
        or not isinstance(source_input, dict)
        or source_input
        != {
            "ref": binding.ref,
            "sha256": binding.source_sha256,
            "source": "content",
            "bytes": source_input.get("bytes"),
            "media_type": expected_source_media_type,
        }
        or isinstance(source_input.get("bytes"), bool)
        or not isinstance(source_input.get("bytes"), int)
        or source_input["bytes"] <= 0
    ):
        raise ValueError("resolved character profile lineage mismatch")
    return {
        **identity,
        "binding": binding.model_dump(mode="json"),
        "path": artifact_name,
        "provenance_path": provenance_name,
    }


def _collect_game_contract(
    run_dir: Path,
    tag: str,
    names: set[str],
) -> _CollectedGameContract:
    """Verify a canonical game artifact before projecting any declared mechanisms."""

    artifact_name = f"game_{tag}.json"
    provenance_name = f"{artifact_name}.meta.json"
    if artifact_name not in names or provenance_name not in names:
        raise ValueError("resolved game contract artifact pair is missing")
    artifact_path = run_dir / artifact_name
    sidecar = _read_sidecar(run_dir / provenance_name, artifact_name)
    _verify_artifact_binding(artifact_path, sidecar, artifact_name)
    try:
        artifact_bytes = artifact_path.read_bytes()
        contract = GameContract.model_validate_json(artifact_bytes)
    except (OSError, ValueError) as error:
        raise ValueError("resolved game contract artifact is invalid") from error
    if canonical_game_contract_json(contract) != artifact_bytes:
        raise ValueError("resolved game contract artifact is not canonical JSON")

    params = sidecar.get("params")
    identity = params.get("game_contract") if isinstance(params, dict) else None
    inputs = sidecar.get("inputs")
    if (
        not isinstance(params, dict)
        or params.get("stage") != "game-resolve"
        or not isinstance(identity, dict)
        or not isinstance(inputs, list)
        or len(inputs) != 1
    ):
        raise ValueError("resolved game contract provenance is invalid")
    try:
        binding = GameContractBinding.model_validate(identity.get("binding"))
    except ValueError as error:
        raise ValueError("resolved game contract binding is invalid") from error

    canonical_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
    source_input = inputs[0]
    identity_keys = {
        "schema_version",
        "kind",
        "resolution_version",
        "binding",
        "game_id",
        "revision",
        "projection",
        "source_sha256",
        "canonical_sha256",
        "canonical_bytes",
        "vocabulary_sha256",
        "rights_status",
        "recipe_resolution_version",
        "art_direction_sha256",
        "artifact_ref",
        "artifact_sha256",
        "artifact_bytes",
    }
    expected_source_media_type = (
        "application/toml" if binding.ref.endswith(".toml") else "application/json"
    )
    expected_art_direction_sha256 = hashlib.sha256(
        game_art_direction_prompt(contract).encode("utf-8")
    ).hexdigest()
    if (
        set(identity) != identity_keys
        or identity.get("schema_version") != 1
        or identity.get("kind") != "resolved-game-contract-v1"
        or identity.get("resolution_version") != GAME_LIBRARY_RESOLUTION_VERSION
        or identity.get("game_id") != contract.game_id
        or identity.get("revision") != contract.revision
        or identity.get("projection") != contract.camera.projection
        or identity.get("source_sha256") != binding.source_sha256
        or identity.get("canonical_sha256") != canonical_sha256
        or identity.get("canonical_bytes") != len(artifact_bytes)
        or identity.get("artifact_ref") != f"sha256:{canonical_sha256}"
        or identity.get("artifact_sha256") != canonical_sha256
        or identity.get("artifact_bytes") != len(artifact_bytes)
        or identity.get("rights_status") != contract.rights.status
        or not re.fullmatch(r"[a-f0-9]{64}", str(identity.get("vocabulary_sha256", "")))
        or identity.get("recipe_resolution_version") != GAME_RESOLUTION_VERSION
        or identity.get("art_direction_sha256") != expected_art_direction_sha256
        or sidecar.get("provider") != "local"
        or sidecar.get("model") != GAME_RESOLUTION_VERSION
        or sidecar.get("refs") != [binding.ref]
        or not isinstance(source_input, dict)
        or source_input
        != {
            "ref": binding.ref,
            "sha256": binding.source_sha256,
            "source": "content",
            "bytes": source_input.get("bytes"),
            "media_type": expected_source_media_type,
        }
        or isinstance(source_input.get("bytes"), bool)
        or not isinstance(source_input.get("bytes"), int)
        or source_input["bytes"] <= 0
    ):
        raise ValueError("resolved game contract lineage mismatch")
    return _CollectedGameContract(
        contract=contract,
        manifest_binding={
            **identity,
            "binding": binding.model_dump(mode="json"),
            "path": artifact_name,
            "provenance_path": provenance_name,
        },
    )


def _collect_runtime_assets(
    run_dir: Path,
    tag: str,
    names: set[str],
    canonical: list[dict[str, Any]],
    village: VillageSpec | None = None,
    resident_render: VillageRenderProfile = STRIP_RESIDENT_RENDER,
    mob_states: frozenset[str] = frozenset(BASE_MOB_STRIP_STATES),
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    world_name = f"world_spec_{tag}.json"
    world_meta = f"{world_name}.meta.json"
    if world_name not in names or world_meta not in names:
        raise ValueError("runtime world spec artifact pair is missing")
    world_sidecar = _read_sidecar(run_dir / world_meta, world_name)
    _verify_artifact_binding(run_dir / world_name, world_sidecar, world_name)
    try:
        world_spec = WorldSpec.model_validate_json((run_dir / world_name).read_bytes())
    except (OSError, ValueError) as error:
        raise ValueError("runtime world spec is invalid") from error

    entries = {entry.get("path"): entry for entry in canonical}
    results: list[dict[str, Any]] = []
    for requirement in _runtime_requirements(tag, world_spec, village, resident_render, mob_states):
        entry = entries.get(requirement.path)
        if not isinstance(entry, dict):
            raise ValueError(
                f"runtime-required role {requirement.role} is missing: {requirement.path}"
            )
        if requirement.alpha == "transparent" and not isinstance(entry.get("transparency"), dict):
            raise ValueError(f"runtime-required role {requirement.role} lacks transparency lineage")
        geometry = _validate_runtime_image(run_dir / requirement.path, requirement)
        provenance = entry.get("provenancePath")
        if not isinstance(provenance, str):
            raise ValueError(f"runtime-required role {requirement.role} lacks provenance binding")
        scale_reference_stage = _scale_reference_owner_stage(requirement)
        scale_reference = (
            _read_required_scale_reference(run_dir, requirement, scale_reference_stage)
            if scale_reference_stage is not None
            else None
        )
        results.append(
            {
                "id": requirement.role,
                "runtimeSlot": requirement.role,
                "path": requirement.path,
                "provenancePath": provenance,
                "alphaExpectation": requirement.alpha,
                "layout": geometry.pop("layout"),
                "geometryValidation": geometry,
                **({"scale_reference": scale_reference} if scale_reference is not None else {}),
                **({"binding": requirement.metadata} if requirement.metadata else {}),
            }
        )
    return results, {"path": world_name, "provenancePath": world_meta}


def _scale_reference_owner_stage(requirement: _RuntimeRequirement) -> str | None:
    """Return the stage that owns this runtime asset's mandatory measurement.

    Most generated sheets use the same identifier at generation and runtime. Mob runtime roles
    retain their established `mob-<slot>-<state>` spelling while their generating stages are
    `mob-<state>-<slot>`, so that one case is mapped back before asking the shared ownership
    predicate. The five player master states are the deliberate exception to that predicate:
    `post-split` measures the final re-sliced runtime bytes, after the generated sheets have been
    composed. They are nevertheless part of the current runtime measurement closure.
    """

    if requirement.role in _POST_SPLIT_SCALE_REFERENCE_ROLES:
        return requirement.role
    if measures_scale_reference(requirement.role):
        return requirement.role
    if not is_mob_strip_runtime_role(requirement.role):
        return None
    metadata = requirement.metadata
    slot = metadata.get("slot") if isinstance(metadata, dict) else None
    state = metadata.get("state") if isinstance(metadata, dict) else None
    if (
        isinstance(slot, bool)
        or not isinstance(slot, int)
        or slot < 0
        or not isinstance(state, str)
    ):
        raise ValueError(f"runtime-required role {requirement.role} has invalid binding")
    stage = mob_strip_stage(state, slot)
    if not measures_scale_reference(stage):
        raise ValueError(f"runtime-required role {requirement.role} has no measurement owner")
    return stage


def _read_required_scale_reference(
    run_dir: Path,
    requirement: _RuntimeRequirement,
    stage: str,
) -> dict[str, Any]:
    """Read one current, provenance-bound measurement or reject the runtime asset.

    A required measurement is part of manifest-v7 validity, not an optional hint. Both bindings
    matter: provenance binds the JSON bytes to their sidecar, while `measured_sha256` binds the
    reading to the exact PNG bytes. The payload is then re-evaluated against the runtime role's
    current cell geometry so a stale frame index, cell size, extent, or partial object cannot be
    published as though it were a current measurement.
    """

    reference_name = scale_reference_artifact_name(Path(requirement.path).name)
    reference_path = run_dir / reference_name
    sidecar_path = Path(f"{reference_path}.meta.json")
    try:
        reference_data = reference_path.read_bytes()
    except OSError as error:
        raise ValueError(
            f"runtime-required role {requirement.role} scale reference is missing"
        ) from error
    try:
        provenance = ArtifactProvenance.model_validate_json(sidecar_path.read_bytes())
    except (OSError, ValueError) as error:
        raise ValueError(
            f"runtime-required role {requirement.role} scale reference provenance is invalid"
        ) from error
    artifact = provenance.artifact
    if (
        artifact is None
        or artifact.media_type != "application/json"
        or artifact.sha256 != hashlib.sha256(reference_data).hexdigest()
        or artifact.bytes != len(reference_data)
    ):
        raise ValueError(
            f"runtime-required role {requirement.role} scale reference binding mismatch"
        )
    try:
        measured_sha256 = hashlib.sha256((run_dir / requirement.path).read_bytes()).hexdigest()
    except OSError as error:
        raise ValueError(f"runtime-required role {requirement.role} is missing") from error
    metadata = provenance.params.get("metadata")
    if (
        not isinstance(metadata, dict)
        or metadata.get("stage") != f"{stage}-scale-reference"
        or metadata.get("measured_sha256") != measured_sha256
    ):
        raise ValueError(f"runtime-required role {requirement.role} scale reference is stale")
    try:
        payload = json.loads(reference_data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(
            f"runtime-required role {requirement.role} scale reference is invalid"
        ) from error
    return _validate_scale_reference_payload(payload, requirement, stage)


def _validate_scale_reference_payload(
    payload: object,
    requirement: _RuntimeRequirement,
    stage: str,
) -> dict[str, Any]:
    """Validate the exact evaluated scale-reference object published by the current producer."""

    contract = contract_for_runtime_role(requirement.role)
    if contract is None:
        raise ValueError(f"runtime-required role {requirement.role} has no scale grid contract")
    cell_width, cell_height = contract.cell_size(requirement.width, requirement.height)
    if not isinstance(payload, dict):
        raise ValueError(f"runtime-required role {requirement.role} scale reference is invalid")
    try:
        parsed = parse_actor_scale_reference(
            {
                "part": payload["part"],
                "top": payload["top_fraction"],
                "bottom": payload["bottom_fraction"],
                "left": payload["left_fraction"],
                "right": payload["right_fraction"],
                "confident": payload["confident"],
                "evidence": payload["evidence"],
            }
        )
        expected = {
            **evaluate_actor_scale_reference(
                parsed,
                frame_width=cell_width,
                frame_height=cell_height,
            ),
            "frame_index": scale_reference_frame(stage),
            "cell_width": cell_width,
            "cell_height": cell_height,
        }
    except (KeyError, ValueError) as error:
        raise ValueError(
            f"runtime-required role {requirement.role} scale reference is invalid"
        ) from error
    if payload != expected:
        raise ValueError(f"runtime-required role {requirement.role} scale reference is invalid")
    return cast(dict[str, Any], payload)


def _read_village_spec(
    run_dir: Path,
    tag: str,
    *,
    directed: bool = False,
) -> VillageSpec:
    """Read the declared village bible under the exact schema the run authored.

    The caller owns optionality: this function is invoked only when the run declares a village.
    Once declared, absence or invalidity must fail closed so the manifest cannot silently omit the
    requested hub or publish resident assets under a mismatched roster contract.
    """

    spec_path = run_dir / f"village_spec_{tag}.json"
    try:
        raw = spec_path.read_bytes()
    except OSError as error:
        raise ValueError("declared village specification is missing or unreadable") from error
    model, _schema_name = village_spec_shape(directed=directed)
    try:
        return model.model_validate_json(raw)
    except ValueError as error:
        raise ValueError("declared village specification is invalid") from error


def _runtime_requirements(
    tag: str,
    world: WorldSpec,
    village: VillageSpec | None = None,
    resident_render: VillageRenderProfile = STRIP_RESIDENT_RENDER,
    mob_states: frozenset[str] = frozenset(BASE_MOB_STRIP_STATES),
) -> tuple[_RuntimeRequirement, ...]:
    requirements = [
        _RuntimeRequirement("concept", f"concept_{tag}.png", 1536, 1024, "opaque"),
        _RuntimeRequirement(
            "character-concept",
            f"character_concept_{tag}.png",
            2400,
            800,
            "transparent",
        ),
        _RuntimeRequirement("ladder", f"ladder_{tag}.png", 256, 1024, "transparent"),
        _RuntimeRequirement(
            "character-climb",
            f"character_{tag}-fromcombined_climb.png",
            256,
            128,
            "transparent",
        ),
        *[
            _RuntimeRequirement(
                f"character-{state}",
                f"character_{tag}-fromcombined_{state}.png",
                2400,
                688,
                "transparent",
                {"state": state},
            )
            for state in ("idle", "walk", "run", "jump", "crawl")
        ],
        _RuntimeRequirement(
            "character-attack", f"character_{tag}_attack.png", 2400, 800, "transparent"
        ),
        _RuntimeRequirement("items", f"items_{tag}.png", 2400, 800, "transparent"),
        _RuntimeRequirement("inventory", f"inventory_{tag}.png", 1536, 1024, "transparent"),
        _RuntimeRequirement("portal", f"portal_{tag}.png", 2048, 1024, "transparent"),
    ]
    requirements.extend(
        _RuntimeRequirement(
            f"layer-{layer.id}",
            f"layer_{tag}_{layer.id}.png",
            2400,
            800,
            "opaque" if layer.opaque else "transparent",
            {
                "zIndex": layer.z_index,
                "parallax": layer.parallax,
                "opaque": layer.opaque,
            },
        )
        for layer in world.layers
    )
    for index, _mob in enumerate(world.mobs):
        requirements.extend(
            (
                _RuntimeRequirement(
                    f"mob-concept-{index}",
                    f"mob_concept_{tag}_{index}.png",
                    2400,
                    800,
                    "transparent",
                    {"slot": index},
                ),
            )
        )
        # One requirement per strip the run actually drew. Enumerated from `mob_states` rather
        # than written out, so a state added there is demanded and published here without a
        # second edit - and states the run did not draw are not demanded, because this check is
        # fail-closed and would reject an undirected run for lacking an attack sheet it was
        # never asked to produce.
        requirements.extend(
            _RuntimeRequirement(
                mob_strip_runtime_role(index, entry.state),
                mob_strip_artifact(tag, index, entry.state),
                2400,
                800,
                "transparent",
                {"slot": index, "state": entry.state},
            )
            for entry in MOB_STRIP_STATES
            if entry.state in mob_states
        )
    requirements.extend(
        _RuntimeRequirement(
            f"obstacles-{index}",
            f"obstacles_{tag}_{index}.png",
            2400,
            800,
            "transparent",
            {"slot": index},
        )
        for index, _sheet in enumerate(world.obstacles)
    )
    if village is not None:
        # Appended through the ordinary requirement list rather than published by a village-only
        # path, so the nine village sheets are held to every check the hunting sheets are held
        # to: exact dimensions, a nontrivial alpha channel, the cell geometry
        # `contract_for_runtime_role` declares for their role, a provenance sidecar bound to the
        # bytes, and the head-matched scale reference that is the entire reason NPCs render at
        # the player's apparent size. That last one needs no wiring here: the reference is looked
        # up from the artifact stem, so `npc_<tag>_<i>_idle.png` finds
        # `npc_<tag>_<i>_idle.scale-reference.json` exactly as a mob strip finds its own.
        #
        # The drawn resident's role, filename, and canvas all come from the run's render
        # profile, which is the only thing about the village publication that a game contract
        # changes here. A still is `village-npc-<i>-still` at 800x1200; a strip is
        # `village-npc-<i>-idle` at 2400x800. Both are looked up through the same
        # `contract_for_runtime_role`, so each is held to its own cell geometry.
        state = resident_render.state
        width, height = (
            (RESIDENT_STILL_WIDTH, RESIDENT_STILL_HEIGHT)
            if resident_render.animation == "still"
            else (2400, 800)
        )
        for index, _npc in enumerate(village.npcs):
            requirements.extend(
                (
                    _RuntimeRequirement(
                        f"village-npc-concept-{index}",
                        f"npc_concept_{tag}_{index}.png",
                        2400,
                        800,
                        "transparent",
                        {"slot": index},
                    ),
                    _RuntimeRequirement(
                        f"village-npc-{index}-{state}",
                        f"npc_{tag}_{index}_{state}.png",
                        width,
                        height,
                        "transparent",
                        {"slot": index, "state": state},
                    ),
                )
            )
        # One sheet for the whole settlement, so it carries no slot: the fixture cells are
        # addressed positionally out of the sheet the way obstacle cells are, and the roster that
        # names them lives in the bible, not in a runtime binding.
        requirements.append(
            _RuntimeRequirement(
                "village-fixtures",
                f"village_fixtures_{tag}.png",
                2400,
                800,
                "transparent",
            )
        )
    return tuple(requirements)


def _validate_runtime_image(path: Path, requirement: _RuntimeRequirement) -> dict[str, object]:
    try:
        data = path.read_bytes()
        facts = inspect_image(data, expected_media_type="image/png")
    except (OSError, ValueError) as error:
        raise ValueError(f"runtime-required role {requirement.role} is not a valid PNG") from error
    if (facts.width, facts.height) != (requirement.width, requirement.height):
        raise ValueError(
            f"runtime-required role {requirement.role} must be "
            f"{requirement.width}x{requirement.height}"
        )
    with Image.open(BytesIO(data)) as opened:
        alpha = opened.convert("RGBA").getchannel("A")
        alpha_extrema = alpha.getextrema()
    if requirement.alpha == "transparent":
        if alpha_extrema is None or alpha_extrema[0] == alpha_extrema[1]:
            raise ValueError(f"runtime-required role {requirement.role} needs nontrivial alpha")
    elif alpha_extrema not in {None, (255, 255)}:
        raise ValueError(f"runtime-required role {requirement.role} must be opaque")

    contract = contract_for_runtime_role(requirement.role)
    if contract is None:
        layout: dict[str, object] = {
            "topology": "single",
            "rows": 1,
            "columns": 1,
            "cellWidth": facts.width,
            "cellHeight": facts.height,
            "gutter": 0,
        }
        grid_facts: dict[str, object] = {}
    else:
        try:
            grid_facts = validate_canonical_grid(data, contract)
        except ValueError as error:
            raise ValueError(
                f"runtime-required role {requirement.role} has invalid cell geometry: {error}"
            ) from error
        layout = _runtime_layout(contract, facts.width, facts.height)
    return {
        "layout": layout,
        "exactDimensions": True,
        "alphaContract": True,
        **grid_facts,
    }


def _runtime_layout(contract: GridContract, width: int, height: int) -> dict[str, object]:
    cell_width, cell_height = contract.cell_size(width, height)
    return {
        "topology": contract.topology,
        "rows": contract.rows,
        "columns": contract.columns,
        "cellWidth": cell_width,
        "cellHeight": cell_height,
        "gutter": contract.gutter,
    }


def _collect_image_repeat(run_dir: Path, names: set[str]) -> list[dict[str, Any]]:
    """Collect only decoded, lineage-bound repeat units proven on one axis."""

    records: list[dict[str, Any]] = []
    for manifest_name in sorted(
        name for name in names if name.endswith(".repeat.json") and not name.startswith(".")
    ):
        manifest_meta = f"{manifest_name}.meta.json"
        if manifest_meta not in names:
            raise ValueError(f"image-repeat manifest provenance is missing for {manifest_name}")
        manifest_path = run_dir / manifest_name
        manifest_provenance = _read_image_repeat_provenance(
            run_dir / manifest_meta,
            manifest_name,
        )
        manifest_data = _verify_image_repeat_artifact_binding(
            manifest_path,
            manifest_provenance,
            manifest_name,
            "application/json",
        )
        try:
            raw_record = json.loads(manifest_data)
            record = ImageRepeatManifest.model_validate_json(manifest_data)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            raise ValueError(f"image-repeat manifest is invalid for {manifest_name}") from None
        if isinstance(record.construction, ImageRepeatRepairConstruction) and not (
            isinstance(raw_record, dict)
            and _raw_image_repeat_v4_construction_matches(raw_record.get("construction"))
        ):
            raise ValueError(f"image-repeat manifest is invalid for {manifest_name}")

        source_name = _run_relative_path(run_dir, record.source.path)
        source_meta = _run_relative_path(run_dir, record.source.provenance_path)
        repeat_name = _run_relative_path(run_dir, record.repeat_unit.path)
        repeat_meta = _run_relative_path(run_dir, record.repeat_unit.provenance_path)
        if source_meta != f"{source_name}.meta.json" or repeat_meta != f"{repeat_name}.meta.json":
            raise ValueError(f"image-repeat provenance adjacency mismatch for {manifest_name}")
        if any(name not in names for name in (source_name, source_meta, repeat_name, repeat_meta)):
            raise ValueError(f"image-repeat artifact pair is incomplete for {manifest_name}")

        source_provenance = _read_image_repeat_provenance(run_dir / source_meta, source_name)
        repeat_provenance = _read_image_repeat_provenance(run_dir / repeat_meta, repeat_name)
        provider_candidate = (
            _collect_image_repeat_provider_candidate(
                run_dir,
                names,
                record.construction,
                manifest_name,
                reserved_names={
                    source_name,
                    source_meta,
                    repeat_name,
                    repeat_meta,
                    manifest_name,
                    manifest_meta,
                },
            )
            if isinstance(record.construction, ImageRepeatRepairConstruction)
            else None
        )
        source_data = _verify_image_repeat_artifact_binding(
            run_dir / source_name,
            source_provenance,
            source_name,
            "image/png",
        )
        repeat_data = _verify_image_repeat_artifact_binding(
            run_dir / repeat_name,
            repeat_provenance,
            repeat_name,
            "image/png",
        )
        _verify_image_repeat_binding(record.source, source_provenance, source_data, manifest_name)
        _verify_image_repeat_binding(
            record.repeat_unit,
            repeat_provenance,
            repeat_data,
            manifest_name,
        )
        try:
            verified = verify_image_repeat_artifact(
                source_data,
                repeat_data,
                record,
                provider_candidate_data=(
                    provider_candidate.data if provider_candidate is not None else None
                ),
            )
        except ValueError:
            raise ValueError(
                f"image-repeat media derivation is invalid for {manifest_name}"
            ) from None
        criteria = canonical_intended_loop_criteria(
            axis=record.axis,
            intended_behavior=record.intent.intended_behavior,
            alpha_policy=record.intent.alpha_policy,
            coverage_policy=record.intent.coverage_policy,
            validation_policy=record.validation.policy,
        )
        semantic_bytes = json.dumps(
            record.validation.intended_loop.model_dump(mode="json", exclude_none=True),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
        _verify_image_repeat_review(
            run_dir,
            names,
            record,
            repeat_data,
            verified.preview_png,
            manifest_name,
        )
        _verify_image_repeat_rights(
            source_provenance,
            repeat_provenance,
            manifest_provenance,
            provider_candidate.provenance if provider_candidate is not None else None,
            record,
            manifest_name,
        )
        if provider_candidate is not None:
            _verify_image_repeat_provider_candidate_provenance(
                provider_candidate,
                repeat_provenance,
                record,
                verified,
                manifest_name,
            )
        _verify_image_repeat_output_provenance(
            repeat_provenance,
            record,
            source_name,
            source_data,
            repeat_data,
            criteria,
            verified.preview_png,
            semantic_bytes,
            verified,
            provider_candidate,
            manifest_name,
        )
        _verify_image_repeat_manifest_provenance(
            manifest_provenance,
            record,
            source_name,
            source_data,
            repeat_name,
            repeat_data,
            criteria,
            verified.preview_png,
            semantic_bytes,
            provider_candidate,
            manifest_name,
        )
        records.append(record.model_dump(mode="json", exclude_none=True))
    return records


def _raw_image_repeat_v4_construction_matches(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        value.get("algorithm") == ENDPOINT_CONDITIONED_REPAIR_ALGORITHM
        and value.get("alpha_reconstruction_algorithm") == "source-endpoint-alpha-smoothstep-v1"
        and value.get("alpha_topology_reconstructed") is True
        and value.get("provider_rgb_interior_preserved") is True
        and value.get("deterministically_reconstructible") is True
    )


def _collect_image_repeat_provider_candidate(
    run_dir: Path,
    names: set[str],
    construction: ImageRepeatRepairConstruction,
    manifest_name: str,
    *,
    reserved_names: set[str],
) -> _CollectedImageRepeatProviderCandidate:
    binding = construction.provider_candidate
    candidate_name = _run_relative_path(run_dir, binding.path)
    candidate_meta = _run_relative_path(run_dir, binding.provenance_path)
    if (
        candidate_meta != f"{candidate_name}.meta.json"
        or candidate_name in reserved_names
        or candidate_meta in reserved_names
        or candidate_name not in names
        or candidate_meta not in names
    ):
        raise ValueError(f"image-repeat provider-candidate pair is incomplete for {manifest_name}")
    provenance_path = run_dir / candidate_meta
    try:
        provenance_data = provenance_path.read_bytes()
    except OSError:
        raise ValueError(
            f"image-repeat provider-candidate provenance is missing for {manifest_name}"
        ) from None
    try:
        provenance = ArtifactProvenance.model_validate_json(provenance_data)
    except ValueError:
        raise ValueError(f"image-repeat provenance is invalid for {candidate_name}") from None
    data = _verify_image_repeat_artifact_binding(
        run_dir / candidate_name,
        provenance,
        candidate_name,
        "image/png",
    )
    _verify_image_repeat_binding(binding, provenance, data, manifest_name)
    return _CollectedImageRepeatProviderCandidate(
        name=candidate_name,
        provenance_name=candidate_meta,
        data=data,
        provenance_data=provenance_data,
        provenance=provenance,
    )


def _read_image_repeat_provenance(path: Path, artifact_name: str) -> ArtifactProvenance:
    try:
        return ArtifactProvenance.model_validate_json(path.read_bytes())
    except (OSError, ValueError):
        raise ValueError(f"image-repeat provenance is invalid for {artifact_name}") from None


def _verify_image_repeat_artifact_binding(
    path: Path,
    provenance: ArtifactProvenance,
    artifact_name: str,
    media_type: str,
) -> bytes:
    try:
        data = path.read_bytes()
    except OSError:
        raise ValueError(f"image-repeat artifact is missing for {artifact_name}") from None
    artifact = provenance.artifact
    if (
        artifact is None
        or artifact.media_type != media_type
        or artifact.sha256 != hashlib.sha256(data).hexdigest()
        or artifact.bytes != len(data)
    ):
        raise ValueError(f"image-repeat artifact binding mismatch for {artifact_name}")
    return data


def _verify_image_repeat_binding(
    binding: ImageRepeatAssetBinding,
    provenance: ArtifactProvenance,
    data: bytes,
    manifest_name: str,
) -> None:
    artifact = provenance.artifact
    try:
        facts = inspect_image(data, expected_media_type="image/png")
    except ValueError:
        raise ValueError(f"image-repeat artifact binding mismatch for {manifest_name}") from None
    if (
        artifact is None
        or binding.sha256 != hashlib.sha256(data).hexdigest()
        or binding.bytes != len(data)
        or binding.sha256 != artifact.sha256
        or binding.bytes != artifact.bytes
        or (binding.width, binding.height) != (facts.width, facts.height)
    ):
        raise ValueError(f"image-repeat artifact binding mismatch for {manifest_name}")


def _verify_image_repeat_review(
    run_dir: Path,
    names: set[str],
    record: ImageRepeatManifest,
    repeat_data: bytes,
    preview: bytes,
    manifest_name: str,
) -> None:
    semantic = record.validation.intended_loop
    binding = semantic.review_artifact
    if binding is None:
        raise ValueError(f"image-repeat review evidence is missing for {manifest_name}")
    review_name = _run_relative_path(run_dir, binding.path)
    review_meta = _run_relative_path(run_dir, binding.provenance_path)
    if (
        review_meta != f"{review_name}.meta.json"
        or review_name not in names
        or review_meta not in names
    ):
        raise ValueError(f"image-repeat review pair is incomplete for {manifest_name}")
    review_data = (run_dir / review_name).read_bytes()
    review_provenance_data = (run_dir / review_meta).read_bytes()
    if (
        hashlib.sha256(review_data).hexdigest() != binding.sha256
        or len(review_data) != binding.bytes
        or hashlib.sha256(review_provenance_data).hexdigest() != binding.provenance_sha256
    ):
        raise ValueError(f"image-repeat review binding mismatch for {manifest_name}")
    review_provenance = _read_image_repeat_provenance(run_dir / review_meta, review_name)
    _verify_image_repeat_artifact_binding(
        run_dir / review_name,
        review_provenance,
        review_name,
        "application/json",
    )
    expected_review = {
        "verdict": semantic.verdict,
        "confidence": semantic.confidence,
        "failure_codes": semantic.failure_codes,
        "evidence": semantic.evidence,
    }
    try:
        actual_review = json.loads(review_data)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError(f"image-repeat review JSON is invalid for {manifest_name}") from None
    validation = review_provenance.validation
    if (
        actual_review != expected_review
        or review_provenance.component.name != "@stage-gen/structured-generation"
        or review_provenance.provider != semantic.reviewer_provider
        or review_provenance.model != semantic.reviewer_model
        or review_provenance.attempts < 1
        or validation.get("preview_sha256") != hashlib.sha256(preview).hexdigest()
        or validation.get("judged_sha256") != hashlib.sha256(repeat_data).hexdigest()
        or validation.get("criteria_sha256") != semantic.criteria_sha256
        or validation.get("semantic_verdict") != "accept"
        or not _content_input_matches(
            review_provenance,
            f"sha256:{hashlib.sha256(preview).hexdigest()}",
            preview,
            "image/png",
        )
    ):
        raise ValueError(f"image-repeat review provenance mismatch for {manifest_name}")


def _verify_image_repeat_rights(
    source: ArtifactProvenance,
    repeat: ArtifactProvenance,
    manifest: ArtifactProvenance,
    provider_candidate: ArtifactProvenance | None,
    record: ImageRepeatManifest,
    manifest_name: str,
) -> None:
    output_rights = repeat.rights
    if (
        output_rights is None
        or manifest.rights != output_rights
        or (provider_candidate is not None and provider_candidate.rights != output_rights)
        or output_rights.status != record.rights_status
        or (
            source.rights is not None
            and source.rights.status == "restricted"
            and output_rights.status != "restricted"
        )
        or (
            output_rights.status == "redistribution-approved"
            and (source.rights is None or source.rights.status != "redistribution-approved")
        )
    ):
        raise ValueError(f"image-repeat rights lineage mismatch for {manifest_name}")


def _verify_image_repeat_provider_candidate_provenance(
    candidate: _CollectedImageRepeatProviderCandidate,
    repeat_provenance: ArtifactProvenance,
    record: ImageRepeatManifest,
    verified: VerifiedImageRepeatArtifact,
    manifest_name: str,
) -> None:
    construction = record.construction
    prepared = verified.repair_conditioning
    response = candidate.provenance.response
    if not isinstance(construction, ImageRepeatRepairConstruction) or prepared is None:
        raise ValueError(f"image-repeat provider-candidate provenance mismatch for {manifest_name}")
    expected_params = {
        "algorithm": ENDPOINT_CONDITIONED_REPAIR_ALGORITHM,
        "axis": record.axis,
        "context_span_px": construction.context_span_px,
        "repair_span_px": construction.repair_span_px,
        "mask_semantics": construction.mask_semantics,
        "alpha_reconstruction_algorithm": construction.alpha_reconstruction_algorithm,
        "provider_responsibility": "rgb_appearance",
        "component_responsibility": "alpha_topology_and_endpoint_continuity",
        "metadata": repeat_provenance.params.get("metadata"),
    }
    expected_validation = {
        "provider_dimensions": [
            prepared.conditioning_width,
            prepared.conditioning_height,
        ],
        "provider_media_type": "image/png",
        "exact_provider_candidate_preserved": True,
        "provider_candidate_role": "rgb_appearance_input",
    }
    provenance = candidate.provenance
    if (
        provenance.component.name != "@stage-gen/image-repeat"
        or provenance.component.version != "0.0.0"
        or provenance.provider != construction.provider
        or provenance.model != construction.model
        or provenance.attempts != construction.attempts
        or provenance.rights != repeat_provenance.rights
        or provenance.prompt != repeat_provenance.prompt
        or provenance.params != expected_params
        or provenance.validation != expected_validation
        or not isinstance(response, dict)
        or response.get("media_type") != "image/png"
        or isinstance(response.get("bytes"), bool)
        or response.get("bytes") != len(candidate.data)
        or not _content_input_matches(
            provenance,
            f"sha256:{hashlib.sha256(prepared.conditioning_png).hexdigest()}",
            prepared.conditioning_png,
            "image/png",
        )
        or not _content_input_matches(
            provenance,
            f"sha256:{hashlib.sha256(prepared.mask_png).hexdigest()}",
            prepared.mask_png,
            "image/png",
        )
    ):
        raise ValueError(f"image-repeat provider-candidate provenance mismatch for {manifest_name}")


def _verify_image_repeat_output_provenance(
    provenance: ArtifactProvenance,
    record: ImageRepeatManifest,
    source_name: str,
    source_data: bytes,
    repeat_data: bytes,
    criteria: bytes,
    preview: bytes,
    semantic: bytes,
    verified: VerifiedImageRepeatArtifact,
    provider_candidate: _CollectedImageRepeatProviderCandidate | None,
    manifest_name: str,
) -> None:
    params = provenance.params
    validation = provenance.validation
    construction = record.construction
    expected_provider = "local"
    expected_model = "direct-wrap-admission-v2"
    expected_attempts = 1
    if isinstance(construction, ImageRepeatRepairConstruction):
        expected_provider = construction.provider
        expected_model = construction.model
        expected_attempts = construction.attempts
    if (
        provenance.component.name != "@stage-gen/image-repeat"
        or provenance.component.version != "0.0.0"
        or provenance.provider != expected_provider
        or provenance.model != expected_model
        or provenance.attempts != expected_attempts
        or provenance.rights is None
        or provenance.rights.status != record.rights_status
        or params.get("axis") != record.axis
        or params.get("decision") != record.decision
        or params.get("criteria_sha256") != record.intent.criteria_sha256
        or params.get("lineage") != record.lineage.model_dump(mode="json")
        or not _image_repeat_branch_provenance_matches(
            provenance,
            record,
            verified,
            provider_candidate,
        )
        or validation.get("source_provenance_bound") is not True
        or validation.get("source_pixels_immutable") is not True
        or validation.get("declared_axis_only") is not True
        or validation.get("other_axis_status") != "not_evaluated"
        or validation.get("deterministic")
        != record.validation.deterministic.model_dump(mode="json")
        or validation.get("intended_loop")
        != record.validation.intended_loop.model_dump(mode="json", exclude_none=True)
        or validation.get("three_repeat_preview_sha256") != hashlib.sha256(preview).hexdigest()
        or not _content_input_matches(provenance, source_name, source_data, "image/png")
        or not _content_input_matches(
            provenance,
            f"sha256:{hashlib.sha256(preview).hexdigest()}",
            preview,
            "image/png",
        )
        or not _content_input_matches(
            provenance,
            f"sha256:{hashlib.sha256(criteria).hexdigest()}",
            criteria,
            "application/json",
        )
        or not _content_input_matches(
            provenance,
            f"sha256:{hashlib.sha256(semantic).hexdigest()}",
            semantic,
            "application/json",
        )
        or hashlib.sha256(repeat_data).hexdigest() != record.repeat_unit.sha256
    ):
        raise ValueError(f"image-repeat output provenance mismatch for {manifest_name}")


def _image_repeat_branch_provenance_matches(
    provenance: ArtifactProvenance,
    record: ImageRepeatManifest,
    verified: VerifiedImageRepeatArtifact,
    provider_candidate: _CollectedImageRepeatProviderCandidate | None,
) -> bool:
    params = provenance.params
    validation = provenance.validation
    construction = record.construction
    if not isinstance(construction, ImageRepeatRepairConstruction):
        return (
            params.get("algorithm") == DIRECT_WRAP_ADMISSION_ALGORITHM
            and validation.get("source_bytes_preserved") is True
            and provenance.response is None
            and verified.repair_png is None
            and verified.repair_conditioning is None
            and verified.raw_repair_png is None
            and verified.alpha_reconstructed_repair_png is None
            and verified.provider_interior_png is None
            and verified.endpoint_anchor_span_px is None
            and verified.alpha_reconstructed_changed_pixels is None
            and verified.anchored_repair_changed_pixels is None
            and provider_candidate is None
        )

    prepared = verified.repair_conditioning
    repair_png = verified.repair_png
    raw_repair_png = verified.raw_repair_png
    alpha_reconstructed_repair_png = verified.alpha_reconstructed_repair_png
    provider_interior_png = verified.provider_interior_png
    lineage = record.lineage
    changed_pixels = validation.get("provider_context_changed_pixels")
    alpha_reconstructed_changed_pixels = validation.get("alpha_reconstructed_changed_pixels")
    anchored_changed_pixels = validation.get("anchored_repair_changed_pixels")
    response = provenance.response
    if (
        prepared is None
        or repair_png is None
        or raw_repair_png is None
        or alpha_reconstructed_repair_png is None
        or provider_interior_png is None
        or verified.endpoint_anchor_span_px is None
        or verified.alpha_reconstructed_changed_pixels is None
        or verified.anchored_repair_changed_pixels is None
        or provider_candidate is None
        or not isinstance(lineage, ImageRepeatRepairLineage)
    ):
        return False
    maximum_context_pixels = construction.context_span_px * record.cross_axis_extent_px * 2
    if (
        params.get("algorithm") != ENDPOINT_CONDITIONED_REPAIR_ALGORITHM
        or params.get("context_span_px") != construction.context_span_px
        or params.get("repair_span_px") != construction.repair_span_px
        or params.get("mask_semantics") != construction.mask_semantics
        or params.get("endpoint_anchor_algorithm") != construction.endpoint_anchor_algorithm
        or params.get("endpoint_anchor_span_px") != construction.endpoint_anchor_span_px
        or params.get("endpoint_anchors_reimposed") is not True
        or params.get("alpha_reconstruction_algorithm")
        != construction.alpha_reconstruction_algorithm
        or params.get("alpha_topology_reconstructed") is not True
        or params.get("provider_rgb_interior_preserved") is not True
        or params.get("deterministically_reconstructible") is not True
        or params.get("provider_candidate")
        != construction.provider_candidate.model_dump(mode="json")
        or validation.get("provider_dimensions")
        != [prepared.conditioning_width, prepared.conditioning_height]
        or validation.get("provider_media_type") != "image/png"
        or validation.get("immutable_regions_reimposed") is not True
        or validation.get("repair_cropped_without_context") is not True
        or validation.get("endpoint_anchors_reimposed") is not True
        or validation.get("alpha_topology_reconstructed") is not True
        or validation.get("provider_rgb_interior_preserved") is not True
        or validation.get("deterministically_reconstructible") is not True
        or verified.endpoint_anchor_span_px != construction.endpoint_anchor_span_px
        or alpha_reconstructed_changed_pixels != verified.alpha_reconstructed_changed_pixels
        or anchored_changed_pixels != verified.anchored_repair_changed_pixels
        or isinstance(changed_pixels, bool)
        or not isinstance(changed_pixels, int)
        or not 0 <= changed_pixels <= maximum_context_pixels
        or isinstance(anchored_changed_pixels, bool)
        or not isinstance(anchored_changed_pixels, int)
        or not 0
        <= anchored_changed_pixels
        <= construction.endpoint_anchor_span_px * record.cross_axis_extent_px * 2
        or isinstance(alpha_reconstructed_changed_pixels, bool)
        or not isinstance(alpha_reconstructed_changed_pixels, int)
        or not 0
        <= alpha_reconstructed_changed_pixels
        <= construction.repair_span_px * record.cross_axis_extent_px
        or hashlib.sha256(provider_candidate.data).hexdigest() != lineage.provider_candidate_sha256
        or hashlib.sha256(raw_repair_png).hexdigest() != lineage.raw_repair_sha256
        or hashlib.sha256(provider_interior_png).hexdigest() != lineage.provider_interior_sha256
        or hashlib.sha256(alpha_reconstructed_repair_png).hexdigest()
        != lineage.alpha_reconstructed_repair_sha256
        or not isinstance(response, dict)
        or response.get("media_type") != "image/png"
        or isinstance(response.get("bytes"), bool)
        or not isinstance(response.get("bytes"), int)
        or response.get("bytes") != len(provider_candidate.data)
    ):
        return False
    return (
        all(
            _content_input_matches(
                provenance,
                f"sha256:{hashlib.sha256(data).hexdigest()}",
                data,
                "image/png",
            )
            for data in (
                prepared.head_context_png,
                prepared.tail_context_png,
                prepared.conditioning_png,
                prepared.mask_png,
            )
        )
        and _content_input_matches(
            provenance,
            provider_candidate.name,
            provider_candidate.data,
            "image/png",
        )
        and _content_input_matches(
            provenance,
            provider_candidate.provenance_name,
            provider_candidate.provenance_data,
            "application/json",
        )
    )


def _verify_image_repeat_manifest_provenance(
    provenance: ArtifactProvenance,
    record: ImageRepeatManifest,
    source_name: str,
    source_data: bytes,
    repeat_name: str,
    repeat_data: bytes,
    criteria: bytes,
    preview: bytes,
    semantic: bytes,
    provider_candidate: _CollectedImageRepeatProviderCandidate | None,
    manifest_name: str,
) -> None:
    params = provenance.params
    validation = provenance.validation
    is_repaired = isinstance(record.construction, ImageRepeatRepairConstruction)
    expected_validation = {
        "typed_contract": True,
        "lower_snake_case": True,
        "repeat_unit_binding": True,
        "lineage_binding": True,
        "deterministic_gate": "pass",
        "semantic_gate": "accept",
        "semantic_review_independent": True,
        "other_axis_status": "not_evaluated",
        **(
            {
                "provider_candidate_binding": True,
                "repair_reconstruction_binding": True,
            }
            if is_repaired
            else {}
        ),
    }
    if (
        provenance.component.name != "@stage-gen/image-repeat"
        or provenance.component.version != "0.0.0"
        or provenance.provider != "local"
        or provenance.model != "image-repeat-manifest-v2"
        or provenance.attempts != 1
        or provenance.rights is None
        or provenance.rights.status != record.rights_status
        or params.get("schema_version") != 2
        or params.get("axis") != record.axis
        or params.get("decision") != record.decision
        or params.get("period_px") != record.period_px
        or params.get("lineage") != record.lineage.model_dump(mode="json")
        or params.get("construction") != record.construction.model_dump(mode="json")
        or validation != expected_validation
        or is_repaired != (provider_candidate is not None)
        or not _content_input_matches(provenance, source_name, source_data, "image/png")
        or not _content_input_matches(provenance, repeat_name, repeat_data, "image/png")
        or not _content_input_matches(
            provenance,
            f"sha256:{hashlib.sha256(criteria).hexdigest()}",
            criteria,
            "application/json",
        )
        or not _content_input_matches(
            provenance,
            f"sha256:{hashlib.sha256(preview).hexdigest()}",
            preview,
            "image/png",
        )
        or not _content_input_matches(
            provenance,
            f"sha256:{hashlib.sha256(semantic).hexdigest()}",
            semantic,
            "application/json",
        )
        or (
            provider_candidate is not None
            and not _content_input_matches(
                provenance,
                provider_candidate.name,
                provider_candidate.data,
                "image/png",
            )
        )
        or (
            provider_candidate is not None
            and not _content_input_matches(
                provenance,
                provider_candidate.provenance_name,
                provider_candidate.provenance_data,
                "application/json",
            )
        )
    ):
        raise ValueError(f"image-repeat manifest provenance mismatch for {manifest_name}")


def _content_input_matches(
    provenance: ArtifactProvenance,
    ref: str,
    data: bytes,
    media_type: str,
) -> bool:
    digest = hashlib.sha256(data).hexdigest()
    return any(
        item.ref == ref
        and item.sha256 == digest
        and item.bytes == len(data)
        and item.media_type == media_type
        and item.source == "content"
        for item in provenance.inputs
    )


def _read_sidecar(path: Path, artifact_name: str) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"canonical provenance is invalid for {artifact_name}") from error
    if (
        not isinstance(parsed, dict)
        or parsed.get("schema_version") != 2
        or not isinstance(parsed.get("artifact"), dict)
        or not isinstance(parsed["artifact"].get("sha256"), str)
        or not isinstance(parsed.get("params"), dict)
    ):
        raise ValueError(f"canonical provenance is invalid for {artifact_name}")
    return parsed


def _generated_transparency(
    run_dir: Path,
    sidecar: dict[str, Any],
    raw_sidecar: dict[str, Any],
    mode: TransparencyMode,
    canonical: str,
    raw: str,
    canonical_meta: str,
    raw_meta: str,
) -> dict[str, Any]:
    transparency = sidecar["params"].get("transparency")
    if not isinstance(transparency, dict) or transparency.get("mode") != str(mode):
        raise ValueError(f"canonical transparency mode mismatch for {canonical}")
    raw_params = raw_sidecar["params"]
    raw_metadata = raw_params.get("metadata")
    if not isinstance(raw_metadata, dict) or raw_metadata.get("transparency_mode") != str(mode):
        raise ValueError(f"retained raw transparency mode mismatch for {canonical}")
    retained = transparency.get("retained_raw_path")
    if not isinstance(retained, str) or _run_relative_path(run_dir, retained) != raw:
        raise ValueError(f"retained raw lineage mismatch for {canonical}")
    raw_digest = _artifact_sha256(raw_sidecar, raw)
    canonical_digest = _artifact_sha256(sidecar, canonical)
    if transparency.get("raw_sha256") != raw_digest:
        raise ValueError(f"retained raw digest mismatch for {canonical}")
    if transparency.get("output_sha256") != canonical_digest:
        raise ValueError(f"canonical output digest mismatch for {canonical}")
    _validate_alpha_contract(sidecar, canonical)
    raw_validation = raw_sidecar.get("validation")
    if (
        not isinstance(raw_validation, dict)
        or raw_validation.get("exact_contract_dimensions") is not True
    ):
        raise ValueError(f"retained raw dimensions are unvalidated for {canonical}")
    validation = sidecar["validation"]
    if raw_validation.get("output_width") != validation.get("output_width") or raw_validation.get(
        "output_height"
    ) != validation.get("output_height"):
        raise ValueError(f"retained raw dimensions mismatch for {canonical}")
    tool = sidecar.get("tool")
    processor = transparency.get("processor")
    processor_name = (
        processor
        if isinstance(processor, str)
        else processor.get("kind", "")
        if isinstance(processor, dict)
        else ""
    )
    derivation: dict[str, Any] = {"kind": _generated_derivation_kind(processor_name, canonical)}
    derivation["sourceSha256"] = raw_digest
    derivation["outputSha256"] = canonical_digest
    if (
        isinstance(tool, dict)
        and isinstance(tool.get("name"), str)
        and isinstance(tool.get("version"), str)
    ):
        derivation["tool"] = {"name": tool["name"], "version": tool["version"]}
    elif isinstance(processor, dict) and isinstance(processor.get("kind"), str):
        derivation["tool"] = {"name": processor["kind"], "version": "1"}
    return {
        "mode": mode,
        "canonicalPath": canonical,
        "retainedRawPath": raw,
        "canonicalProvenancePath": canonical_meta,
        "rawProvenancePath": raw_meta,
        "lineage": {
            "kind": "generated",
            "sourcePaths": [raw],
            "sourceProvenancePaths": [raw_meta],
        },
        "derivation": derivation,
    }


def _generated_derivation_kind(processor: str, canonical: str) -> str:
    normalized = processor.strip().lower()
    if _PER_CELL_GENERATION_VERSION in normalized:
        return _PER_CELL_GENERATION_VERSION
    if _ISOLATED_VIEW_FALLBACK_VERSION in normalized:
        return _ISOLATED_VIEW_FALLBACK_VERSION
    if "grid-cell-normalization" in normalized:
        if "native-alpha" in normalized:
            return "native-alpha+grid-cell-normalization"
        if "chroma" in normalized:
            return "chroma-key+grid-cell-normalization"
        if "background-removal" in normalized:
            return "ai-background-removal+grid-cell-normalization"
        return "grid-cell-normalization"
    if "chroma" in normalized or "local-key" in normalized:
        return "chroma-key"
    if "background-removal" in normalized:
        return "ai-background-removal"
    if "native-alpha" in normalized:
        return "native-alpha"
    raise ValueError(f"unknown generated transparency processor for {canonical}")


def _derived_transparency(
    run_dir: Path,
    names: set[str],
    sidecar: dict[str, Any],
    transparency: dict[str, Any],
    mode: TransparencyMode,
    canonical: str,
    canonical_meta: str,
) -> dict[str, Any]:
    if transparency.get("mode") != str(mode):
        raise ValueError(f"canonical transparency mode mismatch for {canonical}")
    source_path = transparency.get("source_path")
    source_paths_value = transparency.get("source_paths")
    if isinstance(source_path, str):
        source_values = [source_path]
    elif isinstance(source_paths_value, dict):
        source_values = [value for value in source_paths_value.values() if isinstance(value, str)]
    else:
        source_values = []
    if not source_values:
        raise ValueError(f"derived transparency lineage is missing for {canonical}")
    source_names = [_run_relative_path(run_dir, source) for source in source_values]
    source_meta = [f"{source}.meta.json" for source in source_names]
    for source, meta in zip(source_names, source_meta, strict=True):
        if source not in names or meta not in names:
            raise ValueError(f"derived transparency source is missing for {canonical}")
        source_sidecar = _read_sidecar(run_dir / meta, source)
        _verify_artifact_binding(run_dir / source, source_sidecar, source)
        source_transparency = source_sidecar["params"].get("transparency")
        if not isinstance(source_transparency, dict) or source_transparency.get("mode") != str(
            mode
        ):
            raise ValueError(f"derived transparency source mode mismatch for {canonical}")
    _validate_derived_hashes(sidecar, transparency, source_names, source_meta, run_dir, canonical)
    _validate_alpha_contract(sidecar, canonical)
    processor = transparency.get("processor")
    processor_name = (
        processor
        if isinstance(processor, str)
        else processor.get("kind", "")
        if isinstance(processor, dict)
        else ""
    )
    if "slice" in processor_name:
        kind = "png-slice"
    elif "composite" in processor_name:
        kind = "alpha-composite"
    else:
        raise ValueError(f"unknown derived transparency processor for {canonical}")
    derivation: dict[str, Any] = {"kind": kind}
    if isinstance(transparency.get("source_sha256"), str):
        derivation["sourceSha256"] = transparency["source_sha256"]
    if isinstance(transparency.get("output_sha256"), str):
        derivation["outputSha256"] = transparency["output_sha256"]
    tool = sidecar.get("tool")
    if (
        isinstance(tool, dict)
        and isinstance(tool.get("name"), str)
        and isinstance(tool.get("version"), str)
    ):
        derivation["tool"] = {"name": tool["name"], "version": tool["version"]}
    return {
        "mode": mode,
        "canonicalPath": canonical,
        "canonicalProvenancePath": canonical_meta,
        "derivation": derivation,
        "lineage": {
            "kind": "derived",
            "sourcePaths": source_names,
            "sourceProvenancePaths": source_meta,
        },
    }


def _run_relative_path(run_dir: Path, artifact_path: str) -> str:
    path = Path(artifact_path)
    resolved = path.resolve() if path.is_absolute() else (run_dir / path).resolve()
    try:
        relative = resolved.relative_to(run_dir.resolve())
    except ValueError as error:
        raise ValueError(
            "derived transparency source must stay inside the run directory"
        ) from error
    if str(relative) in {"", "."}:
        raise ValueError("derived transparency source must stay inside the run directory")
    return relative.as_posix()


def _artifact_sha256(sidecar: dict[str, Any], artifact_name: str) -> str:
    artifact = sidecar.get("artifact")
    digest = artifact.get("sha256") if isinstance(artifact, dict) else None
    if not isinstance(digest, str):
        raise ValueError(f"canonical provenance is invalid for {artifact_name}")
    return digest


def _verify_artifact_binding(path: Path, sidecar: dict[str, Any], artifact_name: str) -> None:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ValueError(f"canonical artifact is missing for {artifact_name}") from error
    artifact = sidecar.get("artifact")
    if (
        not isinstance(artifact, dict)
        or artifact.get("sha256") != hashlib.sha256(data).hexdigest()
        or artifact.get("bytes") != len(data)
    ):
        raise ValueError(f"canonical artifact binding mismatch for {artifact_name}")


def _validate_alpha_contract(sidecar: dict[str, Any], artifact_name: str) -> None:
    validation = sidecar.get("validation")
    if (
        not isinstance(validation, dict)
        or validation.get("alpha_nontrivial") is not True
        or validation.get("dimensions_preserved") is not True
        or not isinstance(validation.get("output_width"), int)
        or not isinstance(validation.get("output_height"), int)
        or int(validation["output_width"]) <= 0
        or int(validation["output_height"]) <= 0
        or not isinstance(validation.get("transparent_pixels"), int)
        or not isinstance(validation.get("nontransparent_pixels"), int)
        or int(validation["transparent_pixels"]) <= 0
        or int(validation["nontransparent_pixels"]) <= 0
    ):
        raise ValueError(f"canonical alpha validation is invalid for {artifact_name}")


def _validate_derived_hashes(
    sidecar: dict[str, Any],
    transparency: dict[str, Any],
    source_names: list[str],
    source_meta: list[str],
    run_dir: Path,
    canonical: str,
) -> None:
    output_digest = _artifact_sha256(sidecar, canonical)
    if transparency.get("output_sha256") != output_digest:
        raise ValueError(f"derived output digest mismatch for {canonical}")
    source_digests = {
        source: _artifact_sha256(_read_sidecar(run_dir / meta, source), source)
        for source, meta in zip(source_names, source_meta, strict=True)
    }
    recorded = transparency.get("source_hashes")
    if isinstance(recorded, list):
        recorded_digests: dict[str, str] = {}
        for item in recorded:
            if not isinstance(item, dict):
                raise ValueError(f"derived source digests are invalid for {canonical}")
            path = item.get("path")
            digest = item.get("sha256")
            if not isinstance(path, str) or not isinstance(digest, str):
                raise ValueError(f"derived source digests are invalid for {canonical}")
            recorded_digests[_run_relative_path(run_dir, path)] = digest
        if recorded_digests != source_digests:
            raise ValueError(f"derived source digest mismatch for {canonical}")
        return
    singular = transparency.get("source_sha256")
    if len(source_names) != 1 or singular != source_digests[source_names[0]]:
        raise ValueError(f"derived source digests are missing for {canonical}")


def _ensure_run_music_pair(target: Path, fallback: Path) -> dict[str, Any]:
    target_meta = Path(f"{target}.meta.json")
    if target.exists() or target_meta.exists():
        if not target.is_file() or not target_meta.is_file():
            raise ValueError("per-run music must include both artifact and provenance")
        copied_fallback = _existing_fallback_metadata(target, target_meta, fallback)
        if copied_fallback is not None:
            return copied_fallback
        sidecar = _json_object(target_meta, "per-run music provenance")
        return {
            "source": "per-run",
            "rights_status": _optional_rights_status(
                sidecar.get("rights"), "per-run music provenance"
            ),
        }
    fallback_meta = Path(f"{fallback}.meta.json")
    if not fallback.is_file() or not fallback_meta.is_file():
        raise ValueError(
            "scrolling-preview music is missing; generate a per-run artifact with the "
            "generate-music capability or provide a redistribution-approved bundled fallback"
        )
    validated = _validate_fallback(fallback, fallback_meta)
    target.parent.mkdir(parents=True, exist_ok=True)
    installed: list[Path] = []
    temporary: list[Path] = []
    try:
        for destination, data in (
            (target, validated["artifact_bytes"]),
            (target_meta, validated["sidecar_text"].encode()),
        ):
            handle, temp_name = tempfile.mkstemp(
                prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
            )
            temp = Path(temp_name)
            temporary.append(temp)
            with os.fdopen(handle, "wb") as stream:
                os.chmod(temp, 0o600)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, destination)
            temporary.remove(temp)
            installed.append(destination)
    except Exception:
        for path in installed:
            path.unlink(missing_ok=True)
        raise
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)
    return {
        "source": "generated-fallback",
        "rights_status": validated["rights"]["status"],
    }


def _existing_fallback_metadata(
    target: Path, target_meta: Path, fallback: Path
) -> dict[str, Any] | None:
    fallback_meta = Path(f"{fallback}.meta.json")
    if not fallback.is_file() or not fallback_meta.is_file():
        return None
    try:
        if (
            target.read_bytes() != fallback.read_bytes()
            or target_meta.read_bytes() != fallback_meta.read_bytes()
        ):
            return None
    except OSError:
        return None
    validated = _validate_fallback(fallback, fallback_meta)
    return {
        "source": "generated-fallback",
        "rights_status": validated["rights"]["status"],
    }


def _validate_fallback(fallback: Path, meta: Path) -> dict[str, Any]:
    artifact_bytes = fallback.read_bytes()
    sidecar_text = meta.read_text(encoding="utf-8")
    try:
        sidecar = json.loads(sidecar_text)
    except json.JSONDecodeError as error:
        raise ValueError("bundled fallback provenance is not valid JSON") from error
    if (
        not isinstance(sidecar, dict)
        or sidecar.get("schema_version") != 2
        or not isinstance(sidecar.get("artifact"), dict)
    ):
        raise ValueError("bundled fallback provenance is invalid")
    digest = sidecar["artifact"]
    if digest.get("sha256") != hashlib.sha256(artifact_bytes).hexdigest():
        raise ValueError("bundled fallback artifact digest does not match its provenance")
    if digest.get("bytes") != len(artifact_bytes):
        raise ValueError("bundled fallback artifact byte count does not match its provenance")
    rights = _parse_rights(sidecar.get("rights"))
    if rights["status"] != "redistribution-approved":
        raise ValueError(
            "bundled fallback is not publication-approved "
            f"(rights.status={rights['status']}); generate per-run music or record "
            "an explicit reviewed rights decision"
        )
    _assert_publishable_references(sidecar, rights)
    return {
        "artifact_bytes": artifact_bytes,
        "sidecar_text": sidecar_text,
        "rights": rights,
    }


def _parse_rights(value: object) -> dict[str, Any]:
    try:
        rights = ArtifactRights.model_validate(value)
    except ValueError as error:
        raise ValueError("bundled fallback rights are missing or invalid") from error
    return rights.model_dump(mode="json")


def _optional_rights_status(value: object, label: str) -> MusicRightsStatus:
    if value is None:
        return "unrecorded"
    try:
        status = _parse_rights(value)["status"]
        if status == "unreviewed":
            return "unreviewed"
        if status == "restricted":
            return "restricted"
        if status == "redistribution-approved":
            return "redistribution-approved"
        raise ValueError(f"{label} rights are invalid")
    except ValueError as error:
        raise ValueError(f"{label} rights are invalid") from error


def _assert_publishable_references(sidecar: dict[str, Any], rights: dict[str, Any]) -> None:
    for key in ("references", "refs"):
        refs = sidecar.get(key)
        if refs is None:
            continue
        if not isinstance(refs, list) or not all(isinstance(value, str) for value in refs):
            raise ValueError(f"bundled fallback {key} are invalid")
        for reference in refs:
            _assert_portable(reference, key)
    inputs = sidecar.get("inputs")
    if inputs is not None:
        if not isinstance(inputs, list):
            raise ValueError("bundled fallback inputs are invalid")
        for item in inputs:
            if not isinstance(item, dict) or not isinstance(item.get("ref"), str):
                raise ValueError("bundled fallback input reference is invalid")
            _assert_portable(item["ref"], "input ref")
    for basis in rights["basis"]:
        _assert_portable(basis, "rights basis")


def _assert_portable(reference: str, label: str) -> None:
    if not is_portable_artifact_reference(reference):
        raise ValueError(f"bundled fallback {label} must use a stable non-temporary reference")


def _json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} is not valid JSON") from error
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must be an object")
    return parsed


def _write_local_artifact_pair(
    path: Path,
    payload: bytes,
    *,
    media_type: str,
    prompt: str,
    refs: list[str],
    params: dict[str, Any],
    validation: dict[str, Any],
) -> Path:
    artifact = BinaryArtifact(data=payload, media_type=media_type)
    provenance = ProvenanceInput(
        provider="local",
        model="deterministic-manifest",
        prompt=prompt,
        refs=refs,
        params=params,
        validation=validation,
        component=SoftwareIdentity(name="@stage-gen/stage-gen", version="0.0.0"),
        tool=SoftwareIdentity(name="scrolling-preview-manifest", version="1"),
        attempts=1,
    )
    sidecar = Path(f"{path}.meta.json")
    if path.is_file() and sidecar.is_file() and path.read_bytes() == payload:
        try:
            existing = ArtifactProvenance.model_validate_json(sidecar.read_text(encoding="utf-8"))
            expected = build_artifact_provenance(
                artifact,
                provenance.model_copy(update={"timestamp": existing.ts}),
            )
        except (OSError, ValueError):
            pass
        else:
            if existing == expected:
                return sidecar
    return write_artifact_with_provenance(path, artifact, provenance)
