"""Provider-neutral dialogue recipe executor composed from generic services."""

from __future__ import annotations

import asyncio
import base64
import os
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from stage_gen.components import (
    BackgroundMaskArtifact,
    BackgroundRemovalRequest,
    BackgroundRemovalResult,
    CanonicalStyleAnchor,
    CharacterProfile,
    ImageAssetKind,
    ImageGenerationRequest,
    ImageGenerationResult,
    ImageReference,
    ResolvedCharacterProfile,
    StructuredGenerationRequest,
    StructuredGenerationResult,
    StructuredOutputSchema,
    StructuredReference,
    append_style_anchor_once,
    canonical_style_anchor_digest,
    character_profile_sha256,
    resolve_character_profile_binding,
)
from stage_gen.contracts import (
    ArtifactRights,
    BinaryArtifact,
    InputProvenance,
    ProvenanceInput,
    SoftwareIdentity,
)
from stage_gen.image_prompting import (
    build_image_style_compiler_request,
    image_style_compiler_cache_key,
    load_image_style_resources,
)
from stage_gen.media import (
    CHROMA_MATTE_VERSION,
    MAGENTA_EDGE_DECONTAMINATION_VERSION,
    apply_chroma_transparency,
    compose_source_with_alpha,
    decontaminate_magenta_edges,
    inspect_image,
)
from stage_gen.recipes.base import StageContext
from stage_gen.recipes.dialogue_scene.cache import DialogueStageCache
from stage_gen.recipes.dialogue_scene.identity import (
    canonical_json_bytes,
    canonical_sha256,
    content_sha256,
)
from stage_gen.recipes.dialogue_scene.models import (
    EXPRESSION_STATES,
    AttemptLedger,
    AttemptRecord,
    DialoguePlan,
    DialogueRequest,
    DialogueScenePlan,
    DialogueScenePlanDraft,
    DialogueScenePlanV3,
    DialogueThemeRequest,
    DialogueThemeRequestV3,
    ExpressionDirection,
    PromptTemplateBinding,
    ReuseSource,
    SharedLocks,
    SpriteGeometry,
)
from stage_gen.recipes.dialogue_scene.policy import (
    POLICY_DIGEST,
    assert_character_profile_policy,
    assert_dialogue_policy,
)
from stage_gen.recipes.dialogue_scene.prompts import (
    PROFILE_TEMPLATE_DIGEST,
    TEMPLATE_DIGEST,
    background_prompt,
    concept_prompt,
    expression_prompt,
    neutral_prompt,
    plan_prompt,
)
from stage_gen.recipes.dialogue_scene.schema import dialogue_plan_json_schema
from stage_gen.reliability import (
    RetryExhaustedError,
    atomic_write_json,
    resolve_relative_path_within_root,
    write_artifact_with_provenance_async,
)

_COMPONENT = SoftwareIdentity(name="@stage-gen/dialogue-scene", version="3")
_COMPONENT_V4 = SoftwareIdentity(name="@stage-gen/dialogue-scene", version="4")
_STYLE_ASSET_KINDS: tuple[ImageAssetKind, ...] = (
    "concept_art",
    "environment_background",
    "character_sprite",
)


class StructuredService(Protocol):
    async def generate(
        self, request: StructuredGenerationRequest[Any]
    ) -> StructuredGenerationResult[Any]: ...


class ImageService(Protocol):
    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult: ...


class BackgroundService(Protocol):
    async def remove(self, request: BackgroundRemovalRequest) -> BackgroundRemovalResult: ...


@dataclass(frozen=True, slots=True)
class DialogueExecutorContext:
    structured: StructuredService
    images: ImageService
    background: BackgroundService | None = None
    force_stages: frozenset[str] = field(default_factory=frozenset)


class DialogueSceneExecutor:
    """Owns prompts, lineage, post-processing, and the portable bundle inputs."""

    def __init__(self, services: DialogueExecutorContext) -> None:
        unknown = services.force_stages - {
            "prepare",
            "profile-resolve",
            "style-selection",
            "appearance-concept",
            "scene-plan",
            "background",
            "neutral",
            "expressions",
            "canonicalize",
            "bundle",
        }
        if unknown:
            raise ValueError(f"unknown forced dialogue stages: {', '.join(sorted(unknown))}")
        self._services = services
        self._style_resources = load_image_style_resources()

    async def run_stage(self, stage_name: str, context: StageContext) -> Sequence[str]:
        """Implement the generic recipe-executor protocol."""

        return await self.run_dialogue_scene_stage(stage_name, context)

    async def run_dialogue_scene_stage(
        self, stage_name: str, context: StageContext
    ) -> Sequence[str]:
        handlers: dict[str, Callable[[StageContext], Awaitable[tuple[str, ...]]]] = {
            "prepare": self._prepare,
            "profile-resolve": self._profile_resolve,
            "style-selection": self._style_selection,
            "appearance-concept": self._appearance_concept,
            "scene-plan": self._scene_plan,
            "background": self._background,
            "neutral": self._neutral,
            "expressions": self._expressions,
            "canonicalize": self._canonicalize,
            "bundle": self._bundle,
        }
        try:
            handler = handlers[stage_name]
        except KeyError as error:
            raise ValueError(f"unknown dialogue-scene stage: {stage_name}") from error
        cache = DialogueStageCache(context.run_dir)
        request = _request(context)
        dependency_paths = _cache_dependencies(stage_name, request)
        dependencies = cache.dependency_digests(dependency_paths) if dependency_paths else {}
        cache_inputs: dict[str, object] = {
            "request": canonical_sha256(request),
            "policy": POLICY_DIGEST,
            "templates": _template_digest(request),
        }
        if isinstance(request, DialogueThemeRequestV3):
            resolved = _resolve_dialogue_profile(context, request.character_profile)
            cache_inputs["character_profile_source_sha256"] = content_sha256(resolved.source_bytes)
            cache_inputs["character_profile_sha256"] = resolved.canonical_sha256
        if stage_name != "prepare":
            cache_inputs.update(
                {
                    "style_compiler_sha256": self._style_resources.compiler_sha256,
                    "style_resource_sha256": self._style_resources.resource_sha256,
                }
            )
        if stage_name == "style-selection":
            cache_inputs["style_selection"] = image_style_compiler_cache_key(
                _style_selection_brief(context, request),
                _STYLE_ASSET_KINDS,
                resources=self._style_resources,
            )
        if stage_name == "canonicalize":
            cache_inputs["magenta_edge_decontamination_version"] = (
                MAGENTA_EDGE_DECONTAMINATION_VERSION
            )
            if request.transparency_mode == "chroma":
                cache_inputs["chroma_matte_version"] = CHROMA_MATTE_VERSION
        key = cache.key(
            stage_name,
            inputs=cache_inputs,
            dependencies=dependencies,
            recipe_version=_recipe_version(request),
            contract_schema_version=request.schema_version,
        )
        forced = (
            os.environ.get("STAGE_GEN_FORCE") == "1"
            or stage_name in self._services.force_stages
            or stage_name in context.force_stages
        )
        cached = cache.load(stage_name, key, force=forced)
        if cached is not None:
            return cached
        artifacts = tuple(await handler(context))
        stable_artifacts = tuple(path for path in artifacts if path != "attempts.json")
        cache.store(stage_name, key, stable_artifacts)
        return artifacts

    async def _prepare(self, context: StageContext) -> tuple[str, ...]:
        request = _request(context)
        assert_dialogue_policy(request)
        artifacts: list[str] = ["request.json", "request.json.meta.json", "attempts.json"]
        if isinstance(request, DialogueThemeRequest) and isinstance(
            request.appearance.concept, ReuseSource
        ):
            artifacts.extend(
                await self._ingest_reuse(context, request.appearance.concept, "concept")
            )
        if isinstance(request.background, ReuseSource):
            artifacts.extend(await self._ingest_reuse(context, request.background, "background"))
        await _write_local_json(context, "request.json", request, "canonical dialogue request")
        if not (context.run_dir / "attempts.json").exists():
            atomic_write_json(
                context.run_dir / "attempts.json",
                AttemptLedger().model_dump(mode="json"),
            )
        return tuple(artifacts)

    async def _profile_resolve(self, context: StageContext) -> tuple[str, ...]:
        request = _request(context)
        if not isinstance(request, DialogueThemeRequestV3):
            raise ValueError("profile-resolve requires dialogue-theme-request-v3")
        resolved = _resolve_dialogue_profile(context, request.character_profile)
        rights = resolved.profile.rights
        provenance = await _write_local_bytes(
            context,
            "character-profile.json",
            resolved.canonical_bytes,
            "application/json",
            "Validate and canonicalize the authored character profile.",
            refs=[resolved.binding.ref],
            inputs=[resolved.source_provenance],
            params={
                "character_profile_ref": resolved.binding.ref,
                "character_profile_source_sha256": resolved.binding.source_sha256,
                "character_profile_sha256": resolved.canonical_sha256,
                "profile_id": resolved.profile.profile_id,
                "revision": resolved.profile.revision,
            },
            rights=ArtifactRights(
                status=rights.status,
                license_id=rights.license_id,
                notice=rights.notice,
                attribution=rights.attribution,
                basis=rights.basis,
                reviewed_at=rights.reviewed_at,
            ),
        )
        return ("character-profile.json", provenance)

    async def _style_selection(self, context: StageContext) -> tuple[str, ...]:
        compiler_request = build_image_style_compiler_request(
            prompt=_style_selection_brief(context, _request(context)),
            artifact_path=context.run_dir / "style-anchor.json",
            asset_kinds=_STYLE_ASSET_KINDS,
            resources=self._style_resources,
            timeout_seconds=context.config.capability_timeout_s,
            cancellation=context.cancellation,
        )
        try:
            result = await self._services.structured.generate(compiler_request)
        except RetryExhaustedError as error:
            _record_exhausted(
                context,
                "style-selection",
                "style-anchor",
                compiler_request.prompt,
                error.attempts,
                [],
            )
            raise
        _record_selected(
            context,
            "style-selection",
            "style-anchor",
            compiler_request.prompt,
            result.attempts,
            "style-anchor.json",
            result.provider,
            result.model,
            [],
        )
        return (
            "style-anchor.json",
            _relative(context, result.provenance_path),
            "attempts.json",
        )

    async def _appearance_concept(self, context: StageContext) -> tuple[str, ...]:
        request = _request(context)
        output = "assets/concept.png"
        if isinstance(request, DialogueThemeRequest) and isinstance(
            request.appearance.concept, ReuseSource
        ):
            return await self._copy_ingested(context, "refs/concept", output, "concept reuse")
        # Concept precedes the structured plan; identity direction is caller-owned and style is
        # appended exactly once by the image component from the canonical anchor.
        prompt = concept_prompt(request, _profile(context))
        result = await self._image_call(
            context, "appearance-concept", "concept", prompt, output, (), alpha=False
        )
        return (output, _relative(context, result.provenance_path))

    async def _scene_plan(self, context: StageContext) -> tuple[str, ...]:
        request = _request(context)
        request_digest = canonical_sha256(request)
        concept = _read(context, "assets/concept.png")
        reference = _structured_reference(concept, "assets/concept.png")

        profile = _profile(context)

        def parse(value: object) -> DialoguePlan:
            draft = DialogueScenePlanDraft.model_validate(value)
            if isinstance(request, DialogueThemeRequestV3):
                assert profile is not None
                identity, wardrobe = _profile_lock_values(profile)
                return DialogueScenePlanV3(
                    schema_version=3,
                    kind="dialogue-scene-plan-v3",
                    recipe_version="dialogue-scene-v4",
                    policy_version="adult-romance-nonexplicit-v2",
                    expression_profile="romance-core-v2",
                    request_sha256=request_digest,
                    appearance_id=profile.profile_id,
                    character_profile_ref=request.character_profile.ref,
                    character_profile_source_sha256=request.character_profile.source_sha256,
                    character_profile_sha256=character_profile_sha256(profile),
                    shared_locks=SharedLocks(
                        identity=identity,
                        wardrobe=wardrobe,
                        pose=draft.shared_locks.pose,
                        lighting=draft.shared_locks.lighting,
                        style=draft.shared_locks.style,
                    ),
                    geometry=SpriteGeometry(),
                    states=[
                        ExpressionDirection(id=state, direction=draft.states.for_state(state))
                        for state in EXPRESSION_STATES
                    ],
                    prompt_templates=[
                        PromptTemplateBinding(
                            id="profile-neutral-v1", sha256=PROFILE_TEMPLATE_DIGEST
                        ),
                        PromptTemplateBinding(
                            id="profile-expression-edit-v1", sha256=PROFILE_TEMPLATE_DIGEST
                        ),
                    ],
                )
            return DialogueScenePlan(
                schema_version=2,
                kind="dialogue-scene-plan-v2",
                recipe_version="dialogue-scene-v3",
                policy_version="adult-romance-nonexplicit-v2",
                expression_profile="romance-core-v2",
                request_sha256=request_digest,
                appearance_id=request.appearance.id,
                shared_locks=SharedLocks(
                    identity=(
                        f"{request.appearance.label}, adult age {request.appearance.age}. "
                        "Required appearance and wardrobe: "
                        f"{request.appearance.description}."
                    ),
                    wardrobe=(
                        "Required wardrobe and appearance details: "
                        f"{request.appearance.description}. Do not replace specified clothing "
                        "with occupation-associated attire."
                    ),
                    pose=draft.shared_locks.pose,
                    lighting=draft.shared_locks.lighting,
                    style=draft.shared_locks.style,
                ),
                geometry=SpriteGeometry(),
                states=[
                    ExpressionDirection(id=state, direction=draft.states.for_state(state))
                    for state in EXPRESSION_STATES
                ],
                prompt_templates=[
                    PromptTemplateBinding(id="neutral-v5", sha256=TEMPLATE_DIGEST),
                    PromptTemplateBinding(id="expression-edit-v5", sha256=TEMPLATE_DIGEST),
                ],
            )

        prompt = plan_prompt(request, request_digest, profile)
        try:
            result = await self._services.structured.generate(
                StructuredGenerationRequest(
                    prompt=prompt,
                    system=(
                        "Return only the strict dialogue-scene-plan JSON. Do not add story, "
                        "dialogue, provider instructions, paths, or policy exceptions."
                    ),
                    artifact_path=context.run_dir / "plan.json",
                    references=(reference,),
                    schema=StructuredOutputSchema(
                        name=(
                            "dialogue_scene_plan_v3"
                            if isinstance(request, DialogueThemeRequestV3)
                            else "dialogue_scene_plan_v2"
                        ),
                        json_schema=dialogue_plan_json_schema(),
                        strict=True,
                    ),
                    parse=parse,
                    artifact_value=lambda value: value.model_dump(mode="json", exclude_none=True),
                    metadata={
                        "stage": "scene-plan",
                        "request_sha256": request_digest,
                        "policy_sha256": POLICY_DIGEST,
                        "template_sha256": _template_digest(request),
                        **(_profile_provenance(context) if profile is not None else {}),
                        **_style_provenance(context, _style_anchor(context)),
                    },
                    timeout_seconds=context.config.capability_timeout_s,
                    cancellation=context.cancellation,
                    provenance_schema_version=2,
                )
            )
        except RetryExhaustedError as error:
            _record_exhausted(context, "scene-plan", "plan", prompt, error.attempts, [concept])
            raise
        _record_selected(
            context,
            "scene-plan",
            "plan",
            prompt,
            result.attempts,
            "plan.json",
            result.provider,
            result.model,
            [concept],
        )
        return ("plan.json", _relative(context, result.provenance_path), "attempts.json")

    async def _background(self, context: StageContext) -> tuple[str, ...]:
        request, plan = _request(context), _plan(context)
        output = "assets/background.png"
        if isinstance(request.background, ReuseSource):
            return await self._copy_ingested(context, "refs/background", output, "background reuse")
        prompt = background_prompt(request, plan)
        result = await self._image_call(
            context, "background", "background", prompt, output, (), alpha=False
        )
        return (output, _relative(context, result.provenance_path), "attempts.json")

    async def _neutral(self, context: StageContext) -> tuple[str, ...]:
        request, plan = _request(context), _plan(context)
        concept = _read(context, "assets/concept.png")
        result = await self._image_call(
            context,
            "neutral",
            "neutral",
            neutral_prompt(request, plan),
            "raw/expression-neutral.png",
            ((concept, "assets/concept.png"),),
            alpha=False,
        )
        return (
            "raw/expression-neutral.png",
            _relative(context, result.provenance_path),
            "attempts.json",
        )

    async def _expressions(self, context: StageContext) -> tuple[str, ...]:
        plan = _plan(context)
        neutral = _read(context, "raw/expression-neutral.png")
        artifacts: list[str] = []
        for state in EXPRESSION_STATES[1:]:
            output = f"raw/expression-{state}.png"
            result = await self._image_call(
                context,
                "expressions",
                state,
                expression_prompt(state, plan),
                output,
                ((neutral, "raw/expression-neutral.png"),),
                alpha=False,
            )
            artifacts.extend((output, _relative(context, result.provenance_path)))
        artifacts.append("attempts.json")
        return tuple(artifacts)

    async def _canonicalize(self, context: StageContext) -> tuple[str, ...]:
        request = _request(context)
        artifacts: list[str] = []
        for state in EXPRESSION_STATES:
            source_relative = f"raw/expression-{state}.png"
            source = _read(context, source_relative)
            output = f"assets/expression-{state}.png"
            if request.transparency_mode == "chroma":
                data, facts = apply_chroma_transparency(source)
                attempts = 1
                derivation = {"mode": "chroma", **asdict(facts)}
            else:
                if self._services.background is None:
                    raise ValueError("ai transparency requires an injected background service")
                removed_relative = f"raw/expression-{state}.removed.png"
                prompt = "Remove the background while preserving the adult character."
                try:
                    result = await self._services.background.remove(
                        BackgroundRemovalRequest(
                            image_url=_data_url(source),
                            artifact_path=context.run_dir / removed_relative,
                            metadata={
                                "recipe": _recipe_version(request),
                                "stage": "canonicalize",
                                "state": state,
                                **(
                                    _profile_provenance(context)
                                    if isinstance(request, DialogueThemeRequestV3)
                                    else {}
                                ),
                            },
                            timeout_seconds=context.config.capability_timeout_s,
                            cancellation=context.cancellation,
                            validate=_background_validator(
                                source=source,
                                width=1024,
                                height=1536,
                                recipe_contract=_recipe_version(request),
                            ),
                            provenance_schema_version=2,
                        )
                    )
                except RetryExhaustedError as error:
                    _record_exhausted(
                        context, "canonicalize", state, prompt, error.attempts, [source]
                    )
                    raise
                _record_selected(
                    context,
                    "canonicalize",
                    state,
                    prompt,
                    result.attempts,
                    removed_relative,
                    result.provider,
                    result.model,
                    [source],
                )
                data, facts = compose_source_with_alpha(
                    source,
                    removed_data=result.data,
                    mask_data=result.mask.data if result.mask is not None else None,
                )
                attempts = result.attempts
                derivation = {
                    "mode": "ai",
                    "background_removal_path": removed_relative,
                    "background_removal_sha256": content_sha256(result.data),
                    **asdict(facts),
                }
                artifacts.extend((removed_relative, _relative(context, result.provenance_path)))
            data, edge_facts = decontaminate_magenta_edges(data)
            derivation["edge_decontamination"] = {
                "version": MAGENTA_EDGE_DECONTAMINATION_VERSION,
                **edge_facts.as_dict(),
            }
            provenance = await _write_local_bytes(
                context,
                output,
                data,
                "image/png",
                "Canonicalize dialogue sprite transparency.",
                refs=[source_relative],
                params={
                    "derivation": derivation,
                    **(_profile_provenance(context) if _profile(context) is not None else {}),
                },
                attempts=attempts,
            )
            artifacts.extend((output, provenance))
        artifacts.append("attempts.json")
        return tuple(artifacts)

    async def _bundle(self, context: StageContext) -> tuple[str, ...]:
        from stage_gen.recipes.dialogue_scene.manifest import write_dialogue_bundle

        result = await write_dialogue_bundle(context)
        return result

    async def _ingest_reuse(
        self, context: StageContext, source: ReuseSource, role: str
    ) -> tuple[str, ...]:
        if source.ref.startswith(("http://", "https://")):
            raise ValueError("dialogue reuse currently requires a caller-accessible local file")
        input_path = await asyncio.to_thread(lambda: Path(source.ref).expanduser().resolve())
        data = await asyncio.to_thread(input_path.read_bytes)
        if content_sha256(data) != source.sha256:
            raise ValueError(f"{role} reuse digest mismatch")
        facts = inspect_image(data, expected_media_type="image/png")
        relative = f"refs/{role}"
        provenance = await _write_local_bytes(
            context,
            relative,
            data,
            "image/png",
            f"Ingest caller-owned {role} reference.",
            refs=[f"sha256:{source.sha256}"],
            params={"role": role, "width": facts.width, "height": facts.height},
        )
        return relative, provenance

    async def _copy_ingested(
        self, context: StageContext, source: str, output: str, prompt: str
    ) -> tuple[str, ...]:
        data = _read(context, source)
        provenance = await _write_local_bytes(
            context, output, data, "image/png", prompt, refs=[source]
        )
        return output, provenance

    async def _image_call(
        self,
        context: StageContext,
        stage: str,
        role: str,
        prompt: str,
        output: str,
        references: tuple[tuple[bytes, str], ...],
        *,
        alpha: bool,
    ) -> ImageGenerationResult:
        image_references = tuple(_image_reference(data, path) for data, path in references)
        reference_bytes = [data for data, _path in references]
        width, height = (1672, 941) if role == "background" else (1024, 1536)
        chroma = (
            role not in {"concept", "background"}
            and _request(context).transparency_mode == "chroma"
        )
        style_anchor = _style_anchor(context)
        asset_kind: ImageAssetKind
        if role == "concept":
            asset_kind = "concept_art"
        elif role == "background":
            asset_kind = "environment_background"
        else:
            asset_kind = "character_sprite"
        provider_prompt = append_style_anchor_once(prompt, style_anchor, asset_kind)
        try:
            result = await self._services.images.generate(
                ImageGenerationRequest(
                    prompt=prompt,
                    artifact_path=context.run_dir / output,
                    input_references=image_references,
                    aspect_ratio="2:3" if role not in {"concept", "background"} else "auto",
                    quality="high",
                    background="opaque",
                    metadata={
                        "recipe": _recipe_version(_request(context)),
                        "stage": stage,
                        "role": role,
                        "width": width,
                        "height": height,
                        **(
                            _profile_provenance(context)
                            if isinstance(_request(context), DialogueThemeRequestV3)
                            else {}
                        ),
                    },
                    timeout_seconds=context.config.capability_timeout_s,
                    cancellation=context.cancellation,
                    validate=_image_validator(
                        alpha=alpha,
                        width=width,
                        height=height,
                        chroma=chroma,
                        recipe_contract=_recipe_version(_request(context)),
                    ),
                    provenance_schema_version=2,
                    style_anchor=style_anchor,
                    asset_kind=asset_kind,
                )
            )
        except RetryExhaustedError as error:
            _record_exhausted(
                context, stage, role, provider_prompt, error.attempts, reference_bytes
            )
            raise
        _record_selected(
            context,
            stage,
            role,
            provider_prompt,
            result.attempts,
            output,
            result.provider,
            result.model,
            reference_bytes,
        )
        return result


def _request(context: StageContext) -> DialogueRequest:
    request: DialogueRequest
    if context.input.get("schema_version") == 3:
        request = DialogueThemeRequestV3.model_validate(context.input)
    else:
        request = DialogueThemeRequest.model_validate(context.input)
    assert_dialogue_policy(request)
    return request


def _cache_dependencies(stage: str, request: DialogueRequest) -> tuple[str, ...]:
    states = tuple(f"raw/expression-{state}.png" for state in EXPRESSION_STATES)
    values: dict[str, tuple[str, ...]] = {
        "prepare": (),
        "profile-resolve": (),
        "style-selection": ("request.json",),
        "appearance-concept": ("request.json", "style-anchor.json"),
        "scene-plan": (
            "request.json",
            "style-anchor.json",
            "style-anchor.json.meta.json",
            "assets/concept.png",
        ),
        "background": ("request.json", "plan.json", "style-anchor.json"),
        "neutral": (
            "request.json",
            "plan.json",
            "style-anchor.json",
            "assets/concept.png",
        ),
        "expressions": (
            "plan.json",
            "style-anchor.json",
            "raw/expression-neutral.png",
        ),
        "canonicalize": ("request.json", *states),
        "bundle": (
            "request.json",
            "plan.json",
            "attempts.json",
            "style-anchor.json",
            "style-anchor.json.meta.json",
            "assets/concept.png",
            "assets/background.png",
            *(f"assets/expression-{state}.png" for state in EXPRESSION_STATES),
        ),
    }
    if isinstance(request, DialogueThemeRequestV3):
        profile_files = ("character-profile.json", "character-profile.json.meta.json")
        for name in (
            "style-selection",
            "appearance-concept",
            "scene-plan",
            "neutral",
            "expressions",
            "canonicalize",
            "bundle",
        ):
            values[name] = (*values[name], *profile_files)
    return values[stage]


def _plan(context: StageContext) -> DialoguePlan:
    data = _read(context, "plan.json")
    if _request(context).schema_version == 3:
        return DialogueScenePlanV3.model_validate_json(data)
    return DialogueScenePlan.model_validate_json(data)


def _style_anchor(context: StageContext) -> CanonicalStyleAnchor:
    return CanonicalStyleAnchor.model_validate_json(_read(context, "style-anchor.json"))


def _style_selection_brief(context: StageContext, request: DialogueRequest) -> str:
    if isinstance(request, DialogueThemeRequestV3):
        profile = _profile(context)
        if profile is None:
            resolved = _resolve_dialogue_profile(context, request.character_profile)
            profile = resolved.profile
        background_direction = getattr(request.background, "description", None)
        return canonical_json_bytes(
            {
                "scene_brief": request.scene_brief,
                "appearance_description": profile.visual_identity,
                "wardrobe": profile.wardrobe,
                "invariants": profile.invariants,
                "background_direction": background_direction,
                "character_profile_sha256": character_profile_sha256(profile),
            }
        ).decode("utf-8")
    concept_direction = getattr(request.appearance.concept, "description", None)
    background_direction = getattr(request.background, "description", None)
    return canonical_json_bytes(
        {
            "scene_brief": request.scene_brief,
            "appearance_description": request.appearance.description,
            "concept_direction": concept_direction,
            "background_direction": background_direction,
        }
    ).decode("utf-8")


def _template_digest(request: DialogueRequest) -> str:
    return (
        PROFILE_TEMPLATE_DIGEST if isinstance(request, DialogueThemeRequestV3) else TEMPLATE_DIGEST
    )


def _recipe_version(request: DialogueRequest) -> str:
    return (
        "dialogue-scene-v4" if isinstance(request, DialogueThemeRequestV3) else "dialogue-scene-v3"
    )


def _profile(context: StageContext) -> CharacterProfile | None:
    if not isinstance(_request(context), DialogueThemeRequestV3):
        return None
    return CharacterProfile.model_validate_json(_read(context, "character-profile.json"))


def _resolve_dialogue_profile(context: StageContext, binding: object) -> ResolvedCharacterProfile:
    root = context.config.character_library_root
    if root is None:
        raise ValueError("profile-enabled dialogue generation requires character_library_root")
    resolved = resolve_character_profile_binding(
        binding,
        character_library_root=root,
    )
    profile = resolved.profile
    if len(profile.profile_id) > 48:
        raise ValueError("dialogue character_profile profile_id exceeds the scene binding limit")
    if len(profile.display_name) > 96:
        raise ValueError("dialogue character_profile display_name exceeds the scene binding limit")
    if len(profile.description) > 280 or len(profile.visual_identity) > 320:
        raise ValueError("dialogue character_profile descriptive fields exceed scene limits")
    assert_character_profile_policy(profile)
    _profile_lock_values(profile)
    return resolved


def _profile_lock_values(profile: CharacterProfile) -> tuple[str, str]:
    invariants = "; ".join(profile.invariants)
    identity = (
        f"{profile.display_name}, adult age {profile.age_years}. Authoritative appearance: "
        f"{profile.visual_identity}. Character description: {profile.description}. "
        f"Required durable acceptance invariants: {invariants}."
    )
    wardrobe = (
        f"Authoritative wardrobe: {profile.wardrobe}. Required durable acceptance invariants: "
        f"{invariants}. Do not replace authored clothing with role-associated attire."
    )
    if len(identity) > 2000 or len(wardrobe) > 1000:
        raise ValueError("dialogue character_profile exceeds deterministic lock limits")
    return identity, wardrobe


def _profile_provenance(context: StageContext) -> dict[str, object]:
    request = _request(context)
    if not isinstance(request, DialogueThemeRequestV3):
        return {}
    artifact = _read(context, "character-profile.json")
    provenance = _read(context, "character-profile.json.meta.json")
    return {
        "character_profile_ref": request.character_profile.ref,
        "character_profile_source_sha256": request.character_profile.source_sha256,
        "character_profile_path": "character-profile.json",
        "character_profile_sha256": content_sha256(artifact),
        "character_profile_provenance_path": "character-profile.json.meta.json",
        "character_profile_provenance_sha256": content_sha256(provenance),
    }


def _style_provenance(context: StageContext, anchor: CanonicalStyleAnchor) -> dict[str, object]:
    artifact = _read(context, "style-anchor.json")
    provenance = _read(context, "style-anchor.json.meta.json")
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


def _read(context: StageContext, relative: str) -> bytes:
    return resolve_relative_path_within_root(
        context.run_dir, relative, "dialogue artifact path"
    ).read_bytes()


def _relative(context: StageContext, path: str | Path) -> str:
    return Path(path).resolve().relative_to(context.run_dir.resolve()).as_posix()


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
        if alpha and not facts.has_alpha:
            raise ValueError("dialogue image requires alpha")
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
        return validation

    return validate


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


async def _write_local_json(
    context: StageContext, relative: str, value: object, prompt: str
) -> str:
    return await _write_local_bytes(
        context,
        relative,
        canonical_json_bytes(value) + b"\n",
        "application/json",
        prompt,
    )


async def _write_local_bytes(
    context: StageContext,
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
    request = _request(context)
    output = context.run_dir / relative
    provenance = await write_artifact_with_provenance_async(
        output,
        BinaryArtifact(data=data, media_type=media_type),
        ProvenanceInput(
            schema_version=2,
            provider="local",
            model=f"deterministic-{_recipe_version(request)}",
            prompt=prompt,
            refs=refs or [],
            inputs=inputs or [],
            params=params or {},
            validation={"nonempty": True},
            component=(
                _COMPONENT_V4 if isinstance(request, DialogueThemeRequestV3) else _COMPONENT
            ),
            attempts=attempts,
            rights=rights
            or ArtifactRights(
                status="unreviewed",
                license_id=None,
                notice="Rights review is required before publication.",
                attribution=[],
                basis=[],
                reviewed_at=None,
            ),
        ),
    )
    return _relative(context, provenance)


def _load_ledger(context: StageContext) -> AttemptLedger:
    path = context.run_dir / "attempts.json"
    if not path.exists():
        return AttemptLedger()
    return AttemptLedger.model_validate_json(path.read_text(encoding="utf-8"))


def _append_records(context: StageContext, records: list[AttemptRecord]) -> None:
    ledger = _load_ledger(context)
    updated = ledger.model_copy(update={"attempts": [*ledger.attempts, *records]})
    atomic_write_json(
        context.run_dir / "attempts.json",
        updated.model_dump(mode="json", exclude_none=True),
    )


def _record_selected(
    context: StageContext,
    stage: str,
    role: str,
    prompt: str,
    attempts: int,
    artifact: str,
    provider: str,
    model: str,
    references: list[bytes],
) -> None:
    prompt_digest = content_sha256(prompt.encode())
    reference_digests = [content_sha256(value) for value in references]
    records = [
        AttemptRecord(
            stage=stage,
            role=role,
            attempt=ordinal,
            outcome="rejected",
            prompt_sha256=prompt_digest,
            reference_sha256=reference_digests,
            reason="service retry rejected the candidate",
        )
        for ordinal in range(1, attempts)
    ]
    records.append(
        AttemptRecord(
            stage=stage,
            role=role,
            attempt=attempts,
            outcome="selected",
            provider=provider,
            model=model,
            artifact=artifact,
            artifact_sha256=content_sha256(_read(context, artifact)),
            prompt_sha256=prompt_digest,
            reference_sha256=reference_digests,
        )
    )
    _append_records(context, records)


def _record_exhausted(
    context: StageContext,
    stage: str,
    role: str,
    prompt: str,
    attempts: int,
    references: list[bytes],
) -> None:
    _append_records(
        context,
        [
            AttemptRecord(
                stage=stage,
                role=role,
                attempt=ordinal,
                outcome="rejected",
                prompt_sha256=content_sha256(prompt.encode()),
                reference_sha256=[content_sha256(value) for value in references],
                reason="service exhausted its six-attempt retry contract",
            )
            for ordinal in range(1, attempts + 1)
        ],
    )
