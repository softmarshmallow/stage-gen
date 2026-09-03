from __future__ import annotations

from pathlib import Path

import pytest

from stage_gen.components._game_input import AuthoredContractLoadError
from stage_gen.components.platformer_map import (
    bottom_contiguous_surface_row,
    load_prepared_game_map_bytes,
    normalized_terrain_column,
)
from stage_gen.components.platformer_map.prepared import (
    PreparedMapTerrain,
    validate_generated_terrain,
)


def _terrain(
    map_id: str, occupancy: list[str], walk_surface_row: int, **kwargs: object
) -> PreparedMapTerrain:
    """A generated geometry artifact. Geometry rules live here now, not in the map document."""

    return PreparedMapTerrain(
        schema_version=1,
        kind="map-terrain-v1",
        map_id=map_id,
        occupancy=occupancy,
        walk_surface_row=walk_surface_row,
        **kwargs,  # type: ignore[arg-type]
    )


#: Columns the road fixture stands its climbables in, one per declared variant.
_ROAD_COLUMNS = (10, 30, 50)


def _road_terrain(**overrides: object) -> PreparedMapTerrain:
    """Geometry the shipped road would accept: flat ground with an exposed deck per climbable."""

    rows, columns = 14, 56
    grid = [["0"] * columns for _ in range(rows)]
    for row in (11, 12, 13):
        grid[row] = ["1"] * columns
    for column in _ROAD_COLUMNS:
        grid[7][column] = "1"  # four tiles above the surface row, with row 6 left empty
    variants = ("bellroot_ladder", "shrine_rope_ladder", "bellrope_climb")
    placements = [
        {
            "climbable_id": f"c{index + 1}",
            "variant_id": variant,
            "normalized_x": round((column + 0.5) / columns, 6),
            "bottom_surface": "terrain",
            "rise_tiles": 4,
        }
        for index, (column, variant) in enumerate(zip(_ROAD_COLUMNS, variants, strict=True))
    ]
    fields: dict[str, object] = {
        "occupancy": ["".join(row) for row in grid],
        "walk_surface_row": 11,
        "climbable_placements": placements,
    }
    fields.update(overrides)
    terrain = _terrain("crowncrag-road", **fields)  # type: ignore[arg-type]
    return terrain


PACKAGE = Path(__file__).resolve().parents[4] / "library" / "games" / "bellweather"


def _map_bytes(map_id: str) -> bytes:
    return (PACKAGE / "maps" / f"{map_id}.toml").read_bytes()


def test_canonical_maps_own_portal_endpoints_and_optional_climbable_geometry() -> None:
    village = load_prepared_game_map_bytes(_map_bytes("sunpetal-crossing"))
    road = load_prepared_game_map_bytes(_map_bytes("crowncrag-road"))

    assert village.kind == road.kind == "game-map-v10"
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
    assert road.portal is not None
    assert road.portal.mode == "portal-pair-1x2-v1"

    # The map asks for terrain; it does not carry any. Geometry arrives as a generated artifact.
    assert road.terrain.mode == "platformer-chunk-map-v1"
    assert (road.terrain.rows, road.terrain.columns) == (14, 56)
    assert road.terrain.brief.strip()
    assert not hasattr(road.ground, "occupancy")

    terrain = _road_terrain()
    validate_generated_terrain(road, terrain)
    for placement in terrain.climbable_placements:
        column = normalized_terrain_column(placement.normalized_x, 56)
        lower_surface = bottom_contiguous_surface_row(terrain.occupancy, column)
        assert lower_surface is not None
        assert terrain.occupancy[lower_surface - 4][column] == "1"
        assert terrain.occupancy[lower_surface - 5][column] == "0"
        assert terrain.occupancy[lower_surface - 3][column] == "0"


def test_map_rejects_a_retired_identity() -> None:
    source = _map_bytes("sunpetal-crossing").replace(
        b'schema_version = 10\nkind = "game-map-v10"',
        b'schema_version = 9\nkind = "game-map-v9"',
        1,
    )

    with pytest.raises(AuthoredContractLoadError, match="literal_error"):
        load_prepared_game_map_bytes(source)


def test_map_declares_the_camera_outside_the_block_that_directs_generation() -> None:
    # The camera is a runtime fact. Keeping it out of [view] is what stops a camera edit from
    # re-billing every map image, so the separation is asserted rather than left to convention.
    village = load_prepared_game_map_bytes(_map_bytes("sunpetal-crossing"))
    road = load_prepared_game_map_bytes(_map_bytes("crowncrag-road"))

    assert set(village.view.model_dump()) == {"profile", "gameplay_space"}
    assert village.camera.follow_axes == ["x"]
    # The road stacks decks four tiles above the surface, so it asks for a camera that can reach
    # them; the flat village does not.
    assert road.camera.follow_axes == ["x", "y"]
    assert village.camera.mode == road.camera.mode == "player_follow"


def test_map_rejects_a_camera_axis_list_that_is_not_canonical() -> None:
    for broken, problem in (
        (b'follow_axes = ["y", "x"]', "canonical x, y order"),
        (b'follow_axes = ["x", "x"]', "unique"),
        (b'follow_axes = ["z"]', "literal_error"),
        (b'mode = "cinematic_rail"', "literal_error"),
    ):
        field = broken.split(b" =")[0]
        source = _map_bytes("crowncrag-road").replace(
            b'mode = "player_follow"\nfollow_axes = ["x", "y"]',
            (b'mode = "player_follow"\n' + broken)
            if field == b"follow_axes"
            else (broken + b'\nfollow_axes = ["x", "y"]'),
            1,
        )
        with pytest.raises(AuthoredContractLoadError, match=problem):
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
    road = load_prepared_game_map_bytes(_map_bytes("crowncrag-road"))
    placements = [dict(entry) for entry in _road_terrain().model_dump()["climbable_placements"]]
    placements[0]["variant_id"] = "no_such_variant"

    with pytest.raises(ValueError, match="undeclared variants"):
        validate_generated_terrain(road, _road_terrain(climbable_placements=placements))


def test_map_rejects_a_declared_variant_that_is_never_placed() -> None:
    # The map may only declare artwork it actually uses; an unplaced variant is paid generation
    # nobody sees.
    road = load_prepared_game_map_bytes(_map_bytes("crowncrag-road"))
    placements = [dict(entry) for entry in _road_terrain().model_dump()["climbable_placements"]]

    with pytest.raises(ValueError, match="unplaced variants"):
        validate_generated_terrain(road, _road_terrain(climbable_placements=placements[:-1]))


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
    placements = [dict(entry) for entry in _road_terrain().model_dump()["climbable_placements"]]
    placements[0]["rise_tiles"] = 5

    with pytest.raises(ValueError, match="rise_tiles"):
        _road_terrain(climbable_placements=placements)


def test_map_requires_rectangular_binary_occupancy_with_bottom_support() -> None:
    with pytest.raises(ValueError, match="rectangular"):
        _terrain("sunpetal-crossing", ["00000000", "1111111"], 1)
    with pytest.raises(ValueError, match="only zero and one"):
        _terrain("sunpetal-crossing", ["00000000", "1111111x"], 1)
    with pytest.raises(ValueError, match="supported by the bottom row"):
        _terrain("sunpetal-crossing", ["00000000", "00000000"], 1)


def test_map_ground_requires_a_visible_escape_floor_and_two_tile_maximum_rise() -> None:
    with pytest.raises(ValueError, match="bottom-supported escape floor"):
        _terrain("sunpetal-crossing", ["00000000", "11111111", "11111111", "11101111"], 1)
    with pytest.raises(ValueError, match="differ by at most two tiles"):
        _terrain(
            "sunpetal-crossing",
            ["00000000", "11101111", "11101111", "11101111", "11111111"],
            1,
        )
    accepted = _terrain("sunpetal-crossing", ["00000000", "11101111", "11101111", "11111111"], 1)
    assert accepted.occupancy[-1] == "11111111"


def test_map_ladder_must_resolve_between_real_occupancy_surfaces() -> None:
    road = load_prepared_game_map_bytes(_map_bytes("crowncrag-road"))
    # Move a climbable off its deck: column 10 has one, column 40 does not.
    placements = [dict(entry) for entry in _road_terrain().model_dump()["climbable_placements"]]
    placements[0]["normalized_x"] = round(40.5 / 56, 6)
    with pytest.raises(ValueError, match="exposed upper deck"):
        validate_generated_terrain(road, _road_terrain(climbable_placements=placements))

    # Remove the deck the first climbable rises to.
    rows = _road_terrain().occupancy
    stripped = list(rows)
    stripped[7] = "0" * 56
    with pytest.raises(ValueError, match="exposed upper deck"):
        validate_generated_terrain(road, _road_terrain(occupancy=stripped))


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
        _terrain("sunpetal-crossing", ["11111111", "11111111", "11111111"], 2)
    accepted = _terrain("sunpetal-crossing", ["11111111", "11111111", "11111111"], 0)
    assert accepted.walk_surface_row == 0
