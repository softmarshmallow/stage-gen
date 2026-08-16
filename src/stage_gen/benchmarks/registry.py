"""Offline and opt-in benchmark suites."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from stage_gen.config import StageGenConfig
from stage_gen.recipes.registry import list_recipes
from stage_gen.tags import tag_for


@dataclass(frozen=True, slots=True)
class BenchmarkSuite:
    id: str
    description: str
    live: bool
    run: Callable[[StageGenConfig], dict[str, Any]]


def _smoke(_config: StageGenConfig) -> dict[str, Any]:
    first = tag_for("neutral 2D asset study")
    second = tag_for("neutral 2D asset study")
    recipes = list_recipes()
    checks = [
        {"name": "deterministic-tag", "ok": first == second, "detail": first},
        {
            "name": "recipe-registry",
            "ok": any(recipe["id"] == "scrolling-preview" for recipe in recipes),
            "detail": ",".join(recipe["id"] for recipe in recipes),
        },
    ]
    return {"suite": "smoke", "ok": all(check["ok"] for check in checks), "checks": checks}


_SUITES = {
    "smoke": BenchmarkSuite(
        id="smoke",
        description="Offline headless registry and deterministic-tag smoke",
        live=False,
        run=_smoke,
    )
}


def list_benchmark_suites() -> list[dict[str, str | bool]]:
    return [
        {"id": suite.id, "description": suite.description, "live": suite.live}
        for suite in _SUITES.values()
    ]


def run_benchmark(suite_id: str, config: StageGenConfig) -> dict[str, Any]:
    try:
        suite = _SUITES[suite_id]
    except KeyError as error:
        raise ValueError(f"unknown benchmark suite: {suite_id}") from error
    return suite.run(config)
