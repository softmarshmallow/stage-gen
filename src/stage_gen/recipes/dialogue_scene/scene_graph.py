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
from stage_gen.recipes.dialogue_scene.models import EXPRESSION_STATES
from stage_gen.recipes.dialogue_scene.prompts import plan_prompt
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
    SPRITE_CANONICALIZE,
    SPRITE_MATTE,
    STYLE_ANCHOR_KIND,
    STYLE_SELECT,
)

if TYPE_CHECKING:
    from stage_gen.config import StageGenConfig
    from stage_gen.recipes.dialogue_scene.scene_request import ResolvedDialogueScene

DIALOGUE_GRAPH_SCHEMA_VERSION = 3
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


class DialogueSceneGraph(Graph):
    """One dialogue-scene plan of record, bound to the request that produced it."""

    TRACE_SCHEMA_VERSION: ClassVar[int] = DIALOGUE_TRACE_SCHEMA_VERSION
    TRACE_EVENT_KIND: ClassVar[str] = "dialogue-scene-execution-event-v1"
    RUN_SUMMARY_KIND: ClassVar[str] = "dialogue-scene-execution-summary-v1"
    PROJECTION_KIND: ClassVar[str] = "dialogue-scene-execution-projection-v1"
    VIEW_KIND: ClassVar[str] = "dialogue-scene-execution-view-v1"
    VIEW_SCHEMA_VERSION: ClassVar[int] = 3

    schema_version: Literal[3]
    kind: Literal["dialogue-scene-execution-graph-v3"]
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
STRUCTURED_FEATURES = ("structured_output",)
BACKGROUND_REMOVAL_FEATURES = ("alpha_matte",)


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


def expression_template_ids(scene: ResolvedDialogueScene) -> tuple[str, str]:
    """The packaged prompt-template identities this request binds, plan-time known."""

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
    """Compile one authored request into the exact node graph it implies."""

    builder = GraphBuilder(profile=profile)
    request = scene.request
    identity = scene.identity_reference
    # The authored plate's digest rides every image node's cache identity, so
    # replacing the file re-bills the scene rather than leaving sprites drawn
    # against a plate that no longer exists.
    digests = (
        scene.request_sha256,
        scene.policy_digest,
        scene.template_digest,
        identity.sha256,
    )
    identity_inputs = (
        AuthoredInput(label=identity.reference_id, ref=identity.source, sha256=identity.sha256),
    )
    profile_model = scene.profile.profile
    neutral_template, expression_template = expression_template_ids(scene)
    anchor_ref = PortRef(node_id="scene-style-select", port_id="anchor")
    plan_ref = PortRef(node_id="scene-plan", port_id="document")
    concept_ref = PortRef(node_id="scene-concept", port_id="image")

    builder.add(
        REQUEST_RESOLVE,
        "scene-request",
        domain="scene",
        description="Canonicalize the authored dialogue request",
        input_digests=digests,
        ports=(_artifact("request", "request.json", REQUEST_KIND),),
    )
    builder.add(
        PROFILE_RESOLVE,
        "scene-profile-resolve",
        domain="scene",
        description="Validate and materialize the authored character profile",
        depends_on=("scene-request",),
        input_digests=(scene.profile.canonical_sha256, scene.profile.source_sha256),
        ports=(_artifact("profile", "character-profile.json", PROFILE_KIND),),
    )

    builder.add(
        STYLE_SELECT,
        "scene-style-select",
        domain="scene",
        description="Select and materialize the canonical image style anchor",
        depends_on=("scene-profile-resolve",),
        input_digests=(scene.style_resource_sha256, scene.style_compiler_sha256),
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
        "scene-concept",
        domain="appearance",
        description="Publish the authored identity-and-style plate",
        depends_on=("scene-style-select",),
        input_digests=(identity.sha256,),
        ports=(_artifact("image", "assets/concept.png", CONCEPT_KIND),),
        card=NodeCard(authored_inputs=identity_inputs),
    )

    builder.add(
        PLAN_COMPILE,
        "scene-plan",
        domain="scene",
        description="Compile the strict dialogue visual plan",
        depends_on=("scene-concept",),
        input_digests=digests,
        ports=(
            _artifact("document", "plan.json", PLAN_KIND),
            _attempts("scene-plan"),
        ),
        card=NodeCard(
            prompt=plan_prompt(request, scene.request_sha256, profile_model),
            schema_name="dialogue_scene_plan_v4",
            reference_inputs=(concept_ref,),
        ),
    )

    native = request.transparency_mode == "native"
    builder.add(
        BACKDROP_GENERATE,
        "scene-background",
        domain="scene",
        description="Generate the scene background",
        depends_on=("scene-plan", "scene-concept"),
        input_digests=digests,
        ports=(
            _artifact("image", "assets/background.png", BACKDROP_KIND),
            *(
                (_artifact("provider_raw", "raw/background-provider.png", PROVIDER_RAW_KIND),)
                if native
                else ()
            ),
            _attempts("scene-background"),
        ),
        # The backdrop is drawn against the same authored plate as the sprites,
        # so one room and the character standing in it agree on their light.
        card=NodeCard(
            reference_inputs=(concept_ref, plan_ref, anchor_ref),
            authored_inputs=identity_inputs,
        ),
    )

    builder.add(
        EXPRESSION_GENERATE,
        "scene-expression-neutral",
        domain="expression",
        description="Generate the identity-locked neutral expression source",
        params={"state": "neutral"},
        depends_on=("scene-plan", "scene-concept"),
        input_digests=digests,
        ports=(
            _artifact("source", "raw/expression-neutral.png", EXPRESSION_SOURCE_KIND),
            _attempts("scene-expression-neutral"),
        ),
        card=NodeCard(
            template_ref=neutral_template,
            reference_inputs=(concept_ref, plan_ref, anchor_ref),
            authored_inputs=identity_inputs,
        ),
    )
    for state in EXPRESSION_STATES[1:]:
        builder.add(
            EXPRESSION_DERIVE,
            f"scene-expression-{state}",
            domain="expression",
            description=f"Derive the {state} expression from the neutral source",
            params={"state": state},
            depends_on=("scene-expression-neutral",),
            input_digests=digests,
            ports=(
                _artifact("source", f"raw/expression-{state}.png", EXPRESSION_SOURCE_KIND),
                _attempts(f"scene-expression-{state}"),
            ),
            card=NodeCard(
                template_ref=expression_template,
                reference_inputs=(
                    PortRef(node_id="scene-expression-neutral", port_id="source"),
                    plan_ref,
                    anchor_ref,
                ),
            ),
        )

    canonicalize_ids: list[str] = []
    for state in EXPRESSION_STATES:
        node_id = f"scene-canonicalize-{state}"
        canonicalize_ids.append(node_id)
        sprite = _artifact("sprite", f"assets/expression-{state}.png", EXPRESSION_SPRITE_KIND)
        source_ref = PortRef(node_id=f"scene-expression-{state}", port_id="source")
        if request.transparency_mode == "ai":
            builder.add(
                SPRITE_MATTE,
                node_id,
                domain="expression",
                description=f"Derive the portable {state} sprite through background removal",
                params={"state": state},
                depends_on=(f"scene-expression-{state}",),
                input_digests=(scene.transparency_digest,),
                ports=(
                    _artifact("matte", f"raw/expression-{state}.removed.png", MATTE_RAW_KIND),
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
                domain="expression",
                description=f"Derive the portable {state} sprite",
                params={"state": state},
                depends_on=(f"scene-expression-{state}",),
                input_digests=(scene.transparency_digest,),
                ports=(sprite,),
                card=NodeCard(reference_inputs=(source_ref,)),
            )

    builder.add(
        BUNDLE_PACKAGE,
        "scene-bundle",
        domain="scene",
        description="Write the portable dialogue bundle",
        depends_on=("scene-background", *canonicalize_ids),
        input_digests=digests,
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
        kind="dialogue-scene-execution-graph-v3",
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
