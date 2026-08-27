from __future__ import annotations

import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[2]

CURRENT_GAME_DOC_PATHS = (
    "docs/game-contract.md",
    "docs/game-package.md",
    "docs/game-maps.md",
    "docs/game-soundtrack.md",
    "docs/dialogue-character-runtime-pipeline.md",
    "docs/spec/game/authored-contract-schema.md",
    "docs/spec/game/map-generation-contract.md",
    "docs/spec/game/generation-pipeline.md",
    "docs/spec/game/ui.md",
    "docs/spec/scene-gameplay-components.md",
    "docs/spec/game/dialogue-and-cutscene-sequences.md",
)

RETIRED_PREPARED_IDENTITIES = (
    "game-contract-v1",
    "game-contract-v2",
    "game-contract-v3",
    "game-contract-v4",
    "game-map-v1",
    "game-map-v2",
    "game-map-v3",
    "prepared-game-runtime-v1",
    "prepared-game-runtime-v2",
    "prepared-game-runtime-v3",
    "game-map-book-v1",
    "game-map-book-manifest-v2",
    "manifest V7",
)

FORBIDDEN_OLD_VERSION_SUPPORT = (
    r"\bresolved-game-map-book-v1\b",
    r"\bgame-soundtrack-manifest-v1\b",
    r"\bV[2-6]\s*(?:-|through|or)\s*V?[2-7]\b",
    r"\b(?:legacy|older|historical)\s+(?:contract|manifest|map|projection|schema|shape|text)",
    r"\b(?:compatibility behavior|compatibility identifier|compatibility projection)\b",
    r"\bcompatible linear sequence\b",
    r"\bremains compatible\b",
    r"\bsupported versions\b",
    r"\bversion 1 compatibility\b",
)


def _read(relative_path: str) -> str:
    return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")


def test_game_docs_describe_the_exact_current_prepared_closure() -> None:
    documents = {path: _read(path) for path in CURRENT_GAME_DOC_PATHS}

    for path, document in documents.items():
        for identity in RETIRED_PREPARED_IDENTITIES:
            assert identity not in document, f"{path} advertises retired identity {identity}"
        for pattern in FORBIDDEN_OLD_VERSION_SUPPORT:
            assert re.search(pattern, document, flags=re.IGNORECASE) is None, (
                f"{path} advertises old-version support matching {pattern!r}"
            )

    game_contract = documents["docs/game-contract.md"]
    for identity in (
        "`game-package-v3`",
        "`game-contract-v5`",
        "`gameplay-contract-v1`",
        "`game-ui-v1`",
        "`game-map-v5`",
        "`prepared-game-runtime-v7`",
    ):
        assert identity in game_contract
    assert "ladder geometry and placement" in game_contract
    assert "portal presentation" in game_contract
    assert "endpoint anchors" in game_contract

    package = documents["docs/game-package.md"]
    assert "`game.toml` is the membership and digest-closure root" in package
    assert "Player `climb` is the sole current gameplay-driven state" in package
    assert "gameplay movement `crouch` and player motion `crouch`" in package

    maps = documents["docs/game-maps.md"]
    for identity in (
        "`game-map-v5`",
        "`ladder-4-tile-v1`",
        "`portal-pair-1x2-v1`",
        "`prepared-game-runtime-v7`",
    ):
        assert identity in maps
    assert "packaged 47-mask" in maps
    assert "is no map index" in maps

    schema = documents["docs/spec/game/authored-contract-schema.md"]
    assert 'Only `schema_version = 5` and `kind = "game-contract-v5"` are accepted' in schema
    assert 'source = "ui.toml"' in schema
    assert "gameplay.toml` owns climb permission and portal destinations" in schema

    map_contract = documents["docs/spec/game/map-generation-contract.md"]
    assert "exact-current authored, generation, manifest, and consumer contract" in map_contract
    assert "binary terrain occupancy" in map_contract
    assert "`ladder-4-tile-v1`" in map_contract
    assert 'mode = "portal-pair-1x2-v1"' in map_contract

    pipeline = documents["docs/spec/game/generation-pipeline.md"]
    assert "deterministically assemble 47-mask atlas" in pipeline
    assert "Player `crouch` is the current explicit vocabulary boundary" in pipeline
    assert "Optional map-local ladder and portal branches" in pipeline

    ui = documents["docs/spec/game/ui.md"]
    assert "exact current identity is `game-ui-v1`" in ui
    assert "every slot interior" in ui

    soundtrack = documents["docs/game-soundtrack.md"]
    assert "exact identity is\n`game-soundtrack-v1`" in soundtrack
    assert "Provider-free integration" in soundtrack
    assert "`prepared-game-runtime-v7`" in soundtrack

    dialogue = documents["docs/dialogue-character-runtime-pipeline.md"]
    assert "NPC visual identity in `content/npcs.toml`" in dialogue
    assert "dialogue\ncontrol flow in `sequences/*.toml`" in dialogue
    assert "`prepared-game-runtime-v7`" in dialogue

    gameplay = documents["docs/spec/scene-gameplay-components.md"]
    assert "`gameplay-contract-v1`" in gameplay
    assert "binary\noccupancy and 47-mask atlas" in gameplay
    assert "Portal art and endpoint" in gameplay

    sequences = documents["docs/spec/game/dialogue-and-cutscene-sequences.md"]
    assert "current prepared gameplay consumer" in sequences
    assert "`prepared-game-runtime-v7`" in sequences
