"""``stage-gen``: one verb set over the installed workflows, offline.

Every command here runs with credentials and ``STAGE_GEN_*`` overrides removed and the
dotenv loader disabled; the dry runs and the local looping-parallax run reach no provider.
"""

from __future__ import annotations

import json
import os
import runpy
import subprocess
import sys
from io import StringIO
from pathlib import Path
from typing import NoReturn, cast

import pytest

from stage_gen.capabilities import CapabilityArtifactResult, HeadlessRuntime
from stage_gen.config import load_config
from stage_gen.interfaces.cli import main, parse
from stage_gen.interfaces.commands import capability
from stage_gen.provider_env import REQUIRED_PROVIDER_ENV_KEYS
from stage_gen.workflows._registry import discover

REPOSITORY = Path(__file__).resolve().parents[2]
LANTERN_FERRY = REPOSITORY / "src/stage_gen/workflows/universe/inputs/lantern_ferry"
STOREFRONT_INPUTS = REPOSITORY / "src/stage_gen/workflows/storefront/inputs/minimal"
PARALLAX_INPUTS = REPOSITORY / "src/stage_gen/workflows/looping_parallax/inputs/supplied_layers"
CREDENTIALS = ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "FAL_KEY", "ELEVENLABS_API_KEY")
WORKFLOWS = {
    "character-3d",
    "looping-parallax",
    "movie-sprite",
    "portrait-motion",
    "storefront",
    "universe",
}


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("STAGE_GEN_") or key in CREDENTIALS:
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("_STAGE_GEN_DISABLE_DOTENV", "1")


def _stage_gen(*arguments: str) -> tuple[int, str, str]:
    output, errors = StringIO(), StringIO()
    status = main(list(arguments), stdout=output, stderr=errors)
    return status, output.getvalue(), errors.getvalue()


def _subprocess(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("STAGE_GEN_") and key not in CREDENTIALS
    }
    environment["_STAGE_GEN_DISABLE_DOTENV"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "stage_gen.interfaces.cli", *arguments],
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_building_the_parser_loads_no_engine_media_or_workflow_implementation() -> None:
    """``stage-gen --help`` and ``stage-gen list`` stay cheap: the parser is built from the
    manifests and each workflow's argparse-only ``cli`` module."""
    program = """
import sys
from stage_gen.interfaces.cli import build_parser
build_parser()
heavy = sorted(
    name for name in sys.modules
    if name.split('.')[0] in {'numpy', 'PIL', 'cv2', 'gnode'}
    or name.startswith('stage_gen.workflows.') and name.split('.')[-1] not in {'cli', '_registry'}
    and name.count('.') > 2
)
print(heavy)
"""
    completed = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, check=True
    )
    assert completed.stdout.strip() == "[]", completed.stdout


def test_help_lists_the_verbs_and_every_workflow_with_its_promise() -> None:
    status, output, _ = _stage_gen("--help")
    assert status == 0
    for verb in ("list", "show", "plan", "run", "inspect", "view", "example", "catalog"):
        assert f"    {verb}" in output
    for verb in ("capability", "models", "env"):
        assert f"    {verb}" in output
    help_text = _subprocess("run", "--help")
    assert help_text.returncode == 0, help_text.stderr
    flat = " ".join(help_text.stdout.split())
    for found in discover():
        assert found.id in flat and " ".join(found.manifest.promise.split()) in flat
    assert " file " in flat


@pytest.mark.parametrize("verb", ["plan", "run"])
@pytest.mark.parametrize("workflow", sorted(WORKFLOWS))
def test_every_workflow_verb_has_help(verb: str, workflow: str) -> None:
    completed = _subprocess(verb, workflow, "--help")
    assert completed.returncode == 0, completed.stderr
    assert "usage:" in completed.stdout
    if (verb, workflow) == ("run", "character-3d"):
        # The frozen launcher answers its own --help, under the name it is reached by.
        assert "stage-gen run character-3d" in completed.stdout
        assert "--experiment" in completed.stdout


def test_plan_character_3d_refuses_and_says_what_to_run() -> None:
    status, _, errors = _stage_gen("plan", "character-3d")
    assert status == 2
    assert "stage-gen run character-3d --prepare-only" in errors


def test_run_character_3d_forwards_its_arguments_verbatim_and_restores_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from stage_gen.orchestration.character_3d import launch

    seen: list[list[str]] = []

    def launcher() -> NoReturn:
        seen.append(list(sys.argv))
        raise SystemExit(3)

    monkeypatch.setattr(launch, "main", launcher)
    original = sys.argv
    forwarded = ["--experiment", "e.json", "--review-mode=none", "-h", "--", "x y"]
    assert _stage_gen("run", "character-3d", *forwarded)[0] == 3
    assert seen == [["stage-gen run character-3d", *forwarded]]
    assert sys.argv is original


def test_list_and_show_read_the_workflows() -> None:
    status, output, _ = _stage_gen("list", "--json")
    assert status == 0
    rows = json.loads(output)
    assert {row["id"] for row in rows} == WORKFLOWS
    status, output, _ = _stage_gen("list")
    assert status == 0 and "movie-sprite" in output and "Movie sprite" in output
    status, output, _ = _stage_gen("show", "looping-parallax", "--json")
    assert status == 0
    document = json.loads(output)
    assert document["id"] == "looping-parallax"
    assert [step["label"] for step in document["steps"]] == ["Make each layer repeat", "Compose"]
    assert document["sample_plan"]["operation_counts"] == {"local": 3}
    status, output, _ = _stage_gen("show", "character-3d")
    assert status == 0 and "Plan: a character run is prepared inside its launcher" in output
    status, _, errors = _stage_gen("show", "no-such-workflow")
    assert status == 2 and "unknown workflow" in errors


def test_unknown_arguments_are_refused_outside_a_forwarding_workflow() -> None:
    status, _, errors = _stage_gen(
        "plan", "universe", "--phase", "semantic", "--input", str(LANTERN_FERRY), "--bogus"
    )
    assert status == 2 and "unrecognized arguments: --bogus" in errors


def test_looping_parallax_runs_offline_and_plans_like_its_sdk_sample(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    runpy.run_path(str(PARALLAX_INPUTS / "make_inputs.py"))["write_inputs"](inputs)
    status, by_workflow, errors = _stage_gen("plan", "looping-parallax", "--input", str(inputs))
    assert status == 0, errors
    sample = str(PARALLAX_INPUTS / "pipeline.py")
    status, by_file, errors = _stage_gen("plan", "file", sample, "--input", str(inputs))
    assert status == 0, errors
    assert json.loads(by_workflow)["graph"] == json.loads(by_file)["graph"]

    run_dir = tmp_path / "run"
    arguments = ["--input", str(inputs), "--output", str(run_dir)]
    status, output, errors = _stage_gen(
        "run", "looping-parallax", *arguments, "--cache-dir", str(tmp_path / "cache")
    )
    assert status == 0, errors
    assert json.loads(output)["pipeline_id"] == "looping-parallax"
    assert (run_dir / "parallax/manifest.json").is_file()

    status, _, errors = _stage_gen(
        "run", "looping-parallax", *arguments, "--cache-dir", str(tmp_path / "cache")
    )
    assert status == 2
    assert errors == f"stage-gen: {run_dir} already exists; choose a new output folder\n"

    status, output, errors = _stage_gen("inspect", str(run_dir), "--verify", "--json")
    assert status == 0, errors
    record = json.loads(output)
    assert record["workflow"] == "looping-parallax"
    assert record["verification"] == {"verified": True, "problems": []}
    status, output, _ = _stage_gen("inspect", str(run_dir))
    assert status == 0
    assert "workflow  looping-parallax" in output and "verified" not in output

    (run_dir / "parallax/preview.png").write_bytes(b"not the recorded preview")
    status, output, _ = _stage_gen("inspect", str(run_dir), "--verify")
    assert status == 1 and "no: 1 problem(s)" in output

    views = tmp_path / "views"
    status, output, errors = _stage_gen(
        "inspect", str(run_dir), "--write-view", str(views), "--json"
    )
    assert status == 0, errors
    assert json.loads(output)["written_view"] == str(views / "execution-view.json")
    assert (views / "execution-view.json").is_file()


def test_universe_runs_both_phases_dry_and_writes_its_views(tmp_path: Path) -> None:
    """Both phases, a reroll and the run views, with no provider anywhere."""
    from tests.unit.workflows.universe._universe_fixture import materialize_semantic_run

    admitted = REPOSITORY / "tests/contract/fixtures/universe/lantern_ferry.admitted-universe.json"
    cache = ["--cache-dir", str(tmp_path / "cache")]
    status, output, errors = _stage_gen(
        "plan", "universe", "--phase", "semantic", "--input", str(LANTERN_FERRY)
    )
    assert status == 0, errors
    assert len(json.loads(output)["graph"]["nodes"]) == 6

    semantic = tmp_path / "semantic"
    status, output, errors = _stage_gen(
        "run",
        "universe",
        "--phase",
        "semantic",
        "--input",
        str(LANTERN_FERRY),
        "--output",
        str(semantic),
        *cache,
        "--dry-run",
        "--invocation-id",
        "cli-semantic",
    )
    assert status == 0, errors
    report = json.loads(output)
    assert (report["recipe"], report["phase"], report["universe_id"]) == (
        "universe",
        "semantic",
        "lantern_ferry",
    )
    assert report["node_count"] == 6

    # The gallery phase starts from an admission rather than from the package, so stand
    # one up from the committed fixture instead of paying for a semantic run.
    materialize_semantic_run(
        semantic, admitted=admitted, poster=LANTERN_FERRY / "references/poster.png"
    )

    def gallery(output_dir: Path, invocation: str, *extra: str) -> dict[str, object]:
        status, output, errors = _stage_gen(
            "run",
            "universe",
            "--phase",
            "gallery",
            "--input",
            str(LANTERN_FERRY),
            "--semantic-run",
            str(semantic),
            "--output",
            str(output_dir),
            *cache,
            "--dry-run",
            "--invocation-id",
            invocation,
            *extra,
        )
        assert status == 0, errors
        report: dict[str, object] = json.loads(output)
        return report

    first = tmp_path / "gallery"
    report = gallery(first, "cli-gallery")
    assert report["phase"] == "gallery" and report["node_count"] == 42
    counts = report["counts"]
    assert isinstance(counts, dict) and sum(counts.values()) == 8
    assert not (first / "consumer").exists()

    # A reroll advances the ledger the first run left behind.
    second = tmp_path / "gallery-2"
    gallery(
        second,
        "cli-gallery-2",
        "--reroll",
        "low_marsh",
        "--sample-ledger",
        str(first / "sample-ledger.json"),
    )
    assert json.loads((second / "sample-ledger.json").read_bytes())["samples"]["low_marsh"] == 1

    for run_dir in (semantic, first):
        status, output, errors = _stage_gen(
            "inspect", str(run_dir), "--write-view", str(run_dir), "--json"
        )
        assert status == 0, errors
        record = json.loads(output)
        assert record["workflow"] == "universe" and record["view"]["gaps"] == []
        assert (run_dir / "execution-view.json").is_file()


def test_universe_phase_flags_and_failure_injection_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Injecting a failure is a dry-run affordance; a paid run must not take it."""
    from stage_gen.workflows.universe.universe_executor import UniverseExecutor

    def unreachable(*_: object, **__: object) -> NoReturn:
        raise AssertionError("a refused command reached the executor")

    monkeypatch.setattr(UniverseExecutor, "run_semantic", unreachable)
    run_dir = tmp_path / "run"
    status, _, errors = _stage_gen(
        "run",
        "universe",
        "--phase",
        "semantic",
        "--input",
        str(LANTERN_FERRY),
        "--output",
        str(run_dir),
        "--cache-dir",
        str(tmp_path / "cache"),
        "--live",
        "--failure-node",
        "source-lock",
    )
    assert status == 2 and "available only with --dry-run" in errors
    assert not run_dir.exists()
    status, _, errors = _stage_gen(
        "plan", "universe", "--phase", "gallery", "--input", str(LANTERN_FERRY)
    )
    assert status == 2 and "--phase gallery needs --semantic-run" in errors


def test_storefront_plans_and_dry_runs(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    runpy.run_path(str(STOREFRONT_INPUTS / "make_inputs.py"))["write_inputs"](inputs)
    status, output, errors = _stage_gen("plan", "storefront", "--input", str(inputs))
    assert status == 0, errors
    planned = json.loads(output)["graph"]["nodes"]
    run_dir = tmp_path / "run"
    status, output, errors = _stage_gen(
        "run",
        "storefront",
        "--input",
        str(inputs),
        "--output",
        str(run_dir),
        "--cache-dir",
        str(tmp_path / "cache"),
        "--dry-run",
        "--invocation-id",
        "cli-storefront",
    )
    assert status == 0, errors
    report = json.loads(output)
    assert report["ok"] and report["node_count"] == len(planned)
    status, _, errors = _stage_gen("plan", "storefront", "--input", str(inputs), "--reroll", "x")
    assert status == 2 and "does not declare: ['x']" in errors


@pytest.mark.parametrize(
    "argv",
    [
        ["image", "--output", "x.png", "a prompt"],
        ["remove-background", "--input", "x.png", "--output", "y.png"],
        ["music", "--output", "x.mp3", "a prompt"],
        ["sound-effect", "--output", "x.mp3", "--duration", "1", "a prompt"],
        ["speech", "--output", "x.mp3", "--voice", "v", "hi"],
        ["video", "--output", "x.mp4", "--duration", "4", "a prompt"],
    ],
)
def test_one_command_spend_refuses_without_confirmation_off_a_terminal(argv: list[str]) -> None:
    """The only spend in the CLI that nothing prices first still needs a person, or --yes."""
    # Refusing a paid call off a terminal is a usage error: status 2, like argparse.
    status, _, errors = _stage_gen("capability", *argv)
    assert status == 2
    assert "pass --yes to confirm" in errors


def _artifact(kwargs: dict[str, object], size: int) -> CapabilityArtifactResult:
    output = str(kwargs["output_path"])
    return CapabilityArtifactResult(
        artifact_path=output,
        provenance_path=f"{output}.meta.json",
        media_type="audio/mpeg",
        bytes=size,
        attempts=1,
    )


async def test_sound_effect_passes_the_verbatim_prompt_and_route_parameters(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ELEVENLABS_API_KEY", "eleven")
    calls: list[dict[str, object]] = []

    class _Runtime:
        async def generate_sound_effect(self, **kwargs: object) -> CapabilityArtifactResult:
            calls.append(kwargs)
            return _artifact(kwargs, 12_000)

    args = parse(
        [
            "capability",
            "sound-effect",
            "--yes",
            "--output",
            str(tmp_path / "hatch.mp3"),
            "--duration",
            "0.6",
            "--prompt-influence",
            "0.3",
            "metal",
            "hatch",
            "latch release",
        ]
    )
    output = StringIO()
    runtime = cast(HeadlessRuntime, _Runtime())
    status = await capability.dispatch(args, config=load_config(), runtime=runtime, stdout=output)
    assert status == 0
    assert calls == [
        {
            "prompt": "metal hatch latch release",
            "output_path": str(tmp_path / "hatch.mp3"),
            "duration_seconds": 0.6,
            "prompt_influence": 0.3,
            "loop": False,
            "metadata": None,
        }
    ]
    assert json.loads(output.getvalue())["mediaType"] == "audio/mpeg"


async def test_speech_passes_the_verbatim_text_and_the_provider_voice(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ELEVENLABS_API_KEY", "eleven")
    calls: list[dict[str, object]] = []

    class _Runtime:
        async def generate_speech(self, **kwargs: object) -> CapabilityArtifactResult:
            calls.append(kwargs)
            return _artifact(kwargs, 30_000)

    args = parse(
        [
            "capability",
            "speech",
            "--yes",
            "--output",
            str(tmp_path / "go.mp3"),
            "--voice",
            "voice-7",
            "--stability",
            "0.5",
            "--language",
            "ja",
            "[excited]",
            "いくよっ!",
        ]
    )
    output = StringIO()
    runtime = cast(HeadlessRuntime, _Runtime())
    status = await capability.dispatch(args, config=load_config(), runtime=runtime, stdout=output)
    assert status == 0
    # The annotation survives the shell verbatim: nothing strips a bracket.
    assert calls == [
        {
            "text": "[excited] いくよっ!",
            "output_path": str(tmp_path / "go.mp3"),
            "voice": "voice-7",
            "stability": 0.5,
            "language_code": "ja",
            "metadata": None,
        }
    ]


@pytest.mark.parametrize(
    "argv",
    [
        ["sound-effect", "--yes", "--duration", "1", "hit"],
        ["speech", "--yes", "--voice", "v", "hi"],
    ],
)
def test_audio_calls_refuse_a_non_mp3_output_before_any_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, argv: list[str]
) -> None:
    monkeypatch.setenv("ELEVENLABS_API_KEY", "eleven")
    status, _, errors = _stage_gen("capability", *argv, "--output", str(tmp_path / "x.wav"))
    assert status == 2 and ".mp3" in errors


def test_env_import_copies_allowlisted_keys_and_never_overwrites(tmp_path: Path) -> None:
    source = tmp_path / "source.env"
    lines = [f"{key}=fixture-only-{index}" for index, key in enumerate(REQUIRED_PROVIDER_ENV_KEYS)]
    source.write_text("\n".join([*lines, "UNRELATED=value", ""]), encoding="utf-8")
    destination = tmp_path / "copied.env"
    status, output, errors = _stage_gen(
        "env", "import", "--source", str(source), "--destination", str(destination)
    )
    assert status == 0, errors
    report = json.loads(output)
    assert report["imported"] == list(REQUIRED_PROVIDER_ENV_KEYS)
    assert "fixture-only" not in output and "UNRELATED" not in destination.read_text()
    before = destination.read_bytes()
    status, _, errors = _stage_gen(
        "env", "import", "--source", str(source), "--destination", str(destination)
    )
    assert status == 2 and "already exists" in errors
    assert destination.read_bytes() == before


def test_models_routes_reports_the_route_catalog() -> None:
    status, output, _ = _stage_gen("models", "routes")
    assert status == 0
    assert json.loads(output)["kind"] == "stage-gen-model-routes-report-v1"
