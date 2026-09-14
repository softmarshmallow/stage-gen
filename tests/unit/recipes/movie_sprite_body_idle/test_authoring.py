"""Public authoring refuses unsupported controls before a video operation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gnode import BindingTable
from stage_gen.pipeline import plan
from stage_gen.recipes.movie_sprite_body_idle import Authoring, create_pipeline
from stage_gen.recipes.movie_sprite_body_idle.examples.supplied_clip.make_inputs import make_frame


def test_motion_sections_accept_text_and_ordered_lists() -> None:
    authoring = Authoring(
        canonical_image="actor.png",
        prompt="A quiet listening pose.",
        positive_prompts="Let the scarf settle slowly.",
        negative_prompts=["Keep head and shoulders fixed.", "Keep the hand on the prop."],
    )
    assert authoring.positive_prompts == ["Let the scarf settle slowly."]
    assert authoring.negative_prompts == [
        "Keep head and shoulders fixed.",
        "Keep the hand on the prop.",
    ]


@pytest.mark.parametrize("canonical", ["", "/private/actor.png", "../actor.png", "x\\actor.png"])
def test_canonical_reference_must_be_portable(canonical: str) -> None:
    with pytest.raises(ValueError):
        Authoring(canonical_image=canonical)


@pytest.mark.parametrize("unsupported", ["mid_frames", "extra_references", "positivePrompts"])
def test_unknown_authoring_controls_are_not_silently_ignored(unsupported: str) -> None:
    with pytest.raises(ValueError):
        Authoring.model_validate({"canonical_image": "actor.png", unsupported: []})


def test_missing_video_route_is_refused_while_planning(tmp_path: Path) -> None:
    make_frame(0).save(tmp_path / "actor.png")
    (tmp_path / "authoring.json").write_text(json.dumps({"canonical_image": "actor.png"}))
    (tmp_path / "finish.json").write_text("{}")
    definition = create_pipeline(
        authoring_ref="authoring.json",
        finish_ref="finish.json",
        routes=BindingTable(()),
    )
    with pytest.raises(ValueError):
        plan(definition, input_root=tmp_path)
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "actor.png",
        "authoring.json",
        "finish.json",
    ]
