"""Dialogue-scene execution documents and the exact DAG one request produces.

The engine owns topology, scheduling, trace, and identity. This module owns what is
specific to a dialogue scene: which capabilities its nodes may use, what its run's
documents are called, and which header fields bind a graph to one authored request.

A dialogue scene is not a game package, so it carries its own document kind rather
than borrowing the prepared-game one. Two recipes, two vocabularies, one engine.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar, Literal

from pydantic import Field

from gnode import (
    SHA256_PATTERN,
    Binding,
    BindingTable,
    Graph,
    ModelRef,
    Node,
    Resource,
    RetryOwner,
    build_node_cache_key,
    seal_graph,
)
from stage_gen.recipes.dialogue_scene.models import EXPRESSION_STATES, ReuseSource

if TYPE_CHECKING:
    from stage_gen.config import StageGenConfig
    from stage_gen.recipes.dialogue_scene.scene_request import ResolvedDialogueScene

DIALOGUE_GRAPH_SCHEMA_VERSION = 1
DIALOGUE_TRACE_SCHEMA_VERSION = 1
DIALOGUE_GRAPH_CONTRACT_VERSION = "dialogue-scene-graph-v1"


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
    VIEW_SCHEMA_VERSION: ClassVar[int] = 2

    schema_version: Literal[1]
    kind: Literal["dialogue-scene-execution-graph-v1"]
    recipe: Literal["dialogue-scene"]
    scene_id: str
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    def identity_header(self) -> dict[str, object]:
        return {**super().identity_header(), "recipe": self.recipe}

    def annotator_key(self) -> str:
        return self.recipe

    def view_header(self) -> dict[str, object]:
        return {"recipe": self.recipe, "scene_id": self.scene_id}

    def operation_vocabulary(self) -> tuple[str, ...]:
        """Report every declared operation, so a zero count stays visible."""

        return tuple(operation.value for operation in DialogueOperationKind)


IMAGE_FEATURES = ("transparent_background", "reference_images")
STRUCTURED_FEATURES = ("structured_output",)
BACKGROUND_REMOVAL_FEATURES = ("alpha_matte",)

_REQUIRED_FEATURES: dict[DialogueOperationKind, tuple[str, ...]] = {
    DialogueOperationKind.IMAGE_GENERATION: IMAGE_FEATURES,
    DialogueOperationKind.STRUCTURED_GENERATION: STRUCTURED_FEATURES,
    DialogueOperationKind.BACKGROUND_REMOVAL: BACKGROUND_REMOVAL_FEATURES,
}


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


class _GraphBuilder:
    def __init__(self, profile: BindingTable) -> None:
        self.profile = profile
        self._nodes: list[Node] = []
        self._by_id: dict[str, Node] = {}

    @property
    def nodes(self) -> tuple[Node, ...]:
        return tuple(self._nodes)

    def provider(
        self,
        node_id: str,
        *,
        domain: str,
        description: str,
        operation: DialogueOperationKind,
        depends_on: Sequence[str],
        input_digests: Sequence[str],
        outputs: Sequence[str],
    ) -> Node:
        binding = self.profile.require(operation, *_REQUIRED_FEATURES[operation])
        return self.add(
            node_id,
            domain=domain,
            description=description,
            operation=operation,
            depends_on=depends_on,
            input_digests=input_digests,
            outputs=outputs,
            provider=binding.model.provider,
            model=binding.model.model,
            resource_id=binding.resource_id,
            retry_owner=RetryOwner.COMPONENT,
            max_attempts=6,
            duration_seconds=binding.estimated_duration_seconds,
            cost_low=binding.estimated_cost_low_usd,
            cost_high=binding.estimated_cost_high_usd,
        )

    def add(
        self,
        node_id: str,
        *,
        domain: str,
        description: str,
        operation: DialogueOperationKind,
        depends_on: Sequence[str] = (),
        input_digests: Sequence[str] = (),
        outputs: Sequence[str] = (),
        provider: str | None = None,
        model: str | None = None,
        resource_id: str = "local",
        retry_owner: RetryOwner = RetryOwner.NONE,
        max_attempts: int = 1,
        duration_seconds: float = 0.25,
        cost_low: float = 0.0,
        cost_high: float = 0.0,
    ) -> Node:
        if node_id in self._by_id:
            raise ValueError(f"duplicate dialogue graph node: {node_id}")
        dependency_cache_keys: list[str] = []
        for dependency in depends_on:
            try:
                dependency_cache_keys.append(self._by_id[dependency].cache_key)
            except KeyError as error:
                raise ValueError(
                    f"dialogue graph dependency must be added first: {node_id}->{dependency}"
                ) from error
        digests = tuple(dict.fromkeys(input_digests))
        node = Node(
            node_id=node_id,
            domain=domain,
            description=description,
            depends_on=tuple(depends_on),
            operation=operation,
            resource_id=resource_id,
            provider=provider,
            model=model,
            retry_owner=retry_owner,
            max_attempts=max_attempts,
            input_sha256=digests,
            cache_key=build_node_cache_key(
                node_id=node_id,
                operation=operation,
                provider=provider,
                model=model,
                input_sha256=digests,
                dependency_cache_keys=dependency_cache_keys,
                contract_version=DIALOGUE_GRAPH_CONTRACT_VERSION,
            ),
            outputs=tuple(outputs),
            estimated_duration_seconds=float(duration_seconds),
            estimated_cost_low_usd=float(cost_low),
            estimated_cost_high_usd=float(cost_high),
        )
        self._nodes.append(node)
        self._by_id[node_id] = node
        return node


def _resources(profile: BindingTable) -> tuple[Resource, ...]:
    resources = [Resource(resource_id="local", rate_limit_owner="none")]
    for binding in profile.bindings:
        resources.append(
            Resource(
                resource_id=binding.resource_id,
                requests_per_minute=binding.requests_per_minute,
                rate_limit_owner=binding.rate_limit_owner,
            )
        )
    return tuple(resources)


def build_dialogue_scene_graph(
    scene: ResolvedDialogueScene,
    *,
    profile: BindingTable,
) -> DialogueSceneGraph:
    """Compile one authored request into the exact node graph it implies.

    The stage pipeline this replaces walked the four expressions serially inside one
    stage, and canonicalized them inside another. Each is its own node here, so the
    three derived expressions are three independent units of work and each
    canonicalization is admitted, cached, and reported on its own.
    """

    builder = _GraphBuilder(profile)
    request = scene.request
    digests = (scene.request_sha256, scene.policy_digest, scene.template_digest)

    builder.add(
        "scene-request",
        domain="scene",
        description="Canonicalize the authored dialogue request",
        operation=DialogueOperationKind.LOCAL,
        input_digests=digests,
        outputs=("request.json", "request.json.meta.json"),
    )
    upstream = "scene-request"
    if scene.profile is not None:
        builder.add(
            "scene-profile-resolve",
            domain="scene",
            description="Validate and materialize the authored character profile",
            operation=DialogueOperationKind.LOCAL,
            depends_on=(upstream,),
            input_digests=(scene.profile.canonical_sha256, scene.profile.source_sha256),
            outputs=("character-profile.json", "character-profile.json.meta.json"),
        )
        upstream = "scene-profile-resolve"

    builder.provider(
        "scene-style-select",
        domain="scene",
        description="Select and materialize the canonical image style anchor",
        operation=DialogueOperationKind.STRUCTURED_GENERATION,
        depends_on=(upstream,),
        input_digests=(scene.style_resource_sha256, scene.style_compiler_sha256),
        outputs=(
            "style-anchor.json",
            "style-anchor.json.meta.json",
            "attempts/scene-style-select.json",
        ),
    )

    concept_outputs = ("assets/concept.png", "assets/concept.png.meta.json")
    generated_concept_outputs = (*concept_outputs, "attempts/scene-concept.json")
    reuse_concept = scene.concept_reuse is not None
    if reuse_concept:
        builder.add(
            "scene-concept",
            domain="appearance",
            description="Ingest the caller-supplied appearance concept",
            operation=DialogueOperationKind.LOCAL,
            depends_on=("scene-style-select",),
            input_digests=(scene.concept_reuse.sha256,) if scene.concept_reuse else (),
            outputs=concept_outputs,
        )
    else:
        builder.provider(
            "scene-concept",
            domain="appearance",
            description="Generate the adult appearance identity anchor",
            operation=DialogueOperationKind.IMAGE_GENERATION,
            depends_on=("scene-style-select",),
            input_digests=digests,
            outputs=generated_concept_outputs,
        )

    builder.provider(
        "scene-plan",
        domain="scene",
        description="Compile the strict dialogue visual plan",
        operation=DialogueOperationKind.STRUCTURED_GENERATION,
        depends_on=("scene-concept",),
        input_digests=digests,
        outputs=("plan.json", "plan.json.meta.json", "attempts/scene-plan.json"),
    )

    background_outputs = ("assets/background.png", "assets/background.png.meta.json")
    generated_background_outputs = (
        *background_outputs,
        *(
            ("raw/background-provider.png", "raw/background-provider.png.meta.json")
            if request.transparency_mode == "native"
            else ()
        ),
        "attempts/scene-background.json",
    )
    if isinstance(request.background, ReuseSource):
        builder.add(
            "scene-background",
            domain="scene",
            description="Ingest the caller-supplied scene background",
            operation=DialogueOperationKind.LOCAL,
            depends_on=("scene-plan",),
            input_digests=(request.background.sha256,),
            outputs=background_outputs,
        )
    else:
        builder.provider(
            "scene-background",
            domain="scene",
            description="Generate the scene background",
            operation=DialogueOperationKind.IMAGE_GENERATION,
            depends_on=("scene-plan",),
            input_digests=digests,
            outputs=generated_background_outputs,
        )

    builder.provider(
        "scene-expression-neutral",
        domain="expression",
        description="Generate the identity-locked neutral expression source",
        operation=DialogueOperationKind.IMAGE_GENERATION,
        depends_on=("scene-plan", "scene-concept"),
        input_digests=digests,
        outputs=(
            "raw/expression-neutral.png",
            "raw/expression-neutral.png.meta.json",
            "attempts/scene-expression-neutral.json",
        ),
    )
    for state in EXPRESSION_STATES[1:]:
        builder.provider(
            f"scene-expression-{state}",
            domain="expression",
            description=f"Derive the {state} expression from the neutral source",
            operation=DialogueOperationKind.IMAGE_GENERATION,
            depends_on=("scene-expression-neutral",),
            input_digests=digests,
            outputs=(
                f"raw/expression-{state}.png",
                f"raw/expression-{state}.png.meta.json",
                f"attempts/scene-expression-{state}.json",
            ),
        )

    canonicalize_ids: list[str] = []
    for state in EXPRESSION_STATES:
        node_id = f"scene-canonicalize-{state}"
        canonicalize_ids.append(node_id)
        outputs = (
            f"assets/expression-{state}.png",
            f"assets/expression-{state}.png.meta.json",
        )
        if request.transparency_mode == "ai":
            builder.provider(
                node_id,
                domain="expression",
                description=f"Derive the portable {state} sprite through background removal",
                operation=DialogueOperationKind.BACKGROUND_REMOVAL,
                depends_on=(f"scene-expression-{state}",),
                input_digests=(scene.transparency_digest,),
                outputs=(
                    f"raw/expression-{state}.removed.png",
                    f"raw/expression-{state}.removed.png.meta.json",
                    *outputs,
                    f"attempts/{node_id}.json",
                ),
            )
        else:
            builder.add(
                node_id,
                domain="expression",
                description=f"Derive the portable {state} sprite",
                operation=DialogueOperationKind.LOCAL,
                depends_on=(f"scene-expression-{state}",),
                input_digests=(scene.transparency_digest,),
                outputs=outputs,
            )

    builder.add(
        "scene-bundle",
        domain="scene",
        description="Write the portable dialogue bundle",
        operation=DialogueOperationKind.LOCAL,
        depends_on=("scene-background", *canonicalize_ids),
        input_digests=digests,
        outputs=("attempts.json", "bundle.json", "bundle.json.meta.json"),
    )

    return seal_graph(
        DialogueSceneGraph,
        resources=_resources(profile),
        nodes=builder.nodes,
        terminal_node_id="scene-bundle",
        schema_version=DIALOGUE_GRAPH_SCHEMA_VERSION,
        kind="dialogue-scene-execution-graph-v1",
        recipe="dialogue-scene",
        scene_id=scene.scene_id,
        request_sha256=scene.request_sha256,
    )


__all__ = [
    "DIALOGUE_GRAPH_CONTRACT_VERSION",
    "DIALOGUE_GRAPH_SCHEMA_VERSION",
    "DIALOGUE_TRACE_SCHEMA_VERSION",
    "DialogueOperationKind",
    "DialogueSceneGraph",
    "build_dialogue_scene_graph",
    "dialogue_graph_profile",
]
