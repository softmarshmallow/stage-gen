#!/usr/bin/env python3
"""Run the complete credential-free offline gate, and report every step.

The gate used to stop at its first failure. That is the wrong shape for a
gate that a human reads once a day: a formatting drift at step one hid a
type error at step three and a failing contract test at step four for days,
because "it stopped" and "it passed" looked the same from a distance. Every
step now runs, every step is timed, and the verdict is a table.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = REPOSITORY_ROOT / "web"
CREDENTIAL_VARIABLES = (
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "FAL_KEY",
    "ELEVENLABS_API_KEY",
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


def commands(python: str = sys.executable) -> tuple[tuple[str, ...], ...]:
    """The repository-rooted command list, kept for callers that read it as data."""

    return tuple(step.command for step in steps(python, scratch=Path("/dev/null")))


def steps(python: str = sys.executable, *, scratch: Path) -> tuple[Step, ...]:
    """Every step of the gate, in the order it runs.

    ``scratch`` receives the dry-run outputs: each recipe insists on a new
    immutable output directory, so an offline plan of a package is a fake run
    into a directory nobody keeps.
    """

    def dry_run(*command: str, name: str) -> Step:
        # A dry run writes its own fake cache; it goes to scratch, never to the real
        # cache root every paid checkpoint restores from.
        return Step(
            (
                *command,
                "--dry-run",
                "--cache-dir",
                str(scratch / "cache"),
                "--output",
                str(scratch / name),
            )
        )

    return (
        Step(("ruff", "format", "--check", ".")),
        Step(("ruff", "check", ".")),
        Step(("mypy", "--strict", "src", "tests", "scripts")),
        Step(("pytest", "-m", "not live")),
        # The web runtime is a consumer of every manifest the pipeline publishes;
        # its suite runs in under a second and was in no gate at all.
        Step(("bun", "run", "check"), cwd=WEB_ROOT),
        Step(("bun", "test"), cwd=WEB_ROOT),
        Step((python, "scripts/check_docs.py")),
        Step((python, "-m", "build", "--no-isolation")),
        Step((python, "scripts/validate_game_package.py", "--root", ".")),
        Step(("stage-gen", "--help")),
        # Every package in the library plans offline: a route the binding table
        # cannot serve, or an authored input a resolver refuses, fails here
        # rather than against a provider. The two game-contract packages plan
        # through the package selector; the room, scene, universe and case
        # packages plan from their own roots, as a dry run into scratch.
        Step(
            (
                "stage-gen",
                "package",
                "plan",
                "--input",
                "library/games/bellweather",
                "--genre",
                "platformer",
            )
        ),
        # The wave variant plans too, and it is the one package in the library whose
        # gameplay contract carries the two optional round tables: a `[score]` or
        # `[timers]` the resolver would refuse never reaches a runtime family.
        Step(
            (
                "stage-gen",
                "package",
                "plan",
                "--input",
                "library/games/bellweather-waves",
                "--genre",
                "platformer",
            )
        ),
        Step(
            (
                "stage-gen",
                "package",
                "plan",
                "--input",
                "library/games/iron-petal-unit",
                "--genre",
                "runner",
            )
        ),
        dry_run(
            "stage-gen",
            "pointclick-room",
            "generate",
            "--input",
            "library/games/clockmakers_attic",
            name="clockmakers-attic",
        ),
        dry_run(
            "stage-gen",
            "dialogue-scene",
            "generate",
            "--input",
            "library/games/larkfield",
            name="larkfield",
        ),
        dry_run(
            "stage-gen",
            "dialogue-scene",
            "generate",
            "--input",
            "library/games/the_grain",
            name="the-grain-scene",
        ),
        dry_run(
            "stage-gen",
            "universe",
            "semantic",
            "--input",
            "library/games/lantern_ferry",
            name="lantern-ferry",
        ),
        # The survival package is its own root too, and the widest scope is the
        # one that plans every node the recipe can build.
        dry_run(
            "stage-gen",
            "oblique-survival",
            "generate",
            "--input",
            "library/games/ember-hollow",
            name="ember-hollow",
        ),
        Step(("stage-gen", "scenario", "check", "--input", "library/games/bellweather")),
        Step(("stage-gen", "scenario", "check", "--input", "library/games/larkfield")),
        Step(("stage-gen", "scenario", "check", "--input", "library/games/the_grain")),
        Step(("stage-gen", "case", "check", "--input", "library/games/the_grain")),
        Step(("stage-gen", "case", "bundle", "--help")),
        Step(("stage-gen", "universe", "gallery", "--help")),
        # The two provider-free survival commands the dry run does not reach.
        Step(("stage-gen", "oblique-survival", "import-run", "--help")),
    )


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
    environment = sanitized_environment()
    with tempfile.TemporaryDirectory(prefix="stage-gen-gate-") as scratch:
        outcomes = [run_step(step, environment) for step in steps(scratch=Path(scratch))]
    print()
    print(report(outcomes), flush=True)
    return 0 if all(outcome.passed for outcome in outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
