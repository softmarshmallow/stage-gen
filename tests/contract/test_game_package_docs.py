from __future__ import annotations

import tomllib
from pathlib import Path

from bellweather_pipeline.gameplay import GAMEPLAY_CONTRACT_SCHEMA_VERSION
from bellweather_pipeline.maps import PREPARED_GAME_MAP_SCHEMA_VERSION
from demo_game_tools.input_formats.game_contract import PREPARED_GAME_CONTRACT_SCHEMA_VERSION
from demo_game_tools.input_formats.sideview_content import (
    GAME_CONTENT_SCHEMA_VERSION,
    NPC_CONTENT_SCHEMA_VERSION,
    PLAYER_CONTENT_SCHEMA_VERSION,
)
from demo_game_tools.media.soundtrack import GAME_SOUNDTRACK_SCHEMA_VERSION
from demo_game_tools.media.ui import GAME_UI_SCHEMA_VERSION
from iron_petal_unit_pipeline.audio import RUNNER_AUDIO_SCHEMA_VERSION
from stage_gen.components.scenario import (
    SCENARIO_CATALOG_SCHEMA_VERSION,
    SCENARIO_SCHEMA_VERSION,
)


def test_game_input_document_matches_current_prepared_contracts() -> None:
    repository = Path(__file__).parents[2]
    document = (repository / "godot/games/_shared/docs/game-package.md").read_text(encoding="utf-8")
    for game, input_root, game_id in (
        ("bellweather", "godot/games/bellweather/inputs/default", "bellweather"),
        ("iron_petal_unit", "godot/games/iron_petal_unit/inputs", "iron-petal-unit"),
    ):
        package = tomllib.loads((repository / input_root / "game.toml").read_text(encoding="utf-8"))
        assert package["game_id"] == game_id
        assert package["kind"] == f"game-contract-v{PREPARED_GAME_CONTRACT_SCHEMA_VERSION}"
        assert input_root in document
        assert (repository / "godot/games" / game / "pipeline/prepare.py").is_file()
    assert "explicit collection CLI `--input`" in document
    assert "scripts separately default to planning and require `--live`" in document
    assert (
        "godot/tools/validate_game_package.py --root . "
        "--input godot/games/iron_petal_unit/inputs --require-committed"
    ) in document

    assert '`generated_status = "not_checked"`' in document

    for current_contract in (
        f"game-contract-v{PREPARED_GAME_CONTRACT_SCHEMA_VERSION}",
        f"gameplay-contract-v{GAMEPLAY_CONTRACT_SCHEMA_VERSION}",
        f"game-map-v{PREPARED_GAME_MAP_SCHEMA_VERSION}",
        f"game-soundtrack-v{GAME_SOUNDTRACK_SCHEMA_VERSION}",
        f"runner-audio-v{RUNNER_AUDIO_SCHEMA_VERSION}",
        f"game-ui-v{GAME_UI_SCHEMA_VERSION}",
        f"player-content-v{PLAYER_CONTENT_SCHEMA_VERSION}",
        f"mob-content-v{GAME_CONTENT_SCHEMA_VERSION}",
        f"npc-content-v{NPC_CONTENT_SCHEMA_VERSION}",
        f"prop-content-v{GAME_CONTENT_SCHEMA_VERSION}",
        f"item-content-v{GAME_CONTENT_SCHEMA_VERSION}",
        f"scenario-catalog-v{SCENARIO_CATALOG_SCHEMA_VERSION}",
        f"scenario-v{SCENARIO_SCHEMA_VERSION}",
    ):
        assert f"`{current_contract}`" in document

    for removed_input in (
        "map book",
        "WorldSpec",
        "VillageSpec",
    ):
        assert removed_input in document
