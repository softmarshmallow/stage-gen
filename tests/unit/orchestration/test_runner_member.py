"""The runner genre member: resolution, seam rule, and the placement discipline.

Every geometric refusal is asserted through the real resolver against a
baseline package that passes the whole `reaction_fair_v1` discipline, so each
test violates exactly one rule.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stage_gen.orchestration.game_package import (
    GamePackageValidationError,
    resolve_game_package,
)

from .._runner_fixture import (
    ARC_PICKUPS,
    COVER_SHA256,
    FLAT_ROWS,
    GAP28_ROWS,
    GAP_ROWS,
    RUNNER_AVATAR_NO_SLIDE,
    RUNNER_GAMEPLAY_NO_DUCK,
    WIDE_FLAT_ROWS,
)
from .._runner_fixture import (
    chunk_toml as _chunk,
)
from .._runner_fixture import (
    runner_props_toml as _props,
)
from .._runner_fixture import (
    two_genre_package as _two_genre_package,
)


def _hazard(
    prop_id: str, column: int, *, anchor: str = "surface", clearance: float | None = None
) -> str:
    lines = [
        "[[segments.chunks.hazards]]",
        f'prop_id = "{prop_id}"',
        f"column = {column}",
        f'anchor = "{anchor}"',
    ]
    if clearance is not None:
        lines.append(f"clearance_rows = {clearance}")
    return "\n".join(lines) + "\n"


def _refused(tmp_path: Path, code: str, **overrides: str) -> None:
    package = _two_genre_package(tmp_path, **overrides)
    with pytest.raises(GamePackageValidationError) as error:
        resolve_game_package(package)
    assert error.value.code == code, str(error.value)


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
    _refused(tmp_path, "segment_gap_unclearable", chunks=_chunk("too_wide", wide_gap))


def test_a_max_gap_paired_with_a_max_rise_is_refused(tmp_path: Path) -> None:
    """A 3-column pit and a 2-tile rise each pass alone; together the rise
    steals airtime the span needs, and the proof sees them as one arc."""

    riser = ["0" * 28] * 3 + ["0" * 16 + "1" * 4 + "0" * 8] * 2 + ["1" * 13 + "000" + "1" * 12] * 3
    # No pickups needed: the span proof fires before the telegraph proof.
    _refused(tmp_path, "segment_gap_unclearable", chunks=_chunk("gap_with_rise", riser))


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
    _refused(tmp_path, "segment_seam_mismatch", chunks=_chunk("raised_edge", raised_edge))


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
    _refused(
        tmp_path,
        "invalid_runner_track",
        chunks=_chunk("hazard_over_pit", GAP_ROWS, extra=_hazard("toppled_cart", 5)),
    )


def test_a_runner_naming_an_undrawn_prop_is_refused(tmp_path: Path) -> None:
    _refused(
        tmp_path,
        "unresolved_cross_reference",
        chunks=_chunk("unknown_prop", FLAT_ROWS, extra=_hazard("missing_boulder", 2)),
    )


def test_a_hazard_inside_the_apron_is_refused(tmp_path: Path) -> None:
    """The apron is the price of the seam rule: without it, this hazard could
    meet a landing streamed in from any previous chunk."""

    _refused(
        tmp_path,
        "segment_placement_violation",
        chunks=_chunk("apron_hazard", WIDE_FLAT_ROWS, extra=_hazard("toppled_cart", 2)),
    )


def test_hazards_closer_than_the_separation_are_refused(tmp_path: Path) -> None:
    _refused(
        tmp_path,
        "segment_placement_violation",
        chunks=_chunk(
            "crowded",
            WIDE_FLAT_ROWS,
            extra=_hazard("toppled_cart", 8) + "\n" + _hazard("toppled_cart", 11),
        ),
    )


def test_a_hazard_inside_a_landing_clearance_is_refused(tmp_path: Path) -> None:
    """The apron closes the cross-chunk case; landing clearance closes the same
    counterexample one column inside the chunk."""

    _refused(
        tmp_path,
        "segment_placement_violation",
        chunks=_chunk(
            "landing_trap",
            GAP28_ROWS,
            extra=_hazard("toppled_cart", 20) + "\n" + ARC_PICKUPS,
        ),
    )


def test_an_unjumpable_hazard_silhouette_is_refused(tmp_path: Path) -> None:
    """At full player height the arc clears the cart for less than the press
    window floor; the correct fix is a taller jump profile, not a threshold."""

    _refused(
        tmp_path,
        "segment_hazard_unclearable",
        props=_props(cart_height_units=1.0),
    )


def test_an_untelegraphed_pit_is_refused(tmp_path: Path) -> None:
    _refused(
        tmp_path,
        "segment_untelegraphed",
        chunks=_chunk("silent_gap", GAP28_ROWS),
    )


def test_an_overhead_hazard_without_a_duck_profile_is_refused(tmp_path: Path) -> None:
    _refused(
        tmp_path,
        "invalid_runner_gameplay",
        chunks=_chunk(
            "low_garland",
            WIDE_FLAT_ROWS,
            extra=_hazard("toppled_cart", 11, anchor="overhead", clearance=1.6),
        ),
        gameplay=RUNNER_GAMEPLAY_NO_DUCK,
    )


def test_a_duck_profile_without_a_slide_motion_is_refused(tmp_path: Path) -> None:
    _refused(tmp_path, "invalid_runner_avatar", avatar=RUNNER_AVATAR_NO_SLIDE)


def test_an_overhead_clearance_a_ducked_avatar_cannot_fit_is_refused(tmp_path: Path) -> None:
    _refused(
        tmp_path,
        "segment_hazard_unclearable",
        chunks=_chunk(
            "crushing_garland",
            WIDE_FLAT_ROWS,
            extra=_hazard("toppled_cart", 11, anchor="overhead", clearance=1.0),
        ),
    )


def test_an_overhead_clearance_admitting_a_standing_run_is_refused(tmp_path: Path) -> None:
    _refused(
        tmp_path,
        "invalid_runner_track",
        chunks=_chunk(
            "decorative_garland",
            WIDE_FLAT_ROWS,
            extra=_hazard("toppled_cart", 11, anchor="overhead", clearance=2.3),
        ),
    )


def test_an_avatar_slide_without_a_duck_profile_is_refused(tmp_path: Path) -> None:
    """The verb coupling holds in both directions: a slide strip no duck
    profile can trigger would be silent dead spend, not staged art."""

    _refused(
        tmp_path,
        "invalid_runner_avatar",
        chunks=_chunk("warmup_flat", WIDE_FLAT_ROWS),
        gameplay=RUNNER_GAMEPLAY_NO_DUCK,
    )


def test_a_playback_shape_the_runtime_refuses_is_refused_at_admission(tmp_path: Path) -> None:
    from .._runner_fixture import RUNNER_AVATAR

    looping_jump = RUNNER_AVATAR.replace(
        'state = "jump"\nplayback_mode = "once"', 'state = "jump"\nplayback_mode = "loop"'
    )
    _refused(tmp_path, "invalid_runner_avatar", avatar=looping_jump)


def test_a_frame_outside_the_runner_atlas_is_refused_at_admission(tmp_path: Path) -> None:
    from .._runner_fixture import RUNNER_AVATAR

    wide_frames = RUNNER_AVATAR.replace(
        'state = "slide"\nplayback_mode = "once"\ncanonical_frame_indices = [0, 1, 2, 3]',
        'state = "slide"\nplayback_mode = "once"\ncanonical_frame_indices = [0, 1, 2, 4]',
    )
    _refused(tmp_path, "invalid_runner_avatar", avatar=wide_frames)


def test_a_pit_inside_the_apron_is_refused(tmp_path: Path) -> None:
    pit_in_apron = ["0" * 24] * 5 + ["111" + "00" + "1" * 19] * 3
    _refused(
        tmp_path,
        "segment_placement_violation",
        chunks=_chunk("apron_pit", pit_in_apron),
    )


def test_an_unlevel_landing_window_is_refused(tmp_path: Path) -> None:
    """A rise one column after a pit landing is a step inside the window."""

    stepped = ["0" * 28] * 4 + ["0" * 20 + "1" * 2 + "0" * 6] * 1 + ["1" * 16 + "000" + "1" * 9] * 3
    _refused(
        tmp_path,
        "segment_placement_violation",
        chunks=_chunk("stepped_landing", stepped, extra=ARC_PICKUPS),
    )


def test_terrain_features_closer_than_the_separation_are_refused(tmp_path: Path) -> None:
    """Two pits closer than one flown-at-cap arc share a jump uninvited."""

    twin_pits = ["0" * 28] * 5 + ["1" * 8 + "00" + "1" * 5 + "00" + "1" * 11] * 3
    _refused(
        tmp_path,
        "segment_placement_violation",
        chunks=_chunk("twin_pits", twin_pits),
    )


def test_a_rise_over_the_profile_cap_is_refused(tmp_path: Path) -> None:
    tall_step = ["0" * 28] * 2 + ["0" * 14 + "1" * 4 + "0" * 10] * 3 + ["1" * 28] * 3
    _refused(tmp_path, "invalid_runner_track", chunks=_chunk("tall_step", tall_step))


def test_a_drop_scattering_into_a_pit_is_refused(tmp_path: Path) -> None:
    """A run-off fall has no verb: the scatter zone below a drop must be level."""

    drop_into_pit = (
        ["0" * 28] * 3 + ["0" * 7 + "1" * 7 + "0" * 14] * 2 + ["1" * 15 + "00" + "1" * 11] * 3
    )
    _refused(
        tmp_path,
        "segment_placement_violation",
        chunks=_chunk("drop_trap", drop_into_pit),
    )


def test_a_surface_hazard_without_a_declared_height_is_refused(tmp_path: Path) -> None:
    from .._runner_fixture import RUNNER_PROPS

    heightless = RUNNER_PROPS.replace("height_units = 0.85\n", "")
    _refused(tmp_path, "segment_hazard_unclearable", props=heightless)


def test_an_untelegraphed_surface_hazard_is_refused(tmp_path: Path) -> None:
    """A surface hazard is a jump demand; under pickup_arc_v1 it carries a trail."""

    _refused(
        tmp_path,
        "segment_untelegraphed",
        chunks=_chunk(
            "silent_cart",
            WIDE_FLAT_ROWS,
            extra=_hazard("toppled_cart", 11),
        ),
    )
