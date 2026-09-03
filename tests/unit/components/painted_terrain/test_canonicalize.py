"""Publication clips to the band, fills what was missed, and proves the bytes it wrote."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image, ImageChops, ImageDraw

from stage_gen.components.painted_terrain import (
    PAINTED_TERRAIN_CELL_PX,
    canonicalize_painted_terrain_segment,
    occupancy_window,
    painted_silhouette_report,
    painted_terrain_segment_band,
    stitch_painted_terrain,
)
from tests.unit.components.painted_terrain import _fixture as fixture

CELL = PAINTED_TERRAIN_CELL_PX


def _publish(alpha: Image.Image | None = None) -> tuple[bytes, dict[str, object]]:
    seg = fixture.segment()
    return canonicalize_painted_terrain_segment(
        fixture.painting(alpha if alpha is not None else fixture.organic_alpha()),
        occupancy=fixture.OCCUPANCY,
        segment=seg,
        guide=fixture.guide(seg),
        material_identity=fixture.MATERIAL_IDENTITY,
        material_references=[fixture.material_reference()],
    )


def test_publication_is_the_full_grid_at_the_publication_cell() -> None:
    data, report = _publish()
    image = Image.open(BytesIO(data))
    assert image.size == (
        len(fixture.OCCUPANCY[0]) * CELL,
        len(fixture.OCCUPANCY) * CELL,
    )
    assert report["rows"] == len(fixture.OCCUPANCY)


def test_publication_fills_the_band_core_whatever_the_painting_left() -> None:
    # A cell the provider skipped entirely publishes as deterministic material rather than
    # as a hole in the floor, so the inner core is opaque by construction.
    _, report = _publish()
    silhouette = report["silhouette"]
    assert isinstance(silhouette, dict)
    assert silhouette["minimum_solid_core_coverage"] == 1.0


def test_publication_clips_everything_outside_the_band() -> None:
    # However enthusiastic the painting, a hop gap and the air under a deck come back clean.
    alpha = fixture.organic_alpha()
    ImageDraw.Draw(alpha).rectangle((0, 0, alpha.width - 1, alpha.height - 1), fill=255)
    _, report = _publish(alpha)
    silhouette = report["silhouette"]
    assert isinstance(silhouette, dict)
    assert silhouette["maximum_empty_core_coverage"] == 0.0
    assert silhouette["deck_support_run"] == 0


def test_the_deterministic_base_never_reaches_a_silhouette_edge() -> None:
    # It is built on the band's INNER core, which is what stops guide-derived material
    # publishing along the row the player walks on.
    band = painted_terrain_segment_band(fixture.OCCUPANCY, fixture.segment())
    assert ImageChops.darker(band.solid_core, band.outward_band).getextrema() == (0, 0)


def test_a_painting_answering_another_guide_is_refused() -> None:
    with pytest.raises(ValueError, match="guide does not match"):
        canonicalize_painted_terrain_segment(
            fixture.painting(fixture.organic_alpha()),
            occupancy=fixture.OCCUPANCY,
            segment=fixture.segment(),
            guide=fixture.guide(fixture.segment(columns=8)),
            material_identity=fixture.MATERIAL_IDENTITY,
            material_references=[fixture.material_reference()],
        )


def test_a_canvas_of_the_wrong_size_is_refused() -> None:
    wrong = Image.new("RGBA", (512, 512), (10, 20, 30, 255))
    stream = BytesIO()
    wrong.save(stream, format="PNG")
    with pytest.raises(ValueError, match="must be exactly"):
        canonicalize_painted_terrain_segment(
            stream.getvalue(),
            occupancy=fixture.OCCUPANCY,
            segment=fixture.segment(),
            guide=fixture.guide(),
            material_identity=fixture.MATERIAL_IDENTITY,
            material_references=[fixture.material_reference()],
        )


def test_the_stitched_plate_is_the_map_and_is_not_a_runtime_asset() -> None:
    data, _ = _publish()
    plate = stitch_painted_terrain([(fixture.segment(), data)], occupancy=fixture.OCCUPANCY)
    image = Image.open(BytesIO(plate))
    assert image.size == (
        len(fixture.OCCUPANCY[0]) * CELL,
        len(fixture.OCCUPANCY) * CELL,
    )


def test_the_window_pastes_back_so_the_sky_rows_stay_transparent() -> None:
    data, _ = _publish()
    image = Image.open(BytesIO(data)).convert("RGBA")
    sky = image.getchannel("A").crop((0, 0, image.width, CELL))
    assert sky.getextrema() == (0, 0)


def test_the_report_carries_the_measurements_beside_their_subject() -> None:
    _, report = _publish()
    assert report["geometry_authority"] == "authored_occupancy"
    assert report["segment_id"] == "seg00"
    silhouette = report["silhouette"]
    assert isinstance(silhouette, dict)
    assert silhouette["cell_px"] == CELL
    assert set(silhouette) >= {"erode_px", "dilate_px", "surface_dilate_px"}


def test_a_published_plate_measures_the_same_from_its_own_bytes() -> None:
    data, report = _publish()
    image = Image.open(BytesIO(data)).convert("RGBA")
    seg = fixture.segment()
    fresh = painted_silhouette_report(
        image.getchannel("A"),
        occupancy_window(fixture.OCCUPANCY, seg),
        band=painted_terrain_segment_band(fixture.OCCUPANCY, seg),
    )
    assert fresh == report["silhouette"]
