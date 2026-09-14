"""Provider-free tests for the local Afterlight movie_sprite content boundary."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

SPEC = importlib.util.spec_from_file_location(
    "movie_sprite_preparation", Path(__file__).parents[2] / "tools/prepare_movie_sprite.py"
)
assert SPEC and SPEC.loader
preparation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preparation)


def canonical() -> np.ndarray:
    pixels = np.zeros((24, 12, 4), dtype=np.uint8)
    pixels[2:22, 2:10] = [30, 80, 120, 255]
    return pixels


def write_artifact(root: Path, relative: str, data: bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.with_name(path.name + ".meta.json").write_text(
        json.dumps({"artifact": {"sha256": preparation.digest(path), "bytes": len(data)}})
    )
    return path


@pytest.mark.parametrize("relative", ["../outside", "/outside", "a//b", "./a", "a\\b", "res://a"])
def test_content_paths_refuse_escape(tmp_path: Path, relative: str) -> None:
    with pytest.raises(ValueError, match="Invalid relative"):
        preparation.confined_file(tmp_path, relative)


def test_symlinks_refused_even_when_target_is_inside_root(tmp_path: Path) -> None:
    (tmp_path / "actual").write_text("data")
    (tmp_path / "link").symlink_to("actual")
    with pytest.raises(ValueError, match="Symbolic link"):
        preparation.confined_file(tmp_path, "link")


def test_artifact_sidecar_is_a_hash_boundary(tmp_path: Path) -> None:
    path = write_artifact(tmp_path, "canonical.png", b"canonical")
    assert preparation.checked_artifact(tmp_path, "canonical.png")[0] == path
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="differs from provenance"):
        preparation.checked_artifact(tmp_path, "canonical.png")


def test_native_rgb_replacement_keeps_alpha_and_selected_pixels_only() -> None:
    pixels = canonical()
    patch = np.zeros((3, 3, 4), dtype=np.uint8)
    patch[1, 1] = [220, 10, 20, 255]
    result = preparation.apply_patches(pixels, [(3, 4, patch)])
    expected = pixels.copy()
    expected[5, 4, :3] = [220, 10, 20]
    assert np.array_equal(result, expected)
    assert np.array_equal(pixels, canonical())
    patch[1, 1, 3] = 128
    with pytest.raises(ValueError, match="binary"):
        preparation.apply_patches(pixels, [(3, 4, patch)])


def test_patch_at_transparent_or_outside_canvas_is_refused() -> None:
    patch = np.full((2, 2, 4), 255, dtype=np.uint8)
    with pytest.raises(ValueError, match="opaque canonical"):
        preparation.apply_patches(canonical(), [(0, 0, patch)])
    with pytest.raises(ValueError, match="exceeds"):
        preparation.apply_patches(canonical(), [(11, 23, patch)])


def test_downsample_composes_at_native_offset_before_derived_selection() -> None:
    pixels = canonical()
    patch = np.full((3, 3, 4), [180, 20, 50, 255], dtype=np.uint8)
    baseline = preparation.resize_rgba(pixels, (4, 8))
    painted = preparation.resize_rgba(preparation.apply_patches(pixels, [(4, 7, patch)]), (4, 8))
    texture = preparation.replacement_texture(baseline, painted)
    selected = texture[..., 3] == 255
    assert selected.any()
    assert set(np.unique(texture[..., 3])) == {0, 255}
    composed = baseline.copy()
    composed[..., :3][selected] = texture[..., :3][selected]
    assert np.array_equal(composed, painted)


def test_transparent_hidden_rgb_cannot_tint_resampled_face() -> None:
    pixels = np.array([[[220, 20, 40, 255], [0, 255, 0, 0]]], dtype=np.uint8)
    result = preparation.resize_rgba(pixels, (1, 1))
    assert tuple(result[0, 0, :3]) == (220, 20, 40)
    assert 0 < result[0, 0, 3] < 255


def test_atlas_exactness_endpoint_and_registration(tmp_path: Path) -> None:
    base = canonical()
    middle = base.copy()
    middle[18:20, 3:5, :3] = [100, 120, 140]
    support = np.zeros(base.shape[:2], dtype=bool)
    support[4:8, 4:8] = True
    frames = [base, middle, middle, base]
    pages, proof = preparation.pack_frames(
        iter(frames), tmp_path, base, support, count=4, columns=2, rows=1
    )
    assert len(pages) == 2
    assert proof["endpoint_rgba_equal"]
    assert proof["body_alpha_unchanged"]
    for index, original in enumerate(frames):
        with Image.open(tmp_path / pages[index // 2]["file"]) as page:
            restored = np.array(page.crop(((index % 2) * 12, 0, (index % 2 + 1) * 12, 24)))
        assert np.array_equal(restored, original)
    broken = middle.copy()
    broken[5, 5, 0] += 1
    with pytest.raises(ValueError, match="registration"):
        preparation.pack_frames(iter([base, broken, base]), tmp_path, base, support, count=3)
    with pytest.raises(ValueError, match="identical endpoint"):
        preparation.pack_frames(iter([base, middle]), tmp_path, base, support, count=2)


def test_real_lossless_decoder_uses_explicit_count_and_rgba(tmp_path: Path) -> None:
    base = canonical()
    frames = [base, base.copy(), base.copy(), base]
    frames[1][18, 4, :3] = [210, 80, 50]
    source = tmp_path / "body.mkv"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgba",
            "-s",
            "12x24",
            "-r",
            "16",
            "-i",
            "pipe:0",
            "-c:v",
            "ffv1",
            "-pix_fmt",
            "bgra",
            str(source),
        ],
        input=b"".join(frame.tobytes() for frame in frames),
        check=True,
        capture_output=True,
    )
    decoded = list(preparation.decode_frames(source, (12, 24), 4, 16))
    assert all(
        np.array_equal(actual, expected) for actual, expected in zip(decoded, frames, strict=True)
    )
    with pytest.raises(ValueError, match="more frames"):
        list(preparation.decode_frames(source, (12, 24), 3, 16))
    with pytest.raises(ValueError, match="ended during frame"):
        list(preparation.decode_frames(source, (12, 24), 5, 16))
    with pytest.raises(ValueError, match="timebase"):
        list(preparation.decode_frames(source, (12, 24), 4, 24))


def test_no_existing_output_is_overwritten(tmp_path: Path) -> None:
    output = tmp_path / "actor"
    output.mkdir()
    (output / "keep").write_text("unrelated")
    with pytest.raises(ValueError, match="already exists"):
        preparation.prepare_character(tmp_path, "yuzu", output)
    assert (output / "keep").read_text() == "unrelated"
