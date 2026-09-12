"""A copied demo project closes its source dependencies without copying media inputs."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "godot" / "tools" / "package_game_project.py"


def _tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("package_game_project", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", ("bellweather", "iron_petal_unit", "ember_hollow", "the_grain"))
def test_portable_game_has_real_closed_source(tmp_path: Path, name: str) -> None:
    tool = _tool()
    destination = tool.package_project(name, tmp_path / name)
    assert (destination / "main.gd").is_file()
    assert (destination / "gameplay").is_dir()
    assert not any(path.is_symlink() for path in destination.rglob("*"))
    assert (destination / "addons/demo_support/io/run_dir.gd").is_file()
    for unowned in ("inputs", "pipeline", "tests", "assets", "addons/demo_support/testing"):
        assert not (destination / unowned).exists()
    for path in destination.rglob("*.gd"):
        assert path.with_suffix(".gd.uid").is_file()


def test_packaging_never_replaces_an_existing_destination(tmp_path: Path) -> None:
    target = tmp_path / "existing"
    target.mkdir()
    sentinel = target / "user-work.txt"
    sentinel.write_text("keep this")
    with pytest.raises(ValueError, match="already exists"):
        _tool().package_project("bellweather", target)
    assert sentinel.read_text() == "keep this"


def test_packaging_rejects_a_destination_in_maintained_game_sources() -> None:
    tool = _tool()
    with pytest.raises(ValueError, match="outside the maintained game sources"):
        tool.package_project("bellweather", tool.GAMES / "bellweather" / "copied-project")
