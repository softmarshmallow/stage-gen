from __future__ import annotations

import json
from pathlib import Path

from stage_gen.recipes.dialogue_scene.cache import DialogueStageCache


def test_cache_rejects_stale_bytes_and_force(tmp_path: Path) -> None:
    artifact = tmp_path / "assets" / "concept.png"
    artifact.parent.mkdir()
    artifact.write_bytes(b"first")
    cache = DialogueStageCache(tmp_path)
    key = cache.key("appearance-concept", inputs={"request": "a"}, dependencies={})
    cache.store("appearance-concept", key, ("assets/concept.png",))
    saved = json.loads((tmp_path / ".dialogue-cache/appearance-concept.json").read_text())
    assert saved["schema_version"] == 2
    assert saved["kind"] == "dialogue_stage_cache_v2"
    assert "schemaVersion" not in saved
    assert cache.load("appearance-concept", key) == ("assets/concept.png",)
    assert cache.load("appearance-concept", key, force=True) is None
    artifact.write_bytes(b"second")
    assert cache.load("appearance-concept", key) is None


def test_profile_v4_cache_identity_cannot_collide_with_legacy_v3() -> None:
    cache = DialogueStageCache(Path("unused"))
    inputs = {
        "request": "a",
        "character_profile_source_sha256": "b",
        "character_profile_sha256": "c",
    }
    legacy = cache.key("appearance-concept", inputs=inputs, dependencies={})
    profile = cache.key(
        "appearance-concept",
        inputs=inputs,
        dependencies={},
        recipe_version="dialogue-scene-v4",
        contract_schema_version=3,
    )
    assert profile != legacy
