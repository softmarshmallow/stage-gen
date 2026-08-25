from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
from pathlib import Path

import pytest

from stage_gen.capabilities import CapabilityArtifactResult
from stage_gen.interfaces.cli import main
from stage_gen.recipes.base import StageContext

_GAME_ID = "whimsical-storybook-fantasy"
_CANONICAL_GAME_DIRECTORY = Path(__file__).resolve().parents[2] / "library/games" / _GAME_ID


def _copy_canonical_game(root: Path) -> Path:
    destination = root / "library/games" / _GAME_ID
    shutil.copytree(_CANONICAL_GAME_DIRECTORY, destination)
    return destination


class _GameLibraryRuntime:
    def __init__(self) -> None:
        self.game_library_roots: list[Path | None] = []

    async def run_recipe_stage(
        self, recipe_id: str, stage_name: str, context: StageContext
    ) -> tuple[str, ...]:
        assert recipe_id == "scrolling-preview"
        self.game_library_roots.append(context.config.game_library_root)
        artifact = context.run_dir / f"{stage_name}.txt"
        artifact.write_text(stage_name, encoding="utf-8")
        return (str(artifact),)

    async def generate_image(self, **_kwargs: object) -> CapabilityArtifactResult:
        raise NotImplementedError

    async def remove_background(self, **_kwargs: object) -> CapabilityArtifactResult:
        raise NotImplementedError

    async def generate_music(self, **_kwargs: object) -> CapabilityArtifactResult:
        raise NotImplementedError


@pytest.mark.parametrize(
    ("command", "relative_source", "expected_kind", "expected_schema_version"),
    [
        ("game", "game.toml", "resolved-game-contract-v1", 1),
        ("soundtrack", "soundtrack.toml", "resolved-game-soundtrack-v1", 1),
        ("map", "maps/stage-1-approach.toml", "resolved-game-map-v2", 2),
        ("map-book", "maps/index.toml", "resolved-game-map-book-v2", 2),
    ],
)
def test_game_library_cli_validates_and_digests_canonical_current_sources(
    tmp_path: Path,
    command: str,
    relative_source: str,
    expected_kind: str,
    expected_schema_version: int,
) -> None:
    game_directory = _copy_canonical_game(tmp_path)
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
        assert report["map_ids"] == [
            "village-hub",
            "stage-1-approach",
            "stage-2-gauntlet",
            "stage-3-spires",
        ]

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


def test_generate_cli_injects_the_explicit_game_library_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline")
    monkeypatch.setenv("OUT_DIR", str(tmp_path / "out"))
    runtime = _GameLibraryRuntime()

    assert (
        main(
            [
                "generate",
                "--game-library-root",
                str(tmp_path),
                "--transparency",
                "chroma",
                "original quiet ruins",
            ],
            runtime=runtime,
        )
        == 0
    )
    assert runtime.game_library_roots
    assert set(runtime.game_library_roots) == {tmp_path}


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


@pytest.mark.parametrize("action", ["validate", "digest"])
def test_map_book_cli_rejects_a_stale_locked_map(tmp_path: Path, action: str) -> None:
    game_directory = _copy_canonical_game(tmp_path)
    source = game_directory / "maps/index.toml"
    changed_map = game_directory / "maps/stage-2-gauntlet.toml"
    changed_map.write_text(
        changed_map.read_text(encoding="utf-8").replace("The Gauntlet", "Changed Gauntlet"),
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
    assert "source_sha256 mismatch for map_id stage-2-gauntlet" in errors.getvalue()


@pytest.mark.parametrize(
    ("command", "relative_source"),
    [
        ("game", "game.toml"),
        ("soundtrack", "soundtrack.toml"),
        ("map", "maps/stage-1-approach.toml"),
        ("map-book", "maps/index.toml"),
    ],
)
def test_game_library_cli_rejects_symlinked_sources(
    tmp_path: Path,
    command: str,
    relative_source: str,
) -> None:
    external_game_directory = _copy_canonical_game(tmp_path / "external")
    external_source = external_game_directory / relative_source
    workspace = tmp_path / "workspace"
    source = workspace / "library/games" / _GAME_ID / relative_source
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
    assert "must not traverse a symlink" in errors.getvalue()


def test_character_profile_cli_rejects_a_symlinked_source(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    profile_id = "mira-vale-cartographer"
    external_profile = repository / f"library/characters/{profile_id}/profile.toml"
    workspace = tmp_path / "workspace"
    source = workspace / f"library/characters/{profile_id}/profile.toml"
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
                "--character-library-root",
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
        ("game", "library/games/../game.toml", "--game-library-root"),
        ("soundtrack", "library/games/../soundtrack.toml", "--game-library-root"),
        ("map", "library/games/../maps/entry-map.toml", "--game-library-root"),
        ("map-book", "library/games/../maps/index.toml", "--game-library-root"),
        (
            "character-profile",
            "library/characters/../profile.toml",
            "--character-library-root",
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
