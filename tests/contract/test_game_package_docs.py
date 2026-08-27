from __future__ import annotations

import tomllib
from pathlib import Path

from stage_gen.components.game_content import GAME_CONTENT_SCHEMA_VERSION
from stage_gen.components.game_contract import PREPARED_GAME_CONTRACT_SCHEMA_VERSION
from stage_gen.components.game_map import PREPARED_GAME_MAP_SCHEMA_VERSION
from stage_gen.components.game_sequence import GAME_SEQUENCE_SCHEMA_VERSION
from stage_gen.components.game_soundtrack import GAME_SOUNDTRACK_SCHEMA_VERSION
from stage_gen.components.game_ui import GAME_UI_SCHEMA_VERSION
from stage_gen.components.gameplay_contract import GAMEPLAY_CONTRACT_SCHEMA_VERSION
from stage_gen.orchestration.game_package import GAME_PACKAGE_SELECTOR_SCHEMA_VERSION


def test_canonical_game_package_document_matches_current_prepared_contracts() -> None:
    repository = Path(__file__).parents[2]
    document = (repository / "docs/game-package.md").read_text(encoding="utf-8")
    selector = tomllib.loads((repository / "library/games/main.toml").read_text(encoding="utf-8"))

    assert selector == {
        "schema_version": GAME_PACKAGE_SELECTOR_SCHEMA_VERSION,
        "kind": "game-package-v3",
        "game_id": "bellweather",
        "package_ref": "library/games/bellweather/game.toml",
        "package_sha256": selector["package_sha256"],
    }
    assert selector["package_ref"] in document
    assert "library/games/main.toml" in document
    assert "scripts/validate_game_package.py --root . --require-committed" in document
    assert '`generated_status = "not_checked"`' in document

    for current_contract in (
        f"game-contract-v{PREPARED_GAME_CONTRACT_SCHEMA_VERSION}",
        f"gameplay-contract-v{GAMEPLAY_CONTRACT_SCHEMA_VERSION}",
        f"game-map-v{PREPARED_GAME_MAP_SCHEMA_VERSION}",
        f"game-soundtrack-v{GAME_SOUNDTRACK_SCHEMA_VERSION}",
        f"game-ui-v{GAME_UI_SCHEMA_VERSION}",
        f"player-content-v{GAME_CONTENT_SCHEMA_VERSION}",
        f"mob-content-v{GAME_CONTENT_SCHEMA_VERSION}",
        f"npc-content-v{GAME_CONTENT_SCHEMA_VERSION}",
        f"prop-content-v{GAME_CONTENT_SCHEMA_VERSION}",
        f"item-content-v{GAME_CONTENT_SCHEMA_VERSION}",
        f"game-sequence-catalog-v{GAME_SEQUENCE_SCHEMA_VERSION}",
        f"game-sequence-v{GAME_SEQUENCE_SCHEMA_VERSION}",
    ):
        assert f"`{current_contract}`" in document

    for removed_input in (
        "examples request wrapper",
        "map-book index",
        "WorldSpec",
        "VillageSpec",
    ):
        assert removed_input in document
