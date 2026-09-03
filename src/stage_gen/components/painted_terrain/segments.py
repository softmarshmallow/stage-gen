"""How one map's occupancy is cut into provider-sized paintings.

The runner segments its ground because its track is infinite: any chunk may follow any
chunk, so a segment is an authored unit of level design. A platformer map is one finite
grid, so nothing here is authored. Segmentation exists for exactly one reason -- a
1536x1024 conditioning canvas cannot hold 56 columns at the 64-pixel publication cell --
and the partition is therefore derived, has one correct answer, and is pinned by a test
rather than written into a package.

That distinction decides the cut, too. The runner's segments meet in every possible
order, which is what its shared seam bridge is for. These meet in exactly one order, each
segment abutting only its two neighbours, so instead of a bridge each guide simply draws
a couple of its neighbours' real columns as context and the canonicalizer crops them
away.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

#: The publication cell. One authored occupancy cell becomes this many pixels square in
#: every canonical raster, matching the consumer's own ``TILE_PX``.
PAINTED_TERRAIN_CELL_PX: Final = 64

#: The provider conditioning canvas, and the margin kept clear inside it so the guide
#: never runs to the edge of the frame the model is editing.
PAINTED_TERRAIN_GUIDE_WIDTH: Final = 1536
PAINTED_TERRAIN_GUIDE_HEIGHT: Final = 1024
PAINTED_TERRAIN_GUIDE_MARGIN_PX: Final = 32

#: Columns of the neighbouring segment's real occupancy drawn on each side of a guide.
#: They are conditioning only and never reach a published raster: the model paints across
#: a join and sees what continues, rather than inventing an edge twice.
PAINTED_TERRAIN_CONTEXT_COLUMNS: Final = 2

#: A segment narrower than this is mostly context, so its painting would be steered more
#: by its neighbours than by itself.
PAINTED_TERRAIN_MIN_SEGMENT_COLUMNS: Final = 8

_USABLE_WIDTH: Final = PAINTED_TERRAIN_GUIDE_WIDTH - PAINTED_TERRAIN_GUIDE_MARGIN_PX * 2
_USABLE_HEIGHT: Final = PAINTED_TERRAIN_GUIDE_HEIGHT - PAINTED_TERRAIN_GUIDE_MARGIN_PX * 2

#: The widest segment that still lands at the publication cell exactly, context included.
#: At 1472 usable pixels and a 64-pixel cell that is 23 drawn columns, of which four are
#: context.
PAINTED_TERRAIN_MAX_SEGMENT_COLUMNS: Final = (
    _USABLE_WIDTH // PAINTED_TERRAIN_CELL_PX - PAINTED_TERRAIN_CONTEXT_COLUMNS * 2
)

#: The tallest grid whose guide still carries the publication cell. Above it the canvas
#: height binds instead of the width, and no partition can help -- the height cap is
#: independent of how the columns are cut -- so the mode refuses the map offline rather
#: than paying for a soft one.
PAINTED_TERRAIN_MAX_ROWS: Final = _USABLE_HEIGHT // PAINTED_TERRAIN_CELL_PX


@dataclass(frozen=True, slots=True)
class PaintedTerrainSegment:
    """One painting's window onto the map, and the context it is conditioned with."""

    index: int
    start_column: int
    columns: int

    @property
    def segment_id(self) -> str:
        return f"seg{self.index:02d}"

    @property
    def end_column(self) -> int:
        """One past the last authored column this segment publishes."""

        return self.start_column + self.columns

    def context_box(self, map_columns: int) -> tuple[int, int]:
        """The drawn column range, clamped to the map at its two outer ends.

        A segment at the edge of the map has no neighbour to borrow from, so it draws
        fewer columns. The guide keeps a constant cell size rather than a constant width,
        which is what lets every segment publish at the same scale.
        """

        left = max(0, self.start_column - PAINTED_TERRAIN_CONTEXT_COLUMNS)
        right = min(map_columns, self.end_column + PAINTED_TERRAIN_CONTEXT_COLUMNS)
        return left, right


def painted_terrain_segments(columns: int, rows: int) -> tuple[PaintedTerrainSegment, ...]:
    """Cut ``columns`` into the fewest paintings that all publish at native scale.

    Fewest, because every segment is one provider call and one more join to hide. Even,
    because an undersized tail segment would be painted almost entirely from its
    neighbours' context. The remainder goes to the leftmost parts so the result is a
    function of the inputs alone.
    """

    if columns < PAINTED_TERRAIN_MIN_SEGMENT_COLUMNS:
        raise ValueError(
            "painted terrain needs at least "
            f"{PAINTED_TERRAIN_MIN_SEGMENT_COLUMNS} columns, got {columns}"
        )
    if not 1 <= rows <= PAINTED_TERRAIN_MAX_ROWS:
        raise ValueError(
            f"painted terrain needs 1..{PAINTED_TERRAIN_MAX_ROWS} rows, got {rows}; "
            "a taller grid cannot carry the publication cell on the guide canvas"
        )
    count = -(-columns // PAINTED_TERRAIN_MAX_SEGMENT_COLUMNS)
    base, remainder = divmod(columns, count)
    if base < PAINTED_TERRAIN_MIN_SEGMENT_COLUMNS:
        raise ValueError(
            f"painted terrain cannot cut {columns} columns into {count} usable segments"
        )
    segments: list[PaintedTerrainSegment] = []
    start = 0
    for index in range(count):
        width = base + (1 if index < remainder else 0)
        segments.append(PaintedTerrainSegment(index=index, start_column=start, columns=width))
        start += width
    return tuple(segments)


def painted_terrain_row_window(occupancy: list[str] | tuple[str, ...]) -> tuple[int, int]:
    """The row range carrying any terrain, as ``[top, bottom)``.

    A hunting map is mostly air: Crowncrag Road is 28.6 per cent solid, where the runner's
    ground is a near-continuous mass. Conditioning on the whole grid would spend most of
    the canvas on empty sky and leave the model reading a sparse scatter of blocks. The
    guide draws this window instead, and the canonicalizer pastes the result back into
    full height, so publication is unaffected and the model sees a picture with something
    in it.
    """

    rows = [index for index, row in enumerate(occupancy) if "1" in row]
    if not rows:
        raise ValueError("painted terrain occupancy has no solid cell")
    return rows[0], rows[-1] + 1


__all__ = [
    "PAINTED_TERRAIN_CELL_PX",
    "PAINTED_TERRAIN_CONTEXT_COLUMNS",
    "PAINTED_TERRAIN_GUIDE_HEIGHT",
    "PAINTED_TERRAIN_GUIDE_MARGIN_PX",
    "PAINTED_TERRAIN_GUIDE_WIDTH",
    "PAINTED_TERRAIN_MAX_ROWS",
    "PAINTED_TERRAIN_MAX_SEGMENT_COLUMNS",
    "PAINTED_TERRAIN_MIN_SEGMENT_COLUMNS",
    "PaintedTerrainSegment",
    "painted_terrain_row_window",
    "painted_terrain_segments",
]
