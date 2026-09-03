"""The tolerance band between what collides and what is drawn.

The runner proves its published alpha exactly: every solid cell opaque to its last pixel,
every empty cell transparent to its first. That is right for a ground which is one
continuous mass whose only visible edge is the top. Ported unchanged to a hunting map it
would publish one razor-straight line across fifty-six tiles and eleven perfect
rectangles -- which is *more* rectilinear than the 47-mask atlas already shipping, whose
cells carry transparent contours and whose caps are lifted ten source pixels
(``TERRAIN_ATLAS_WALK_SURFACE_INSET_PX``). Spending provider calls to make the silhouette
squarer than it is today would move the very axis this family exists to move, backwards.

So the drawn edge is allowed to leave the authored one, by a bounded and *published*
amount. Occupancy is still the sole collision authority -- the collision heightfield is
computed in ``prepared-terrain.ts`` from ``terrain.json`` and nothing samples the image at
any stage -- and the band travels in the manifest, so a consumer drawing a debug overlay
knows exactly how far the art may stray.

The band is deliberately not symmetric, and not even uniform by direction:

* Drawn wider than collision reads as grass or moss over the feet. Mild, and the atlas
  already errs this way on purpose.
* Drawn narrower puts a body on visible air. That reads as a bug.
* And an overhang above a walking surface is the one outward error that *does* read as a
  bug, because it is the edge a player judges a jump against.

Hence: a generous outward allowance below and to the sides, half that above a walking
surface, and a small inward allowance everywhere.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from PIL import Image, ImageChops, ImageDraw

#: How far the drawn edge may fall short of the authored one, in published pixels.
#: An eighth of a cell: a one-tile deck keeps a 48-pixel opaque core, so it can never
#: thin to the point of reading as a ledge the player would fall through.
PAINTED_TERRAIN_ERODE_PX: Final = 8

#: How far a mass may overhang its authored block sideways or below. A quarter of a cell,
#: so a deck's drawn thickness ranges from 0.75 to 1.5 tiles -- room for a mossy lip and a
#: ragged underside without ever closing a one-tile hop gap, which keeps a 32-pixel
#: guaranteed-clear core.
PAINTED_TERRAIN_DILATE_PX: Final = 16

#: How far a mass may overhang *upward*, over the air above a walking surface. Half the
#: sideways allowance: this is the edge a player reads a jump against, so it stays close
#: to the geometry while everything the player never lands on is free to be ragged.
PAINTED_TERRAIN_SURFACE_DILATE_PX: Final = 8

#: Alpha at which a published pixel counts as drawn.
PAINTED_TERRAIN_VISIBLE_ALPHA: Final = 128

#: Coverage of an empty cell's guaranteed-clear core above which that cell counts as
#: filled, for the purpose of finding a pillar under a deck.
_SUPPORT_COVERAGE: Final = 0.35

#: The share of a cell, measured down from its top edge, that carries the footing line a
#: player reads a landing against. A quarter cell: deep enough that a thin skin of paint
#: cannot pass for a surface, shallow enough to say nothing about the mass below it.
_SURFACE_BAND_SHARE: Final = 0.25


@dataclass(frozen=True, slots=True)
class PaintedSilhouetteBand:
    """The three regions every measurement here is taken over.

    ``solid_core`` is what must be drawn, ``clean_empty`` is what must not be, and
    ``outward_band`` is the strip between them where the art is free -- the only place an
    organic edge can live, and therefore the place we measure to find out whether the
    model drew one at all.
    """

    solid_core: Image.Image
    clean_empty: Image.Image
    outward_band: Image.Image
    cell_px: int


def painted_silhouette_band(
    occupancy: Sequence[str],
    *,
    cell_px: int,
    erode_px: int = PAINTED_TERRAIN_ERODE_PX,
    dilate_px: int = PAINTED_TERRAIN_DILATE_PX,
    surface_dilate_px: int = PAINTED_TERRAIN_SURFACE_DILATE_PX,
) -> PaintedSilhouetteBand:
    """Build the band as unions of grown rectangles, exactly.

    Morphology on a union of axis-aligned cells is just the same union with every box
    grown, so this is exact rather than approximate, and it is a few hundred rectangle
    fills rather than a rank filter with a 33-pixel kernel over a 3584x896 plate. The
    erosion uses the identity ``erode(A) = complement(dilate(complement(A)))``, which is
    what lets it be drawn the same way.

    Off-grid is not uniform. Above the top row is sky, so a solid cell there is eroded
    from above and may overhang upward. Beyond the sides and below the bottom row the
    world simply continues -- the player can walk off neither -- so nothing there is an
    edge, and the raster stays opaque to its border.
    """

    rows = len(occupancy)
    columns = len(occupancy[0])
    width, height = columns * cell_px, rows * cell_px
    solid = Image.new("L", (width, height), 0)
    empty_grown = Image.new("L", (width, height), 0)
    solid_grown = Image.new("L", (width, height), 0)
    solid_draw = ImageDraw.Draw(solid)
    empty_draw = ImageDraw.Draw(empty_grown)
    grown_draw = ImageDraw.Draw(solid_grown)
    # Off-grid sky, grown down into the first row.
    empty_draw.rectangle((-erode_px, -erode_px, width + erode_px, erode_px - 1), fill=255)
    for row, values in enumerate(occupancy):
        top = row * cell_px
        for column, value in enumerate(values):
            left = column * cell_px
            box = (left, top, left + cell_px - 1, top + cell_px - 1)
            if value == "1":
                solid_draw.rectangle(box, fill=255)
                grown_draw.rectangle(
                    (
                        left - dilate_px,
                        top - surface_dilate_px,
                        left + cell_px - 1 + dilate_px,
                        top + cell_px - 1 + dilate_px,
                    ),
                    fill=255,
                )
            else:
                empty_draw.rectangle(
                    (
                        left - erode_px,
                        top - erode_px,
                        left + cell_px - 1 + erode_px,
                        top + cell_px - 1 + erode_px,
                    ),
                    fill=255,
                )
    return PaintedSilhouetteBand(
        solid_core=ImageChops.subtract(solid, empty_grown),
        clean_empty=ImageChops.invert(solid_grown),
        outward_band=ImageChops.subtract(solid_grown, solid),
        cell_px=cell_px,
    )


def painted_silhouette_report(
    alpha: Image.Image,
    occupancy: Sequence[str],
    *,
    band: PaintedSilhouetteBand,
) -> dict[str, object]:
    """Measure one painting against the band, cell by cell.

    Everything here is a share, and every share is reported beside the cell that produced
    the worst one, because a mean over a raster is exactly how a defect that is a *line*
    stays invisible -- the lesson the runner's published-base check was written from.
    """

    cell_px = band.cell_px
    rows = len(occupancy)
    columns = len(occupancy[0])
    if alpha.size != (columns * cell_px, rows * cell_px):
        raise ValueError("painted terrain silhouette report requires a full-grid alpha plate")
    opaque = alpha.point(lambda value: 255 if value >= PAINTED_TERRAIN_VISIBLE_ALPHA else 0)

    def share(region: Image.Image, box: tuple[int, int, int, int] | None = None) -> float | None:
        mask = region if box is None else region.crop(box)
        total = _count(mask)
        if total == 0:
            return None
        drawn = opaque if box is None else opaque.crop(box)
        return _count(ImageChops.darker(mask, drawn)) / total

    worst_solid: tuple[float, int, int] | None = None
    worst_surface: tuple[float, int, int] | None = None
    worst_empty: tuple[float, int, int] | None = None
    worst_gap: tuple[float, int, int] | None = None
    worst_hole: tuple[float, int, int] | None = None
    support_run = 0
    empty_core: dict[tuple[int, int], float] = {}
    for row in range(rows):
        for column in range(columns):
            box = (
                column * cell_px,
                row * cell_px,
                (column + 1) * cell_px,
                (row + 1) * cell_px,
            )
            if occupancy[row][column] == "1":
                covered = share(band.solid_core, box)
                if covered is not None and (worst_solid is None or covered < worst_solid[0]):
                    worst_solid = (covered, row, column)
                if row == 0 or occupancy[row - 1][column] == "0":
                    # The walking surface, measured over the core rather than the whole
                    # cell. A deck's end cell is exposed on two sides at once and an
                    # organic silhouette rounds that corner; judging the whole cell would
                    # read a correctly drawn corner as a missing floor.
                    surface = share(
                        band.solid_core,
                        (
                            box[0],
                            box[1],
                            box[2],
                            box[1] + int(cell_px * _SURFACE_BAND_SHARE),
                        ),
                    )
                    if surface is not None and (
                        worst_surface is None or surface < worst_surface[0]
                    ):
                        worst_surface = (surface, row, column)
                if _interior(occupancy, row, column):
                    whole = _count(opaque.crop(box)) / (cell_px * cell_px)
                    if worst_hole is None or whole < worst_hole[0]:
                        worst_hole = (whole, row, column)
                continue
            covered = share(band.clean_empty, box)
            if covered is None:
                continue
            empty_core[(row, column)] = covered
            if worst_empty is None or covered > worst_empty[0]:
                worst_empty = (covered, row, column)
            if _between_solids(occupancy, row, column) and (
                worst_gap is None or covered > worst_gap[0]
            ):
                worst_gap = (covered, row, column)
    for (row, column), covered in empty_core.items():
        if covered <= _SUPPORT_COVERAGE or row == 0 or occupancy[row - 1][column] != "1":
            continue
        run = 0
        walk = row
        while walk < rows and empty_core.get((walk, column), 0.0) > _SUPPORT_COVERAGE:
            run += 1
            walk += 1
        support_run = max(support_run, run)
    return {
        "minimum_solid_core_coverage": _round(worst_solid),
        "minimum_solid_core_cell": _cell(worst_solid),
        "minimum_surface_core_coverage": _round(worst_surface),
        "minimum_surface_core_cell": _cell(worst_surface),
        "maximum_empty_core_coverage": _round(worst_empty),
        "maximum_empty_core_cell": _cell(worst_empty),
        "maximum_gap_core_coverage": _round(worst_gap),
        "maximum_gap_core_cell": _cell(worst_gap),
        "minimum_interior_coverage": _round(worst_hole),
        "minimum_interior_cell": _cell(worst_hole),
        "deck_support_run": support_run,
        "outward_band_share": round(share(band.outward_band) or 0.0, 4),
        "erode_px": PAINTED_TERRAIN_ERODE_PX,
        "dilate_px": PAINTED_TERRAIN_DILATE_PX,
        "surface_dilate_px": PAINTED_TERRAIN_SURFACE_DILATE_PX,
        "cell_px": cell_px,
    }


def _count(mask: Image.Image) -> int:
    return mask.histogram()[255]


def _interior(occupancy: Sequence[str], row: int, column: int) -> bool:
    rows = len(occupancy)
    columns = len(occupancy[0])
    if row == 0:
        return False
    for delta_row, delta_column in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        near_row, near_column = row + delta_row, column + delta_column
        if not (0 <= near_row < rows and 0 <= near_column < columns):
            continue
        if occupancy[near_row][near_column] == "0":
            return False
    return True


def _between_solids(occupancy: Sequence[str], row: int, column: int) -> bool:
    """A hop gap: air with terrain to its left and right on the same row."""

    values = occupancy[row]
    return "1" in values[:column] and "1" in values[column + 1 :]


def _round(worst: tuple[float, int, int] | None) -> float | None:
    return None if worst is None else round(worst[0], 4)


def _cell(worst: tuple[float, int, int] | None) -> list[int] | None:
    return None if worst is None else [worst[1], worst[2]]


__all__ = [
    "PAINTED_TERRAIN_DILATE_PX",
    "PAINTED_TERRAIN_ERODE_PX",
    "PAINTED_TERRAIN_SURFACE_DILATE_PX",
    "PAINTED_TERRAIN_VISIBLE_ALPHA",
    "PaintedSilhouetteBand",
    "painted_silhouette_band",
    "painted_silhouette_report",
]
