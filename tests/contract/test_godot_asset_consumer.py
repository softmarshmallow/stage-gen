"""The small Godot template consumes an image without any complete-game contract."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path
from types import ModuleType

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "godot/templates/asset_consumer"


def _preparer() -> ModuleType:
    spec = importlib.util.spec_from_file_location("asset_consumer_prepare", TEMPLATE / "prepare.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "consumer"
    shutil.copytree(TEMPLATE, project, ignore=shutil.ignore_patterns(".godot", "content"))
    return project


def _asset(tmp_path: Path) -> tuple[Path, bytes]:
    source = tmp_path / "source.png"
    Image.new("RGBA", (16, 8), (20, 80, 100, 255)).save(source)
    data = source.read_bytes()
    metadata = json.dumps(
        {
            "schema_version": 2,
            "artifact": {
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "media_type": "image/png",
            },
        }
    ).encode()
    Path(f"{source}.meta.json").write_bytes(metadata)
    return source, metadata


def test_consumer_preparation_preserves_media_and_sidecar(tmp_path: Path) -> None:
    project = _project(tmp_path)
    source, metadata = _asset(tmp_path)
    _preparer().prepare_asset(source, project)
    assert (project / "content/preview.png").read_bytes() == source.read_bytes()
    assert (project / "content/preview.png.meta.json").read_bytes() == metadata


def test_refused_provenance_keeps_previous_prepared_content(tmp_path: Path) -> None:
    project = _project(tmp_path)
    source, metadata = _asset(tmp_path)
    prepare = _preparer().prepare_asset
    prepare(source, project)
    original = source.read_bytes()
    Image.new("RGBA", (4, 4), (80, 40, 20, 255)).save(source)
    with pytest.raises(ValueError, match="provenance"):
        prepare(source, project)
    assert (project / "content/preview.png").read_bytes() == original
    assert (project / "content/preview.png.meta.json").read_bytes() == metadata


def test_consumer_refuses_a_symlink_output_directory(tmp_path: Path) -> None:
    project = _project(tmp_path)
    source, _ = _asset(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (project / "content").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="real directory"):
        _preparer().prepare_asset(source, project)
    assert list(outside.iterdir()) == []


def test_godot_scene_loads_prepared_image_without_legacy_runtime(tmp_path: Path) -> None:
    executable = shutil.which("godot")
    if executable is None:
        pytest.skip("Godot is not installed")
    project = _project(tmp_path)
    source, _ = _asset(tmp_path)
    _preparer().prepare_asset(source, project)
    result = subprocess.run(
        [
            executable,
            "--headless",
            "--path",
            str(project),
            "--log-file",
            str(tmp_path / "godot.log"),
            "--script",
            "res://tests/consume.gd",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "asset consumer loaded 16 x 8" in result.stdout
