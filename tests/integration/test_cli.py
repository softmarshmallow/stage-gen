from __future__ import annotations

import hashlib
import json
import os
import zipfile
from io import StringIO
from pathlib import Path

import pytest

from stage_gen.capabilities import CapabilityArtifactResult
from stage_gen.interfaces.cli import build_parser, main
from stage_gen.recipes.base import StageContext


class CliRuntime:
    def __init__(self) -> None:
        self.phases: list[str] = []
        self.inputs: list[dict[str, object]] = []
        self.character_library_roots: list[Path | None] = []

    async def run_recipe_stage(
        self, recipe_id: str, stage_name: str, context: StageContext
    ) -> tuple[str, ...]:
        assert recipe_id == "scrolling-preview"
        self.phases.append(stage_name)
        self.inputs.append(dict(context.input))
        self.character_library_roots.append(context.config.character_library_root)
        path = context.run_dir / f"{stage_name}.txt"
        path.write_text(stage_name, encoding="utf-8")
        return (str(path),)

    async def generate_image(self, **_kwargs: object) -> CapabilityArtifactResult:
        raise NotImplementedError

    async def remove_background(self, **_kwargs: object) -> CapabilityArtifactResult:
        raise NotImplementedError

    async def generate_music(self, **_kwargs: object) -> CapabilityArtifactResult:
        raise NotImplementedError


class DialogueCliRuntime(CliRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.force_values: list[str | None] = []
        self.force_stages: list[frozenset[str]] = []
        self.affected_stages: list[frozenset[str]] = []

    async def run_recipe_stage(
        self, recipe_id: str, stage_name: str, context: StageContext
    ) -> tuple[str, ...]:
        assert recipe_id == "dialogue-scene"
        self.phases.append(stage_name)
        self.inputs.append(dict(context.input))
        self.character_library_roots.append(context.config.character_library_root)
        self.force_values.append(os.environ.get("STAGE_GEN_FORCE"))
        self.force_stages.append(context.force_stages)
        self.affected_stages.append(context.affected_stages)
        path = context.run_dir / f"{stage_name}.txt"
        path.write_text(stage_name, encoding="utf-8")
        return (str(path),)


def test_cli_offline_surfaces_require_a_prepared_package() -> None:
    help_text = " ".join(build_parser().format_help().split())
    assert "Prepared game generation requires a directory or ZIP containing game.toml." in help_text
    assert "bare prompt" not in help_text

    output = StringIO()
    assert main(["recipes"], stdout=output) == 0
    assert "scrolling-preview" in output.getvalue()
    output = StringIO()
    assert main(["benchmark", "smoke"], stdout=output) == 0
    assert '"ok": true' in output.getvalue()


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
    assert len(plan["graph"]["nodes"]) == 215
    assert plan["projection"]["operation_counts"] == {
        "local": 102,
        "image_generation": 92,
        "structured_generation": 18,
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
    assert report["node_count"] == 215
    assert report["provider_operation_counts"] == {
        "image_generation": 92,
        "structured_generation": 18,
        "music_generation": 3,
    }
    assert (tmp_path / "run/execution-plan.json").is_file()
    assert (tmp_path / "run/execution-trace.jsonl").is_file()

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
    profile = repository / "library/characters/mira-vale-cartographer/profile.toml"
    validate_output = StringIO()
    assert (
        main(
            [
                "character-profile",
                "validate",
                "--input",
                str(profile),
                "--character-library-root",
                str(repository),
            ],
            stdout=validate_output,
        )
        == 0
    )
    validated = json.loads(validate_output.getvalue())
    assert validated == {
        "binding": {
            "kind": "character-profile-binding-v1",
            "ref": "library/characters/mira-vale-cartographer/profile.toml",
            "schema_version": 1,
            "source_sha256": "3637614c8d5a13cfa6d4f7aa889a750bdecac2c1f14375483e26ef37aedfb0cf",
        },
        "canonical_bytes": validated["canonical_bytes"],
        "canonical_sha256": validated["canonical_sha256"],
        "kind": "resolved-character-profile-v1",
        "profile_id": "mira-vale-cartographer",
        "resolution_version": "character-profile-library-resolution-v1",
        "revision": 1,
        "rights_status": "unreviewed",
        "schema_version": 1,
        "source_sha256": "3637614c8d5a13cfa6d4f7aa889a750bdecac2c1f14375483e26ef37aedfb0cf",
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
                "--character-library-root",
                str(repository),
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
    assert "--character-library-root CHARACTER_LIBRARY_ROOT" in help_text

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
                "--character-library-root",
                str(repository),
            ],
            stderr=error_output,
        )
        == 1
    )
    assert "must be inside character library root" in error_output.getvalue()

    invalid_root = tmp_path / "workspace"
    invalid_profile = invalid_root / "library/characters/broken/profile.toml"
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
                "--character-library-root",
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


@pytest.mark.skip(reason="prompt and recipe-file generation were removed by the package cutover")
@pytest.mark.parametrize(
    ("recipe", "relative_example", "expected_first", "expected_count"),
    [
        (
            "dialogue-scene",
            "examples/dialogue-theme/profile-enabled-date.toml",
            "prepare",
            10,
        ),
        (
            "scrolling-preview",
            "examples/scrolling-preview/profile-enabled-coast.toml",
            "profile-resolve",
            7,
        ),
    ],
)
def test_profile_enabled_examples_route_without_provider_calls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    recipe: str,
    relative_example: str,
    expected_first: str,
    expected_count: int,
) -> None:
    repository = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("OPENAI_API_KEY", "offline")
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline")
    monkeypatch.setenv("FAL_KEY", "offline")
    monkeypatch.setenv("OUT_DIR", str(tmp_path / "out"))
    runtime: CliRuntime = DialogueCliRuntime() if recipe == "dialogue-scene" else CliRuntime()
    output = StringIO()
    assert (
        main(
            [
                "generate",
                "--recipe",
                recipe,
                "--input",
                str(repository / relative_example),
                "--character-library-root",
                str(repository),
                "--transparency",
                "native",
            ],
            runtime=runtime,
            stdout=output,
        )
        == 0
    )
    assert runtime.phases[0] == expected_first
    assert "profile-resolve" in runtime.phases
    assert len(runtime.phases) == expected_count
    assert set(runtime.character_library_roots) == {repository}


@pytest.mark.skip(reason="prompt and recipe-file generation were removed by the package cutover")
@pytest.mark.parametrize(
    ("suffix", "document"),
    [
        (
            ".json",
            json.dumps(
                {
                    "prompt": "ink-lined moonlit ruins",
                    "theme": {"hostile_action": 3, "threat_disturbance": 2},
                }
            ),
        ),
        (
            ".input",
            json.dumps(
                {
                    "prompt": "ink-lined moonlit ruins",
                    "theme": {"hostile_action": 3, "threat_disturbance": 2},
                }
            ),
        ),
        (
            ".toml",
            'prompt = "ink-lined moonlit ruins"\n\n'
            "[theme]\n"
            "hostile_action = 3\n"
            "threat_disturbance = 2\n",
        ),
    ],
)
def test_cli_input_accepts_json_and_toml_theme_documents(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    suffix: str,
    document: str,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline")
    monkeypatch.setenv("OUT_DIR", str(tmp_path / "out"))
    input_path = tmp_path / f"generation{suffix}"
    input_path.write_text(document, encoding="utf-8")
    runtime = CliRuntime()
    output = StringIO()

    assert (
        main(
            ["generate", "--input", str(input_path), "--transparency", "chroma"],
            runtime=runtime,
            stdout=output,
        )
        == 0
    )

    assert runtime.phases[0] == "theme-compile"
    assert runtime.phases.count("theme-compile") == 1
    assert runtime.inputs[0]["theme"] == {
        "sexual_content": 0,
        "nudity_exposure": 0,
        "hostile_action": 3,
        "injury_detail": 0,
        "substance_depiction": 0,
        "threat_disturbance": 2,
    }
    assert "stages=7" in output.getvalue()


@pytest.mark.skip(reason="generic recipe generation was removed from the game package CLI")
def test_dialogue_sample_routes_through_public_cli_with_force_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "offline")
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline")
    monkeypatch.setenv("FAL_KEY", "offline")
    monkeypatch.setenv("OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("STAGE_GEN_FORCE", "1")
    sample = (
        Path(__file__).resolve().parents[2] / "examples/dialogue-theme/adult-university-date.json"
    )
    runtime = DialogueCliRuntime()
    output = StringIO()

    assert (
        main(
            ["generate", "--recipe", "dialogue-scene", "--input", str(sample)],
            runtime=runtime,
            stdout=output,
        )
        == 0
    )

    assert runtime.phases == [
        "prepare",
        "style-selection",
        "appearance-concept",
        "scene-plan",
        "background",
        "neutral",
        "expressions",
        "canonicalize",
        "bundle",
    ]
    assert set(runtime.force_values) == {"1"}
    appearance = runtime.inputs[0]["appearance"]
    assert isinstance(appearance, dict)
    assert appearance["age"] == 23
    run_files = list((tmp_path / "out").glob("*/run.json"))
    assert len(run_files) == 1
    run_state = json.loads(run_files[0].read_text(encoding="utf-8"))
    assert run_state["schema_version"] == 3
    assert run_state["kind"] == "recipe_run_v3"
    assert "runDir" not in run_state
    assert "run_dir" in run_state
    assert "transparencyMode" not in run_state["input"]
    assert run_state["input"]["transparency_mode"] == "native"
    assert "stages=9" in output.getvalue()


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


@pytest.mark.skip(reason="generic recipe generation was removed from the game package CLI")
def test_dialogue_public_force_stage_forwards_validated_dag_plan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "offline")
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline")
    monkeypatch.setenv("FAL_KEY", "offline")
    monkeypatch.setenv("OUT_DIR", str(tmp_path / "out"))
    sample = (
        Path(__file__).resolve().parents[2] / "examples/dialogue-theme/adult-university-date.json"
    )
    runtime = DialogueCliRuntime()

    assert (
        main(
            [
                "generate",
                "--recipe",
                "dialogue-scene",
                "--input",
                str(sample),
                "--force-stage",
                "appearance-concept",
                "--force-stage",
                "canonicalize",
            ],
            runtime=runtime,
        )
        == 0
    )

    expected_affected = frozenset(
        {
            "appearance-concept",
            "scene-plan",
            "background",
            "neutral",
            "expressions",
            "canonicalize",
            "bundle",
        }
    )
    assert set(runtime.force_stages) == {frozenset({"appearance-concept", "canonicalize"})}
    assert set(runtime.affected_stages) == {expected_affected}


@pytest.mark.skip(reason="generic recipe generation was removed from the game package CLI")
@pytest.mark.parametrize(
    "force_args",
    [
        ["--force-stage", "missing"],
        ["--force-stage", "neutral", "--force-stage", "neutral"],
        ["--force-stage", "../neutral"],
    ],
)
def test_dialogue_public_force_stage_rejects_before_runtime_calls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    force_args: list[str],
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline")
    monkeypatch.setenv("FAL_KEY", "offline")
    monkeypatch.setenv("OUT_DIR", str(tmp_path / "out"))
    sample = (
        Path(__file__).resolve().parents[2] / "examples/dialogue-theme/adult-university-date.json"
    )
    runtime = DialogueCliRuntime()
    errors = StringIO()

    assert (
        main(
            [
                "generate",
                "--recipe",
                "dialogue-scene",
                "--input",
                str(sample),
                *force_args,
            ],
            runtime=runtime,
            stderr=errors,
        )
        == 1
    )
    assert runtime.phases == []
    assert "forced stage" in errors.getvalue()


@pytest.mark.skip(reason="generic recipe generation was removed from the game package CLI")
def test_dialogue_cli_rejects_a_bundle_without_background(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline")
    monkeypatch.setenv("FAL_KEY", "offline")
    monkeypatch.setenv("OUT_DIR", str(tmp_path / "out"))
    sample = (
        Path(__file__).resolve().parents[2] / "examples/dialogue-theme/adult-university-date.json"
    )
    document = json.loads(sample.read_text(encoding="utf-8"))
    document["background"] = {"mode": "none"}
    invalid = tmp_path / "no-background.json"
    invalid.write_text(json.dumps(document), encoding="utf-8")
    runtime = DialogueCliRuntime()
    errors = StringIO()

    assert (
        main(
            ["generate", "--recipe", "dialogue-scene", "--input", str(invalid)],
            runtime=runtime,
            stderr=errors,
        )
        == 1
    )
    assert runtime.phases == []
    assert "invalid dialogue-theme-request-v2" in errors.getvalue()


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
