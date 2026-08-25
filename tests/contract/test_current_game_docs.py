from __future__ import annotations

import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[2]

GAME_DOC_PATHS = (
    "docs/game-contract.md",
    "docs/game-maps.md",
    "docs/game-soundtrack.md",
    "docs/dialogue-character-runtime-pipeline.md",
    "docs/spec/game/authored-contract-schema.md",
    "docs/spec/scene-gameplay-components.md",
    "docs/spec/game/dialogue-and-cutscene-sequences.md",
)

FORBIDDEN_OLD_VERSION_SUPPORT = (
    r"\bgame-contract-v1\b",
    r"\bgame-contract-v2\b",
    r"\bgame-map-v1\b",
    r"\bresolved-game-map-book-v1\b",
    r"\bgame-map-book-manifest-v1\b",
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


def test_game_docs_describe_only_the_current_contract_closure() -> None:
    documents = {path: _read(path) for path in GAME_DOC_PATHS}

    for path, document in documents.items():
        for pattern in FORBIDDEN_OLD_VERSION_SUPPORT:
            assert re.search(pattern, document, flags=re.IGNORECASE) is None, (
                f"{path} advertises old-version support matching {pattern!r}"
            )

    game_contract = documents["docs/game-contract.md"]
    assert "current closure is `game-contract-v3`, `game-soundtrack-v1`" in game_contract
    assert "`game-map-book-v1` containing only `game-map-v2` sources" in game_contract
    assert "manifest V7 with soundtrack and map-book projection V2" in game_contract

    maps = documents["docs/game-maps.md"]
    for identifier in (
        "`game-map-book-v1`",
        "`game-map-v2`",
        "`resolved-game-map-book-v2`",
        "`game-map-book-manifest-v2`",
    ):
        assert identifier in maps
    assert "When `map_book` is omitted, manifest V7 omits" in maps

    soundtrack = documents["docs/game-soundtrack.md"]
    assert "`game-soundtrack-v1`" in soundtrack
    assert "`game-soundtrack-manifest-v2` inside\nscrolling manifest V7" in soundtrack
    assert "When `soundtrack` is omitted" in soundtrack

    dialogue = documents["docs/dialogue-character-runtime-pipeline.md"]
    assert "scrolling run manifest V7" in dialogue
    assert "When `dialogue_characters` is absent" in dialogue

    schema = documents["docs/spec/game/authored-contract-schema.md"]
    assert "Only `game-contract-v3` is accepted" in schema
    assert "publishes only scrolling manifest V7" in schema

    gameplay = documents["docs/spec/scene-gameplay-components.md"]
    assert "Only `game-contract-v3` is accepted" in gameplay
    assert "exact top-level manifest V7 identity" in gameplay

    sequences = documents["docs/spec/game/dialogue-and-cutscene-sequences.md"]
    assert "accepts the dialogue-character projection only in\nmanifest V7" in sequences
    assert "`dialogue_characters` is absent" in sequences
