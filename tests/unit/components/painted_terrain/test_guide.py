"""The guide says where terrain is, where it ends, and where it leaves the frame."""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO

import pytest
from PIL import Image

from stage_gen.components.painted_terrain import (
    PAINTED_TERRAIN_CELL_PX,
    build_painted_terrain_guide,
    cell_exposure,
    painted_terrain_guide_layout,
    validate_painted_terrain_material_references,
)
from tests.unit.components.painted_terrain import _fixture as fixture


def _guide_image() -> Image.Image:
    return Image.open(BytesIO(fixture.guide())).convert("RGBA")


def test_the_guide_draws_at_the_publication_cell_so_nothing_resamples() -> None:
    layout = painted_terrain_guide_layout(fixture.OCCUPANCY, fixture.segment())
    assert layout.cell_px == PAINTED_TERRAIN_CELL_PX


def test_the_guide_is_cropped_to_the_rows_carrying_terrain() -> None:
    layout = painted_terrain_guide_layout(fixture.OCCUPANCY, fixture.segment())
    assert (layout.window_top_row, layout.window_rows) == (2, 6)


def test_the_bottom_row_bleeds_off_the_canvas() -> None:
    # A window whose bottom edge is a hard line reads as a mass that ENDS there, and the
    # first two measured paintings duly gave the bank an underside and pulled it up off the
    # map's last row -- the row that meets the bottom of the viewport.
    layout = painted_terrain_guide_layout(fixture.OCCUPANCY, fixture.segment())
    assert layout.bottom_bleed_px > 0
    image = _guide_image()
    bottom = image.getchannel("A").crop((0, image.height - 1, image.width, image.height))
    assert bottom.getextrema()[1] == 255


def test_a_window_short_of_the_last_row_keeps_its_underside() -> None:
    # Bleeding a window that does not reach the floor would erase a real bottom edge.
    occupancy = ("1111", "1111", "0000", "0000")
    layout = painted_terrain_guide_layout(occupancy, fixture.segment(columns=4))
    assert layout.bottom_bleed_px == 0


def test_a_deck_reads_as_a_mass_that_ends_on_every_exposed_side() -> None:
    # The runner's guide only knows `top_exposed`, because its ground never terminates
    # except at the aprons. A floating deck terminates on all four sides.
    exposure = cell_exposure(fixture.OCCUPANCY, 2, 2)
    assert (exposure.top, exposure.bottom, exposure.left) == (True, True, True)
    assert exposure.right is False


def test_off_grid_is_sky_above_and_more_world_at_the_sides() -> None:
    bottom_left = cell_exposure(fixture.OCCUPANCY, len(fixture.OCCUPANCY) - 1, 0)
    assert bottom_left.bottom is False
    assert bottom_left.left is False
    assert cell_exposure(fixture.OCCUPANCY, 4, 0).top is True


def test_the_guide_is_deterministic_for_one_material_and_occupancy() -> None:
    assert fixture.guide() == fixture.guide()


def test_a_different_material_identity_yields_a_different_guide() -> None:
    other, _ = build_painted_terrain_guide(
        fixture.OCCUPANCY,
        fixture.segment(),
        material_identity="f" * 64,
        material_references=[fixture.material_reference()],
    )
    assert other != fixture.guide()


def test_the_report_records_what_the_model_will_be_looking_at() -> None:
    _, report = build_painted_terrain_guide(
        fixture.OCCUPANCY,
        fixture.segment(),
        material_identity=fixture.MATERIAL_IDENTITY,
        material_references=[fixture.material_reference()],
    )
    assert report["geometry_authority"] == "authored_occupancy"
    assert isinstance(report["drawn_solid_share"], float)
    assert report["drawn_solid_share"] > 0.4


def test_unusable_material_references_are_refused_while_planning() -> None:
    with pytest.raises(ValueError, match="at least one material reference"):
        validate_painted_terrain_material_references([])


# The guide is a cache input: its bytes feed the provider node's identity and
# every downstream lineage. A change to how it is drawn is therefore either a
# deliberate re-bill or a silent divergence between warm and cold runs, and a
# determinism test that calls the builder twice cannot tell. This digest can.
PINNED_GUIDE_SHA256 = "a278a47eba8f60988631f09aaea4de432d8675c24525c140016808d3c40d74a2"


def test_the_guide_bytes_are_pinned_so_a_redraw_is_a_decision() -> None:
    assert sha256(fixture.guide()).hexdigest() == PINNED_GUIDE_SHA256
