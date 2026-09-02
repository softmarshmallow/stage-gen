"""Every instruction the universe recipe sends, composed at plan time.

The prose here is tuned: fifteen recorded runs moved these words, and most
of the rules in them exist because a specific run failed without them. It is
carried over verbatim from the spike that earned it. Only the plumbing
changed — the builders take plain values rather than a package object, so
this module knows nothing about how a package is resolved.

Each node's card carries its full static prompt, so the plan states exactly
what every node will be told; the handlers append only the run's own data.
"""

from __future__ import annotations

# The instruction blocks below are tuned prose. Rewrapping them to satisfy the
# line limit would risk changing the bytes a model is sent, which is a
# correctness question, not a style one.
# ruff: noqa: E501
import re
from typing import TYPE_CHECKING

from stage_gen.recipes.universe.medium import (
    SHARED_LOCAL_WEATHER,
    SHARED_OUTPUT_FORM,
    SHARED_STAGING_RULE,
    MediumContract,
)
from stage_gen.recipes.universe.models import EntityDirection
from stage_gen.recipes.universe.ontology import ONTOLOGY_PROMPT, REGISTER_PROMPT

if TYPE_CHECKING:
    from collections.abc import Mapping


def compact_words(value: str, *, max_words: int) -> str:
    compacted = " ".join(value.split())
    words = compacted.split(" ")
    if len(words) <= max_words:
        return compacted
    selected: list[str] = []
    used = 0
    for sentence in re.split(r"(?<=[.!?])\s+", compacted):
        n = len(sentence.split(" "))
        if used + n > max_words:
            break
        selected.append(sentence)
        used += n
    if selected:
        return " ".join(selected)
    prefix = " ".join(words[:max_words]).rstrip(",;:-")
    return prefix if prefix.endswith((".", "!", "?")) else f"{prefix}."


def proposal_instructions(
    *, title: str, universe_id: str, min_entities: int, max_entities: int
) -> str:
    return f"""Create one complete expanded universe proposal for "{title}" from the attached approved poster, the synopsis, and the expansion direction that follow.

{ONTOLOGY_PROMPT}

CENSUS
- Set universe_id exactly to {universe_id}. Emit between {min_entities} and {max_entities} entities. The distribution across classes must be irregular and honest: choose what this world needs, not a quota. A large universe still needs several systems, at least two events, at least two ideas, and at least two kinds unless the world truly lacks them.
- Every entity gets two to four concise lineaged facts, a summary a cold reader understands, a how_it_works_or_lives paragraph, and a present_tension sentence. Every entity takes part in at least one relationship. Emit at least as many relationships as entities and at most three times as many, spanning at least four relationship families. The graph must be ONE connected component: before returning, walk the relationships and confirm every entity can reach every other; a small cluster linked only to itself (for example one actor and the collective they belong to) fails. Every actor connects to a place and to at least one non-actor class; every collective connects to a place or a system it operates in.
- Give every collective and every major place a culturally grounded identity marker record with correct lineage. A marker whose form is invented uses generated_extension and cites a direction id.
- Emit one or more audience viewpoints, at least three institutional tensions with material stakes on each side, typed poster observations (ids prefixed poster_), source conflicts where the poster and synopsis disagree, direction coverage for every requirement id exactly once, citing evidence_ids copied byte-for-byte from ids this proposal emits (entity, fact, relationship, marker, tension, viewpoint, or poster observation ids; never a field name such as relationships, never a paraphrased or re-prefixed id), and unresolved questions the source leaves open.
- Fact and relationship evidence_ids may contain only synopsis paragraph ids and poster observation ids with canonical_status evidence. Direction requirement ids appear only in direction_requirement_ids.
- Elaboration changes lineage: a fact is explicit_source only when every specific in its claim is stated by the cited paragraph. The moment a claim adds a category, mechanism, custom, practice, number, or name the synopsis does not state, the whole fact becomes conservative_inference (if the synopsis implies it) or generated_extension (if the direction motivates it). Split a sourced core and an invented elaboration into two facts rather than blending them under explicit_source.
- Lineage honesty: a detail you invent for texture (a marker's colour, a custom, a tool's construction) is generated_extension with a direction id, or conservative_inference when the synopsis implies it; it is never explicit_source. A causal relationship_kind (caused, resulted_in, prevents) requires the synopsis to state that cause; where the synopsis leaves a cause open, use depends_on or a hedged summary with conservative_inference and keep the open cause in unresolved_questions.
- One record per practice: never emit both a collective and a separate system for the same craft or trade (a guild and its craft, a gleaner band and gleaning, riggers and rigging). Choose one: either the collective, whose how_it_works_or_lives explains the practice, or the system, whose practitioners appear as relationships to actors, collectives, and places. A physical infrastructure (a water system, a road network) and the workforce that runs it may both exist only when the workforce record is about politics, livelihood, and authority and never restates the infrastructure's operation.
- Taxonomic relationships (instance_of, variant_of, descended_from) link an individual or subtype to a kind; an actor belonging to a collective is member_of, never instance_of. An assembly or installation is not an instance of the kind of its parts.
- Every relationship must read as a true sentence "<source> <relationship_kind> <target>" with the endpoints' classes: a system is not carried, made, or owned; a place does not use a tool; a kind does not act. If the sentence is false or awkward, choose another kind or drop the edge.
- The festival calendar named in the direction must be a developed subject: when the Unmooring Festival falls, what it marks, who runs it, and what it wrongly assumed about Thalen.
- Do not add gameplay statistics, decorative creatures, generic magic, or franchise-shaped filler. Do not describe any image; concept planning happens later.
Return only the strict schema object."""


def plan_instructions(*, title: str) -> str:
    return f"""Plan the concept-image set for the admitted universe "{title}" as one coherent gallery, not as isolated pictures. The gallery is how a cold reader will explore this world, so the set must cover its full range and every image must teach something no other image teaches.

{REGISTER_PROMPT}

RULES
- Emit exactly one plan entry per admitted entity, in any order. concept_mode must be valid for the entity's primary class. visible_fact_ids must be the entity's own fact ids that the image can honestly make visible; visible_relationship_ids must be incident relationships.
- primary_purpose is what the image answers for the audience; spread purposes across the set, no purpose above three tenths of entries.
- lesson_key is a lower_snake_case noun phrase naming the one practice, function, rule, moment, or relationship this image teaches (for example non_wounding_resin_harvest, certificate_invalidation, fold_house_collapse_sequence, anchor_shear_test). Every lesson_key in the set must be different; the validator rejects any repeat. Before returning, list your lesson keys and merge or replace any two that name the same lesson in different words.
- The synopsis's decisive beats (the early waking, the certificate invalidation, the anchor line disabled, the reservoir opened, the turning at the breach, the kite hung on the gate) each belong to exactly one entry. Every other entity related to such a beat is shown at a different moment of its existence: its ordinary work, its origin, its cost, its dispute, its aftermath.
- scene_premise is one paragraph describing one continuous in-world moment with one primary entity and a consequential action or state change. For a collective, system, idea, or event, describe people, structures, tools, weather, water, vegetation, or terrain doing or undergoing the entity's consequences.
- Staging uses only what the proposal contains. A scene_premise may add incidental physical detail (a rope's sag, a wet step) but must not introduce a custom, mark, rite, role, office, rule, or institution the proposal does not state. If a scene needs one, choose a different scene.
- signature_motif declares the composition in three strokes: action_verb, dominant_prop, vantage, as defined above. The dominant_prop must be the largest legible object mass in the scene_premise, not a background element. Before returning, list every (action_verb, dominant_prop) pair and every dominant_prop; no pair may repeat, no dominant_prop may serve more than two entries, no action_verb more than three, no vantage more than half, and at least four vantages must appear. Crowds beside ropes in front of timber frames are one motif no matter how the register changes; give each collective its own dominant prop and its own vantage.
- in_frame_contrast names the two states one frame holds side by side so the mechanism is visible without a caption: the answered signal line beside the ignored one, the cut cord beside the intact one, the certified beam beside the condemned one, the wet reservoir beside the dry channel. Every system and idea entry, and every entry in visible_system_instance or practiced_or_contested_idea mode, must state a real contrast in at least one full sentence; a single-state demonstration of the practice is rejected. Other entries may write "none" or state a contrast when one helps. The contrast must be physical and simultaneous; never a before-and-after split panel.
- Sourced moments keep sourced conditions. When the entity's visible facts fix a time, weather, or place (the turning happens in the storm; the festival is a night; the waking is during the festival), the register must match the source. Achieve set diversity by choosing other entities' registers, never by relocating a sourced moment.
- {SHARED_STAGING_RULE}
- unique_contribution states, in one sentence, what this image shows that no other entry shows. Two entries must not explain the same cultural practice, trade, or institutional function. Where the universe pairs a collective with the system it practises, the collective's scene shows who they are (membership, authority, livelihood, a dispute, a rite) and the system's scene shows how the mechanism works or fails (a rule being applied, a limit reached, a breakdown), never the same craft demonstration twice. The same holds for a place and the thing or event associated with it.
- weather_justification names the physical reason the scene has this weather. Wet weather is allowed only where the world would actually be wet in that moment.
- Do not describe rendering style, medium, camera lenses, or color grading; that belongs to a later medium contract.
- set_rationale explains how the set spreads across scale, time, weather, setting, population, and purpose.
Return only the strict schema object."""


REVIEW_INSTRUCTIONS = """You are an independent semantic reviewer. Judge whether the proposal and gallery plan below form a coherent, source-bounded, explorable universe. You may not edit them. Emit at least these checks: source_boundary, source_fidelity, lineage_and_extension, ontology_and_facets, relationship_graph, entity_selection, institutional_tension, identity_marker_use, gallery_range, one_image_one_lesson, cold_reader_legibility, publication_boundary.

- source_boundary fails if a fact treats poster typography, layout, or marketing hierarchy as canon, or if the direction is cited as evidence.
- source_fidelity fails on contradiction of the synopsis.
- entity_selection fails when the census pads a class or omits a subject the synopsis makes central.
- gallery_range fails when scene registers cluster (same weather, time, or scale dominating) or when wet weather is a mood rather than a scene fact.
- one_image_one_lesson fails when two plan entries teach the same practice or institutional function.
- cold_reader_legibility fails when summaries rely on terms the package never explains.
- publication_boundary fails only if the proposal itself claims rights clearance, publication, approval, or reviewed status. The run's source lock and admission record already carry publication_authorized=false; do not require the proposal to restate it.
- lineage_and_extension judges the lineage class of each claim. Count the claims whose lineage class is wrong (invented content labeled explicit_source or visual_observation, or a synopsis fact labeled generated_extension). Fail when such claims exceed one in twenty of all facts, or when any mislabel contradicts the synopsis rather than elaborating it; otherwise pass and list each mislabeled claim id in advisory_findings so a later revision can relabel it. Which direction requirement id a generated extension cites is never a failure as long as it cites at least one relevant requirement.
- Blocking checks are source_boundary, source_fidelity, lineage_and_extension, ontology_and_facets, relationship_graph, entity_selection, institutional_tension, identity_marker_use, and publication_boundary. gallery_range, one_image_one_lesson, cold_reader_legibility, and any further check you add are advisory: put their findings in advisory_findings and set their status to pass unless the defect is pervasive, meaning it affects more than a quarter of the entries. A deterministic validator already enforces register spread and unique lesson keys; your role on those checks is to name the residual overlaps so the gallery review can weigh them.
Copy the required digests exactly. verdict is fail exactly when any check fails. Return only the strict schema object."""


def global_direction_instructions(*, title: str, medium: MediumContract, universe_id: str) -> str:
    return f"""Compile the global visual grammar for "{title}" as text-only production control. This is not an image brief; it is the shared world logic every entity direction will inherit.

{medium.compile_guidance}

- Observe the attached poster once for broad visual evidence and art grammar only. Do not copy its composition, subjects, typography, or title treatment.
- world_silhouette_language: how forests, trunks, root arches, towns, walls, rigs, and figures read as shapes at distance.
- architecture_grammar and costume_grammar: distinct building and dress logic per culture named in the universe, derived from their materials, mobility, and institutions.
- material_language: the small set of materials that define this world and how each reads.
- palette_by_region: one entry per region or culture with a palette that keeps whites and grays neutral; no global yellow, amber, sepia, or teal-orange cast.
- scale_anchors: the objects that let a viewer read size (a person, a fold-house frame, a trunk, a wall).
- technology_and_ecology_rules: what the world can and cannot do physically, stated as constraints an image must not violate.
- forbidden_substitutions: at least three concrete things an image must never replace this world's forms with (for example generic castle, generic wizard staff).
- poster_observation_ids_used: which admitted poster observations informed the grammar.
Set medium_id exactly to {medium.medium_id} and universe_id exactly to {universe_id}. Return only the strict schema object."""


def entity_direction_instructions(*, medium: MediumContract) -> str:
    return f"""Compile exactly one text-only concept direction for the bound entity. This request has zero image references and zero masks.

{medium.compile_guidance}

- primary_subject: the one primary entity as it will be seen, presence-only language.
- action_beat: agent, goal, obstacle, intervention, and visible_state_change of the single moment. For an event this is its decisive causal beat; for anything else it is the consequential micro-action that makes the entity legible.
- immediate_environment: only what is physically present in this one continuous scene.
- composition_and_camera: framing, scale placement, and depth in the medium's own terms. Realize the sealed signature_motif: the vantage is the camera's vantage, the dominant_prop is the largest legible mass in the frame, and the action_verb is what the primary subject is visibly doing. If the plan states an in_frame_contrast, place both states in the same frame where the eye reads them together. Never an isometric, orthographic, catalog-plate, or cutaway view; the scene is seen from a place a person or bird could stand.
- Lighting follows the register's time of day in value, not only in colour: a day scene is high-key with most of the frame above mid value and shadows that stay open; dusk and dawn keep a lit sky; only night and storm may be low-key.
- visual_identity: silhouette, proportions, construction_logic, materials, color_placement, scale_anchor, wear_and_history, characteristic_motion_or_use, and forbidden_substitutions. This is the medium-neutral identity a viewer must recognize.
- register_realization: one paragraph that establishes the sealed scene register (scale, time of day, weather, setting, population, energy) as concrete visible conditions. A dry scene stays dry; a night scene must show how it is lit.
- continuity_notes: what must agree with the global grammar.
- avoid: concrete things this scene must not contain. Always include explanatory staging and readable text.
- Identity markers are text records; do not stage a flag, crest, seal, badge, or logo. A subordinate culturally grounded applied marking on the owner's own materials is acceptable only when nothing can be read from it.
- Do not name or imitate any franchise, studio, artist, or performer. Do not use words foreign to the medium.
Return only the strict schema object."""


IMAGE_REVIEW_INSTRUCTIONS = """You are an independent image reviewer for one entity concept image. Judge the attached image against the sealed entity record, plan entry, and direction summary. You may admit or reject; you never edit or propose a new image.

Grades (pass or fail):
- entity_identity: the primary entity is recognizably the sealed subject; class and role read without a caption. Fail when the subject is generic or the visual identity contradicts the record.
- action_legibility: fail only when the entity's meaning is not readable at class level: an actor with no purposeful act, a thing not in use, a collective, system, idea, or event with no visible consequence, or a beat replaced by a tableau, display, or symbol. Which knot, which root, which hand, which exact instant, or whether a named consequence is fully visible in one frame is advisory: record it in advisory_findings and pass the grade when the viewer can still tell what kind of act is happening and who is doing it.
- medium_fidelity: defined by the medium criteria below, calibrated as follows. For a drawn or painted medium, a richly painted, atmospheric, densely detailed background is normal theatrical practice and is not CG; fail only when the image is photographic, when surfaces show 3D-rendered specular shading, when it is visibly photobashed, when the character and the environment are in two different production languages, or when wet surfaces read as glossy photographic reflections. For a photographed medium, fail only on illustration, animation, painterly rendering, or CG finish.
- register_fidelity: the visible scale, time of day, weather, setting, population, and energy match the sealed register. Any rain, wet surfaces, or storm lighting in a dry scene fails. Night in a day scene fails.
- readable_text_absent: fail only for readable or meaning-bearing text, numbers, labels, captions, UI, legends, or arrows. Incidental non-semantic marks on machinery, fabric, or bark that cannot be read are advisory, not blocking.
- explanatory_form_absent: fail for diagram, map, timeline, chart, atlas, sheet, kit, blueprint, infographic, montage, collage, split panel, turnaround, variant grid, or a standalone flag, crest, seal, badge, or logo presentation.
- technical_quality: fail for malformed anatomy, smeared faces, broken geometry, pseudo-detail noise, or a global yellow, amber, sepia, or teal-orange cast.
verdict is reject exactly when any grade fails; list every failing reason in blocking_findings and everything else in advisory_findings. Add advisory findings (never blocking) when the plan entry's dominant_prop is not the largest legible mass, when the vantage differs from the sealed one, when a stated in_frame_contrast shows only one of its two states, or when a day scene renders low-key and dark. what_the_image_teaches states in one or two sentences what a cold reader learns about the world from this image alone. Copy entity_id and artifact_sha256 exactly. Return only the strict schema object."""


def image_prompt(
    *,
    entity_id: str,
    direction: EntityDirection,
    global_direction: Mapping[str, object],
    medium: MediumContract,
) -> str:
    """Assemble the one instruction an image node sends.

    Medium first and medium last: the render contract opens the prompt and the
    negative block closes it, because a renderer that speaks one medium will
    otherwise be overruled by scene prose that speaks another. Everything
    between is word-budgeted, so a verbose direction cannot crowd the contract
    out of the model's attention.
    """

    beat = direction.action_beat
    identity = direction.visual_identity
    w = compact_words
    forbidden = global_direction["forbidden_substitutions"]
    substitutions = list(forbidden) if isinstance(forbidden, list) else [forbidden]
    world = "\n".join(
        (
            f"Silhouette language: {w(str(global_direction['world_silhouette_language']), max_words=60)}",
            f"Architecture: {w(str(global_direction['architecture_grammar']), max_words=60)}",
            f"Costume: {w(str(global_direction['costume_grammar']), max_words=50)}",
            f"Materials: {w(str(global_direction['material_language']), max_words=50)}",
            f"Scale anchors: {w(str(global_direction['scale_anchors']), max_words=30)}",
            "Never substitute: " + "; ".join(str(x) for x in substitutions[:6]) + ".",
        )
    )
    scene = "\n".join(
        (
            f"Primary subject: {w(direction.primary_subject, max_words=70)}",
            f"The moment: {w(beat.agent, max_words=25)} {w(beat.goal, max_words=25)} {w(beat.obstacle, max_words=25)} {w(beat.intervention, max_words=30)} {w(beat.visible_state_change, max_words=30)}",
            f"Environment: {w(direction.immediate_environment, max_words=70)}",
            f"Composition: {w(direction.composition_and_camera, max_words=60)}",
            f"Identity: silhouette {w(identity.silhouette, max_words=30)} Proportions {w(identity.proportions, max_words=25)} Construction {w(identity.construction_logic, max_words=30)} Materials {w(identity.materials, max_words=30)} Color placement {w(identity.color_placement, max_words=30)} Scale anchor {w(identity.scale_anchor, max_words=20)} Wear {w(identity.wear_and_history, max_words=25)} Motion or use {w(identity.characteristic_motion_or_use, max_words=25)}",
            f"Conditions: {w(direction.register_realization, max_words=60)}",
            "Avoid: " + "; ".join(direction.avoid[:8]) + ".",
        )
    )
    return "\n\n".join(
        (
            medium.render_block,
            SHARED_STAGING_RULE,
            f"WORLD GRAMMAR\n{world}",
            f"ENTITY SCENE ({entity_id})\n{scene}",
            SHARED_LOCAL_WEATHER,
            SHARED_OUTPUT_FORM,
            medium.negative_block,
        )
    )


__all__ = [
    "IMAGE_REVIEW_INSTRUCTIONS",
    "REVIEW_INSTRUCTIONS",
    "compact_words",
    "entity_direction_instructions",
    "global_direction_instructions",
    "image_prompt",
    "plan_instructions",
    "proposal_instructions",
]
