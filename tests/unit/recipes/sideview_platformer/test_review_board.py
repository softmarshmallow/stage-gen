"""The map review board draws what the runtime draws: ground at tile scale, the whole map."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from bellweather_pipeline import prepared_world
from bellweather_pipeline.prepared_world import _fold_into_strips, _ground_preview


def _plate(path: Path, *, columns: int, rows: int, cell: int = 120) -> None:
    plate = Image.new("RGBA", (columns * cell, rows * cell), (0, 0, 0, 0))
    plate.paste((200, 160, 90, 255), (0, (rows - 1) * cell, columns * cell, rows * cell))
    stream = io.BytesIO()
    plate.save(stream, format="PNG")
    path.write_bytes(stream.getvalue())


def test_ground_is_drawn_one_tile_per_row_on_the_frame_bottom(tmp_path: Path) -> None:
    path = tmp_path / "ground.evidence.png"
    _plate(path, columns=40, rows=3)
    preview = _ground_preview(path, (4096, 720), ["000", "000", "111"], composed=True)
    # Resampling softens the tile edge by a few rows, so measure where the ground is solid.
    box = preview.getchannel("A").point(lambda value: 255 if value >= 128 else 0).getbbox()
    assert box is not None
    inset = round(prepared_world._COMPOSITE_WALK_SURFACE_INSET_FRACTION * 64)
    # The filled bottom row is one 64 px tile, 40 tiles wide, lifted by the runtime's inset.
    assert box == (0, 720 - inset - 64, 40 * 64, 720 - inset)


def test_a_board_wider_than_a_strip_folds_into_equal_stacked_strips() -> None:
    board = Image.new("RGBA", (4096, 720), (0, 0, 0, 0))
    board.paste((255, 0, 0, 255), (0, 0, 10, 720))
    board.paste((0, 0, 255, 255), (4086, 0, 4096, 720))
    folded = _fold_into_strips(board)
    gap = prepared_world._COMPOSITE_STRIP_GAP_PX
    assert folded.size == (2048, 2 * 720 + gap)
    assert folded.getpixel((0, 0)) == (255, 0, 0, 255)
    assert folded.getpixel((2047, 720 + gap)) == (0, 0, 255, 255)
    assert folded.getpixel((1000, 720)) == prepared_world._COMPOSITE_STRIP_GAP_RGBA
    narrow = Image.new("RGBA", (1800, 720))
    assert _fold_into_strips(narrow) is narrow
