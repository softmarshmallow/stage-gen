from __future__ import annotations

from pathlib import Path

import pytest

from stage_gen.components._game_input import AuthoredContractLoadError
from stage_gen.components.game_map import (
    bottom_contiguous_surface_row,
    load_prepared_game_map_bytes,
    normalized_terrain_column,
)

PACKAGE = Path(__file__).resolve().parents[4] / "library" / "games" / "bellweather"


def _map_bytes(map_id: str) -> bytes:
    return (PACKAGE / "maps" / f"{map_id}.toml").read_bytes()


def test_canonical_maps_own_portal_endpoints_and_optional_ladder_geometry() -> None:
    village = load_prepared_game_map_bytes(_map_bytes("sunpetal-crossing"))
    road = load_prepared_game_map_bytes(_map_bytes("crowncrag-road"))

    assert village.kind == road.kind == "game-map-v4"
    assert village.ladder is None
    assert village.portal is not None
    assert [endpoint.anchor for endpoint in village.portal.endpoints] == [
        "west_gate",
        "east_gate",
    ]
    assert [endpoint.role for endpoint in village.portal.endpoints] == ["entry", "exit"]

    assert road.ladder is not None
    assert road.ladder.mode == "ladder-4-tile-v1"
    assert road.ladder.placements[0].model_dump() == {
        "ladder_id": "bellroot_ladder",
        "normalized_x": 0.52,
        "bottom_surface": "terrain",
        "rise_tiles": 4,
    }
    assert road.portal is not None
    assert road.portal.mode == "portal-pair-1x2-v1"
    occupancy = road.ground.occupancy
    assert len(occupancy) == 12
    assert {len(row) for row in occupancy} == {64}
    ladder_column = normalized_terrain_column(0.52, 64)
    lower_surface = bottom_contiguous_surface_row(occupancy, ladder_column)
    assert ladder_column == 33
    assert lower_surface == 9
    assert occupancy[lower_surface - 4][ladder_column] == "1"
    assert occupancy[lower_surface - 5][ladder_column] == "0"
    assert occupancy[lower_surface - 3][ladder_column] == "0"


def test_map_rejects_the_obsolete_v3_identity() -> None:
    source = _map_bytes("sunpetal-crossing").replace(
        b'schema_version = 4\nkind = "game-map-v4"',
        b'schema_version = 3\nkind = "game-map-v3"',
        1,
    )

    with pytest.raises(AuthoredContractLoadError, match="literal_error"):
        load_prepared_game_map_bytes(source)


def test_map_rejects_unknown_ladder_reference() -> None:
    source = _map_bytes("crowncrag-road").replace(
        b'reference_ids = ["amberbell_scene"]\nprompt = """\nCreate one sturdy',
        b'reference_ids = ["missing_ladder_reference"]\nprompt = """\nCreate one sturdy',
        1,
    )

    with pytest.raises(AuthoredContractLoadError, match="unknown IDs"):
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


def test_map_ladder_must_resolve_between_real_occupancy_surfaces() -> None:
    source = _map_bytes("crowncrag-road").replace(b"normalized_x = 0.52", b"normalized_x = 0.23", 1)
    with pytest.raises(AuthoredContractLoadError, match="bottom-supported terrain"):
        load_prepared_game_map_bytes(source)

    source = _map_bytes("crowncrag-road").replace(
        b"0000000000000000000000000000011111111110000000000000000000000000",
        b"0000000000000000000000000000000000000000000000000000000000000000",
        1,
    )
    with pytest.raises(AuthoredContractLoadError, match="exposed upper deck"):
        load_prepared_game_map_bytes(source)


def test_map_portal_endpoint_must_resolve_to_supported_terrain() -> None:
    source = _map_bytes("crowncrag-road").replace(b"normalized_x = 0.05", b"normalized_x = 0.23", 1)

    with pytest.raises(AuthoredContractLoadError, match="portal endpoint west_gate"):
        load_prepared_game_map_bytes(source)
