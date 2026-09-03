"""The band is the whole argument for this family, so it is the file that earns its keep.

Exact alpha equality -- the runner's rule -- would publish one straight line across the
map and a row of perfect rectangles, which is squarer than the tile atlas already
shipping. These tests say what the replacement admits and, more importantly, what it still
refuses.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from stage_gen.components.painted_terrain import (
    PAINTED_TERRAIN_CELL_PX,
    PAINTED_TERRAIN_DILATE_PX,
    PAINTED_TERRAIN_ERODE_PX,
    PAINTED_TERRAIN_SURFACE_DILATE_PX,
    painted_silhouette_band,
    painted_silhouette_report,
)
from tests.unit.components.painted_terrain import _fixture as fixture

CELL = PAINTED_TERRAIN_CELL_PX
BAND = painted_silhouette_band(fixture.OCCUPANCY, cell_px=CELL)


def _rectilinear() -> Image.Image:
    """Alpha that is exactly the occupancy: what a model that traced the guide returns."""

    alpha = Image.new("L", (len(fixture.OCCUPANCY[0]) * CELL, len(fixture.OCCUPANCY) * CELL), 0)
    draw = ImageDraw.Draw(alpha)
    for row, values in enumerate(fixture.OCCUPANCY):
        for column, value in enumerate(values):
            if value == "1":
                draw.rectangle(
                    (column * CELL, row * CELL, (column + 1) * CELL - 1, (row + 1) * CELL - 1),
                    fill=255,
                )
    return alpha


def _report(alpha: Image.Image) -> dict[str, object]:
    return painted_silhouette_report(alpha, fixture.OCCUPANCY, band=BAND)


def _share(facts: dict[str, object], key: str) -> float:
    """One measured share. The report is JSON evidence, so it carries cells too and types
    as ``object``; a comparison has to say which of its keys it believes is a number."""

    value = facts[key]
    assert isinstance(value, float)
    return value


def test_the_outward_allowance_is_asymmetric_by_direction() -> None:
    # Drawn wider than collision reads as moss over the feet; drawn narrower puts a body on
    # visible air; and an overhang above a surface is the one outward error a player reads a
    # jump against. Three different errors, so three different numbers.
    assert PAINTED_TERRAIN_ERODE_PX < PAINTED_TERRAIN_DILATE_PX
    assert PAINTED_TERRAIN_SURFACE_DILATE_PX < PAINTED_TERRAIN_DILATE_PX


def test_a_one_tile_deck_keeps_a_core_thicker_than_half_a_tile() -> None:
    # The band has to leave a deck unmistakably solid at its thinnest admitted draw.
    assert CELL - 2 * PAINTED_TERRAIN_ERODE_PX > CELL // 2


def test_a_one_tile_hop_gap_keeps_a_guaranteed_clear_core() -> None:
    # Otherwise the outward allowance could close the gap the player jumps through.
    assert CELL - 2 * PAINTED_TERRAIN_DILATE_PX > 0


def test_a_traced_silhouette_is_admissible_but_uses_none_of_the_fringe() -> None:
    # Safe, and pointless: this is the signal that a painting bought nothing.
    facts = _report(_rectilinear())
    assert facts["minimum_solid_core_coverage"] == 1.0
    assert facts["maximum_empty_core_coverage"] == 0.0
    assert facts["outward_band_share"] == 0.0


def test_an_organic_silhouette_is_admitted_and_does_use_the_fringe() -> None:
    facts = _report(fixture.full_plate(fixture.organic_alpha(), fixture.segment()))
    assert _share(facts, "minimum_solid_core_coverage") > 0.9
    assert _share(facts, "maximum_empty_core_coverage") < 0.05
    assert facts["maximum_gap_core_coverage"] == 0.0
    assert facts["deck_support_run"] == 0
    assert _share(facts, "outward_band_share") > 0.05


def test_a_bite_out_of_the_walking_surface_is_caught() -> None:
    alpha = _rectilinear()
    draw = ImageDraw.Draw(alpha)
    row = 5  # the bank's top row in the fixture grid
    draw.rectangle(
        (5 * CELL, row * CELL, 6 * CELL - 1, row * CELL + PAINTED_TERRAIN_ERODE_PX), fill=0
    )
    facts = _report(alpha)
    assert isinstance(facts["minimum_solid_core_coverage"], float)
    assert facts["minimum_solid_core_coverage"] < 1.0
    assert facts["minimum_solid_core_cell"] == [row, 5]


def test_a_pillar_under_a_deck_is_caught_by_its_own_rule() -> None:
    # The measurement that matters: rock the player walks straight through. A mean over
    # empty cells cannot see it, which is why the run is counted instead.
    alpha = _rectilinear()
    ImageDraw.Draw(alpha).rectangle((3 * CELL, 3 * CELL, 4 * CELL - 1, 5 * CELL - 1), fill=255)
    assert _report(alpha)["deck_support_run"] == 2


def test_a_filled_hop_gap_is_caught_separately_from_general_leakage() -> None:
    alpha = _rectilinear()
    ImageDraw.Draw(alpha).rectangle((6 * CELL, 2 * CELL, 7 * CELL - 1, 3 * CELL - 1), fill=255)
    facts = _report(alpha)
    assert facts["maximum_gap_core_coverage"] == 1.0
    assert facts["maximum_gap_core_cell"] == [2, 6]


def test_a_painted_backdrop_is_caught() -> None:
    alpha = _rectilinear()
    ImageDraw.Draw(alpha).rectangle((0, 0, alpha.width - 1, CELL - 1), fill=255)
    assert _report(alpha)["maximum_empty_core_coverage"] == 1.0


def test_a_hole_punched_in_a_mass_is_caught() -> None:
    alpha = _rectilinear()
    ImageDraw.Draw(alpha).ellipse((8 * CELL, 6 * CELL + 8, 8 * CELL + 48, 7 * CELL - 8), fill=0)
    facts = _report(alpha)
    assert isinstance(facts["minimum_interior_coverage"], float)
    assert facts["minimum_interior_coverage"] < 1.0


def test_the_band_is_cut_from_the_whole_map_so_a_deck_end_is_not_squared_off() -> None:
    # A cell whose neighbour is solid gets no inset on that side; a cell whose neighbour is
    # air does. That is what makes the erosion directional rather than uniform.
    core = BAND.solid_core
    interior = core.crop((9 * CELL, 6 * CELL, 10 * CELL, 7 * CELL))
    assert interior.getextrema() == (255, 255)
    deck_end = core.crop((2 * CELL, 2 * CELL, 3 * CELL, 3 * CELL))
    assert deck_end.getextrema()[0] == 0
