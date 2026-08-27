from __future__ import annotations

from pathlib import Path

import pytest

from stage_gen.components._game_input import AuthoredContractLoadError
from stage_gen.components.game_content import (
    load_mob_content_bytes,
    load_player_content_bytes,
)
from stage_gen.components.game_contract import load_prepared_game_contract_bytes
from stage_gen.components.game_map import load_prepared_game_map_bytes
from stage_gen.components.game_sequence import load_game_sequence_bytes
from stage_gen.components.game_ui import load_game_ui_bytes
from stage_gen.components.gameplay_contract import load_gameplay_contract_bytes

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
    sequence = load_game_sequence_bytes(_bytes("sequences/sunpetal-welcome.toml"))

    assert game.game_id == gameplay.game_id == game_map.game_id == "bellweather"
    assert ui.game_id == game.game_id
    assert player.players[0].player_id == game.cast.player_id
    assert "crouch" in gameplay.navigation.allowed_movements
    crouch = next(motion for motion in player.players[0].motions if motion.state == "crouch")
    assert crouch.playback_mode == "loop"
    assert crouch.canonical_frame_indices == [0, 1, 2, 3]
    assert crouch.frames_per_second == 6
    assert [entry.mob_id for entry in mobs.mobs] == game.cast.mob_ids
    assert sequence.entry_node_id == "mara_greeting"


def test_prepared_root_rejects_unknown_fields() -> None:
    source = _bytes("game.toml") + b"\nunknown_root = true\n"

    with pytest.raises(AuthoredContractLoadError, match="extra_forbidden"):
        load_prepared_game_contract_bytes(source)


def test_map_contract_rejects_a_second_opaque_layer() -> None:
    source = _bytes("maps/sunpetal-crossing.toml").replace(
        b'alpha_mode = "transparent"', b'alpha_mode = "opaque"', 1
    )

    with pytest.raises(AuthoredContractLoadError, match="exactly one opaque"):
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


def test_sequence_contract_rejects_an_unresolved_node() -> None:
    source = _bytes("sequences/sunpetal-welcome.toml").replace(
        b'next_node_id = "wayfarer_question"', b'next_node_id = "missing_node"', 1
    )

    with pytest.raises(AuthoredContractLoadError, match="unknown node_id"):
        load_game_sequence_bytes(source)
