"""Facing review criteria for actor strips."""

from __future__ import annotations

import pytest

from stage_gen.recipes.scrolling_preview.review_criteria import (
    ACTOR_FACING_ERROR_CODE,
    REQUIRED_SIDE_VIEW_FACING,
    ActorFacingError,
    ActorFacingVerdict,
    actor_facing_json_schema,
    actor_facing_prompt,
    evaluate_actor_facing,
    parse_actor_facing,
    reviews_facing,
)


def _verdict(
    facing: str, *, confident: bool = True, evidence: str = "eyes point that way"
) -> ActorFacingVerdict:
    return parse_actor_facing({"facing": facing, "confident": confident, "evidence": evidence})


class TestReviewedStages:
    @pytest.mark.parametrize(
        "stage",
        [
            "mob-idle-0",
            "mob-hurt-7",
            "character-master-strip-idle",
            "character-master-strip-run",
            "character-attack",
        ],
    )
    def test_side_view_strips_carry_a_facing_contract(self, stage: str) -> None:
        assert reviews_facing(stage) is True

    @pytest.mark.parametrize(
        "stage",
        [
            # Authored rear-facing on purpose, so it has no left/right contract to check.
            "character-climb",
            # Turnarounds show every side by definition.
            "character-concept",
            "mob-concept-3",
            "tileset",
            "items",
            "ladder",
            "portal",
        ],
    )
    def test_stages_without_a_facing_contract_are_not_reviewed(self, stage: str) -> None:
        assert reviews_facing(stage) is False


class TestVerdictEvaluation:
    def test_a_right_facing_strip_is_accepted_and_recorded(self) -> None:
        record = evaluate_actor_facing(_verdict("right", evidence="face points right"))
        assert record["actor_facing"] == "right"
        assert record["actor_facing_required"] == REQUIRED_SIDE_VIEW_FACING
        assert record["actor_facing_confident"] is True
        assert record["actor_facing_evidence"] == "face points right"

    def test_a_confident_left_facing_strip_is_rejected(self) -> None:
        with pytest.raises(ActorFacingError) as caught:
            evaluate_actor_facing(_verdict("left", evidence="snail head sits left of the shell"))
        error = caught.value
        assert error.code == ACTOR_FACING_ERROR_CODE
        assert error.facing == "left"
        assert "snail head sits left of the shell" in error.evidence
        assert error.as_dict()["code"] == ACTOR_FACING_ERROR_CODE

    def test_an_unconfident_reading_is_recorded_but_never_blocks(self) -> None:
        # Half a run's strips face the wrong way, so rejection has to be cheap to be worth it -
        # but a subject with no locatable front would otherwise fail forever.
        record = evaluate_actor_facing(_verdict("left", confident=False, evidence="unclear"))
        assert record["actor_facing"] == "left"
        assert record["actor_facing_confident"] is False

    @pytest.mark.parametrize("facing", ["front", "back", "indeterminate"])
    def test_non_side_views_are_left_to_the_deterministic_camera_check(self, facing: str) -> None:
        # raster_contracts measures mirror symmetry and already owns head-on detection; a second
        # opinion here would only add a way for the two to disagree.
        record = evaluate_actor_facing(_verdict(facing, evidence="viewed head-on"))
        assert record["actor_facing"] == facing


class TestReviewRequest:
    def test_the_prompt_never_reveals_the_expected_answer(self) -> None:
        # A reviewer told which way to expect stops producing evidence and starts confirming.
        prompt = actor_facing_prompt("a creature")
        lowered = prompt.lower()
        assert "should face" not in lowered
        assert "expected" not in lowered
        assert "must face" not in lowered

    def test_the_prompt_separates_the_subject_from_the_strip_reading_order(self) -> None:
        # Frames always advance rightwards; that is not the subject's facing.
        prompt = actor_facing_prompt("a creature").lower()
        assert "not for the strip" in prompt

    def test_the_schema_is_strict_and_closed(self) -> None:
        schema = actor_facing_json_schema()
        properties = schema["properties"]
        assert isinstance(properties, dict)
        assert set(properties) == {"facing", "confident", "evidence"}


class TestPromptAndGateAgree:
    """The instruction and the check must name the same direction.

    These drifted before: `character-attack` carried a bare one-liner while its neighbours
    carried the full cell discipline, and the provider duly painted template borders into it.
    """

    def test_the_generation_directive_asks_for_the_facing_the_review_requires(self) -> None:
        from stage_gen.recipes.scrolling_preview.executor import _side_view_facing_directive

        directive = _side_view_facing_directive().lower()
        assert f"faces the {REQUIRED_SIDE_VIEW_FACING} edge" in directive
        opposite = "left" if REQUIRED_SIDE_VIEW_FACING == "right" else "right"
        assert f"never draw it facing {opposite}" in directive

    def test_the_directive_separates_subject_facing_from_sheet_reading_order(self) -> None:
        # Frames always advance rightwards. Read as one instruction, "facing right" and "frames
        # run left to right" are easy to conflate, and conflating them produces the defect.
        from stage_gen.recipes.scrolling_preview.executor import _side_view_facing_directive

        assert "not the sheet" in _side_view_facing_directive().lower()

    def test_every_reviewed_character_and_mob_strip_carries_the_directive(self) -> None:
        from stage_gen.recipes.scrolling_preview.executor import (
            _character_strip_prompt,
            _mob_strip_prompt,
            _side_view_facing_directive,
        )

        directive = _side_view_facing_directive()
        for state in ("idle", "walk", "run", "jump", "crawl", "attack"):
            assert directive in _character_strip_prompt(state), state
        for state in ("idle", "hurt"):
            assert directive in _mob_strip_prompt("a creature", state), state


class TestContainmentKeepsEqualBilling:
    """Containment is as binding as facing, and regressed once when it stopped reading that way.

    Crossing a cell boundary fails `scrolling-grid-cross-cell-isolation-v1`, which is
    unrecoverable and burns all six provider attempts. When facing was promoted to a leading
    labelled directive, containment was left as a trailing sub-clause and `character-attack` -
    the one pose with a horizontally extended weapon - started failing isolation where it had
    passed.
    """

    def test_both_contracts_lead_as_labelled_directives(self) -> None:
        from stage_gen.recipes.scrolling_preview.executor import _character_strip_prompt

        prompt = _character_strip_prompt("attack")
        assert "FACING, before anything else:" in prompt
        assert "CELL CONTAINMENT, equally binding:" in prompt

    def test_containment_names_the_extended_reach_case_outright(self) -> None:
        from stage_gen.recipes.scrolling_preview.executor import _cell_containment_directive

        directive = _cell_containment_directive(
            grid="4x1", subject="frame", appendages="weapons"
        ).lower()
        assert "thrust weapon" in directive
        assert "scale that subject down" in directive
        # A sheet of separate subjects, never one scene arranged over a grid. The obstacles
        # sheet failed on every seam at once for exactly that reason.
        assert "never one scene" in directive

    def test_every_strip_prompt_carries_containment(self) -> None:
        from stage_gen.recipes.scrolling_preview.executor import (
            _character_strip_prompt,
            _mob_strip_prompt,
        )

        for state in ("idle", "walk", "run", "jump", "crawl", "attack"):
            assert "CELL CONTAINMENT" in _character_strip_prompt(state), state
        for state in ("idle", "hurt"):
            assert "CELL CONTAINMENT" in _mob_strip_prompt("a creature", state), state


class TestGridSheetsCarryContainmentToo:
    """Obstacles and items are grid sheets with the same failure mode as the strips.

    Both asked for "isolated" cells without saying what isolation means, and `obstacles-1`
    exhausted twelve provider attempts across two runs returning one connected scene arranged
    over a 2x4 grid - content crossing every vertical and horizontal seam at once.
    """

    def test_the_directive_adapts_to_a_two_row_sheet(self) -> None:
        from stage_gen.recipes.scrolling_preview.executor import _cell_containment_directive

        directive = _cell_containment_directive(
            grid="2-row x 4-column", subject="prop", appendages="branches"
        )
        assert "strict 2-row x 4-column equal cells" in directive
        assert "each prop's whole silhouette" in directive
