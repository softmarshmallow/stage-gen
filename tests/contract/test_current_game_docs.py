from __future__ import annotations

import re
from pathlib import Path

from stage_gen.identities import current_versions

REPOSITORY_ROOT = Path(__file__).parents[2]

CURRENT_GAME_DOC_PATHS = (
    "docs/game-contract.md",
    "docs/game-package.md",
    "docs/game-maps.md",
    "docs/game-soundtrack.md",
    "docs/game-sound-effects.md",
    "docs/game-voice.md",
    "docs/spec/model-eleven-v3.md",
    "docs/dialogue-character-runtime-pipeline.md",
    "docs/spec/game/authored-contract-schema.md",
    "docs/spec/game/map-generation-contract.md",
    "docs/spec/game/generation-pipeline.md",
    "docs/spec/game/ui.md",
    "docs/spec/scene-gameplay-components.md",
    "docs/spec/game/dialogue-and-cutscene-sequences.md",
    "docs/spec/game/pointclick-room.md",
    "docs/spec/game/runner.md",
    "docs/spec/game/fx.md",
)

#: Which documents must name which identities, at whatever version is current. The
#: version itself derives from the identity table; a bump edits the code, not this.
REQUIRED_FAMILIES = {
    "docs/game-contract.md": (
        "game-package",
        "game-contract",
        "gameplay-contract",
        "game-ui",
        "game-map",
        "prepared-game-runtime",
    ),
    "docs/game-maps.md": (
        "game-map",
        "climbable-atlas",
        "portal-pair-1x2",
        "prepared-game-runtime",
    ),
    "docs/game-package.md": ("sideview-runner-runtime",),
    "docs/spec/game/authored-contract-schema.md": ("game-contract",),
    "docs/spec/game/map-generation-contract.md": ("map-terrain", "climbable-atlas"),
    "docs/spec/game/generation-pipeline.md": (
        "sideview-platformer-execution-graph",
        "sideview-platformer-world",
        "sideview-platformer-content",
    ),
    "docs/spec/game/ui.md": ("game-ui",),
    "docs/game-soundtrack.md": ("game-soundtrack", "prepared-game-runtime"),
    "docs/game-sound-effects.md": ("runner-audio", "generated_clip"),
    "docs/spec/game/runner.md": (
        "runner-audio",
        "generated_clip",
        "spoken_line",
        "game-voices",
        "runner-track",
        "runner-avatar",
        "runner-structural-ground",
    ),
    "docs/game-voice.md": ("game-voices", "spoken_line"),
    "docs/spec/game/fx.md": ("game-fx",),
    "docs/dialogue-character-runtime-pipeline.md": ("prepared-game-runtime",),
    "docs/spec/scene-gameplay-components.md": ("gameplay-contract",),
    "docs/spec/game/dialogue-and-cutscene-sequences.md": ("prepared-game-runtime",),
    "docs/spec/game/pointclick-room.md": (
        "pointclick-room",
        "pointclick-room-execution-graph",
        "pointclick-room-runtime",
        "pointclick-solvability",
    ),
}

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

    versions = current_versions()
    for path, families in REQUIRED_FAMILIES.items():
        for family in families:
            current = versions[family]
            assert any(
                f"{family}-v{v}" in documents[path] or f"{family}_v{v}" in documents[path]
                for v in current
            ), f"{path} does not name the current {family}"

    for path, document in documents.items():
        for pattern in FORBIDDEN_OLD_VERSION_SUPPORT:
            assert re.search(pattern, document, flags=re.IGNORECASE) is None, (
                f"{path} advertises old-version support matching {pattern!r}"
            )

    game_contract = documents["docs/game-contract.md"]
    assert "climbable geometry and placement" in game_contract
    assert "portal presentation" in game_contract
    assert "endpoint anchors" in game_contract

    package = documents["docs/game-package.md"]
    assert "`game.toml` is the membership root" in package
    assert "The player climb states `climb_ladder` and `climb_rope` are the only" in package
    assert "gameplay movement `crouch` and player motion `crouch`" in package

    maps = documents["docs/game-maps.md"]
    assert "packaged 47-mask" in maps
    assert "is no map index" in maps

    schema = documents["docs/spec/game/authored-contract-schema.md"]
    assert 'Only `schema_version = 9` and `kind = "game-contract-v9"` are accepted' in schema
    assert 'source = "ui.toml"' in schema
    assert "gameplay.toml` owns climb permission and portal destinations" in schema
    assert 'source = "runner/audio.toml"' in schema

    map_contract = documents["docs/spec/game/map-generation-contract.md"]
    assert "exact-current authored, generation, manifest, and consumer contract" in map_contract
    # Geometry left the authored document; the request that produces it is what the map owns.
    assert "the terrain request a generator answers" in map_contract
    assert 'mode = "portal-pair-1x2-v1"' in map_contract

    pipeline = documents["docs/spec/game/generation-pipeline.md"]
    assert "deterministically assemble 47-mask atlas" in pipeline
    assert "Player `crouch` is the current explicit vocabulary boundary" in pipeline
    assert "Optional map-local climbable and portal branches" in pipeline
    # The persisted recipe identity and its execution-document kinds, post-bump.
    # Nodes are typed and registry-dispatched, not addressed by path or name convention.
    assert "Every node in this graph is **typed**" in pipeline
    assert "`2d/sideview/platformer/motion_atlas.generate`" in pipeline
    assert "Dispatch is a registry lookup over `type_id`" in pipeline

    ui = documents["docs/spec/game/ui.md"]
    assert "`preview_icons`" in ui
    assert "every slot interior" in ui

    soundtrack = documents["docs/game-soundtrack.md"]
    assert "Provider-free integration" in soundtrack

    sound_effects = documents["docs/game-sound-effects.md"]
    assert "No normalization, no trimming, no\nconcatenation" in sound_effects
    assert "spec/model-eleven-text-to-sound-v2.md" in sound_effects

    runner = documents["docs/spec/game/runner.md"]
    assert "native-alpha GPT Image 2" in runner
    voice = documents["docs/game-voice.md"]
    assert "generate-speech" in voice

    dialogue = documents["docs/dialogue-character-runtime-pipeline.md"]
    assert "NPC visual identity in `content/npcs.toml`" in dialogue
    assert "dialogue\ncontrol flow in `scenarios/*.scenario`" in dialogue

    gameplay = documents["docs/spec/scene-gameplay-components.md"]
    assert "binary\noccupancy and 47-mask atlas" in gameplay
    assert "Portal art and endpoint" in gameplay

    sequences = documents["docs/spec/game/dialogue-and-cutscene-sequences.md"]
    assert "current prepared gameplay consumer" in sequences

    room = documents["docs/spec/game/pointclick-room.md"]
    assert "The third recipe on the engine, at taxonomy path `2d/roomview/pointclick`" in room
    # Admission is a proof, not a schema check: the recipe refuses an unfinishable room.
    assert "**Admission is a proof.**" in room
