"""The closed surface table, and the normalization that makes its promise true."""

from __future__ import annotations

import pytest

from gnode import inspect_image
from stage_gen.media.images import normalize_png_cover
from stage_gen.recipes.storefront.surfaces import (
    DRAW_EDGE_MULTIPLE,
    MAX_RATIO_DRIFT,
    SURFACES,
    Surface,
    SurfaceKind,
    surface,
    surfaces_digest_material,
)
from tests.unit.recipes.storefront._fixture import solid_png


def test_every_declared_kind_is_in_the_table() -> None:
    assert set(SURFACES) == set(SurfaceKind)
    for kind in SurfaceKind:
        assert surface(kind.value).kind is kind


def test_an_unknown_kind_is_refused_by_name_with_the_known_ones() -> None:
    with pytest.raises(ValueError, match="unknown storefront surface kind 'wallpaper'"):
        surface("wallpaper")
    with pytest.raises(ValueError, match="app_icon"):
        surface("wallpaper")


@pytest.mark.parametrize("kind", list(SurfaceKind))
def test_the_draw_canvas_reaches_the_ship_canvas_exactly(kind: SurfaceKind) -> None:
    """The two canvases are a promise: whatever is drawn, this is what ships.

    Proven against the draw canvas the table declares, because that is the one
    the provider is actually asked for — a table entry whose ratio drifted from
    its ship canvas would still pass a test that only fed it the ship size.
    """

    declared = surface(kind.value)
    drawn = solid_png(declared.draw_width, declared.draw_height, (12, 24, 36))
    shipped, record = normalize_png_cover(
        drawn, width=declared.ship_width, height=declared.ship_height
    )
    assert inspect_image(shipped, expected_media_type="image/png").width == declared.ship_width
    assert inspect_image(shipped, expected_media_type="image/png").height == declared.ship_height
    assert record.output["width"] == declared.ship_width
    assert record.output["height"] == declared.ship_height
    # A canvas that needs no work says so, and one that does names the cut rather
    # than quietly re-encoding: the provenance is where a reader learns which.
    assert record.operation == ("resize-cover" if declared.resizes else "png-reencode")


def test_every_draw_edge_is_one_the_image_route_will_accept() -> None:
    """The rule that cost a live run: GPT Image 2 refuses an edge off the grid.

    The route reports it only once the request is in flight, so a table entry
    that breaks it burns six attempts on every surface before anything says why.
    Universe's canvases all satisfy it by luck of their own arithmetic, which is
    exactly why copying their magnitude was not enough.
    """

    for kind in SurfaceKind:
        declared = surface(kind.value)
        assert declared.draw_width % DRAW_EDGE_MULTIPLE == 0, kind.value
        assert declared.draw_height % DRAW_EDGE_MULTIPLE == 0, kind.value


def test_the_two_canvases_share_a_ratio_within_a_pixel() -> None:
    """A draw canvas at a different ratio would make the cut a recomposition.

    The crop is meant to be a trim. A tenth of a percent is the rounding a
    whole-pixel canvas on a sixteen-pixel grid forces; anything past it means the
    table is asking for a picture that gets its sides cut off.
    """

    for kind in SurfaceKind:
        declared = surface(kind.value)
        drawn = declared.draw_width / declared.draw_height
        ship = declared.ship_width / declared.ship_height
        assert abs(drawn - ship) / ship <= MAX_RATIO_DRIFT, kind.value


def test_a_surface_off_the_edge_grid_is_refused_where_it_is_written() -> None:
    """The table itself refuses it, so no such entry can reach a provider."""

    with pytest.raises(ValueError, match="not a multiple of 16"):
        Surface(
            kind=SurfaceKind.APP_ICON,
            title="Bad icon",
            ship_width=1290,
            ship_height=2796,
            draw_width=1181,
            draw_height=2560,
            forbids_alpha_channel=True,
            max_bytes=1,
            purpose="x",
        )


def test_a_draw_canvas_at_the_wrong_ratio_is_refused_too() -> None:
    with pytest.raises(ValueError, match="off the ship ratio"):
        Surface(
            kind=SurfaceKind.FEATURE_GRAPHIC,
            title="Bad banner",
            ship_width=1024,
            ship_height=500,
            draw_width=1024,
            draw_height=1024,
            forbids_alpha_channel=False,
            max_bytes=1,
            purpose="x",
        )


def test_only_the_icon_refuses_an_alpha_channel() -> None:
    forbidding = {kind for kind in SurfaceKind if surface(kind.value).forbids_alpha_channel}
    assert forbidding == {SurfaceKind.APP_ICON}


def test_the_digest_material_names_every_geometry_fact_and_moves_with_it() -> None:
    material = surfaces_digest_material()
    assert len(material) == len(SurfaceKind)
    icon = surface(SurfaceKind.APP_ICON.value)
    assert f"{icon.draw_size}->{icon.ship_size}" in material[0]
    assert "alpha_channel_forbidden=1" in material[0]
