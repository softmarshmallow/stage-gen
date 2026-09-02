"""The runner genre member: resolution, seam rule, and the placement discipline.

Every geometric refusal is asserted through the real resolver against a
baseline package that passes the whole `reaction_fair_v1` discipline, so each
test violates exactly one rule.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from hashlib import sha256
from io import BytesIO, StringIO
from pathlib import Path

import pytest
from PIL import Image

from stage_gen.interfaces.cli import main
from stage_gen.orchestration.game_package import (
    GamePackageValidationError,
    ResolvedRunnerOnlyPackage,
    resolve_game_package,
    resolve_prepared_package,
    validate_game_package,
)
from stage_gen.recipes.sideview_runner.runner_request import resolve_runner_package

from .._runner_fixture import (
    ARC_PICKUPS,
    COVER_SHA256,
    ENCOUNTER_CHUNKS,
    ENCOUNTER_ROWS,
    ENCOUNTER_WALK_SURFACE_ROW,
    FLAT_ROWS,
    GAP28_ROWS,
    GAP_ROWS,
    RUNNER_AVATAR,
    RUNNER_AVATAR_FLY,
    RUNNER_AVATAR_NO_SLIDE,
    RUNNER_BOSSES,
    RUNNER_GAMEPLAY_ENCOUNTER,
    RUNNER_GAMEPLAY_NO_DUCK,
    RUNNER_PROJECTILES,
    WIDE_FLAT_ROWS,
    runner_only_package,
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


def test_a_runner_only_package_resolves_without_inventing_a_platformer(tmp_path: Path) -> None:
    source = runner_only_package(tmp_path)

    package = resolve_prepared_package(source)

    assert isinstance(package, ResolvedRunnerOnlyPackage)
    assert [entry.genre for entry in package.game.genres] == ["runner"]
    assert package.runner.track.track_id == "meadow-dash"
    identity = package.identity()
    assert identity["schema_version"] == 6
    assert identity["kind"] == "resolved-game-package-v6"
    genres = identity["genres"]
    assert isinstance(genres, dict)
    assert list(genres) == ["runner"]
    assert genres["runner"] == {
        "track_id": "meadow-dash",
        "avatar_id": "wayfarer_sprinter",
        "segment_ids": ["warmup_flat", "first_gap"],
        "prop_ids": ["toppled_cart"],
        "item_ids": ["meadow_penny"],
        "effect_ids": [
            "air_jump_whistle",
            "clear_sparkle",
            "leaf_slide",
            "run_ended",
            "soft_landing",
            "takeoff_whistle",
            "token_chime",
        ],
        "track_ids": ["orchard_rush", "sunpetal_sprint"],
    }
    assert resolve_runner_package(source).package is not None


def test_the_platformer_compatibility_resolver_still_requires_its_member(
    tmp_path: Path,
) -> None:
    with pytest.raises(GamePackageValidationError) as error:
        resolve_game_package(runner_only_package(tmp_path))

    assert error.value.code == "missing_genre_member"
    assert "platformer" in str(error.value)


def test_runner_only_directory_and_zip_have_the_same_closure(tmp_path: Path) -> None:
    source = runner_only_package(tmp_path)
    archive = tmp_path / "runner-only.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                output.write(path, Path("runner-only", path.relative_to(source)).as_posix())

    directory = resolve_prepared_package(source)
    zipped = resolve_prepared_package(archive)

    assert isinstance(directory, ResolvedRunnerOnlyPackage)
    assert isinstance(zipped, ResolvedRunnerOnlyPackage)
    assert zipped.source_kind == "zip"
    assert zipped.closure_sha256 == directory.closure_sha256


def test_repository_package_validation_accepts_a_runner_only_selection(tmp_path: Path) -> None:
    authored = runner_only_package(tmp_path / "authored")
    workspace = tmp_path / "workspace"
    package = workspace / "library" / "games" / "bellweather"
    package.parent.mkdir(parents=True)
    shutil.copytree(authored, package)
    (package.parent / "main.toml").write_text(
        """schema_version = 4
kind = "game-package-v4"
game_id = "bellweather"
package_ref = "library/games/bellweather/game.toml"
""",
        encoding="utf-8",
    )

    report = validate_game_package(workspace)

    assert report["valid"] is True
    assert report["schema_version"] == 6
    assert report["kind"] == "game-package-validation-v6"
    assert report["genres"] == resolve_prepared_package(package).identity()["genres"]


def test_package_cli_validates_digests_and_selects_the_only_runner(tmp_path: Path) -> None:
    package = runner_only_package(tmp_path)
    validate_output = StringIO()

    assert main(["package", "validate", "--input", str(package)], stdout=validate_output) == 0
    report = json.loads(validate_output.getvalue())
    assert report["valid"] is True
    assert list(report["genres"]) == ["runner"]

    digest_output = StringIO()
    assert main(["package", "digest", "--input", str(package)], stdout=digest_output) == 0
    assert digest_output.getvalue() == f"{report['closure_sha256']}\n"

    plan_output = StringIO()
    assert main(["package", "plan", "--input", str(package)], stdout=plan_output) == 0
    plan = json.loads(plan_output.getvalue())
    assert plan["genre"] == "runner"
    assert plan["graph"]["nodes"][0]["node_id"] == "package-resolve"


def test_combined_avatar_requires_a_package_level_visible_rider_head_override(
    tmp_path: Path,
) -> None:
    combined = RUNNER_AVATAR.replace(
        '''body_kind = "human"
age = 19
silhouette_mode = "single_character_v1"
proportion_basis = "character_head_v1"''',
        '''body_kind = "piloted_machine"
age = 11
silhouette_mode = "visible_rider_machine_v1"
proportion_basis = "visible_rider_head_v1"''',
    )
    without_override = runner_only_package(tmp_path / "without", avatar=combined)
    with pytest.raises(GamePackageValidationError) as error:
        resolve_prepared_package(without_override)
    assert error.value.code == "invalid_runner_avatar"
    assert "visible rider heads" in str(error.value)

    admitted = resolve_prepared_package(
        runner_only_package(tmp_path / "with", avatar=combined, piloted_heads_tall=4.5)
    )
    assert isinstance(admitted, ResolvedRunnerOnlyPackage)
    assert admitted.runner.avatar.avatar.age == 11
    assert admitted.game.proportion.heads_for("piloted_machine") == 4.5


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


def test_a_floating_solid_above_an_otherwise_valid_seam_is_refused(tmp_path: Path) -> None:
    floating_edge = [
        "000000000000",
        "000000000000",
        "000000000000",
        "100000000000",
        "000000000000",
        "111111111111",
        "111111111111",
        "111111111111",
    ]
    _refused(tmp_path, "segment_seam_mismatch", chunks=_chunk("floating_edge", floating_edge))


def test_structural_ground_rejects_transparent_material_references_before_planning(
    tmp_path: Path,
) -> None:
    from .._runner_fixture import COVER_SHA256, runner_only_package

    package = runner_only_package(tmp_path)
    track_path = package / "runner/track.toml"
    track_path.write_text(
        track_path.read_text(encoding="utf-8").replace(
            'mode = "terrain-atlas-3x3-minimal-v1"',
            'mode = "runner-structural-ground-v1"',
        ),
        encoding="utf-8",
    )
    stream = BytesIO()
    Image.new("RGBA", (32, 32), (80, 70, 60, 0)).save(stream, format="PNG")
    transparent = stream.getvalue()
    replacement_sha256 = sha256(transparent).hexdigest()
    (package / "references/cover.png").write_bytes(transparent)
    contract_paths = [package / "game.toml", *sorted((package / "runner").rglob("*.toml"))]
    for path in contract_paths:
        path.write_text(
            path.read_text(encoding="utf-8").replace(COVER_SHA256, replacement_sha256),
            encoding="utf-8",
        )

    with pytest.raises(GamePackageValidationError) as error:
        resolve_game_package(package)
    assert error.value.code == "invalid_reference_image"
    assert "structural-ground references are unusable" in str(error.value)


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


# --------------------------------------------------------------------- encounter


def _encounter_package(tmp_path: Path, **overrides: str) -> Path:
    """The passing encounter closure: taller band, arena chunk, boss, projectiles."""

    settings: dict[str, object] = {
        "chunks": ENCOUNTER_CHUNKS,
        "gameplay": RUNNER_GAMEPLAY_ENCOUNTER,
        "avatar": RUNNER_AVATAR_FLY,
        "bosses": RUNNER_BOSSES,
        "projectiles": RUNNER_PROJECTILES,
        "rows": ENCOUNTER_ROWS,
        "walk_surface_row": ENCOUNTER_WALK_SURFACE_ROW,
    }
    settings.update(overrides)
    return _two_genre_package(tmp_path, **settings)  # type: ignore[arg-type]


def _encounter_refused(tmp_path: Path, code: str, **overrides: str) -> str:
    package = _encounter_package(tmp_path, **overrides)
    with pytest.raises(GamePackageValidationError) as error:
        resolve_game_package(package)
    assert error.value.code == code, str(error.value)
    return str(error.value)


def test_an_encounter_package_resolves_with_its_boss_arena_and_projectiles(
    tmp_path: Path,
) -> None:
    resolved = resolve_game_package(_encounter_package(tmp_path))

    runner = resolved.runner
    assert runner is not None
    assert runner.gameplay.encounter is not None
    assert runner.gameplay.encounter.boss_id == "bramble_harvester"
    assert runner.bosses is not None
    assert [entry.boss_id for entry in runner.bosses.bosses] == ["bramble_harvester"]
    assert runner.projectiles is not None
    assert sorted(entry.projectile_id for entry in runner.projectiles.projectiles) == [
        "spark_pin",
        "thorn_burst",
    ]
    assert [chunk.segment_id for chunk in runner.track.segments.arena_chunks()] == ["harvest_arena"]


def test_an_encounter_without_a_fly_motion_is_refused(tmp_path: Path) -> None:
    message = _encounter_refused(tmp_path, "invalid_runner_avatar", avatar=RUNNER_AVATAR)

    assert "no fly motion to wear" in message


def test_a_fly_motion_without_an_encounter_is_refused(tmp_path: Path) -> None:
    package = _two_genre_package(tmp_path, avatar=RUNNER_AVATAR_FLY)

    with pytest.raises(GamePackageValidationError) as error:
        resolve_game_package(package)

    assert error.value.code == "invalid_runner_avatar"
    assert "no encounter to trigger it" in str(error.value)


def test_an_encounter_naming_an_undrawn_boss_is_refused(tmp_path: Path) -> None:
    _encounter_refused(
        tmp_path,
        "unresolved_cross_reference",
        gameplay=RUNNER_GAMEPLAY_ENCOUNTER.replace(
            'boss_id = "bramble_harvester"', 'boss_id = "thicket_router"', 1
        ),
    )


def test_an_encounter_naming_an_unauthored_arena_is_refused(tmp_path: Path) -> None:
    _encounter_refused(
        tmp_path,
        "unresolved_cross_reference",
        gameplay=RUNNER_GAMEPLAY_ENCOUNTER.replace(
            'arena_segment_id = "harvest_arena"', 'arena_segment_id = "harvest_flat"', 1
        ),
    )


def test_an_encounter_naming_an_undrawn_projectile_is_refused(tmp_path: Path) -> None:
    _encounter_refused(
        tmp_path,
        "unresolved_cross_reference",
        gameplay=RUNNER_GAMEPLAY_ENCOUNTER.replace(
            'boss_projectile_id = "thorn_burst"', 'boss_projectile_id = "seed_shell"', 1
        ),
    )


def test_an_encounter_without_a_boss_catalog_is_refused(tmp_path: Path) -> None:
    package = _two_genre_package(
        tmp_path,
        chunks=ENCOUNTER_CHUNKS,
        gameplay=RUNNER_GAMEPLAY_ENCOUNTER,
        avatar=RUNNER_AVATAR_FLY,
        projectiles=RUNNER_PROJECTILES,
        rows=ENCOUNTER_ROWS,
        walk_surface_row=ENCOUNTER_WALK_SURFACE_ROW,
    )

    with pytest.raises(GamePackageValidationError) as error:
        resolve_game_package(package)

    assert error.value.code == "unresolved_cross_reference"
    assert "no boss catalog" in str(error.value)


def test_an_arena_chunk_without_an_encounter_is_dead_art(tmp_path: Path) -> None:
    package = _two_genre_package(
        tmp_path,
        chunks=ENCOUNTER_CHUNKS,
        rows=ENCOUNTER_ROWS,
        walk_surface_row=ENCOUNTER_WALK_SURFACE_ROW,
    )

    with pytest.raises(GamePackageValidationError) as error:
        resolve_game_package(package)

    assert error.value.code == "invalid_runner_track"
    assert "harvest_arena" in str(error.value)


def test_a_boss_no_encounter_fights_is_dead_art(tmp_path: Path) -> None:
    two_bosses = RUNNER_BOSSES + RUNNER_BOSSES.split("[[bosses]]", 1)[1].join(
        ["[[bosses]]", ""]
    ).replace("bramble_harvester", "thicket_router").replace("Bramble Harvester", "Thicket Router")

    message = _encounter_refused(tmp_path, "invalid_runner_boss", bosses=two_bosses)

    assert "thicket_router" in message


def test_a_projectile_no_role_fires_is_dead_art(tmp_path: Path) -> None:
    spare = (
        RUNNER_PROJECTILES
        + """
[[projectiles]]
projectile_id = "husk_shard"
display_name = "Husk Shard"
silhouette = "irregular_v1"
flight = "flat_bolt_v1"
impact = "single_target_v1"
reference_ids = ["cover_style"]
length_units = 0.28
prompt = "A drifting fragment of dry husk."
"""
    )

    message = _encounter_refused(tmp_path, "invalid_projectile_content", projectiles=spare)

    assert "husk_shard" in message


def test_a_salvo_that_leaves_no_clear_lane_is_refused(tmp_path: Path) -> None:
    """The default eight-row band cannot hold three shots and a 2.40-row avatar."""

    package = _two_genre_package(
        tmp_path,
        chunks="\n".join(
            [
                _chunk("meadow_flat", WIDE_FLAT_ROWS),
                _chunk("meadow_arena", WIDE_FLAT_ROWS, role="arena"),
            ]
        ),
        gameplay=RUNNER_GAMEPLAY_ENCOUNTER.replace(
            'arena_segment_id = "harvest_arena"', 'arena_segment_id = "meadow_arena"', 1
        ),
        avatar=RUNNER_AVATAR_FLY,
        bosses=RUNNER_BOSSES,
        projectiles=RUNNER_PROJECTILES,
    )

    with pytest.raises(GamePackageValidationError) as error:
        resolve_game_package(package)

    assert error.value.code == "segment_hazard_unclearable"
    assert "lane" in str(error.value)
