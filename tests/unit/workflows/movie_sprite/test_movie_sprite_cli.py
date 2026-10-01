"""``stage-gen plan|run movie-sprite`` keeps offline planning separate from provider opt-in."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NoReturn

import pytest
from PIL import Image

from stage_gen.components.character_3d.budget_pool import BudgetPool
from stage_gen.config import StageGenConfig
from stage_gen.interfaces.cli import parse
from stage_gen.pipeline import PipelinePlan, plan
from stage_gen.workflows.movie_sprite import cli
from stage_gen.workflows.movie_sprite.inputs.supplied_clip.make_inputs import make_inputs


def _inputs(root: Path) -> Path:
    inputs = root / "inputs"
    inputs.mkdir()
    Image.new("RGBA", (32, 48), (240, 140, 90, 255)).save(inputs / "actor.png")
    (inputs / "authoring.json").write_text(json.dumps({"canonical_image": "actor.png"}))
    (inputs / "finish.json").write_text(json.dumps({"source_mode": "chroma"}))
    return inputs


def _arguments(root: Path, verb: str = "plan", *extra: str) -> list[str]:
    return [
        verb,
        "movie-sprite",
        "--input-root",
        str(root / "inputs"),
        "--authoring",
        "authoring.json",
        "--finish",
        "finish.json",
        "--output-root",
        str(root / "output"),
        *(["--cache-root", str(root / "cache")] if verb == "run" else []),
        *extra,
    ]


def _invoke(*arguments: str) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if not key.endswith(("_KEY", "_TOKEN"))}
    env["_STAGE_GEN_DISABLE_DOTENV"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "stage_gen.interfaces.cli", *arguments],
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
        "run",
        "movie-sprite",
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
async def test_invalid_plan_never_opens_credentials_or_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from stage_gen import config
    from stage_gen.orchestration import movie_sprite_services

    _inputs(tmp_path)
    (tmp_path / "inputs/authoring.json").write_text(json.dumps({"canonical_image": "missing.png"}))

    def forbidden(*args: object, **kwargs: object) -> NoReturn:
        raise AssertionError("credentials or provider were opened before offline admission")

    monkeypatch.setattr(config, "load_config", forbidden)
    monkeypatch.setattr(movie_sprite_services, "MovieSpriteVideoService", forbidden)
    arguments = _arguments(
        tmp_path, "run", "--live", "--budget-root", str(tmp_path / "budget"), "--budget-usd", "10"
    )
    with pytest.raises((ValueError, OSError)):
        await cli._execute(parse(arguments))
    assert not (tmp_path / "budget").exists()


@pytest.mark.asyncio
async def test_live_config_and_service_are_opened_after_plan_and_always_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from stage_gen import config
    from stage_gen.orchestration import movie_sprite_services

    _inputs(tmp_path)
    dotenv = tmp_path / "provider.env"
    dotenv.write_text("FAL_KEY=fixture-only-secret\nUNRELATED=value\n")
    events: list[str] = []
    real_plan = plan

    def planned(*args: Any, **kwargs: Any) -> PipelinePlan:
        result = real_plan(*args, **kwargs)
        events.append("plan")
        return result

    def load(*, env: Mapping[str, str | None] | None = None, **kwargs: object) -> StageGenConfig:
        assert events == ["plan"]
        assert env is not None and env["FAL_KEY"] == "fixture-only-secret"
        events.append("config")
        return config.StageGenConfig(fal_key="fixture-only-secret")

    class FakeService:
        provider_operations = 0
        known_cost_usd = None

        def __init__(
            self,
            configured: StageGenConfig,
            budget: BudgetPool,
            *,
            live: bool,
            operation_id: str,
        ) -> None:
            assert events == ["plan", "config"]
            assert live and operation_id == "take-01"
            self.budget = budget
            events.append("service")

        async def aclose(self) -> None:
            events.append("closed")

        def budget_snapshot(self) -> dict[str, Any]:
            return self.budget.snapshot()

    async def run(*args: object, **kwargs: object) -> SimpleNamespace:
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
    monkeypatch.setattr("stage_gen.pipeline.plan", planned)
    monkeypatch.setattr("stage_gen.pipeline.run", run)
    monkeypatch.setattr(config, "load_config", load)
    monkeypatch.setattr(movie_sprite_services, "MovieSpriteVideoService", FakeService)
    arguments = _arguments(
        tmp_path,
        "run",
        "--live",
        "--budget-root",
        str(tmp_path / "budget"),
        "--budget-usd",
        "10",
        "--dotenv",
        str(dotenv),
    )
    result = await cli._execute(parse(arguments))
    assert result["status"] == "succeeded"
    assert events == ["plan", "config", "service", "plan", "run", "closed"]


@pytest.mark.parametrize(
    ("extra", "refusal"),
    [
        (("--replay", "--live"), "--replay binds no live provider"),
        (("--live",), "--live requires --budget-root and --budget-usd"),
        ((), "generation requires --live; use --replay for cached generation"),
    ],
)
def test_run_refuses_an_opt_in_its_flags_cannot_mean(
    tmp_path: Path, extra: tuple[str, ...], refusal: str
) -> None:
    _inputs(tmp_path)
    result = _invoke(*_arguments(tmp_path, "run", *extra))
    assert result.returncode == 2
    assert refusal in result.stderr
    assert not (tmp_path / "output").exists() and not (tmp_path / "cache").exists()
