from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def load_check_script() -> ModuleType:
    path = Path(__file__).parents[2] / "scripts" / "check.py"
    spec = importlib.util.spec_from_file_location("stage_gen_check", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
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
        "library/games/bellweather",
        "--genre",
        "runner",
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
    assert ("stage-gen", "dialogue-scene", "generate", "--help") in commands
