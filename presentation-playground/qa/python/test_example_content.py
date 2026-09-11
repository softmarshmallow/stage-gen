"""Offline file-boundary tests for the host-specific prepared-content copier."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "example_content", Path(__file__).parents[2] / "tools/prepare_example_content.py"
)
assert SPEC and SPEC.loader
content = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(content)


def fixture_project(root: Path) -> Path:
    root.mkdir()
    voice = root / "games/bishoujo_afterlight/voice"
    voice.mkdir(parents=True)
    (voice / "manifest.json").write_text(
        json.dumps(
            {
                "lines": {
                    "line": {
                        "en": {
                            "path": "res://clips/line.mp3",
                            "provenance_path": "clips/line.mp3.meta.json",
                        }
                    }
                }
            }
        )
    )
    clips = root / "clips"
    clips.mkdir()
    (clips / "line.mp3").write_bytes(b"prepared bytes")
    (clips / "line.mp3.meta.json").write_text('{"rights":"fixture"}')
    assets = root / "assets"
    assets.mkdir()
    (assets / "art.png").write_bytes(b"prepared image")
    (assets / "art.png.import").write_text("cache")
    (assets / "script.gd").write_text("extends Node")
    return root


def test_copy_preserves_bound_content_and_provenance_without_code(tmp_path: Path) -> None:
    source = fixture_project(tmp_path / "source")
    output = tmp_path / "content"
    result = content.prepare(output, source)
    assert set(result["files"]) == {
        "assets/art.png",
        "games/bishoujo_afterlight/voice/manifest.json",
        "clips/line.mp3",
        "clips/line.mp3.meta.json",
    }
    for relative in result["files"]:
        assert (output / relative).read_bytes() == (source / relative).read_bytes()
    assert json.loads((output / "content_inventory.json").read_text()) == result
    with pytest.raises(ValueError, match="already exists"):
        content.prepare(output, source)


@pytest.mark.parametrize(
    "binding",
    [
        "../escape.mp3",
        "res://../escape.mp3",
        "/absolute.mp3",
        "clips/../line.mp3",
        "clips\\line.mp3",
    ],
)
def test_recording_bindings_cannot_escape(tmp_path: Path, binding: str) -> None:
    source = fixture_project(tmp_path / "source")
    manifest = source / "games/bishoujo_afterlight/voice/manifest.json"
    manifest.write_text(json.dumps({"lines": [{"path": binding}]}))
    with pytest.raises(ValueError, match="Invalid content binding"):
        content.prepare(tmp_path / "output", source)
    assert not (tmp_path / "output").exists()


def test_symlink_content_is_rejected(tmp_path: Path) -> None:
    source = fixture_project(tmp_path / "source")
    original = source / "clips/line.mp3"
    original.unlink()
    original.symlink_to(source / "assets/art.png")
    with pytest.raises(ValueError, match="symbolic link"):
        content.prepare(tmp_path / "output", source)
    assert not (tmp_path / "output").exists()


def test_missing_recording_has_no_partial_destination(tmp_path: Path) -> None:
    source = fixture_project(tmp_path / "source")
    (source / "clips/line.mp3").unlink()
    with pytest.raises(FileNotFoundError):
        content.prepare(tmp_path / "output", source)
    assert not (tmp_path / "output").exists()
