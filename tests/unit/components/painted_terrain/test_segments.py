"""The partition is derived, so it has one correct answer and this pins it."""

from __future__ import annotations

from itertools import pairwise

import pytest

from stage_gen.components.painted_terrain import (
    PAINTED_TERRAIN_CELL_PX,
    PAINTED_TERRAIN_GUIDE_HEIGHT,
    PAINTED_TERRAIN_GUIDE_MARGIN_PX,
    PAINTED_TERRAIN_MAX_ROWS,
    PAINTED_TERRAIN_MAX_SEGMENT_COLUMNS,
    PAINTED_TERRAIN_MIN_SEGMENT_COLUMNS,
    painted_terrain_row_window,
    painted_terrain_segments,
)


def test_crowncrag_road_cuts_into_three_segments_at_the_publication_cell() -> None:
    # Fifty-six columns is the shipped hunting map. Four segments of fourteen would also
    # fit, but at fourteen columns the canvas HEIGHT binds and the guide lands at 68 pixels
    # per cell -- a fourth provider call bought to arrive at a downscale. Three of 19/19/18
    # is the widest cut that still fits, and it lands at exactly 64.
    assert [segment.columns for segment in painted_terrain_segments(56, 14)] == [19, 19, 18]
    assert PAINTED_TERRAIN_MAX_SEGMENT_COLUMNS == 19


def test_segments_tile_the_map_without_gap_or_overlap() -> None:
    columns = 96
    segments = painted_terrain_segments(columns, 12)
    assert segments[0].start_column == 0
    assert segments[-1].end_column == columns
    for left, right in pairwise(segments):
        assert left.end_column == right.start_column
    assert all(segment.columns >= PAINTED_TERRAIN_MIN_SEGMENT_COLUMNS for segment in segments)


def test_segment_ids_are_stable_and_ordered() -> None:
    assert [segment.segment_id for segment in painted_terrain_segments(56, 14)] == [
        "seg00",
        "seg01",
        "seg02",
    ]


def test_context_stops_at_the_map_edges() -> None:
    first, middle, last = painted_terrain_segments(56, 14)
    # The outer ends have no neighbour to borrow from, so they draw fewer columns rather
    # than inventing any.
    assert first.context_box(56) == (0, 21)
    assert middle.context_box(56) == (17, 40)
    assert last.context_box(56) == (36, 56)


def test_a_grid_taller_than_the_guide_can_carry_is_refused_before_any_spend() -> None:
    # The height cap is independent of the partition, so no cut can rescue a tall map: it
    # has to be refused rather than silently painted at a coarser cell.
    usable_height = PAINTED_TERRAIN_GUIDE_HEIGHT - PAINTED_TERRAIN_GUIDE_MARGIN_PX * 2
    assert PAINTED_TERRAIN_MAX_ROWS == usable_height // PAINTED_TERRAIN_CELL_PX == 15
    with pytest.raises(ValueError, match="rows"):
        painted_terrain_segments(56, PAINTED_TERRAIN_MAX_ROWS + 1)


def test_a_map_narrower_than_one_usable_segment_is_refused() -> None:
    with pytest.raises(ValueError, match="columns"):
        painted_terrain_segments(PAINTED_TERRAIN_MIN_SEGMENT_COLUMNS - 1, 12)


def test_the_row_window_is_the_rows_carrying_terrain() -> None:
    occupancy = ("0000", "0110", "0000", "1111")
    assert painted_terrain_row_window(occupancy) == (1, 4)


def test_an_empty_grid_has_no_window() -> None:
    with pytest.raises(ValueError, match="no solid cell"):
        painted_terrain_row_window(("0000", "0000"))
