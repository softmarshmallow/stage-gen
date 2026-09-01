"""The runner genre member: resolution, seam rule, and clearable-gap admission."""

from __future__ import annotations

from pathlib import Path

import pytest

from stage_gen.orchestration.game_package import (
    GamePackageValidationError,
    resolve_game_package,
)

from .._runner_fixture import (
    COVER_SHA256,
    FLAT_ROWS,
    GAP_ROWS,
)
from .._runner_fixture import (
    chunk_toml as _chunk,
)
from .._runner_fixture import (
    two_genre_package as _two_genre_package,
)


def test_a_two_genre_package_resolves_both_members(tmp_path: Path) -> None:
    package = resolve_game_package(_two_genre_package(tmp_path))

    assert [entry.genre for entry in package.game.genres] == ["platformer", "runner"]
    assert package.runner is not None
    assert package.runner.track.track_id == "meadow-dash"
    assert package.runner.avatar.avatar.avatar_id == "wayfarer_sprinter"
    identity = package.identity()
    genres = identity["genres"]
    assert isinstance(genres, dict)
    assert genres["runner"]["segment_ids"] == ["warmup_flat", "first_gap"]
    # The shared reference: both genres bind the same cover bytes by digest.
    assert package.file("references/cover.png").sha256 == COVER_SHA256


def test_an_unclearable_gap_is_refused_before_any_spend(tmp_path: Path) -> None:
    wide_gap = [
        "000000000000",
        "000000000000",
        "000000000000",
        "000000000000",
        "000000000000",
        "111100001111",
        "111100001111",
        "111100001111",
    ]
    package = _two_genre_package(tmp_path, chunks=_chunk("too_wide", wide_gap))

    with pytest.raises(GamePackageValidationError) as error:
        resolve_game_package(package)
    assert error.value.code == "segment_gap_unclearable"


def test_a_chunk_whose_seam_breaks_the_shared_surface_is_refused(tmp_path: Path) -> None:
    raised_edge = [
        "000000000000",
        "000000000000",
        "000000000000",
        "000000000000",
        "100000000000",
        "111111111111",
        "111111111111",
        "111111111111",
    ]
    package = _two_genre_package(tmp_path, chunks=_chunk("raised_edge", raised_edge))

    with pytest.raises(GamePackageValidationError) as error:
        resolve_game_package(package)
    assert error.value.code == "segment_seam_mismatch"


def test_a_pit_stays_illegal_in_the_platformer_family() -> None:
    """The rule the runner drops stays enforced for its sibling: the platformer's
    generated-terrain contract still refuses a bottom-row hole, so widening the
    container did not loosen the family that forbids pits."""

    import pydantic

    from stage_gen.components.platformer_map.prepared import PreparedMapTerrain

    holed = ["000000000000"] * 5 + ["111111111111"] * 2 + ["111111111110"]
    with pytest.raises(pydantic.ValidationError, match="bottom-supported escape floor"):
        PreparedMapTerrain(
            schema_version=1,
            kind="map-terrain-v1",
            map_id="meadow-dash",
            occupancy=holed,
            walk_surface_row=5,
        )


def test_a_runner_hazard_over_a_pit_is_refused(tmp_path: Path) -> None:
    package = _two_genre_package(
        tmp_path,
        chunks=_chunk(
            "hazard_over_pit",
            GAP_ROWS,
            extra='[[segments.chunks.hazards]]\nprop_id = "toppled_cart"\ncolumn = 5\n',
        ),
    )

    with pytest.raises(GamePackageValidationError) as error:
        resolve_game_package(package)
    assert error.value.code == "invalid_runner_track"


def test_a_runner_naming_an_undrawn_prop_is_refused(tmp_path: Path) -> None:
    package = _two_genre_package(
        tmp_path,
        chunks=_chunk(
            "unknown_prop",
            FLAT_ROWS,
            extra='[[segments.chunks.hazards]]\nprop_id = "missing_boulder"\ncolumn = 2\n',
        ),
    )

    with pytest.raises(GamePackageValidationError) as error:
        resolve_game_package(package)
    assert error.value.code == "unresolved_cross_reference"
