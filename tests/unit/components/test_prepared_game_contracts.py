from __future__ import annotations

from pathlib import Path

import pytest

from stage_gen.components._game_input import AuthoredContractLoadError
from stage_gen.components.game_contract import load_prepared_game_contract_bytes
from stage_gen.components.game_ui import load_game_ui_bytes
from stage_gen.components.platformer_content import (
    load_mob_content_bytes,
    load_npc_content_bytes,
    load_player_content_bytes,
    load_projectile_content_bytes,
)
from stage_gen.components.platformer_gameplay import load_gameplay_contract_bytes
from stage_gen.components.platformer_map import load_prepared_game_map_bytes
from stage_gen.components.scenario import (
    load_scenario_catalog_bytes,
    resolve_scenario_bytes,
)

PACKAGE = Path(__file__).resolve().parents[3] / "library" / "games" / "bellweather"


def _bytes(relative: str) -> bytes:
    return (PACKAGE / relative).read_bytes()


def test_each_prepared_contract_module_loads_the_canonical_source() -> None:
    game = load_prepared_game_contract_bytes(_bytes("game.toml"))
    gameplay = load_gameplay_contract_bytes(_bytes("gameplay.toml"))
    ui = load_game_ui_bytes(_bytes("ui.toml"))
    game_map = load_prepared_game_map_bytes(_bytes("maps/sunpetal-crossing.toml"))
    player = load_player_content_bytes(_bytes("content/player.toml"))
    mobs = load_mob_content_bytes(_bytes("content/mobs.toml"))
    npcs = load_npc_content_bytes(_bytes("content/npcs.toml"))
    catalog = load_scenario_catalog_bytes(_bytes("scenarios/index.toml"))

    assert game.game_id == gameplay.game_id == game_map.game_id == "bellweather"
    assert ui.game_id == game.game_id
    platformer = game.platformer_member()
    assert platformer is not None
    assert player.players[0].player_id == platformer.cast.player_id
    assert "crouch" in gameplay.navigation.allowed_movements
    crouch = next(motion for motion in player.players[0].motions if motion.state == "crouch")
    assert crouch.playback_mode == "loop"
    assert crouch.canonical_frame_indices == [0, 1, 2, 3]
    assert crouch.frames_per_second == 6
    assert [entry.mob_id for entry in mobs.mobs] == platformer.cast.mob_ids
    assert npcs.world_orientation == "front"
    assert [entry.npc_id for entry in npcs.npcs] == platformer.cast.npc_ids
    assert all(entry.motions[0].playback_mode == "hold" for entry in npcs.npcs)
    assert all(entry.motions[0].canonical_frame_indices == [0] for entry in npcs.npcs)
    assert catalog.scenario_ids == (
        "sunpetal_welcome",
        "elowen_skybell_memory",
        "brom_mended_things",
        "pip_lantern_road",
    )


def test_prepared_root_rejects_unknown_fields() -> None:
    source = _bytes("game.toml") + b"\nunknown_root = true\n"

    with pytest.raises(AuthoredContractLoadError, match="extra_forbidden"):
        load_prepared_game_contract_bytes(source)


def test_prepared_root_rejects_the_retired_digest_pinning_identity() -> None:
    source = _bytes("game.toml").replace(
        b'schema_version = 8\nkind = "game-contract-v8"',
        b'schema_version = 7\nkind = "game-contract-v7"',
        1,
    )

    with pytest.raises(AuthoredContractLoadError, match="literal_error"):
        load_prepared_game_contract_bytes(source)


def test_prepared_root_rejects_a_reintroduced_member_digest() -> None:
    """Member digests are computed at ingest. An authored one is refused, not ignored."""

    source = _bytes("game.toml").replace(
        b'[universe]\nsource = "universe.md"\n',
        b'[universe]\nsource = "universe.md"\nsource_sha256 = "' + b"0" * 64 + b'"\n',
        1,
    )

    with pytest.raises(AuthoredContractLoadError, match="extra_forbidden"):
        load_prepared_game_contract_bytes(source)


def test_scenario_catalog_rejects_a_retired_identity() -> None:
    source = _bytes("scenarios/index.toml").replace(
        b'kind = "scenario-catalog-v1"',
        b'kind = "game-sequence-catalog-v2"',
        1,
    )

    with pytest.raises(AuthoredContractLoadError, match="literal_error"):
        load_scenario_catalog_bytes(source)


def test_scenario_catalog_rejects_a_reintroduced_source_digest() -> None:
    source = _bytes("scenarios/index.toml").replace(
        b'scenario_id = "sunpetal_welcome"\n',
        b'scenario_id = "sunpetal_welcome"\nsource_sha256 = "' + b"0" * 64 + b'"\n',
        1,
    )

    with pytest.raises(AuthoredContractLoadError, match="extra_forbidden"):
        load_scenario_catalog_bytes(source)


def test_map_contract_rejects_a_second_opaque_layer() -> None:
    # A well-formed second base: opaque alpha paired with the canvas_cover anchor, so the
    # per-layer placement rule passes and the map-level uniqueness rule is what rejects it.
    source = _bytes("maps/sunpetal-crossing.toml").replace(
        b'alpha_mode = "transparent"\nvertical_anchor = "screen_top"',
        b'alpha_mode = "opaque"\nvertical_anchor = "canvas_cover"',
        1,
    )

    with pytest.raises(AuthoredContractLoadError, match="exactly one opaque"):
        load_prepared_game_map_bytes(source)


def test_map_contract_rejects_an_opaque_layer_without_the_canvas_cover_anchor() -> None:
    source = _bytes("maps/sunpetal-crossing.toml").replace(
        b'alpha_mode = "transparent"\nvertical_anchor = "screen_top"',
        b'alpha_mode = "opaque"\nvertical_anchor = "screen_top"',
        1,
    )

    with pytest.raises(AuthoredContractLoadError, match="canvas_cover vertical anchor"):
        load_prepared_game_map_bytes(source)


def test_player_contract_rejects_obsolete_authored_facing_coverage() -> None:
    source = _bytes("content/player.toml") + b'\nrequired_facings = ["left", "right"]\n'

    with pytest.raises(AuthoredContractLoadError, match="extra_forbidden"):
        load_player_content_bytes(source)


def test_player_contract_rejects_crawl_as_an_ambiguous_motion_state() -> None:
    source = _bytes("content/player.toml").replace(b'state = "crouch"', b'state = "crawl"')

    with pytest.raises(AuthoredContractLoadError, match="unsupported motion states: crawl"):
        load_player_content_bytes(source)


def test_content_catalog_rejects_unknown_reference_ids() -> None:
    source = _bytes("content/mobs.toml").replace(
        b'reference_ids = ["cover_style"]', b'reference_ids = ["missing_reference"]', 1
    )

    with pytest.raises(AuthoredContractLoadError, match="unknown IDs"):
        load_mob_content_bytes(source)


def test_npc_contract_rejects_the_obsolete_world_motions_field() -> None:
    source = _bytes("content/npcs.toml").replace(b"[[npcs.motions]]", b"[[npcs.world_motions]]")

    with pytest.raises(AuthoredContractLoadError, match="extra_forbidden"):
        load_npc_content_bytes(source)


def test_a_scenario_whose_script_drifted_from_its_digest_is_refused() -> None:
    """The catalog names the halves; the declarations sign for the prose."""

    with pytest.raises(ValueError, match="does not match its authored digest"):
        resolve_scenario_bytes(
            _bytes("scenarios/sunpetal_welcome.toml"),
            _bytes("scenarios/sunpetal_welcome.scenario") + b'\n"Extra."\n',
            scenario_id="sunpetal_welcome",
        )


def test_a_scenario_whose_declared_id_is_not_its_path_is_refused() -> None:
    with pytest.raises(ValueError, match="which its own path does not name"):
        resolve_scenario_bytes(
            _bytes("scenarios/sunpetal_welcome.toml"),
            _bytes("scenarios/sunpetal_welcome.scenario"),
            scenario_id="elowen_skybell_memory",
        )


def _as_ranged(source: bytes) -> bytes:
    """The shipped package as it would read if the wayfarer threw.

    Bellweather ships melee, because it ships a character drawn carrying a sword. These tests are
    about the taxonomy rather than about that choice, so they compose the pairing they need instead
    of assuming the library package happens to be authored with it - which is what pinned them to
    one game's art direction and broke them when it changed.
    """

    return source.replace(
        b'critical_profile = "standard_v1"\n',
        b'critical_profile = "standard_v1"\n'
        b'weapon_class = "ranged_dps_v1"\n'
        b'projectile_id = "paperwing_dart"\n',
        1,
    )


def test_combat_names_a_weapon_class_and_the_object_it_throws() -> None:
    gameplay = load_gameplay_contract_bytes(_as_ranged(_bytes("gameplay.toml")))

    assert gameplay.combat.weapon_class == "ranged_dps_v1"
    assert gameplay.combat.projectile_id == "paperwing_dart"
    # The class names a pose that the character content already draws, which is the whole reason
    # a throwing package costs no extra generation.
    player = load_player_content_bytes(_bytes("content/player.toml"))
    assert gameplay.combat.secondary_action in {
        motion.state for motion in player.players[0].motions
    }


def test_a_package_that_never_names_the_weapon_class_parses_as_melee() -> None:
    # The field arrived after packages had already shipped, and the shipped package is one that
    # omits it. A contract that never names it means the class every one of those was played with,
    # not an invalid contract.
    gameplay = load_gameplay_contract_bytes(_bytes("gameplay.toml"))

    assert gameplay.combat.weapon_class == "melee_dps_v1"
    assert gameplay.combat.projectile_id is None


def test_combat_rejects_a_weapon_class_outside_the_taxonomy() -> None:
    source = _as_ranged(_bytes("gameplay.toml")).replace(
        b'weapon_class = "ranged_dps_v1"', b'weapon_class = "hitscan_dps_v1"'
    )

    with pytest.raises(AuthoredContractLoadError, match="literal_error"):
        load_gameplay_contract_bytes(source)


def test_a_throwing_class_must_name_what_it_throws() -> None:
    source = _as_ranged(_bytes("gameplay.toml")).replace(b'projectile_id = "paperwing_dart"\n', b"")

    with pytest.raises(AuthoredContractLoadError, match="ranged_dps_v1 requires projectile_id"):
        load_gameplay_contract_bytes(source)


def test_a_swinging_class_must_not_name_a_projectile() -> None:
    # A melee package naming one describes artwork nothing will ever put in the air, which is a
    # contradiction worth catching at authoring time rather than a harmless unused field.
    source = _as_ranged(_bytes("gameplay.toml")).replace(
        b'weapon_class = "ranged_dps_v1"', b'weapon_class = "melee_dps_v1"'
    )

    with pytest.raises(
        AuthoredContractLoadError, match="projectile_id requires a throwing weapon_class"
    ):
        load_gameplay_contract_bytes(source)


def test_the_projectile_catalog_declares_what_is_drawn_and_how_it_behaves() -> None:
    catalog = load_projectile_content_bytes(_bytes("content/projectiles.toml"))

    entry = catalog.projectiles[0]
    assert entry.projectile_id == "paperwing_dart"
    assert entry.silhouette == "axial_v1"
    assert entry.flight == "flat_bolt_v1"
    assert entry.impact == "single_target_v1"
    # Length, not height: the subject is drawn lying along its own travel axis.
    assert entry.length_units == 0.50


def test_a_projectile_outside_a_facet_vocabulary_is_refused() -> None:
    for field, bad in (
        (b'silhouette = "axial_v1"', b'silhouette = "spiral_v1"'),
        (b'flight = "flat_bolt_v1"', b'flight = "homing_v1"'),
        (b'impact = "single_target_v1"', b'impact = "chain_v1"'),
    ):
        source = _bytes("content/projectiles.toml").replace(field, bad)
        with pytest.raises(AuthoredContractLoadError, match="literal_error"):
            load_projectile_content_bytes(source)


def test_the_projectile_catalog_rejects_a_height_it_cannot_mean() -> None:
    # `height_units` is what every standing family declares; a projectile declares a length, and
    # accepting both names for one measurement is the defect the unit contract exists to prevent.
    source = _bytes("content/projectiles.toml").replace(
        b"length_units = 0.50", b"height_units = 0.50"
    )

    with pytest.raises(AuthoredContractLoadError, match="extra_forbidden"):
        load_projectile_content_bytes(source)


def test_the_package_root_declares_the_projectile_catalog_it_ships() -> None:
    game = load_prepared_game_contract_bytes(_bytes("game.toml"))

    platformer = game.platformer_member()
    assert platformer is not None
    assert platformer.content.projectiles is not None
    assert platformer.content.projectiles.source == "content/projectiles.toml"


def test_a_package_that_fires_nothing_declares_no_projectile_catalog() -> None:
    # The one optional content family. Every other catalog describes something a playable package
    # must have; a projectile is owed only by a game whose weapons throw one.
    source = _bytes("game.toml").replace(
        b'[genres.content.projectiles]\nsource = "content/projectiles.toml"\n\n', b""
    )

    game = load_prepared_game_contract_bytes(source)
    platformer = game.platformer_member()
    assert platformer is not None and platformer.content.projectiles is None
