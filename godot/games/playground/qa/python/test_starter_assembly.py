from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

PROJECT = Path(__file__).resolve().parents[2]


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "assemble_presentation_starter", PROJECT / "tools/assemble_starter.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCRIPT = _script()


def test_assembly_copies_the_actual_sdk_without_demo_dependencies(tmp_path: Path) -> None:
    destination = tmp_path / "standalone"
    report = SCRIPT.assemble(destination)
    assert (destination / "project.godot").is_file()
    assert (destination / "main.gd").is_file()
    assert not (destination / ".gdignore").exists()
    assert not (destination / "games").exists()
    assert not (destination / "assets").exists()
    assert not (destination / "presentation").exists()
    for relative, expected in report["sdk_files"].items():
        source = PROJECT / "addons/game_presentation" / relative
        copied = destination / "addons/game_presentation" / relative
        assert copied.read_bytes() == source.read_bytes()
        assert hashlib.sha256(copied.read_bytes()).hexdigest() == expected
    serialized = (destination / "assembly.json").read_text()
    assert str(PROJECT) not in serialized
    assert json.loads(serialized) == report
    assert (destination / "addons/game_presentation/actors/presets/manpu.json").is_file()


@pytest.mark.parametrize("existing_content", [False, True])
def test_existing_destination_is_never_replaced(tmp_path: Path, existing_content: bool) -> None:
    destination = tmp_path / "existing"
    destination.mkdir()
    if existing_content:
        (destination / "keep.txt").write_text("keep")
    with pytest.raises(ValueError, match="already exists"):
        SCRIPT.assemble(destination)
    if existing_content:
        assert (destination / "keep.txt").read_text() == "keep"


def test_starter_cannot_be_assembled_inside_the_development_project() -> None:
    with pytest.raises(ValueError, match="outside the development project"):
        SCRIPT.assemble(PROJECT / "never-created-starter-test-output")
    assert not (PROJECT / "never-created-starter-test-output").exists()


def test_source_links_are_refused_and_output_remains_absent(tmp_path: Path) -> None:
    source = tmp_path / "source"
    starter = source / "starter_source"
    sdk = source / "addons/game_presentation"
    starter.mkdir(parents=True)
    sdk.mkdir(parents=True)
    (starter / "project.godot").write_text("config_version=5")
    (starter / "main.gd").write_text("extends Control")
    (sdk / "unsafe.gd").symlink_to(starter / "main.gd")
    output = tmp_path / "result"
    with pytest.raises(ValueError, match="symbolic link"):
        SCRIPT.assemble(output, source)
    assert not output.exists()


def test_cache_and_ignore_markers_are_not_copied(tmp_path: Path) -> None:
    source = tmp_path / "source"
    starter = source / "starter_source"
    sdk = source / "addons/game_presentation"
    starter.mkdir(parents=True)
    sdk.mkdir(parents=True)
    (starter / "project.godot").write_text("config_version=5")
    (starter / "main.gd").write_text("extends Control")
    (starter / ".gdignore").write_text("")
    (sdk / "sample.gd").write_text("extends RefCounted")
    (sdk / ".godot").mkdir()
    (sdk / ".godot/cache").write_text("disposable")
    output = tmp_path / "result"
    SCRIPT.assemble(output, source)
    assert not (output / ".gdignore").exists()
    assert not (output / "addons/game_presentation/.godot").exists()
