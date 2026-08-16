#!/usr/bin/env python3
"""Run the complete credential-free Python offline gate."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CREDENTIAL_VARIABLES = ("OPENROUTER_API_KEY", "FAL_KEY")


def sanitized_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    environment = dict(os.environ if source is None else source)
    for variable in CREDENTIAL_VARIABLES:
        environment.pop(variable, None)
    environment["_STAGE_GEN_DISABLE_DOTENV"] = "1"
    return environment


def commands(python: str = sys.executable) -> tuple[tuple[str, ...], ...]:
    return (
        ("ruff", "format", "--check", "."),
        ("ruff", "check", "."),
        ("mypy", "--strict", "src", "tests", "scripts"),
        ("pytest", "-m", "not live"),
        (python, "scripts/check_docs.py"),
        (python, "-m", "build", "--no-isolation"),
        ("stage-gen", "--help"),
        ("stage-gen", "recipes"),
        ("stage-gen", "benchmark", "list"),
        ("stage-gen", "benchmark", "smoke"),
    )


def run_command(command: Sequence[str], environment: dict[str, str]) -> None:
    printable = " ".join(command)
    print(f"+ {printable}", flush=True)
    subprocess.run(command, cwd=REPOSITORY_ROOT, env=environment, check=True)


def main() -> int:
    environment = sanitized_environment()
    try:
        for command in commands():
            run_command(command, environment)
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"offline gate failed: {error}", file=sys.stderr)
        return 1
    print("Python offline gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
