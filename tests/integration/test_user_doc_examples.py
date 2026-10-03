"""The user documentation is the specification: every example project plans as written.

The guide and its example projects live in local/gnode/user-docs until they are published;
where that folder is present, each project must expand, validate and price offline with
`gnode plan --check`, exactly as its README runs it.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from gnode import cli

USER_DOCS = Path(__file__).resolve().parents[2] / "local/gnode/user-docs"

#: (project folder, the arguments its README plans it with)
PROJECTS = (
    ("examples/looping-parallax", ("looping-parallax", "--inputs", "inputs/harbor.yaml")),
    ("examples/concept-gallery", ("concept-gallery", "--inputs", "inputs/tidebell.yaml")),
    ("examples/rigged-character", ("rigged-character", "--inputs", "inputs/wren.yaml")),
    (
        "examples/game-build/kitewharf/assets",
        ("level_art.py:build", "--arg", "level=../levels/docks.toml"),
    ),
    ("blind-tests/voiced-scene", ("voiced-scene", "--inputs", "inputs/one.yaml")),
    ("blind-tests/voiced-scene", ("voiced-scenes", "--inputs", "inputs/scenes.yaml")),
    ("blind-tests/portrait-motion", ("portrait-motion", "--inputs", "inputs/one.yaml")),
    ("blind-tests/portrait-motion", ("portrait-batch", "--inputs", "inputs/batch.yaml")),
)


@pytest.mark.skipif(not USER_DOCS.is_dir(), reason="the user docs are local until published")
@pytest.mark.parametrize(("folder", "arguments"), PROJECTS)
def test_the_example_plans_offline_as_written(folder: str, arguments: tuple[str, ...]) -> None:
    project = USER_DOCS / folder
    routes = USER_DOCS / "routes.yaml"
    out, err = io.StringIO(), io.StringIO()
    status = cli.main(
        ["plan", *arguments, "--routes", str(routes), "--check"],
        stdout=out,
        stderr=err,
        cwd=project,
    )
    assert status == 0, out.getvalue() + err.getvalue()
