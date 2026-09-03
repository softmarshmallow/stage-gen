"""Source admission runs inside the provider's retry budget, so it refuses cheaply.

Two of these rules exist because a hunting map breaks an assumption the runner could
make. Its ground is one near-continuous mass, so a mean over empty cells is a fair summary
of leakage. Here the map is mostly air, and a model can fill every hop gap on the level
while still scoring 0.07 on that mean.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from stage_gen.components.painted_terrain import (
    PAINTED_TERRAIN_CELL_PX,
    painted_terrain_join_discontinuity,
    validate_painted_terrain_source,
)
from tests.unit.components.painted_terrain import _fixture as fixture

CELL = PAINTED_TERRAIN_CELL_PX


def _validate(source: bytes) -> dict[str, object]:
    seg = fixture.segment()
    return validate_painted_terrain_source(
        source,
        occupancy=fixture.OCCUPANCY,
        segment=seg,
        guide=fixture.guide(seg),
        material_identity=fixture.MATERIAL_IDENTITY,
        material_references=[fixture.material_reference()],
    )


def test_an_organic_painting_is_admitted_and_reports_its_fringe() -> None:
    facts = _validate(fixture.painting(fixture.organic_alpha()))
    silhouette = facts["silhouette"]
    assert isinstance(silhouette, dict)
    outward = silhouette["outward_band_share"]
    assert isinstance(outward, float)
    assert outward > 0.05


def test_the_guide_returned_unedited_is_refused_as_guide_colour() -> None:
    # Every coverage floor passes on the guide itself: they count opaque pixels, so they
    # measure alpha rather than authorship.
    with pytest.raises(ValueError, match="guide colour"):
        _validate(fixture.guide())


def test_a_filled_hop_gap_is_refused() -> None:
    alpha = fixture.organic_alpha()
    box = fixture.cell_box(fixture.segment(), 2, 6)
    ImageDraw.Draw(alpha).rectangle((box[0], box[1], box[2] - 1, box[3] - 1), fill=255)
    with pytest.raises(ValueError, match="closed a gap"):
        _validate(fixture.painting(alpha))


def test_a_support_hung_under_a_deck_is_refused() -> None:
    # Two consecutive filled cells under a deck is a pillar, and a pillar is rock the
    # player walks straight through -- the worst drawn-versus-collision mismatch available.
    alpha = fixture.organic_alpha()
    top = fixture.cell_box(fixture.segment(), 3, 3)
    bottom = fixture.cell_box(fixture.segment(), 4, 3)
    ImageDraw.Draw(alpha).rectangle((top[0], top[1], top[2] - 1, bottom[3] - 1), fill=255)
    with pytest.raises(ValueError, match="support under a floating deck"):
        _validate(fixture.painting(alpha))


def test_air_between_levels_painted_solid_is_refused() -> None:
    # What a backdrop looks like from here: whole empty cells filled. The guide's row
    # window crops the sky away before the model ever sees it, so the reachable version of
    # this failure is the storey gap rather than the sky above the map.
    alpha = fixture.organic_alpha()
    left = fixture.cell_box(fixture.segment(), 4, 0)
    right = fixture.cell_box(fixture.segment(), 4, 15)
    ImageDraw.Draw(alpha).rectangle((left[0], left[1], right[2] - 1, right[3] - 1), fill=255)
    with pytest.raises(ValueError, match="air the player moves through"):
        _validate(fixture.painting(alpha))


def test_a_notch_cut_into_the_walking_surface_is_refused() -> None:
    alpha = fixture.organic_alpha()
    # Just past the eight pixels a surface may fall short by, and no deeper: a deep notch
    # is refused as a hole in the cell instead, which is a different complaint.
    box = fixture.cell_box(fixture.segment(), 5, 8)
    ImageDraw.Draw(alpha).rectangle((box[0], box[1], box[2] - 1, box[1] + 13), fill=0)
    with pytest.raises(ValueError, match="walking surface"):
        _validate(fixture.painting(alpha))


def test_a_fully_opaque_canvas_is_refused_before_anything_is_measured() -> None:
    opaque = Image.new("RGBA", (1536, 1024), (120, 100, 80, 255))
    stream = BytesIO()
    opaque.save(stream, format="PNG")
    with pytest.raises(ValueError, match="true transparency"):
        _validate(stream.getvalue())


def test_a_join_is_measured_against_the_map_it_sits_in() -> None:
    # A cut is invisible when the step across it is unremarkable among the steps inside the
    # paintings, which is a measurement rather than an opinion.
    plate = Image.new("RGBA", (4 * CELL, CELL), (0, 0, 0, 0))
    ImageDraw.Draw(plate).rectangle((0, 0, 4 * CELL - 1, CELL - 1), fill=(120, 110, 90, 255))
    facts = painted_terrain_join_discontinuity(plate, boundaries=[2], cell_px=CELL)
    joins = facts["joins"]
    assert isinstance(joins, dict)
    assert joins["2"]["step"] == 0.0


def test_a_join_with_a_material_step_shows_up_against_the_median() -> None:
    plate = Image.new("RGBA", (4 * CELL, CELL), (0, 0, 0, 0))
    draw = ImageDraw.Draw(plate)
    draw.rectangle((0, 0, 2 * CELL - 1, CELL - 1), fill=(40, 40, 40, 255))
    draw.rectangle((2 * CELL, 0, 4 * CELL - 1, CELL - 1), fill=(200, 200, 200, 255))
    facts = painted_terrain_join_discontinuity(plate, boundaries=[2], cell_px=CELL)
    joins = facts["joins"]
    assert isinstance(joins, dict)
    step = joins["2"]["step"]
    assert isinstance(step, float)
    assert step == 160.0
