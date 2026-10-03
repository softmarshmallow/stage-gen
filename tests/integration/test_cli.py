from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from io import StringIO
from pathlib import Path

import pytest

from demo_game_collection.cli import build_parser, main


def test_cli_help_names_the_gnode_build_and_no_generation_of_its_own() -> None:
    help_text = " ".join(build_parser().format_help().split())
    assert "build with gnode from the game's own folder" in help_text
    for retired in ("generate", "export-view", "doctor", "models"):
        assert f"{{{retired}," not in help_text and f",{retired}," not in help_text
        assert f",{retired}}}" not in help_text


def test_prepared_package_cli_validates_and_digests_directory_and_zip(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    package = repository / "godot/games/bellweather/inputs/default"
    validate_output = StringIO()

    assert (
        main(
            ["package", "validate", "--input", str(package)],
            stdout=validate_output,
        )
        == 0
    )
    report = json.loads(validate_output.getvalue())
    assert report["valid"] is True
    assert report["game_id"] == "bellweather"
    assert report["file_count"] == sum(
        1 for path in package.rglob("*") if path.is_file() and path.name != ".gdignore"
    )

    digest_output = StringIO()
    assert (
        main(
            ["package", "digest", "--input", str(package)],
            stdout=digest_output,
        )
        == 0
    )
    assert digest_output.getvalue() == f"{report['closure_sha256']}\n"

    archive = tmp_path / "bellweather.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for source in sorted(package.rglob("*")):
            if source.is_file() and source.name != ".gdignore":
                output.write(source, Path("bellweather", source.relative_to(package)).as_posix())
    zip_output = StringIO()
    assert (
        main(
            ["package", "validate", "--input", str(archive)],
            stdout=zip_output,
        )
        == 0
    )
    assert json.loads(zip_output.getvalue())["closure_sha256"] == report["closure_sha256"]


def test_character_profile_cli_validate_digest_help_and_errors(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    repository = Path(__file__).resolve().parents[2]
    package = repository / "godot/games/the_grain/inputs"
    profile = package / "characters/ruth.toml"
    validate_output = StringIO()
    assert (
        main(
            [
                "character-profile",
                "validate",
                "--input",
                str(profile),
                "--package-root",
                str(package),
            ],
            stdout=validate_output,
        )
        == 0
    )
    validated = json.loads(validate_output.getvalue())
    assert validated == {
        "binding": {
            "kind": "character-profile-binding-v1",
            "ref": "characters/ruth.toml",
            "schema_version": 1,
            "source_sha256": validated["source_sha256"],
        },
        "canonical_bytes": validated["canonical_bytes"],
        "canonical_sha256": validated["canonical_sha256"],
        "kind": "resolved-character-profile-v1",
        "profile_id": "ruth-ellery",
        "resolution_version": "character-profile-library-resolution-v1",
        "revision": 1,
        "rights_status": "unreviewed",
        "schema_version": 1,
        "source_sha256": validated["source_sha256"],
        "valid": True,
    }
    digest_output = StringIO()
    assert (
        main(
            [
                "character-profile",
                "digest",
                "--input",
                str(profile),
                "--package-root",
                str(package),
            ],
            stdout=digest_output,
        )
        == 0
    )
    assert digest_output.getvalue() == f"{validated['source_sha256']}\n"

    with pytest.raises(SystemExit) as exit_info:
        build_parser().parse_args(["character-profile", "validate", "--help"])
    help_text = capsys.readouterr().out
    assert exit_info.value.code == 0
    assert "--input INPUT_PATH" in help_text
    assert "--package-root PACKAGE_ROOT" in help_text

    error_output = StringIO()
    outside = tmp_path / "profile.toml"
    outside.write_text("invalid", encoding="utf-8")
    assert (
        main(
            [
                "character-profile",
                "validate",
                "--input",
                str(outside),
                "--package-root",
                str(package),
            ],
            stderr=error_output,
        )
        == 1
    )
    assert "must be inside the package root" in error_output.getvalue()

    invalid_root = tmp_path / "workspace"
    invalid_profile = invalid_root / "broken.toml"
    invalid_profile.parent.mkdir(parents=True)
    invalid_profile.write_text(
        'schema_version = 1\nkind = "character-profile-v1"\nprofile_id = "broken"\n',
        encoding="utf-8",
    )
    invalid_output = StringIO()
    assert (
        main(
            [
                "character-profile",
                "validate",
                "--input",
                str(invalid_profile),
                "--package-root",
                str(invalid_root),
            ],
            stderr=invalid_output,
        )
        == 1
    )
    assert "invalid character profile contract" in invalid_output.getvalue()


def _soundtrack_toml() -> str:
    return """schema_version = 1
kind = "game-soundtrack-v1"
game_id = "test-game"
revision = 1

[playback]
selection = "shuffle"
no_immediate_repeat = true

[[tracks]]
track_id = "field_theme"
display_name = "Field Theme"
creative_brief = "An original optimistic instrumental for outdoor exploration."

[tracks.generation]
intent = "generate"
instrumental = true
seamless_loop = true
target_duration_seconds = 90

[[tracks]]
track_id = "village_evening"
display_name = "Village Evening"
creative_brief = "An original warm instrumental for a safe village at dusk."

[tracks.generation]
intent = "generate"
instrumental = true
seamless_loop = true
target_duration_seconds = 120
"""


def test_soundtrack_cli_validate_and_digest_use_the_game_library_binding(tmp_path: Path) -> None:
    soundtrack = tmp_path / "godot/games/test_game/inputs/soundtrack.toml"
    soundtrack.parent.mkdir(parents=True)
    soundtrack.write_text(_soundtrack_toml(), encoding="utf-8")
    expected_source_sha256 = hashlib.sha256(soundtrack.read_bytes()).hexdigest()

    validate_output = StringIO()
    assert (
        main(
            [
                "soundtrack",
                "validate",
                "--input",
                str(soundtrack),
                "--game-library-root",
                str(tmp_path),
            ],
            stdout=validate_output,
        )
        == 0
    )
    validated = json.loads(validate_output.getvalue())
    assert validated["valid"] is True
    assert validated["kind"] == "resolved-game-soundtrack-v1"
    assert validated["game_id"] == "test-game"
    assert validated["track_ids"] == ["field_theme", "village_evening"]
    assert validated["playback"] == {
        "selection": "shuffle",
        "no_immediate_repeat": True,
    }
    assert validated["source_sha256"] == expected_source_sha256
    assert validated["binding"] == {
        "schema_version": 1,
        "kind": "game-soundtrack-binding-v1",
        "ref": "godot/games/test_game/inputs/soundtrack.toml",
        "source_sha256": expected_source_sha256,
    }

    digest_output = StringIO()
    assert (
        main(
            [
                "soundtrack",
                "digest",
                "--input",
                str(soundtrack),
                "--game-library-root",
                str(tmp_path),
            ],
            stdout=digest_output,
        )
        == 0
    )
    assert digest_output.getvalue() == f"{expected_source_sha256}\n"


def test_soundtrack_cli_rejects_a_source_outside_the_game_owned_path(tmp_path: Path) -> None:
    soundtrack = tmp_path / "outside/soundtrack.toml"
    soundtrack.parent.mkdir(parents=True)
    soundtrack.write_text(_soundtrack_toml(), encoding="utf-8")
    (tmp_path / "game-inputs").mkdir()
    error_output = StringIO()

    assert (
        main(
            [
                "soundtrack",
                "validate",
                "--input",
                str(soundtrack),
                "--game-library-root",
                str(tmp_path / "game-inputs"),
            ],
            stderr=error_output,
        )
        == 1
    )
    assert "game soundtrack input must be inside game library root" in error_output.getvalue()


def test_scenario_cli_proves_the_shipped_scenario_without_touching_a_provider() -> None:
    repository = Path(__file__).resolve().parents[2]
    package = repository / "godot/games/the_grain/inputs"
    output = StringIO()

    assert main(["scenario", "check", "--input", str(package)], stdout=output) == 0

    report = json.loads(output.getvalue())
    # Admission covers the retained game's whole catalog, including every ending.
    assert report["game_id"] == "the_grain"
    scenarios = {entry["scenario_id"]: entry for entry in report["scenarios"]}
    assert set(scenarios) == {
        "e1_office",
        "e1_way_in",
        "e1_table",
        "e1_coffee",
        "e1_the_court",
        "e1_statements",
    }
    assert all(scenario["admitted"] for scenario in scenarios.values())
    assert all(scenario["endings"] for scenario in scenarios.values())
    way_in = scenarios["e1_way_in"]
    assert set(way_in["endings"]) == {"first_bell"}
    assert way_in["endings"]["first_bell"][0] == "the_service_door"
    assert way_in["endings"]["first_bell"][-1] == "the_first_bell"


def test_scenario_cli_refuses_a_script_that_drifted_from_its_digest(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    repository = Path(__file__).resolve().parents[2]
    package = tmp_path / "the_grain"
    shutil.copytree(repository / "godot/games/the_grain/inputs", package)
    script = package / "scenarios/e1_way_in.scenario"
    script.write_text(script.read_text(encoding="utf-8") + '\n"Extra."\n', encoding="utf-8")

    assert main(["scenario", "check", "--input", str(package)], stdout=StringIO()) != 0
    assert "does not match its authored digest" in capsys.readouterr().err


def test_scenario_cli_repairs_the_digest_but_still_proves_the_narrative(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Repairing a digest must not be a way to bless prose the proof would refuse."""

    repository = Path(__file__).resolve().parents[2]
    package = tmp_path / "the_grain"
    shutil.copytree(repository / "godot/games/the_grain/inputs", package)
    script = package / "scenarios/e1_way_in.scenario"
    original = script.read_text(encoding="utf-8")

    script.write_text(original + "\n\nlabel orphan:\n    end first_bell\n", encoding="utf-8")
    assert (
        main(
            ["scenario", "check", "--input", str(package), "--write-digest"],
            stdout=StringIO(),
        )
        != 0
    )
    assert "labels no path reaches: orphan" in capsys.readouterr().err

    script.write_text(
        original.replace("one clean note at a time", "one clear note at a time"), encoding="utf-8"
    )
    output = StringIO()
    assert (
        main(["scenario", "check", "--input", str(package), "--write-digest"], stdout=output) == 0
    )
    repaired = json.loads(output.getvalue())
    declarations = (package / "scenarios/e1_way_in.toml").read_text(encoding="utf-8")
    assert repaired["e1_way_in"] in declarations
