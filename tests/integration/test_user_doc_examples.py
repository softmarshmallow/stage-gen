"""The user guide is the specification: every example project plans as written.

The guide's example projects live in docs/guide/examples; each must expand, validate and
price offline with `gnode plan --check`, exactly as its README runs it, against the
illustrative routes beside them. The blind tests stay in local/gnode/user-docs, and run
where that folder is present.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from gnode import cli

REPOSITORY = Path(__file__).resolve().parents[2]
EXAMPLES = REPOSITORY / "docs/guide/examples"
BLIND_TESTS = REPOSITORY / "local/gnode/user-docs/blind-tests"
ROUTES = EXAMPLES / "routes.yaml"

#: (project folder, the arguments its README plans it with)
EXAMPLE_PROJECTS = (
    ("looping-parallax", ("looping-parallax", "--inputs", "inputs/harbor.yaml")),
    ("concept-gallery", ("concept-gallery", "--inputs", "inputs/tidebell.yaml")),
    ("rigged-character", ("rigged-character", "--inputs", "inputs/wren.yaml")),
    ("game-build/kitewharf/assets", ("level_art.py:build", "--arg", "level=../levels/docks.toml")),
)
BLIND_TEST_PROJECTS = (
    ("voiced-scene", ("voiced-scene", "--inputs", "inputs/one.yaml")),
    ("voiced-scene", ("voiced-scenes", "--inputs", "inputs/scenes.yaml")),
    ("portrait-motion", ("portrait-motion", "--inputs", "inputs/one.yaml")),
    ("portrait-motion", ("portrait-batch", "--inputs", "inputs/batch.yaml")),
)


def _plans(project: Path, arguments: tuple[str, ...]) -> None:
    out, err = io.StringIO(), io.StringIO()
    status = cli.main(
        ["plan", *arguments, "--routes", str(ROUTES), "--check"],
        stdout=out,
        stderr=err,
        cwd=project,
    )
    assert status == 0, out.getvalue() + err.getvalue()


@pytest.mark.parametrize(("folder", "arguments"), EXAMPLE_PROJECTS)
def test_the_guide_example_plans_offline_as_written(
    folder: str, arguments: tuple[str, ...]
) -> None:
    _plans(EXAMPLES / folder, arguments)


@pytest.mark.skipif(not BLIND_TESTS.is_dir(), reason="the blind tests are local")
@pytest.mark.parametrize(("folder", "arguments"), BLIND_TEST_PROJECTS)
def test_the_blind_test_plans_offline_as_written(folder: str, arguments: tuple[str, ...]) -> None:
    _plans(BLIND_TESTS / folder, arguments)
