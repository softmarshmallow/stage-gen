"""`stage-gen case check`: the CLI surface over the case container.

It lives beside the contract rather than in `tests/integration/` because the
fixture it needs is the case package builder next door, and `tests/integration/`
is not a package - the same reason the scenario component's own CLI-shaped checks
sit with their fixtures. The command itself is admission with no event loop, no
config, and no provider: it never needs one.
"""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest

from stage_gen.interfaces.cli import build_parser, main

from .package import write_case_package


def test_the_parser_declares_the_case_command() -> None:
    arguments = build_parser().parse_args(["case", "check", "--input", "."])

    assert arguments.command == "case"
    assert arguments.case_command == "check"
    assert arguments.structure_only is False


def test_case_cli_proves_the_container_and_binds_every_leaf(tmp_path: Path) -> None:
    write_case_package(tmp_path)
    output = StringIO()

    assert main(["case", "check", "--input", str(tmp_path)], stdout=output) == 0

    report = json.loads(output.getvalue())
    assert report["game_id"] == "testcase"
    case = report["cases"][0]
    assert case["admitted"] is True
    assert case["bound"] is True
    assert case["terminals"] == {"b_statements": ["b_office", "b_motor_court", "b_statements"]}
    # The crossing, as the CLI reports it: the room exports the fact and the
    # closing scenario imports the same identifier.
    assert "rang_the_bell" in case["leaves"]["b_motor_court"]["exports"]
    assert case["leaves"]["b_statements"]["imports"] == ["rang_the_bell"]
    assert case["facts"]["window_before"]["establishment"] == "defaults_false"


def test_case_cli_structure_only_proves_a_case_whose_leaves_do_not_exist_yet(
    tmp_path: Path,
) -> None:
    """A writer authors the container before all six movements are written."""

    write_case_package(tmp_path, write_leaves=False)
    output = StringIO()

    assert (
        main(
            ["case", "check", "--input", str(tmp_path), "--structure-only"],
            stdout=output,
        )
        == 0
    )
    assert json.loads(output.getvalue())["cases"][0]["bound"] is False
    # Without the escape hatch the same package is refused, because the leaves it
    # names are not there to be proven.
    assert main(["case", "check", "--input", str(tmp_path)], stdout=StringIO()) != 0


def test_case_cli_refuses_a_case_the_catalog_does_not_hold(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_case_package(tmp_path)

    assert (
        main(
            ["case", "check", "--input", str(tmp_path), "--case", "episode_two"], stdout=StringIO()
        )
        != 0
    )
    assert "is not in" in capsys.readouterr().err
