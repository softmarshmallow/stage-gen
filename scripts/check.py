#!/usr/bin/env python3
"""Run the complete credential-free offline gate, and report every step.

The gate used to stop at its first failure. That is the wrong shape for a
gate that a human reads once a day: a formatting drift at step one hid a
type error at step three and a failing contract test at step four for days,
because "it stopped" and "it passed" looked the same from a distance. Every
step now runs, every step is timed, and the verdict is a table.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
WEB_ROOT = REPOSITORY_ROOT / "web"
CREDENTIAL_VARIABLES = (
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "FAL_KEY",
    "ELEVENLABS_API_KEY",
    "TRIPO_API_KEY",
)


@dataclass(frozen=True)
class Step:
    command: tuple[str, ...]
    cwd: Path = REPOSITORY_ROOT


@dataclass(frozen=True)
class Outcome:
    step: Step
    returncode: int | None
    seconds: float

    @property
    def passed(self) -> bool:
        return self.returncode == 0


def sanitized_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    environment = dict(os.environ if source is None else source)
    for variable in CREDENTIAL_VARIABLES:
        environment.pop(variable, None)
    environment["_STAGE_GEN_DISABLE_DOTENV"] = "1"
    return environment


def commands(
    python: str = sys.executable, *, scope: str = "product"
) -> tuple[tuple[str, ...], ...]:
    """The repository-rooted command list, kept for callers that read it as data."""

    return tuple(step.command for step in steps(python, scratch=Path("/dev/null"), scope=scope))


# Source roots are explicit: checking each game wrapper named prepare.py in one
# mypy invocation would invent duplicate top-level modules. Their typed behavior
# lives in these packages; the wrappers are exercised by the local smoke commands.
GAME_PYTHON_ROOTS = (
    "godot/games/_shared/python/src",
    "godot/games/bellweather/pipeline/src",
    "godot/games/iron_petal_unit/pipeline/src",
    "godot/games/ember_hollow/pipeline/src",
    "godot/games/the_grain/pipeline/src",
    "godot/tools/python/src",
)
GAME_TYPED_TOOLS = (
    "godot/games/bellweather/tools/author_terrain.py",
    "godot/games/bellweather/tools/design_map.py",
    "godot/games/bellweather/tools/prove_climbable_bands.py",
    "godot/games/bellweather/tools/render_asset_scale_figures.py",
    "godot/games/ember_hollow/tools/write_oblique_survival_cache_keys.py",
    "godot/tools/parity_diff.py",
    "godot/tools/validate_game_package.py",
    "godot/tools/write_game_contract_identities.py",
    "godot/tools/write_game_graph_contract.py",
    "godot/tools/write_game_model_policy_snapshot.py",
)


def _game_steps(python: str, *, scratch: Path) -> tuple[Step, ...]:
    """Exercise game-owned preparation entry points without provider work."""
    plans = (
        ("bellweather", ()),
        ("bellweather", ("--variant", "waves")),
        ("iron_petal_unit", ()),
        ("ember_hollow", ()),
        ("the_grain", ("--mode", "case")),
        ("the_grain", ("--mode", "room")),
        ("the_grain", ("--mode", "dialogue")),
    )
    result = [
        Step((python, f"godot/games/{game}/pipeline/prepare.py", "--plan", *options))
        for game, options in plans
    ]
    for game, label, options in (
        ("the_grain", "room", ("--mode", "room")),
        ("the_grain", "dialogue", ("--mode", "dialogue")),
        ("ember_hollow", "survival", ()),
    ):
        result.append(
            Step(
                (
                    python,
                    f"godot/games/{game}/pipeline/prepare.py",
                    *options,
                    "--dry-run",
                    "--cache-dir",
                    str(scratch / "game-cache"),
                    "--output",
                    str(scratch / f"{game}-{label}"),
                )
            )
        )
    result.extend(
        Step((python, "godot/tools/validate_game_package.py", "--input", input_path))
        for input_path in (
            "godot/games/bellweather/inputs/default",
            "godot/games/bellweather/inputs/waves",
            "godot/games/iron_petal_unit/inputs",
        )
    )
    result.extend(
        Step(("demo-games", "scenario", "check", "--input", input_path))
        for input_path in (
            "godot/games/bellweather/inputs/default",
            "godot/games/the_grain/inputs",
        )
    )
    result.extend(
        (
            Step(("demo-games", "case", "bundle", "--help")),
            Step(("demo-games", "oblique-survival", "import-run", "--help")),
            Step((python, "godot/tools/write_game_model_policy_snapshot.py")),
        )
    )
    return tuple(result)


def _asset_steps(python: str, *, scratch: Path) -> tuple[Step, ...]:
    """Execute a real local recipe and plan retained independent asset recipes."""
    parallax = "src/stage_gen/recipes/looping_parallax/examples/supplied_layers"
    storefront = "src/stage_gen/recipes/storefront/examples/minimal"
    inputs = scratch / "parallax-inputs"
    run = scratch / "parallax-run"
    return (
        Step((python, f"{parallax}/make_inputs.py", str(inputs))),
        Step(
            (
                "stage-gen",
                "pipeline",
                "run",
                f"{parallax}/pipeline.py",
                "--input",
                str(inputs),
                "--output",
                str(run),
                "--cache-dir",
                str(scratch / "asset-cache"),
            )
        ),
        Step(("stage-gen", "pipeline", "inspect", str(run))),
        Step((python, f"{storefront}/make_inputs.py", str(scratch / "storefront-inputs"))),
        Step(
            (
                "stage-gen",
                "storefront",
                "generate",
                "--input",
                str(scratch / "storefront-inputs"),
                "--dry-run",
                "--cache-dir",
                str(scratch / "asset-cache"),
                "--output",
                str(scratch / "storefront-run"),
            )
        ),
        Step(
            (
                "stage-gen",
                "universe",
                "semantic",
                "--input",
                "src/stage_gen/recipes/universe/examples/lantern_ferry",
                "--dry-run",
                "--cache-dir",
                str(scratch / "asset-cache"),
                "--output",
                str(scratch / "lantern-ferry"),
            )
        ),
        Step((python, "scripts/write_model_policy_snapshot.py")),
        Step(("stage-gen", "--help")),
        Step(("stage-gen-portrait-motion", "--help")),
    )


def steps(
    python: str = sys.executable, *, scratch: Path, scope: str = "product"
) -> tuple[Step, ...]:
    """Owned gates; the default product gate needs neither Bun nor Godot."""
    from scripts.test_ownership import paths_for

    product_tests = paths_for(REPOSITORY_ROOT, "product")
    groups: dict[str, tuple[Step, ...]] = {
        "product": (
            Step(("ruff", "format", "--check", "src", "scripts", "examples", *product_tests)),
            Step(("ruff", "check", "src", "scripts", "examples", *product_tests)),
            Step(("mypy", "--strict", "src")),
            Step(("pytest", "-m", "not live", *product_tests)),
            Step((python, "-m", "build", "--no-isolation")),
            *_asset_steps(python, scratch=scratch),
        ),
        "viewer": (
            Step(("bun", "run", "check"), WEB_ROOT),
            Step(("bun", "test"), WEB_ROOT),
            Step(("pytest", "-m", "not live", *paths_for(REPOSITORY_ROOT, "viewer"))),
        ),
        "godot": (
            Step((python, "godot/tools/check.py")),
            Step(("pytest", "-m", "not live", *paths_for(REPOSITORY_ROOT, "godot"))),
        ),
        "games": (
            Step(("pytest", "-m", "not live", *paths_for(REPOSITORY_ROOT, "games"))),
            *_game_steps(python, scratch=scratch),
        ),
        "apps": (Step(("pytest", "-m", "not live", *paths_for(REPOSITORY_ROOT, "apps"))),),
        "docs": (Step((python, "scripts/check_docs.py")),),
    }
    if scope == "all":
        return (
            Step(("ruff", "format", "--check", ".")),
            Step(("ruff", "check", ".")),
            Step(
                (
                    "mypy",
                    "--strict",
                    "src",
                    "tests",
                    "scripts",
                    *GAME_PYTHON_ROOTS,
                    *GAME_TYPED_TOOLS,
                    "godot/templates/asset_consumer/prepare.py",
                    "apps/concept_studio/src",
                    "examples",
                )
            ),
            Step(("pytest", "-m", "not live")),
            *groups["viewer"][:2],
            *groups["godot"][:-1],
            *groups["docs"],
            *groups["games"][1:],
            *_asset_steps(python, scratch=scratch),
            Step((python, "-m", "build", "--no-isolation")),
            Step(("stage-gen", "--help")),
            Step(("stage-gen-concept", "models")),
        )
    if scope not in groups:
        raise ValueError(f"unknown verification scope: {scope}")
    return groups[scope]


def run_step(step: Step, environment: dict[str, str]) -> Outcome:
    printable = " ".join(step.command)
    print(f"+ {printable}", flush=True)
    started = time.monotonic()
    try:
        completed = subprocess.run(step.command, cwd=step.cwd, env=environment, check=False)
    except OSError as error:
        print(f"  could not start: {error}", file=sys.stderr, flush=True)
        return Outcome(step, None, time.monotonic() - started)
    return Outcome(step, completed.returncode, time.monotonic() - started)


def report(outcomes: Sequence[Outcome]) -> str:
    width = max(len(" ".join(outcome.step.command)) for outcome in outcomes)
    lines = []
    for outcome in outcomes:
        verdict = "PASS" if outcome.passed else "FAIL"
        code = "-" if outcome.returncode is None else str(outcome.returncode)
        printable = " ".join(outcome.step.command)
        lines.append(f"{verdict}  {outcome.seconds:7.1f}s  exit {code:>3}  {printable:<{width}}")
    failed = [outcome for outcome in outcomes if not outcome.passed]
    total = sum(outcome.seconds for outcome in outcomes)
    summary = (
        f"offline gate: {len(outcomes) - len(failed)} of {len(outcomes)} steps passed "
        f"in {total:.0f}s"
    )
    return "\n".join([*lines, summary])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run credential-free checks for an owned surface")
    parser.add_argument(
        "--scope",
        choices=("product", "viewer", "godot", "games", "apps", "docs", "all"),
        default="product",
    )
    args = parser.parse_args()
    environment = sanitized_environment()
    environment["PATH"] = (
        str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
    )
    with tempfile.TemporaryDirectory(prefix="stage-gen-gate-") as scratch:
        outcomes = [
            run_step(step, environment)
            for step in steps(scratch=Path(scratch).resolve(), scope=args.scope)
        ]
    print()
    print(report(outcomes), flush=True)
    return 0 if all(outcome.passed for outcome in outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
