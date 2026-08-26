from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from stage_gen.interfaces.cli import _parse_input_document
from stage_gen.recipes.dialogue_scene.identity import canonical_json_bytes, canonical_sha256
from stage_gen.recipes.dialogue_scene.models import DialogueBundle, DialogueThemeRequest
from stage_gen.recipes.dialogue_scene.recipe import (
    dialogue_scene_recipe,
    parse_dialogue_scene_input,
)


def request_value(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 2,
        "kind": "dialogue-theme-request-v2",
        "scene_brief": "Adult university study lounge after a graduate seminar",
        "appearance": {
            "id": "mio-researcher",
            "label": "Mio",
            "age": 23,
            "role": "Graduate researcher",
            "description": "Adult woman in a navy cardigan",
            "concept": {
                "mode": "generate",
                "description": "Original clean Japanese anime visual-novel character direction",
            },
        },
        "background": {"mode": "generate", "description": "Evening study lounge"},
        "dialogue": [
            {
                "id": "opening",
                "speaker": "Mio",
                "text": "I hoped you would stay after the seminar.",
                "expression_state": "neutral",
            }
        ],
        "presentation": {"slot": "right", "framing_zoom": 70, "source_framing_zoom": 70},
        "transparency_mode": "chroma",
    }
    value.update(overrides)
    return value


def profile_request_value(source_sha256: str, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 3,
        "kind": "dialogue-theme-request-v3",
        "scene_brief": "Adult cartographer conversation beside a quiet harbor",
        "character_profile": {
            "schema_version": 1,
            "kind": "character-profile-binding-v1",
            "ref": "library/characters/mira-vale-cartographer/profile.toml",
            "source_sha256": source_sha256,
        },
        "background": {"mode": "generate", "description": "Quiet harbor at dusk"},
        "dialogue": [
            {
                "id": "opening",
                "speaker": "Mira Vale",
                "text": "The tide changed the coastline again.",
                "expression_state": "neutral",
            }
        ],
        "presentation": {"slot": "right", "framing_zoom": 70, "source_framing_zoom": 70},
        "transparency_mode": "chroma",
    }
    value.update(overrides)
    return value


def test_request_is_strict_canonical_and_rejects_v1_or_camel_case() -> None:
    parsed = parse_dialogue_scene_input(request_value())
    reversed_value = dict(reversed(list(parsed.items())))
    assert canonical_json_bytes(parsed) == canonical_json_bytes(reversed_value)
    assert canonical_sha256(parsed) == canonical_sha256(reversed_value)

    with pytest.raises(ValueError, match="invalid dialogue-theme-request-v2"):
        parse_dialogue_scene_input(request_value(kind="dialogue-theme-request"))
    camel = request_value()
    camel["sceneBrief"] = camel.pop("scene_brief")
    with pytest.raises(ValueError, match="invalid dialogue-theme-request-v2"):
        parse_dialogue_scene_input(camel)
    with pytest.raises(ValueError, match="invalid dialogue-theme-request-v2"):
        parse_dialogue_scene_input({**request_value(), "unknown": True})
    with pytest.raises(ValueError, match="content policy"):
        parse_dialogue_scene_input(
            request_value(scene_brief="A minor in a university study lounge")
        )


def test_request_accepts_native_alpha_and_defaults_new_documents_to_native() -> None:
    explicit = DialogueThemeRequest.model_validate(request_value(transparency_mode="native"))
    assert explicit.transparency_mode == "native"

    omitted = request_value()
    del omitted["transparency_mode"]
    assert DialogueThemeRequest.model_validate(omitted).transparency_mode == "native"


def test_request_rejects_underage_duplicate_beats_and_unknown_expression() -> None:
    underage = request_value()
    appearance = underage["appearance"]
    assert isinstance(appearance, dict)
    underage["appearance"] = {**appearance, "age": 20}
    with pytest.raises(ValueError):
        parse_dialogue_scene_input(underage)

    duplicate = request_value()
    dialogue = duplicate["dialogue"]
    assert isinstance(dialogue, list)
    duplicate["dialogue"] = [dialogue[0], dialogue[0]]
    with pytest.raises(ValueError, match="unique"):
        parse_dialogue_scene_input(duplicate)

    invalid_state = request_value()
    invalid_dialogue = invalid_state["dialogue"]
    assert isinstance(invalid_dialogue, list)
    first_beat = invalid_dialogue[0]
    assert isinstance(first_beat, dict)
    invalid_state["dialogue"] = [{**first_beat, "expression_state": "angry"}]
    with pytest.raises(ValueError):
        parse_dialogue_scene_input(invalid_state)

    without_background = request_value(background={"mode": "none"})
    with pytest.raises(ValueError, match="invalid dialogue-theme-request-v2"):
        parse_dialogue_scene_input(without_background)


def test_recipe_declares_locked_dependency_dag() -> None:
    assert [stage.name for stage in dialogue_scene_recipe.stages] == [
        "prepare",
        "style-selection",
        "appearance-concept",
        "scene-plan",
        "background",
        "neutral",
        "expressions",
        "canonicalize",
        "bundle",
    ]
    assert dialogue_scene_recipe.stages[-1].depends_on == ("background", "canonicalize")


def test_profile_request_is_strict_v3_and_selects_only_the_profile_dag() -> None:
    request = profile_request_value("a" * 64)
    parsed = parse_dialogue_scene_input(request)
    assert parsed == request
    assert [stage.name for stage in dialogue_scene_recipe.stages_for(parsed)] == [
        "prepare",
        "profile-resolve",
        "style-selection",
        "appearance-concept",
        "scene-plan",
        "background",
        "neutral",
        "expressions",
        "canonicalize",
        "bundle",
    ]
    assert dialogue_scene_recipe.stages_for(request_value()) == dialogue_scene_recipe.stages

    with pytest.raises(ValueError, match="invalid dialogue-theme-request-v3"):
        parse_dialogue_scene_input(
            profile_request_value("a" * 64, character_profile={"ref": "profile.toml"})
        )
    outside_library = profile_request_value("a" * 64)
    outside_binding = outside_library["character_profile"]
    assert isinstance(outside_binding, dict)
    outside_binding["ref"] = "authored/mira/profile.toml"
    with pytest.raises(ValueError, match="library/characters"):
        parse_dialogue_scene_input(outside_library)
    camel = profile_request_value("a" * 64)
    binding = camel["character_profile"]
    assert isinstance(binding, dict)
    binding["sourceSha256"] = binding.pop("source_sha256")
    with pytest.raises(ValueError, match="invalid dialogue-theme-request-v3"):
        parse_dialogue_scene_input(camel)


def test_bundle_paths_rights_and_review_are_strict() -> None:
    raw = {
        "schema_version": 2,
        "kind": "dialogue-scene-bundle-v2",
        "recipe": "dialogue-scene",
        "recipe_version": "dialogue-scene-v3",
        "tag": "demo",
        "run_identity_sha256": "a" * 64,
        "request": {
            "path": "request.json",
            "sha256": "b" * 64,
            "provenance_path": "request.json.meta.json",
            "provenance_sha256": "1" * 64,
        },
        "plan": {
            "path": "plan.json",
            "sha256": "c" * 64,
            "provenance_path": "plan.json.meta.json",
            "provenance_sha256": "2" * 64,
        },
        "assets": [
            {
                "id": "concept",
                "role": "concept",
                "state": None,
                "path": "assets/concept.png",
                "sha256": "d" * 64,
                "bytes": 1,
                "media": {
                    "mime_type": "image/png",
                    "width": 1024,
                    "height": 1536,
                    "alpha": False,
                },
                "provenance_path": "assets/concept.png.meta.json",
                "provenance_sha256": "e" * 64,
                "selected_attempt": 1,
            },
            {
                "id": "background",
                "role": "background",
                "state": None,
                "path": "assets/background.png",
                "sha256": "3" * 64,
                "bytes": 1,
                "media": {
                    "mime_type": "image/png",
                    "width": 1672,
                    "height": 941,
                    "alpha": False,
                },
                "provenance_path": "assets/background.png.meta.json",
                "provenance_sha256": "4" * 64,
                "selected_attempt": 1,
            },
            *[
                {
                    "id": f"mio-{state}",
                    "role": "expression",
                    "state": state,
                    "path": f"assets/expression-{state}.png",
                    "sha256": "d" * 64,
                    "bytes": 1,
                    "media": {
                        "mime_type": "image/png",
                        "width": 1024,
                        "height": 1536,
                        "alpha": True,
                    },
                    "provenance_path": f"assets/expression-{state}.png.meta.json",
                    "provenance_sha256": "e" * 64,
                    "selected_attempt": 1,
                }
                for state in ("neutral", "delighted", "flustered", "concerned")
            ],
        ],
        "attempt_ledger": {"path": "attempts.json", "sha256": "f" * 64},
        "scene_data": {
            "scene_id": "mio-scene",
            "title": "Study lounge",
            "scene_label": "Study lounge",
            "concept_asset_id": "concept",
            "background": {"asset_id": "background", "alt": "University study lounge"},
            "appearance": {
                "id": "mio",
                "label": "Mio",
                "age": 23,
                "role": "Graduate researcher",
                "tagline": "Graduate researcher",
                "description": "Adult woman in a navy cardigan",
                "visual_identity": "Adult woman in a navy cardigan",
                "art_direction": "Original visual novel art",
            },
            "placement": {"slot": "right", "framing_zoom": 70, "source_framing_zoom": 70},
            "available_states": ["neutral", "delighted", "flustered", "concerned"],
            "expression_variants": [
                {
                    "id": f"mio-{state}",
                    "asset_id": f"mio-{state}",
                    "appearance_id": "mio",
                    "state": state,
                    "label": state,
                    "description": f"Adult {state} expression",
                    "alt": f"Mio with a {state} expression",
                    "slot": "right",
                }
                for state in ("neutral", "delighted", "flustered", "concerned")
            ],
            "dialogue": [
                {
                    "id": "opening",
                    "speaker": "Mio",
                    "text": "I hoped you would stay.",
                    "expression_state": "neutral",
                }
            ],
        },
        "review": {"status": "pending", "path": None, "sha256": None},
        "rights": {"aggregate": "unreviewed", "publication_authorized": False},
    }
    assert DialogueBundle.model_validate(raw).rights.publication_authorized is False
    legacy = {**raw, "schema_version": 1, "kind": "dialogue-scene-bundle"}
    with pytest.raises(ValidationError):
        DialogueBundle.model_validate(legacy)
    camel = {**raw, "runIdentitySha256": raw["run_identity_sha256"]}
    del camel["run_identity_sha256"]
    with pytest.raises(ValidationError):
        DialogueBundle.model_validate(camel)
    raw["assets"][0]["path"] = "../escape.png"  # type: ignore[index]
    with pytest.raises(ValidationError, match="portable relative"):
        DialogueBundle.model_validate(raw)


def test_canonical_serialization_is_standards_compliant_json() -> None:
    request = DialogueThemeRequest.model_validate(request_value())
    assert json.loads(canonical_json_bytes(request)) == request.model_dump(
        mode="json", exclude_none=True
    )


def test_cli_document_loader_routes_json_and_toml_to_strict_request() -> None:
    value = request_value()
    assert parse_dialogue_scene_input(
        _parse_input_document(json.dumps(value), suffix=".json")
    ) == parse_dialogue_scene_input(value)
    toml = """
schema_version = 2
kind = "dialogue-theme-request-v2"
scene_brief = "Adult university study lounge after a graduate seminar"
transparency_mode = "chroma"

[appearance]
id = "mio-researcher"
label = "Mio"
age = 23
role = "Graduate researcher"
description = "Adult woman in a navy cardigan"

[appearance.concept]
mode = "generate"
description = "Original clean Japanese anime visual-novel character direction"

[background]
mode = "generate"
description = "Evening study lounge"

[[dialogue]]
id = "opening"
speaker = "Mio"
text = "I hoped you would stay after the seminar."
expression_state = "neutral"

[presentation]
slot = "right"
framing_zoom = 70
source_framing_zoom = 70
"""
    assert parse_dialogue_scene_input(_parse_input_document(toml, suffix=".toml")) == (
        parse_dialogue_scene_input(value)
    )
