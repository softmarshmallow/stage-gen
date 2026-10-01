"""Every documented ``stage-gen`` command parses with the real CLI.

A command shown to a reader is a promise: a renamed verb, a dropped flag or a misspelt
workflow id must fail here, not on the reader's machine. Commands are read from fenced
``sh``/``bash`` blocks in README.md, the live docs (``docs/`` without its history roots),
each workflow's ``page.mdx``, ``contract.md`` and example pages, the Godot docs, and each
``workflow.toml`` ``[try]`` table. Each is parsed by ``stage_gen.interfaces.cli.parse``, the
console script's own ``parse_known_args`` path, and never executed.
"""

from __future__ import annotations

import argparse
import re
import shlex
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from stage_gen.interfaces.cli import build_parser, parse

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPOSITORY_ROOT / "src/stage_gen/workflows"
#: History describes what was true when it was written, so its commands are not held to today.
HISTORY_ROOTS = ("docs/decisions/", "docs/plans/", "docs/research/", "docs/media/")
FENCE = re.compile(
    r"^(?P<indent>[ \t]*)```(?P<info>[^\n`]*)\n(?P<body>.*?)^(?P=indent)```", re.M | re.S
)
SHELL_FENCES = {"sh", "bash", "shell", "console"}
ENVIRONMENT = re.compile(r"^[A-Z_][A-Z0-9_]*=")
#: The ``uv run`` options a documented command may carry before ``stage-gen``.
UV_RUN_FLAGS_WITH_VALUE = {"--group", "--extra", "--with", "--python", "--directory"}
COMMAND_SEPARATORS = {"&&", "||", ";", "|"}


@dataclass(frozen=True, slots=True)
class Documented:
    source: str
    arguments: tuple[str, ...]

    def __str__(self) -> str:
        return f"{self.source}: stage-gen {shlex.join(self.arguments)}"


def _documents() -> list[Path]:
    documents = [REPOSITORY_ROOT / "README.md"]
    documents += [
        path
        for path in sorted((REPOSITORY_ROOT / "docs").rglob("*.md"))
        if not path.relative_to(REPOSITORY_ROOT).as_posix().startswith(HISTORY_ROOTS)
    ]
    for pattern in ("*/page.mdx", "*/contract.md", "*/examples/*.mdx"):
        documents += sorted(WORKFLOWS.glob(pattern))
    documents += [
        path
        for path in sorted((REPOSITORY_ROOT / "godot").rglob("*.md"))
        if "docs" in path.relative_to(REPOSITORY_ROOT / "godot").parts[:-1]
        and "history" not in path.parts
    ]
    return documents


def _logical_lines(body: str) -> Iterator[str]:
    """A shell block's lines, with backslash continuations joined."""
    pending = ""
    for line in body.splitlines():
        stripped = line.rstrip()
        if stripped.endswith("\\"):
            pending += stripped[:-1] + " "
            continue
        yield pending + stripped
        pending = ""
    if pending:
        yield pending


def _commands(line: str) -> Iterator[tuple[str, ...]]:
    """The ``stage-gen`` invocations in one shell line, after env assignments and ``uv run``."""
    try:
        tokens = shlex.split(line, comments=True)
    except ValueError:
        return
    command: list[str] = []
    for token in [*tokens, ";"]:
        if token not in COMMAND_SEPARATORS:
            command.append(token)
            continue
        words = command
        command = []
        while words and ENVIRONMENT.match(words[0]):
            words = words[1:]
        if words[:2] == ["uv", "run"]:
            words = words[2:]
            while words and words[0].startswith("--"):
                flag = words.pop(0)
                if flag in UV_RUN_FLAGS_WITH_VALUE and "=" not in flag:
                    words = words[1:]
        if words and words[0] == "stage-gen":
            yield tuple(words[1:])


def documented_commands() -> list[Documented]:
    found: list[Documented] = []
    for document in _documents():
        relative = document.relative_to(REPOSITORY_ROOT).as_posix()
        for fence in FENCE.finditer(document.read_text(encoding="utf-8")):
            if fence.group("info").strip().split(" ")[0] not in SHELL_FENCES:
                continue
            for line in _logical_lines(fence.group("body")):
                found.extend(Documented(relative, command) for command in _commands(line))
    for manifest in sorted(WORKFLOWS.glob("*/workflow.toml")):
        relative = manifest.relative_to(REPOSITORY_ROOT).as_posix()
        table = tomllib.loads(manifest.read_text(encoding="utf-8")).get("try", {})
        for command in table.get("commands", []):
            words = shlex.split(command)
            while words and ENVIRONMENT.match(words[0]):
                words = words[1:]
            assert words[0] == "stage-gen", f"{relative}: [try] command must start with stage-gen"
            found.append(Documented(f"{relative} [try]", tuple(words[1:])))
    return found


DOCUMENTED = documented_commands()
PARSER = build_parser()


def test_the_scan_reads_every_kind_of_source() -> None:
    sources = {command.source for command in DOCUMENTED}
    assert "README.md" in sources
    assert any(source.startswith("docs/") for source in sources)
    assert any(source.endswith("/page.mdx") for source in sources)
    assert any(source.endswith("/contract.md") for source in sources)
    assert any(source.startswith("godot/") for source in sources)
    assert sum(source.endswith("[try]") for source in sources) == len(
        list(WORKFLOWS.glob("*/workflow.toml"))
    )


@pytest.mark.parametrize("command", DOCUMENTED, ids=str)
def test_documented_command_parses_with_the_real_cli(command: Documented) -> None:
    if "--help" in command.arguments or "-h" in command.arguments:
        # A help request parses only as far as the command it asks about; that much must exist.
        arguments = command.arguments[
            : command.arguments.index("--help" if "--help" in command.arguments else "-h")
        ]
        with pytest.raises(SystemExit) as exit_:
            parse((*arguments, "--help"), PARSER)
        assert exit_.value.code == 0, f"{command} asks for help on a command that is not there"
        return
    try:
        args = parse(command.arguments, PARSER)
    except (SystemExit, ValueError) as error:
        pytest.fail(f"{command} does not parse: {error}")
    assert isinstance(args, argparse.Namespace)
    assert getattr(args, "handler", None) is not None, f"{command} names no command"


def test_a_retired_command_fails_the_parse() -> None:
    for retired in (
        ("pipeline", "plan", "file.py:pipeline", "--input", "in"),
        ("universe", "semantic", "--input", "in"),
        ("plan", "movie-sprite", "--cache-dir", "cache"),
    ):
        with pytest.raises((SystemExit, ValueError)):
            parse(retired, PARSER)
