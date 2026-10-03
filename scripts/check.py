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
    "godot/packages/scenario_runtime/authoring/src",
    "godot/games/_shared/python/src",
    "godot/games/bellweather/pipeline/src",
    "godot/games/iron_petal_unit/pipeline/src",
    "godot/games/ember_hollow/pipeline/src",
    "godot/games/the_grain/pipeline/src",
    "godot/tools/python/src",
)
#: Games built with gnode: each one's builder and node modules are typed in their own run,
#: because node modules are top-level files whose names would collide across projects.
GNODE_GAME_PROJECTS = (
    "godot/games/iron_petal_unit",
    "godot/games/bellweather",
    "godot/games/the_grain",
    "godot/games/ember_hollow",
)
#: The builder a one-builder gnode game plans from its own folder.
BUILDER = "pipeline/workflow.py:build"
#: Each gnode game's builders, the packages each one plans offline, and any other arguments.
GNODE_GAME_PLANS: tuple[tuple[str, tuple[tuple[str, str, tuple[str, ...]], ...]], ...] = (
    ("iron_petal_unit", ((BUILDER, "inputs", ()),)),
    ("bellweather", ((BUILDER, "inputs/default", ()), (BUILDER, "inputs/waves", ()))),
    (
        "the_grain",
        (
            ("pipeline/workflow.py:room", "inputs/rooms/window", ()),
            ("pipeline/workflow.py:room", "inputs/rooms/motor_court", ()),
            ("pipeline/workflow.py:scene", "inputs", ()),
        ),
    ),
    (
        "ember_hollow",
        tuple(
            (BUILDER, "inputs", ("--arg", f"scope={scope}"))
            for scope in ("minimal", "props", "actors", "full")
        ),
    ),
)
GAME_TYPED_TOOLS = (
    "godot/games/bellweather/tools/author_terrain.py",
    "godot/games/bellweather/tools/design_map.py",
    "godot/games/bellweather/tools/prove_climbable_bands.py",
    "godot/games/bellweather/tools/render_asset_scale_figures.py",
    "godot/tools/parity_diff.py",
    "godot/tools/render_terrain_atlas_qa.py",
    "godot/tools/validate_game_package.py",
    "godot/tools/write_game_contract_identities.py",
    "godot/tools/write_game_graph_contract.py",
)


def _gnode_game_typechecks() -> tuple[Step, ...]:
    return tuple(
        Step(("mypy", "--strict", f"{game}/pipeline/workflow.py", f"{game}/pipeline/nodes"))
        for game in GNODE_GAME_PROJECTS
    )


def _game_steps(python: str, *, scratch: Path) -> tuple[Step, ...]:
    """Exercise game-owned preparation entry points without provider work."""
    result = [
        # The Grain's script proves its case; its rooms and scene are planned below.
        Step((python, "godot/games/the_grain/pipeline/prepare.py")),
    ]
    # A game built with gnode: its node types are locked and its builders plan each of its
    # packages, offline, from the game's folder.
    for game, plans in GNODE_GAME_PLANS:
        home = REPOSITORY_ROOT / "godot/games" / game
        result.append(Step(("gnode", "lock", "--check"), cwd=home))
        result.extend(
            Step(
                ("gnode", "plan", builder, "--arg", f"package={package}", *extra, "--check"),
                cwd=home,
            )
            for builder, package, extra in plans
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
    result.append(Step(("demo-games", "case", "bundle", "--help")))
    return tuple(result)


CHARACTER_SAMPLE = "src/stage_gen/workflows/character_3d/inputs/sample/inputs.yaml"


def _asset_steps(python: str, *, scratch: Path) -> tuple[Step, ...]:
    """Run a real local workflow through gnode, check every workflow file's lock, and plan
    every workflow whose calls are all paid."""
    from stage_gen.workflows._registry import discover

    parallax = "src/stage_gen/workflows/looping_parallax/inputs/supplied_layers"
    inputs = scratch / "parallax-inputs"
    movie = "src/stage_gen/workflows/movie_sprite/inputs/supplied_clip"
    clip = scratch / "movie-sprite-inputs"
    portrait = "src/stage_gen/workflows/portrait_motion/inputs/make_inputs.py"
    face = scratch / "portrait-inputs"
    # A scratch folder with no gnode.yaml: the runs and their cache stay inside it.
    project = scratch / "parallax-project"
    files = [w for w in discover() if w.root.joinpath("workflow.yaml").is_file()]
    return (
        *(Step(("gnode", "lock", workflow.id, "--check")) for workflow in files),
        Step((python, f"{parallax}/make_inputs.py", str(inputs))),
        Step((python, "-c", f"import pathlib; pathlib.Path({str(project)!r}).mkdir()")),
        Step(
            ("gnode", "run", "looping-parallax", "--inputs", str(inputs / "inputs.yaml")),
            cwd=project,
        ),
        Step(("gnode", "inspect", "looping-parallax", "--verify"), cwd=project),
        # movie-sprite: the paid take is only planned; the supplied clip is finished for free.
        Step((python, f"{movie}/make_inputs.py", str(clip))),
        Step(("gnode", "plan", "movie-sprite", "--inputs", str(clip / "take.yaml")), cwd=project),
        Step(("gnode", "run", "movie-sprite", "--inputs", str(clip / "clip.yaml")), cwd=project),
        Step(("gnode", "inspect", "movie-sprite", "--verify"), cwd=project),
        # portrait-motion: every call is paid, so both paths are planned; pytest runs them on
        # the sample's stand-in answers.
        Step((python, portrait, str(face))),
        *(
            Step(("gnode", "plan", "portrait-motion", "--inputs", str(face / name)), cwd=project)
            for name in ("face.yaml", "whole.yaml")
        ),
        # gnode's published document schemas, and the language-neutral conformance suite that
        # any gnode implementation must pass, run through the gnode command only.
        Step((python, "scripts/write_gnode_schemas.py", "--check")),
        Step((python, "tests/conformance/run.py")),
        # universe: the plan prices the world phase exactly and the gallery at its ceiling.
        Step(
            (
                "gnode",
                "plan",
                "universe",
                "--inputs",
                str(
                    REPOSITORY_ROOT
                    / "src/stage_gen/workflows/universe/inputs/lantern_ferry/inputs.yaml"
                ),
                "--check",
            ),
            cwd=project,
        ),
        # character-3d: every agent, mesh and rig call is paid, and its run needs Blender; the
        # committed brief is planned, and pytest runs the graph on stand-ins.
        Step(
            (
                "gnode",
                "plan",
                "character-3d",
                "--inputs",
                str(REPOSITORY_ROOT / CHARACTER_SAMPLE),
            ),
            cwd=project,
        ),
        Step((python, "scripts/write_model_policy_snapshot.py")),
        Step(("gnode", "--help")),
        Step(
            (
                python,
                "scripts/catalog.py",
                "--check",
                "--allow-missing-examples",
                "--out",
                str(scratch / "catalog"),
            )
        ),
    )


def steps(
    python: str = sys.executable, *, scratch: Path, scope: str = "product"
) -> tuple[Step, ...]:
    """Owned gates; the default product gate needs neither Bun nor Godot."""
    from scripts.test_ownership import paths_for

    product_tests = paths_for(REPOSITORY_ROOT, "product")
    groups: dict[str, tuple[Step, ...]] = {
        "product": (
            Step(
                (
                    "ruff",
                    "format",
                    "--check",
                    "src",
                    "scripts",
                    "docs/sdk/pipelines",
                    *product_tests,
                )
            ),
            Step(("ruff", "check", "src", "scripts", "docs/sdk/pipelines", *product_tests)),
            Step(("mypy", "--strict", "src")),
            Step(("pytest", "-m", "not live", *product_tests)),
            Step((python, "-m", "build", "--no-isolation")),
            *_asset_steps(python, scratch=scratch),
        ),
        "web": (
            Step(("bun", "run", "check"), WEB_ROOT),
            Step(("bun", "test"), WEB_ROOT),
            # The static site, from the catalog and whatever the example store holds.
            Step((python, "scripts/site.py", "build", "--allow-missing-examples")),
            Step(("pytest", "-m", "not live", *paths_for(REPOSITORY_ROOT, "web"))),
        ),
        "godot": (
            Step((python, "godot/tools/check.py")),
            Step(("pytest", "-m", "not live", *paths_for(REPOSITORY_ROOT, "godot"))),
        ),
        "games": (
            Step(("pytest", "-m", "not live", *paths_for(REPOSITORY_ROOT, "games"))),
            *_gnode_game_typechecks(),
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
                    "docs/sdk/pipelines",
                )
            ),
            Step(("pytest", "-m", "not live")),
            *groups["web"][:3],
            *groups["godot"][:-1],
            *groups["docs"],
            *groups["games"][1:],
            *_asset_steps(python, scratch=scratch),
            Step((python, "-m", "build", "--no-isolation")),
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
        choices=("product", "web", "godot", "games", "apps", "docs", "all"),
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
