"""Parameterised head-to-body proportion for the player character."""

from __future__ import annotations

import pytest

from stage_gen.recipes.scrolling_preview.proportion import (
    MAXIMUM_HEADS_TALL,
    MINIMUM_HEADS_TALL,
    character_proportion_prompt,
    character_proportion_tag_suffix,
    parse_character_heads_tall,
)
from stage_gen.recipes.scrolling_preview.recipe import (
    parse_scrolling_preview_input,
    scrolling_preview_tag,
)


class TestParsing:
    @pytest.mark.parametrize("value", [2, 2.0, 2.5, 3, 6.5, 8, 8.0])
    def test_accepts_the_supported_range(self, value: float) -> None:
        assert parse_character_heads_tall(value) == round(float(value), 1)

    @pytest.mark.parametrize("value", [1.9, 0, -3, 8.1, 100])
    def test_rejects_builds_outside_the_range(self, value: float) -> None:
        with pytest.raises(ValueError, match="between"):
            parse_character_heads_tall(value)

    def test_two_heads_is_the_floor(self) -> None:
        # Below this a body cannot carry readable limbs, wardrobe, or a weapon at sprite scale.
        assert MINIMUM_HEADS_TALL == 2.0
        assert parse_character_heads_tall(MINIMUM_HEADS_TALL) == 2.0
        with pytest.raises(ValueError):
            parse_character_heads_tall(MINIMUM_HEADS_TALL - 0.1)

    @pytest.mark.parametrize("value", [True, False, "3", None, [3]])
    def test_rejects_non_numbers(self, value: object) -> None:
        # bool is an int in Python, so True would otherwise read as a one-head character.
        with pytest.raises(ValueError, match="must be a number"):
            parse_character_heads_tall(value)

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_rejects_non_finite(self, value: float) -> None:
        with pytest.raises(ValueError, match=r"finite|between"):
            parse_character_heads_tall(value)

    def test_rounds_to_one_decimal_so_equivalent_requests_share_a_tag(self) -> None:
        # One decimal is the finest distinction that survives a sprite a few hundred pixels
        # tall, so near-identical requests must collapse to one build and one run directory.
        assert parse_character_heads_tall(2.54) == 2.5
        assert parse_character_heads_tall(2.5) == 2.5
        assert parse_character_heads_tall(2.499) == 2.5
        assert parse_character_heads_tall(2.61) == 2.6
        collapsed = {parse_character_heads_tall(value) for value in (2.5, 2.51, 2.54, 2.499)}
        assert collapsed == {2.5}


class TestPrompt:
    def test_states_the_head_fraction_not_just_the_count(self) -> None:
        # "three heads tall" is jargon a model honours inconsistently; a fraction is a
        # measurement it can act on.
        assert "33% of the full standing height" in character_proportion_prompt(3.0)
        assert "50% of the full standing height" in character_proportion_prompt(2.0)

    def test_names_the_build_so_the_number_is_not_the_only_signal(self) -> None:
        assert "super-deformed" in character_proportion_prompt(2.0)
        assert "chibi" in character_proportion_prompt(3.5)
        assert "naturalistic" in character_proportion_prompt(MAXIMUM_HEADS_TALL)

    def test_binds_the_proportion_across_views_and_frames(self) -> None:
        assert "every view and every frame" in character_proportion_prompt(2.0)

    def test_renders_whole_numbers_without_a_trailing_decimal(self) -> None:
        assert "exactly 2 heads tall" in character_proportion_prompt(2.0)
        assert "exactly 2.5 heads tall" in character_proportion_prompt(2.5)


class TestRunIsolation:
    def test_each_build_gets_its_own_run_directory(self) -> None:
        # Two proportions must never share cached artwork.
        base = scrolling_preview_tag(parse_scrolling_preview_input("whimsical forest"))
        two = scrolling_preview_tag(
            parse_scrolling_preview_input({"prompt": "whimsical forest", "character_heads_tall": 2})
        )
        six = scrolling_preview_tag(
            parse_scrolling_preview_input({"prompt": "whimsical forest", "character_heads_tall": 6})
        )
        assert len({base, two, six}) == 3
        assert two.endswith("heads-2")
        assert six.endswith("heads-6")

    def test_a_fractional_build_keeps_a_filesystem_safe_tag(self) -> None:
        assert character_proportion_tag_suffix(2.5) == "heads-2p5"

    def test_unset_is_the_default_and_leaves_the_input_untouched(self) -> None:
        # Unset must stay meaningful: it hands the choice back to the image model rather than
        # quietly applying a house style.
        parsed = parse_scrolling_preview_input("whimsical forest")
        assert "character_heads_tall" not in parsed

    def test_an_out_of_range_request_fails_at_input_parse(self) -> None:
        with pytest.raises(ValueError, match="between"):
            parse_scrolling_preview_input({"prompt": "whimsical forest", "character_heads_tall": 1})
