from __future__ import annotations

import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[2]

CURRENT_GAME_DOC_PATHS = (
    "docs/game-contract.md",
    "docs/game-package.md",
    "docs/game-maps.md",
    "docs/game-soundtrack.md",
    "docs/game-sound-effects.md",
    "docs/dialogue-character-runtime-pipeline.md",
    "docs/spec/game/authored-contract-schema.md",
    "docs/spec/game/map-generation-contract.md",
    "docs/spec/game/generation-pipeline.md",
    "docs/spec/game/ui.md",
    "docs/spec/scene-gameplay-components.md",
    "docs/spec/game/dialogue-and-cutscene-sequences.md",
    "docs/spec/game/pointclick-room.md",
    "docs/spec/game/runner.md",
)

RETIRED_PREPARED_IDENTITIES = (
    "game-contract-v1",
    "game-ui-v1",
    "game-package-v3",
    "game-sequence-catalog-v1",
    "game-contract-v2",
    "game-contract-v3",
    "game-contract-v4",
    "game-contract-v6",
    "game-contract-v7",
    "game-contract-v8",
    "game-map-v1",
    "game-map-v2",
    "game-map-v3",
    "game-map-v7",
    "game-map-v8",
    "prepared-game-runtime-v1",
    "prepared-game-runtime-v2",
    "prepared-game-runtime-v3",
    "prepared-game-runtime-v9",
    "game-map-book-v1",
    "game-map-book-manifest-v2",
    "manifest V7",
    # Retired by the coordinated persisted-vocabulary bump that landed with the node ABI.
    # The before/after table in docs/spec/asset-taxonomy.md is the one place these survive,
    # deliberately as history; no current game doc may advertise them again.
    "scrolling-preview",
    "prepared-game-execution-graph-v1",
    "prepared-game-execution-view-v1",
    "dialogue-scene-execution-graph-v1",
    "prepared-world-v1",
    "prepared-content-v3",
    # Retired when the room gained its cover: every published room image is now
    # generated against one style reference, and the manifest ships it.
    "pointclick-room-runtime-v1",
    # Retired when the cover became an authored package member: a room is a
    # directory of room.toml plus the references its art is drawn against.
    "pointclick-room-v1",
    # Retired by the CookieRun adoption pass: the runner family gained the
    # duck verb, hazard anchors, and the published arc arithmetic in one bump.
    "runner-gameplay-v1",
    "runner-track-v1",
    "runner-avatar-v1",
    "sideview-runner-runtime-v1",
    "sideview-runner-runtime-v2",
    # Retired when runner packages gained per-segment structural ground and
    # honest visible-rider-machine actor semantics.
    "runner-track-v2",
    "runner-avatar-v2",
    "sideview-runner-runtime-v3",
    # Retired when the runner split what `collision_policy` had conflated: the
    # torso box admission proves is one thing, and what a contact costs is
    # another. The gameplay contract gained a per-source consequence table and
    # an optional vitals gauge, and the runtime manifest publishes both.
    "runner-gameplay-v2",
    "sideview-runner-runtime-v4",
    # Retired when the runner's audio realization union gained the generated
    # clip: an effect may now name a run artifact, so the runtime manifest
    # moved with the contract.
    "runner-audio-v1",
    "sideview-runner-runtime-v5",
    "runner-audio-v2",
    "sideview-runner-runtime-v6",
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
            # Bounded on the right, so a retired `-v1` is not read out of a current `-v10`.
            assert re.search(rf"{re.escape(identity)}(?![0-9])", document) is None, (
                f"{path} advertises retired identity {identity}"
            )
        for pattern in FORBIDDEN_OLD_VERSION_SUPPORT:
            assert re.search(pattern, document, flags=re.IGNORECASE) is None, (
                f"{path} advertises old-version support matching {pattern!r}"
            )

    game_contract = documents["docs/game-contract.md"]
    for identity in (
        "`game-package-v4`",
        "`game-contract-v9`",
        "`gameplay-contract-v1`",
        "`game-ui-v2`",
        "`game-map-v9`",
        "`prepared-game-runtime-v10`",
    ):
        assert identity in game_contract
    assert "climbable geometry and placement" in game_contract
    assert "portal presentation" in game_contract
    assert "endpoint anchors" in game_contract

    package = documents["docs/game-package.md"]
    assert "`game.toml` is the membership root" in package
    assert "The player climb states `climb_ladder` and `climb_rope` are the only" in package
    assert "gameplay movement `crouch` and player motion `crouch`" in package

    maps = documents["docs/game-maps.md"]
    for identity in (
        "`game-map-v9`",
        "`climbable-atlas-v1`",
        "`portal-pair-1x2-v1`",
        "`prepared-game-runtime-v10`",
    ):
        assert identity in maps
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
    assert "`map-terrain-v1`" in map_contract
    assert "`climbable-atlas-v1`" in map_contract
    assert 'mode = "portal-pair-1x2-v1"' in map_contract

    pipeline = documents["docs/spec/game/generation-pipeline.md"]
    assert "deterministically assemble 47-mask atlas" in pipeline
    assert "Player `crouch` is the current explicit vocabulary boundary" in pipeline
    assert "Optional map-local climbable and portal branches" in pipeline
    # The persisted recipe identity and its execution-document kinds, post-bump.
    for identity in (
        '`recipe: "sideview-platformer"`',
        "`sideview-platformer-execution-graph-v1`",
        "`sideview-platformer-world-v1`",
        "`sideview-platformer-content-v1`",
    ):
        assert identity in pipeline
    # Nodes are typed and registry-dispatched, not addressed by path or name convention.
    assert "Every node in this graph is **typed**" in pipeline
    assert "`2d/sideview/platformer/motion_atlas.generate`" in pipeline
    assert "Dispatch is a registry lookup over `type_id`" in pipeline

    ui = documents["docs/spec/game/ui.md"]
    assert "exact current identity is `game-ui-v2`" in ui
    assert "every slot interior" in ui

    soundtrack = documents["docs/game-soundtrack.md"]
    assert "exact identity is\n`game-soundtrack-v1`" in soundtrack
    assert "Provider-free integration" in soundtrack
    assert "`prepared-game-runtime-v10`" in soundtrack

    sound_effects = documents["docs/game-sound-effects.md"]
    assert "`runner-audio-v3`" in sound_effects
    assert "`generated_clip_v1`" in sound_effects
    assert "No normalization, no trimming, no\nconcatenation" in sound_effects
    assert "spec/model-eleven-text-to-sound-v2.md" in sound_effects

    runner = documents["docs/spec/game/runner.md"]
    assert "`runner-audio-v3`" in runner
    assert "`generated_clip_v1`" in runner
    assert "`runner-track-v3`" in runner
    assert "`runner-avatar-v3`" in runner
    assert "`runner-structural-ground-v1`" in runner
    assert "native-alpha GPT Image 2" in runner
    assert "`sideview-runner-runtime-v7`" in documents["docs/game-package.md"]

    dialogue = documents["docs/dialogue-character-runtime-pipeline.md"]
    assert "NPC visual identity in `content/npcs.toml`" in dialogue
    assert "dialogue\ncontrol flow in `scenarios/*.scenario`" in dialogue
    assert "`prepared-game-runtime-v10`" in dialogue

    gameplay = documents["docs/spec/scene-gameplay-components.md"]
    assert "`gameplay-contract-v1`" in gameplay
    assert "binary\noccupancy and 47-mask atlas" in gameplay
    assert "Portal art and endpoint" in gameplay

    sequences = documents["docs/spec/game/dialogue-and-cutscene-sequences.md"]
    assert "current prepared gameplay consumer" in sequences
    assert "`prepared-game-runtime-v10`" in sequences

    room = documents["docs/spec/game/pointclick-room.md"]
    for identity in (
        "`pointclick-room-v2`",
        "`pointclick-room-execution-graph-v1`",
        "`pointclick-room-runtime-v2`",
        "`pointclick-solvability-v1`",
    ):
        assert identity in room
    assert "The third recipe on the engine, at taxonomy path `2d/roomview/pointclick`" in room
    # Admission is a proof, not a schema check: the recipe refuses an unfinishable room.
    assert "**Admission is a proof.**" in room
