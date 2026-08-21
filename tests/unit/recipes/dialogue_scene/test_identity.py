from __future__ import annotations

from stage_gen.recipes.dialogue_scene.identity import (
    canonical_sha256,
    run_identity,
    stage_identity,
)

from .test_contracts import profile_request_value, request_value


def test_profile_run_identity_uses_v4_while_legacy_identity_remains_exact_v3() -> None:
    legacy = request_value()
    assert run_identity(legacy) == f"dialogue-{canonical_sha256(legacy)[:24]}"

    profile_request = profile_request_value("a" * 64)
    expected = canonical_sha256({"recipe_version": 4, "request": profile_request})
    assert run_identity(profile_request) == f"dialogue-{expected[:24]}"

    legacy_stage = stage_identity(
        run_id="legacy",
        stage="prepare",
        dependencies={},
        generation=0,
    )
    explicit_legacy_stage = stage_identity(
        run_id="legacy",
        stage="prepare",
        dependencies={},
        generation=0,
        recipe_version=3,
    )
    profile_stage = stage_identity(
        run_id="legacy",
        stage="prepare",
        dependencies={},
        generation=0,
        recipe_version=4,
    )
    assert legacy_stage == explicit_legacy_stage
    assert profile_stage != legacy_stage
