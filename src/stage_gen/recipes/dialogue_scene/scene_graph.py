"""Dialogue-scene execution documents and the exact DAG one request produces.

The engine owns topology, scheduling, trace, and identity. This module owns what is
specific to a dialogue scene: which capabilities its nodes may use, what its run's
documents are called, and which header fields bind a graph to one authored request.

A dialogue scene is not a game package, so it carries its own document kind rather
than borrowing the prepared-game one. Two recipes, two vocabularies, one engine.

Every node instantiates a declared type (scene_types.py) and declares typed ports;
where a node's instruction text is known at plan time it rides the node's card, so
the plan itself states what each node will be told, and the runtime consumes the
same text instead of a second composition.
"""

from __future__ import annotations

from enum import StrEnum
from hashlib import sha256
from typing import TYPE_CHECKING, ClassVar, Literal

from pydantic import Field

from gnode import (
    SHA256_PATTERN,
    AuthoredInput,
    Binding,
    BindingTable,
    Graph,
    GraphBuilder,
    ModelRef,
    NodeCard,
    Port,
    PortRef,
    seal_graph,
)
from stage_gen.components.game_ui.nodes import add_ui_atlas_nodes
from stage_gen.recipes.dialogue_scene.identity import canonical_json_bytes
from stage_gen.recipes.dialogue_scene.prompts import (
    background_prompt,
    plan_prompt,
    track_prompt,
    ui_atlas_prompt,
)
from stage_gen.recipes.dialogue_scene.scene_types import (
    ATTEMPT_LEDGER_KIND,
    BACKDROP_GENERATE,
    BACKDROP_KIND,
    BUNDLE_KIND,
    BUNDLE_PACKAGE,
    CONCEPT_INGEST,
    CONCEPT_KIND,
    EXPRESSION_DERIVE,
    EXPRESSION_GENERATE,
    EXPRESSION_SOURCE_KIND,
    EXPRESSION_SPRITE_KIND,
    MATTE_RAW_KIND,
    MERGED_ATTEMPTS_KIND,
    PLAN_COMPILE,
    PLAN_KIND,
    PROFILE_KIND,
    PROFILE_RESOLVE,
    PROVIDER_RAW_KIND,
    REQUEST_KIND,
    REQUEST_RESOLVE,
    SCENARIO_ADMISSION_KIND,
    SCENARIO_ADMIT,
    SCENARIO_KIND,
    SPRITE_CANONICALIZE,
    SPRITE_MATTE,
    STYLE_ANCHOR_KIND,
    STYLE_SELECT,
    TRACK_GENERATE,
    TRACK_KIND,
)

if TYPE_CHECKING:
    from stage_gen.components.scenario import TrackDeclaration
    from stage_gen.config import StageGenConfig
    from stage_gen.recipes.dialogue_scene.scene_request import ResolvedDialogueScene

DIALOGUE_GRAPH_SCHEMA_VERSION = 5
DIALOGUE_TRACE_SCHEMA_VERSION = 1
#: The cache tree this recipe's node artifacts live under. Renaming it is the
#: whole-recipe invalidation lever; per-type levers are the types' own
#: ``contract_version`` values.
DIALOGUE_CACHE_NAMESPACE = "dialogue-scene-nodes-v2"
DIALOGUE_CACHE_RECORD_KIND = "dialogue-scene-node-cache-v2"


class DialogueOperationKind(StrEnum):
    """The capabilities a dialogue-scene node is allowed to use."""

    LOCAL = "local"
    IMAGE_GENERATION = "image_generation"
    STRUCTURED_GENERATION = "structured_generation"
    BACKGROUND_REMOVAL = "background_removal"
    MUSIC_GENERATION = "music_generation"


class DialogueSceneGraph(Graph):
    """One dialogue-scene plan of record, bound to the request that produced it."""

    TRACE_SCHEMA_VERSION: ClassVar[int] = DIALOGUE_TRACE_SCHEMA_VERSION
    TRACE_EVENT_KIND: ClassVar[str] = "dialogue-scene-execution-event-v1"
    RUN_SUMMARY_KIND: ClassVar[str] = "dialogue-scene-execution-summary-v1"
    PROJECTION_KIND: ClassVar[str] = "dialogue-scene-execution-projection-v1"
    VIEW_KIND: ClassVar[str] = "dialogue-scene-execution-view-v1"
    # The run-view document's version, which is NOT this recipe's version: the view is the
    # shared read-only shape every recipe exports for the run viewer, and it is 3 across all
    # of them. It was bumped to 5 alongside the graph when the scene gained several
    # scenarios, which silently made every scene run unreadable by the viewer — the document
    # shape had not changed at all. `scene_view.DIALOGUE_VIEW_SCHEMA_VERSION` said 3 the
    # whole time; this is the value the writer actually reads.
    VIEW_SCHEMA_VERSION: ClassVar[int] = 3

    schema_version: Literal[5]
    kind: Literal["dialogue-scene-execution-graph-v5"]
    recipe: Literal["dialogue-scene"]
    game_id: str
    scene_id: str
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    def identity_header(self) -> dict[str, object]:
        return {**super().identity_header(), "recipe": self.recipe}

    def annotator_key(self) -> str:
        return self.recipe

    def view_header(self) -> dict[str, object]:
        return {"recipe": self.recipe, "game_id": self.game_id, "scene_id": self.scene_id}

    def operation_vocabulary(self) -> tuple[str, ...]:
        """Report every declared operation, so a zero count stays visible."""

        return tuple(operation.value for operation in DialogueOperationKind)


IMAGE_FEATURES = ("transparent_background", "reference_images")
#: What the bound route can do, which is not the same as what any one node asks of it:
#: the plan compiler needs only structured output, while the UI atlas judge is handed the
#: evidence sheet and so needs image input from the same model.
STRUCTURED_FEATURES = ("structured_output", "image_input")
BACKGROUND_REMOVAL_FEATURES = ("alpha_matte",)
MUSIC_FEATURES = ("instrumental_loop",)


def dialogue_graph_profile(config: StageGenConfig) -> BindingTable:
    """Declare the provider routes this plan may use, credentials untouched.

    Each entry is one ``model@provider`` route with the features it is known to
    support. A capability whose route does not declare a required feature is refused
    while planning - offline, before any spend.
    """

    bindings = [
        Binding(
            operation=DialogueOperationKind.IMAGE_GENERATION,
            model=ModelRef(model=config.openai_image_model, provider="openai"),
            features=frozenset(IMAGE_FEATURES),
            resource_id="openai-image",
            estimated_duration_seconds=120.0,
            estimated_cost_low_usd=0.04,
            estimated_cost_high_usd=0.20,
            requests_per_minute=config.openai_image_ipm,
            rate_limit_owner="provider_adapter",
            verified_on="2026-08-25",
        ),
        Binding(
            operation=DialogueOperationKind.STRUCTURED_GENERATION,
            model=ModelRef(model=config.text_model, provider="openrouter"),
            features=frozenset(STRUCTURED_FEATURES),
            resource_id="openrouter-structured",
            estimated_duration_seconds=30.0,
            estimated_cost_low_usd=0.005,
            estimated_cost_high_usd=0.08,
            verified_on="2026-08-20",
        ),
    ]
    bindings.append(
        Binding(
            operation=DialogueOperationKind.MUSIC_GENERATION,
            model=ModelRef(model=config.music_model, provider="openrouter"),
            features=frozenset(MUSIC_FEATURES),
            resource_id="openrouter-music",
            estimated_duration_seconds=180.0,
            estimated_cost_low_usd=0.10,
            estimated_cost_high_usd=0.80,
            verified_on="2026-08-14",
        )
    )
    if config.fal_key is not None:
        bindings.append(
            Binding(
                operation=DialogueOperationKind.BACKGROUND_REMOVAL,
                model=ModelRef(model=config.background_removal_model, provider="fal"),
                features=frozenset(BACKGROUND_REMOVAL_FEATURES),
                resource_id="fal-background-removal",
                estimated_duration_seconds=20.0,
                estimated_cost_low_usd=0.002,
                estimated_cost_high_usd=0.02,
                verified_on="2026-08-20",
            )
        )
    return BindingTable(bindings)


def _artifact(port_id: str, ref: str, kind: str) -> Port:
    """One artifact-plus-sidecar port; the pair stays visibly one payload."""

    return Port(port_id=port_id, artifact_ref=ref, kind=kind, sidecar_ref=f"{ref}.meta.json")


def _attempts(node_id: str) -> Port:
    return Port(
        port_id="attempts",
        artifact_ref=f"attempts/{node_id}.json",
        kind=ATTEMPT_LEDGER_KIND,
    )


def _slug(value: str) -> str:
    """Node and asset ids are kebab; the authored vocabulary is snake."""

    return value.replace("_", "-")


def _brief_digest(brief: str) -> str:
    """One stage's own words, so editing one backdrop does not re-bill the others."""

    return sha256(brief.encode("utf-8")).hexdigest()


def _track_digest(track: TrackDeclaration) -> str:
    """One track's brief and production intent, and nothing else in the scenario."""

    return sha256(canonical_json_bytes(track)).hexdigest()


def expression_template_ids(scene: ResolvedDialogueScene) -> tuple[str, str]:
    """The packaged prompt-template identities this request binds, plan-time known.

    Still named for the base plate and the edit, not for `neutral` and the other
    three: the templates say how a face is drawn from scratch and how one is
    edited, which is unchanged by the faces now being authored.
    """

    native = scene.request.transparency_mode == "native"
    return (
        "profile-native-neutral-v1" if native else "profile-neutral-v1",
        "profile-native-expression-edit-v1" if native else "profile-expression-edit-v1",
    )


def build_dialogue_scene_graph(
    scene: ResolvedDialogueScene,
    *,
    profile: BindingTable,
) -> DialogueSceneGraph:
    """Compile one authored request into the exact node graph it implies.

    The graph fans out over what the bound scenarios declare between them: once
    per bound scenario, once per distinct drawable actor, once per distinct stage,
    once per distinct track, and once per face that actor's own profile declares.
    Nothing here reads a fixed count - a scene with one actor and one backdrop
    produces the graph it used to, and a scene with a cast of nine across six
    scenarios produces the same shape, wider.

    The de-duplication is the resolver's union, not a filter applied here: every
    fan-out below walks a list that already holds one entry per distinct id. What
    this function must not do is let a node's identity depend on WHICH scenario
    asked for it - a backdrop node is named for its stage, keyed on the stage's
    own brief, and carries no scenario in its cache identity, so the same room
    named by three scenarios is one node, drawn once, and cached once.
    """

    builder = GraphBuilder(profile=profile)
    request = scene.request
    style_plate = scene.style_reference
    # The authored plate's digest rides every image node's cache identity, so
    # replacing the file re-bills the scene rather than leaving sprites drawn
    # against a plate that no longer exists.
    # `art_request_sha256`, not `request_sha256`: the narrative is deliberately
    # outside every image node's cache identity, so rewording a line of dialogue
    # does not re-bill provider images that would come back identical.
    digests = (
        scene.art_request_sha256,
        scene.policy_digest,
        scene.template_digest,
        style_plate.sha256,
    )
    style_inputs = (
        AuthoredInput(
            label=style_plate.reference_id, ref=style_plate.source, sha256=style_plate.sha256
        ),
    )
    neutral_template, expression_template = expression_template_ids(scene)
    anchor_ref = PortRef(node_id="scene-style-select", port_id="anchor")
    style_ref = PortRef(node_id="scene-style-plate", port_id="image")

    builder.add(
        REQUEST_RESOLVE,
        "scene-request",
        domain="scene",
        description="Canonicalize the authored dialogue request",
        input_digests=(scene.request_sha256, scene.policy_digest, scene.template_digest),
        ports=(_artifact("request", "request.json", REQUEST_KIND),),
    )
    # One admit node per bound narrative. A single node publishing all of them
    # would make editing the fourth scenario re-publish the other five, and the
    # proof that admitted one scenario would no longer be an artifact of its own.
    scenario_node_ids: list[str] = []
    for binding, scenario in zip(request.scenarios, scene.scenarios, strict=True):
        scenario_id = scenario.declarations.scenario_id
        node_id = f"scenario-{_slug(scenario_id)}"
        scenario_node_ids.append(node_id)
        builder.add(
            SCENARIO_ADMIT,
            node_id,
            domain="scene",
            description=f"Admit the {scenario_id} scenario and publish its proof",
            params={"scenario": scenario_id},
            depends_on=("scene-request",),
            input_digests=(scenario.program_sha256,),
            ports=(
                _artifact("program", f"scenarios/{_slug(scenario_id)}.json", SCENARIO_KIND),
                _artifact(
                    "proof",
                    f"scenarios/{_slug(scenario_id)}.validation.json",
                    SCENARIO_ADMISSION_KIND,
                ),
            ),
            card=NodeCard(
                authored_inputs=(
                    AuthoredInput(
                        label="scenario",
                        ref=binding.ref,
                        sha256=binding.source_sha256,
                    ),
                )
            ),
        )
    builder.add(
        STYLE_SELECT,
        "scene-style-select",
        domain="scene",
        description="Select and materialize the canonical image style anchor",
        depends_on=("scene-request",),
        # A barrier edge, not a lineage one. `scene-request` publishes the whole
        # authored document, so its own cache key has to cover every byte of it -
        # including the narrative. Inheriting that key here would drag the
        # narrative back into every downstream image through the dependency
        # chain, undoing `art_request_sha256`. The art fan-out therefore carries
        # the art identity directly and orders after the request without
        # borrowing its identity.
        cache_depends_on=(),
        input_digests=(
            scene.art_request_sha256,
            scene.style_resource_sha256,
            scene.style_compiler_sha256,
        ),
        ports=(
            _artifact("anchor", "style-anchor.json", STYLE_ANCHOR_KIND),
            _attempts("scene-style-select"),
        ),
        card=NodeCard(prompt=scene.style_selection_brief, schema_name="canonical_style_anchor"),
    )

    # Nothing generates the art direction. The authored plate arrives with the
    # package, is held to its declared digest offline, and is published into the
    # run here so every downstream node reads it through an ordinary port.
    builder.add(
        CONCEPT_INGEST,
        "scene-style-plate",
        domain="scene",
        description="Publish the authored style plate",
        depends_on=("scene-style-select",),
        input_digests=(style_plate.sha256,),
        ports=(_artifact("image", "assets/style-plate.png", CONCEPT_KIND),),
        card=NodeCard(authored_inputs=style_inputs),
    )

    native = request.transparency_mode == "native"
    terminal_ids: list[str] = []

    # ------------------------------------------------------------------ stages
    for stage in scene.stages:
        node_id = f"stage-{_slug(stage.stage_id)}"
        terminal_ids.append(node_id)
        builder.add(
            BACKDROP_GENERATE,
            node_id,
            domain="stage",
            description=f"Generate the {stage.stage_id} backdrop",
            params={"stage": stage.stage_id},
            depends_on=("scene-style-plate",),
            input_digests=(*digests, _brief_digest(stage.brief)),
            ports=(
                _artifact("image", f"assets/{node_id}.png", BACKDROP_KIND),
                *(
                    (
                        _artifact(
                            "provider_raw",
                            f"raw/{node_id}-provider.png",
                            PROVIDER_RAW_KIND,
                        ),
                    )
                    if native
                    else ()
                ),
                _attempts(node_id),
            ),
            # Every backdrop is drawn against the same authored plate as the
            # sprites, so a room and the people standing in it agree on light.
            card=NodeCard(
                prompt=background_prompt(stage.brief),
                reference_inputs=(style_ref, anchor_ref),
                authored_inputs=style_inputs,
            ),
        )

    # ------------------------------------------------------------------ actors
    for actor in scene.actors:
        slug = actor.asset_prefix
        plate = actor.identity_reference
        actor_inputs = (
            style_inputs
            if plate is None
            else (
                *style_inputs,
                AuthoredInput(label=plate.reference_id, ref=plate.source, sha256=plate.sha256),
            )
        )
        actor_digests = (
            *digests,
            actor.profile.canonical_sha256,
            *(() if plate is None else (plate.sha256,)),
        )
        profile_node = f"actor-{slug}-profile"
        plan_node = f"actor-{slug}-plan"
        # The base face is the actor's own first authored expression, not a fixed
        # `neutral`: a detective's resting face is `blunt` and a witness's is
        # `repeating`, and there is no scene-wide word for either.
        base = actor.base
        base_node = f"actor-{slug}-{_slug(base.expression_id)}"

        builder.add(
            PROFILE_RESOLVE,
            profile_node,
            domain="actor",
            description=f"Validate and materialize the authored profile for {actor.actor_id}",
            params={"actor": actor.actor_id},
            depends_on=("scene-style-plate",),
            input_digests=(actor.profile.canonical_sha256, actor.profile.source_sha256),
            ports=(_artifact("profile", f"characters/{slug}.json", PROFILE_KIND),),
        )
        builder.add(
            PLAN_COMPILE,
            plan_node,
            domain="actor",
            description=f"Compile the strict visual plan for {actor.actor_id}",
            params={"actor": actor.actor_id},
            # The plate is a real dependency, not just a card reference: the
            # handler reads it through its dependency port, so the edge has to
            # exist for lineage to be declared rather than assumed.
            depends_on=(profile_node, "scene-style-plate"),
            input_digests=actor_digests,
            ports=(
                _artifact("document", f"plans/{slug}.json", PLAN_KIND),
                _attempts(plan_node),
            ),
            card=NodeCard(
                prompt=plan_prompt(request, scene.art_request_sha256, actor.profile.profile),
                schema_name="dialogue_scene_plan_v8",
                reference_inputs=(style_ref,),
            ),
        )
        plan_ref = PortRef(node_id=plan_node, port_id="document")
        builder.add(
            EXPRESSION_GENERATE,
            base_node,
            domain="actor",
            description=(
                f"Generate the identity-locked {base.expression_id} sprite for {actor.actor_id}"
            ),
            params={"actor": actor.actor_id, "state": base.expression_id},
            depends_on=(plan_node, "scene-style-plate"),
            input_digests=actor_digests,
            ports=(
                _artifact(
                    "source",
                    f"raw/{slug}-{_slug(base.expression_id)}.png",
                    EXPRESSION_SOURCE_KIND,
                ),
                _attempts(base_node),
            ),
            card=NodeCard(
                template_ref=neutral_template,
                reference_inputs=(style_ref, plan_ref, anchor_ref),
                authored_inputs=actor_inputs,
            ),
        )
        for expression in actor.edits:
            state = _slug(expression.expression_id)
            builder.add(
                EXPRESSION_DERIVE,
                f"actor-{slug}-{state}",
                domain="actor",
                description=(
                    f"Derive the {expression.expression_id} expression for {actor.actor_id}"
                ),
                params={"actor": actor.actor_id, "state": expression.expression_id},
                depends_on=(base_node,),
                input_digests=actor_digests,
                ports=(
                    _artifact("source", f"raw/{slug}-{state}.png", EXPRESSION_SOURCE_KIND),
                    _attempts(f"actor-{slug}-{state}"),
                ),
                card=NodeCard(
                    template_ref=expression_template,
                    reference_inputs=(
                        PortRef(node_id=base_node, port_id="source"),
                        plan_ref,
                        anchor_ref,
                    ),
                ),
            )
        for expression in actor.expressions:
            state = _slug(expression.expression_id)
            node_id = f"actor-{slug}-canonicalize-{state}"
            terminal_ids.append(node_id)
            sprite = _artifact("sprite", f"assets/{slug}-{state}.png", EXPRESSION_SPRITE_KIND)
            source_ref = PortRef(node_id=f"actor-{slug}-{state}", port_id="source")
            if request.transparency_mode == "ai":
                builder.add(
                    SPRITE_MATTE,
                    node_id,
                    domain="actor",
                    description=(
                        f"Matte the portable {expression.expression_id} sprite for {actor.actor_id}"
                    ),
                    params={"actor": actor.actor_id, "state": expression.expression_id},
                    depends_on=(f"actor-{slug}-{state}",),
                    input_digests=(scene.transparency_digest,),
                    ports=(
                        _artifact("matte", f"raw/{slug}-{state}.removed.png", MATTE_RAW_KIND),
                        sprite,
                        _attempts(node_id),
                    ),
                    card=NodeCard(
                        prompt="Remove the background while preserving the adult character.",
                        reference_inputs=(source_ref,),
                    ),
                )
            else:
                builder.add(
                    SPRITE_CANONICALIZE,
                    node_id,
                    domain="actor",
                    description=(
                        f"Derive the portable {expression.expression_id} sprite "
                        f"for {actor.actor_id}"
                    ),
                    params={"actor": actor.actor_id, "state": expression.expression_id},
                    depends_on=(f"actor-{slug}-{state}",),
                    input_digests=(scene.transparency_digest,),
                    ports=(sprite,),
                    card=NodeCard(reference_inputs=(source_ref,)),
                )

    # ------------------------------------------------------------------ tracks
    # One track per distinct music identity, exactly as one backdrop per distinct
    # stage. The scenarios are the catalog: they say which tracks exist and what
    # each one is for, and admission already refused a script that plays an
    # undeclared track or declares one nothing plays. Two scenarios that share a
    # theme share the recording; the resolver already refused two scenarios that
    # disagree about what one track_id is.
    for track in scene.tracks:
        node_id = f"track-{_slug(track.track_id)}"
        terminal_ids.append(node_id)
        builder.add(
            TRACK_GENERATE,
            node_id,
            domain="track",
            description=f"Generate the {track.track_id} track",
            params={"track": track.track_id},
            # Ordered after the request, not descended from it. Music is not
            # drawn against the style plate and owes nothing to the art
            # identity; its own brief is the whole of its cache key, so
            # rewording a line, re-plating the scene, or editing another
            # track's brief all leave this one cached.
            depends_on=("scene-request",),
            cache_depends_on=(),
            input_digests=(_track_digest(track),),
            ports=(
                _artifact("audio", f"assets/{node_id}.mp3", TRACK_KIND),
                _attempts(node_id),
            ),
            card=NodeCard(prompt=track_prompt(request.game_id, track)),
        )

    # Panels and buttons are the one thing every genre draws the same way, so the scene
    # plans the shared nine-slice triplet rather than a fourth private copy of it. Its
    # identity is the style plate: re-plate the scene and the interface re-bills with
    # every other image drawn against it.
    terminal_ids.extend(
        add_ui_atlas_nodes(
            builder,
            root="scene-style-plate",
            ui=scene.ui,
            style_prompt=ui_atlas_prompt,
            direction_digests=(scene.style_reference.sha256,),
            attempts_port=_attempts,
        )
    )

    builder.add(
        BUNDLE_PACKAGE,
        "scene-bundle",
        domain="scene",
        description="Write the portable dialogue bundle",
        depends_on=(*scenario_node_ids, *terminal_ids),
        input_digests=(
            *digests,
            *(scenario.program_sha256 for scenario in scene.scenarios),
        ),
        ports=(
            Port(
                port_id="merged_attempts", artifact_ref="attempts.json", kind=MERGED_ATTEMPTS_KIND
            ),
            _artifact("bundle", "bundle.json", BUNDLE_KIND),
        ),
    )

    return seal_graph(
        DialogueSceneGraph,
        resources=builder.resources(),
        nodes=builder.nodes,
        terminal_node_id="scene-bundle",
        schema_version=DIALOGUE_GRAPH_SCHEMA_VERSION,
        kind="dialogue-scene-execution-graph-v5",
        recipe="dialogue-scene",
        game_id=request.game_id,
        scene_id=scene.scene_id,
        request_sha256=scene.request_sha256,
    )


__all__ = [
    "DIALOGUE_CACHE_NAMESPACE",
    "DIALOGUE_CACHE_RECORD_KIND",
    "DIALOGUE_GRAPH_SCHEMA_VERSION",
    "DIALOGUE_TRACE_SCHEMA_VERSION",
    "DialogueOperationKind",
    "DialogueSceneGraph",
    "build_dialogue_scene_graph",
    "dialogue_graph_profile",
    "expression_template_ids",
]
