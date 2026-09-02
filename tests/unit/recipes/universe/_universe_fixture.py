"""Synthetic universe contracts for the recipe's offline tests.

Hand-built rather than generated: the evaluators are the thing under test, so
their inputs must be authored by a person who knows which rule each fixture is
meant to satisfy or break.
"""

from __future__ import annotations

from stage_gen.recipes.universe import models
from stage_gen.recipes.universe.ontology import CONCEPT_PURPOSES, DRY_WEATHER, MODES_BY_CLASS

SYNOPSIS_IDS = {"synopsis_p01", "synopsis_p02"}
REQUIREMENT_IDS = {"direction_extension_layer", "direction_visual_range"}


def _fact(
    fact_id: str,
    lineage: str = "explicit_source",
    evidence: list[str] | None = None,
    direction: list[str] | None = None,
) -> models.Fact:
    return models.Fact(
        fact_id=fact_id,
        claim=f"claim {fact_id}",
        lineage=lineage,
        basis="basis",
        evidence_ids=evidence if evidence is not None else ["synopsis_p01"],
        direction_requirement_ids=direction or [],
    )


def _entity(
    entity_id: str, primary: str, salience: str = "supporting", facets: list[str] | None = None
) -> models.Entity:
    return models.Entity(
        entity_id=entity_id,
        display_name=entity_id.replace("_", " ").title(),
        primary_class=primary,
        facets=facets or [],
        entity_kind="kind",
        salience=salience,
        summary=f"{entity_id} summary",
        how_it_works_or_lives="works",
        present_tension="tension",
        facts=[_fact(f"{entity_id}_f1"), _fact(f"{entity_id}_f2")],
    )


def _rel(rid: str, family: str, kind: str, source: str, target: str) -> models.Relationship:
    return models.Relationship(
        relationship_id=rid,
        relationship_family=family,
        relationship_kind=kind,
        source_entity_id=source,
        target_entity_id=target,
        summary="summary",
        temporal_scope="now",
        perspective="shared",
        lineage="explicit_source",
        evidence_ids=["synopsis_p01"],
        direction_requirement_ids=[],
    )


def make_proposal(entity_count: int = 12) -> models.UniverseProposal:
    classes = ["actor", "collective", "place", "thing", "kind", "system", "event", "idea"]
    entities = [
        _entity(f"e{i:02d}", classes[i % len(classes)], "major" if i < 3 else "supporting")
        for i in range(entity_count)
    ]
    rels = []
    families = [
        "spatial",
        "social_political",
        "material_functional",
        "causal_historical",
        "symbolic",
    ]
    kinds = ["located_in", "member_of", "uses", "caused", "represents"]
    for i in range(entity_count):
        j = (i + 1) % entity_count
        rels.append(
            _rel(
                f"r{i:02d}",
                families[i % 5],
                kinds[i % 5],
                entities[i].entity_id,
                entities[j].entity_id,
            )
        )
    markers = [
        models.IdentityMarker(
            marker_id=f"m_{e.entity_id}",
            owner_entity_id=e.entity_id,
            form="knot pattern",
            materials="rope",
            applied_use="on gates",
            meaning="belonging",
            limits="none",
            historical_origin="old",
            lineage="conservative_inference",
            evidence_ids=["synopsis_p02"],
            direction_requirement_ids=[],
            independently_admitted_thing_id=None,
        )
        for e in entities
        if e.primary_class == "collective" or (e.primary_class == "place" and e.salience == "major")
    ]
    return models.UniverseProposal(
        universe_id="test_universe",
        title="Test Universe",
        premise=_fact("universe_premise"),
        present_state=_fact("universe_present_state"),
        physical_ecological_rules=[_fact("rule_1")],
        institutional_tensions=[
            models.InstitutionalTension(
                tension_id=f"t{i}",
                summary="s",
                participant_entity_ids=["e00", "e01"],
                fact_ids=["e00_f1"],
                material_stakes="stakes",
                competing_legitimate_needs="needs",
            )
            for i in range(3)
        ],
        visual_observations=[
            models.VisualObservation(
                observation_id="poster_rig",
                category="thing",
                claim="a rig",
                confidence="high",
                canonical_status="evidence",
            )
        ],
        viewpoints=[
            models.Viewpoint(
                viewpoint_id="v1",
                display_name="Iri",
                summary="s",
                anchor_entity_ids=["e00"],
                initially_known="little",
                entry_question="why?",
            )
        ],
        entities=entities,
        relationships=rels,
        identity_markers=markers,
        direction_coverage=[
            models.DirectionCoverage(
                requirement_id=r, status="satisfied", evidence_ids=["e00"], note="n"
            )
            for r in sorted(REQUIREMENT_IDS)
        ],
        source_conflicts=[],
        unresolved_questions=["what next?"],
    )


def evaluate(proposal: models.UniverseProposal) -> models.ProposalEvaluation:
    return models.evaluate_proposal(
        proposal,
        universe_id="test_universe",
        synopsis_ids=SYNOPSIS_IDS,
        requirement_ids=REQUIREMENT_IDS,
        min_entities=8,
        max_entities=20,
    )


def make_plan(proposal: models.UniverseProposal) -> models.GalleryPlan:
    scales = ["intimate", "human", "architectural", "landscape"]
    times = ["day", "dawn", "dusk", "day", "night"]
    weathers = ["clear", "overcast", "wind", "fog", "rain", "clear", "snow"]
    settings = ["exterior", "interior", "threshold"]
    purposes = list(CONCEPT_PURPOSES)
    plans = []
    for i, entity in enumerate(proposal.entities):
        mode = MODES_BY_CLASS[entity.primary_class][0]
        weather = weathers[i % len(weathers)]
        plans.append(
            models.ConceptPlan(
                entity_id=entity.entity_id,
                concept_mode=mode,
                primary_purpose=purposes[i % len(purposes)],
                lesson_key=f"lesson_{i:02d}",
                audience_question="q?",
                visible_fact_ids=[entity.facts[0].fact_id],
                visible_relationship_ids=[],
                scene_premise="one moment",
                signature_motif=models.SignatureMotif(
                    action_verb=f"verb_{i % 9:02d}",
                    dominant_prop=f"prop_{i:02d}",
                    vantage=["eye_level", "low_angle", "high_angle", "aerial", "over_shoulder"][
                        i % 5
                    ],
                ),
                in_frame_contrast="the answered line hangs taut beside the ignored one gone slack",
                unique_contribution=f"unique {i}",
                scene_register=models.SceneRegister(
                    scale=scales[i % 4],
                    time_of_day=times[i % 5],
                    weather=weather,
                    weather_justification=(
                        "the scene sits in the open through the wet season crossing"
                        if weather not in DRY_WEATHER
                        else "dry"
                    ),
                    setting=settings[i % 3],
                    population=["solitary", "few", "crowd"][i % 3],
                    energy="working",
                ),
            )
        )
    return models.GalleryPlan(universe_id=proposal.universe_id, set_rationale="spread", plans=plans)


def entity_direction(entity_id: str, realization: str, extra: str = "") -> models.EntityDirection:
    return models.EntityDirection(
        entity_id=entity_id,
        primary_subject="a figure " + extra,
        action_beat=models.ActionBeat(
            agent="a", goal="g", obstacle="o", intervention="i", visible_state_change="c"
        ),
        immediate_environment="env",
        composition_and_camera="wide",
        visual_identity=models.VisualIdentity(
            silhouette="s",
            proportions="p",
            construction_logic="c",
            materials="m",
            color_placement="c",
            scale_anchor="a",
            wear_and_history="w",
            characteristic_motion_or_use="u",
            forbidden_substitutions=["castle"],
        ),
        register_realization=realization,
        continuity_notes="n",
        avoid=["readable text"],
    )
