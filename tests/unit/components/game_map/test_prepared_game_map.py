from __future__ import annotations

from pathlib import Path

import pytest

from stage_gen.components._game_input import AuthoredContractLoadError
from stage_gen.components.game_map import (
    PreparedMapGround,
    bottom_contiguous_surface_row,
    load_prepared_game_map_bytes,
    normalized_terrain_column,
)

PACKAGE = Path(__file__).resolve().parents[4] / "library" / "games" / "bellweather"


def _map_bytes(map_id: str) -> bytes:
    return (PACKAGE / "maps" / f"{map_id}.toml").read_bytes()


def test_canonical_maps_own_portal_endpoints_and_optional_climbable_geometry() -> None:
    village = load_prepared_game_map_bytes(_map_bytes("sunpetal-crossing"))
    road = load_prepared_game_map_bytes(_map_bytes("crowncrag-road"))

    assert village.kind == road.kind == "game-map-v7"
    assert village.layers[2].presentation.detail_blur_screen_pixels == 0.65
    assert village.climbable is None
    assert village.portal is not None
    assert [endpoint.anchor for endpoint in village.portal.endpoints] == [
        "west_gate",
        "east_gate",
    ]
    assert [endpoint.role for endpoint in village.portal.endpoints] == ["entry", "exit"]

    assert road.climbable is not None
    assert road.climbable.mode == "climbable-atlas-v1"
    # Atlas order is every ladder left to right, then every rope. Column index is roster index.
    assert [entry.variant_id for entry in road.climbable.variants] == [
        "bellroot_ladder",
        "shrine_rope_ladder",
        "bellrope_climb",
    ]
    assert road.climbable.role_of("bellroot_ladder") == "ladder"
    assert road.climbable.role_of("bellrope_climb") == "rope"
    # Terrain and placements are compiled by scripts/author_terrain.py, so these assert the
    # compiled result rather than a hand-drawn matrix.
    assert road.climbable.placements[0].model_dump() == {
        "climbable_id": "river_ladder",
        "variant_id": "bellroot_ladder",
        "normalized_x": 0.067708,
        "bottom_surface": "terrain",
        "rise_tiles": 4,
    }
    assert len(road.climbable.placements) == 5
    assert road.portal is not None
    assert road.portal.mode == "portal-pair-1x2-v1"
    occupancy = road.ground.occupancy
    assert len(occupancy) == 16
    assert {len(row) for row in occupancy} == {96}
    # Every placement must resolve to the same exposed four-tile deck.
    for placement in road.climbable.placements:
        column = normalized_terrain_column(placement.normalized_x, 96)
        lower_surface = bottom_contiguous_surface_row(occupancy, column)
        assert lower_surface is not None
        assert occupancy[lower_surface - 4][column] == "1"
        assert occupancy[lower_surface - 5][column] == "0"
        assert occupancy[lower_surface - 3][column] == "0"
    assert normalized_terrain_column(0.067708, 96) == 6


def test_map_rejects_the_obsolete_v6_identity() -> None:
    source = _map_bytes("sunpetal-crossing").replace(
        b'schema_version = 7\nkind = "game-map-v7"',
        b'schema_version = 6\nkind = "game-map-v6"',
        1,
    )

    with pytest.raises(AuthoredContractLoadError, match="literal_error"):
        load_prepared_game_map_bytes(source)


def test_map_rejects_unknown_climbable_reference() -> None:
    source = _map_bytes("crowncrag-road").replace(
        b'[climbable]\nmode = "climbable-atlas-v1"\nreference_ids = ["amberbell_scene"]',
        b'[climbable]\nmode = "climbable-atlas-v1"\nreference_ids = ["missing_reference"]',
        1,
    )

    with pytest.raises(AuthoredContractLoadError, match="unknown IDs"):
        load_prepared_game_map_bytes(source)


def test_map_rejects_a_placement_naming_an_undeclared_variant() -> None:
    source = _map_bytes("crowncrag-road").replace(
        b'climbable_id = "river_ladder"\nvariant_id = "bellroot_ladder"',
        b'climbable_id = "river_ladder"\nvariant_id = "no_such_variant"',
        1,
    )

    with pytest.raises(AuthoredContractLoadError, match="undeclared variants"):
        load_prepared_game_map_bytes(source)


def test_map_rejects_a_declared_variant_that_is_never_placed() -> None:
    # Drop both placements that use the rope variant, leaving it declared but unplaced.
    source = _map_bytes("crowncrag-road")
    for block in (
        b'[[climbable.placements]]\nclimbable_id = "bell_rope"\n'
        b'variant_id = "bellrope_climb"\nnormalized_x = 0.567708\n'
        b'bottom_surface = "terrain"\nrise_tiles = 4\n\n',
        b'[[climbable.placements]]\nclimbable_id = "crown_rope"\n'
        b'variant_id = "bellrope_climb"\nnormalized_x = 0.880208\n'
        b'bottom_surface = "terrain"\nrise_tiles = 4\n\n',
    ):
        assert block in source
        source = source.replace(block, b"", 1)

    with pytest.raises(AuthoredContractLoadError, match="unplaced variants"):
        load_prepared_game_map_bytes(source)


def test_map_rejects_more_than_three_variants_in_one_role() -> None:
    # crowncrag-road declares two ladders, so two spares are needed to cross the per-role bound.
    extra = b"".join(
        b'[[climbable.ladders]]\nvariant_id = "spare_ladder_'
        + str(index).encode()
        + b'"\nprompt = """\nA spare ladder that pushes the role past its bound.\n"""\n\n'
        for index in (1, 2)
    )
    source = _map_bytes("crowncrag-road").replace(
        b"[[climbable.ropes]]", extra + b"[[climbable.ropes]]", 1
    )

    with pytest.raises(AuthoredContractLoadError, match="too_long"):
        load_prepared_game_map_bytes(source)


def test_map_rejects_duplicate_portal_roles() -> None:
    source = _map_bytes("sunpetal-crossing").replace(b'role = "exit"', b'role = "entry"', 1)

    with pytest.raises(AuthoredContractLoadError, match="portal role values must be unique"):
        load_prepared_game_map_bytes(source)


def test_map_rejects_noncanonical_ladder_rise() -> None:
    source = _map_bytes("crowncrag-road").replace(b"rise_tiles = 4", b"rise_tiles = 5", 1)

    with pytest.raises(AuthoredContractLoadError, match="literal_error"):
        load_prepared_game_map_bytes(source)


def test_map_requires_rectangular_binary_occupancy_with_bottom_support() -> None:
    source = _map_bytes("sunpetal-crossing").replace(b"occupancy = [", b"unknown_occupancy = [", 1)
    with pytest.raises(AuthoredContractLoadError, match="occupancy"):
        load_prepared_game_map_bytes(source)

    source = _map_bytes("sunpetal-crossing").replace(
        b'"0000000000000000000000000000000000000000000000000000000000000000"',
        b'"000000000000000000000000000000000000000000000000000000000000000"',
        1,
    )
    with pytest.raises(AuthoredContractLoadError, match="rectangular"):
        load_prepared_game_map_bytes(source)

    source = _map_bytes("sunpetal-crossing").replace(
        b"1111111111111111111111111111111111111111111111111111111111111111",
        b"0000000000000000000000000000000000000000000000000000000000000000",
    )
    with pytest.raises(AuthoredContractLoadError, match="supported by the bottom row"):
        load_prepared_game_map_bytes(source)


def test_map_ground_requires_a_visible_escape_floor_and_two_tile_maximum_rise() -> None:
    with pytest.raises(ValueError, match="bottom-supported escape floor"):
        PreparedMapGround(
            mode="terrain-atlas-3x3-minimal-v1",
            reference_ids=["scene"],
            occupancy=["00000000", "11111111", "11111111", "11101111"],
            vertical_fit="floor_to_screen_bottom",
            walk_surface_row=1,
            prompt="Create readable terrain.",
        )
    with pytest.raises(ValueError, match="differ by at most two tiles"):
        PreparedMapGround(
            mode="terrain-atlas-3x3-minimal-v1",
            reference_ids=["scene"],
            occupancy=["00000000", "11101111", "11101111", "11101111", "11111111"],
            vertical_fit="floor_to_screen_bottom",
            walk_surface_row=1,
            prompt="Create readable terrain.",
        )
    accepted = PreparedMapGround(
        mode="terrain-atlas-3x3-minimal-v1",
        reference_ids=["scene"],
        occupancy=["00000000", "11101111", "11101111", "11111111"],
        vertical_fit="floor_to_screen_bottom",
        walk_surface_row=1,
        prompt="Create readable terrain.",
    )
    assert accepted.occupancy[-1] == "11111111"


def test_map_ladder_must_resolve_between_real_occupancy_surfaces() -> None:
    # Move a climbable off its deck: column 6 has one, column 40 does not.
    source = _map_bytes("crowncrag-road").replace(
        b"normalized_x = 0.067708", b"normalized_x = 0.421875", 1
    )
    with pytest.raises(AuthoredContractLoadError, match="exposed upper deck"):
        load_prepared_game_map_bytes(source)

    # Remove the deck the first climbable rises to.
    source = _map_bytes("crowncrag-road").replace(
        b"000011111111110000000000000000000000000000000000000000000000000000000000000000000000000000000000",
        b"0" * 96,
        1,
    )
    with pytest.raises(AuthoredContractLoadError, match="exposed upper deck"):
        load_prepared_game_map_bytes(source)


def test_map_portal_endpoint_may_move_to_another_valid_escape_floor() -> None:
    source = _map_bytes("crowncrag-road").replace(b"normalized_x = 0.05", b"normalized_x = 0.23", 1)
    game_map = load_prepared_game_map_bytes(source)
    assert game_map.portal is not None
    assert game_map.portal.endpoints[0].normalized_x == 0.23


def test_layer_vertical_anchor_and_alpha_mode_must_agree() -> None:
    source = _map_bytes("sunpetal-crossing").replace(
        b'alpha_mode = "opaque"\nvertical_anchor = "canvas_cover"',
        b'alpha_mode = "opaque"\nvertical_anchor = "screen_bottom"',
        1,
    )
    with pytest.raises(AuthoredContractLoadError, match="canvas_cover vertical anchor"):
        load_prepared_game_map_bytes(source)

    source = _map_bytes("sunpetal-crossing").replace(
        b'alpha_mode = "transparent"\nvertical_anchor = "screen_bottom"',
        b'alpha_mode = "transparent"\nvertical_anchor = "canvas_cover"',
        1,
    )
    with pytest.raises(AuthoredContractLoadError, match="only the opaque base layer"):
        load_prepared_game_map_bytes(source)


def test_canvas_cover_layer_cannot_declare_a_vertical_offset() -> None:
    source = _map_bytes("sunpetal-crossing").replace(
        b'vertical_anchor = "canvas_cover"',
        b'vertical_anchor = "canvas_cover"\nvertical_offset = 0.2',
        1,
    )
    with pytest.raises(AuthoredContractLoadError, match="cannot declare a vertical offset"):
        load_prepared_game_map_bytes(source)


def test_walk_surface_row_must_expose_a_terrain_surface() -> None:
    with pytest.raises(ValueError, match="expose a terrain surface"):
        PreparedMapGround(
            mode="terrain-atlas-3x3-minimal-v1",
            reference_ids=["scene"],
            occupancy=["11111111", "11111111", "11111111"],
            vertical_fit="floor_to_screen_bottom",
            walk_surface_row=2,
            prompt="Create readable terrain.",
        )
    accepted = PreparedMapGround(
        mode="terrain-atlas-3x3-minimal-v1",
        reference_ids=["scene"],
        occupancy=["11111111", "11111111", "11111111"],
        vertical_fit="floor_to_screen_bottom",
        walk_surface_row=0,
        prompt="Create readable terrain.",
    )
    assert accepted.walk_surface_row == 0
