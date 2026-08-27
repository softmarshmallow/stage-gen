"""The deterministic build gate: a sheet drawn to a different head count than the run asked for.

Separate from the facing review on purpose. Facing needs a vision model because a silhouette does
not locate a face; the drawn build is arithmetic over two numbers that already exist, so it is a
gate that runs on every held sheet rather than a review that samples one.
"""

from __future__ import annotations

import pytest

import stage_gen.recipes.scrolling_preview.executor as executor_module
from stage_gen.recipes.scrolling_preview.proportion import (
    ACTOR_PROPORTION_ERROR_CODE,
    PROPORTION_TOLERANCE_FACTOR,
    ActorProportionError,
    evaluate_actor_proportion,
    measured_heads_tall,
)

#: Measured on the first village generated with the proportion directive in place, against a
#: requested build of two. Three residents landed in range; the elf ignored the directive and was
#: drawn as a realistic adult. The runtime matches heads, so she would have rendered about three
#: and a half times the player's height with every other contract passing.
_LIVE_RUN = (
    ("player", 460, 223.5, 2.06, True),
    ("baker", 510, 200.8, 2.54, True),
    ("smith", 526, 172.0, 3.06, True),
    ("cartwright", 611, 183.2, 3.34, True),
    ("elf herbalist", 592, 79.2, 7.47, False),
)


class TestMeasurement:
    @pytest.mark.parametrize(("label", "height", "head", "expected", "_ok"), _LIVE_RUN)
    def test_the_drawn_build_is_recovered_from_two_numbers_already_on_hand(
        self, label: str, height: int, head: float, expected: float, _ok: bool
    ) -> None:
        assert measured_heads_tall(sprite_height_px=height, head_extent_px=head) == pytest.approx(
            expected, abs=0.01
        ), label

    @pytest.mark.parametrize(("height", "head"), [(0, 100.0), (-1, 100.0), (100, 0.0), (100, -2.0)])
    def test_a_degenerate_measurement_is_refused_rather_than_divided(
        self, height: int, head: float
    ) -> None:
        with pytest.raises(ValueError):
            measured_heads_tall(sprite_height_px=height, head_extent_px=head)


class TestGate:
    @pytest.mark.parametrize(("label", "height", "head", "measured", "accepted"), _LIVE_RUN)
    def test_the_gate_reproduces_the_live_runs_verdicts(
        self, label: str, height: int, head: float, measured: float, accepted: bool
    ) -> None:
        """The one case that matters is separated from the three that do not."""

        if accepted:
            record = evaluate_actor_proportion(
                requested_heads=2, sprite_height_px=height, head_extent_px=head
            )
            assert record["measured_heads_tall"] == pytest.approx(measured, abs=0.01)
            return
        with pytest.raises(ActorProportionError) as caught:
            evaluate_actor_proportion(
                requested_heads=2, sprite_height_px=height, head_extent_px=head
            )
        assert caught.value.code == ACTOR_PROPORTION_ERROR_CODE
        assert caught.value.measured == pytest.approx(measured, abs=0.01)
        assert caught.value.requested == 2

    def test_the_bound_is_symmetric_because_either_direction_renders_wrong(self) -> None:
        """A realistic run handed a chibi fails by the same mechanism as the reverse."""

        with pytest.raises(ActorProportionError):
            evaluate_actor_proportion(requested_heads=6, sprite_height_px=200, head_extent_px=100.0)

    @pytest.mark.parametrize("factor", [0.5, 1.0])
    def test_a_tolerance_that_cannot_admit_anything_is_refused(self, factor: float) -> None:
        with pytest.raises(ValueError, match="must exceed 1"):
            evaluate_actor_proportion(
                requested_heads=2,
                sprite_height_px=460,
                head_extent_px=223.5,
                tolerance_factor=factor,
            )

    def test_the_boundary_is_inclusive_on_both_sides(self) -> None:
        for height in (
            2 * PROPORTION_TOLERANCE_FACTOR * 100.0,
            2 / PROPORTION_TOLERANCE_FACTOR * 100.0,
        ):
            evaluate_actor_proportion(
                requested_heads=2, sprite_height_px=height, head_extent_px=100.0
            )

    def test_the_record_states_the_range_it_judged_against(self) -> None:
        record = evaluate_actor_proportion(
            requested_heads=2, sprite_height_px=460, head_extent_px=223.5
        )
        assert record["accepted_range"] == [1.0, 4.0]
        assert record["requested_heads_tall"] == 2


class TestHeldStages:
    @pytest.mark.parametrize(
        "stage",
        ["character-attack", "character-climb", "village-npc-0-idle", "village-npc-3-idle"],
    )
    def test_the_cast_is_held_to_the_runs_build(self, stage: str) -> None:
        assert executor_module._holds_run_build(stage)

    @pytest.mark.parametrize(
        "stage",
        [
            "mob-idle-0",
            "mob-hurt-2",
            "village-npc-concept-0",
            "character-concept",
            "village-fixtures",
            "character-master-strip-idle",
        ],
    )
    def test_creatures_turnarounds_and_sheets_are_not(self, stage: str) -> None:
        """A creature's build is its own, and the run's head count describes its cast.

        The master strips are excluded for the same reason `measures_scale_reference` excludes
        them: they are re-sliced before publication, so `post-split` owns their measurement and
        this gate would judge an artifact the runtime never loads.
        """

        assert not executor_module._holds_run_build(stage)
