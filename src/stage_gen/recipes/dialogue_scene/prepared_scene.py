"""Execute one dialogue-scene node: prompts, validators, lineage, and provenance.

Every provider operation stays inside a component service, which owns the whole
retry-validate-persist contract; this module owns what a dialogue scene asks for and
what it will accept back. The stage pipeline this replaces walked four expressions
serially inside one stage and canonicalized them inside another - here each is a node,
so each is scheduled, cached, and reported on its own.

Attempt records are written per node rather than appended to one shared ledger: nodes
run concurrently, and a single mutable file is a stage-serial assumption. The terminal
bundle node merges them in graph order into the ``attempts.json`` the bundle binds.
"""

from __future__ import annotations

import base64
from dataclasses import asdict
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image

from gnode import (
    ArtifactRights,
    BackgroundRemovalRequest,
    BinaryArtifact,
    CacheDisposition,
    ImageGenerationRequest,
    ImageReference,
    InputProvenance,
    NodeArtifact,
    NodeExecutionError,
    NodeExecutionResult,
    NodeTypeRegistry,
    ProvenanceInput,
    RetryExhaustedError,
    SoftwareIdentity,
    StructuredGenerationRequest,
    StructuredOutputSchema,
    StructuredReference,
    atomic_write_json,
    dependency_port,
    resolve_relative_path_within_root,
    write_artifact_with_provenance_async,
)
from stage_gen.identity import STAGE_GEN_TOOL
from stage_gen.image_prompting import build_image_style_compiler_request
from stage_gen.image_style import (
    CanonicalStyleAnchor,
    ImageAssetKind,
    append_style_anchor_once,
    canonical_style_anchor_digest,
    compile_style_prompt_anchor,
)
from stage_gen.media import (
    CHROMA_MATTE_VERSION,
    MAGENTA_EDGE_DECONTAMINATION_VERSION,
    NATIVE_ALPHA_OPAQUE_THRESHOLD,
    apply_chroma_transparency,
    compose_source_with_alpha,
    decontaminate_magenta_edges,
    inspect_image,
    normalize_png,
    normalize_png_cover,
)
from stage_gen.recipes.dialogue_scene.identity import (
    canonical_json_bytes,
    content_sha256,
)
from stage_gen.recipes.dialogue_scene.manifest import write_dialogue_bundle
from stage_gen.recipes.dialogue_scene.models import (
    EXPRESSION_STATES,
    AttemptLedger,
    AttemptRecord,
    DialogueScenePlan,
    DialogueScenePlanDraft,
    ExpressionDirection,
    ExpressionState,
    PromptTemplateBinding,
    SharedLocks,
    SpriteGeometry,
)
from stage_gen.recipes.dialogue_scene.policy import POLICY_DIGEST
from stage_gen.recipes.dialogue_scene.prompts import expression_prompt, neutral_prompt
from stage_gen.recipes.dialogue_scene.scene_graph import (
    DIALOGUE_CACHE_NAMESPACE,
    DIALOGUE_CACHE_RECORD_KIND,
    DialogueOperationKind,
    DialogueSceneGraph,
)
from stage_gen.recipes.dialogue_scene.scene_request import (
    ResolvedDialogueScene,
    ResolvedSceneActor,
    profile_lock_values,
)
from stage_gen.recipes.dialogue_scene.scene_types import (
    BACKDROP_GENERATE,
    BUNDLE_PACKAGE,
    CONCEPT_INGEST,
    EXPRESSION_DERIVE,
    EXPRESSION_GENERATE,
    EXPRESSION_SOURCE_KIND,
    PLAN_COMPILE,
    PROFILE_RESOLVE,
    REQUEST_RESOLVE,
    SCENARIO_ADMIT,
    SPRITE_CANONICALIZE,
    SPRITE_MATTE,
    STYLE_SELECT,
)
from stage_gen.recipes.dialogue_scene.schema import dialogue_plan_json_schema
from stage_gen.recipes.node_cache import NodeArtifactCache

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from gnode import (
        BackgroundMaskArtifact,
        BackgroundRemovalService,
        ImageGenerationService,
        Node,
        NodeExecutionContext,
        NodeHandler,
        StructuredGenerationService,
    )
    from stage_gen.recipes.dialogue_scene.models import DialoguePlan

_COMPONENT = SoftwareIdentity(name="@stage-gen/dialogue-scene", version="5")

SPRITE_WIDTH = 1024
SPRITE_HEIGHT = 1536
BACKGROUND_WIDTH = 1672
BACKGROUND_HEIGHT = 941
NATIVE_BACKGROUND_WIDTH = 1680
NATIVE_BACKGROUND_HEIGHT = 944


def scene_target_node_ids(graph: DialogueSceneGraph) -> tuple[str, ...]:
    """Every node except the terminal bundle, which the caller publishes explicitly."""

    return tuple(node.node_id for node in graph.nodes if node.node_id != graph.terminal_node_id)


class DialogueSceneNodeHandler:
    """Dispatch dialogue nodes while provider operations stay component-owned."""

    def __init__(
        self,
        graph: DialogueSceneGraph,
        scene: ResolvedDialogueScene,
        *,
        run_dir: Path,
        cache_dir: Path,
        image_service: ImageGenerationService,
        structured_service: StructuredGenerationService[Any],
        background_service: BackgroundRemovalService | None = None,
        capability_timeout_s: float | None = None,
    ) -> None:
        self._graph = graph
        self._scene = scene
        self._run_dir = run_dir
        self._images = image_service
        self._structured = structured_service
        self._background = background_service
        self._timeout = capability_timeout_s
        self._cache = NodeArtifactCache(
            graph,
            run_dir=run_dir,
            cache_dir=cache_dir,
            namespace=DIALOGUE_CACHE_NAMESPACE,
            record_kind=DIALOGUE_CACHE_RECORD_KIND,
        )
        self._registry = self._build_registry()

    async def __call__(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        cached = self._cache.read(node, context)
        if cached is not None:
            return cached
        try:
            result = await self._registry(node, context)
        except NodeExecutionError:
            raise
        except Exception as error:
            external = node.operation != DialogueOperationKind.LOCAL
            attempts = int(getattr(error, "attempts", 1))
            raise NodeExecutionError(
                str(error),
                attempts=attempts,
                provider_operations=attempts if external else 0,
            ) from error
        self._cache.write(node, context, result)
        return result

    # ---------------------------------------------------------------- dispatch

    def _build_registry(self) -> NodeTypeRegistry:
        """Registered types replace the id-string chain this handler once walked."""

        registry = NodeTypeRegistry()
        registry.register(REQUEST_RESOLVE, self._bind(self._write_request))
        registry.register(SCENARIO_ADMIT, self._bind(self._write_scenario))
        registry.register(PROFILE_RESOLVE, self._bind(self._write_profile))
        registry.register(STYLE_SELECT, self._bind(self._select_style))
        registry.register(CONCEPT_INGEST, self._bind(self._concept_publish))
        registry.register(PLAN_COMPILE, self._bind(self._plan))
        registry.register(BACKDROP_GENERATE, self._bind(self._backdrop_generate))
        registry.register(EXPRESSION_GENERATE, self._bind(self._expression))
        registry.register(EXPRESSION_DERIVE, self._bind(self._expression))
        registry.register(SPRITE_MATTE, self._bind(self._canonicalize_matte))
        registry.register(SPRITE_CANONICALIZE, self._bind(self._canonicalize_local))
        registry.register(BUNDLE_PACKAGE, self._bind(self._bundle))
        return registry

    def _bind(self, method: Callable[[Node], Awaitable[NodeExecutionResult]]) -> NodeHandler:
        async def handler(node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
            return await method(node)

        return handler

    def _node_actor(self, node: Node) -> ResolvedSceneActor:
        """The declared actor this node instance is bound to."""

        actor_id = node.params.get("actor")
        if actor_id is None:
            raise ValueError(f"node {node.node_id} declares no actor")
        return self._scene.actor(str(actor_id))

    def _node_stage(self, node: Node) -> str:
        stage_id = node.params.get("stage")
        if stage_id is None:
            raise ValueError(f"node {node.node_id} declares no stage")
        return str(stage_id)

    def _node_state(self, node: Node) -> ExpressionState:
        """The declared expression this node instance is bound to."""

        candidate = node.params.get("state")
        for state in EXPRESSION_STATES:
            if state == candidate:
                return state
        raise ValueError(f"node {node.node_id} declares no known expression state")

    # ------------------------------------------------------------------ nodes

    async def _write_request(self, node: Node) -> NodeExecutionResult:
        """Publish the canonical document as exactly its canonical bytes.

        No trailing newline: the plan binds the canonical digest, so the file the
        run ships has to hash to that same value or a consumer holding both can
        never prove the plan was compiled from the document beside it. The
        character profile is published the same way, for the same reason.
        """

        await self._write_local(
            "request.json",
            self._scene.request_bytes,
            "application/json",
            "Canonicalize the authored dialogue request.",
            params={"request_sha256": self._scene.request_sha256},
        )
        return self._result(node, provider_operations=0)

    async def _write_scenario(self, node: Node) -> NodeExecutionResult:
        """Publish the compiled narrative and the proof that admitted it.

        Both were settled while the package resolved, so this writes what was
        already proven rather than re-deriving it. The proof ships beside the
        program for the same reason `puzzle.validation.json` does: a run that
        claims a scenario is finishable should carry the evidence.
        """

        scenario = self._scene.scenario
        await self._write_local(
            "scenario.json",
            scenario.program_bytes,
            "application/json",
            "Compile the authored scenario into its program.",
            refs=[self._scene.request.scenario.ref],
            params={
                "scenario_id": scenario.declarations.scenario_id,
                "scenario_source_sha256": self._scene.request.scenario.source_sha256,
                "script_sha256": scenario.declarations.script_sha256,
                "program_sha256": scenario.program_sha256,
            },
        )
        await self._write_local(
            "scenario.validation.json",
            canonical_json_bytes(scenario.admission.model_dump(mode="json")),
            "application/json",
            "Prove the authored scenario reachable and finishable.",
            params={
                "reachable_states": scenario.admission.reachable_states,
                "endings": len(scenario.admission.witnesses),
            },
        )
        return self._result(node, provider_operations=0)

    async def _write_profile(self, node: Node) -> NodeExecutionResult:
        profile = self._node_actor(node).profile
        rights = profile.profile.rights
        await self._write_local(
            node.port("profile").artifact_ref,
            profile.canonical_bytes,
            "application/json",
            "Validate and canonicalize the authored character profile.",
            refs=[profile.ref],
            inputs=[profile.source_provenance],
            params={
                "character_profile_ref": profile.ref,
                "character_profile_source_sha256": profile.source_sha256,
                "character_profile_sha256": profile.canonical_sha256,
                "profile_id": profile.profile.profile_id,
                "revision": profile.profile.revision,
            },
            rights=ArtifactRights(
                status=rights.status,
                attribution=rights.attribution,
                basis=rights.basis,
                reviewed_at=rights.reviewed_at,
            ),
        )
        return self._result(node, provider_operations=0)

    async def _select_style(self, node: Node) -> NodeExecutionResult:
        request = build_image_style_compiler_request(
            prompt=self._card_prompt(node),
            artifact_path=self._run_dir / "style-anchor.json",
            asset_kinds=("concept_art", "character_sprite", "environment_background"),
            timeout_seconds=self._timeout,
        )
        result = await self._provider_call(
            node,
            "style-anchor",
            request.prompt,
            (),
            lambda: self._structured.generate(request),
            "style-anchor.json",
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _concept_publish(self, node: Node) -> NodeExecutionResult:
        """Publish the authored identity plate into the run, rights and all.

        The bytes were read and digest-checked while the package resolved, so
        this writes what the author committed - never a redraw of it - and
        carries their rights decision across, because the run now ships a copy.
        """

        identity = self._scene.style_reference
        await self._write_local(
            "assets/style-plate.png",
            identity.data,
            identity.media_type,
            "Publish the authored style plate.",
            refs=[identity.provenance_ref],
            params={
                "role": "style",
                "reference_id": identity.reference_id,
                "source": identity.source,
                "source_sha256": identity.sha256,
            },
            rights=ArtifactRights(
                status=identity.rights_status,
                basis=list(identity.rights_basis),
                reviewed_at=None,
            ),
        )
        return self._result(node, provider_operations=0)

    async def _plan(self, node: Node) -> NodeExecutionResult:
        scene = self._scene
        concept_path = self._dependency_artifact(node, kind="portrait-concept-v1")
        concept = self._read(concept_path)
        prompt = self._card_prompt(node)
        request = StructuredGenerationRequest(
            prompt=prompt,
            system=(
                "Return only the strict dialogue-scene-plan JSON. Do not add story, "
                "dialogue, provider instructions, paths, or policy exceptions."
            ),
            artifact_path=self._run_dir / node.port("document").artifact_ref,
            references=(_structured_reference(concept, concept_path),),
            schema=StructuredOutputSchema(
                name="dialogue_scene_plan_v6",
                json_schema=dialogue_plan_json_schema(),
                strict=True,
            ),
            parse=lambda value: self._parse_plan(self._node_actor(node), value),
            artifact_value=lambda value: value.model_dump(mode="json", exclude_none=True),
            metadata={
                "node": node.node_id,
                "request_sha256": scene.request_sha256,
                "policy_sha256": POLICY_DIGEST,
                "template_sha256": scene.template_digest,
                **self._profile_provenance(self._node_actor(node)),
                **self._style_provenance(),
            },
            timeout_seconds=self._timeout,
            provenance_schema_version=2,
        )
        result = await self._provider_call(
            node,
            "plan",
            prompt,
            [concept],
            lambda: self._structured.generate(request),
            node.port("document").artifact_ref,
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _backdrop_generate(self, node: Node) -> NodeExecutionResult:
        scene = self._scene
        native = scene.request.transparency_mode == "native"
        published = node.port("image").artifact_ref
        provider_output = node.port("provider_raw").artifact_ref if native else published
        prompt = self._card_prompt(node)
        # Every room is drawn against the same authored plate the cast is, so a
        # backdrop and the people standing in it cannot disagree about the light.
        style_relative = self._dependency_artifact(node, kind="portrait-concept-v1")
        references = ((self._read(style_relative), style_relative),)
        # "background" is the asset role that provenance and validation key on;
        # which stage this instance draws is already on the node's params.
        result = await self._image(
            node, "background", prompt, provider_output, references, alpha=False
        )
        if not native:
            return self._result(node, attempts=result.attempts, provider_operations=result.attempts)
        normalized, record = normalize_png(
            result.data, width=BACKGROUND_WIDTH, height=BACKGROUND_HEIGHT
        )
        await self._write_local(
            published,
            normalized,
            "image/png",
            "Normalize the provider-native opaque dialogue background to the runtime canvas.",
            refs=[provider_output],
            inputs=[
                InputProvenance(
                    ref=provider_output,
                    sha256=content_sha256(result.data),
                    source="content",
                    bytes=len(result.data),
                    media_type="image/png",
                )
            ],
            params={
                "normalization": asdict(record),
                "source_provenance_path": self._relative(result.provenance_path),
            },
            attempts=result.attempts,
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _expression(self, node: Node) -> NodeExecutionResult:
        scene = self._scene
        state = self._node_state(node)
        actor = self._node_actor(node)
        plan = self._plan_document(actor)
        alpha = scene.request.transparency_mode == "native"
        if state == "neutral":
            source_relative = self._dependency_artifact(node, kind="portrait-concept-v1")
            prompt = neutral_prompt(
                scene.request, plan, has_identity_plate=actor.identity_reference is not None
            )
        else:
            source_relative = self._dependency_artifact(node, kind=EXPRESSION_SOURCE_KIND)
            prompt = expression_prompt(
                state, plan, transparency_mode=scene.request.transparency_mode
            )
        source = self._read(source_relative)
        references = ((source, source_relative),)
        result = await self._image(
            node, state, prompt, node.port("source").artifact_ref, references, alpha=alpha
        )
        return self._result(node, attempts=result.attempts, provider_operations=result.attempts)

    async def _canonicalize_local(self, node: Node) -> NodeExecutionResult:
        scene = self._scene
        state = self._node_state(node)
        mode = scene.request.transparency_mode
        source_relative = self._dependency_artifact(node, kind=EXPRESSION_SOURCE_KIND)
        source = self._read(source_relative)
        if mode == "chroma":
            data, facts = apply_chroma_transparency(source)
            derivation: dict[str, object] = {"mode": "chroma", **asdict(facts)}
        elif mode == "native":
            transparent_pixels, nontransparent_pixels = _native_alpha_counts(source)
            data, normalization = normalize_png_cover(
                source, width=SPRITE_WIDTH, height=SPRITE_HEIGHT
            )
            derivation = {
                "mode": "native",
                "source_sha256": content_sha256(source),
                "transparent_pixels": transparent_pixels,
                "nontransparent_pixels": nontransparent_pixels,
                "alpha_canonicalization": asdict(normalization),
            }
        else:
            raise ValueError("ai transparency canonicalization is a matte node")
        if mode != "native":
            data, edge_facts = decontaminate_magenta_edges(data)
            derivation["edge_decontamination"] = {
                "version": MAGENTA_EDGE_DECONTAMINATION_VERSION,
                **edge_facts.as_dict(),
            }
            derivation["chroma_matte_version"] = CHROMA_MATTE_VERSION
        return await self._finish_sprite(
            node, state, source_relative, data, derivation, attempts=1, provider_operations=0
        )

    async def _canonicalize_matte(self, node: Node) -> NodeExecutionResult:
        state = self._node_state(node)
        source_relative = self._dependency_artifact(node, kind=EXPRESSION_SOURCE_KIND)
        source = self._read(source_relative)
        data, derivation, attempts = await self._remove_background(node, state, source)
        data, edge_facts = decontaminate_magenta_edges(data)
        derivation["edge_decontamination"] = {
            "version": MAGENTA_EDGE_DECONTAMINATION_VERSION,
            **edge_facts.as_dict(),
        }
        return await self._finish_sprite(
            node,
            state,
            source_relative,
            data,
            derivation,
            attempts=attempts,
            provider_operations=attempts,
        )

    async def _finish_sprite(
        self,
        node: Node,
        state: ExpressionState,
        source_relative: str,
        data: bytes,
        derivation: dict[str, object],
        *,
        attempts: int,
        provider_operations: int,
    ) -> NodeExecutionResult:
        await self._write_local(
            node.port("sprite").artifact_ref,
            data,
            "image/png",
            "Canonicalize dialogue sprite transparency.",
            refs=[source_relative],
            params={
                "derivation": derivation,
                **self._profile_provenance(self._node_actor(node)),
            },
            attempts=attempts,
        )
        return self._result(node, attempts=attempts, provider_operations=provider_operations)

    async def _remove_background(
        self, node: Node, state: ExpressionState, source: bytes
    ) -> tuple[bytes, dict[str, object], int]:
        if self._background is None:
            raise ValueError("ai transparency requires an injected background-removal service")
        removed_relative = node.port("matte").artifact_ref
        prompt = self._card_prompt(node)
        request = BackgroundRemovalRequest(
            image_url=_data_url(source),
            artifact_path=self._run_dir / removed_relative,
            metadata={
                "recipe": self._scene.recipe_version,
                "node": node.node_id,
                "state": state,
                **self._profile_provenance(self._node_actor(node)),
            },
            timeout_seconds=self._timeout,
            validate=_background_validator(
                source=source,
                width=SPRITE_WIDTH,
                height=SPRITE_HEIGHT,
                recipe_contract=self._scene.recipe_version,
            ),
            provenance_schema_version=2,
        )
        service = self._background
        result = await self._provider_call(
            node, state, prompt, [source], lambda: service.remove(request), removed_relative
        )
        data, facts = compose_source_with_alpha(
            source,
            removed_data=result.data,
            mask_data=result.mask.data if result.mask is not None else None,
        )
        derivation: dict[str, object] = {
            "mode": "ai",
            "background_removal_path": removed_relative,
            "background_removal_sha256": content_sha256(result.data),
            **asdict(facts),
        }
        return data, derivation, result.attempts

    async def _bundle(self, node: Node) -> NodeExecutionResult:
        """Merge every node's attempts in graph order, then write the portable bundle."""

        records: list[AttemptRecord] = []
        for graph_node in self._graph.nodes:
            path = self._run_dir / "attempts" / f"{graph_node.node_id}.json"
            if not path.is_file():
                continue
            ledger = AttemptLedger.model_validate_json(path.read_text(encoding="utf-8"))
            records.extend(ledger.attempts)
        atomic_write_json(
            self._run_dir / "attempts.json",
            AttemptLedger(attempts=records).model_dump(mode="json", exclude_none=True),
        )
        await write_dialogue_bundle(self._run_dir, tag=self._scene.scene_id)
        return self._result(node, provider_operations=0)

    # ---------------------------------------------------------------- helpers

    def _parse_plan(self, actor: ResolvedSceneActor, value: object) -> DialoguePlan:
        scene = self._scene
        draft = DialogueScenePlanDraft.model_validate(value)
        states = [
            ExpressionDirection(id=state, direction=draft.states.for_state(state))
            for state in EXPRESSION_STATES
        ]
        native = scene.request.transparency_mode == "native"
        profile = actor.profile
        identity, wardrobe = profile_lock_values(profile.profile)
        return DialogueScenePlan(
            schema_version=6,
            kind="dialogue-scene-plan-v6",
            recipe_version="dialogue-scene-v7",
            policy_version="coming-of-age-nonexplicit-v3",
            expression_profile="expression-core-v3",
            request_sha256=scene.request_sha256,
            appearance_id=profile.profile.profile_id,
            character_profile_ref=profile.ref,
            character_profile_source_sha256=profile.source_sha256,
            character_profile_sha256=profile.canonical_sha256,
            identity_reference_sha256=(
                actor.identity_reference.sha256
                if actor.identity_reference is not None
                else scene.style_reference.sha256
            ),
            shared_locks=SharedLocks(
                identity=identity,
                wardrobe=wardrobe,
                pose=draft.shared_locks.pose,
                lighting=draft.shared_locks.lighting,
                style=draft.shared_locks.style,
            ),
            geometry=SpriteGeometry(),
            states=states,
            prompt_templates=[
                PromptTemplateBinding(
                    id="profile-native-neutral-v1" if native else "profile-neutral-v1",
                    sha256=scene.template_digest,
                ),
                PromptTemplateBinding(
                    id=(
                        "profile-native-expression-edit-v1"
                        if native
                        else "profile-expression-edit-v1"
                    ),
                    sha256=scene.template_digest,
                ),
            ],
        )

    async def _image(
        self,
        node: Node,
        role: str,
        prompt: str,
        output: str,
        references: tuple[tuple[bytes, str], ...],
        *,
        alpha: bool,
    ) -> Any:
        scene = self._scene
        native = scene.request.transparency_mode == "native"
        sprite = role not in {"concept", "background"}
        width, height = (
            (BACKGROUND_WIDTH, BACKGROUND_HEIGHT)
            if role == "background"
            else (SPRITE_WIDTH, SPRITE_HEIGHT)
        )
        provider_width, provider_height = (
            (NATIVE_BACKGROUND_WIDTH, NATIVE_BACKGROUND_HEIGHT)
            if native and role == "background"
            else (width, height)
        )
        asset_kind: ImageAssetKind = (
            "concept_art"
            if role == "concept"
            else "environment_background"
            if role == "background"
            else "character_sprite"
        )
        anchor = self._style_anchor()
        request = ImageGenerationRequest(
            prompt=prompt,
            artifact_path=self._run_dir / output,
            input_references=tuple(_image_reference(data, path) for data, path in references),
            aspect_ratio="2:3" if sprite else "auto",
            quality="high",
            background="transparent" if sprite and native else "opaque",
            output_format="png" if native else None,
            size=f"{provider_width}x{provider_height}" if native else None,
            metadata={
                "recipe": scene.recipe_version,
                "node": node.node_id,
                "role": role,
                "width": width,
                "height": height,
                **(
                    {"provider_width": provider_width, "provider_height": provider_height}
                    if native
                    else {}
                ),
                **(
                    {}
                    if node.params.get("actor") is None
                    else self._profile_provenance(self._node_actor(node))
                ),
            },
            timeout_seconds=self._timeout,
            validate=_image_validator(
                alpha=alpha,
                width=provider_width,
                height=provider_height,
                chroma=sprite and scene.request.transparency_mode == "chroma",
                recipe_contract=scene.recipe_version,
            ),
            provenance_schema_version=2,
            prompt_anchor=compile_style_prompt_anchor(anchor, asset_kind),
        )
        return await self._provider_call(
            node,
            role,
            append_style_anchor_once(prompt, anchor, asset_kind),
            [data for data, _path in references],
            lambda: self._images.generate(request),
            output,
        )

    async def _provider_call(
        self,
        node: Node,
        role: str,
        prompt: str,
        references: Sequence[bytes],
        call: Callable[[], Any],
        artifact: str,
    ) -> Any:
        try:
            result = await call()
        except RetryExhaustedError as error:
            self._write_attempts(
                node,
                _rejected_records(node.node_id, role, prompt, references, error.attempts),
            )
            raise
        self._write_attempts(
            node,
            [
                *_rejected_records(node.node_id, role, prompt, references, result.attempts - 1),
                AttemptRecord(
                    stage=node.node_id,
                    role=role,
                    attempt=result.attempts,
                    outcome="selected",
                    provider=result.provider,
                    model=result.model,
                    artifact=artifact,
                    artifact_sha256=content_sha256(self._read(artifact)),
                    prompt_sha256=content_sha256(prompt.encode()),
                    reference_sha256=[content_sha256(value) for value in references],
                ),
            ],
        )
        return result

    def _write_attempts(self, node: Node, records: Sequence[AttemptRecord]) -> None:
        atomic_write_json(
            self._run_dir / "attempts" / f"{node.node_id}.json",
            AttemptLedger(attempts=list(records)).model_dump(mode="json", exclude_none=True),
        )

    async def _write_local(
        self,
        relative: str,
        data: bytes,
        media_type: str,
        prompt: str,
        *,
        refs: list[str] | None = None,
        inputs: list[InputProvenance] | None = None,
        params: dict[str, object] | None = None,
        attempts: int = 1,
        rights: ArtifactRights | None = None,
    ) -> str:
        scene = self._scene
        provenance = await write_artifact_with_provenance_async(
            self._run_dir / relative,
            BinaryArtifact(data=data, media_type=media_type),
            ProvenanceInput(
                schema_version=2,
                provider="local",
                model=f"deterministic-{scene.recipe_version}",
                prompt=prompt,
                refs=refs or [],
                inputs=inputs or [],
                params=params or {},
                validation={"nonempty": True},
                component=_COMPONENT,
                tool=STAGE_GEN_TOOL,
                attempts=attempts,
                rights=rights
                or ArtifactRights(status="unreviewed", attribution=[], basis=[], reviewed_at=None),
            ),
        )
        return self._relative(provenance)

    def _result(
        self, node: Node, *, attempts: int = 1, provider_operations: int
    ) -> NodeExecutionResult:
        refs: list[str] = []
        for port in node.ports:
            refs.append(port.artifact_ref)
            if port.sidecar_ref is not None:
                refs.append(port.sidecar_ref)
        artifacts = tuple(
            NodeArtifact(
                artifact_ref=ref,
                sha256=content_sha256(self._read(ref)),
                bytes=len(self._read(ref)),
            )
            for ref in refs
            if (self._run_dir / ref).is_file()
        )
        return NodeExecutionResult(
            cache=CacheDisposition.MISS,
            attempts=attempts,
            provider_operations=provider_operations,
            artifacts=artifacts,
        )

    def _card_prompt(self, node: Node) -> str:
        """The plan is the single source of a node's static instruction text."""

        if node.card is None or node.card.prompt is None:
            raise ValueError(f"node {node.node_id} declares no card prompt")
        return node.card.prompt

    def _dependency_artifact(self, node: Node, *, kind: str) -> str:
        """Resolve one typed input to the artifact ref its producer declared."""

        _producer, port = dependency_port(self._graph, node, kind=kind)
        return port.artifact_ref

    def _read(self, relative: str) -> bytes:
        return resolve_relative_path_within_root(
            self._run_dir, relative, "dialogue artifact path"
        ).read_bytes()

    def _relative(self, path: str | Path) -> str:
        return Path(path).resolve().relative_to(self._run_dir.resolve()).as_posix()

    def _style_anchor(self) -> CanonicalStyleAnchor:
        return CanonicalStyleAnchor.model_validate_json(self._read("style-anchor.json"))

    def _plan_document(self, actor: ResolvedSceneActor) -> DialoguePlan:
        return DialogueScenePlan.model_validate_json(self._read(f"plans/{actor.asset_prefix}.json"))

    def _profile_provenance(self, actor: ResolvedSceneActor) -> dict[str, object]:
        profile = actor.profile
        path = f"characters/{actor.asset_prefix}.json"
        artifact = self._read(path)
        provenance = self._read(f"{path}.meta.json")
        return {
            "actor_id": actor.actor_id,
            "character_profile_ref": profile.ref,
            "character_profile_source_sha256": profile.source_sha256,
            "character_profile_path": path,
            "character_profile_sha256": content_sha256(artifact),
            "character_profile_provenance_path": f"{path}.meta.json",
            "character_profile_provenance_sha256": content_sha256(provenance),
        }

    def _style_provenance(self) -> dict[str, object]:
        anchor = self._style_anchor()
        artifact = self._read("style-anchor.json")
        provenance = self._read("style-anchor.json.meta.json")
        return {
            "style_anchor_path": "style-anchor.json",
            "style_anchor_artifact_sha256": content_sha256(artifact),
            "style_anchor_provenance_path": "style-anchor.json.meta.json",
            "style_anchor_provenance_sha256": content_sha256(provenance),
            "style_anchor_sha256": canonical_style_anchor_digest(anchor),
            "style_compiler_sha256": anchor.compiler_sha256,
            "style_compiler_version": anchor.compiler_version,
            "style_resource_sha256": anchor.resource_sha256,
            "style_skill_sha256": anchor.skill_sha256,
            "style_vocabulary_sha256": anchor.vocabulary_sha256,
        }


def _rejected_records(
    node_id: str, role: str, prompt: str, references: Sequence[bytes], count: int
) -> list[AttemptRecord]:
    prompt_digest = content_sha256(prompt.encode())
    reference_digests = [content_sha256(value) for value in references]
    return [
        AttemptRecord(
            stage=node_id,
            role=role,
            attempt=ordinal,
            outcome="rejected",
            prompt_sha256=prompt_digest,
            reference_sha256=reference_digests,
            reason="service retry rejected the candidate",
        )
        for ordinal in range(1, count + 1)
    ]


def _data_url(data: bytes) -> str:
    return f"data:image/png;base64,{base64.b64encode(data).decode('ascii')}"


def _image_reference(data: bytes, path: str) -> ImageReference:
    return ImageReference(
        url=_data_url(data), provenance_ref=f"{path}#sha256={content_sha256(data)}"
    )


def _structured_reference(data: bytes, path: str) -> StructuredReference:
    return StructuredReference(
        url=_data_url(data), provenance_ref=f"{path}#sha256={content_sha256(data)}"
    )


def _image_validator(
    *, alpha: bool, width: int, height: int, chroma: bool, recipe_contract: str
) -> Callable[[BinaryArtifact], dict[str, object]]:
    def validate(artifact: BinaryArtifact) -> dict[str, object]:
        facts = inspect_image(artifact.data, expected_media_type="image/png")
        if (facts.width, facts.height) != (width, height):
            raise ValueError(
                f"dialogue image dimensions must be {width}x{height}; "
                f"received {facts.width}x{facts.height}"
            )
        validation: dict[str, object] = {
            "width": facts.width,
            "height": facts.height,
            "alpha": facts.has_alpha,
            "recipe_contract": recipe_contract,
        }
        if chroma:
            _output, chroma_facts = apply_chroma_transparency(artifact.data)
            validation["chroma_transparent_pixels"] = chroma_facts.transparent_pixels
            validation["chroma_nontransparent_pixels"] = chroma_facts.nontransparent_pixels
        if alpha:
            transparent_pixels, nontransparent_pixels = _native_alpha_counts(artifact.data)
            validation["transparent_pixels"] = transparent_pixels
            validation["nontransparent_pixels"] = nontransparent_pixels
        return validation

    return validate


def _native_alpha_counts(data: bytes) -> tuple[int, int]:
    facts = inspect_image(data, expected_media_type="image/png")
    if not facts.has_alpha:
        raise ValueError("dialogue image requires native alpha")
    with Image.open(BytesIO(data)) as opened:
        alpha = opened.convert("RGBA").getchannel("A").tobytes()
    transparent_pixels = sum(value < 255 for value in alpha)
    nontransparent_pixels = sum(value > 0 for value in alpha)
    if (
        transparent_pixels == 0
        or nontransparent_pixels == 0
        or min(alpha) != 0
        or max(alpha) < NATIVE_ALPHA_OPAQUE_THRESHOLD
    ):
        raise ValueError(
            "dialogue native alpha must contain fully transparent and substantially opaque "
            "visible pixels"
        )
    return transparent_pixels, nontransparent_pixels


def _background_validator(
    *, source: bytes, width: int, height: int, recipe_contract: str
) -> Callable[[BinaryArtifact, BackgroundMaskArtifact | None], dict[str, object]]:
    def validate(
        artifact: BinaryArtifact, mask: BackgroundMaskArtifact | None
    ) -> dict[str, object]:
        composed, alpha_facts = compose_source_with_alpha(
            source,
            removed_data=artifact.data,
            mask_data=mask.data if mask is not None else None,
        )
        facts = inspect_image(composed, expected_media_type="image/png")
        if (facts.width, facts.height) != (width, height):
            raise ValueError(
                f"dialogue removal dimensions must be {width}x{height}; "
                f"received {facts.width}x{facts.height}"
            )
        return {
            "width": facts.width,
            "height": facts.height,
            "alpha": facts.has_alpha,
            "transparent_pixels": alpha_facts.transparent_pixels,
            "nontransparent_pixels": alpha_facts.nontransparent_pixels,
            "recipe_contract": recipe_contract,
        }

    return validate


__all__ = ["DialogueSceneNodeHandler", "scene_target_node_ids"]
