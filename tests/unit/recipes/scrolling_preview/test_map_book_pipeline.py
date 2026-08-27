from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from stage_gen.components.game_map import load_game_map
from stage_gen.config import StageGenConfig, TransparencyMode
from stage_gen.contracts import ArtifactProvenance
from stage_gen.recipes.base import StageContext, resolve_force_stage_plan
from stage_gen.recipes.scrolling_preview import manifest as manifest_module
from stage_gen.recipes.scrolling_preview import map_book as map_book_module
from stage_gen.recipes.scrolling_preview.manifest import write_scrolling_preview_manifest
from stage_gen.recipes.scrolling_preview.map_book import (
    MAP_BOOK_MANIFEST_KIND,
    CollectedMapBook,
    assert_map_book_matches_game_and_soundtrack,
    collect_scrolling_map_book,
    map_book_contract_path,
    resolve_scrolling_map_book,
)
from stage_gen.recipes.scrolling_preview.recipe import parse_scrolling_preview_input
from stage_gen.recipes.scrolling_preview.soundtrack import CollectedSoundtrack
from stage_gen.recipes.scrolling_preview.stages import scrolling_preview_stages


def _write_game(root: Path, *, with_population: bool = True) -> tuple[Path, str]:
    source = root / "library/games/test-game/game.toml"
    source.parent.mkdir(parents=True, exist_ok=True)
    gameplay = ""
    if with_population:
        gameplay = """
[gameplay.combat_text]
schema_version = 1
kind = "combat-text-v1"
enabled = true

[gameplay.mob_population]
schema_version = 2
kind = "mob-population-v2"
update_interval_ms = 100
max_spawn_batch_per_update = 1

[[gameplay.mob_population.maps]]
map_id = "stage-1-approach"
seed_salt = 17

[[gameplay.mob_population.maps.zones]]
zone_id = "main-field"
surface = "terrain"
left_column = 8
right_column_exclusive = 48
initial_population = 1
target_population = 1
population_cap = 1
respawn_delay_ms = 5000
respawn_variance_ms = 1000
spawn_interval_ms = 500
spawn_batch_size = 1
retry_delay_ms = 250
spawn_visibility = "offscreen_preferred"
camera_margin_px = 128
min_player_distance_px = 256
minimum_spawn_separation_px = 64
wander_radius_px = 128
replacement_policy = "same_archetype"

[[gameplay.mob_population.maps.zones.spawn_table]]
mob_tier = 1
weight = 1
min_alive = 1
max_alive = 1
"""
    source.write_text(
        f"""schema_version = 3
kind = "game-contract-v3"
game_id = "test-game"
revision = 3
display_name = "Test Game"

[camera]
projection = "side_view_2d"

[style]
keywords = ["hand-painted gouache", "warm dusk palette", "soft diffuse light"]

[proportion]
heads_tall = 2.0

[cast.player]
body_kind = "human"

[cast.resident]
body_kind_default = "human"
{gameplay}
[rights]
status = "unreviewed"
""",
        encoding="utf-8",
    )
    return source, hashlib.sha256(source.read_bytes()).hexdigest()


def _write_soundtrack(root: Path) -> tuple[Path, str]:
    source = root / "library/games/test-game/soundtrack.toml"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        """schema_version = 1
kind = "game-soundtrack-v1"
game_id = "test-game"
revision = 1

[playback]
selection = "shuffle"
no_immediate_repeat = true

[[tracks]]
track_id = "first_theme"
display_name = "First Theme"
creative_brief = "An original quiet exploration instrumental."

[tracks.generation]
intent = "generate"
instrumental = true
seamless_loop = true
target_duration_seconds = 60

[[tracks]]
track_id = "second_theme"
display_name = "Second Theme"
creative_brief = "An original energetic exploration instrumental."

[tracks.generation]
intent = "generate"
instrumental = true
seamless_loop = true
target_duration_seconds = 60
""",
        encoding="utf-8",
    )
    return source, hashlib.sha256(source.read_bytes()).hexdigest()


def _write_map(
    root: Path,
    map_id: str,
    tracks: tuple[str, str],
    *,
    map_version: int = 2,
    profile_role: str | None = None,
) -> tuple[Path, str]:
    source = root / f"library/games/test-game/maps/{map_id}.toml"
    source.parent.mkdir(parents=True, exist_ok=True)
    profile = ""
    role = profile_role or ("social_hub" if map_id == "village-hub" else "combat_field")
    is_social_hub = role == "social_hub"
    scroll_axes = '"horizontal"' if is_social_hub else '"horizontal", "vertical"'
    platform_model = "none" if is_social_hub else "one_way"
    affordances = (
        '"ground_move", "jump"'
        if is_social_hub
        else '"ground_move", "jump", "air_jump", "drop_through", "ladder_climb"'
    )
    profile = f'''
[level_profile]
schema_version = 1
kind = "level-profile-v1"
role = "{role}"

[level_profile.view]
projection = "orthographic_2d"
viewpoint = "side_on"

[level_profile.camera]
tracking_mode = "player_follow"
framing_mode = "dead_zone"
scroll_axes = [{scroll_axes}]

[level_profile.traversal]
ground_model = "heightfield"
platform_model = "{platform_model}"
affordances = [{affordances}]

[level_profile.mechanisms]
encounter_model = "{"none" if is_social_hub else "continuous_population"}"
combat_model = "{"none" if is_social_hub else "real_time_action"}"
loot_model = "{"none" if is_social_hub else "defeat_drops"}"
transition_model = "bidirectional_portals"
interaction_model = "{"proximity_dialogue" if is_social_hub else "none"}"
'''
    source.write_text(
        f'''schema_version = {map_version}
kind = "game-map-v{map_version}"
game_id = "test-game"
map_id = "{map_id}"
revision = 1
display_name = "{map_id}"
soundtrack_track_ids = ["{tracks[0]}", "{tracks[1]}"]
{profile}''',
        encoding="utf-8",
    )
    return source, hashlib.sha256(source.read_bytes()).hexdigest()


def _write_map_book(
    root: Path,
    *,
    second_tracks: tuple[str, str] = ("first_theme", "second_theme"),
    map_version: int = 2,
) -> tuple[Path, str]:
    entry_map_id = "village-hub"
    combat_map_id = "stage-1-approach"
    _, first_sha = _write_map(
        root,
        entry_map_id,
        ("first_theme", "second_theme"),
        map_version=map_version,
    )
    _, second_sha = _write_map(root, combat_map_id, second_tracks, map_version=map_version)
    source = root / "library/games/test-game/maps/index.toml"
    source.write_text(
        f'''schema_version = 1
kind = "game-map-book-v1"
game_id = "test-game"
revision = 1
entry_map_id = "{entry_map_id}"

[[maps]]
map_id = "{entry_map_id}"
source_sha256 = "{first_sha}"

[[maps]]
map_id = "{combat_map_id}"
source_sha256 = "{second_sha}"
''',
        encoding="utf-8",
    )
    return source, hashlib.sha256(source.read_bytes()).hexdigest()


def _context(
    tmp_path: Path,
    *,
    map_book_sha256: str,
    soundtrack_sha256: str,
    game_sha256: str | None = None,
    village: bool = True,
) -> StageContext:
    if game_sha256 is None:
        _, game_sha256 = _write_game(tmp_path)
    run_dir = tmp_path / "out" / "test-tag"
    run_dir.mkdir(parents=True)
    input_payload: dict[str, object] = {
        "prompt": "test",
        "game": {
            "schema_version": 1,
            "kind": "game-contract-binding-v1",
            "ref": "library/games/test-game/game.toml",
            "source_sha256": game_sha256,
        },
        "soundtrack": {
            "schema_version": 1,
            "kind": "game-soundtrack-binding-v1",
            "ref": "library/games/test-game/soundtrack.toml",
            "source_sha256": soundtrack_sha256,
        },
        "map_book": {
            "schema_version": 1,
            "kind": "game-map-book-binding-v1",
            "ref": "library/games/test-game/maps/index.toml",
            "source_sha256": map_book_sha256,
        },
    }
    if village:
        input_payload["village"] = {"schema_version": 1, "kind": "village_hub_v1"}
    return StageContext(
        input=input_payload,
        tag="test-tag",
        run_dir=run_dir,
        config=StageGenConfig(
            game_library_root=tmp_path,
            transparency_mode=TransparencyMode.CHROMA,
        ),
    )


def _soundtrack_manifest(context: StageContext) -> dict[str, object]:
    sidecar = json.loads(
        Path(f"{map_book_contract_path(context.run_dir, context.tag)}.meta.json").read_text(
            encoding="utf-8"
        )
    )
    soundtrack = sidecar["params"]["map_book"]["soundtrack"]
    return {
        "schema_version": 2,
        "kind": "game-soundtrack-manifest-v2",
        "game_id": "test-game",
        "source": {
            "source_sha256": soundtrack["source_sha256"],
            "canonical_sha256": soundtrack["canonical_sha256"],
        },
        "tracks": [
            {"track_id": "first_theme"},
            {"track_id": "second_theme"},
        ],
    }


def test_parser_and_stage_graph_insert_only_the_local_map_book_stage() -> None:
    value = {
        "prompt": "test",
        "game": {
            "schema_version": 1,
            "kind": "game-contract-binding-v1",
            "ref": "library/games/test-game/game.toml",
            "source_sha256": "a" * 64,
        },
        "soundtrack": {
            "schema_version": 1,
            "kind": "game-soundtrack-binding-v1",
            "ref": "library/games/test-game/soundtrack.toml",
            "source_sha256": "b" * 64,
        },
        "map_book": {
            "schema_version": 1,
            "kind": "game-map-book-binding-v1",
            "ref": "library/games/test-game/maps/index.toml",
            "source_sha256": "c" * 64,
        },
    }
    parsed = parse_scrolling_preview_input(value)
    stages = scrolling_preview_stages(parsed)
    by_name = {stage.name: stage for stage in stages}
    assert by_name["map-book-resolve"].depends_on == (
        "game-resolve",
        "soundtrack-resolve",
    )
    assert "map-book-resolve" in by_name["manifest"].depends_on
    assert [stage.name for stage in stages].index("map-book-resolve") < [
        stage.name for stage in stages
    ].index("concept")
    assert "map_book" in parsed
    without_map_book = {key: item for key, item in value.items() if key != "map_book"}
    with pytest.raises(ValueError, match="requires a map_book"):
        parse_scrolling_preview_input(without_map_book)

    with pytest.raises(ValueError, match="requires game and soundtrack"):
        parse_scrolling_preview_input(
            {"prompt": "test", "game": value["game"], "map_book": value["map_book"]}
        )


def test_full_map_graph_is_topological_and_force_propagation_is_scoped() -> None:
    parsed = parse_scrolling_preview_input(
        {
            "prompt": "test",
            "game": {
                "schema_version": 1,
                "kind": "game-contract-binding-v1",
                "ref": "library/games/test-game/game.toml",
                "source_sha256": "a" * 64,
            },
            "soundtrack": {
                "schema_version": 1,
                "kind": "game-soundtrack-binding-v1",
                "ref": "library/games/test-game/soundtrack.toml",
                "source_sha256": "b" * 64,
            },
            "map_book": {
                "schema_version": 1,
                "kind": "game-map-book-binding-v1",
                "ref": "library/games/test-game/maps/index.toml",
                "source_sha256": "c" * 64,
            },
            "village": {"schema_version": 1, "kind": "village_hub_v1"},
        }
    )
    stages = scrolling_preview_stages(parsed)
    resolve_force_stage_plan(stages, ())
    seen: set[str] = set()
    for stage in stages:
        assert set(stage.depends_on) <= seen
        seen.add(stage.name)

    soundtrack_force = resolve_force_stage_plan(
        stages,
        ("soundtrack-resolve",),
    )
    assert soundtrack_force.affected == {
        "soundtrack-resolve",
        "map-book-resolve",
        "soundtrack-generate",
        "manifest",
    }
    map_force = resolve_force_stage_plan(stages, ("map-book-resolve",))
    assert map_force.affected == {"map-book-resolve", "manifest"}


async def test_map_book_resolve_is_digest_bound_and_collects_ordered_projection(
    tmp_path: Path,
) -> None:
    _, soundtrack_sha = _write_soundtrack(tmp_path)
    _, map_book_sha = _write_map_book(tmp_path)
    context = _context(
        tmp_path,
        map_book_sha256=map_book_sha,
        soundtrack_sha256=soundtrack_sha,
    )

    artifacts = await resolve_scrolling_map_book(context)
    output = map_book_contract_path(context.run_dir, context.tag)
    assert artifacts == (str(output), f"{output}.meta.json")
    document = json.loads(await asyncio.to_thread(output.read_text, encoding="utf-8"))
    assert [entry["map_id"] for entry in document["maps"]] == [
        "village-hub",
        "stage-1-approach",
    ]
    provenance = ArtifactProvenance.model_validate_json(
        await asyncio.to_thread(Path(f"{output}.meta.json").read_bytes)
    )
    assert provenance.params["stage"] == "map-book-resolve"
    assert len(provenance.inputs) == 5

    collected = collect_scrolling_map_book(
        context.run_dir,
        context.tag,
        soundtrack_manifest=_soundtrack_manifest(context),
    )
    assert collected.manifest["kind"] == MAP_BOOK_MANIFEST_KIND
    assert collected.manifest["entry_map_id"] == "village-hub"
    collected_maps = collected.manifest["maps"]
    assert isinstance(collected_maps, list)
    assert [entry["map_id"] for entry in collected_maps if isinstance(entry, dict)] == [
        "village-hub",
        "stage-1-approach",
    ]
    assert collected.artifact_paths == (output.name, f"{output.name}.meta.json")

    before = (await asyncio.to_thread(output.stat)).st_mtime_ns
    assert await resolve_scrolling_map_book(context) == artifacts
    assert (await asyncio.to_thread(output.stat)).st_mtime_ns == before


@pytest.mark.asyncio
async def test_v2_map_book_collection_projects_complete_level_profiles(tmp_path: Path) -> None:
    _, soundtrack_sha = _write_soundtrack(tmp_path)
    _, map_book_sha = _write_map_book(tmp_path, map_version=2)
    context = _context(
        tmp_path,
        map_book_sha256=map_book_sha,
        soundtrack_sha256=soundtrack_sha,
        village=True,
    )
    await resolve_scrolling_map_book(context)
    collected = collect_scrolling_map_book(
        context.run_dir,
        context.tag,
        soundtrack_manifest=_soundtrack_manifest(context),
    )
    assert collected.manifest["schema_version"] == 2
    assert collected.manifest["kind"] == MAP_BOOK_MANIFEST_KIND
    maps = collected.manifest["maps"]
    assert isinstance(maps, list)
    assert maps[0]["map_id"] == "village-hub"
    assert maps[0]["level_profile"]["role"] == "social_hub"
    assert maps[0]["level_profile"]["mechanisms"]["interaction_model"] == "proximity_dialogue"
    second_mechanisms = maps[1]["level_profile"]["mechanisms"]
    assert second_mechanisms["encounter_model"] == "continuous_population"


@pytest.mark.asyncio
async def test_map_book_resolve_rejects_unsupported_profile_before_artifact_write(
    tmp_path: Path,
) -> None:
    _, soundtrack_sha = _write_soundtrack(tmp_path)
    index_path, _ = _write_map_book(tmp_path, map_version=2)
    second_path = tmp_path / "library/games/test-game/maps/stage-1-approach.toml"
    original_second_sha = hashlib.sha256(second_path.read_bytes()).hexdigest()
    second_path.write_text(
        second_path.read_text(encoding="utf-8").replace(
            'interaction_model = "none"',
            'interaction_model = "proximity_dialogue"',
        ),
        encoding="utf-8",
    )
    replacement_second_sha = hashlib.sha256(second_path.read_bytes()).hexdigest()
    index_path.write_text(
        index_path.read_text(encoding="utf-8").replace(
            original_second_sha,
            replacement_second_sha,
        ),
        encoding="utf-8",
    )
    context = _context(
        tmp_path,
        map_book_sha256=hashlib.sha256(index_path.read_bytes()).hexdigest(),
        soundtrack_sha256=soundtrack_sha,
        village=True,
    )

    with pytest.raises(ValueError, match="only the canonical social_hub and combat_field"):
        await resolve_scrolling_map_book(context)
    assert not map_book_contract_path(context.run_dir, context.tag).exists()


@pytest.mark.asyncio
async def test_map_book_v2_village_identity_requires_the_asset_opt_in(tmp_path: Path) -> None:
    _, soundtrack_sha = _write_soundtrack(tmp_path)
    _, map_book_sha = _write_map_book(tmp_path, map_version=2)
    context = _context(
        tmp_path,
        map_book_sha256=map_book_sha,
        soundtrack_sha256=soundtrack_sha,
        village=False,
    )

    with pytest.raises(ValueError, match=r"village identity.*asset opt-in"):
        await resolve_scrolling_map_book(context)
    assert not map_book_contract_path(context.run_dir, context.tag).exists()


@pytest.mark.asyncio
async def test_map_book_v2_rejects_profile_that_contradicts_static_geometry(
    tmp_path: Path,
) -> None:
    _, soundtrack_sha = _write_soundtrack(tmp_path)
    index_path, _ = _write_map_book(tmp_path, map_version=2)
    stage_path = tmp_path / "library/games/test-game/maps/stage-1-approach.toml"
    original_stage_sha = hashlib.sha256(stage_path.read_bytes()).hexdigest()
    _, replacement_stage_sha = _write_map(
        tmp_path,
        "stage-1-approach",
        ("first_theme", "second_theme"),
        map_version=2,
        profile_role="social_hub",
    )
    index_path.write_text(
        index_path.read_text(encoding="utf-8").replace(
            original_stage_sha,
            replacement_stage_sha,
        ),
        encoding="utf-8",
    )
    context = _context(
        tmp_path,
        map_book_sha256=hashlib.sha256(index_path.read_bytes()).hexdigest(),
        soundtrack_sha256=soundtrack_sha,
        village=True,
    )

    with pytest.raises(
        ValueError,
        match="stage-1-approach requires level_profile role combat_field, got social_hub",
    ):
        await resolve_scrolling_map_book(context)
    assert not map_book_contract_path(context.run_dir, context.tag).exists()


@pytest.mark.asyncio
async def test_map_book_resolve_rejects_missing_population_before_artifact_write(
    tmp_path: Path,
) -> None:
    _, soundtrack_sha = _write_soundtrack(tmp_path)
    _, map_book_sha = _write_map_book(tmp_path, map_version=2)
    _, game_sha = _write_game(tmp_path, with_population=False)
    context = _context(
        tmp_path,
        map_book_sha256=map_book_sha,
        soundtrack_sha256=soundtrack_sha,
        game_sha256=game_sha,
        village=True,
    )

    with pytest.raises(ValueError, match=r"before generation.*missing: stage-1-approach"):
        await resolve_scrolling_map_book(context)
    assert not map_book_contract_path(context.run_dir, context.tag).exists()


def test_scrolling_profile_gate_rejects_every_near_miss_capability_combination(
    tmp_path: Path,
) -> None:
    social_path, _ = _write_map(
        tmp_path,
        "village-hub",
        ("first_theme", "second_theme"),
        map_version=2,
    )
    combat_path, _ = _write_map(
        tmp_path,
        "stage-1-approach",
        ("first_theme", "second_theme"),
        map_version=2,
    )
    social_map = load_game_map(social_path)
    combat_map = load_game_map(combat_path)
    assert social_map.level_profile is not None
    assert combat_map.level_profile is not None
    social = social_map.level_profile.model_dump(mode="json")
    combat = combat_map.level_profile.model_dump(mode="json")
    map_book_module._validate_scrolling_level_profile(social)
    map_book_module._validate_scrolling_level_profile(combat)

    invalid_profiles: list[dict[str, Any]] = []
    social_scrolls_vertically = copy.deepcopy(social)
    social_scrolls_vertically["camera"]["scroll_axes"] = ["horizontal", "vertical"]
    invalid_profiles.append(social_scrolls_vertically)

    social_enables_combat = copy.deepcopy(social)
    social_enables_combat["mechanisms"].update(
        {
            "encounter_model": "continuous_population",
            "combat_model": "real_time_action",
            "loot_model": "defeat_drops",
            "interaction_model": "none",
        }
    )
    invalid_profiles.append(social_enables_combat)

    combat_lacks_vertical_camera = copy.deepcopy(combat)
    combat_lacks_vertical_camera["camera"]["scroll_axes"] = ["horizontal"]
    invalid_profiles.append(combat_lacks_vertical_camera)

    combat_lacks_ladder = copy.deepcopy(combat)
    combat_lacks_ladder["traversal"]["affordances"] = [
        "ground_move",
        "jump",
        "air_jump",
        "drop_through",
    ]
    invalid_profiles.append(combat_lacks_ladder)

    combat_enables_dialogue = copy.deepcopy(combat)
    combat_enables_dialogue["mechanisms"]["interaction_model"] = "proximity_dialogue"
    invalid_profiles.append(combat_enables_dialogue)

    for profile in invalid_profiles:
        with pytest.raises(ValueError, match="only the canonical social_hub and combat_field"):
            map_book_module._validate_scrolling_level_profile(profile)


async def test_map_book_resolve_rejects_unknown_soundtrack_track_id(tmp_path: Path) -> None:
    _, soundtrack_sha = _write_soundtrack(tmp_path)
    _, map_book_sha = _write_map_book(
        tmp_path,
        second_tracks=("first_theme", "missing_theme"),
    )
    context = _context(
        tmp_path,
        map_book_sha256=map_book_sha,
        soundtrack_sha256=soundtrack_sha,
    )
    with pytest.raises(ValueError, match="missing_theme"):
        await resolve_scrolling_map_book(context)


def test_map_book_binding_must_share_the_game_and_soundtrack_owner() -> None:
    with pytest.raises(ValueError, match="share game_id"):
        assert_map_book_matches_game_and_soundtrack(
            {
                "schema_version": 1,
                "kind": "game-map-book-binding-v1",
                "ref": "library/games/other-game/maps/index.toml",
                "source_sha256": "a" * 64,
            },
            {
                "schema_version": 1,
                "kind": "game-contract-binding-v1",
                "ref": "library/games/test-game/game.toml",
                "source_sha256": "b" * 64,
            },
            {
                "schema_version": 1,
                "kind": "game-soundtrack-binding-v1",
                "ref": "library/games/test-game/soundtrack.toml",
                "source_sha256": "c" * 64,
            },
        )


async def test_map_book_collection_rejects_a_tampered_resolved_contract(
    tmp_path: Path,
) -> None:
    _, soundtrack_sha = _write_soundtrack(tmp_path)
    _, map_book_sha = _write_map_book(tmp_path)
    context = _context(
        tmp_path,
        map_book_sha256=map_book_sha,
        soundtrack_sha256=soundtrack_sha,
    )
    await resolve_scrolling_map_book(context)
    soundtrack_manifest = _soundtrack_manifest(context)
    output = map_book_contract_path(context.run_dir, context.tag)
    raw = await asyncio.to_thread(output.read_bytes)
    await asyncio.to_thread(output.write_bytes, raw + b"\n")
    with pytest.raises(ValueError, match="missing, stale, or invalid"):
        collect_scrolling_map_book(
            context.run_dir,
            context.tag,
            soundtrack_manifest=soundtrack_manifest,
        )


@pytest.mark.parametrize("tamper", ["map_source", "game", "soundtrack", "track_ids"])
async def test_map_book_collection_rejects_tampered_provenance_lineage(
    tmp_path: Path,
    tamper: str,
) -> None:
    _, soundtrack_sha = _write_soundtrack(tmp_path)
    _, map_book_sha = _write_map_book(tmp_path)
    context = _context(
        tmp_path,
        map_book_sha256=map_book_sha,
        soundtrack_sha256=soundtrack_sha,
    )
    await resolve_scrolling_map_book(context)
    soundtrack_manifest = _soundtrack_manifest(context)
    output = map_book_contract_path(context.run_dir, context.tag)
    sidecar_path = Path(f"{output}.meta.json")
    sidecar = json.loads(await asyncio.to_thread(sidecar_path.read_text, encoding="utf-8"))
    identity = sidecar["params"]["map_book"]
    if tamper == "map_source":
        identity["map_sources"][0]["source_sha256"] = "0" * 64
    elif tamper == "game":
        identity["game_contract"]["source_sha256"] = "0" * 64
    elif tamper == "soundtrack":
        identity["soundtrack"]["canonical_sha256"] = "0" * 64
    else:
        identity["soundtrack"]["track_ids"] = ["other_one", "other_two"]
    await asyncio.to_thread(
        sidecar_path.write_text,
        json.dumps(sidecar),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"missing, stale, or invalid|lineage"):
        collect_scrolling_map_book(
            context.run_dir,
            context.tag,
            soundtrack_manifest=soundtrack_manifest,
        )


async def test_manifest_rejects_map_bundle_without_game_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    tag = "map-aware"
    for name, data in {
        f"music_{tag}_first_theme.mp3": b"ID3test",
        f"music_{tag}_first_theme.mp3.meta.json": b"{}",
        f"soundtrack_{tag}.json": b"{}",
        f"soundtrack_{tag}.json.meta.json": b"{}",
        f"map_book_{tag}.json": b"{}",
        f"map_book_{tag}.json.meta.json": b"{}",
    }.items():
        (run_dir / name).write_bytes(data)

    collected_soundtrack = CollectedSoundtrack(
        manifest={
            "schema_version": 2,
            "kind": "game-soundtrack-manifest-v2",
            "game_id": "test-game",
            "revision": 1,
            "source": {
                "path": f"soundtrack_{tag}.json",
                "provenance_path": f"soundtrack_{tag}.json.meta.json",
                "source_sha256": "a" * 64,
                "canonical_sha256": "b" * 64,
            },
            "playback": {
                "selection": "shuffle",
                "no_immediate_repeat": True,
            },
            "tracks": [
                {"track_id": "first_theme"},
                {"track_id": "second_theme"},
            ],
        },
        artifact_paths=(
            f"soundtrack_{tag}.json",
            f"soundtrack_{tag}.json.meta.json",
            f"music_{tag}_first_theme.mp3",
            f"music_{tag}_first_theme.mp3.meta.json",
        ),
        default_music={
            "path": f"music_{tag}_first_theme.mp3",
            "provenance_path": f"music_{tag}_first_theme.mp3.meta.json",
            "source": "per-run",
            "rights_status": "unreviewed",
        },
    )
    collected_map_book = CollectedMapBook(
        manifest={
            "schema_version": 2,
            "kind": MAP_BOOK_MANIFEST_KIND,
            "game_id": "test-game",
            "revision": 1,
            "entry_map_id": "entry-map",
            "source": {
                "path": f"map_book_{tag}.json",
                "provenance_path": f"map_book_{tag}.json.meta.json",
                "source_sha256": "c" * 64,
                "canonical_sha256": "d" * 64,
            },
            "soundtrack": {
                "source_sha256": "a" * 64,
                "canonical_sha256": "b" * 64,
            },
            "maps": [
                {
                    "map_id": "entry-map",
                    "soundtrack_track_ids": ["first_theme", "second_theme"],
                },
                {
                    "map_id": "second-map",
                    "soundtrack_track_ids": ["first_theme", "second_theme"],
                },
            ],
        },
        artifact_paths=(
            f"map_book_{tag}.json",
            f"map_book_{tag}.json.meta.json",
        ),
    )

    monkeypatch.setattr(
        manifest_module,
        "collect_scrolling_soundtrack",
        lambda _run_dir, _tag: collected_soundtrack,
    )

    def collect_map_book(
        _run_dir: Path,
        _tag: str,
        *,
        soundtrack_manifest: dict[str, object],
    ) -> CollectedMapBook:
        assert soundtrack_manifest["schema_version"] == 2
        assert soundtrack_manifest["kind"] == "game-soundtrack-manifest-v2"
        return collected_map_book

    monkeypatch.setattr(
        manifest_module,
        "collect_scrolling_map_book",
        collect_map_book,
    )
    monkeypatch.setattr(
        manifest_module,
        "_collect_runtime_assets",
        lambda _run_dir, value_tag, *_args: (
            [],
            {
                "path": f"world_spec_{value_tag}.json",
                "provenancePath": f"world_spec_{value_tag}.json.meta.json",
            },
        ),
    )

    with pytest.raises(ValueError, match="requires a game contract"):
        await write_scrolling_preview_manifest(
            run_dir=run_dir,
            tag=tag,
            transparency_mode=TransparencyMode.CHROMA,
            soundtrack=True,
            map_book=True,
        )
