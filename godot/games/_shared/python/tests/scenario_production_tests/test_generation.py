"""Track production requirements are game metadata, independent of narrative syntax."""

import pytest

from demo_game_tools.scenario import ScenarioDeclarations


def _declarations() -> ScenarioDeclarations:
    return ScenarioDeclarations.model_validate(
        {
            "schema_version": 2,
            "kind": "scenario-v2",
            "game_id": "testgame",
            "scenario_id": "last_class",
            "display_name": "The Last Class",
            "revision": 1,
            "script": "scenarios/last_class.scenario",
            "script_sha256": "0" * 64,
            "entry": "start",
            "cast": [{"actor_id": "you", "display_name": "You"}],
            "stages": [{"stage_id": "classroom", "brief": "An original empty classroom"}],
            "flags": [{"flag_id": "quiet"}],
            "endings": [{"outcome_id": "listened", "label": "You listened"}],
        }
    )


def _declarations_with_track() -> ScenarioDeclarations:
    """The same scenario, plus one declared music identity.

    `generation` is the soundtrack component's own `TrackGenerationIntent`, so a
    scenario and a soundtrack catalog say "how to produce this track" in exactly
    one shape rather than two that drift.
    """

    payload = _declarations().model_dump(mode="json")
    payload["tracks"] = [
        {
            "track_id": "room_tone",
            "brief": "An original sparse instrumental for an empty room",
            "generation": {
                "intent": "generate",
                "instrumental": True,
                "seamless_loop": True,
                "target_duration_seconds": 60,
            },
        }
    ]
    return ScenarioDeclarations.model_validate(payload)


def test_a_track_declaration_carries_the_soundtrack_components_generation_intent() -> None:
    declarations = _declarations_with_track()
    track = declarations.tracks[0]
    assert track.track_id == "room_tone"
    assert track.generation.instrumental is True
    assert track.generation.target_duration_seconds == 60


def test_a_track_declared_without_generation_intent_is_refused() -> None:
    payload = _declarations().model_dump(mode="json")
    payload["tracks"] = [{"track_id": "room_tone", "brief": "An original brief"}]
    with pytest.raises(ValueError, match="generation"):
        ScenarioDeclarations.model_validate(payload)
