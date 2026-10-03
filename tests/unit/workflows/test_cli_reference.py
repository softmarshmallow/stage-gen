"""``command_reference``: gnode's argparse tree, which the site's CLI reference is written from."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from gnode import cli
from stage_gen.workflows._reference import command_reference

REPOSITORY = Path(__file__).resolve().parents[3]


def _find(command: dict[str, Any], *path: str) -> dict[str, Any]:
    for name in path:
        command = next(entry for entry in command["commands"] if entry["name"] == name)
    return command


def _argument(command: dict[str, Any], name: str) -> dict[str, Any]:
    return next(entry for entry in command["arguments"] if name in entry["names"])


def test_every_command_is_in_the_reference_once() -> None:
    reference = command_reference()
    assert reference["kind"] == "gnode-cli-v1"
    assert reference["prog"] == "gnode"
    names = [command["name"] for command in reference["commands"]]
    assert len(names) == len(set(names))
    assert names[:2] == ["plan", "run"]
    assert {"reroll", "pick", "takes", "inspect", "view", "nodes", "doctor"} <= set(names)
    assert [command["name"] for command in _find(reference, "takes")["commands"]] == [
        "list",
        "mv",
    ]


def test_arguments_carry_their_usage_help_and_defaults() -> None:
    reference = command_reference()
    run = _find(reference, "run")
    assert run["usage"].startswith("gnode run [-h] [--inputs INPUTS]")
    deliver = _argument(run, "--deliver")
    assert deliver["repeatable"] and deliver["metavar"] == "OUTPUT=PATH"
    live = _argument(run, "--live")
    assert live["metavar"] is None and live["default"] is None
    view = _find(reference, "view")
    assert _argument(view, "--port")["default"] == "3000"
    assert view["usage"] == "gnode view [-h] [--port PORT] [--no-open] [runs ...]"
    roots = _argument(view, "[runs ...]")
    assert roots["positional"] and roots["repeatable"] and roots["default"] is None
    assert all("-h" not in entry["names"] for entry in run["arguments"])


def test_the_reference_does_not_depend_on_the_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLUMNS", "40")
    narrow = command_reference()
    monkeypatch.setenv("COLUMNS", "200")
    assert command_reference() == narrow


def test_the_reference_is_portable_json() -> None:
    text = json.dumps(command_reference())
    assert str(REPOSITORY) not in text and str(Path.home()) not in text


def test_an_absolute_path_default_is_refused() -> None:
    parser = cli.build_parser()
    commands = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    probe = commands.add_parser("probe", help="a command with a private default")
    probe.add_argument("--where", type=Path, default=Path.home() / "private")
    with pytest.raises(ValueError, match="absolute path"):
        command_reference(parser)


def test_every_command_and_argument_says_what_it_is() -> None:
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
            if not child["summary"]:
                bare.append(" ".join((*path, child["name"])))
            walk(child, (*path, child["name"]))

    reference = command_reference()
    walk(reference, (reference["prog"],))
    assert bare == [], "commands or arguments without help: " + ", ".join(bare)
    assert echoed == [], "help repeating its recorded default: " + ", ".join(echoed)
