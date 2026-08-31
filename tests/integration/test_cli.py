from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from io import StringIO
from pathlib import Path

import pytest

from stage_gen.interfaces.cli import build_parser, main


def test_cli_offline_surfaces_require_a_prepared_package() -> None:
    help_text = " ".join(build_parser().format_help().split())
    assert "Prepared game generation requires a directory or ZIP containing game.toml." in help_text
    assert "bare prompt" not in help_text


def test_prepared_package_cli_validates_and_digests_directory_and_zip(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    package = repository / "library/games/bellweather"
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
    assert report["file_count"] == sum(1 for path in package.rglob("*") if path.is_file())

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
            if source.is_file():
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

    plan_output = StringIO()
    assert main(["package", "plan", "--input", str(package)], stdout=plan_output) == 0
    plan = json.loads(plan_output.getvalue())
    assert len(plan["graph"]["nodes"]) == 221
    assert plan["projection"]["operation_counts"] == {
        "local": 104,
        "image_generation": 93,
        "structured_generation": 21,
        "music_generation": 3,
    }


def test_generate_cli_runs_the_prepared_graph_without_provider_calls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("_STAGE_GEN_DISABLE_DOTENV", "1")
    repository = Path(__file__).resolve().parents[2]
    package = repository / "library/games/bellweather"
    output = StringIO()

    assert (
        main(
            [
                "generate",
                "--input",
                str(package),
                "--dry-run",
                "--output",
                str(tmp_path / "run"),
                "--cache-dir",
                str(tmp_path / "cache"),
                "--invocation-id",
                "integration-test",
            ],
            stdout=output,
        )
        == 0
    )
    report = json.loads(output.getvalue())
    assert report["ok"] is True
    assert report["node_count"] == 221
    assert report["provider_operation_counts"] == {
        "image_generation": 93,
        "structured_generation": 21,
        "music_generation": 3,
    }
    assert (tmp_path / "run/execution-plan.json").is_file()
    assert (tmp_path / "run/execution-trace.jsonl").is_file()

    view_output = StringIO()
    assert main(["export-view", "--run", str(tmp_path / "run")], stdout=view_output) == 0
    view_report = json.loads(view_output.getvalue())
    assert view_report["run_state"] == "succeeded"
    assert view_report["nodes"] == 221
    assert view_report["states"]["succeeded"] == 221
    view_path = tmp_path / "run/execution-view.json"
    assert view_path.is_file()
    view_document = json.loads(view_path.read_text(encoding="utf-8"))
    assert view_document["kind"] == "sideview-platformer-execution-view-v1"
    assert view_document["schema_version"] == 3
    assert str(tmp_path) not in view_path.read_text(encoding="utf-8")

    error = StringIO()
    assert main(["export-view", "--run", str(tmp_path / "no-such-run")], stderr=error) == 1
    assert "no execution-plan.json" in error.getvalue()

    error = StringIO()
    assert main(["generate", "--input", str(package)], stderr=error) == 1
    assert "generate requires --output" in error.getvalue()

    error = StringIO()
    assert (
        main(
            [
                "generate",
                "--input",
                str(package),
                "--output",
                str(tmp_path / "live-run"),
            ],
            stderr=error,
        )
        == 1
    )
    assert "requires --checkpoint world, content, or integration" in error.getvalue()


def test_character_profile_cli_validate_digest_help_and_errors(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    repository = Path(__file__).resolve().parents[2]
    package = repository / "library/games/larkfield"
    profile = package / "character.toml"
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
            "ref": "character.toml",
            "schema_version": 1,
            "source_sha256": validated["source_sha256"],
        },
        "canonical_bytes": validated["canonical_bytes"],
        "canonical_sha256": validated["canonical_sha256"],
        "kind": "resolved-character-profile-v1",
        "profile_id": "nao-kirishima",
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
    soundtrack = tmp_path / "library/games/test-game/soundtrack.toml"
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
        "ref": "library/games/test-game/soundtrack.toml",
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
    soundtrack = tmp_path / "library/soundtracks/test-game/soundtrack.toml"
    soundtrack.parent.mkdir(parents=True)
    soundtrack.write_text(_soundtrack_toml(), encoding="utf-8")
    error_output = StringIO()

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
            stderr=error_output,
        )
        == 1
    )
    assert (
        "game soundtrack input must equal ROOT/library/games/<game_id>/soundtrack.toml"
    ) in error_output.getvalue()


def test_generate_help_exposes_package_dry_run_controls(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        build_parser().parse_args(["generate", "--help"])
    help_text = capsys.readouterr().out

    assert exit_info.value.code == 0
    assert "--dry-run" in help_text
    assert "--checkpoint {world,content,integration}" in help_text
    assert "--artifact-root ARTIFACT_ROOTS" in help_text
    assert "--failure-node FAILURE_NODE" in help_text
    assert "--force-stage" not in help_text


def test_doctor_consumes_cwd_dotenv_without_exposing_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in (
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "FAL_KEY",
        "_STAGE_GEN_DISABLE_DOTENV",
    ):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=doctor-openai\nOPENROUTER_API_KEY=doctor-openrouter\nFAL_KEY=doctor-fal\n",
        encoding="utf-8",
    )
    output = StringIO()

    assert main(["doctor", "--json"], stdout=output) == 0

    rendered = output.getvalue()
    report = json.loads(rendered)
    assert report["ok"] is True
    assert report["capabilities"] == {"openai": True, "openrouter": True, "fal": True}
    assert "doctor-openai" not in rendered
    assert "doctor-openrouter" not in rendered
    assert "doctor-fal" not in rendered


def test_scenario_cli_proves_the_shipped_scenario_without_touching_a_provider() -> None:
    repository = Path(__file__).resolve().parents[2]
    package = repository / "library/games/larkfield"
    output = StringIO()

    assert main(["scenario", "check", "--input", str(package)], stdout=output) == 0

    report = json.loads(output.getvalue())
    assert report["admitted"] is True
    assert report["scenario_id"] == "last_class"
    assert report["endings"] == {
        "listened": ["arrival", "listening", "recording", "ending_quiet"],
        "talked": ["arrival", "asking", "recording", "ending_talked"],
    }


def test_scenario_cli_refuses_a_script_that_drifted_from_its_digest(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    repository = Path(__file__).resolve().parents[2]
    package = tmp_path / "larkfield"
    shutil.copytree(repository / "library/games/larkfield", package)
    script = package / "scenarios/last_class.scenario"
    script.write_text(script.read_text(encoding="utf-8") + '\n"Extra."\n', encoding="utf-8")

    assert main(["scenario", "check", "--input", str(package)], stdout=StringIO()) != 0
    assert "does not match its authored digest" in capsys.readouterr().err


def test_scenario_cli_repairs_the_digest_but_still_proves_the_narrative(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Repairing a digest must not be a way to bless prose the proof would refuse."""

    repository = Path(__file__).resolve().parents[2]
    package = tmp_path / "larkfield"
    shutil.copytree(repository / "library/games/larkfield", package)
    script = package / "scenarios/last_class.scenario"
    original = script.read_text(encoding="utf-8")

    script.write_text(original + "\n\nlabel orphan:\n    end talked\n", encoding="utf-8")
    assert (
        main(
            ["scenario", "check", "--input", str(package), "--write-digest"],
            stdout=StringIO(),
        )
        != 0
    )
    assert "labels no path reaches: orphan" in capsys.readouterr().err

    script.write_text(original.replace("hot dust", "dust"), encoding="utf-8")
    output = StringIO()
    assert (
        main(["scenario", "check", "--input", str(package), "--write-digest"], stdout=output) == 0
    )
    repaired = json.loads(output.getvalue())
    assert repaired["admitted"] is True
    assert repaired["script_sha256"] in (package / "scenario.toml").read_text(encoding="utf-8")
