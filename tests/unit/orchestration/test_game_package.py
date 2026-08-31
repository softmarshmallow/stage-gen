from __future__ import annotations

import hashlib
import re
import shutil
import stat
import zipfile
from pathlib import Path

import pytest

from stage_gen.orchestration.game_package import (
    GamePackageValidationError,
    invalid_game_package_report,
    resolve_game_package,
    validate_game_package,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SOURCE_PACKAGE = REPOSITORY_ROOT / "library" / "games" / "bellweather"


def _copy_package(tmp_path: Path) -> Path:
    target = tmp_path / "bellweather"
    shutil.copytree(SOURCE_PACKAGE, target)
    return target


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_zip(package: Path, output: Path, *, wrapped: bool = True) -> None:
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(package.rglob("*")):
            if not source.is_file():
                continue
            relative = source.relative_to(package)
            archive_name = Path(package.name, relative) if wrapped else relative
            archive.write(source, archive_name.as_posix())


def test_resolve_bellweather_directory_captures_complete_exact_current_package() -> None:
    package = resolve_game_package(SOURCE_PACKAGE)

    assert package.game.game_id == "bellweather"
    assert package.package_sha256 == _sha256(SOURCE_PACKAGE / "game.toml")
    assert len(package.files) == sum(1 for path in SOURCE_PACKAGE.rglob("*") if path.is_file())
    assert [entry.map_id for entry in package.maps] == [
        "sunpetal-crossing",
        "crowncrag-road",
    ]
    assert [entry.mob_id for entry in package.mobs.mobs] == package.game.cast.mob_ids
    assert [entry.npc_id for entry in package.npcs.npcs] == package.game.cast.npc_ids
    assert package.scenario_catalog.scenario_ids[0] == "sunpetal_welcome"
    assert re.fullmatch(r"[a-f0-9]{64}", package.closure_sha256)


@pytest.mark.parametrize("wrapped", [True, False])
def test_directory_and_zip_resolve_to_the_same_canonical_identity(
    tmp_path: Path, wrapped: bool
) -> None:
    package = _copy_package(tmp_path)
    archive = tmp_path / "bellweather.zip"
    _write_zip(package, archive, wrapped=wrapped)

    directory = resolve_game_package(package)
    zipped = resolve_game_package(archive)

    assert zipped.source_kind == "zip"
    assert zipped.package_sha256 == directory.package_sha256
    assert zipped.canonical_game_sha256 == directory.canonical_game_sha256
    assert zipped.closure_sha256 == directory.closure_sha256
    assert [entry.identity() for entry in zipped.files] == [
        entry.identity() for entry in directory.files
    ]


def test_validate_repository_selector_resolves_bellweather() -> None:
    report = validate_game_package(REPOSITORY_ROOT)

    assert report["valid"] is True
    assert report["kind"] == "game-package-validation-v4"
    assert report["game_id"] == "bellweather"
    assert report["generated_status"] == "not_checked"
    assert report["file_count"] == sum(1 for path in SOURCE_PACKAGE.rglob("*") if path.is_file())


def test_rejects_the_retired_digest_pinning_selector(tmp_path: Path) -> None:
    """The v3 selector pinned game.toml by digest. Its shape is retired, not tolerated."""

    workspace = tmp_path / "workspace"
    package = workspace / "library" / "games" / "bellweather"
    package.parent.mkdir(parents=True)
    shutil.copytree(SOURCE_PACKAGE, package)
    selector = workspace / "library" / "games" / "main.toml"
    selector.write_text(
        f'''schema_version = 3
kind = "game-package-v3"
game_id = "bellweather"
package_ref = "library/games/bellweather/game.toml"
package_sha256 = "{_sha256(package / "game.toml")}"
''',
        encoding="utf-8",
    )

    with pytest.raises(GamePackageValidationError) as caught:
        validate_game_package(workspace)

    assert caught.value.code == "invalid_selector"


def test_rejects_a_selector_that_reintroduces_the_package_digest(tmp_path: Path) -> None:
    """A current selector carrying the removed field is refused rather than ignored."""

    workspace = tmp_path / "workspace"
    package = workspace / "library" / "games" / "bellweather"
    package.parent.mkdir(parents=True)
    shutil.copytree(SOURCE_PACKAGE, package)
    selector = workspace / "library" / "games" / "main.toml"
    selector.write_text(
        f'''schema_version = 4
kind = "game-package-v4"
game_id = "bellweather"
package_ref = "library/games/bellweather/game.toml"
package_sha256 = "{_sha256(package / "game.toml")}"
''',
        encoding="utf-8",
    )

    with pytest.raises(GamePackageValidationError) as caught:
        validate_game_package(workspace)

    assert caught.value.code == "invalid_selector"
    assert "extra_forbidden" in str(caught.value)


def test_editing_a_member_needs_no_bookkeeping_anywhere_else(tmp_path: Path) -> None:
    """The point of the change: a member edit resolves without touching game.toml or main.toml."""

    workspace = tmp_path / "workspace"
    package = workspace / "library" / "games" / "bellweather"
    package.parent.mkdir(parents=True)
    shutil.copytree(SOURCE_PACKAGE, package)
    shutil.copy2(
        REPOSITORY_ROOT / "library" / "games" / "main.toml",
        workspace / "library" / "games" / "main.toml",
    )
    gameplay = package / "gameplay.toml"
    original = resolve_game_package(package).closure_sha256
    gameplay.write_text(
        gameplay.read_text(encoding="utf-8").replace(
            "starting_health = 10", "starting_health = 11"
        ),
        encoding="utf-8",
    )

    report = validate_game_package(workspace)

    assert report["valid"] is True
    assert report["closure_sha256"] != original


def test_rejects_accepted_media_that_no_longer_matches_its_review(tmp_path: Path) -> None:
    """Evidence digests stay authored: they bind a human verdict to the exact reviewed bytes."""

    package = _copy_package(tmp_path)
    cover = package / "references/cover.png"
    cover.write_bytes(cover.read_bytes() + b"\x00")

    with pytest.raises(GamePackageValidationError) as caught:
        resolve_game_package(package)

    assert caught.value.code == "stale_source_digest"
    assert "references/cover.png" in str(caught.value)


def test_rejects_unresolved_cross_contract_id(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    gameplay = package / "gameplay.toml"
    gameplay.write_text(
        gameplay.read_text(encoding="utf-8").replace(
            'mob_id = "petal_puff"', 'mob_id = "missing_mob"', 1
        ),
        encoding="utf-8",
    )

    with pytest.raises(GamePackageValidationError) as caught:
        resolve_game_package(package)

    assert caught.value.code == "unresolved_cross_reference"
    assert "missing_mob" in str(caught.value)


def test_crouch_gameplay_capability_requires_player_motion_coverage(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    player = package / "content/player.toml"
    crouch = """
[[players.motions]]
state = "crouch"
playback_mode = "loop"
canonical_frame_indices = [0, 1, 2, 3]
frames_per_second = 6
"""
    player.write_text(player.read_text(encoding="utf-8").replace(crouch, ""), encoding="utf-8")

    with pytest.raises(GamePackageValidationError) as caught:
        resolve_game_package(package)

    assert caught.value.code == "unresolved_cross_reference"
    assert "required player motion state" in str(caught.value)
    assert "crouch" in str(caught.value)


def test_rejects_a_placed_rope_without_its_own_player_climb_state(tmp_path: Path) -> None:
    """A rope drawn as a ladder climb is a silent defect, so the package must not resolve."""

    package = _copy_package(tmp_path)
    player = package / "content/player.toml"
    rope = """
[[players.motions]]
state = "climb_rope"
playback_mode = "gameplay_driven"
canonical_frame_indices = [0, 1]
anchor = "top"
"""
    assert rope in player.read_text(encoding="utf-8")
    player.write_text(player.read_text(encoding="utf-8").replace(rope, ""), encoding="utf-8")

    with pytest.raises(GamePackageValidationError) as caught:
        resolve_game_package(package)

    assert caught.value.code == "unresolved_cross_reference"
    assert "required player motion state" in str(caught.value)
    assert "climb_rope" in str(caught.value)


def test_requires_only_the_climb_states_the_maps_declare(tmp_path: Path) -> None:
    """Crowncrag declares both roles, so the package owes both strips and no others.

    Which climb states a player needs follows from the roster a map can DRAW. Placement is
    generated terrain and does not exist at package resolution, so a declared rope variant is
    already reason enough for the player to be able to climb a rope.
    """

    package = resolve_game_package(_copy_package(tmp_path))
    roles = {
        role
        for game_map in package.maps
        if game_map.climbable is not None
        for role, variants in (
            ("ladder", game_map.climbable.ladders),
            ("rope", game_map.climbable.ropes),
        )
        if variants
    }
    assert roles == {"ladder", "rope"}
    states = {motion.state for motion in package.player.players[0].motions}
    assert {"climb_ladder", "climb_rope"} <= states
    assert "climb" not in states


def test_climb_motions_declare_a_grip_anchor_rather_than_a_foot_anchor(tmp_path: Path) -> None:
    """Registration moved out of the recipe, so the authored package is what keeps it correct.

    A climb registered on its feet pins them and swings the head instead, which reads in play as
    bouncing rather than climbing. Nothing in code defaults these to `top` any more.
    """

    package = resolve_game_package(_copy_package(tmp_path))
    anchors = {motion.state: motion.anchor for motion in package.player.players[0].motions}

    assert anchors["climb_ladder"] == "top"
    assert anchors["climb_rope"] == "top"
    assert {state for state, anchor in anchors.items() if anchor != "bottom"} == {
        "climb_ladder",
        "climb_rope",
    }


def test_rejects_orphaned_package_files(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    (package / "unused.toml").write_text("unused = true\n", encoding="utf-8")

    with pytest.raises(GamePackageValidationError) as caught:
        resolve_game_package(package)

    assert caught.value.code == "orphan_package_file"
    assert "unused.toml" in str(caught.value)


def test_rejects_directory_symlinks(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    (package / "references" / "linked.png").symlink_to(package / "references" / "cover.png")

    with pytest.raises(GamePackageValidationError) as caught:
        resolve_game_package(package)

    assert caught.value.code == "symlink_escape"


def test_rejects_a_symlinked_directory_root(tmp_path: Path) -> None:
    actual_parent = tmp_path / "actual"
    actual_parent.mkdir()
    package = _copy_package(actual_parent)
    linked = tmp_path / "linked-package"
    linked.symlink_to(package, target_is_directory=True)

    with pytest.raises(GamePackageValidationError) as caught:
        resolve_game_package(linked)

    assert caught.value.code == "invalid_package_root"


def test_rejects_a_symlinked_zip_input(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    archive = tmp_path / "bellweather.zip"
    _write_zip(package, archive)
    linked = tmp_path / "linked.zip"
    linked.symlink_to(archive)

    with pytest.raises(GamePackageValidationError) as caught:
        resolve_game_package(linked)

    assert caught.value.code == "invalid_package_zip"


def test_rejects_a_zip_symlink_entry(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    archive = tmp_path / "bellweather.zip"
    _write_zip(package, archive)
    symlink = zipfile.ZipInfo("bellweather/linked-reference.png")
    symlink.create_system = 3
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "a") as output:
        output.writestr(symlink, "references/cover.png")

    with pytest.raises(GamePackageValidationError) as caught:
        resolve_game_package(archive)

    assert caught.value.code == "symlink_escape"


def test_rejects_zip_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "bellweather.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("bellweather/game.toml", "schema_version = 5\n")
        output.writestr("../outside.txt", "escape")

    with pytest.raises(GamePackageValidationError) as caught:
        resolve_game_package(archive)

    assert caught.value.code == "invalid_package"
    assert "parent segments" in str(caught.value)


def test_invalid_report_is_machine_readable(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    (package / "game.toml").unlink()

    with pytest.raises(GamePackageValidationError) as caught:
        resolve_game_package(package)

    report = invalid_game_package_report(caught.value)
    assert report["valid"] is False
    assert report["source_status"] == "invalid"
    assert report["errors"] == [
        {"code": "missing_package_file", "message": "prepared package is missing game.toml"}
    ]


def test_repository_gate_failure_keeps_source_truth_separate() -> None:
    report = invalid_game_package_report(
        GamePackageValidationError(
            "uncommitted_game_package", "package closure differs from Git HEAD"
        )
    )

    assert report["source_status"] == "current"
    assert report["disposition"] == "commit_before_publish"


def _rearm_as_ranged(package: Path, *, projectile_id: str, equipment: str) -> None:
    gameplay = package / "gameplay.toml"
    gameplay.write_text(
        gameplay.read_text(encoding="utf-8").replace(
            'critical_profile = "standard_v1"\n',
            'critical_profile = "standard_v1"\n'
            'weapon_class = "ranged_dps_v1"\n'
            f'projectile_id = "{projectile_id}"\n',
            1,
        ),
        encoding="utf-8",
    )
    player = package / "content/player.toml"
    player.write_text(
        player.read_text(encoding="utf-8").replace(
            'equipment = "hand_weapon_v1"', f'equipment = "{equipment}"', 1
        ),
        encoding="utf-8",
    )


def test_rejects_a_projectile_the_catalog_does_not_ship(tmp_path: Path) -> None:
    """A class that throws must throw something the package actually drew.

    The same closure question `currency_item_id` and `starting_item_ids` are already asked. Left to
    the runtime it would be a package that validates clean, ships, and then declines to fire.
    """

    package = _copy_package(tmp_path)
    # The shipped package swings, so the throwing pairing is composed here rather than assumed.
    # It also has to move the player's declared equipment: a hand weapon cannot fight ranged, and
    # that check would otherwise fire first and mask the one under test.
    _rearm_as_ranged(package, projectile_id="missing_throwable", equipment="thrown_kit_v1")

    with pytest.raises(GamePackageValidationError) as caught:
        resolve_game_package(package)

    assert caught.value.code == "unresolved_cross_reference"
    assert "projectile_id" in str(caught.value)


def test_rejects_a_character_drawn_with_a_weapon_their_kit_cannot_use(tmp_path: Path) -> None:
    """The drawn character and the kit they fight with are one fact authored in two files.

    Until this check existed a package could ship a figure carrying a sword and a combat policy
    that throws darts, and nothing objected: the equipment lived in free prose that no validator
    reads. Both halves are closed names now, so the contradiction is refusable without reading a
    word of the authored description.
    """

    package = _copy_package(tmp_path)
    # A throwing kit, but the character is still drawn carrying the sword.
    _rearm_as_ranged(package, projectile_id="paperwing_dart", equipment="hand_weapon_v1")

    with pytest.raises(GamePackageValidationError) as caught:
        resolve_game_package(package)

    assert caught.value.code == "player_equipment_mismatch"
    assert "hand_weapon_v1" in str(caught.value)
    assert "ranged_dps_v1" in str(caught.value)


def test_a_package_that_disables_combat_may_draw_whatever_it_likes(tmp_path: Path) -> None:
    """The scope of the check, asserted so it is not later read as an oversight.

    `weapon_class` defaults to `melee_dps_v1`, so an unconditional pairing check would force every
    story package with no fighting in it to draw a hand weapon or nothing at all. The equipment
    pairing is scoped to combat for the same reason the required attack poses are.
    """

    package = _copy_package(tmp_path)
    gameplay = package / "gameplay.toml"
    gameplay.write_text(
        gameplay.read_text(encoding="utf-8").replace(
            "[combat]\nenabled = true", "[combat]\nenabled = false", 1
        ),
        encoding="utf-8",
    )
    player = package / "content/player.toml"
    player.write_text(
        player.read_text(encoding="utf-8").replace(
            'equipment = "hand_weapon_v1"', 'equipment = "focus_implement_v1"', 1
        ),
        encoding="utf-8",
    )

    resolved = resolve_game_package(package)

    assert resolved.gameplay.combat.enabled is False
    assert resolved.player.players[0].equipment == "focus_implement_v1"


def test_accepts_a_character_whose_drawn_kit_matches_how_they_fight(tmp_path: Path) -> None:
    # The other direction, so the check above is not passing for want of any valid ranged package.
    package = _copy_package(tmp_path)
    _rearm_as_ranged(package, projectile_id="paperwing_dart", equipment="thrown_kit_v1")

    resolved = resolve_game_package(package)

    assert resolved.gameplay.combat.weapon_class == "ranged_dps_v1"
    assert resolved.player.players[0].equipment == "thrown_kit_v1"


def test_a_swinging_package_names_no_projectile_and_still_resolves() -> None:
    # The shipped package is exactly this case, so it is asserted in place rather than composed:
    # a melee character who names no round, with a projectile catalog still in the package.
    resolved = resolve_game_package(SOURCE_PACKAGE)

    assert resolved.gameplay.combat.weapon_class == "melee_dps_v1"
    assert resolved.gameplay.combat.projectile_id is None
    assert resolved.player.players[0].equipment == "hand_weapon_v1"
