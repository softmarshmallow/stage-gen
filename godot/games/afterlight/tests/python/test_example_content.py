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
    voice = root / "voice"
    voice.mkdir(parents=True)
    (voice / "manifest.json").write_text(
        json.dumps(
            {
                "lines": {
                    "line": {
                        "en": {
                            "path": "res://voice/clips/line.mp3",
                        }
                    }
                }
            }
        )
    )
    clips = voice / "clips"
    clips.mkdir()
    (clips / "line.mp3").write_bytes(b"prepared bytes")
    assets = root / "assets"
    assets.mkdir()
    (assets / "art.png").write_bytes(b"prepared image")
    (assets / "art.png.import").write_text("cache")
    (assets / "script.gd").write_text("extends Node")
    return root


def test_copy_preserves_bound_content_without_code(tmp_path: Path) -> None:
    source = fixture_project(tmp_path / "source")
    output = tmp_path / "content"
    result = content.prepare(output, source)
    assert set(result["files"]) == {
        "assets/art.png",
        "voice/manifest.json",
        "voice/clips/line.mp3",
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
    manifest = source / "voice/manifest.json"
    manifest.write_text(json.dumps({"lines": [{"path": binding}]}))
    with pytest.raises(ValueError, match="Invalid content binding"):
        content.prepare(tmp_path / "output", source)
    assert not (tmp_path / "output").exists()


def test_symlink_content_is_rejected(tmp_path: Path) -> None:
    source = fixture_project(tmp_path / "source")
    original = source / "voice/clips/line.mp3"
    original.unlink()
    original.symlink_to(source / "assets/art.png")
    with pytest.raises(ValueError, match="symbolic link"):
        content.prepare(tmp_path / "output", source)
    assert not (tmp_path / "output").exists()


def test_missing_recording_has_no_partial_destination(tmp_path: Path) -> None:
    source = fixture_project(tmp_path / "source")
    (source / "voice/clips/line.mp3").unlink()
    with pytest.raises(FileNotFoundError):
        content.prepare(tmp_path / "output", source)
    assert not (tmp_path / "output").exists()


def test_movie_sprite_export_keeps_verified_source_provenance_only(tmp_path: Path) -> None:
    source = fixture_project(tmp_path / "source")
    movie = source / "assets/movie_sprite/yuzu"
    preserved = movie / "provenance/sources/body.mkv"
    preserved.parent.mkdir(parents=True)
    preserved.write_bytes(b"validated local lossless source")
    inventory = {
        "files": {
            "provenance/sources/body.mkv": content.hashlib.sha256(
                preserved.read_bytes()
            ).hexdigest()
        }
    }
    (movie / "inventory.json").write_text(json.dumps(inventory))
    (movie.parent / ".gdignore").write_text("")
    (source / "assets/unrelated.mkv").write_bytes(b"not a selected movie source")
    report = content.prepare(tmp_path / "export", source)
    assert "assets/movie_sprite/yuzu/provenance/sources/body.mkv" in report["files"]
    assert "assets/movie_sprite/.gdignore" in report["files"]
    assert "assets/unrelated.mkv" not in report["files"]
    preserved.write_bytes(b"changed")
    with pytest.raises(ValueError, match="inventory differs"):
        content.prepare(tmp_path / "second-export", source)


def test_movie_sprite_inventory_cannot_include_code(tmp_path: Path) -> None:
    source = fixture_project(tmp_path / "source")
    movie = source / "assets/movie_sprite/yuzu"
    movie.mkdir(parents=True)
    code = movie / "source.gd"
    code.write_text("extends Node")
    (movie / "inventory.json").write_text(
        json.dumps({"files": {"source.gd": content.hashlib.sha256(code.read_bytes()).hexdigest()}})
    )
    with pytest.raises(ValueError, match="Unsupported movie diagnostic content"):
        content.prepare(tmp_path / "export", source)
