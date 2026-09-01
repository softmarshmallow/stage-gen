from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path

import pytest

from stage_gen.interfaces.cli import main

_GAME_ID = "test-game"


def _game_source() -> str:
    return """schema_version = 3
kind = "game-contract-v3"
game_id = "test-game"
revision = 1
display_name = "Test Game"

[camera]
projection = "side_view_2d"

[style]
keywords = ["hand-painted gouache", "warm dusk palette", "soft diffuse light"]
avoid = ["3D rendering"]

[proportion]
heads_tall = 2.0

[cast.player]
body_kind = "human"

[cast.resident]
body_kind_default = "human"

[rights]
status = "unreviewed"
"""


def _soundtrack_source() -> str:
    return """schema_version = 1
kind = "game-soundtrack-v1"
game_id = "test-game"
revision = 1

[playback]
selection = "shuffle"
no_immediate_repeat = true

[[tracks]]
track_id = "field_day"
display_name = "Field Day"
creative_brief = "An original instrumental for a bright field."

[tracks.generation]
intent = "generate"
instrumental = true
seamless_loop = true
target_duration_seconds = 90

[[tracks]]
track_id = "field_night"
display_name = "Field Night"
creative_brief = "An original instrumental for a quiet field."

[tracks.generation]
intent = "generate"
instrumental = true
seamless_loop = true
target_duration_seconds = 90
"""


def _map_source(map_id: str) -> str:
    return f'''schema_version = 2
kind = "game-map-v2"
game_id = "test-game"
map_id = "{map_id}"
revision = 1
display_name = "Test Map"
soundtrack_track_ids = ["field_day", "field_night"]

[level_profile]
schema_version = 1
kind = "level-profile-v1"
role = "combat_field"

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
encounter_model = "continuous_population"
combat_model = "real_time_action"
loot_model = "defeat_drops"
transition_model = "bidirectional_portals"
interaction_model = "none"
'''


def _write_component_library(root: Path) -> Path:
    game = root / "library" / "games" / _GAME_ID
    maps = game / "maps"
    maps.mkdir(parents=True)
    (game / "game.toml").write_text(_game_source(), encoding="utf-8")
    (game / "soundtrack.toml").write_text(_soundtrack_source(), encoding="utf-8")
    entries: list[tuple[str, str]] = []
    for map_id in ("field-one", "field-two"):
        source = maps / f"{map_id}.toml"
        source.write_text(_map_source(map_id), encoding="utf-8")
        entries.append((map_id, hashlib.sha256(source.read_bytes()).hexdigest()))
    rows = "\n".join(
        f'''[[maps]]
map_id = "{map_id}"
source_sha256 = "{source_sha256}"
'''
        for map_id, source_sha256 in entries
    )
    (maps / "index.toml").write_text(
        f"""schema_version = 1
kind = "game-map-book-v1"
game_id = "test-game"
revision = 1
entry_map_id = "field-one"

{rows}""",
        encoding="utf-8",
    )
    return game


@pytest.mark.parametrize(
    ("command", "relative_source", "expected_kind", "expected_schema_version"),
    [
        ("soundtrack", "soundtrack.toml", "resolved-game-soundtrack-v1", 1),
        ("map", "maps/field-one.toml", "resolved-game-map-v2", 2),
        ("map-book", "maps/index.toml", "resolved-game-map-book-v2", 2),
    ],
)
def test_registered_component_cli_surfaces_validate_and_digest_isolated_sources(
    tmp_path: Path,
    command: str,
    relative_source: str,
    expected_kind: str,
    expected_schema_version: int,
) -> None:
    game_directory = _write_component_library(tmp_path)
    source = game_directory / relative_source
    expected_source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()

    validate_output = io.StringIO()
    assert (
        main(
            [
                command,
                "validate",
                "--input",
                str(source),
                "--game-library-root",
                str(tmp_path),
            ],
            stdout=validate_output,
        )
        == 0
    )
    report = json.loads(validate_output.getvalue())
    assert report["valid"] is True
    assert report["kind"] == expected_kind
    assert report["schema_version"] == expected_schema_version
    assert report["game_id"] == _GAME_ID
    assert report["source_sha256"] == expected_source_sha256
    if command == "map":
        assert report["level_profile"]["role"] == "combat_field"
    elif command == "map-book":
        assert report["map_ids"] == ["field-one", "field-two"]

    digest_output = io.StringIO()
    assert (
        main(
            [
                command,
                "digest",
                "--input",
                str(source),
                "--game-library-root",
                str(tmp_path),
            ],
            stdout=digest_output,
        )
        == 0
    )
    assert digest_output.getvalue() == f"{expected_source_sha256}\n"


@pytest.mark.parametrize("action", ["validate", "digest"])
def test_map_book_cli_rejects_a_stale_locked_map(tmp_path: Path, action: str) -> None:
    game_directory = _write_component_library(tmp_path)
    source = game_directory / "maps/index.toml"
    changed_map = game_directory / "maps/field-two.toml"
    changed_map.write_text(
        changed_map.read_text(encoding="utf-8").replace("Test Map", "Changed Map"),
        encoding="utf-8",
    )
    errors = io.StringIO()

    assert (
        main(
            [
                "map-book",
                action,
                "--input",
                str(source),
                "--game-library-root",
                str(tmp_path),
            ],
            stderr=errors,
        )
        == 1
    )
    assert "source_sha256 mismatch for map_id field-two" in errors.getvalue()


@pytest.mark.parametrize(
    ("command", "relative_source"),
    [
        ("soundtrack", "soundtrack.toml"),
        ("map", "maps/field-one.toml"),
        ("map-book", "maps/index.toml"),
    ],
)
def test_registered_component_cli_surfaces_reject_symlinked_sources(
    tmp_path: Path,
    command: str,
    relative_source: str,
) -> None:
    external_game_directory = _write_component_library(tmp_path / "external")
    external_source = external_game_directory / relative_source
    workspace = tmp_path / "workspace"
    source = workspace / "library" / "games" / _GAME_ID / relative_source
    source.parent.mkdir(parents=True)
    source.symlink_to(external_source)
    errors = io.StringIO()

    assert (
        main(
            [
                command,
                "validate",
                "--input",
                str(source),
                "--game-library-root",
                str(workspace),
            ],
            stderr=errors,
        )
        == 1
    )
    assert "symlink" in errors.getvalue()


def test_map_cli_rejects_the_previous_game_map_schema(tmp_path: Path) -> None:
    source = tmp_path / "library/games/test-game/maps/entry-map.toml"
    source.parent.mkdir(parents=True)
    source.write_text(
        """schema_version = 1
kind = "game-map-v1"
game_id = "test-game"
map_id = "entry-map"
revision = 1
display_name = "Entry Map"
soundtrack_track_ids = ["first_theme", "second_theme"]
""",
        encoding="utf-8",
    )
    errors = io.StringIO()

    assert (
        main(
            [
                "map",
                "validate",
                "--input",
                str(source),
                "--game-library-root",
                str(tmp_path),
            ],
            stderr=errors,
        )
        == 1
    )
    assert "invalid game map contract" in errors.getvalue()


def test_character_profile_cli_rejects_a_symlinked_source(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    external_profile = repository / "library/games/larkfield/characters/nao.toml"
    workspace = tmp_path / "workspace"
    source = workspace / "character.toml"
    source.parent.mkdir(parents=True)
    source.symlink_to(external_profile)
    errors = io.StringIO()

    assert (
        main(
            [
                "character-profile",
                "validate",
                "--input",
                str(source),
                "--package-root",
                str(workspace),
            ],
            stderr=errors,
        )
        == 1
    )
    assert "must not traverse a symlink" in errors.getvalue()


@pytest.mark.parametrize(
    ("command", "relative_source", "root_option"),
    [
        ("soundtrack", "library/games/../soundtrack.toml", "--game-library-root"),
        ("map", "library/games/../maps/entry-map.toml", "--game-library-root"),
        ("map-book", "library/games/../maps/index.toml", "--game-library-root"),
        (
            "character-profile",
            "library/games/../profile.toml",
            "--package-root",
        ),
    ],
)
def test_authored_library_cli_rejects_parent_segments_before_reading(
    tmp_path: Path,
    command: str,
    relative_source: str,
    root_option: str,
) -> None:
    workspace = tmp_path / "workspace"
    source = workspace / relative_source
    escaped_target = Path(os.path.normpath(source))
    escaped_target.parent.mkdir(parents=True, exist_ok=True)
    escaped_target.write_text("must not be read", encoding="utf-8")
    errors = io.StringIO()

    assert (
        main(
            [command, "validate", "--input", str(source), root_option, str(workspace)],
            stderr=errors,
        )
        == 1
    )
    assert "dot or parent" in errors.getvalue()


def test_map_cli_rejects_non_game_owned_source_path(tmp_path: Path) -> None:
    source = tmp_path / "maps/entry-map.toml"
    source.parent.mkdir()
    source.write_text("not relevant", encoding="utf-8")
    errors = io.StringIO()

    assert (
        main(
            [
                "map",
                "validate",
                "--input",
                str(source),
                "--game-library-root",
                str(tmp_path),
            ],
            stderr=errors,
        )
        == 1
    )
    assert "ROOT/library/games/<game_id>/maps/<map_id>.toml" in errors.getvalue()
