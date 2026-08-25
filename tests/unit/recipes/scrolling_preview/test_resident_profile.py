"""The resident render profile: a still is not a mob strip with fewer frames."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from stage_gen.components.game_contract import (
    GameContract,
    ResidentDirection,
    load_game_contract,
    load_game_vocabulary,
)
from stage_gen.recipes.scrolling_preview import executor as executor_module
from stage_gen.recipes.scrolling_preview.game import (
    GAME_DIRECTION_PREFIX,
    append_game_art_direction_once,
    assert_projection_supported,
    game_art_direction_prompt,
    game_contract_tag_suffix,
    resident_render_plan,
)
from stage_gen.recipes.scrolling_preview.proportion import evaluate_actor_proportion
from stage_gen.recipes.scrolling_preview.raster_contracts import (
    RESIDENT_STILL_HEIGHT,
    RESIDENT_STILL_WIDTH,
    contract_for_runtime_role,
    contract_for_stage,
)
from stage_gen.recipes.scrolling_preview.resident import (
    DirectedVillageSpec,
    directed_village_spec_json_schema,
    resident_still_subject,
    validate_directed_roster_vocabulary,
)
from stage_gen.recipes.scrolling_preview.review_criteria import (
    REQUIRED_SIDE_VIEW_FACING,
    REQUIRED_STILL_FACING,
    actor_facing_prompt,
    evaluate_actor_facing,
    is_resident_still,
    parse_actor_facing,
    required_facing,
    reviews_facing,
)
from stage_gen.recipes.scrolling_preview.scale_reference import measures_scale_reference

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
SHIPPED_REF = "library/games/whimsical-storybook-fantasy/game.toml"
SHIPPED_PATH = REPOSITORY_ROOT / SHIPPED_REF
VOCABULARY = load_game_vocabulary().vocabulary


def _npc(index: int, stance: str, holding: str, body_kind: str = "human") -> dict[str, Any]:
    return {
        "role_label": f"role-{index}",
        "name": f"Name{index}",
        "body_plan": f"wiry and quick, trade {index}",
        "brief": f"brief {index}",
        "greeting": "Hello.",
        "remark": "Fine weather.",
        "farewell": "Safe travels.",
        "body_kind": body_kind,
        "stance": stance,
        "holding": holding,
    }


def _roster(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "Hollowbrook",
        "one_liner": "A quiet market square.",
        "narrative": "A crossing where the road widens into stalls.",
        "fixtures_theme": "market stalls",
        "npcs": [
            _npc(0, "leaning_on_counter", "bread_loaf"),
            _npc(1, "arms_crossed", "hammer", "dwarf"),
            _npc(2, "kneeling_at_crate", "basket"),
            _npc(3, "standing_at_ease", "lantern", "elf"),
        ],
        "fixtures": [{"name": f"fixture-{i}", "brief": f"brief {i}"} for i in range(8)],
    }
    payload.update(overrides)
    return payload


def _game() -> GameContract:
    return load_game_contract(SHIPPED_PATH)


class TestDirectedRoster:
    def test_a_directed_roster_carries_a_body_a_pose_and_something_in_the_hands(self) -> None:
        spec = DirectedVillageSpec.model_validate(_roster())
        validate_directed_roster_vocabulary(spec, VOCABULARY)
        assert [npc.stance for npc in spec.npcs] == [
            "leaning_on_counter",
            "arms_crossed",
            "kneeling_at_crate",
            "standing_at_ease",
        ]
        assert [npc.body_kind for npc in spec.npcs] == ["human", "dwarf", "human", "elf"]

    def test_two_residents_doing_the_same_thing_read_as_one_resident_drawn_twice(self) -> None:
        roster = _roster()
        roster["npcs"][2] = _npc(2, "leaning_on_counter", "bread_loaf")
        with pytest.raises(ValueError, match="differ in stance or held prop"):
            DirectedVillageSpec.model_validate(roster)

    def test_four_humans_are_an_ordinary_village_not_an_error(self) -> None:
        # Forcing four species onto a market square produces a menagerie, not a town.
        roster = _roster()
        for npc in roster["npcs"]:
            npc["body_kind"] = "human"
        DirectedVillageSpec.model_validate(roster)

    def test_the_prose_no_longer_has_to_smuggle_an_anatomical_noun(self) -> None:
        # `body_kind` names the anatomy from a reviewed list, so the rule that burned six
        # provider attempts on the first live village no longer applies to a directed roster.
        roster = _roster()
        for index, npc in enumerate(roster["npcs"]):
            npc["body_plan"] = f"steady and weathered, keeper of stall {index}"
        DirectedVillageSpec.model_validate(roster)

    def test_a_resident_may_not_have_a_body_no_person_has(self) -> None:
        roster = _roster()
        roster["npcs"][0]["body_kind"] = "quadruped"
        with pytest.raises(ValueError, match="not a body a village resident has"):
            validate_directed_roster_vocabulary(
                DirectedVillageSpec.model_validate(roster), VOCABULARY
            )

    def _npc_properties(self, **kwargs: bool) -> dict[str, Any]:
        schema = directed_village_spec_json_schema(VOCABULARY, **kwargs)
        definitions = cast(dict[str, Any], schema["$defs"])
        return cast(dict[str, Any], definitions["DirectedVillageNpc"]["properties"])

    def test_the_request_schema_offers_the_vocabulary_as_enums(self) -> None:
        npc = self._npc_properties(allow_pose=True, allow_held_prop=True)
        assert npc["body_kind"]["enum"] == list(VOCABULARY.people_body_kinds)
        assert npc["stance"]["enum"] == list(VOCABULARY.stance_names)
        assert npc["holding"]["enum"] == list(VOCABULARY.prop_names)
        assert "minLength" not in npc["stance"]

    def test_turning_poses_off_narrows_the_enum_rather_than_dropping_the_field(self) -> None:
        # A one-member enum states the intent more plainly than an absent field: "everyone
        # stands at ease" rather than "decide for yourself".
        npc = self._npc_properties(allow_pose=False, allow_held_prop=False)
        assert npc["stance"]["enum"] == ["standing_at_ease"]
        assert npc["holding"]["enum"] == ["none"]

    def test_the_subject_leads_with_anatomy_and_ends_with_the_action(self) -> None:
        spec = DirectedVillageSpec.model_validate(_roster())
        subject = resident_still_subject(spec.npcs[0], vocabulary=VOCABULARY)
        assert subject.startswith(VOCABULARY.body("human").anatomy)
        assert VOCABULARY.stance("leaning_on_counter").direction in subject
        assert VOCABULARY.prop("bread_loaf").direction in subject

    def test_empty_hands_are_stated_by_saying_nothing_about_hands(self) -> None:
        roster = _roster()
        roster["npcs"][0] = _npc(0, "hands_on_hips", "none")
        spec = DirectedVillageSpec.model_validate(roster)
        subject = resident_still_subject(spec.npcs[0], vocabulary=VOCABULARY)
        assert VOCABULARY.prop("none").direction not in subject
        assert VOCABULARY.stance("hands_on_hips").direction in subject


class TestStillRenderContract:
    def test_a_still_is_one_cell_and_a_strip_is_still_four(self) -> None:
        still = contract_for_stage("village-npc-2-still")
        assert still is not None
        assert (still.rows, still.columns) == (1, 1)
        assert still.fixed_side_view_frames is False
        assert still.cell_size(RESIDENT_STILL_WIDTH, RESIDENT_STILL_HEIGHT) == (800, 1200)
        strip = contract_for_stage("village-npc-2-idle")
        assert strip is not None
        assert (strip.rows, strip.columns) == (1, 4)
        assert strip.fixed_side_view_frames is True

    def test_the_producer_and_the_runtime_agree_on_a_still(self) -> None:
        assert contract_for_runtime_role("village-npc-2-still") == contract_for_stage(
            "village-npc-2-still"
        )

    def test_a_still_halves_the_sheet_and_doubles_the_drawn_figure(self) -> None:
        # The strip was 2400x800 for four 600x800 cells, of which the runtime drew one. Pinned
        # because both halves of the trade are what justify the shape change.
        strip_sheet = 2400 * 800
        strip_drawn_cell = 600 * 800
        still = RESIDENT_STILL_WIDTH * RESIDENT_STILL_HEIGHT
        assert still * 2 == strip_sheet
        assert still == strip_drawn_cell * 2

    def test_the_turnaround_is_not_mistaken_for_a_still(self) -> None:
        assert is_resident_still("village-npc-concept-0") is False
        assert is_resident_still("village-npc-0-still") is True
        concept = contract_for_stage("village-npc-concept-0")
        assert concept is not None and concept.columns == 3


class TestStillReview:
    def test_a_still_is_reviewed_against_the_viewer_and_a_strip_against_the_edge(self) -> None:
        assert reviews_facing("village-npc-0-still") is True
        assert required_facing("village-npc-0-still") == REQUIRED_STILL_FACING
        assert required_facing("village-npc-0-idle") == REQUIRED_SIDE_VIEW_FACING

    @pytest.mark.parametrize("facing", ["left", "right", "back"])
    def test_a_resident_turned_away_is_rejected(self, facing: str) -> None:
        # `back` matters most and is invisible to the deterministic symmetry check, which reads
        # a figure seen from behind as a perfectly good front view.
        verdict = parse_actor_facing(
            {"facing": facing, "confident": True, "evidence": "the eyes point away"}
        )
        with pytest.raises(ValueError, match="stand turned away"):
            evaluate_actor_facing(verdict, required=REQUIRED_STILL_FACING)

    @pytest.mark.parametrize(
        ("facing", "confident"), [("front", True), ("indeterminate", True), ("left", False)]
    )
    def test_a_front_or_unresolved_reading_passes(self, facing: str, confident: bool) -> None:
        record = evaluate_actor_facing(
            parse_actor_facing(
                {"facing": facing, "confident": confident, "evidence": "the eyes point out"}
            ),
            required=REQUIRED_STILL_FACING,
        )
        assert record["actor_facing_required"] == REQUIRED_STILL_FACING

    def test_the_side_view_gate_is_untouched(self) -> None:
        # `front` and `back` are still passed for a strip: a mob roster contains subjects with
        # no locatable front, and a strict rule would fail them forever.
        for facing in ("front", "back", "right"):
            evaluate_actor_facing(
                parse_actor_facing({"facing": facing, "confident": True, "evidence": "beak"})
            )
        with pytest.raises(ValueError, match="render backwards"):
            evaluate_actor_facing(
                parse_actor_facing({"facing": "left", "confident": True, "evidence": "beak"})
            )

    def test_the_reviewer_is_told_what_it_is_actually_looking_at(self) -> None:
        still = actor_facing_prompt("a game character", still=True)
        strip = actor_facing_prompt("a game character")
        assert "single still figure" in still
        assert "four-frame" not in still
        assert "frames advance rightwards" not in still
        assert "four-frame side-view animation strip" in strip

    def test_a_still_is_measured_and_build_gated_exactly_as_a_strip_is(self) -> None:
        # The two checks that decide whether a resident renders at the right size are kept.
        assert measures_scale_reference("village-npc-0-still") is True
        assert executor_module._holds_run_build("village-npc-0-still") is True
        assert executor_module._holds_run_build("mob-idle-0") is False


class TestGameDirection:
    def test_the_art_direction_clause_renders_the_authored_keywords_in_order(self) -> None:
        contract = _game()
        clause = game_art_direction_prompt(contract)
        assert clause.startswith(GAME_DIRECTION_PREFIX)
        assert ", ".join(contract.style.keywords) in clause
        assert clause.rstrip().endswith(".")
        for avoidance in contract.style.avoid:
            assert avoidance in clause

    def test_the_clause_is_appended_once_and_a_second_game_is_refused(self) -> None:
        contract = _game()
        once = append_game_art_direction_once("Draw a cart.", contract)
        assert append_game_art_direction_once(once, contract) == once
        assert once.count(GAME_DIRECTION_PREFIX) == 1
        with pytest.raises(ValueError, match="different or malformed"):
            append_game_art_direction_once(
                f"{once}\n\n{GAME_DIRECTION_PREFIX}something else.", contract
            )

    def test_a_game_drawn_for_another_camera_is_refused_by_name(self) -> None:
        contract = _game()
        assert_projection_supported(contract)
        rewritten = contract.model_copy(
            update={"camera": contract.camera.model_copy(update={"projection": "top_down_2d"})}
        )
        with pytest.raises(ValueError, match="top_down_2d"):
            assert_projection_supported(rewritten)

    def test_the_tag_moves_when_the_vocabulary_moves(self) -> None:
        # The contract names `warm dusk palette`; the vocabulary decides what that becomes in a
        # prompt. A tag keyed on the contract alone would serve artwork drawn under wording that
        # no longer exists.
        binding = {
            "schema_version": 1,
            "kind": "game-contract-binding-v1",
            "ref": SHIPPED_REF,
            "source_sha256": "a" * 64,
        }
        first = game_contract_tag_suffix(binding, vocabulary_sha256="a" * 64)
        second = game_contract_tag_suffix(binding, vocabulary_sha256="b" * 64)
        assert first != second
        assert first.startswith("game-v1-")
        # Keyed on the ref rather than the source digest, matching the character profile:
        # revising a game in place refreshes a run rather than stranding it.
        revised = {**binding, "source_sha256": "c" * 64}
        assert game_contract_tag_suffix(revised, vocabulary_sha256="a" * 64) == first

    def test_the_shipped_game_asks_for_stills_at_one_frame(self) -> None:
        plan = resident_render_plan(_game().cast.resident)
        assert (plan.animation, plan.orientation, plan.frames) == ("still", "front", 1)
        assert plan.is_still is True
        strip = resident_render_plan(
            ResidentDirection.model_validate(
                {"body_kind_default": "human", "orientation": "side", "animation": "strip"}
            )
        )
        assert (strip.animation, strip.frames) == ("strip", 4)

    def test_a_resident_drawn_to_the_game_build_passes_the_gate_a_stray_one_fails(self) -> None:
        # The measured numbers are the live ones recorded in `proportion.py`: a village asked
        # for two heads returned residents at 2.54-3.34 and one elf at 7.47.
        requested = _game().heads_for("elf")
        assert requested == 2.0
        evaluate_actor_proportion(
            requested_heads=requested, sprite_height_px=305.0, head_extent_px=100.0
        )
        with pytest.raises(ValueError, match="scrolling-actor-proportion-v1"):
            evaluate_actor_proportion(
                requested_heads=requested, sprite_height_px=747.0, head_extent_px=100.0
            )
