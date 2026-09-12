# test-owner: product
from __future__ import annotations

import importlib.util
import shlex
import sys
import tomllib
from pathlib import Path
from types import ModuleType


def load_check_script() -> ModuleType:
    path = Path(__file__).parents[2] / "scripts" / "check.py"
    spec = importlib.util.spec_from_file_location("stage_gen_check", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: dataclasses resolve their annotations through
    # sys.modules, and the gate script declares two.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_offline_gate_removes_provider_credentials_and_lists_required_checks() -> None:
    check = load_check_script()
    environment = check.sanitized_environment(
        {
            "PATH": "/bin",
            "OPENAI_API_KEY": "openai",
            "OPENROUTER_API_KEY": "openrouter",
            "FAL_KEY": "fal",
            "ELEVENLABS_API_KEY": "elevenlabs",
            "TRIPO_API_KEY": "tripo",
        }
    )
    assert environment == {"PATH": "/bin", "_STAGE_GEN_DISABLE_DOTENV": "1"}
    commands = check.commands("python", scope="all")
    assert ("pytest", "-m", "not live") in commands
    assert ("ruff", "format", "--check", ".") in commands
    typecheck = next(command for command in commands if command[0] == "mypy")
    assert typecheck[:5] == ("mypy", "--strict", "src", "tests", "scripts")
    root = Path(__file__).parents[2]
    project = tomllib.loads((root / "pyproject.toml").read_text())
    members = project["tool"]["uv"]["workspace"]["members"]
    assert {member + "/src" for member in members if member.startswith("godot/")} <= set(typecheck)
    assert all((root / target).exists() for target in typecheck[2:])
    # The copyable template retains its existing typed script; game-local
    # wrappers are exercised as commands, avoiding multiple modules named prepare.
    assert [target for target in typecheck if target.endswith("prepare.py")] == [
        "godot/templates/asset_consumer/prepare.py"
    ]
    assert ("python", "scripts/check_docs.py") in commands
    assert ("python", "scripts/write_model_policy_snapshot.py") in commands
    assert ("python", "godot/tools/write_game_model_policy_snapshot.py") in commands
    assert ("bun", "test") in commands
    # Godot owns discovery, fixture preparation and the different native adapters.
    # The root gate delegates without maintaining a second project/test roster.
    assert commands.count(("python", "godot/tools/check.py")) == 1
    assert not any("godot/tools/run_native_suite.py" in command for command in commands)
    assert check.commands("python", scope="godot")[0] == ("python", "godot/tools/check.py")


def test_games_gate_exercises_local_defaults_variants_and_explicit_sources() -> None:
    check = load_check_script()
    commands = check.commands("python", scope="games")
    game_scripts = [
        command
        for command in commands
        if command[0] == "python" and command[1].endswith("/pipeline/prepare.py")
    ]
    plans = [command for command in game_scripts if "--plan" in command]
    assert len(plans) == 7
    assert {command[1].split("/")[2] for command in plans} == {
        "bellweather",
        "iron_petal_unit",
        "ember_hollow",
        "the_grain",
    }
    assert any(command[-2:] == ("--variant", "waves") for command in plans)
    grain_modes = {command[-1] for command in plans if command[1].split("/")[2] == "the_grain"}
    assert grain_modes == {"case", "room", "dialogue"}
    dry_runs = [command for command in game_scripts if "--dry-run" in command]
    assert len(dry_runs) == 3
    assert {command[1].split("/")[2] for command in dry_runs} == {"the_grain", "ember_hollow"}
    assert all("--output" in command and "--cache-dir" in command for command in dry_runs)
    assert all("--live" not in command for command in commands)
    validators = [
        command
        for command in commands
        if command[:2] == ("python", "godot/tools/validate_game_package.py")
    ]
    assert {command[3] for command in validators if command[2] == "--input"} == {
        "godot/games/bellweather/inputs/default",
        "godot/games/bellweather/inputs/waves",
        "godot/games/iron_petal_unit/inputs",
    }
    assert (
        "demo-games",
        "scenario",
        "check",
        "--input",
        "godot/games/the_grain/inputs",
    ) in commands
    assert ("demo-games", "case", "bundle", "--help") in commands
    assert ("demo-games", "oblique-survival", "import-run", "--help") in commands
    assert all("legacy" not in command and "main.toml" not in command for command in commands)


def test_ci_uses_the_same_typecheck_surface_as_the_aggregate_gate() -> None:
    check = load_check_script()
    commands = check.commands("python", scope="all")
    typecheck = next(command for command in commands if command[0] == "mypy")
    workflow = (Path(__file__).parents[2] / ".github/workflows/gate.yml").read_text()
    body = workflow.split("      - name: Typecheck product and optional consumers\n", 1)[1]
    lines = body.splitlines()[1:]
    script_lines = []
    for line in lines:
        if not line.startswith("          "):
            break
        script_lines.append(line.strip())
    assert tuple(shlex.split(" ".join(script_lines))) == ("uv", "run", "--all-groups", *typecheck)


def test_the_gate_reports_every_step_rather_than_stopping_at_the_first() -> None:
    check = load_check_script()
    outcomes = [
        check.Outcome(check.Step(("ruff", "format", "--check", ".")), 1, 0.5),
        check.Outcome(check.Step(("pytest",)), 0, 12.0),
        check.Outcome(check.Step(("bun", "test")), None, 0.0),
    ]
    table = check.report(outcomes)
    lines = table.splitlines()
    assert lines[0].startswith("FAIL") and "exit   1" in lines[0]
    assert lines[1].startswith("PASS")
    assert lines[2].startswith("FAIL") and "exit   -" in lines[2]
    assert lines[-1] == "offline gate: 1 of 3 steps passed in 12s"


def test_product_gate_does_not_require_optional_consumers() -> None:
    check = load_check_script()
    commands = check.commands("python")
    assert all(command[0] != "bun" for command in commands)
    assert all(not item.startswith("godot/") for command in commands for item in command)
    assert ("mypy", "--strict", "src") in commands
    tests = next(command for command in commands if command[0] == "pytest")
    assert len(tests) > 3
    assert not any("concept_studio" in item or "test_godot_" in item for item in tests)


def test_owned_test_gates_partition_every_offline_test() -> None:
    from scripts.test_ownership import TestOwner, paths_for
    from scripts.test_ownership import test_owners as collect_owners

    root = Path(__file__).parents[2]
    owned = collect_owners(root)
    expected = {
        str(path.relative_to(root))
        for path in (root / "tests").rglob("test_*.py")
        if not path.is_relative_to(root / "tests/live")
    }
    assert set(owned) == expected
    scopes: tuple[TestOwner, ...] = ("product", "games", "godot", "viewer", "apps")
    groups = [set(paths_for(root, scope)) for scope in scopes]
    assert set.union(*groups) == expected
    assert sum(map(len, groups)) == len(expected)
