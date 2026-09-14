"""Independent-consumer assembly, without providers or prepared game content."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

PACKAGE = Path(__file__).resolve().parents[2]


def _tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "movie_sprite_actor_assembly", PACKAGE / "tools/assemble_standalone.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TOOL = _tool()


def test_actual_payload_and_dependency_are_copied_with_hash_uid_and_license_closure(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "independent"
    report = TOOL.assemble(destination)
    assert set(report["dependency_files"]) == {"content_io"}
    assert (destination / "project.godot").is_file()
    assert (destination / "main.gd").is_file()
    assert (destination / "fixture_factory.gd").is_file()
    assert not (destination / "games").exists()
    assert not (destination / "assets").exists()
    assert not (destination / ".godot").exists()
    assert not (destination / ".gdignore").exists()
    source_by_name = TOOL.addon_closure(PACKAGE / TOOL.SDK_PATH)
    manifests = {"movie_sprite_actor": report["sdk_files"], **report["dependency_files"]}
    all_uids: list[str] = []
    for name, hashes in manifests.items():
        installed = destination / "addons" / name
        assert (installed / "LICENSE").is_file()
        assert (installed / "sdk.json").is_file()
        for relative, digest in hashes.items():
            copied = installed / relative
            assert not copied.is_symlink()
            assert copied.read_bytes() == (source_by_name[name] / relative).read_bytes()
            assert hashlib.sha256(copied.read_bytes()).hexdigest() == digest
            if copied.suffix in {".gd", ".gdshader"}:
                uid = copied.with_suffix(copied.suffix + ".uid")
                assert uid.is_file()
                all_uids.append(uid.read_text().strip())
                source = copied.read_text()
                assert "res://games/" not in source
                assert "res://diagnostics/" not in source
                assert "afterlight" not in source.lower()
    assert len(all_uids) == len(set(all_uids))
    assert all(uid.startswith("uid://") for uid in all_uids)
    for relative, digest in report["example_files"].items():
        assert hashlib.sha256((destination / relative).read_bytes()).hexdigest() == digest
    assert not any(path.is_symlink() for path in destination.rglob("*"))
    serialized = (destination / "assembly.json").read_text()
    assert str(PACKAGE) not in serialized
    assert json.loads(serialized) == report


@pytest.mark.parametrize("occupied", [False, True])
def test_existing_destination_is_preserved(tmp_path: Path, occupied: bool) -> None:
    destination = tmp_path / "existing"
    destination.mkdir()
    if occupied:
        (destination / "keep.txt").write_text("keep")
    with pytest.raises(ValueError, match="already exists"):
        TOOL.assemble(destination)
    if occupied:
        assert (destination / "keep.txt").read_text() == "keep"


def test_output_cannot_enter_package_or_dependency() -> None:
    for root in TOOL.addon_closure(PACKAGE / TOOL.SDK_PATH).values():
        output = root / "never-created-independent-consumer"
        with pytest.raises(ValueError, match="outside the development package"):
            TOOL.assemble(output)
        assert not output.exists()


def _synthetic_package(root: Path) -> Path:
    package = root / "package"
    addon = package / "addons/movie_sprite_actor"
    addon.mkdir(parents=True)
    (addon / "sdk.json").write_text(json.dumps({"dependencies": []}))
    (addon / "actor.gd").write_text("extends Node2D\n")
    example = package / "examples/standalone"
    example.mkdir(parents=True)
    (example / "project.godot").write_text("config_version=5\n")
    (example / "main.gd").write_text("extends Node2D\n")
    (example / "fixture_factory.gd").write_text("extends RefCounted\n")
    return package


def test_source_symlink_refusal_leaves_no_output(tmp_path: Path) -> None:
    package = _synthetic_package(tmp_path)
    (package / "addons/movie_sprite_actor/linked.gd").symlink_to(
        package / "examples/standalone/main.gd"
    )
    output = tmp_path / "consumer"
    with pytest.raises(ValueError, match="symbolic link"):
        TOOL.assemble(output, package)
    assert not output.exists()


def test_disposable_editor_cache_and_ignore_markers_are_omitted(tmp_path: Path) -> None:
    package = _synthetic_package(tmp_path)
    example = package / "examples/standalone"
    (example / ".gdignore").write_text("")
    (example / ".godot").mkdir()
    (example / ".godot/cache").write_text("cache")
    output = tmp_path / "consumer"
    TOOL.assemble(output, package)
    assert not (output / ".gdignore").exists()
    assert not (output / ".godot").exists()


def test_failed_copy_does_not_publish_partial_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _synthetic_package(tmp_path)
    output = tmp_path / "consumer"

    def fail(*args: object, **kwargs: object) -> dict[str, str]:
        raise OSError("injected copy failure")

    monkeypatch.setattr(TOOL, "copy_files", fail)
    with pytest.raises(OSError, match="injected copy failure"):
        TOOL.assemble(output, package)
    assert not output.exists()


def _checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "movie_sprite_actor_check", PACKAGE / "tools/check_standalone.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("fault", ["missing", "failed", "wrong_mode", "partial", "script_error"])
def test_runner_rejects_missing_or_incomplete_success_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    checker = _checker()
    monkeypatch.setattr(checker.shutil, "which", lambda _engine: "/synthetic/godot")

    def fake_run(command: list[str], **kwargs: object) -> object:
        captures = Path(command[command.index("--capture-dir") + 1])
        captures.mkdir(parents=True)
        if fault != "missing":
            report = {
                "status": "failed" if fault == "failed" else "passed",
                "errors": [],
                "pixel_checks_executed": fault == "wrong_mode",
                "checks": 1 if fault == "partial" else 15,
                "renderer": "headless",
            }
            (captures / "verification.json").write_text(json.dumps(report))
        return checker.subprocess.CompletedProcess(
            command, 0, "SCRIPT ERROR: stopped" if fault == "script_error" else "", ""
        )

    monkeypatch.setattr(checker.subprocess, "run", fake_run)
    with pytest.raises(ValueError):
        checker.check("godot", capture_dir=tmp_path / "proof")


def test_runner_preserves_existing_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checker = _checker()
    monkeypatch.setattr(checker.shutil, "which", lambda _engine: "/synthetic/godot")
    captures = tmp_path / "proof"
    captures.mkdir()
    (captures / "keep.txt").write_text("keep")
    with pytest.raises(ValueError, match="already exists"):
        checker.check("godot", capture_dir=captures)
    assert (captures / "keep.txt").read_text() == "keep"
