"""Resolve authored map metadata and project it into a scrolling manifest."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from gnode import (
    ArtifactProvenance,
    BinaryArtifact,
    InputProvenance,
    ProvenanceInput,
    SoftwareIdentity,
    sha256_hex,
    write_artifact_with_provenance_async,
)
from stage_gen.components.game_contract import (
    GameContractBinding,
    ResolvedGameContract,
    resolve_game_contract_binding,
)
from stage_gen.components.game_map import (
    GAME_MAP_LIBRARY_RESOLUTION_VERSION,
    GameMapBookBinding,
    ResolvedGameMapBook,
    canonical_game_map_json,
    canonical_resolved_game_map_book_json,
    load_resolved_game_map_book_bytes,
    resolve_game_map_book_binding,
)
from stage_gen.components.game_soundtrack import (
    GameSoundtrackBinding,
    ResolvedGameSoundtrack,
    resolve_game_soundtrack_binding,
)
from stage_gen.recipes.base import StageContext
from stage_gen.recipes.scrolling_preview.cache import valid_artifact_pair

MAP_BOOK_RESOLUTION_VERSION = "scrolling-game-map-book-resolution-v2"
MAP_BOOK_MANIFEST_KIND = "game-map-book-manifest-v2"

_SUPPORTED_SCROLLING_LEVEL_PROFILES: dict[str, dict[str, object]] = {
    "social_hub": {
        "schema_version": 1,
        "kind": "level-profile-v1",
        "role": "social_hub",
        "view": {"projection": "orthographic_2d", "viewpoint": "side_on"},
        "camera": {
            "tracking_mode": "player_follow",
            "framing_mode": "dead_zone",
            "scroll_axes": ["horizontal"],
        },
        "traversal": {
            "ground_model": "heightfield",
            "platform_model": "none",
            "affordances": ["ground_move", "jump"],
        },
        "mechanisms": {
            "encounter_model": "none",
            "combat_model": "none",
            "loot_model": "none",
            "transition_model": "bidirectional_portals",
            "interaction_model": "proximity_dialogue",
        },
    },
    "combat_field": {
        "schema_version": 1,
        "kind": "level-profile-v1",
        "role": "combat_field",
        "view": {"projection": "orthographic_2d", "viewpoint": "side_on"},
        "camera": {
            "tracking_mode": "player_follow",
            "framing_mode": "dead_zone",
            "scroll_axes": ["horizontal", "vertical"],
        },
        "traversal": {
            "ground_model": "heightfield",
            "platform_model": "one_way",
            "affordances": [
                "ground_move",
                "jump",
                "air_jump",
                "drop_through",
                "climb",
            ],
        },
        "mechanisms": {
            "encounter_model": "continuous_population",
            "combat_model": "real_time_action",
            "loot_model": "defeat_drops",
            "transition_model": "bidirectional_portals",
            "interaction_model": "none",
        },
    },
}

# The core contract intentionally stops at engine-neutral scene semantics. This
# allowlist belongs to the optional scrolling-demo adapter: each identity names
# one static geometry implementation in web/lib/runtime/stages.ts.
_SCROLLING_DEMO_LEVEL_ROLE_BY_MAP_ID = {
    "village-hub": "social_hub",
    "stage-1-approach": "combat_field",
    "stage-2-gauntlet": "combat_field",
    "stage-3-spires": "combat_field",
}

_RECIPE_COMPONENT = SoftwareIdentity(name="@stage-gen/stage-gen", version="0.0.0")
_TOOL = SoftwareIdentity(name="stage-gen", version="0.0.0")


@dataclass(frozen=True, slots=True)
class CollectedMapBook:
    manifest: dict[str, object]
    artifact_paths: tuple[str, ...]


def parse_game_map_book_binding(value: object) -> dict[str, object]:
    return GameMapBookBinding.model_validate(value).model_dump(mode="json")


def assert_map_book_matches_game_and_soundtrack(
    map_book_value: object,
    game_value: object,
    soundtrack_value: object,
) -> None:
    map_book = GameMapBookBinding.model_validate(map_book_value)
    game = GameContractBinding.model_validate(game_value)
    soundtrack = GameSoundtrackBinding.model_validate(soundtrack_value)
    owners = {
        PurePosixPath(map_book.ref).parts[:3],
        PurePosixPath(game.ref).parts[:3],
        PurePosixPath(soundtrack.ref).parts[:3],
    }
    if len(owners) != 1:
        raise ValueError("scrolling-preview map_book, game, and soundtrack must share game_id")


def map_book_contract_path(run_dir: Path, tag: str) -> Path:
    return run_dir / f"map_book_{tag}.json"


async def resolve_scrolling_map_book(context: StageContext) -> tuple[str, ...]:
    resolved, soundtrack, game = await _resolve_from_context(context)
    output = map_book_contract_path(context.run_dir, context.tag)
    identity = _resolved_identity(resolved, soundtrack, game)
    force = "map-book-resolve" in context.affected_stages
    if valid_artifact_pair(
        output,
        validator=lambda path, sidecar: _valid_resolved_cache(path, sidecar, resolved, identity),
        force=force,
    ):
        return (str(output), f"{output}.meta.json")
    sidecar = await write_artifact_with_provenance_async(
        output,
        BinaryArtifact(data=resolved.canonical_bytes, media_type="application/json"),
        ProvenanceInput(
            provider="local",
            model=MAP_BOOK_RESOLUTION_VERSION,
            prompt="resolve authored game map book",
            refs=[
                resolved.binding.ref,
                *(game_map.source_ref for game_map in resolved.maps),
                game.binding.ref,
                soundtrack.binding.ref,
            ],
            inputs=[
                *resolved.source_provenance,
                game.source_provenance,
                soundtrack.source_provenance,
            ],
            params={"stage": "map-book-resolve", "map_book": identity},
            validation={
                "source_digests_verified": True,
                "canonical_digest_verified": True,
                "game_id_verified": True,
                "map_ids_unique": True,
                "map_order_verified": True,
                "soundtrack_track_ids_verified": True,
                "level_profiles_supported": True,
                "static_map_topology_supported": True,
            },
            component=_RECIPE_COMPONENT,
            tool=_TOOL,
            attempts=1,
        ),
    )
    return (str(output), str(sidecar))


def collect_scrolling_map_book(
    run_dir: Path,
    tag: str,
    *,
    soundtrack_manifest: Mapping[str, object],
) -> CollectedMapBook:
    if (
        soundtrack_manifest.get("schema_version") != 2
        or soundtrack_manifest.get("kind") != "game-soundtrack-manifest-v2"
    ):
        raise ValueError("map book requires a current soundtrack manifest")
    contract_path = map_book_contract_path(run_dir, tag)
    if not valid_artifact_pair(
        contract_path,
        validator=_valid_collected_contract,
        force=False,
    ):
        raise ValueError("resolved map book artifact pair is missing, stale, or invalid")
    document = load_resolved_game_map_book_bytes(contract_path.read_bytes())
    sidecar = _read_sidecar(Path(f"{contract_path}.meta.json"))
    params = sidecar.get("params")
    identity = params.get("map_book") if isinstance(params, Mapping) else None
    if not isinstance(identity, Mapping):
        raise ValueError("resolved map book identity is missing")

    soundtrack_tracks = soundtrack_manifest.get("tracks")
    if not isinstance(soundtrack_tracks, list):
        raise ValueError("map book requires a complete soundtrack manifest")
    available_ids: set[object] = set()
    available_track_ids: list[str] = []
    for entry in soundtrack_tracks:
        track_id = entry.get("track_id") if isinstance(entry, Mapping) else None
        if not isinstance(track_id, str) or track_id in available_ids:
            raise ValueError("map book requires unique soundtrack manifest track identities")
        available_ids.add(track_id)
        available_track_ids.append(track_id)
    _assert_known_track_ids(document.referenced_track_ids, available_ids)

    map_sources = identity.get("map_sources")
    if not isinstance(map_sources, list) or len(map_sources) != len(document.maps):
        raise ValueError("resolved map book source identities are incomplete")
    source_by_id: dict[str, Mapping[str, object]] = {}
    for source in map_sources:
        if not isinstance(source, Mapping) or not isinstance(source.get("map_id"), str):
            raise ValueError("resolved map source identity is invalid")
        source_by_id[str(source["map_id"])] = source

    maps: list[dict[str, object]] = []
    for game_map in document.maps:
        source = source_by_id.get(game_map.map_id)
        if source is None:
            raise ValueError(f"resolved map source identity is missing: {game_map.map_id}")
        _validate_scrolling_level_profile(game_map.level_profile.model_dump(mode="json"))
        maps.append(
            {
                "map_id": game_map.map_id,
                "revision": game_map.revision,
                "display_name": game_map.display_name,
                "soundtrack_track_ids": list(game_map.soundtrack_track_ids),
                "source_ref": source["source_ref"],
                "source_sha256": source["source_sha256"],
                "canonical_sha256": source["canonical_sha256"],
                "level_profile": game_map.level_profile.model_dump(mode="json"),
            }
        )

    soundtrack_identity = identity.get("soundtrack")
    if not isinstance(soundtrack_identity, Mapping):
        raise ValueError("resolved map book soundtrack identity is missing")
    soundtrack_source = soundtrack_manifest.get("source")
    if (
        soundtrack_manifest.get("game_id") != document.game_id
        or not isinstance(soundtrack_source, Mapping)
        or soundtrack_source.get("source_sha256") != soundtrack_identity.get("source_sha256")
        or soundtrack_source.get("canonical_sha256") != soundtrack_identity.get("canonical_sha256")
        or soundtrack_identity.get("track_ids") != available_track_ids
    ):
        raise ValueError("resolved map book soundtrack lineage does not match the manifest")
    return CollectedMapBook(
        manifest={
            "schema_version": 2,
            "kind": MAP_BOOK_MANIFEST_KIND,
            "game_id": document.game_id,
            "revision": document.revision,
            "entry_map_id": document.entry_map_id,
            "source": {
                "path": contract_path.name,
                "provenance_path": f"{contract_path.name}.meta.json",
                "source_sha256": identity["source_sha256"],
                "canonical_sha256": identity["canonical_sha256"],
            },
            "soundtrack": {
                "source_sha256": soundtrack_identity["source_sha256"],
                "canonical_sha256": soundtrack_identity["canonical_sha256"],
            },
            "maps": maps,
        },
        artifact_paths=(contract_path.name, f"{contract_path.name}.meta.json"),
    )


async def _resolve_from_context(
    context: StageContext,
) -> tuple[ResolvedGameMapBook, ResolvedGameSoundtrack, ResolvedGameContract]:
    if "map_book" not in context.input:
        raise ValueError("map-book-resolve requires a game map book binding")
    if "game" not in context.input or "soundtrack" not in context.input:
        raise ValueError("a game map book requires game and soundtrack bindings")
    assert_map_book_matches_game_and_soundtrack(
        context.input["map_book"],
        context.input["game"],
        context.input["soundtrack"],
    )
    root = context.config.game_library_root
    if root is None:
        raise ValueError("map-book-directed scrolling generation requires game_library_root")
    resolved, soundtrack, game = await asyncio.gather(
        asyncio.to_thread(
            resolve_game_map_book_binding,
            context.input["map_book"],
            game_library_root=root,
        ),
        asyncio.to_thread(
            resolve_game_soundtrack_binding,
            context.input["soundtrack"],
            game_library_root=root,
        ),
        asyncio.to_thread(
            resolve_game_contract_binding,
            context.input["game"],
            game_library_root=root,
        ),
    )
    game_binding = GameContractBinding.model_validate(context.input["game"])
    game_id = PurePosixPath(game_binding.ref).parts[2]
    if (
        resolved.book.game_id != game_id
        or soundtrack.soundtrack.game_id != game_id
        or game.contract.game_id != game_id
    ):
        raise ValueError("resolved map book, game, and soundtrack game_id values must match")
    _assert_known_track_ids(
        resolved.document.referenced_track_ids,
        set(soundtrack.soundtrack.track_ids),
    )
    for game_map in resolved.document.maps:
        _validate_scrolling_level_profile(game_map.level_profile.model_dump(mode="json"))
    _validate_scrolling_demo_topology(
        resolved,
        has_village="village" in context.input,
    )
    _validate_resolved_population_coverage(resolved, game)
    return resolved, soundtrack, game


def _assert_known_track_ids(referenced: frozenset[str], available: set[object]) -> None:
    unknown = sorted(referenced - {item for item in available if isinstance(item, str)})
    if unknown:
        raise ValueError(f"map book references unknown soundtrack track_id values: {unknown}")


def _validate_resolved_population_coverage(
    resolved: ResolvedGameMapBook,
    game: ResolvedGameContract,
) -> None:
    """Reject an incomplete encounter profile before any provider-backed stage can run."""
    required = frozenset(
        game_map.map_id
        for game_map in resolved.document.maps
        if game_map.level_profile.mechanisms.encounter_model == "continuous_population"
    )
    gameplay = game.contract.gameplay
    population = gameplay.mob_population if gameplay is not None else None
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
            "continuous_population maps before generation; "
            f"missing: {missing}; unexpected: {unexpected}"
        )


def _validate_scrolling_demo_topology(
    resolved: ResolvedGameMapBook,
    *,
    has_village: bool,
) -> None:
    """Bind current scene semantics to this adapter's finite static geometry registry."""

    social_hub_ids: set[str] = set()
    for game_map in resolved.document.maps:
        profile = game_map.level_profile
        expected_role = _SCROLLING_DEMO_LEVEL_ROLE_BY_MAP_ID.get(game_map.map_id)
        if expected_role is None:
            raise ValueError(
                f"scrolling-preview map-book-v2 names unsupported static map_id {game_map.map_id}"
            )
        if profile.role != expected_role:
            actual_role = profile.role
            raise ValueError(
                f"scrolling-preview map {game_map.map_id} requires level_profile role "
                f"{expected_role}, got {actual_role}"
            )
        if profile.role == "social_hub":
            social_hub_ids.add(game_map.map_id)

    expected_social_hub_ids = {"village-hub"} if has_village else set()
    if social_hub_ids != expected_social_hub_ids:
        raise ValueError(
            "scrolling-preview map-book-v2 village identity must exactly match the "
            "generated village asset opt-in"
        )


def _resolved_identity(
    resolved: ResolvedGameMapBook,
    soundtrack: ResolvedGameSoundtrack,
    game: ResolvedGameContract,
) -> dict[str, object]:
    return {
        **resolved.identity(),
        "recipe_resolution_version": MAP_BOOK_RESOLUTION_VERSION,
        "artifact_ref": f"sha256:{resolved.canonical_sha256}",
        "artifact_sha256": resolved.canonical_sha256,
        "artifact_bytes": len(resolved.canonical_bytes),
        "game_contract": {
            "ref": game.binding.ref,
            "schema_version": game.contract.schema_version,
            "source_sha256": game.source_sha256,
            "canonical_sha256": game.canonical_sha256,
        },
        "soundtrack": {
            "ref": soundtrack.binding.ref,
            "source_sha256": soundtrack.source_sha256,
            "canonical_sha256": soundtrack.canonical_sha256,
            "track_ids": list(soundtrack.soundtrack.track_ids),
        },
    }


def _valid_resolved_cache(
    path: Path,
    sidecar: dict[str, Any],
    resolved: ResolvedGameMapBook,
    identity: Mapping[str, object],
) -> bool:
    try:
        if path.read_bytes() != resolved.canonical_bytes:
            return False
        document = load_resolved_game_map_book_bytes(resolved.canonical_bytes)
        if canonical_resolved_game_map_book_json(document) != resolved.canonical_bytes:
            return False
    except (OSError, ValueError):
        return False
    params = sidecar.get("params")
    soundtrack = identity.get("soundtrack")
    game_contract = identity.get("game_contract")
    return (
        sidecar.get("provider") == "local"
        and sidecar.get("model") == MAP_BOOK_RESOLUTION_VERSION
        and isinstance(soundtrack, Mapping)
        and isinstance(game_contract, Mapping)
        and sidecar.get("refs")
        == [
            resolved.binding.ref,
            *(game_map.source_ref for game_map in resolved.maps),
            game_contract.get("ref"),
            soundtrack.get("ref"),
        ]
        and isinstance(params, Mapping)
        and params.get("stage") == "map-book-resolve"
        and params.get("map_book") == dict(identity)
    )


def _valid_collected_contract(path: Path, sidecar: dict[str, Any]) -> bool:
    try:
        raw = path.read_bytes()
        document = load_resolved_game_map_book_bytes(raw)
        if canonical_resolved_game_map_book_json(document) != raw:
            return False
        provenance = ArtifactProvenance.model_validate(sidecar)
        params = provenance.params
        identity = params.get("map_book")
        if not isinstance(identity, Mapping):
            return False
        binding = GameMapBookBinding.model_validate(identity.get("binding"))
    except (OSError, ValueError):
        return False

    identity_keys = {
        "schema_version",
        "kind",
        "resolution_version",
        "binding",
        "game_id",
        "revision",
        "entry_map_id",
        "map_ids",
        "source_sha256",
        "canonical_sha256",
        "canonical_bytes",
        "map_sources",
        "recipe_resolution_version",
        "artifact_ref",
        "artifact_sha256",
        "artifact_bytes",
        "game_contract",
        "soundtrack",
    }
    canonical_sha256 = sha256_hex(raw)
    if (
        provenance.provider != "local"
        or provenance.model != MAP_BOOK_RESOLUTION_VERSION
        or provenance.prompt != "resolve authored game map book"
        or set(params) != {"stage", "map_book"}
        or params.get("stage") != "map-book-resolve"
        or set(identity) != identity_keys
        or identity.get("schema_version") != 2
        or identity.get("kind") != "resolved-game-map-book-v2"
        or identity.get("resolution_version") != GAME_MAP_LIBRARY_RESOLUTION_VERSION
        or identity.get("recipe_resolution_version") != MAP_BOOK_RESOLUTION_VERSION
        or identity.get("binding") != binding.model_dump(mode="json")
        or binding.ref != f"library/games/{document.game_id}/maps/index.toml"
        or identity.get("game_id") != document.game_id
        or identity.get("revision") != document.revision
        or identity.get("entry_map_id") != document.entry_map_id
        or identity.get("map_ids") != list(document.map_ids)
        or identity.get("source_sha256") != binding.source_sha256
        or identity.get("canonical_sha256") != canonical_sha256
        or identity.get("canonical_bytes") != len(raw)
        or identity.get("artifact_ref") != f"sha256:{canonical_sha256}"
        or identity.get("artifact_sha256") != canonical_sha256
        or identity.get("artifact_bytes") != len(raw)
    ):
        return False

    map_sources = identity.get("map_sources")
    game_contract = identity.get("game_contract")
    soundtrack = identity.get("soundtrack")
    if (
        not isinstance(map_sources, list)
        or len(map_sources) != len(document.maps)
        or not isinstance(game_contract, Mapping)
        or set(game_contract) != {"ref", "schema_version", "source_sha256", "canonical_sha256"}
        or game_contract.get("ref") != f"library/games/{document.game_id}/game.toml"
        or game_contract.get("schema_version") != 3
        or not _is_sha256(game_contract.get("source_sha256"))
        or not _is_sha256(game_contract.get("canonical_sha256"))
        or not isinstance(soundtrack, Mapping)
        or set(soundtrack) != {"ref", "source_sha256", "canonical_sha256", "track_ids"}
        or soundtrack.get("ref") != f"library/games/{document.game_id}/soundtrack.toml"
        or not _is_sha256(soundtrack.get("source_sha256"))
        or not _is_sha256(soundtrack.get("canonical_sha256"))
        or not _valid_track_id_list(soundtrack.get("track_ids"))
        or len(provenance.inputs) != len(document.maps) + 3
    ):
        return False

    refs = [binding.ref]
    if not _source_input_matches(
        provenance.inputs[0],
        ref=binding.ref,
        source_sha256=binding.source_sha256,
    ):
        return False
    for index, (game_map, source) in enumerate(
        zip(document.maps, map_sources, strict=True),
        start=1,
    ):
        if not isinstance(source, Mapping):
            return False
        canonical_map = canonical_game_map_json(game_map)
        source_ref = f"library/games/{document.game_id}/maps/{game_map.map_id}.toml"
        source_sha256 = source.get("source_sha256")
        expected_source_keys = {
            "schema_version",
            "kind",
            "resolution_version",
            "game_id",
            "map_id",
            "revision",
            "soundtrack_track_ids",
            "source_ref",
            "source_sha256",
            "canonical_sha256",
            "canonical_bytes",
        }
        expected_source_keys.add("level_profile")
        if (
            set(source) != expected_source_keys
            or source.get("schema_version") != 2
            or source.get("kind") != "resolved-game-map-v2"
            or source.get("resolution_version") != GAME_MAP_LIBRARY_RESOLUTION_VERSION
            or source.get("game_id") != game_map.game_id
            or source.get("map_id") != game_map.map_id
            or source.get("revision") != game_map.revision
            or source.get("soundtrack_track_ids") != list(game_map.soundtrack_track_ids)
            or source.get("source_ref") != source_ref
            or not _is_sha256(source_sha256)
            or source.get("canonical_sha256") != sha256_hex(canonical_map)
            or source.get("canonical_bytes") != len(canonical_map)
            or source.get("level_profile") != game_map.level_profile.model_dump(mode="json")
            or not _source_input_matches(
                provenance.inputs[index],
                ref=source_ref,
                source_sha256=source_sha256,
            )
        ):
            return False
        refs.append(source_ref)

    game_ref = str(game_contract["ref"])
    game_source_sha256 = game_contract["source_sha256"]
    if not _source_input_matches(
        provenance.inputs[-2],
        ref=game_ref,
        source_sha256=game_source_sha256,
    ):
        return False
    refs.append(game_ref)

    soundtrack_ref = str(soundtrack["ref"])
    soundtrack_source_sha256 = soundtrack["source_sha256"]
    if not _source_input_matches(
        provenance.inputs[-1],
        ref=soundtrack_ref,
        source_sha256=soundtrack_source_sha256,
    ):
        return False
    refs.append(soundtrack_ref)
    return provenance.refs == refs


def _validate_scrolling_level_profile(value: Mapping[str, object]) -> None:
    """Gate engine-neutral profiles against the optional demo runtime's exact capabilities."""

    role = value.get("role")
    expected = _SUPPORTED_SCROLLING_LEVEL_PROFILES.get(role) if isinstance(role, str) else None
    if expected is None or dict(value) != expected:
        raise ValueError(
            "scrolling-preview supports only the canonical social_hub and combat_field "
            "level-profile capability combinations"
        )


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _valid_track_id_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= 2
        and all(isinstance(item, str) for item in value)
        and len(set(value)) == len(value)
    )


def _source_input_matches(
    value: InputProvenance,
    *,
    ref: str,
    source_sha256: object,
) -> bool:
    return (
        value.ref == ref
        and value.sha256 == source_sha256
        and value.source == "content"
        and isinstance(value.bytes, int)
        and value.bytes > 0
        and value.media_type == "application/toml"
    )


def _read_sidecar(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError("resolved map book provenance is unreadable") from error
    if not isinstance(value, dict):
        raise ValueError("resolved map book provenance must be an object")
    return value


__all__ = [
    "MAP_BOOK_MANIFEST_KIND",
    "MAP_BOOK_RESOLUTION_VERSION",
    "CollectedMapBook",
    "assert_map_book_matches_game_and_soundtrack",
    "collect_scrolling_map_book",
    "map_book_contract_path",
    "parse_game_map_book_binding",
    "resolve_scrolling_map_book",
]
