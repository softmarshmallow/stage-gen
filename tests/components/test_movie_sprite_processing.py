"""Native alpha, source registration and bounded geometry regression evidence."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from stage_gen.components.movie_sprite import (
    FinishSettings,
    finish_video,
    inspect_source_video,
    validate_finish_config,
)
from stage_gen.components.movie_sprite.geometry import (
    AttachmentRepair,
    Pixels,
    anchor_rgba,
    feather_mask,
    fixed_masks,
    morph,
)
from stage_gen.components.movie_sprite.models import LocalRepair
from stage_gen.components.movie_sprite.processing import key_frame


def _video(tmp_path: Path, frames: Pixels, fps: int | str = 12) -> bytes:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("ffmpeg required for native video regression")
    path = tmp_path / "source.mkv"
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgba",
            "-s",
            f"{frames.shape[2]}x{frames.shape[1]}",
            "-framerate",
            str(fps),
            "-i",
            "pipe:0",
            "-an",
            "-c:v",
            "ffv1",
            "-level",
            "3",
            "-pix_fmt",
            "bgra",
            str(path),
        ],
        input=frames.tobytes(),
        capture_output=True,
        check=True,
        timeout=120,
    )
    return path.read_bytes()


def _frames() -> Pixels:
    frame = np.zeros((96, 64, 4), dtype=np.uint8)
    frame[12:84, 14:50] = [170, 70, 40, 255]
    frame[30:50:3, 20:46:3, :3] = 240
    frame[12:84, 13] = [160, 60, 45, 127]
    frames = np.repeat(frame[None], 6, axis=0)
    frames[1:5, 65:74, 20:27, :3] = [30, 60, 220]
    return frames


def _archive(data: bytes) -> Pixels:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return np.stack(
            [
                np.asarray(Image.open(io.BytesIO(archive.read(name))).convert("RGBA"))
                for name in archive.namelist()
            ]
        )


def test_finished_video_preserves_every_rgba_pixel_and_retimes_once(tmp_path: Path) -> None:
    frames = _frames()
    # Even invisible RGB is preserved in imported finished sources.
    frames[:, 0, 0] = [100, 70, 25, 0]
    outputs = finish_video(
        _video(tmp_path, frames),
        {
            "source_mode": "finished",
            "loop_closure": "none",
            "playback_seconds": 2,
            "export_frames": True,
        },
    )
    assert set(outputs) == {
        "video",
        "preview",
        "canonical",
        "manifest",
        "report",
        "contact_sheet",
        "frames_zip",
    }
    assert np.array_equal(_archive(outputs["frames_zip"]), frames)
    assert np.array_equal(np.asarray(Image.open(io.BytesIO(outputs["canonical"]))), frames[0])
    manifest = json.loads(outputs["manifest"])
    assert manifest["frame_count"] == 6
    assert manifest["playback_fps"] == 3
    assert manifest["playback_seconds"] == 2
    assert manifest["source_frame_indices"] == list(range(6))
    assert json.loads(outputs["report"])["all_native_frames_lossless_verified"] is True


def test_finished_loop_refuses_unequal_endpoints(tmp_path: Path) -> None:
    frames = _frames()
    frames[-1, 50, 30, 0] += 1
    with pytest.raises(ValueError, match="Loop endpoints differ"):
        finish_video(
            _video(tmp_path, frames),
            {
                "source_mode": "finished",
                "loop_closure": "none",
            },
        )


def test_fractional_source_rate_survives_finished_import(tmp_path: Path) -> None:
    frames = _frames()[[0, 0]]
    outputs = finish_video(
        _video(tmp_path, frames, fps="24000/1001"),
        {
            "source_mode": "finished",
            "loop_closure": "none",
            "playback_seconds": None,
        },
    )
    assert json.loads(outputs["manifest"])["playback_rate"] == "24000/1001"


def test_compact_regions_preserve_guard_motion_and_canonical_pixels(tmp_path: Path) -> None:
    frames = _frames()
    frames[1:5, 20:40, 20:45, :3] = [100, 90, 70]
    video = _video(tmp_path, frames)
    config: dict[str, Any] = {
        "source_mode": "rgba",
        "loop_closure": "none",
        "playback_seconds": 2,
        "source_sha256": hashlib.sha256(video).hexdigest(),
        "coordinate_size": [64, 96],
        "fixed_regions": [{"polygon_xy": [[18, 16], [48, 16], [48, 54], [18, 54]]}],
        "moving_guards": [{"polygon_xy": [[28, 30], [38, 30], [38, 45], [28, 45]]}],
        "outside_feather_pixels": 3,
        "export_frames": True,
    }
    outputs = finish_video(video, config)
    decoded = _archive(outputs["frames_zip"])
    hard, weights, guards = fixed_masks(FinishSettings.model_validate(config), (64, 96))
    assert np.array_equal(decoded[2][hard], frames[0][hard])
    assert np.array_equal(decoded[2][guards], frames[2][guards])
    assert np.array_equal(decoded[2][weights == 0], frames[2][weights == 0])


def test_wrong_source_binding_is_refused_before_decode(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="source_sha256"):
        finish_video(_video(tmp_path, _frames()), {"source_sha256": "0" * 64})


def test_source_admission_decodes_frames_and_rejects_corrupt_media(tmp_path: Path) -> None:
    source = _video(tmp_path, _frames())
    facts = inspect_source_video(source)
    assert [facts["width"], facts["height"], facts["frame_count"]] == [64, 96, 6]
    assert facts["fps"] == 12
    assert facts["source_sha256"] == hashlib.sha256(source).hexdigest()
    with pytest.raises(ValueError):
        inspect_source_video(source[: len(source) // 2])
    with pytest.raises(ValueError, match="container"):
        inspect_source_video(b"#EXTM3U\nfile:///private/input\n")


def test_chroma_fixed_head_and_flow_closure_preserve_middle_motion(tmp_path: Path) -> None:
    source = np.repeat(_frames()[0:1], 30, axis=0)
    source[..., :3][source[..., 3] == 0] = [11, 242, 18]
    source[..., 3] = 255
    source[1:, 20:27, 20:40, :3] = [80, 100, 160]
    source[1:, 64:72, 25:32, :3] = [30, 70, 160]
    raw = _video(tmp_path, source)
    config: dict[str, Any] = {
        "source_mode": "chroma",
        "playback_seconds": 5,
        "seam_frames": 3,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "coordinate_size": [64, 96],
        "fixed_regions": [{"polygon_xy": [[18, 16], [44, 16], [44, 32], [18, 32]]}],
        "moving_guards": [{"polygon_xy": [[24, 62], [34, 62], [34, 74], [24, 74]]}],
        "outside_feather_pixels": 2,
        "export_frames": True,
    }
    settings = FinishSettings.model_validate(config)
    output = finish_video(raw, config)
    frames = _archive(output["frames_zip"])
    hard, weight, guards = fixed_masks(settings, (64, 96))
    keyed = key_frame(source[12], settings.chroma)
    assert np.array_equal(frames[0], frames[-1])
    assert np.array_equal(frames[12][hard], frames[0][hard])
    assert np.array_equal(frames[12][weight == 0], keyed[weight == 0])
    assert np.array_equal(frames[12][guards], keyed[guards])
    report = json.loads(output["report"])
    assert report["playback_fps"] == 6
    assert len(report["frames"]) == 30
    assert report["frames"][12]["endpoint_morph_amount"] == 0


@pytest.mark.parametrize(
    "config",
    [
        {"fixed_regions": [{"polygon_xy": [[1, 1], [5, 1], [3, 5]]}]},
        {"source_mode": "finished"},
        {
            "source_mode": "finished",
            "loop_closure": "none",
            "moving_guards": [{"polygon_xy": [[1, 1], [5, 1], [3, 5]]}],
        },
        {"coordinate_size": [2162, 3840]},
        {"playback_seconds": float("nan")},
        {"chroma": {"key_rgb": [250, 0, 0]}},
        {"unrecognized": True},
    ],
)
def test_invalid_settings_are_refused_offline(config: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        validate_finish_config(config)


def test_premultiplied_anchor_does_not_bleed_hidden_rgb() -> None:
    current = np.asarray([[[255, 0, 0, 0], [100, 80, 60, 255]]], dtype=np.uint8)
    canonical = np.asarray([[[0, 0, 255, 255], [20, 30, 40, 255]]], dtype=np.uint8)
    result = anchor_rgba(current, canonical, np.asarray([[0.5, 1]], dtype=np.float32))
    assert result[0, 0].tolist() == [0, 0, 255, 128]
    assert result[0, 1].tolist() == canonical[0, 1].tolist()
    assert np.array_equal(
        anchor_rgba(current, current, np.asarray([[0.5, 1]], dtype=np.float32)), current
    )


def _translation() -> tuple[Pixels, Pixels]:
    first = np.zeros((192, 192, 4), np.uint8)
    first[48:128, 45:105] = [180, 70, 50, 255]
    first[60:118:7, 48:102:6, :3] = 255
    last = np.zeros_like(first)
    last[:, 8:] = first[:, :-8]
    return first, last


def test_flow_moves_silhouette_instead_of_dissolving_two_outlines() -> None:
    first, last = _translation()
    middle, maximum = morph(first, last, 0.5)
    xx = np.indices(first.shape[:2])[1]
    centroid = float((xx * middle[..., 3]).sum() / middle[..., 3].sum())
    original = float((xx * first[..., 3]).sum() / first[..., 3].sum())
    assert abs(centroid - original - 4) < 0.6
    assert maximum < 12
    _, occupied_x = np.nonzero(middle[..., 3] > 128)
    assert 58 <= occupied_x.max() - occupied_x.min() + 1 <= 62
    assert not middle[middle[..., 3] == 0, :3].any()
    assert np.array_equal(morph(first, last, 0)[0], first)
    assert np.array_equal(morph(first, last, 1)[0], last)
    with pytest.raises(ValueError, match="displacement"):
        morph(first, last, 0.5, maximum_displacement=1)


def test_local_repair_preserves_alpha_exterior_and_existing_hard_field() -> None:
    canonical = np.zeros((128, 128, 4), dtype=np.uint8)
    canonical[8:120, 8:120] = [180, 170, 150, 255]
    canonical[35:90:4, 35:90:4, :3] = 40
    current = canonical.copy()
    current[24:105, 27:108] = canonical[24:105, 24:105]
    config = LocalRepair.model_validate(
        {
            "polygon_xy": [[55, 55], [65, 55], [65, 65], [55, 65]],
            "roi_xyxy": [24, 24, 104, 104],
            "falloff_pixels": 12,
            "pin_feather_pixels": 2,
            "max_displacement_pixels": 12,
        }
    )
    empty = np.zeros((128, 128), dtype=bool)
    repair = AttachmentRepair(config, canonical, empty, empty)
    fixed_hard = empty.copy()
    fixed_hard[30:61, 40:75] = True
    weights = feather_mask(fixed_hard, 3)
    anchored = anchor_rgba(current, canonical, weights)
    result, maximum = repair.apply(anchored, canonical, fixed_hard, weights, current)
    assert maximum < 12
    assert np.array_equal(result[repair.hard], canonical[repair.hard])
    assert np.array_equal(result[~repair.field], anchored[~repair.field])
    assert np.array_equal(result[..., 3], anchored[..., 3])
    assert np.array_equal(result[fixed_hard], canonical[fixed_hard])
    guard = empty.copy()
    guard[60, 60] = True
    with pytest.raises(ValueError, match="moving guards"):
        AttachmentRepair(config, canonical, guard, empty)


def test_native_4k_finished_clip_is_not_downscaled(tmp_path: Path) -> None:
    frames = np.zeros((2, 3840, 2160, 4), dtype=np.uint8)
    frames[:, 100:3700, 100:2060] = [170, 60, 40, 255]
    outputs = finish_video(
        _video(tmp_path, frames, fps=2),
        {
            "source_mode": "finished",
            "loop_closure": "none",
            "playback_seconds": None,
            "preview_max_size": [180, 320],
        },
    )
    manifest = json.loads(outputs["manifest"])
    assert [manifest["width"], manifest["height"]] == [2160, 3840]
    assert manifest["playback_seconds"] == 1
    with Image.open(io.BytesIO(outputs["canonical"])) as image:
        assert image.size == (2160, 3840)
        assert np.array_equal(np.asarray(image), frames[0])
