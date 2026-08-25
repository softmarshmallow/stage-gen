from __future__ import annotations

import tomllib
from pathlib import Path

from stage_gen.components.game_contract import GAME_CONTRACT_SCHEMA_VERSION
from stage_gen.components.game_map import GAME_MAP_BOOK_SCHEMA_VERSION, GAME_MAP_SCHEMA_VERSION
from stage_gen.components.game_soundtrack import GAME_SOUNDTRACK_SCHEMA_VERSION
from stage_gen.orchestration.game_package import GAME_PACKAGE_SELECTOR_SCHEMA_VERSION


def test_canonical_game_package_document_matches_current_contracts() -> None:
    repository = Path(__file__).parents[2]
    document = (repository / "docs/game-package.md").read_text(encoding="utf-8")
    selector = tomllib.loads((repository / "library/games/main.toml").read_text(encoding="utf-8"))

    assert selector["schema_version"] == GAME_PACKAGE_SELECTOR_SCHEMA_VERSION
    assert selector["kind"] == "game-package-v1"
    assert selector["request_ref"] in document
    assert "library/games/main.toml" in document
    assert "scripts/validate_game_package.py --root . --require-committed" in document
    assert '`generated_status = "not_checked"`' in document

    for current_contract in (
        f"game-contract-v{GAME_CONTRACT_SCHEMA_VERSION}",
        f"game-soundtrack-v{GAME_SOUNDTRACK_SCHEMA_VERSION}",
        f"game-map-book-v{GAME_MAP_BOOK_SCHEMA_VERSION}",
        f"game-map-v{GAME_MAP_SCHEMA_VERSION}",
    ):
        assert f"`{current_contract}`" in document

    for retired_claim in (
        "game-contract-v1",
        "game-contract-v2",
        "game-map-v1",
        "scrolling manifest V2",
        "scrolling manifest V3",
        "legacy behavior",
    ):
        assert retired_claim not in document
