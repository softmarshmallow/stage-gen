"""Source publication and declared dependency boundaries, without running Godot."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


def _tool() -> ModuleType:
    path = Path(__file__).parents[1] / "tools/_shared/source_assembly.py"
    spec = importlib.util.spec_from_file_location("godot_source_assembly", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_failed_copy_never_publishes_partial_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = _tool()
    source = tmp_path / "source"
    source.mkdir()
    (source / "one.gd").write_text("extends RefCounted\n")
    destination = tmp_path / "assembled"

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("injected copy failure")

    monkeypatch.setattr(tool.shutil, "copy2", fail)
    with pytest.raises(OSError, match="injected"), tool.staged_destination(destination) as stage:
        tool.copy_files(source, stage, tool.files(source))
    assert not destination.exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["source"]


def test_dependency_links_are_explicit_and_payload_links_refused(tmp_path: Path) -> None:
    tool = _tool()
    addons = tmp_path / "addons"
    owner = addons / "owner"
    owner.mkdir(parents=True)
    shared = tmp_path / "shared"
    shared.mkdir()
    (owner / "sdk.json").write_text(json.dumps({"dependencies": ["shared"]}))
    (addons / "shared").symlink_to(shared, target_is_directory=True)
    (shared / "one.gd").write_text("extends RefCounted\n")
    assert tool.addon_closure(owner) == {"shared": shared, "owner": owner}
    (shared / "unexpected.gd").symlink_to(owner / "sdk.json")
    with pytest.raises(ValueError, match="symbolic link"):
        tool.files(shared)


def test_dependency_cycles_and_parent_references_are_refused(tmp_path: Path) -> None:
    tool = _tool()
    owner = tmp_path / "owner"
    peer = tmp_path / "peer"
    owner.mkdir()
    peer.mkdir()
    (owner / "sdk.json").write_text(json.dumps({"dependencies": ["peer"]}))
    (peer / "sdk.json").write_text(json.dumps({"dependencies": ["owner"]}))
    with pytest.raises(ValueError, match="Cyclic"):
        tool.addon_closure(owner)
    (peer / "sdk.json").write_text(json.dumps({"dependencies": ["../outside"]}))
    with pytest.raises(ValueError, match="Invalid"):
        tool.addon_closure(owner)
