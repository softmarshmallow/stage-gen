"""A node type's source is named the same wherever its project and packages sit.

A source package kept inside the project, or a project kept inside a source package, is
named from the nearer of the two, so ``gnode.lock`` pins the same source in any checkout.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
import yaml

from gnode import cli
from tests.unit.gnode.workflow._project import write

STAMP = """
from gnode import Ctx, node
import {package}


@node("stamp", params={{"text": str}}, outputs={{"text": "text"}}, version=1)
def stamp(ctx: Ctx) -> dict:
    return {{"text": ctx.out.text({package}.VALUE + ctx.params["text"])}}
"""


def _lock(root: Path) -> dict[str, str]:
    out, err = io.StringIO(), io.StringIO()
    assert cli.main(["lock"], stdout=out, stderr=err, cwd=root) == 0, err.getvalue()
    locked = yaml.safe_load((root / "gnode.lock").read_text(encoding="utf-8"))["nodes"]
    assert isinstance(locked, dict)
    return locked


def test_a_source_package_kept_inside_the_project_locks_as_it_does_outside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "game/pipeline/src"
    write(source, {"kitewharf_tools/__init__.py": "VALUE = 'kite '\n"})
    monkeypatch.syspath_prepend(str(source))
    project = {
        "gnode.yaml": "gnode: project/v1\nsources: [kitewharf_tools]\n",
        "nodes/stamps.py": STAMP.format(package="kitewharf_tools"),
    }

    inside = _lock(write(tmp_path / "game", project))
    elsewhere = _lock(write(tmp_path / "copy", project))

    assert inside == elsewhere


def test_a_project_kept_inside_a_source_package_names_its_own_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path / "src", {"kitewharf_app/__init__.py": "VALUE = 'app '\n"})
    monkeypatch.syspath_prepend(str(tmp_path / "src"))
    project = {
        "gnode.yaml": "gnode: project/v1\nsources: [kitewharf_app]\n",
        "nodes/stamps.py": STAMP.format(package="kitewharf_app"),
    }

    inside = _lock(write(tmp_path / "src/kitewharf_app/workflows/art", project))
    elsewhere = _lock(write(tmp_path / "copy", project))

    assert list(inside) == ["nodes/stamps.py#stamp@1"]
    assert inside == elsewhere
