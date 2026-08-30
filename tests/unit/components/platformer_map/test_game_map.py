from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from stage_gen.components.platformer_map import (
    GameMap,
    GameMapBook,
    GameMapLoadError,
    ResolvedGameMapBookDocument,
    canonical_game_map_json,
    load_game_map_book_bytes,
    load_game_map_bytes,
    resolve_game_map_book_binding,
    resolve_game_map_source,
)


def _map_toml(
    map_id: str = "stage-1-approach",
    *,
    game_id: str = "test-game",
    tracks: tuple[str, ...] = ("sunpetal_road", "highwhim_spires"),
) -> str:
    return _map_v2_toml(
        map_id,
        game_id=game_id,
        tracks=tracks,
        role="combat_field",
        encounter_model="continuous_population",
        interaction_model="none",
    )


def _previous_map_toml(map_id: str = "stage-1-approach") -> str:
    return f'''schema_version = 1
kind = "game-map-v1"
game_id = "test-game"
map_id = "{map_id}"
revision = 1
display_name = "Previous Map"
soundtrack_track_ids = ["sunpetal_road", "highwhim_spires"]
'''


def _level_profile(
    *,
    role: str = "combat_field",
    encounter_model: str = "continuous_population",
    interaction_model: str = "none",
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "level-profile-v1",
        "role": role,
        "view": {"projection": "orthographic_2d", "viewpoint": "side_on"},
        "camera": {
            "tracking_mode": "player_follow",
            "framing_mode": "dead_zone",
            "scroll_axes": ["horizontal"],
        },
        "traversal": {
            "ground_model": "heightfield",
            "platform_model": "one_way",
            "affordances": ["ground_move", "jump", "air_jump", "drop_through"],
        },
        "mechanisms": {
            "encounter_model": encounter_model,
            "combat_model": "real_time_action" if role == "combat_field" else "none",
            "loot_model": "defeat_drops" if role == "combat_field" else "none",
            "transition_model": "bidirectional_portals",
            "interaction_model": interaction_model,
        },
    }


def _map_v2_toml(
    map_id: str,
    *,
    game_id: str = "test-game",
    tracks: tuple[str, ...] = ("sunpetal_road", "highwhim_spires"),
    role: str = "combat_field",
    encounter_model: str = "continuous_population",
    interaction_model: str = "none",
) -> str:
    rendered_tracks = ", ".join(json.dumps(track) for track in tracks)
    combat_model = "real_time_action" if role == "combat_field" else "none"
    loot_model = "defeat_drops" if role == "combat_field" else "none"
    return f'''schema_version = 2
kind = "game-map-v2"
game_id = "{game_id}"
map_id = "{map_id}"
revision = 2
display_name = "Test Map"
soundtrack_track_ids = [{rendered_tracks}]

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
scroll_axes = ["horizontal"]

[level_profile.traversal]
ground_model = "heightfield"
platform_model = "one_way"
affordances = ["ground_move", "jump", "air_jump", "drop_through"]

[level_profile.mechanisms]
encounter_model = "{encounter_model}"
combat_model = "{combat_model}"
loot_model = "{loot_model}"
transition_model = "bidirectional_portals"
interaction_model = "{interaction_model}"
'''


def _write_map(root: Path, map_id: str, *, contents: str | None = None) -> tuple[Path, str]:
    source = root / f"library/games/test-game/maps/{map_id}.toml"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(contents or _map_toml(map_id), encoding="utf-8")
    return source, hashlib.sha256(source.read_bytes()).hexdigest()


def _write_book(root: Path, entries: list[tuple[str, str]]) -> tuple[Path, str]:
    source = root / "library/games/test-game/maps/index.toml"
    source.parent.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(
        f'''[[maps]]
map_id = "{map_id}"
source_sha256 = "{source_sha256}"
'''
        for map_id, source_sha256 in entries
    )
    source.write_text(
        f'''schema_version = 1
kind = "game-map-book-v1"
game_id = "test-game"
revision = 1
entry_map_id = "{entries[0][0]}"

{rows}''',
        encoding="utf-8",
    )
    return source, hashlib.sha256(source.read_bytes()).hexdigest()


def _binding(source_sha256: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "game-map-book-binding-v1",
        "ref": "library/games/test-game/maps/index.toml",
        "source_sha256": source_sha256,
    }


def test_map_is_strict_and_canonicalizes_only_the_shuffle_pool() -> None:
    game_map = GameMap.model_validate(
        {
            "schema_version": 2,
            "kind": "game-map-v2",
            "game_id": "test-game",
            "map_id": "stage-1-approach",
            "revision": 1,
            "display_name": "The Approach",
            "soundtrack_track_ids": ["sunpetal_road", "highwhim_spires"],
            "level_profile": _level_profile(),
        }
    )
    assert game_map.soundtrack_track_ids == ["highwhim_spires", "sunpetal_road"]
    assert json.loads(canonical_game_map_json(game_map))["map_id"] == "stage-1-approach"

    for invalid in (
        {**game_map.model_dump(), "map_id": "StageOne"},
        {**game_map.model_dump(), "display_name": " padded "},
        {**game_map.model_dump(), "display_name": "x" * 161},
        {**game_map.model_dump(), "revision": 9_007_199_254_740_992},
        {**game_map.model_dump(), "soundtrack_track_ids": ["one_track"]},
        {
            **game_map.model_dump(),
            "soundtrack_track_ids": ["a" * 65, "two_track"],
        },
        {
            **game_map.model_dump(),
            "soundtrack_track_ids": ["same_track", "same_track"],
        },
        {**game_map.model_dump(), "terrain": "rolling"},
        {**game_map.model_dump(), "soundtrackTrackIds": ["one_track", "two_track"]},
    ):
        with pytest.raises(ValidationError):
            GameMap.model_validate(invalid)


def test_current_game_map_requires_a_complete_canonical_level_profile() -> None:
    payload = {
        "schema_version": 2,
        "kind": "game-map-v2",
        "game_id": "test-game",
        "map_id": "stage-1-approach",
        "revision": 2,
        "display_name": "The Approach",
        "soundtrack_track_ids": ["sunpetal_road", "highwhim_spires"],
        "level_profile": _level_profile(),
    }
    game_map = GameMap.model_validate(payload)
    canonical = json.loads(canonical_game_map_json(game_map))
    assert canonical["level_profile"] == _level_profile()
    assert canonical["level_profile"]["mechanisms"]["interaction_model"] == "none"

    with pytest.raises(ValidationError, match="level_profile"):
        GameMap.model_validate(
            {key: value for key, value in payload.items() if key != "level_profile"}
        )
    with pytest.raises(ValidationError):
        GameMap.model_validate({**payload, "schema_version": 1, "kind": "game-map-v1"})

    invalid_order: Any = copy.deepcopy(payload)
    invalid_order["level_profile"]["camera"]["scroll_axes"] = ["vertical", "horizontal"]
    with pytest.raises(ValidationError, match="canonical horizontal, vertical order"):
        GameMap.model_validate(invalid_order)

    invalid_air_jump: Any = copy.deepcopy(payload)
    invalid_air_jump["level_profile"]["traversal"]["affordances"] = [
        "ground_move",
        "air_jump",
    ]
    with pytest.raises(ValidationError, match="air_jump requires jump"):
        GameMap.model_validate(invalid_air_jump)

    invalid_platform: Any = copy.deepcopy(payload)
    invalid_platform["level_profile"]["traversal"]["platform_model"] = "none"
    with pytest.raises(ValidationError, match="require platform_model='one_way'"):
        GameMap.model_validate(invalid_platform)

    invalid_loot: Any = copy.deepcopy(payload)
    invalid_loot["level_profile"]["mechanisms"]["combat_model"] = "none"
    with pytest.raises(ValidationError, match=r"defeat_drops.*requires.*real_time_action"):
        GameMap.model_validate(invalid_loot)


def test_map_book_preserves_authored_order_and_requires_entry_first() -> None:
    book = GameMapBook.model_validate(
        {
            "schema_version": 1,
            "kind": "game-map-book-v1",
            "game_id": "test-game",
            "revision": 1,
            "entry_map_id": "village-hub",
            "maps": [
                {"map_id": "village-hub", "source_sha256": "a" * 64},
                {"map_id": "stage-1-approach", "source_sha256": "b" * 64},
            ],
        }
    )
    assert book.map_ids == ("village-hub", "stage-1-approach")

    for invalid_maps, entry in (
        (book.maps, "stage-1-approach"),
        ([book.maps[0], book.maps[0]], "village-hub"),
    ):
        with pytest.raises(ValidationError):
            GameMapBook.model_validate(
                {**book.model_dump(), "entry_map_id": entry, "maps": invalid_maps}
            )
    with pytest.raises(ValidationError):
        GameMapBook.model_validate({**book.model_dump(), "revision": 9_007_199_254_740_992})


def test_strict_loaders_reject_native_time_and_duplicate_json_keys() -> None:
    with pytest.raises(GameMapLoadError, match="native date/time"):
        load_game_map_bytes(
            (_map_toml() + "published_at = 2026-08-24\n").encode(),
            source_suffix=".toml",
        )
    with pytest.raises(GameMapLoadError, match="duplicate JSON key"):
        load_game_map_book_bytes(b'{"schema_version":1,"schema_version":1}', source_suffix=".json")


def test_book_resolution_binds_index_and_every_fixed_map_source(tmp_path: Path) -> None:
    first, first_sha = _write_map(tmp_path, "village-hub")
    second, second_sha = _write_map(tmp_path, "stage-1-approach")
    book_path, book_sha = _write_book(
        tmp_path,
        [("village-hub", first_sha), ("stage-1-approach", second_sha)],
    )

    resolved = resolve_game_map_book_binding(_binding(book_sha), game_library_root=tmp_path)
    assert resolved.source_path == book_path
    assert resolved.document.map_ids == ("village-hub", "stage-1-approach")
    assert [item.source_path for item in resolved.maps] == [first, second]
    assert [item.source_sha256 for item in resolved.maps] == [first_sha, second_sha]
    assert len(resolved.source_provenance) == 3
    assert resolved.identity()["canonical_sha256"] == resolved.canonical_sha256


def test_book_resolution_uses_only_current_maps_and_resolved_document_identity(
    tmp_path: Path,
) -> None:
    _, first_sha = _write_map(
        tmp_path,
        "village-hub",
        contents=_map_v2_toml(
            "village-hub",
            role="social_hub",
            encounter_model="none",
            interaction_model="proximity_dialogue",
        ),
    )
    _, second_sha = _write_map(
        tmp_path,
        "stage-1-approach",
        contents=_map_v2_toml(
            "stage-1-approach",
            role="combat_field",
            encounter_model="continuous_population",
            interaction_model="none",
        ),
    )
    _, book_sha = _write_book(
        tmp_path,
        [("village-hub", first_sha), ("stage-1-approach", second_sha)],
    )
    resolved = resolve_game_map_book_binding(_binding(book_sha), game_library_root=tmp_path)
    assert resolved.document.schema_version == 2
    assert resolved.document.kind == "resolved-game-map-book-v2"
    assert resolved.identity()["schema_version"] == 2
    assert resolved.maps[0].identity()["level_profile"] == _level_profile(
        role="social_hub",
        encounter_model="none",
        interaction_model="proximity_dialogue",
    )

    previous_document = resolved.document.model_dump(mode="json")
    with pytest.raises(ValidationError):
        ResolvedGameMapBookDocument.model_validate(
            {
                **previous_document,
                "schema_version": 1,
                "kind": "resolved-game-map-book-v1",
            }
        )

    _, previous_sha = _write_map(
        tmp_path,
        "village-hub",
        contents=_previous_map_toml("village-hub"),
    )
    _, previous_book_sha = _write_book(
        tmp_path,
        [("village-hub", previous_sha), ("stage-1-approach", second_sha)],
    )
    with pytest.raises(ValueError, match="invalid game map contract"):
        resolve_game_map_book_binding(_binding(previous_book_sha), game_library_root=tmp_path)


def test_book_resolution_fails_closed_on_index_or_map_drift(tmp_path: Path) -> None:
    _, first_sha = _write_map(tmp_path, "village-hub")
    second, second_sha = _write_map(tmp_path, "stage-1-approach")
    _, book_sha = _write_book(
        tmp_path,
        [("village-hub", first_sha), ("stage-1-approach", second_sha)],
    )

    with pytest.raises(ValueError, match="game map book source_sha256 mismatch"):
        resolve_game_map_book_binding(_binding("0" * 64), game_library_root=tmp_path)

    second.write_text(_map_toml("stage-1-approach") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="stage-1-approach"):
        resolve_game_map_book_binding(_binding(book_sha), game_library_root=tmp_path)


def test_map_authoring_resolution_requires_fixed_path_and_matching_identity(
    tmp_path: Path,
) -> None:
    source, _ = _write_map(tmp_path, "stage-1-approach")
    resolved = resolve_game_map_source(source, game_library_root=tmp_path)
    assert resolved.game_map.map_id == "stage-1-approach"

    wrong = tmp_path / "library/games/test-game/maps/wrong-name.toml"
    wrong.write_text(_map_toml("stage-1-approach"), encoding="utf-8")
    with pytest.raises(ValueError, match="map_id must match"):
        resolve_game_map_source(wrong, game_library_root=tmp_path)

    outside = tmp_path / "maps/stage-1-approach.toml"
    outside.parent.mkdir()
    outside.write_text(_map_toml(), encoding="utf-8")
    with pytest.raises(ValueError, match="must equal"):
        resolve_game_map_source(outside, game_library_root=tmp_path)


def test_book_resolution_rejects_symlinked_map_source(tmp_path: Path) -> None:
    _, first_sha = _write_map(tmp_path, "village-hub")
    external = tmp_path / "external.toml"
    external.write_text(_map_toml("stage-1-approach"), encoding="utf-8")
    second = tmp_path / "library/games/test-game/maps/stage-1-approach.toml"
    second.symlink_to(external)
    _, book_sha = _write_book(
        tmp_path,
        [
            ("village-hub", first_sha),
            ("stage-1-approach", hashlib.sha256(external.read_bytes()).hexdigest()),
        ],
    )

    with pytest.raises(ValueError, match="symlink"):
        resolve_game_map_book_binding(_binding(book_sha), game_library_root=tmp_path)
