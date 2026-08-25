"""Direct contract tests for actor scale-reference measurements."""

from __future__ import annotations

from stage_gen.recipes.scrolling_preview.scale_reference import (
    actor_scale_reference_prompt,
    evaluate_actor_scale_reference,
    parse_actor_scale_reference,
)


def test_strip_prompt_uses_the_selected_frames_coordinate_space() -> None:
    prompt = actor_scale_reference_prompt("a game character", 2)

    assert "frame 3, counting from the left" in prompt
    assert "selected frame's height" in prompt
    assert "selected frame's width" in prompt
    assert "whole image's width" not in prompt


def test_still_prompt_describes_the_single_cell_the_reviewer_receives() -> None:
    prompt = actor_scale_reference_prompt("a village resident", 0, still=True)

    assert "single still figure" in prompt
    assert "four-frame animation strip" not in prompt
    assert "whole image's height" in prompt
    assert "whole image's width" in prompt


def test_reference_extent_uses_the_inspected_frames_dimensions() -> None:
    reference = parse_actor_scale_reference(
        {
            "part": "head",
            "top": 0.1,
            "bottom": 0.2,
            "left": 0.1,
            "right": 0.6,
            "confident": True,
            "evidence": "head bounded inside the selected frame",
        }
    )

    record = evaluate_actor_scale_reference(
        reference,
        frame_width=100,
        frame_height=200,
    )

    assert record["extent_pixels"] == 50.0
