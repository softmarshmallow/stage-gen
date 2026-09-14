"""Bounded disk IO and corruption refusal for the native movie sprite frame store."""

from __future__ import annotations

import io
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from stage_gen.components.movie_sprite import processing
from stage_gen.components.movie_sprite.frame_store import FrameStore
from stage_gen.recipes.movie_sprite_body_idle.examples.supplied_clip.make_inputs import make_inputs


def test_frame_store_roundtrip_preserves_order_and_independent_reads(tmp_path: Path) -> None:
    source = np.arange(4 * 3 * 5 * 4, dtype=np.uint8).reshape((4, 3, 5, 4))
    path = tmp_path / "frames.rgba"
    store = FrameStore(path, source.shape, create=True)
    for index in (3, 0, 2, 1):
        store[index] = source[index]
    assert len(store) == 4
    assert store.frame_bytes == 60
    assert path.read_bytes() == source.tobytes()
    assert np.array_equal(np.stack(list(store)), source)
    before = store[-1]
    assert not before.flags.writeable
    store[-1] = np.zeros_like(source[-1])
    assert np.array_equal(before, source[-1])
    assert not store[-1].any()
    assert np.array_equal(store[0], source[0])
    reopened = FrameStore(path, source.shape)
    assert np.array_equal(reopened[2], source[2])


def test_frame_store_refuses_out_of_bounds_and_invalid_writes(tmp_path: Path) -> None:
    path = tmp_path / "frames.rgba"
    store = FrameStore(path, (3, 4, 5, 4), create=True)
    frame = np.full((4, 5, 4), 127, dtype=np.uint8)
    store[1] = frame
    original = path.read_bytes()
    for index in (-4, 3):
        with pytest.raises(IndexError):
            _ = store[index]
        with pytest.raises(IndexError):
            store[index] = frame
    with pytest.raises(TypeError):
        _ = store[:]
    for invalid in (frame.astype(np.float32), frame[..., :3], frame[None]):
        with pytest.raises(ValueError):
            store[0] = invalid
    assert path.read_bytes() == original
    with pytest.raises(FileExistsError):
        FrameStore(path, (3, 4, 5, 4), create=True)
    assert path.read_bytes() == original


def test_frame_store_refuses_truncated_and_mismatched_files(tmp_path: Path) -> None:
    path = tmp_path / "frames.rgb"
    store = FrameStore(path, (3, 4, 5, 3), create=True)
    path.write_bytes(b"\x80" * (store.frame_bytes * 3 - 1))
    with pytest.raises(ValueError, match="incomplete frame"):
        _ = store[-1]
    with pytest.raises(ValueError, match="declared dimensions"):
        FrameStore(path, (3, 4, 5, 3))
    path.write_bytes(b"\x80" * (store.frame_bytes * 3 + 1))
    with pytest.raises(ValueError, match="declared dimensions"):
        FrameStore(path, (3, 4, 5, 3))


def test_single_frame_access_never_reads_the_sequence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "frames.rgba"
    store = FrameStore(path, (20, 4, 5, 4), create=True)
    data = np.arange(20 * store.frame_bytes, dtype=np.uint8).tobytes()
    path.write_bytes(data)
    reads: list[int] = []

    class BoundedReader(io.BytesIO):
        def read(self, size: int = -1) -> bytes:
            assert size == store.frame_bytes
            reads.append(size)
            return super().read(size)

    original_open = Path.open

    def open_frame(file: Path, mode: str = "r", *args: object, **kwargs: object):
        if file == path and mode == "rb":
            return BoundedReader(data)
        return original_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_frame)
    assert store[13].tobytes() == data[13 * store.frame_bytes : 14 * store.frame_bytes]
    assert reads == [store.frame_bytes]


def test_decode_caps_actual_frames_when_source_duration_underreports(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    make_inputs(inputs)
    facts = {"width": 96, "height": 160, "fps": 6, "duration_seconds": 0.5}
    with pytest.raises(ValueError, match=r"timestamps|duration"):
        processing._decode(
            inputs / "actor.mkv",
            tmp_path,
            facts,
            "ffmpeg",
            "ffprobe",
            preview_size=(96, 160),
        )
    # The source really has twelve frames. The falsely declared three-frame
    # timeline may consume only its reserved five frames before rejection.
    assert (tmp_path / "source.rgba").stat().st_size == 5 * 96 * 160 * 4


def test_disk_preflight_includes_preview_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts = {"width": 96, "height": 160, "fps": 6, "duration_seconds": 2}
    old_incomplete_reservation = 96 * 160 * 4 * 14 * 2 + processing.MAX_OUTPUT_BYTES
    monkeypatch.setattr(
        processing.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(free=old_incomplete_reservation),
    )
    with pytest.raises(ValueError, match="Insufficient temporary disk"):
        processing._decode(
            tmp_path / "unused.mkv",
            tmp_path,
            facts,
            "ffmpeg",
            "ffprobe",
            preview_size=(96, 160),
        )
    assert not (tmp_path / "source.rgba").exists()


@pytest.mark.parametrize("alpha", [True, False], ids=["lossless-body", "mp4-preview"])
def test_encoder_stops_and_refuses_an_oversized_export(tmp_path: Path, alpha: bool) -> None:
    channels = 4 if alpha else 3
    frames = np.random.default_rng(7).integers(0, 256, (20, 96, 64, channels), dtype=np.uint8)
    source = tmp_path / "source.rgba"
    source.write_bytes(frames.tobytes())
    target = tmp_path / ("bounded.mkv" if alpha else "bounded.mp4")
    limit = 16_000
    with pytest.raises(ValueError, match="compressed output byte bound"):
        processing._encode(
            source,
            target,
            (64, 96),
            Fraction(12),
            "ffmpeg",
            alpha=alpha,
            maximum_bytes=limit,
        )
    # FFmpeg may finish the packet that crosses -fs, but must not encode the
    # remaining sequence. Reserve room for one frame and codec overhead.
    assert limit <= target.stat().st_size < limit + frames[0].nbytes * 2
