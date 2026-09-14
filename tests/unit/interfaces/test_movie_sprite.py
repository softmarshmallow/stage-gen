"""The family CLI keeps offline planning separate from provider opt-in."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from stage_gen.interfaces import movie_sprite as cli
from stage_gen.recipes.movie_sprite_body_idle.examples.supplied_clip.make_inputs import make_inputs


def _inputs(root: Path) -> Path:
    inputs = root / "inputs"
    inputs.mkdir()
    Image.new("RGBA", (32, 48), (240, 140, 90, 255)).save(inputs / "actor.png")
    (inputs / "authoring.json").write_text(json.dumps({"canonical_image": "actor.png"}))
    (inputs / "finish.json").write_text(json.dumps({"source_mode": "chroma"}))
    return inputs


def _arguments(root: Path, *extra: str) -> list[str]:
    return [
        "body",
        "idle",
        "plan",
        "--input-root",
        str(root / "inputs"),
        "--authoring",
        "authoring.json",
        "--finish",
        "finish.json",
        "--output-root",
        str(root / "output"),
        "--cache-root",
        str(root / "cache"),
        *extra,
    ]


def _invoke(*arguments: str) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if not key.endswith(("_KEY", "_TOKEN"))}
    env["_STAGE_GEN_DISABLE_DOTENV"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "stage_gen.interfaces.movie_sprite", *arguments],
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )


def test_public_cli_plans_generation_without_credentials(tmp_path: Path) -> None:
    _inputs(tmp_path)
    result = _invoke(*_arguments(tmp_path))
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    assert response["provider_operations"] == 0
    assert response["selected_nodes"] == ["prepare", "generate", "finish"]
    assert not (tmp_path / "budget").exists()


def test_public_cli_runs_supplied_synthetic_clip_without_provider(tmp_path: Path) -> None:
    make_inputs(tmp_path / "inputs")
    result = _invoke(
        "body",
        "idle",
        "run",
        "--input-root",
        str(tmp_path / "inputs"),
        "--source",
        "actor.mkv",
        "--finish",
        "finish.json",
        "--output-root",
        str(tmp_path / "output"),
        "--cache-root",
        str(tmp_path / "cache"),
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "output/body/canonical.png").is_file()
    assert sum(json.loads(result.stdout)["provider_operation_counts"].values()) == 0


@pytest.mark.asyncio
async def test_invalid_plan_never_opens_credentials_or_budget(tmp_path: Path, monkeypatch) -> None:
    from stage_gen import config
    from stage_gen.orchestration import movie_sprite_services

    _inputs(tmp_path)
    (tmp_path / "inputs/authoring.json").write_text(json.dumps({"canonical_image": "missing.png"}))

    def forbidden(*args, **kwargs):
        raise AssertionError("credentials or provider were opened before offline admission")

    monkeypatch.setattr(config, "load_config", forbidden)
    monkeypatch.setattr(movie_sprite_services, "MovieSpriteVideoService", forbidden)
    arguments = _arguments(
        tmp_path, "--live", "--budget-root", str(tmp_path / "budget"), "--budget-usd", "10"
    )
    arguments[2] = "run"
    args = cli._parser().parse_args(arguments)
    with pytest.raises((ValueError, OSError)):
        await cli._execute(args)
    assert not (tmp_path / "budget").exists()


@pytest.mark.asyncio
async def test_live_config_and_service_are_opened_after_plan_and_always_closed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from stage_gen import config
    from stage_gen.orchestration import movie_sprite_services

    _inputs(tmp_path)
    dotenv = tmp_path / "provider.env"
    dotenv.write_text("FAL_KEY=fixture-only-secret\nUNRELATED=value\n")
    events = []
    real_plan = cli.plan

    def planned(*args, **kwargs):
        result = real_plan(*args, **kwargs)
        events.append("plan")
        return result

    def load(*, env=None, **kwargs):
        assert events == ["plan"]
        assert env is not None and env["FAL_KEY"] == "fixture-only-secret"
        events.append("config")
        return config.StageGenConfig(fal_key="fixture-only-secret")

    class FakeService:
        provider_operations = 0
        known_cost_usd = None

        def __init__(self, configured, budget, *, live, operation_id):
            assert events == ["plan", "config"]
            assert live and operation_id == "take-01"
            self.budget = budget
            events.append("service")

        async def aclose(self):
            events.append("closed")

        def budget_snapshot(self):
            return self.budget.snapshot()

    async def run(*args, **kwargs):
        assert events == ["plan", "config", "service", "plan"]
        assert kwargs["allow_provider_calls"] is True
        events.append("run")
        return SimpleNamespace(
            summary=SimpleNamespace(
                ok=True,
                model_dump=lambda **kw: {
                    "ok": True,
                    "provider_operations": 0,
                },
            )
        )

    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.setattr(cli, "plan", planned)
    monkeypatch.setattr(cli, "run", run)
    monkeypatch.setattr(config, "load_config", load)
    monkeypatch.setattr(movie_sprite_services, "MovieSpriteVideoService", FakeService)
    arguments = _arguments(
        tmp_path,
        "--live",
        "--budget-root",
        str(tmp_path / "budget"),
        "--budget-usd",
        "10",
        "--dotenv",
        str(dotenv),
    )
    arguments[2] = "run"
    result = await cli._execute(cli._parser().parse_args(arguments))
    assert result["status"] == "succeeded"
    assert events == ["plan", "config", "service", "plan", "run", "closed"]


def test_face_alias_forwards_unchanged_arguments_and_restores_process_argv(monkeypatch) -> None:
    from stage_gen.interfaces import portrait_motion

    original = ["stage-gen-movie-sprite", "face", "repaint", "verify", "--run", "fixture"]
    seen = []
    monkeypatch.setattr(sys, "argv", original)
    monkeypatch.setattr(portrait_motion, "entrypoint", lambda: seen.append(list(sys.argv)))
    cli.entrypoint()
    assert seen == [["stage-gen-movie-sprite face repaint", "verify", "--run", "fixture"]]
    assert sys.argv is original
