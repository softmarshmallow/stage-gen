from __future__ import annotations

import importlib.util
import sys
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
        }
    )
    assert environment == {"PATH": "/bin", "_STAGE_GEN_DISABLE_DOTENV": "1"}
    commands = check.commands("python")
    assert ("pytest", "-m", "not live") in commands
    assert ("ruff", "format", "--check", ".") in commands
    assert ("mypy", "--strict", "src", "tests", "scripts") in commands
    assert ("python", "scripts/check_docs.py") in commands
    # Both reference members and the selected Iron Petal runner plan offline in
    # the gate, so a broken binding table or refused authored input fails here
    # rather than against a provider.
    assert (
        "stage-gen",
        "package",
        "plan",
        "--input",
        "library/games/bellweather",
        "--genre",
        "platformer",
    ) in commands
    assert (
        "stage-gen",
        "package",
        "plan",
        "--input",
        "library/games/iron-petal-unit",
        "--genre",
        "runner",
    ) in commands
    assert ("bun", "test") in commands
    assert ("python", "scripts/validate_game_package.py", "--root", ".") in commands
    # Every other package in the library plans offline too, as a dry run into
    # scratch, or as the offline proof its recipe offers.
    joined = [" ".join(command) for command in commands]
    assert any(
        c.startswith(
            "stage-gen pointclick-room generate --input library/games/clockmakers_attic --dry-run"
        )
        for c in joined
    )
    assert any(
        c.startswith("stage-gen dialogue-scene generate --input library/games/larkfield --dry-run")
        for c in joined
    )
    assert any(
        c.startswith("stage-gen dialogue-scene generate --input library/games/the_grain --dry-run")
        for c in joined
    )
    assert any(
        c.startswith("stage-gen universe semantic --input library/games/lantern_ferry --dry-run")
        for c in joined
    )
    assert ("stage-gen", "scenario", "check", "--input", "library/games/the_grain") in commands
    assert ("stage-gen", "case", "check", "--input", "library/games/the_grain") in commands


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
