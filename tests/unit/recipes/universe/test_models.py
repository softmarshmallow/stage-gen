"""The deterministic evaluators: what a universe and its gallery plan must satisfy.

These run inside the structured service's single retry owner, so every rule
here is a rule a model gets six attempts to meet. That is why the split between
blocking errors and advisory warnings matters more than usual: a hint a model
cannot self-correct from becomes six burnt attempts and an unchanged answer.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from stage_gen.recipes.universe import models
from stage_gen.recipes.universe.medium import ANIME_2D, LIVE_ACTION
from tests.unit.recipes.universe._universe_fixture import (
    entity_direction,
    evaluate,
    make_plan,
    make_proposal,
)


def test_proposal_evaluator_accepts_the_fixture_universe() -> None:
    assert evaluate(make_proposal())["status"] == "pass"


def test_proposal_evaluator_rejects_direction_as_evidence_and_dangling_references() -> None:
    """The expansion direction is rationale; citing it as evidence is the classic slip."""

    proposal = make_proposal()
    proposal.entities[0].facts[0].evidence_ids = ["direction_visual_range"]
    proposal.relationships[0].target_entity_id = "not_an_entity"
    errors = evaluate(proposal)["errors"]
    assert any("evidence" in error for error in errors)
    assert any("not_an_entity" in error for error in errors)


def test_proposal_evaluator_rejects_a_disconnected_graph() -> None:
    proposal = make_proposal()
    proposal.relationships = proposal.relationships[:2]
    errors = evaluate(proposal)["errors"]
    assert any("components; expected 1" in error for error in errors)
    assert any("entities without relationships" in error for error in errors)


def test_plan_evaluator_accepts_a_diverse_set() -> None:
    proposal = make_proposal()
    assert models.evaluate_plan(make_plan(proposal), proposal)["status"] == "pass"


def test_plan_evaluator_rejects_repeated_motifs_and_missing_contrast() -> None:
    """The motif axis exists because four entries once shared one picture."""

    proposal = make_proposal()
    plan = make_plan(proposal)
    plan.plans[1].signature_motif = models.SignatureMotif(
        action_verb=plan.plans[0].signature_motif.action_verb,
        dominant_prop=plan.plans[0].signature_motif.dominant_prop,
        vantage="eye_level",
    )
    system_entry = next(
        entry
        for entry in plan.plans
        if proposal.entity(entry.entity_id).primary_class in {"system", "idea"}
    )
    system_entry.in_frame_contrast = "none"
    errors = models.evaluate_plan(plan, proposal)["errors"]
    assert any("signature motif" in error for error in errors)
    assert any("in_frame_contrast" in error for error in errors)


def test_plan_evaluator_rejects_duplicate_registers_and_clustered_rain() -> None:
    proposal = make_proposal()
    plan = make_plan(proposal)
    for entry in plan.plans:
        entry.scene_register = plan.plans[0].scene_register.model_copy()
    errors = models.evaluate_plan(plan, proposal)["errors"]
    assert any("register" in error for error in errors)


def test_plan_evaluator_checks_scale_and_interior_without_an_overused_verb() -> None:
    """A set-level obligation the register prompt states unconditionally.

    The spike nested these two checks inside the over-used-verb branch, so a
    gallery only had to spread its scales once it had already failed something
    else. Every plan the spike ever admitted passed this rule by accident.
    """

    proposal = make_proposal()
    plan = make_plan(proposal)
    for entry in plan.plans:
        entry.scene_register.scale = "human"
        entry.scene_register.setting = "exterior"
    verbs = {entry.signature_motif.action_verb for entry in plan.plans}
    assert len(verbs) == len(plan.plans) or len(verbs) > 3, "no verb may be over-used here"
    errors = models.evaluate_plan(plan, proposal)["errors"]
    assert any("scale intimate is unused" in error for error in errors)
    assert any("no interior scene planned" in error for error in errors)
    assert not any("action_verb used by more than" in error for error in errors)


def test_plan_evaluator_rejects_a_mode_its_class_cannot_take() -> None:
    proposal = make_proposal()
    plan = make_plan(proposal)
    place = next(
        entry for entry in plan.plans if proposal.entity(entry.entity_id).primary_class == "place"
    )
    place.concept_mode = "character_portrait"  # type: ignore[assignment]
    errors = models.evaluate_plan(plan, proposal)["errors"]
    assert any("mode character_portrait invalid for place" in error for error in errors)


def test_plan_evaluator_rejects_repeated_lesson_keys() -> None:
    proposal = make_proposal()
    plan = make_plan(proposal)
    plan.plans[1].lesson_key = plan.plans[0].lesson_key
    assert any("lesson_key" in error for error in models.evaluate_plan(plan, proposal)["errors"])


def test_direction_acceptance_is_identity_only() -> None:
    """Hard rejection costs six attempts; only the binding is worth that price."""

    proposal = make_proposal()
    plan = make_plan(proposal).plans[0]
    direction = entity_direction(plan.entity_id, "a dry clear working day at eye level")
    assert models.evaluate_direction(direction, plan, ANIME_2D) == []
    foreign = entity_direction("some_other_entity", "a dry clear working day")
    assert models.evaluate_direction(foreign, plan, ANIME_2D) != []


def test_wet_mentions_ignore_negations_and_substrings() -> None:
    """ "rain" matched inside "restrained" for a whole gallery run once."""

    assert models.wet_mentions("the restrained crew crossed the terrain") == []
    assert models.wet_mentions("no rain reaches the deck") == []
    assert models.wet_mentions("rain beads on the rail") == ["rain"]


def test_direction_warnings_flag_medium_and_register_drift() -> None:
    proposal = make_proposal()
    plan = make_plan(proposal).plans[0]
    plan.scene_register.weather = "clear"
    direction = entity_direction(
        plan.entity_id, "rain sheets across the deck", extra="shot on 35mm film stock"
    )
    warnings = models.direction_warnings(direction, plan, ANIME_2D)
    assert any("rain" in warning or "wet" in warning for warning in warnings)
    assert any("film stock" in warning for warning in warnings)
    assert models.direction_warnings(direction, plan, LIVE_ACTION) != warnings


def test_image_review_verdict_must_agree_with_its_grades() -> None:
    with pytest.raises(ValidationError):
        models.ImageReview(
            review_id="universe_independent_image_review",
            entity_id="e00",
            artifact_sha256="0" * 64,
            entity_identity="fail",
            action_legibility="pass",
            medium_fidelity="pass",
            register_fidelity="pass",
            readable_text_absent="pass",
            explanatory_form_absent="pass",
            technical_quality="pass",
            verdict="admit",
            blocking_findings=[],
            advisory_findings=[],
            what_the_image_teaches="nothing",
        )


def test_sample_ledger_refuses_a_negative_draw() -> None:
    with pytest.raises(ValidationError):
        models.SampleLedger(
            schema_version=1,
            kind="universe-sample-ledger-v1",
            universe_id="test_universe",
            samples={"e00": -1},
        )


def test_census_bounds_must_be_ordered() -> None:
    with pytest.raises(ValidationError):
        models.Census(min_entities=10, max_entities=4)


def test_proposal_evaluator_binds_the_universe_id() -> None:
    proposal = make_proposal()
    proposal.universe_id = "another_universe"
    assert any("universe_id" in error for error in evaluate(proposal)["errors"])


def test_only_declared_synopsis_ids_may_be_cited_as_evidence() -> None:
    proposal = make_proposal()
    proposal.entities[1].facts[0].evidence_ids = ["synopsis_p99"]
    errors = evaluate(proposal)["errors"]
    assert any("synopsis_p99" in error for error in errors)
