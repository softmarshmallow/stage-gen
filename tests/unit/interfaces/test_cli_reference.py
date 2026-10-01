"""``command_reference``: the argparse tree the site's CLI reference is written from."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from stage_gen.interfaces.cli import build_parser, command_reference

REPOSITORY = Path(__file__).resolve().parents[3]


def _find(command: dict[str, Any], *path: str) -> dict[str, Any]:
    for name in path:
        command = next(entry for entry in command["commands"] if entry["name"] == name)
    return command


def _argument(command: dict[str, Any], name: str) -> dict[str, Any]:
    return next(entry for entry in command["arguments"] if name in entry["names"])


def test_every_command_is_in_the_reference_once() -> None:
    reference = command_reference()
    assert reference["kind"] == "stage-gen-cli-v1"
    assert reference["prog"] == "stage-gen"
    names = [command["name"] for command in reference["commands"]]
    assert len(names) == len(set(names))
    assert names[:5] == ["list", "show", "plan", "run", "inspect"]
    assert {"view", "example", "catalog", "capability", "models", "env"} <= set(names)
    from stage_gen.workflows._registry import discover

    workflows = [workflow.id for workflow in discover()]
    for verb in ("plan", "run"):
        targets = [command["name"] for command in _find(reference, verb)["commands"]]
        assert targets == [*workflows, "file"]


def test_arguments_carry_their_usage_help_and_defaults() -> None:
    reference = command_reference()
    export = _find(reference, "catalog", "export")
    assert export["usage"].startswith("stage-gen catalog export [-h] --out OUT_DIR")
    out = _argument(export, "--out")
    assert out["required"] and out["metavar"] == "OUT_DIR" and not out["positional"]
    check = _argument(export, "--check")
    assert check["metavar"] is None and check["default"] is None
    assert _argument(_find(reference, "view"), "--port")["default"] == "3000"
    runs = _argument(_find(reference, "view"), "--runs")
    assert runs["repeatable"] and runs["default"] is None
    assert all("-h" not in entry["names"] for entry in export["arguments"])


def test_a_forwarding_workflow_is_marked() -> None:
    run = _find(command_reference(), "run", "character-3d")
    assert run["forwards"] and run["arguments"] == []
    assert not _find(command_reference(), "run", "looping-parallax")["forwards"]


def test_the_reference_does_not_depend_on_the_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLUMNS", "40")
    narrow = command_reference()
    monkeypatch.setenv("COLUMNS", "200")
    assert command_reference() == narrow


def test_the_reference_is_portable_json() -> None:
    text = json.dumps(command_reference())
    assert str(REPOSITORY) not in text and str(Path.home()) not in text


def test_an_absolute_path_default_is_refused() -> None:
    parser = build_parser()
    commands = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    probe = commands.add_parser("probe", help="a command with a private default")
    probe.add_argument("--where", type=Path, default=Path.home() / "private")
    with pytest.raises(ValueError, match="absolute path"):
        command_reference(parser)


def test_every_argument_says_what_it_is() -> None:
    bare: list[str] = []
    # The site renders a recorded default itself, so help that repeats it reads twice.
    echoed: list[str] = []

    def walk(command: dict[str, Any], path: tuple[str, ...]) -> None:
        for argument in command["arguments"]:
            name = f"{' '.join(path)} {'/'.join(argument['names'])}"
            if not argument["help"]:
                bare.append(name)
            elif argument["default"] is not None and "default:" in argument["help"]:
                echoed.append(name)
        for child in command["commands"]:
            walk(child, (*path, child["name"]))

    reference = command_reference()
    walk(reference, (reference["prog"],))
    assert bare == [], "arguments without help: " + ", ".join(bare)
    assert echoed == [], "help repeating its recorded default: " + ", ".join(echoed)
