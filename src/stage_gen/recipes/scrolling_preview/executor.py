"""Recipe-specific execution composed from reusable component services."""

from __future__ import annotations

import asyncio
import base64
import json
import math
import os
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path
from typing import Any, cast

from PIL import Image
from PIL import __version__ as pillow_version

from stage_gen.components import (
    BackgroundRemovalRequest,
    BackgroundRemovalService,
    CanonicalStyleAnchor,
    ImageAssetKind,
    ImageGenerationRequest,
    ImageGenerationService,
    ImageReference,
    StructuredGenerationRequest,
    StructuredGenerationService,
    StructuredOutputSchema,
    StructuredReference,
)
from stage_gen.components.character_profile import (
    CharacterProfile,
    ResolvedCharacterProfile,
    resolve_character_profile_binding,
)
from stage_gen.components.game_contract import (
    GameContract,
    GameVocabulary,
    ResolvedGameContract,
    resolve_game_contract_binding,
)
from stage_gen.components.image_generation import (
    append_style_anchor_once,
    canonical_style_anchor_digest,
    render_style_anchor,
)
from stage_gen.config import TransparencyMode
from stage_gen.contracts import (
    ArtifactProvenance,
    BinaryArtifact,
    InputProvenance,
    ProvenanceInput,
    SoftwareIdentity,
)
from stage_gen.image_prompting import build_image_style_compiler_request
from stage_gen.media import (
    CHROMA_MATTE_VERSION,
    apply_chroma_transparency,
    compose_source_with_alpha,
    inspect_image,
    normalize_png,
)
from stage_gen.recipes.base import StageContext
from stage_gen.recipes.scrolling_preview.cache import valid_artifact_pair
from stage_gen.recipes.scrolling_preview.game import (
    GAME_RESOLUTION_VERSION,
    ResidentRenderPlan,
    append_game_art_direction_once,
    assert_projection_supported,
    game_identity,
    resident_render_plan,
)
from stage_gen.recipes.scrolling_preview.manifest import write_scrolling_preview_manifest
from stage_gen.recipes.scrolling_preview.map_book import resolve_scrolling_map_book
from stage_gen.recipes.scrolling_preview.mob_states import (
    BASE_MOB_STRIP_STATES,
    MOB_STRIP_STATES,
    mob_strip_artifact,
    mob_strip_stage,
    mob_strip_state,
)
from stage_gen.recipes.scrolling_preview.models import (
    NEAR_FOREGROUND_PARALLAX,
    WORLD_SPEC_NORMALIZATION_VERSION,
    WorldLayer,
    WorldSpec,
    WorldSpecCanonicalization,
    canonicalize_generated_world_spec,
)
from stage_gen.recipes.scrolling_preview.profile import (
    PROFILE_RESOLUTION_VERSION,
    character_profile_prompt,
)
from stage_gen.recipes.scrolling_preview.proportion import (
    ActorProportionError,
    character_proportion_prompt,
    evaluate_actor_proportion,
    parse_character_heads_tall,
)
from stage_gen.recipes.scrolling_preview.raster_contracts import (
    GRID_EMPTY_CELL_ERROR_CODE,
    GRID_ISOLATION_ERROR_CODE,
    GRID_NORMALIZATION_VERSION,
    GRID_PAINTED_CELL_FRAME_ERROR_CODE,
    GRID_UNIFORM_SOURCE_ERROR_CODE,
    ISOLATED_ALPHA_CLEANUP_VERSION,
    ISOLATED_SUBJECT_FIT_VERSION,
    RESIDENT_STILL_HEIGHT,
    RESIDENT_STILL_WIDTH,
    GridContract,
    GridSourceLayoutError,
    canonicalize_isolated_view_alpha,
    contract_for_stage,
    fit_isolated_view_alpha,
    grid_semantic_contract,
    grid_semantic_role,
    normalize_canonical_grid,
    remap_canonical_grid,
    side_view_symmetry_ceiling,
    validate_canonical_grid,
    validate_generated_source,
    validate_isolated_view_alpha,
    validate_isolated_view_source,
    validate_recoverable_isolated_view_alpha,
)
from stage_gen.recipes.scrolling_preview.resident import (
    DirectedVillageNpc,
    DirectedVillageSpec,
    directed_village_spec_json_schema,
    resident_still_subject,
    validate_directed_roster_vocabulary,
    village_spec_shape,
)
from stage_gen.recipes.scrolling_preview.review_criteria import (
    ACTOR_FACING_SCHEMA_NAME,
    REQUIRED_SIDE_VIEW_FACING,
    ActorFacingError,
    ActorFacingVerdict,
    actor_facing_json_schema,
    actor_facing_prompt,
    evaluate_actor_facing,
    is_resident_still,
    parse_actor_facing,
    required_facing,
    reviews_facing,
)
from stage_gen.recipes.scrolling_preview.scale_reference import (
    ACTOR_SCALE_REFERENCE_SCHEMA_NAME,
    actor_scale_reference_json_schema,
    actor_scale_reference_prompt,
    evaluate_actor_scale_reference,
    measures_scale_reference,
    parse_actor_scale_reference,
    scale_reference_frame,
)
from stage_gen.recipes.scrolling_preview.soundtrack import (
    generate_scrolling_soundtrack,
    resolve_scrolling_soundtrack,
)
from stage_gen.recipes.scrolling_preview.tileset_materials import (
    TILESET_MATERIAL_SYNTHESIS_VERSION,
    canonicalize_tileset_material,
    flatten_tileset_to_background,
    synthesize_tileset_from_materials,
    tileset_material_dependency_evidence,
    tileset_material_prompt,
    validate_tileset_material_swatch,
)
from stage_gen.recipes.scrolling_preview.village import (
    STILL_RESIDENT_RENDER,
    STRIP_RESIDENT_RENDER,
    VILLAGE_NPC_COUNT,
    VILLAGE_SPEC_SCHEMA_NAME,
    VillageNpc,
    VillageSpec,
    npc_turnaround_subject,
    village_enabled,
)
from stage_gen.reliability import (
    ArtifactBundleEntry,
    RetryExhaustedError,
    RetryFailureRecord,
    sanitize_for_persistence,
    sha256_hex,
    write_artifact_bundle_with_provenance_async,
    write_artifact_with_provenance_async,
)
from stage_gen.resources import image_template_dir
from stage_gen.theme import (
    THEME_COMPILER_VERSION,
    THEME_SCHEMA_VERSION,
    CompiledThemePlan,
    assert_no_raw_theme_control_leak,
    build_theme_plan_request,
    parse_theme_handles,
)

_RECIPE_COMPONENT = SoftwareIdentity(name="@stage-gen/stage-gen", version="0.0.0")
_STATES = ("idle", "walk", "run", "jump", "crawl")
_ISOLATED_VIEW_FALLBACK_VERSION = "isolated-view-fallback-v1"
_PER_CELL_GENERATION_VERSION = "per-cell-generation-v1"
_TILESET_MATERIAL_SWATCH_SIZE = 1024
_TURNAROUND_VIEW_ROLES = ("front", "side", "back")
# Semantic regenerations allowed per reviewed strip. These are not provider retries: the
# artifact being discarded is complete and satisfies every deterministic contract, and what is
# being asked for is different artwork. Measured on a full run, facing arrives wrong about half
# the time and the rolls look independent, so one regeneration clears most of it and two leaves
# roughly one strip in eight of the remainder - past that the cost of another full image
# generation stops being worth the shrinking return.
_ACTOR_REVIEW_MAXIMUM_REGENERATIONS = 2
#: Matches the runtime cell extractor, so a measured height agrees with what is drawn.
_PAINTED_ALPHA_THRESHOLD = 64
_SCROLLING_IMAGE_ASSET_KINDS: tuple[ImageAssetKind, ...] = (
    "concept_art",
    "character_sprite",
    "environment_background",
    "illustration",
    "asset_sheet",
    "tileable_texture",
    "interface_art",
    "effect_sheet",
)
_PER_CELL_LAYOUT_CODES = frozenset(
    {
        GRID_ISOLATION_ERROR_CODE,
        GRID_EMPTY_CELL_ERROR_CODE,
        GRID_UNIFORM_SOURCE_ERROR_CODE,
        # A painted cell template is a sheet the provider could not deliver cleanly, which is
        # exactly what both fallbacks exist to route around. It was added to the grid contracts
        # as a sibling rule without being admitted here, and that omission is not inert: a
        # single attempt tripping it made a six-attempt history ineligible, so an exhausted
        # sheet lost its fallback entirely and failed the run instead of degrading.
        GRID_PAINTED_CELL_FRAME_ERROR_CODE,
    }
)
# Codes whose raise sites name a specific cell. Every other admitted code describes the sheet as
# a whole and must not carry coordinates, which is what keeps a recorded history unforgeable.
# The painted-frame code is raised both ways - per cell by the ring check, and without
# coordinates by the gutter check - so it is the one code allowed either shape.
_CELL_SCOPED_LAYOUT_CODES = frozenset(
    {GRID_EMPTY_CELL_ERROR_CODE, GRID_PAINTED_CELL_FRAME_ERROR_CODE}
)
# Sheet exhaustion hands off to material synthesis for the same typed grid-source failures the
# per-cell fallback already recognizes; both mean the provider could not deliver a valid grid.
_TILESET_SHEET_FALLBACK_ERROR_CODES = _PER_CELL_LAYOUT_CODES


@dataclass(frozen=True, slots=True)
class _ImageSpec:
    stage: str
    prompt: str
    output: Path
    width: int
    height: int
    references: tuple[Path, ...] = ()
    transparent: bool = True
    metadata: dict[str, object] | None = None
    compiled_creative_base: bool = False
    isolated_view: bool = False
    theme_family: str | None = None
    portable_references: bool = False


@dataclass(frozen=True, slots=True)
class _CompiledThemeContext:
    plan: CompiledThemePlan
    identity: dict[str, object]
    artifact_bytes: int


@dataclass(frozen=True, slots=True)
class _StyleAnchorContext:
    anchor: CanonicalStyleAnchor
    identity: dict[str, object]
    artifact_bytes: int


@dataclass(frozen=True, slots=True)
class _GameContractContext:
    """One run's resolved game contract, its identity, and the roles it directs."""

    resolved: ResolvedGameContract
    identity: dict[str, object]
    artifact_bytes: int

    @property
    def contract(self) -> GameContract:
        return self.resolved.contract

    @property
    def vocabulary(self) -> GameVocabulary:
        return self.resolved.vocabulary.vocabulary

    @property
    def resident(self) -> ResidentRenderPlan:
        return resident_render_plan(self.contract.cast.resident)


@dataclass(frozen=True, slots=True)
class _CharacterProfileContext:
    profile: CharacterProfile
    identity: dict[str, object]
    artifact_bytes: int


@dataclass(frozen=True, slots=True)
class _PerCellDefinition:
    index: int
    row: int
    column: int
    role: str
    prompt: str
    source_spec: dict[str, object]
    action: str
    silhouette: str
    minimum_height_fraction: float
    maximum_height_fraction: float


@dataclass(frozen=True, slots=True)
class _PerCellAdapterPlan:
    adapter: str
    parent_contract: dict[str, object]
    cells: tuple[_PerCellDefinition, ...]
    world_concept: Path
    layout_prior: Path | None
    identity_policy: str


@dataclass(frozen=True, slots=True)
class _TilesetMaterialPlan:
    parent_contract: dict[str, object]
    wireframe: Path
    world_concept: Path
    world_spec: Path
    layer_description: str
    prompts: dict[str, str]


class ScrollingPreviewExecutor:
    """Own scrolling-preview prompts, filenames, fan-out, and post-processing."""

    def __init__(
        self,
        *,
        image_service: ImageGenerationService,
        structured_service: StructuredGenerationService[Any],
        background_service: BackgroundRemovalService | None = None,
    ) -> None:
        self._images = image_service
        self._structured = structured_service
        self._background = background_service

    async def run_scrolling_preview_stage(
        self, stage_name: str, context: StageContext
    ) -> Sequence[str]:
        handlers: dict[str, Callable[[StageContext], Awaitable[Sequence[str]]]] = {
            "game-resolve": self._game_resolve,
            "soundtrack-resolve": self._soundtrack_resolve,
            "soundtrack-generate": self._soundtrack_generate,
            "map-book-resolve": self._map_book_resolve,
            "profile-resolve": self._profile_resolve,
            "theme-compile": self._theme_compile,
            "style-select": self._style_select,
            "concept": self._concept,
            "world-spec": self._world_spec,
            "wave-a": self._wave_a,
            "wave-b": self._wave_b,
            "post-split": self._post_split,
            "village-spec": self._village_spec,
            "village-concepts": self._village_concepts,
            "village-stills": self._village_stills,
            "village-strips": self._village_strips,
            "manifest": self._manifest,
            "maintenance-regenerate-tileset": self._regenerate_tileset,
        }
        try:
            handler = handlers[stage_name]
        except KeyError as error:
            raise ValueError(f"unknown scrolling-preview stage: {stage_name}") from error
        return await handler(context)

    async def _soundtrack_resolve(self, context: StageContext) -> Sequence[str]:
        return await resolve_scrolling_soundtrack(context)

    async def _soundtrack_generate(self, context: StageContext) -> Sequence[str]:
        return await generate_scrolling_soundtrack(context)

    async def _map_book_resolve(self, context: StageContext) -> Sequence[str]:
        return await resolve_scrolling_map_book(context)

    async def _game_resolve(self, context: StageContext) -> Sequence[str]:
        """Resolve the authored game contract once, and persist what directed the run.

        The canonical contract JSON is written into the run rather than only referenced, for the
        same reason the resolved character profile is: a run directory has to remain readable
        after the library moves on. `game_<tag>.json` is the exact direction the artwork was
        generated under, digest-bound to the authored source it came from.
        """

        if "game" not in context.input:
            raise ValueError("game-resolve requires a game contract binding")
        resolved = await asyncio.to_thread(
            resolve_game_contract_binding,
            context.input["game"],
            game_library_root=_required_game_library_root(context),
        )
        # Refused here rather than at the first image: this is the earliest stage that has both
        # the contract and the recipe in hand, and a run that cannot be drawn should fail before
        # it spends anything.
        assert_projection_supported(resolved.contract)
        output = _game_contract_path(context)
        identity = _resolved_game_identity(resolved)
        if valid_artifact_pair(
            output,
            validator=lambda path, sidecar: _valid_game_contract_cache(
                path, sidecar, resolved, identity
            ),
        ):
            return (str(output), f"{output}.meta.json")
        sidecar = await write_artifact_with_provenance_async(
            output,
            BinaryArtifact(data=resolved.canonical_bytes, media_type="application/json"),
            ProvenanceInput(
                provider="local",
                model=GAME_RESOLUTION_VERSION,
                prompt="resolve authored game contract",
                refs=[resolved.binding.ref],
                inputs=[resolved.source_provenance],
                params={"stage": "game-resolve", "game_contract": identity},
                validation={
                    "source_digest_verified": True,
                    "canonical_digest_verified": True,
                    "vocabulary_digest_verified": True,
                    "projection_supported": True,
                    "rights_status": resolved.contract.rights.status,
                },
                component=_RECIPE_COMPONENT,
                tool=SoftwareIdentity(name="stage-gen", version="0.0.0"),
                attempts=1,
            ),
        )
        return (str(output), str(sidecar))

    async def _profile_resolve(self, context: StageContext) -> Sequence[str]:
        if "character_profile" not in context.input:
            raise ValueError("profile-resolve requires character_profile")
        resolved = await asyncio.to_thread(
            resolve_character_profile_binding,
            context.input["character_profile"],
            character_library_root=_required_character_library_root(context),
        )
        output = _character_profile_path(context)
        identity = _resolved_character_profile_identity(resolved)
        if valid_artifact_pair(
            output,
            validator=lambda path, sidecar: _valid_character_profile_cache(
                path, sidecar, resolved, identity
            ),
        ):
            return (str(output), f"{output}.meta.json")
        sidecar = await write_artifact_with_provenance_async(
            output,
            BinaryArtifact(data=resolved.canonical_bytes, media_type="application/json"),
            ProvenanceInput(
                provider="local",
                model=PROFILE_RESOLUTION_VERSION,
                prompt="resolve authored character profile",
                refs=[resolved.binding.ref],
                inputs=[resolved.source_provenance],
                params={"stage": "profile-resolve", "character_profile": identity},
                validation={
                    "source_digest_verified": True,
                    "canonical_digest_verified": True,
                    "portable_reference_verified": True,
                    "rights_status": resolved.profile.rights.status,
                },
                component=_RECIPE_COMPONENT,
                tool=SoftwareIdentity(name="stage-gen", version="0.0.0"),
                attempts=1,
            ),
        )
        return (str(output), str(sidecar))

    async def _theme_compile(self, context: StageContext) -> Sequence[str]:
        if "theme" not in context.input:
            raise ValueError("theme-compile requires theme controls")
        output = _theme_plan_path(context)
        request = build_theme_plan_request(
            str(context.input["prompt"]),
            parse_theme_handles(context.input["theme"]),
            output,
            timeout_seconds=context.config.capability_timeout_s,
            cancellation=context.cancellation,
        )
        if valid_artifact_pair(
            output,
            validator=lambda path, sidecar: _valid_theme_plan_cache(path, sidecar, request),
        ):
            return (str(output), f"{output}.meta.json")
        generated = await self._structured.generate(request)
        return (str(output), generated.provenance_path)

    async def _style_select(self, context: StageContext) -> Sequence[str]:
        if "style_anchor" not in context.input:
            raise ValueError("style-select requires the versioned style_anchor opt-in")
        compiled = await _read_compiled_theme(context)
        output = _style_anchor_path(context)
        request = build_image_style_compiler_request(
            prompt=_style_selection_brief(context, compiled),
            artifact_path=output,
            asset_kinds=_SCROLLING_IMAGE_ASSET_KINDS,
            timeout_seconds=context.config.capability_timeout_s,
            cancellation=context.cancellation,
        )
        if _valid_style_anchor_pair(
            output,
            validator=lambda path, sidecar: _valid_style_anchor_cache(path, sidecar, request),
        ):
            return (str(output), f"{output}.meta.json")
        generated = await self._structured.generate(request)
        return (str(output), generated.provenance_path)

    async def _concept(self, context: StageContext) -> Sequence[str]:
        user_prompt = str(context.input["prompt"])
        compiled = await _read_compiled_theme(context)
        output = context.run_dir / f"concept_{context.tag}.png"
        metadata: dict[str, object]
        if compiled is None:
            prompt = (
                "2D scrolling-game scene concept art, wide cinematic landscape view.\n"
                f"Theme: {user_prompt}.\n"
                "Compose clear distant, middle, and foreground depth. Hand-painted, fully "
                "opaque, without text or labels."
            )
            metadata = {"stage": "concept", "user_prompt": user_prompt}
        else:
            prompt = _themed_concept_prompt(compiled.plan.concept)
            metadata = {"stage": "concept"}
        result = await self._generate_image_asset(
            context,
            _ImageSpec(
                stage="concept",
                prompt=prompt,
                output=output,
                width=1536,
                height=1024,
                transparent=False,
                metadata=metadata,
                compiled_creative_base=compiled is not None,
            ),
        )
        return result

    async def _world_spec(self, context: StageContext) -> Sequence[str]:
        output = context.run_dir / f"world_spec_{context.tag}.json"
        compiled = await _read_compiled_theme(context)
        style = await _read_style_anchor(context)
        if valid_artifact_pair(
            output,
            validator=lambda path, sidecar: (
                _valid_world_spec_cache(
                    path,
                    sidecar,
                    compiled.identity if compiled is not None else None,
                )
                and _style_identity_matches(sidecar, style.identity if style is not None else None)
            ),
        ):
            return (str(output), f"{output}.meta.json")
        prompt = str(context.input["prompt"])
        concept = context.run_dir / f"concept_{context.tag}.png"
        reference = await _structured_reference(concept)

        def parse(value: object) -> WorldSpecCanonicalization:
            canonicalized = canonicalize_generated_world_spec(value)
            spec = canonicalized.spec
            if len(spec.mobs) != 8:
                raise ValueError(f"mobs length {len(spec.mobs)} != requested 8")
            if len(spec.obstacles) != 3:
                raise ValueError(f"obstacles length {len(spec.obstacles)} != requested 3")
            return canonicalized

        request_prompt = (
            f'WORLD PROMPT: "{prompt}"\nDesign a side-scrolling world bible with exactly '
            "8 ascending, anatomy-distinct mobs; exactly 3 uniquely themed obstacle "
            "sheets with 8 props each; exactly 8 semantically distinct items; and 1-5 "
            "parallax layers with exactly one opaque z=0/parallax=0 backdrop. Include at least "
            "one transparent layer; the front-most transparent layer must be the near foreground "
            "with parallax exactly 1.8."
        )
        request_metadata: dict[str, object] = {"stage": "world-spec", "user_prompt": prompt}
        if compiled is not None:
            request_prompt = _append_compiled_directive(
                request_prompt,
                compiled.plan.world_spec,
                compiled.plan.hard_exclusions,
            )
            request_metadata["theme_compilation"] = compiled.identity
        if style is not None:
            request_prompt = (
                f"{request_prompt.rstrip()}\n\n"
                f"{render_style_anchor(style.anchor, 'environment_background')}"
            )
            request_metadata["style_anchor"] = style.identity

        generated = await self._structured.generate(
            StructuredGenerationRequest(
                system=(
                    "You are a world-design agent. Return only the strict structured object. "
                    "The attached concept is the source of truth for palette and atmosphere."
                ),
                prompt=request_prompt,
                artifact_path=output,
                references=(reference,),
                schema=StructuredOutputSchema(
                    name="scrolling_preview_world_spec",
                    description="World and asset plan for the scrolling preview recipe",
                    json_schema=WorldSpec.model_json_schema(),
                    strict=True,
                ),
                parse=parse,
                artifact_value=lambda result: result.artifact_value(),
                validate=lambda result: result.validation,
                metadata=request_metadata,
                timeout_seconds=context.config.capability_timeout_s,
                cancellation=context.cancellation,
            )
        )
        return (str(output), generated.provenance_path)

    async def _wave_a(self, context: StageContext) -> Sequence[str]:
        spec = await _read_world_spec(context)
        character_profile = await _read_character_profile(context)
        concept = context.run_dir / f"concept_{context.tag}.png"
        concept_data = await asyncio.to_thread(concept.read_bytes)
        concept_binding = {
            "role": "world-concept-style-reference",
            "path": concept.name,
            "sha256": sha256_hex(concept_data),
            "bytes": len(concept_data),
        }
        templates = _template_root()
        obstacle_template = templates / "obstacle_template.png"
        obstacle_template_data = await asyncio.to_thread(obstacle_template.read_bytes)
        obstacle_template_binding = {
            "role": "obstacle-layout-prior",
            "path": obstacle_template.name,
            "sha256": sha256_hex(obstacle_template_data),
            "bytes": len(obstacle_template_data),
        }
        item_source_specs = [item.model_dump(mode="json") for item in spec.items]
        items_prompt = (
            "Eight distinct collectible items in a strict 2-row x 4-column grid, one "
            "complete centred item per equal cell, ordered left-to-right across the top "
            "row then left-to-right across the bottom row. "
            + _cell_containment_directive(
                grid="2-row x 4-column",
                subject="item",
                appendages="handles, straps, chains, and glow",
            )
            + "CLEAN PLATE: keep the supplied template's uniform background clear and do not "
            "render template lines, labels, borders, or shadows. "
            + "The items are: "
            + "; ".join(
                f"cell {index + 1} {item.name}: {item.brief}"
                for index, item in enumerate(spec.items)
            )
        )
        image_specs: list[_ImageSpec] = []
        for layer in spec.layers:
            image_specs.append(
                _ImageSpec(
                    stage=f"layer-{layer.id}",
                    prompt=_parallax_layer_prompt(layer),
                    output=context.run_dir / f"layer_{context.tag}_{layer.id}.png",
                    width=2400,
                    height=800,
                    references=(concept,),
                    transparent=not layer.opaque,
                    metadata={
                        "stage": f"layer-{layer.id}",
                        "opaque": layer.opaque,
                        "z_index": layer.z_index,
                        "parallax": layer.parallax,
                    },
                )
            )
        character_prompt = _turnaround_prompt("Player character")
        if character_profile is not None:
            character_prompt = (
                f"{character_prompt.rstrip()}\n\n"
                f"{character_profile_prompt(character_profile.profile)}"
            )
        # Proportion is stated here and nowhere else. This is where the character is designed;
        # every strip takes this turnaround as a reference image, so the build carries visually
        # rather than by repeating the instruction. Restating it in the strip prompts would push
        # against the facing and containment directives that already compete for weight there -
        # lengthening those is exactly what regressed `character-attack` into isolation
        # failures once already.
        heads_tall = await _actor_heads_tall(context)
        if heads_tall is not None:
            character_prompt = (
                f"{character_prompt.rstrip()}\n\n{character_proportion_prompt(heads_tall)}"
            )
        character_references = (concept,)
        image_specs.extend(
            [
                self._tileset_spec(context),
                _ImageSpec(
                    "character-concept",
                    character_prompt,
                    context.run_dir / f"character_concept_{context.tag}.png",
                    2400,
                    800,
                    character_references,
                    metadata={
                        "turnaround_prompt_reference_contract": (
                            _turnaround_prompt_reference_contract(
                                character_prompt,
                                reference_bindings=(concept_binding,),
                            )
                        )
                    },
                ),
                _ImageSpec(
                    "items",
                    items_prompt,
                    context.run_dir / f"items_{context.tag}.png",
                    2400,
                    800,
                    (obstacle_template, concept),
                    metadata={
                        "per_cell_generation_contract": _per_cell_parent_contract(
                            stage="items",
                            prompt=items_prompt,
                            source_specs=item_source_specs,
                            reference_bindings=(
                                obstacle_template_binding,
                                concept_binding,
                            ),
                            identity_policy="independent-distinct-items",
                        )
                    },
                ),
                _ImageSpec(
                    "inventory",
                    "Inventory panel matching the supplied slot layout, without labels.",
                    context.run_dir / f"inventory_{context.tag}.png",
                    1536,
                    1024,
                    (templates / "inventory_template.png", concept),
                ),
                _ImageSpec(
                    "portal",
                    # The grid contract proves two isolated non-empty cells, never what is in
                    # them. Asking for "landmarks" returned framed dioramas complete with
                    # terrain, buildings, signage and a painted copy of the player, all of which
                    # the runtime then placed into the level as one sprite.
                    "Two complete isolated portal archways, one centred per equal cell in a "
                    "strict 1-row x 2-column grid: a free-standing stone gateway whose opening "
                    "holds a glowing threshold. Keep a clear transparent border around each "
                    "archway; no ground, platform, terrain, cliff, scenery, foliage, buildings, "
                    "characters, labels, text, signage, or shadows.",
                    context.run_dir / f"portal_{context.tag}.png",
                    2048,
                    1024,
                    (concept,),
                ),
                _ImageSpec(
                    "ladder",
                    "One complete front-facing climbable ladder, two registered parallel rails "
                    "and evenly spaced readable rungs spanning almost the full height. Keep a "
                    "clear transparent border; no ground, platform, labels, shadows, or scenery.",
                    context.run_dir / f"ladder_{context.tag}.png",
                    256,
                    1024,
                    (concept,),
                    metadata={"runtime_role": "ladder", "rows": 1, "cols": 1, "gutter": 2},
                ),
            ]
        )
        for index, mob in enumerate(spec.mobs):
            mob_prompt = _turnaround_prompt(f"Creature {mob.name}, {mob.body_plan}. {mob.brief}")
            image_specs.append(
                _ImageSpec(
                    f"mob-concept-{index}",
                    mob_prompt,
                    context.run_dir / f"mob_concept_{context.tag}_{index}.png",
                    2400,
                    800,
                    (concept,),
                    metadata={
                        "slot": index,
                        "tier_label": mob.tier_label,
                        "turnaround_prompt_reference_contract": (
                            _turnaround_prompt_reference_contract(
                                mob_prompt,
                                reference_bindings=(concept_binding,),
                            )
                        ),
                    },
                )
            )
        for index, sheet in enumerate(spec.obstacles):
            obstacle_source_specs = [prop.model_dump(mode="json") for prop in sheet.props]
            # Same containment discipline the strips carry. Without it this sheet asked for
            # "isolated props ... with clear cell boundaries" and repeatedly returned one
            # connected scene arranged over a grid, which fails cell isolation on every seam at
            # once and burns all six provider attempts.
            obstacle_prompt = (
                f"Eight complete isolated props for {sheet.sheet_theme} in a strict 2-row x "
                "4-column grid, one prop per equal cell, ordered left-to-right across each "
                "row. "
                + _cell_containment_directive(
                    grid="2-row x 4-column",
                    subject="prop",
                    appendages="branches, banners, ropes, and cast debris",
                )
                + "CLEAN PLATE: do not render template lines, labels, borders, or shadows. "
                + "The props are: "
                + "; ".join(
                    f"cell {prop_index + 1} {prop.name}: {prop.brief}"
                    for prop_index, prop in enumerate(sheet.props)
                )
            )
            image_specs.append(
                _ImageSpec(
                    f"obstacles-{index}",
                    obstacle_prompt,
                    context.run_dir / f"obstacles_{context.tag}_{index}.png",
                    2400,
                    800,
                    (obstacle_template, concept),
                    metadata={
                        "sheet_theme": sheet.sheet_theme,
                        "slot": index,
                        "per_cell_generation_contract": _per_cell_parent_contract(
                            stage=f"obstacles-{index}",
                            prompt=obstacle_prompt,
                            source_specs=obstacle_source_specs,
                            reference_bindings=(
                                obstacle_template_binding,
                                concept_binding,
                            ),
                            identity_policy="cell-0-scale-style-anchor",
                            sheet_theme=sheet.sheet_theme,
                        ),
                    },
                )
            )
        return await self._fan_out(context, image_specs)

    def _tileset_spec(self, context: StageContext) -> _ImageSpec:
        """Return the production tileset contract shared by the recipe and maintenance CLI."""

        return _ImageSpec(
            "tileset",
            "Ground tileset, strict 12-column x 4-row atlas matching the supplied wireframe. "
            "Preserve every equal cell as an independent semantic terrain role and leave a "
            "clear 2-pixel-equivalent strategy-background gutter inside every cell boundary. "
            "Texture the wireframe shapes without joining scenery across cells. The canonical "
            "interior-fill cell at row 4 column 1 must cover its complete inset.",
            context.run_dir / f"tileset_{context.tag}.png",
            2400,
            800,
            (_template_root() / "wireframe.png", context.run_dir / f"concept_{context.tag}.png"),
        )

    async def _regenerate_tileset(self, context: StageContext) -> Sequence[str]:
        """Regenerate only the tileset while preserving the production recipe contract."""

        return await self._generate_image_asset(context, self._tileset_spec(context), force=True)

    async def _wave_b(self, context: StageContext) -> Sequence[str]:
        spec = await _read_world_spec(context)
        template = _template_root() / "character_template.png"
        character = context.run_dir / f"character_concept_{context.tag}.png"
        # Which strips each creature gets. A run without a game contract draws exactly the two it
        # always drew, so its prompts, its artifact names and therefore its cached artwork are
        # untouched; a directed run adds the attack pose the combat system needs. Gated on the
        # contract rather than on a flag so enabling combat is one authored decision, and so no
        # existing run silently gains eight image calls it did not ask for.
        game = await _read_game_contract(context)
        mob_states = (
            frozenset(entry.state for entry in MOB_STRIP_STATES)
            if game is not None
            else frozenset(BASE_MOB_STRIP_STATES)
        )
        strip_specs = [
            _ImageSpec(
                f"character-master-strip-{state}",
                _character_strip_prompt(state),
                context.run_dir / f"character_{context.tag}_combined_strip_{state}.png",
                2400,
                800,
                (template, character),
                metadata={
                    "state": state,
                    "rows": 1,
                    "cols": 4,
                    "composite_row_height": 688,
                    "part_of": f"character_{context.tag}_combined.png",
                },
            )
            for state in _STATES
        ]
        image_specs = [
            _ImageSpec(
                "character-attack",
                # This was a bare one-liner while the climb spec two entries below and every
                # master-sheet state carried the full cell discipline. The provider duly painted
                # the template's own cell borders into it, which nothing checked until now.
                _character_strip_prompt("attack"),
                context.run_dir / f"character_{context.tag}_attack.png",
                2400,
                800,
                (template, character),
            ),
            _ImageSpec(
                "character-climb",
                "Four-frame rear-facing ladder-climb loop in a strict 1-row x 4-column strip. "
                "Preserve the supplied character identity and scale. Alternate hands and feet "
                "across four complete poses on one registered centreline and leave clear gutters; "
                "do not draw the ladder, template marks, labels, borders, ground, or shadows.",
                context.run_dir / f"character_{context.tag}-fromcombined_climb.png",
                256,
                128,
                (character,),
                metadata={
                    "runtime_role": "character-climb",
                    "state": "climb",
                    "rows": 1,
                    "cols": 4,
                    "cellW": 64,
                    "cellH": 128,
                    "gutter": 2,
                },
            ),
        ]
        for index, mob in enumerate(spec.mobs):
            concept = context.run_dir / f"mob_concept_{context.tag}_{index}.png"
            # The head-on check reads a silhouette, which cannot tell a dome's side view from
            # its front. This creature's own turnaround can, so the ceiling comes from there -
            # and an unreadable concept falls back to the default ceiling rather than failing
            # the wave, since a missing concept is already reported by the stage that owns it.
            strip_metadata = await _mob_strip_metadata(concept)
            # One spec per declared state rather than two written out by hand. Adding `attack`
            # to `MOB_STRIP_STATES` is what puts it on the wire, and the same record supplies the
            # motion clause, the appendage list and the frame the head is measured in - so the
            # fan-out cannot disagree with the five predicates that validate what it produces.
            image_specs.extend(
                _ImageSpec(
                    mob_strip_stage(entry.state, index),
                    _mob_strip_prompt(mob.name, entry.state),
                    context.run_dir / mob_strip_artifact(context.tag, index, entry.state),
                    2400,
                    800,
                    (concept, template),
                    metadata=dict(strip_metadata) or None,
                )
                for entry in MOB_STRIP_STATES
                if entry.state in mob_states
            )
        # The character master is composed from its own five strips and nothing else, so it is
        # generated and published before the mobs are asked for. Fanning all of wave B out
        # together coupled them: `_fan_out` cancels its group on the first failure, so one
        # stubborn creature - measured here at twelve exhausted provider attempts across two
        # runs - left five validated character strips composed into nothing, and the runtime
        # kept loading the previous generation's artwork. The stage still fails on a mob
        # failure; it just no longer discards work that was already finished and correct.
        strips = await self._fan_out(context, strip_specs)
        master = await self._compose_character_master(context)
        generated = await self._fan_out(context, image_specs)
        strip_prefix = f"character_{context.tag}_combined_strip_"
        published = tuple(
            path for path in (*strips, *generated) if not Path(path).name.startswith(strip_prefix)
        )
        return (*master, *published)

    async def _compose_character_master(self, context: StageContext) -> Sequence[str]:
        compiled = await _read_compiled_theme(context)
        style = await _read_style_anchor(context)
        character_profile = await _read_character_profile(context)
        sources = tuple(
            context.run_dir / f"character_{context.tag}_combined_strip_{state}.png"
            for state in _STATES
        )
        source_bytes = tuple(
            await asyncio.gather(*(asyncio.to_thread(path.read_bytes) for path in sources))
        )
        source_hashes = [
            {"path": str(path), "sha256": sha256_hex(data)}
            for path, data in zip(sources, source_bytes, strict=True)
        ]
        source_paths = {state: str(path) for state, path in zip(_STATES, sources, strict=True)}
        output = context.run_dir / f"character_{context.tag}_combined.png"

        def valid_cache(path: Path, meta: dict[str, Any]) -> bool:
            return (
                _exact_image(path, 2400, 3440, alpha=True)
                and _source_hashes_match(meta, source_hashes)
                and _metadata_field(meta, "composite_contract") == "per-cell-fit-v1"
                and (compiled is None or _theme_identity_matches(meta, compiled.identity))
                and _style_identity_matches(meta, style.identity if style is not None else None)
                and _character_profile_identity_matches(
                    meta,
                    character_profile.identity if character_profile is not None else None,
                )
            )

        if valid_artifact_pair(
            output,
            transparency_mode=context.config.transparency_mode,
            validator=valid_cache,
        ):
            return (str(output), f"{output}.meta.json")
        composite, transparent_pixels, nontransparent_pixels = await asyncio.to_thread(
            _compose_master_rows, source_bytes
        )
        output_hash = sha256_hex(composite)
        sidecar = await write_artifact_with_provenance_async(
            output,
            BinaryArtifact(data=composite, media_type="image/png"),
            ProvenanceInput(
                provider="local",
                model="deterministic-alpha-composite",
                prompt=str(context.input["prompt"]),
                refs=[str(path) for path in sources],
                inputs=[
                    InputProvenance(
                        ref=str(path),
                        sha256=sha256_hex(data),
                        source="reference",
                        bytes=len(data),
                        media_type="image/png",
                    )
                    for path, data in zip(sources, source_bytes, strict=True)
                ]
                + ([_style_anchor_input(style)] if style is not None else [])
                + (
                    [_character_profile_input(character_profile)]
                    if character_profile is not None
                    else []
                ),
                params={
                    "stage": "character-master",
                    "transparency": {
                        "mode": str(context.config.transparency_mode),
                        "processor": "deterministic-alpha-composite",
                        "source_paths": source_paths,
                        "source_hashes": source_hashes,
                        "output_sha256": output_hash,
                    },
                    "metadata": {
                        "composite_strategy": "per-row-per-cell-fit",
                        "composite_contract": "per-cell-fit-v1",
                        "states": list(_STATES),
                        "rows": 5,
                        "cols": 4,
                        "cellW": 600,
                        "cellH": 688,
                        "strip_gen_height": 800,
                        "composite_offsets_y": [row * 688 for row in range(5)],
                        **(
                            {"theme_compilation": compiled.identity} if compiled is not None else {}
                        ),
                        **({"style_anchor": style.identity} if style is not None else {}),
                        **(
                            {"character_profile": character_profile.identity}
                            if character_profile is not None
                            else {}
                        ),
                    },
                },
                validation={
                    "transparency_mode": str(context.config.transparency_mode),
                    "dimensions_preserved": True,
                    "output_width": 2400,
                    "output_height": 3440,
                    "alpha_nontrivial": True,
                    "transparent_pixels": transparent_pixels,
                    "nontransparent_pixels": nontransparent_pixels,
                    "output_sha256": output_hash,
                },
                component=_RECIPE_COMPONENT,
                tool=SoftwareIdentity(name="Pillow", version=pillow_version),
                attempts=1,
            ),
        )
        return (str(output), str(sidecar))

    async def _post_split(self, context: StageContext) -> Sequence[str]:
        compiled = await _read_compiled_theme(context)
        style = await _read_style_anchor(context)
        character_profile = await _read_character_profile(context)
        master = context.run_dir / f"character_{context.tag}_combined.png"
        master_bytes = await asyncio.to_thread(master.read_bytes)
        facts = inspect_image(master_bytes, expected_media_type="image/png")
        if (facts.width, facts.height) != (2400, 3440):
            raise ValueError("character master sheet must be 2400x3440")
        slices = await asyncio.to_thread(_slice_master, master_bytes)
        source_hash = sha256_hex(master_bytes)
        artifacts: list[str] = []
        for state, data in zip(_STATES, slices, strict=True):
            output = context.run_dir / f"character_{context.tag}-fromcombined_{state}.png"
            if not valid_artifact_pair(
                output,
                transparency_mode=context.config.transparency_mode,
                validator=lambda path, meta: (
                    _exact_image(path, 2400, 688, alpha=True)
                    and _source_hash_matches(meta, source_hash)
                    and _valid_character_state_grid(path)
                    and (compiled is None or _theme_identity_matches(meta, compiled.identity))
                    and _style_identity_matches(meta, style.identity if style is not None else None)
                    and _character_profile_identity_matches(
                        meta,
                        character_profile.identity if character_profile is not None else None,
                    )
                ),
            ):
                output_hash = sha256_hex(data)
                transparent_pixels, nontransparent_pixels = _alpha_counts(data)
                grid_validation = validate_canonical_grid(
                    data, GridContract(rows=1, columns=4, gutter=8, anchor="bottom")
                )
                sidecar = await write_artifact_with_provenance_async(
                    output,
                    BinaryArtifact(data=data, media_type="image/png"),
                    ProvenanceInput(
                        provider="local",
                        model="deterministic-png-slice",
                        prompt=f"slice character master sheet row {state}",
                        refs=[master.name],
                        inputs=[
                            InputProvenance(
                                ref=master.name,
                                sha256=source_hash,
                                source="content",
                                bytes=len(master_bytes),
                                media_type="image/png",
                            ),
                            *([_style_anchor_input(style)] if style is not None else []),
                            *(
                                [_character_profile_input(character_profile)]
                                if character_profile is not None
                                else []
                            ),
                        ],
                        params={
                            "transparency": {
                                "mode": str(context.config.transparency_mode),
                                "source_path": str(master),
                                "source_sha256": source_hash,
                                "output_sha256": output_hash,
                                "processor": "master-sheet-slice",
                            },
                            "metadata": {
                                "state": state,
                                "row_height": 688,
                                **(
                                    {"theme_compilation": compiled.identity}
                                    if compiled is not None
                                    else {}
                                ),
                                **({"style_anchor": style.identity} if style is not None else {}),
                                **(
                                    {"character_profile": character_profile.identity}
                                    if character_profile is not None
                                    else {}
                                ),
                            },
                        },
                        validation={
                            "exact_contract_dimensions": True,
                            "dimensions_preserved": True,
                            "transparency_mode": str(context.config.transparency_mode),
                            "alpha_nontrivial": True,
                            "transparent_pixels": transparent_pixels,
                            "nontransparent_pixels": nontransparent_pixels,
                            "output_width": 2400,
                            "output_height": 688,
                            "output_sha256": output_hash,
                            **grid_validation,
                        },
                        component=_RECIPE_COMPONENT,
                        tool=SoftwareIdentity(name="Pillow", version=pillow_version),
                        attempts=1,
                    ),
                )
            else:
                sidecar = Path(f"{output}.meta.json")
            artifacts.extend((str(output), str(sidecar)))
            # Measured here rather than on the generated strip: composition and re-slicing sit
            # between them, so this is the first artifact that is the pixels the runtime draws.
            artifacts.extend(
                await self._measure_published_scale_reference(
                    context,
                    output,
                    stage=f"character-{state}",
                    cell_width=600,
                    cell_height=688,
                )
            )
        return artifacts

    async def _measure_published_scale_reference(
        self,
        context: StageContext,
        published: Path,
        *,
        stage: str,
        cell_width: int,
        cell_height: int,
    ) -> Sequence[str]:
        """Measure a published actor sheet's scale reference, reusing any reading on these bytes."""

        reference_path = published.with_name(f"{published.stem}.scale-reference.json")
        artifact = await asyncio.to_thread(published.read_bytes)
        measured_sha256 = sha256_hex(artifact)
        if await _cached_actor_scale_reference(reference_path, measured_sha256) is not None:
            return (str(reference_path), f"{reference_path}.meta.json")
        generated = await self._structured.generate(
            StructuredGenerationRequest(
                system=(
                    "You are a sprite-sheet measurer. Return only the strict structured object."
                ),
                prompt=actor_scale_reference_prompt("a game character", 0),
                artifact_path=reference_path,
                references=(await _structured_reference(published),),
                schema=StructuredOutputSchema(
                    name=ACTOR_SCALE_REFERENCE_SCHEMA_NAME,
                    description="Anatomical scale reference for an actor animation strip",
                    json_schema=actor_scale_reference_json_schema(),
                    strict=True,
                ),
                parse=parse_actor_scale_reference,
                artifact_value=lambda reference: {
                    **evaluate_actor_scale_reference(
                        reference, frame_width=cell_width, frame_height=cell_height
                    ),
                    "frame_index": 0,
                    "cell_width": cell_width,
                    "cell_height": cell_height,
                },
                validate=lambda reference: evaluate_actor_scale_reference(
                    reference, frame_width=cell_width, frame_height=cell_height
                ),
                metadata={
                    "stage": f"{stage}-scale-reference",
                    "measured_sha256": measured_sha256,
                },
                timeout_seconds=context.config.capability_timeout_s,
                cancellation=context.cancellation,
            )
        )
        return (str(reference_path), generated.provenance_path)

    async def _village_spec(self, context: StageContext) -> Sequence[str]:
        """Design the village bible, from the same concept image the world bible was designed on.

        This mirrors `_world_spec` deliberately and does not extend it. `world_spec_<tag>.json`
        keeps its exact bytes when a village is enabled, so every artifact an existing run
        already holds stays cache-valid and enabling the village costs one structured call plus
        nine image calls rather than a regeneration. A `village` field on `WorldSpec` would have
        rewritten an artifact every run already has, and invalidated all of them.

        The concept travels as the reference for the same reason it does in `_world_spec`: it is
        the run's style root, and a settlement designed without seeing it reads as a different
        world's town dropped into this one.
        """

        if not village_enabled(context.input):
            raise ValueError("village-spec requires the versioned village opt-in")
        output = context.run_dir / f"village_spec_{context.tag}.json"
        compiled = await _read_compiled_theme(context)
        style = await _read_style_anchor(context)
        # Read before the cache check, not after: the bound game decides which roster shape this
        # run wrote, and a cache validator that guesses the shape can never match a directed
        # bible - so the roster regenerated on every run and took all nine village images with
        # it, since every village prompt is derived from it.
        game = await _read_game_contract(context)
        directed = game is not None
        if valid_artifact_pair(
            output,
            validator=lambda path, sidecar: (
                _valid_village_spec_cache(
                    path,
                    sidecar,
                    compiled.identity if compiled is not None else None,
                    directed=directed,
                )
                and _style_identity_matches(sidecar, style.identity if style is not None else None)
            ),
        ):
            return (str(output), f"{output}.meta.json")
        prompt = str(context.input["prompt"])
        concept = context.run_dir / f"concept_{context.tag}.png"
        reference = await _structured_reference(concept)

        def parse(value: object) -> VillageSpec:
            if game is None:
                return VillageSpec.model_validate(value)
            directed = DirectedVillageSpec.model_validate(value)
            # The enums in the request schema already constrain these, so this is a second,
            # independent check on values a provider has been told to pick from a list. Held
            # here rather than trusted because a schema is a request and a validator is a fact.
            validate_directed_roster_vocabulary(directed, game.vocabulary)
            return directed

        request_prompt = (
            f'WORLD PROMPT: "{prompt}"\nDesign a peaceful settlement that belongs to this same '
            f"world: a hub the player travels to between hunts, where nothing is hunted and "
            f"nothing attacks. Give it exactly {VILLAGE_NPC_COUNT} residents, each with a "
            "distinct trade. "
        )
        if game is None:
            request_prompt += (
                "Each body_plan must begin with the kind of body the resident has, "
                "using a plain noun for it - human, dwarf, elf, gnome, child, badger, mouse, "
                'avian, reptilian and the like - followed by build and trade, as in "elderly '
                'human baker" or "broad badger smith". A body_plan that names only a profession '
                "is rejected. "
            )
        else:
            # Under a game contract the anatomy comes from `body_kind`, which is an enum, so the
            # prose is asked for what prose is good at instead of being asked to smuggle a noun.
            request_prompt += (
                "Choose each resident's body_kind, stance and holding from the values the "
                "schema allows, and use body_plan for build and trade only - the body itself is "
                'already named by body_kind, as in "wiry and quick, the village baker". No two '
                "residents may share both a stance and a held prop: what a resident is doing is "
                "what makes them read as a different person from the one beside them. "
            )
        request_prompt += (
            "No two consecutive residents may share a body plan. Also give exactly 8 "
            "village fixtures - stalls, wells, carts, signs, racks - that furnish "
            "the settlement. The residents are ordinary townsfolk who live and work here: not "
            "monsters, not creatures from the bestiary, and not the player character. Each "
            "resident speaks exactly three short lines - a greeting, a remark, and a farewell - "
            "that fit on one line of a dialogue box."
        )
        request_metadata: dict[str, object] = {"stage": "village-spec", "user_prompt": prompt}
        if game is not None:
            request_metadata["game_contract"] = game.identity
        if compiled is not None:
            request_prompt = _append_compiled_directive(
                request_prompt,
                compiled.plan.world_spec,
                compiled.plan.hard_exclusions,
            )
            request_metadata["theme_compilation"] = compiled.identity
        if style is not None:
            request_prompt = (
                f"{request_prompt.rstrip()}\n\n"
                f"{render_style_anchor(style.anchor, 'environment_background')}"
            )
            request_metadata["style_anchor"] = style.identity

        generated = await self._structured.generate(
            StructuredGenerationRequest(
                system=(
                    "You are a world-design agent. Return only the strict structured object. "
                    "The attached concept is the source of truth for palette and atmosphere."
                ),
                prompt=request_prompt,
                artifact_path=output,
                references=(reference,),
                schema=StructuredOutputSchema(
                    name=village_spec_shape(directed=directed)[1],
                    description="Village hub roster for the scrolling preview recipe",
                    json_schema=(
                        VillageSpec.model_json_schema()
                        if game is None
                        else directed_village_spec_json_schema(
                            game.vocabulary,
                            allow_pose=game.resident.allow_pose,
                            allow_held_prop=game.resident.allow_held_prop,
                        )
                    ),
                    strict=True,
                ),
                parse=parse,
                artifact_value=lambda spec: spec.model_dump(mode="json"),
                validate=_village_spec_roster_record,
                metadata=request_metadata,
                timeout_seconds=context.config.capability_timeout_s,
                cancellation=context.cancellation,
            )
        )
        return (str(output), generated.provenance_path)

    async def _village_concepts(self, context: StageContext) -> Sequence[str]:
        """Fan out the residents' turnarounds and the one settlement fixture sheet.

        Both halves are the hunting run's own shapes with a different subject: a resident
        turnaround is a mob turnaround, and the fixture sheet is an obstacle sheet whose props
        happen to be stalls and wells. They are built from the identical spec shapes rather than
        near-copies so they inherit the identical machinery - the fixture sheet's per-cell
        fallback, and the turnarounds' isolated-view fallback - instead of silently losing it.
        """

        spec = await _read_village_spec(context)
        concept = context.run_dir / f"concept_{context.tag}.png"
        concept_data = await asyncio.to_thread(concept.read_bytes)
        concept_binding = {
            "role": "world-concept-style-reference",
            "path": concept.name,
            "sha256": sha256_hex(concept_data),
            "bytes": len(concept_data),
        }
        obstacle_template = _template_root() / "obstacle_template.png"
        obstacle_template_data = await asyncio.to_thread(obstacle_template.read_bytes)
        obstacle_template_binding = {
            "role": "obstacle-layout-prior",
            "path": obstacle_template.name,
            "sha256": sha256_hex(obstacle_template_data),
            "bytes": len(obstacle_template_data),
        }
        # The run's build reaches the residents here, at their turnaround, exactly as it reaches
        # the player at theirs - and for the same reason: the strips take the turnaround as a
        # reference image, so the build carries visually rather than by repeating the instruction
        # where it would compete with the facing and containment directives.
        #
        # Omitting it was a real defect, not a missing nicety. The runtime scales every actor so
        # their heads agree, so proportion decides rendered height outright: measured on the first
        # live village, a seven-head elf herbalist beside a two-head player renders about three
        # and a half times the player's height. Residents drawn to a different build than the
        # cast they stand in are not merely off-style, they are the wrong size.
        game = await _read_game_contract(context)
        image_specs: list[_ImageSpec] = []
        for index, npc in enumerate(spec.npcs):
            # Under a game contract each resident resolves their own build from the game's one
            # table, keyed on the body kind they were generated with. Without one the whole cast
            # takes the run's single number, which is what `character_heads_tall` can express.
            heads_tall = await _actor_heads_tall(
                context,
                body_kind=(npc.body_kind if isinstance(npc, DirectedVillageNpc) else None),
            )
            proportion = (
                "" if heads_tall is None else f"\n\n{character_proportion_prompt(heads_tall)}"
            )
            subject = (
                resident_still_subject(npc, vocabulary=game.vocabulary)
                if game is not None and isinstance(npc, DirectedVillageNpc)
                else npc_turnaround_subject(npc)
            )
            npc_prompt = f"{_turnaround_prompt(subject).rstrip()}{proportion}"
            image_specs.append(
                _ImageSpec(
                    f"village-npc-concept-{index}",
                    npc_prompt,
                    context.run_dir / f"npc_concept_{context.tag}_{index}.png",
                    2400,
                    800,
                    (concept,),
                    metadata={
                        "slot": index,
                        "role_label": npc.role_label,
                        "turnaround_prompt_reference_contract": (
                            _turnaround_prompt_reference_contract(
                                npc_prompt,
                                reference_bindings=(concept_binding,),
                            )
                        ),
                    },
                )
            )
        fixtures_prompt = _village_fixtures_prompt(spec)
        image_specs.append(
            _ImageSpec(
                "village-fixtures",
                fixtures_prompt,
                context.run_dir / f"village_fixtures_{context.tag}.png",
                2400,
                800,
                (obstacle_template, concept),
                metadata={
                    "sheet_theme": spec.fixtures_theme,
                    "per_cell_generation_contract": _per_cell_parent_contract(
                        stage="village-fixtures",
                        prompt=fixtures_prompt,
                        source_specs=[fixture.model_dump(mode="json") for fixture in spec.fixtures],
                        reference_bindings=(
                            obstacle_template_binding,
                            concept_binding,
                        ),
                        identity_policy="cell-0-scale-style-anchor",
                        sheet_theme=spec.fixtures_theme,
                    ),
                },
            )
        )
        return await self._fan_out(context, image_specs)

    async def _village_stills(self, context: StageContext) -> Sequence[str]:
        """Fan out one forward-facing still per resident, through the reviewed-asset path.

        This is the resident render profile in practice, and what it replaces is instructive: the
        strip stage below draws four side-view frames of which the runtime renders one, in
        profile. A still draws one frame, facing the player, on half the sheet and at twice the
        resolution on the figure itself.

        What it keeps from the strip path is everything that decides whether a resident is
        *correct*: `_fan_out` routes it through `_generate_reviewed_image_asset`, so the facing is
        reviewed - against `front` rather than `right`, decided by `required_facing` - the build
        is gated against the game's table, and the head-matched scale reference is measured on
        the accepted bytes. A resident standing turned away, or at twice the player's height, is
        still caught.

        What it drops is the four-frame symmetry check, and that is not a relaxation: it compares
        frames, and there is one.
        """

        spec = await _read_directed_village_spec(context)
        game = await _read_game_contract(context)
        if game is None:
            raise ValueError("village-stills requires a game contract binding")
        image_specs: list[_ImageSpec] = []
        for index, npc in enumerate(spec.npcs):
            concept = context.run_dir / f"npc_concept_{context.tag}_{index}.png"
            heads_tall = await _actor_heads_tall(context, body_kind=npc.body_kind)
            image_specs.append(
                _ImageSpec(
                    f"village-npc-{index}-still",
                    _resident_still_prompt(npc, game=game),
                    context.run_dir / f"npc_{context.tag}_{index}_still.png",
                    RESIDENT_STILL_WIDTH,
                    RESIDENT_STILL_HEIGHT,
                    # The resident's own turnaround leads, as it does for a strip: it is the
                    # design this still must match. The character template does not travel, it
                    # is a four-cell layout prior and would ask a single portrait to be a strip.
                    (concept,),
                    metadata={
                        "slot": index,
                        "role_label": npc.role_label,
                        "body_kind": npc.body_kind,
                        "stance": npc.stance,
                        "holding": npc.holding,
                        # Carried so `_accept_actor_build` judges this resident against the
                        # build their own body kind resolved to, rather than the player's.
                        **({} if heads_tall is None else {"requested_heads_tall": heads_tall}),
                    },
                )
            )
        return await self._fan_out(context, image_specs)

    async def _village_strips(self, context: StageContext) -> Sequence[str]:
        """Fan out one idle strip per resident, through the reviewed-asset path.

        `_fan_out` routes these through `_generate_reviewed_image_asset`, which is the entire
        reason the village is worth building on top of this week's work: an NPC idle strip
        carries a left/right facing contract, so it gets the same facing review the mob strips
        get, and it measures the same head-matched scale reference the player's strips do. A
        resident who faced away from an approaching player, or who stood a head taller than the
        player beside them, would both be immediately visible bugs, and neither is recoverable
        from a silhouette.
        """

        spec = await _read_village_spec(context)
        template = _template_root() / "character_template.png"
        image_specs: list[_ImageSpec] = []
        for index, npc in enumerate(spec.npcs):
            concept = context.run_dir / f"npc_concept_{context.tag}_{index}.png"
            # Same reasoning as the mob strips: the head-on check reads a silhouette and cannot
            # tell one resident's side view from their front, so the ceiling comes from this
            # resident's own turnaround, and an unreadable turnaround falls back to the default
            # rather than failing the stage that does not own it.
            strip_metadata = await _mob_strip_metadata(concept)
            image_specs.append(
                _ImageSpec(
                    f"village-npc-{index}-idle",
                    _npc_idle_strip_prompt(npc),
                    context.run_dir / f"npc_{context.tag}_{index}_idle.png",
                    2400,
                    800,
                    (concept, template),
                    metadata=dict(strip_metadata) or None,
                )
            )
        return await self._fan_out(context, image_specs)

    async def _manifest(self, context: StageContext) -> Sequence[str]:
        game = await _read_game_contract(context)
        result = await write_scrolling_preview_manifest(
            run_dir=context.run_dir,
            tag=context.tag,
            transparency_mode=context.config.transparency_mode,
            character_profile="character_profile" in context.input,
            village=village_enabled(context.input),
            # Which mob strips this run drew. Same rule as the resident profile below: taken
            # from the request, never inferred from which files happen to be on disk, because a
            # manifest that inferred it would happily publish a half-regenerated run.
            mob_states=(
                frozenset(entry.state for entry in MOB_STRIP_STATES)
                if game is not None
                else frozenset(BASE_MOB_STRIP_STATES)
            ),
            # Which resident artwork this run produced, so the manifest demands the files that
            # exist and publishes the frame count the runtime must slice by.
            resident_render=(
                STRIP_RESIDENT_RENDER
                if game is None or not game.resident.is_still
                else STILL_RESIDENT_RENDER
            ),
            soundtrack="soundtrack" in context.input,
            map_book="map_book" in context.input,
            # Every directed contract publishes its verified current identity.
            game_contract=game is not None,
        )
        return result.artifacts

    async def _fan_out(self, context: StageContext, specs: Sequence[_ImageSpec]) -> Sequence[str]:
        results: list[Sequence[str] | None] = [None] * len(specs)

        async def run(index: int, spec: _ImageSpec) -> None:
            try:
                results[index] = await self._generate_reviewed_image_asset(context, spec)
            except Exception as error:
                raise RuntimeError(
                    f"asset {spec.stage} ({spec.output.name}) failed: {error}"
                ) from error

        try:
            async with asyncio.TaskGroup() as group:
                for index, spec in enumerate(specs):
                    group.create_task(run(index, spec), name=f"scrolling-preview:{spec.stage}")
        except ExceptionGroup as error:
            leaf = _actionable_exception(error)
            raise RuntimeError(str(leaf)) from leaf
        return tuple(path for result in results if result is not None for path in result)

    async def _generate_reviewed_image_asset(
        self, context: StageContext, spec: _ImageSpec
    ) -> Sequence[str]:
        """Generate an asset, then have a side-view strip's facing reviewed before accepting it.

        The review sits outside the provider retry owner on purpose. A provider retry re-runs a
        call that failed; this discards a complete artifact that satisfies every contract and
        asks for different artwork, which `AGENTS.md` keeps as a separate budget.

        Facing cannot join the deterministic gate in `raster_contracts` because it is not
        recoverable from a silhouette - see `review_criteria`. It is checked here instead, and
        only where a stage carries a left/right contract at all.
        """

        artifacts = await self._generate_image_asset(context, spec)
        if reviews_facing(spec.stage):
            artifacts = await self._accept_actor_facing(context, spec, artifacts)
        if _holds_run_build(spec.stage):
            artifacts = await self._accept_actor_build(context, spec, artifacts)
        # Measured last, on whichever artwork survived the review. Measuring before it - which
        # is where this call used to sit - wrote the reference from art that a rejected facing
        # verdict then replaced, and nothing re-measured the replacement. The sheet published to
        # the runtime was therefore scaled by a head belonging to a discarded image, which is
        # invisible in every deterministic gate and shows up only as one actor rendering at the
        # wrong size. That is the exact defect this reference exists to prevent, so it is taken
        # from the accepted bytes or not at all.
        if measures_scale_reference(spec.stage):
            await self._measure_actor_scale_reference(context, spec)
        return artifacts

    async def _accept_actor_facing(
        self, context: StageContext, spec: _ImageSpec, artifacts: Sequence[str]
    ) -> Sequence[str]:
        """Regenerate until the strip faces the contracted way, or fail the stage.

        Bounded by `_ACTOR_REVIEW_MAXIMUM_REGENERATIONS`, which is a semantic-regeneration budget
        and deliberately separate from the provider retry budget the generator owns.
        """

        rejected: list[dict[str, object]] = []
        for attempt in range(_ACTOR_REVIEW_MAXIMUM_REGENERATIONS + 1):
            try:
                await self._review_actor_facing(context, spec)
                return artifacts
            except ActorFacingError as error:
                rejected.append({"regeneration": attempt, **error.as_dict()})
                if attempt == _ACTOR_REVIEW_MAXIMUM_REGENERATIONS:
                    raise ActorFacingError(
                        f"{spec.stage} still faces {error.facing} after "
                        f"{_ACTOR_REVIEW_MAXIMUM_REGENERATIONS} semantic regenerations "
                        f"({json.dumps(rejected)})",
                        facing=error.facing,
                        evidence=error.evidence,
                    ) from error
                # `force` skips the cache. The artifact on disk passes every deterministic
                # contract, so without this the next call would reuse the rejected art.
                artifacts = await self._generate_image_asset(context, spec, force=True)
        return artifacts

    async def _accept_actor_build(
        self, context: StageContext, spec: _ImageSpec, artifacts: Sequence[str]
    ) -> Sequence[str]:
        """Reject a sheet drawn to a different build than the run asked for, and try again.

        Deterministic, and free of provider calls in its own right: the drawn build is the painted
        height over the head extent, and both are already measured for other reasons. So unlike
        facing - which needs a vision model because a silhouette does not locate a face - this is
        a gate, and it runs on every actor sheet held to the run's build rather than on a sample.

        It exists because the directive alone is not reliable. The first village generated with
        `CHARACTER PROPORTION` in its resident prompts returned three residents at 2.54, 3.06 and
        3.34 heads against a requested 2 - the right cast - and one elf at 7.47, drawn as a
        realistic adult. Nothing downstream could see that: every grid, alpha and facing contract
        passed. The runtime then matches heads, which converts the ignored directive into a
        resident rendering three and a half times the player's height.

        Mobs are exempt by `_holds_run_build`. A creature's build is its own; the run's head count
        describes its cast.
        """

        # Taken from the spec when the fan-out resolved a build for this particular actor, and
        # from the run otherwise. A directed village resolves each resident against their own
        # `body_kind`, so a two-head baker and a 2.4-head heron in the same village are each
        # judged against the number they were drawn to rather than against the player's.
        requested = _spec_requested_heads(spec)
        if requested is None:
            requested = await _actor_heads_tall(context)
        if requested is None:
            return artifacts
        rejected: list[dict[str, object]] = []
        for attempt in range(_ACTOR_REVIEW_MAXIMUM_REGENERATIONS + 1):
            try:
                await self._review_actor_build(context, spec, requested)
                return artifacts
            except ActorProportionError as error:
                rejected.append({"regeneration": attempt, **error.as_dict()})
                if attempt == _ACTOR_REVIEW_MAXIMUM_REGENERATIONS:
                    raise ActorProportionError(
                        f"{spec.stage} is still {error.measured:.2f} heads tall after "
                        f"{_ACTOR_REVIEW_MAXIMUM_REGENERATIONS} semantic regenerations "
                        f"({json.dumps(rejected)})",
                        measured=error.measured,
                        requested=error.requested,
                    ) from error
                artifacts = await self._generate_image_asset(context, spec, force=True)
                # The replacement is different artwork, so both prior readings describe an image
                # that no longer exists. Facing is re-reviewed and the head re-measured against
                # the new bytes before the build is judged again.
                if reviews_facing(spec.stage):
                    artifacts = await self._accept_actor_facing(context, spec, artifacts)
        return artifacts

    async def _review_actor_build(
        self, context: StageContext, spec: _ImageSpec, requested: float
    ) -> None:
        """Measure this sheet's drawn build and record it beside the artifact."""

        await self._measure_actor_scale_reference(context, spec)
        reference_path = _actor_scale_reference_path(spec)
        try:
            payload = json.loads(await asyncio.to_thread(reference_path.read_text, "utf-8"))
        except (OSError, ValueError):
            # No reference means no build to check. The stage that owns the measurement already
            # reports its own failure; re-reporting it here as a proportion fault would name the
            # wrong cause.
            return
        head_extent = payload.get("extent_pixels") if isinstance(payload, dict) else None
        if not isinstance(head_extent, (int, float)) or isinstance(head_extent, bool):
            return
        contract = _spec_grid_contract(spec)
        if contract is None:
            return
        cell_width, _cell_height = contract.cell_size(spec.width, spec.height)
        frame = scale_reference_frame(spec.stage)
        data = await asyncio.to_thread(spec.output.read_bytes)
        height = _painted_frame_height(data, frame=frame, cell_width=cell_width)
        if height is None:
            return
        evaluate_actor_proportion(
            requested_heads=requested,
            sprite_height_px=float(height),
            head_extent_px=float(head_extent),
        )

    async def _measure_actor_scale_reference(self, context: StageContext, spec: _ImageSpec) -> None:
        """Record one anatomical reference for this sheet, so the runtime can match scales.

        Cell geometry differs sheet to sheet and every one of them is a separate provider call,
        so nothing ties their draw scale together - measured on a real run the same character's
        head spans 223px idle, 161px crawling, 152px attacking and 47px climbing. The head is
        the one measurement that means the same thing in every pose, and it is not recoverable
        from alpha, so it is taken once here and written beside the artifact.
        """

        reference_path = _actor_scale_reference_path(spec)
        artifact = await asyncio.to_thread(spec.output.read_bytes)
        measured_sha256 = sha256_hex(artifact)
        if await _cached_actor_scale_reference(reference_path, measured_sha256) is not None:
            return
        contract = _spec_grid_contract(spec)
        if contract is None:
            return
        cell_width, cell_height = contract.cell_size(spec.width, spec.height)
        frame = scale_reference_frame(spec.stage)
        generated = await self._structured.generate(
            StructuredGenerationRequest(
                system=(
                    "You are a sprite-sheet measurer. Return only the strict structured object."
                ),
                prompt=actor_scale_reference_prompt(
                    _review_subject(spec.stage),
                    frame,
                    still=is_resident_still(spec.stage),
                ),
                artifact_path=reference_path,
                references=(await _structured_reference(spec.output),),
                schema=StructuredOutputSchema(
                    name=ACTOR_SCALE_REFERENCE_SCHEMA_NAME,
                    description="Anatomical scale reference for an actor animation strip",
                    json_schema=actor_scale_reference_json_schema(),
                    strict=True,
                ),
                parse=parse_actor_scale_reference,
                artifact_value=lambda reference: {
                    **evaluate_actor_scale_reference(
                        reference,
                        frame_width=cell_width,
                        frame_height=cell_height,
                    ),
                    "frame_index": frame,
                    "cell_width": cell_width,
                    "cell_height": cell_height,
                },
                validate=lambda reference: evaluate_actor_scale_reference(
                    reference, frame_width=cell_width, frame_height=cell_height
                ),
                metadata={
                    "stage": f"{spec.stage}-scale-reference",
                    "measured_sha256": measured_sha256,
                },
                timeout_seconds=context.config.capability_timeout_s,
                cancellation=context.cancellation,
            )
        )
        _ = generated

    async def _review_actor_facing(self, context: StageContext, spec: _ImageSpec) -> None:
        """Record which way a generated strip faces, and reject a confident wrong answer."""

        review_path = _actor_facing_review_path(spec)
        artifact = await asyncio.to_thread(spec.output.read_bytes)
        reviewed_sha256 = sha256_hex(artifact)
        required = required_facing(spec.stage)
        cached = await _cached_actor_facing_verdict(review_path, reviewed_sha256)
        if cached is not None:
            evaluate_actor_facing(cached, required=required)
            return
        reference = await _structured_reference(spec.output)
        generated = await self._structured.generate(
            StructuredGenerationRequest(
                system=(
                    "You are a sprite-sheet reviewer. Return only the strict structured object."
                ),
                prompt=actor_facing_prompt(
                    _review_subject(spec.stage),
                    still=is_resident_still(spec.stage),
                ),
                artifact_path=review_path,
                references=(reference,),
                schema=StructuredOutputSchema(
                    name=ACTOR_FACING_SCHEMA_NAME,
                    description="Which way an actor animation strip faces",
                    json_schema=actor_facing_json_schema(),
                    strict=True,
                ),
                parse=parse_actor_facing,
                artifact_value=lambda verdict: verdict.model_dump(mode="json"),
                metadata={
                    "stage": f"{spec.stage}-facing-review",
                    # Binds the verdict to the exact bytes it was taken on, so a resumed run can
                    # tell a reusable answer from one that belongs to superseded artwork.
                    "reviewed_sha256": reviewed_sha256,
                },
                timeout_seconds=context.config.capability_timeout_s,
                cancellation=context.cancellation,
            )
        )
        evaluate_actor_facing(generated.value, required=required)

    async def _generate_image_asset(
        self, context: StageContext, spec: _ImageSpec, *, force: bool = False
    ) -> Sequence[str]:
        compiled = await _read_compiled_theme(context)
        style = await _read_style_anchor(context)
        game = await _read_game_contract(context)
        character_profile = (
            await _read_character_profile(context) if _is_player_asset_stage(spec.stage) else None
        )
        grid_contract = _spec_grid_contract(spec)
        mode = context.config.transparency_mode if spec.transparent else None
        raw_path = _retained_raw_path(spec)
        if not force:
            image_provider = self._images.provider if spec.stage == "tileset" else ""
            image_model = self._images.model if spec.stage == "tileset" else ""
            tileset_resume = await _tileset_material_resume_record(
                context,
                spec,
                contract=grid_contract,
                mode=mode,
                image_provider=image_provider,
                image_model=image_model,
                theme_identity=compiled.identity if compiled is not None else None,
                style=style,
            )
            if tileset_resume is not None:
                if tileset_resume.get("cache_complete") is True:
                    return (str(spec.output), f"{spec.output}.meta.json")
                return await self._generate_tileset_material_atlas(
                    context,
                    spec,
                    sheet_failures=cast(list[dict[str, object]], tileset_resume["sheet_failures"]),
                    sheet_exhaustion=cast(dict[str, object], tileset_resume["sheet_exhaustion"]),
                    force=False,
                )
            if style is None:
                resume_record = _per_cell_resume_record(
                    raw_path,
                    spec=spec,
                    contract=grid_contract,
                    mode=mode,
                    theme_identity=compiled.identity if compiled is not None else None,
                )
                if resume_record is not None:
                    return await self._generate_per_cell_grid(
                        context,
                        spec,
                        sheet_failures=cast(
                            list[dict[str, object]], resume_record["sheet_failures"]
                        ),
                        sheet_exhaustion=cast(dict[str, object], resume_record["sheet_exhaustion"]),
                        force=False,
                    )
        raw_cache_valid = valid_artifact_pair(
            raw_path,
            transparency_mode=mode,
            validator=lambda path, meta: (
                _valid_raw_asset_cache(path, meta, spec=spec, contract=grid_contract)
                and _optional_theme_identity_matches(
                    meta, compiled.identity if compiled is not None else None
                )
                and _style_identity_matches(meta, style.identity if style is not None else None)
                and _character_profile_identity_matches(
                    meta,
                    character_profile.identity if character_profile is not None else None,
                )
            ),
            force=force,
        )
        if raw_cache_valid:
            if mode is None:
                return (str(spec.output), f"{spec.output}.meta.json")
            canonical_cache_valid = valid_artifact_pair(
                spec.output,
                transparency_mode=mode,
                validator=lambda path, meta: (
                    _valid_transparency_cache(
                        path,
                        meta,
                        raw_path=raw_path,
                        mode=mode,
                        width=spec.width,
                        height=spec.height,
                        contract=grid_contract,
                        expected_metadata=spec.metadata,
                    )
                    and _optional_theme_identity_matches(
                        meta, compiled.identity if compiled is not None else None
                    )
                    and _style_identity_matches(meta, style.identity if style is not None else None)
                    and _character_profile_identity_matches(
                        meta,
                        character_profile.identity if character_profile is not None else None,
                    )
                ),
                force=force,
            )
            if canonical_cache_valid:
                return (str(spec.output), f"{spec.output}.meta.json")
            canonical = await self._derive_transparency(context, spec, raw_path)
            return (str(spec.output), str(canonical))

        references = tuple(
            [
                await _image_reference(
                    path,
                    portable=spec.portable_references,
                )
                for path in spec.references
            ]
        )
        provider_path = raw_path.parent / f".{raw_path.name}.provider-{uuid.uuid4().hex}.png"
        prompt = spec.prompt
        request_metadata: dict[str, object] = {
            "stage": spec.stage,
            # The spec prompt is what asked for this artifact, so it is part of the artifact's
            # identity. Without it a rewritten prompt leaves every cached raw in place and the
            # new instruction silently never reaches the provider.
            "spec_prompt_sha256": sha256_hex(spec.prompt.encode()),
            "requested_width": spec.width,
            "requested_height": spec.height,
            **({"transparency_mode": str(mode)} if mode is not None else {}),
            **(spec.metadata or {}),
            **(
                {"grid_contract": grid_contract.as_dict(spec.width, spec.height)}
                if grid_contract is not None
                else {}
            ),
        }
        if compiled is not None:
            if spec.compiled_creative_base:
                prompt = _append_binding_visual_constraints(prompt, compiled.plan.hard_exclusions)
            else:
                prompt = _append_compiled_directive(
                    prompt,
                    _directive_for_image_stage(
                        compiled.plan,
                        spec.theme_family or spec.stage,
                    ),
                    compiled.plan.hard_exclusions,
                )
            request_metadata["theme_compilation"] = compiled.identity
        if style is not None:
            request_metadata["style_anchor"] = style.identity
        if character_profile is not None:
            request_metadata["character_profile"] = character_profile.identity
        if game is not None:
            # Appended after the theme directive and the style anchor, and before the
            # transparency clause. This is the most specific direction the run carries - it says
            # which game this is, where the anchor says which medium the repository draws in -
            # so it sits closest to the instruction the provider acts on last.
            prompt = append_game_art_direction_once(prompt, game.contract)
            request_metadata["game_contract"] = game.identity
        effective_prompt = _prompt_for_transparency(prompt, mode)
        if compiled is not None:
            assert_no_raw_theme_control_leak(effective_prompt)
            _assert_no_raw_theme_controls_in_metadata(request_metadata)

        def validate_provider(artifact: BinaryArtifact) -> dict[str, object]:
            return _validate_provider_asset(
                artifact.data,
                spec=spec,
                contract=grid_contract,
            )

        try:
            try:
                generated = await self._images.generate(
                    ImageGenerationRequest(
                        prompt=effective_prompt,
                        artifact_path=provider_path,
                        input_references=references,
                        aspect_ratio=_provider_aspect_ratio(spec.width, spec.height),
                        quality="high",
                        background="opaque",
                        moderation="low",
                        metadata=request_metadata,
                        timeout_seconds=context.config.capability_timeout_s,
                        cancellation=context.cancellation,
                        validate=validate_provider,
                        style_anchor=style.anchor if style is not None else None,
                        asset_kind=(
                            _asset_kind_for_image_stage(spec.stage) if style is not None else None
                        ),
                    )
                )
            except RetryExhaustedError as error:
                sheet_failures = _resolved_grid_failure_history(error)
                if _eligible_tileset_material_fallback(
                    spec,
                    grid_contract,
                    error,
                    sheet_failures,
                ):
                    return await self._generate_tileset_material_atlas(
                        context,
                        spec,
                        sheet_failures=sheet_failures,
                        sheet_exhaustion={
                            "attempts": error.attempts,
                            "retries": error.retries,
                            "request_prompt_sha256": sha256_hex(effective_prompt.encode()),
                        },
                        force=force,
                    )
                if _eligible_per_cell_fallback(
                    spec,
                    grid_contract,
                    error,
                    sheet_failures,
                ):
                    return await self._generate_per_cell_grid(
                        context,
                        spec,
                        sheet_failures=sheet_failures,
                        sheet_exhaustion={
                            "attempts": error.attempts,
                            "retries": error.retries,
                            "request_prompt_sha256": sha256_hex(effective_prompt.encode()),
                        },
                        force=force,
                    )
                if _eligible_isolated_view_fallback(spec, grid_contract, error):
                    return await self._generate_isolated_turnaround(
                        context,
                        spec,
                        sheet_error=error,
                        force=force,
                    )
                raise
            upstream = await _read_provenance(Path(generated.provenance_path))
            embedded_upstream = _embedded_provenance(upstream)
            _assert_temp_path_absent(embedded_upstream, provider_path)
            normalized, record = normalize_png(generated.data, width=spec.width, height=spec.height)
            source_metadata = upstream.params.get("metadata")
            source_metadata = source_metadata if isinstance(source_metadata, dict) else {}
            source_hash = sha256_hex(generated.data)
            sidecar = await write_artifact_with_provenance_async(
                raw_path,
                BinaryArtifact(data=normalized, media_type="image/png"),
                ProvenanceInput(
                    provider=upstream.provider,
                    model=upstream.model,
                    seed=upstream.seed,
                    prompt=upstream.prompt,
                    refs=list(upstream.refs),
                    inputs=[
                        *upstream.inputs,
                        *(
                            [
                                InputProvenance(
                                    ref=str(compiled.identity["artifact_ref"]),
                                    sha256=str(compiled.identity["artifact_sha256"]),
                                    source="content",
                                    bytes=compiled.artifact_bytes,
                                    media_type="application/json",
                                )
                            ]
                            if compiled is not None
                            else []
                        ),
                        *([_style_anchor_input(style)] if style is not None else []),
                        *(
                            [_character_profile_input(character_profile)]
                            if character_profile is not None
                            else []
                        ),
                        InputProvenance(
                            ref=f"provider-output:{spec.stage}",
                            sha256=source_hash,
                            source="content",
                            bytes=len(generated.data),
                            media_type=generated.media_type,
                        ),
                    ],
                    params={
                        **upstream.params,
                        "metadata": {
                            **source_metadata,
                            "stage": spec.stage,
                            "normalization": record.as_dict(),
                            **({"transparency_mode": str(mode)} if mode is not None else {}),
                            **(spec.metadata or {}),
                            **(
                                {"grid_contract": grid_contract.as_dict(spec.width, spec.height)}
                                if grid_contract is not None
                                else {}
                            ),
                            **(
                                {"theme_compilation": compiled.identity}
                                if compiled is not None
                                else {}
                            ),
                            **({"style_anchor": style.identity} if style is not None else {}),
                            **(
                                {"character_profile": character_profile.identity}
                                if character_profile is not None
                                else {}
                            ),
                        },
                        "postprocess": [record.as_dict()],
                        "upstream_provenance": embedded_upstream,
                    },
                    validation={
                        **upstream.validation,
                        "exact_contract_dimensions": True,
                        "output_width": spec.width,
                        "output_height": spec.height,
                        "output_sha256": sha256_hex(normalized),
                    },
                    component=_RECIPE_COMPONENT,
                    tool=SoftwareIdentity(
                        name=str(record.tool["name"]),
                        version=str(record.tool["version"]),
                    ),
                    attempts=upstream.attempts,
                    response={
                        **(upstream.response or {}),
                        "source_component": upstream.component.model_dump(mode="json"),
                        "source_artifact_sha256": source_hash,
                        "upstream_provenance": "inline",
                    },
                ),
            )
            if mode is None:
                return (str(raw_path), str(sidecar))
            canonical = await self._derive_transparency(context, spec, raw_path)
            return (str(spec.output), str(canonical))
        finally:
            await asyncio.to_thread(provider_path.unlink, missing_ok=True)
            await asyncio.to_thread(Path(f"{provider_path}.meta.json").unlink, missing_ok=True)

    async def _generate_isolated_turnaround(
        self,
        context: StageContext,
        spec: _ImageSpec,
        *,
        sheet_error: RetryExhaustedError,
        force: bool,
    ) -> Sequence[str]:
        contract = _spec_grid_contract(spec)
        if contract is None or (contract.rows, contract.columns) != (1, 3):
            raise ValueError("isolated-view fallback requires an exact 1x3 concept contract")
        if not spec.references:
            raise ValueError("isolated-view fallback requires the world concept reference")
        compiled = await _read_compiled_theme(context)
        style = await _read_style_anchor(context)
        character_profile = (
            await _read_character_profile(context) if _is_player_asset_stage(spec.stage) else None
        )
        cell_width, cell_height = contract.cell_size(spec.width, spec.height)
        world_concept = spec.references[0]
        view_outputs: list[Path] = []
        view_data: list[bytes] = []
        component_records: list[dict[str, object]] = []
        identity_anchor: dict[str, object] | None = None

        for index, role in enumerate(_TURNAROUND_VIEW_ROLES):
            view_output = _isolated_view_output(spec.output, index)
            references = (world_concept,) if index == 0 else (world_concept, view_outputs[0])
            reference_bindings: list[dict[str, object]] = []
            for reference in references:
                reference_data = await asyncio.to_thread(reference.read_bytes)
                reference_bindings.append(
                    {
                        "path": reference.name,
                        "sha256": sha256_hex(reference_data),
                        "bytes": len(reference_data),
                    }
                )
            view_prompt = _isolated_view_prompt(spec.prompt, role)
            view_contract = _isolated_view_request_contract(
                spec,
                index=index,
                role=role,
                prompt=view_prompt,
                reference_bindings=reference_bindings,
                identity_anchor=identity_anchor,
            )
            family = _isolated_view_family(spec.stage)
            view_spec = _ImageSpec(
                stage=f"{family}-isolated-view-{index}",
                prompt=view_prompt,
                output=view_output,
                width=cell_width,
                height=cell_height,
                references=references,
                metadata={
                    "parent_stage": spec.stage,
                    "isolated_view_fallback": view_contract,
                },
                isolated_view=True,
            )
            await self._generate_image_asset(context, view_spec, force=force)
            raw_path = _retained_raw_path(view_spec)
            canonical = await asyncio.to_thread(view_output.read_bytes)
            raw = await asyncio.to_thread(raw_path.read_bytes)
            validate_isolated_view_alpha(canonical)
            raw_record = await _read_provenance(Path(f"{raw_path}.meta.json"))
            canonical_record = await _read_provenance(Path(f"{view_output}.meta.json"))
            component = _isolated_view_component_record(
                index=index,
                role=role,
                raw_path=raw_path,
                raw=raw,
                raw_record=raw_record,
                canonical_path=view_output,
                canonical=canonical,
                canonical_record=canonical_record,
                identity_anchor=identity_anchor,
            )
            component_records.append(component)
            view_outputs.append(view_output)
            view_data.append(canonical)
            if index == 0:
                identity_anchor = {
                    "path": view_output.name,
                    "sha256": sha256_hex(canonical),
                    "bytes": len(canonical),
                    "source_view": 0,
                }

        precomposite = Image.new("RGBA", (spec.width, spec.height), (0, 0, 0, 0))
        for index, data in enumerate(view_data):
            with Image.open(BytesIO(data)) as opened:
                view = opened.convert("RGBA")
            precomposite.alpha_composite(view, (index * cell_width, 0))
        canonical, geometry_validation = normalize_canonical_grid(
            _image_png_bytes(precomposite), contract
        )
        with Image.open(BytesIO(canonical)) as opened:
            canonical_image = opened.convert("RGBA")
        background = (
            (255, 0, 255) if str(context.config.transparency_mode) == "chroma" else (128, 128, 128)
        )
        raw_image = Image.new("RGB", canonical_image.size, background)
        raw_image.paste(canonical_image.convert("RGB"), mask=canonical_image.getchannel("A"))
        raw = _image_png_bytes(raw_image)
        source_validation = validate_generated_source(
            raw,
            width=spec.width,
            height=spec.height,
            contract=contract,
        )
        grid_normalization = geometry_validation.get("grid_normalization")
        if not isinstance(grid_normalization, dict):
            raise ValueError("isolated-view fallback grid normalization evidence is missing")
        bound_normalization = _bind_grid_normalization_to_raw(grid_normalization, raw=raw)
        geometry_validation = {
            **geometry_validation,
            "grid_normalization": bound_normalization,
        }
        fallback_record = _isolated_view_fallback_record(
            spec,
            contract=contract,
            mode=str(context.config.transparency_mode),
            sheet_error=sheet_error,
            components=component_records,
            raw=raw,
            canonical=canonical,
        )
        raw_path = _retained_raw_path(spec)
        metadata = {
            "stage": spec.stage,
            "spec_prompt_sha256": sha256_hex(spec.prompt.encode()),
            "transparency_mode": str(context.config.transparency_mode),
            **(spec.metadata or {}),
            "grid_contract": contract.as_dict(spec.width, spec.height),
            "isolated_view_fallback": fallback_record,
            **({"theme_compilation": compiled.identity} if compiled is not None else {}),
            **({"style_anchor": style.identity} if style is not None else {}),
            **(
                {"character_profile": character_profile.identity}
                if character_profile is not None
                else {}
            ),
        }
        component_inputs = _isolated_view_component_inputs(component_records)
        theme_inputs = (
            [
                InputProvenance(
                    ref=str(compiled.identity["artifact_ref"]),
                    sha256=str(compiled.identity["artifact_sha256"]),
                    source="content",
                    bytes=compiled.artifact_bytes,
                    media_type="application/json",
                )
            ]
            if compiled is not None
            else []
        )
        style_inputs = [_style_anchor_input(style)] if style is not None else []
        profile_inputs = (
            [_character_profile_input(character_profile)] if character_profile is not None else []
        )
        raw_sidecar = await write_artifact_with_provenance_async(
            raw_path,
            BinaryArtifact(data=raw, media_type="image/png"),
            ProvenanceInput(
                provider="local",
                model=_ISOLATED_VIEW_FALLBACK_VERSION,
                prompt=spec.prompt,
                refs=[str(component["raw_path"]) for component in component_records],
                inputs=[*component_inputs, *theme_inputs, *style_inputs, *profile_inputs],
                params={
                    "metadata": metadata,
                    "fallback": fallback_record,
                },
                validation={
                    "exact_contract_dimensions": True,
                    "output_width": spec.width,
                    "output_height": spec.height,
                    "output_sha256": sha256_hex(raw),
                    **source_validation,
                },
                component=_RECIPE_COMPONENT,
                tool=SoftwareIdentity(
                    name="isolated-view-compositor",
                    version=_ISOLATED_VIEW_FALLBACK_VERSION,
                ),
                attempts=1,
                response={"sheet_exhaustion": fallback_record["sheet_exhaustion"]},
            ),
        )
        raw_record = await _read_provenance(Path(raw_sidecar))
        embedded_raw = _embedded_provenance(raw_record)
        transparent_pixels, nontransparent_pixels = _alpha_counts(canonical)
        output_hash = sha256_hex(canonical)
        canonical_sidecar = await write_artifact_with_provenance_async(
            spec.output,
            BinaryArtifact(data=canonical, media_type="image/png"),
            ProvenanceInput(
                provider="local",
                model=_ISOLATED_VIEW_FALLBACK_VERSION,
                prompt=spec.prompt,
                refs=[raw_path.name, *[path.name for path in view_outputs]],
                inputs=[
                    InputProvenance(
                        ref=raw_path.name,
                        sha256=sha256_hex(raw),
                        source="content",
                        bytes=len(raw),
                        media_type="image/png",
                    ),
                    *component_inputs,
                    *theme_inputs,
                    *style_inputs,
                    *profile_inputs,
                ],
                params={
                    "transparency": {
                        "mode": str(context.config.transparency_mode),
                        "retained_raw_path": raw_path.name,
                        "raw_sha256": sha256_hex(raw),
                        "output_sha256": output_hash,
                        "processor": {
                            "kind": (f"{_ISOLATED_VIEW_FALLBACK_VERSION}+grid-cell-normalization"),
                            "version": GRID_NORMALIZATION_VERSION,
                        },
                        "source_provenance": embedded_raw,
                        "grid_normalization": bound_normalization,
                        "isolated_view_fallback": fallback_record,
                    },
                    "metadata": metadata,
                },
                validation={
                    "alpha_nontrivial": True,
                    "transparent_pixels": transparent_pixels,
                    "nontransparent_pixels": nontransparent_pixels,
                    "dimensions_preserved": True,
                    "output_width": spec.width,
                    "output_height": spec.height,
                    "output_sha256": output_hash,
                    "isolated_view_fallback": fallback_record,
                    **geometry_validation,
                },
                component=_RECIPE_COMPONENT,
                tool=SoftwareIdentity(
                    name="isolated-view-compositor",
                    version=_ISOLATED_VIEW_FALLBACK_VERSION,
                ),
                attempts=1,
                response={
                    "sheet_exhaustion": fallback_record["sheet_exhaustion"],
                    "identity_anchor": identity_anchor,
                },
            ),
        )
        return str(spec.output), str(canonical_sidecar)

    async def _generate_per_cell_grid(
        self,
        context: StageContext,
        spec: _ImageSpec,
        *,
        sheet_failures: list[dict[str, object]],
        sheet_exhaustion: dict[str, object],
        force: bool,
    ) -> Sequence[str]:
        contract = _spec_grid_contract(spec)
        if contract is None or (contract.rows, contract.columns) != (2, 4):
            raise ValueError("per-cell generation requires an exact 2x4 parent contract")
        if not _eligible_per_cell_stage(spec):
            raise ValueError(f"per-cell generation is not enabled for {spec.stage}")
        if not _valid_per_cell_failure_history(sheet_failures):
            raise ValueError("per-cell generation requires six eligible typed sheet failures")

        compiled = await _read_compiled_theme(context)
        style = await _read_style_anchor(context)
        plan = await _build_per_cell_adapter_plan(context, spec)
        cell_width, cell_height = contract.cell_size(spec.width, spec.height)
        prior_bindings: dict[int, dict[str, object]] = {}
        if plan.layout_prior is not None:
            for cell in plan.cells:
                prior_bindings[cell.index] = await _write_per_cell_prior(
                    plan.layout_prior,
                    output=_per_cell_prior_output(spec.output, cell.row, cell.column),
                    row=cell.row,
                    column=cell.column,
                    rows=contract.rows,
                    columns=contract.columns,
                )

        component_records: list[dict[str, object] | None] = [None] * len(plan.cells)
        component_data: list[bytes | None] = [None] * len(plan.cells)
        identity_anchor: dict[str, object] | None = None

        async def generate_cell(
            cell: _PerCellDefinition,
            anchor: Mapping[str, object] | None,
        ) -> None:
            prior = prior_bindings.get(cell.index)
            references = [plan.world_concept]
            reference_roles = ["world-concept-style-reference"]
            if anchor is not None:
                references.append(spec.output.with_name(str(anchor["path"])))
                reference_roles.append("cell-0-style-scale-anchor")
            if prior is not None:
                references.append(spec.output.with_name(str(prior["path"])))
                reference_roles.append("cell-layout-prior")
            bindings = await _per_cell_reference_bindings(
                references,
                roles=reference_roles,
            )
            cell_contract = _per_cell_component_contract(
                spec,
                plan=plan,
                cell=cell,
                reference_bindings=bindings,
                identity_anchor=anchor,
                prior=prior,
            )
            cell_output = _per_cell_output(spec.output, cell.row, cell.column)
            cell_spec = _ImageSpec(
                stage=f"per-cell-{plan.adapter}-{cell.index}",
                prompt=cell.prompt,
                output=cell_output,
                width=cell_width,
                height=cell_height,
                references=tuple(references),
                metadata={
                    "parent_stage": spec.stage,
                    "per_cell_generation": cell_contract,
                },
                isolated_view=True,
                theme_family="items",
                portable_references=True,
            )
            try:
                await self._generate_image_asset(context, cell_spec, force=force)
            except Exception as error:
                raise RuntimeError(
                    f"per-cell {cell.role} ({cell.row},{cell.column}) failed: {error}"
                ) from error
            raw_path = _retained_raw_path(cell_spec)
            raw = await asyncio.to_thread(raw_path.read_bytes)
            canonical = await asyncio.to_thread(cell_output.read_bytes)
            _validate_per_cell_component_bytes(raw, canonical, cell_contract)
            raw_record = await _read_provenance(Path(f"{raw_path}.meta.json"))
            canonical_record = await _read_provenance(Path(f"{cell_output}.meta.json"))
            component_records[cell.index] = _per_cell_component_record(
                cell=cell,
                raw_path=raw_path,
                raw=raw,
                raw_record=raw_record,
                canonical_path=cell_output,
                canonical=canonical,
                canonical_record=canonical_record,
                cell_contract=cell_contract,
                prior=prior,
            )
            component_data[cell.index] = canonical

        async def generate_parallel(
            cells: Sequence[_PerCellDefinition],
            anchor: Mapping[str, object] | None,
        ) -> None:
            try:
                async with asyncio.TaskGroup() as group:
                    for cell in cells:
                        group.create_task(
                            generate_cell(cell, anchor),
                            name=f"per-cell:{spec.stage}:{cell.index}",
                        )
            except ExceptionGroup as error:
                leaf = _actionable_exception(error)
                raise RuntimeError(str(leaf)) from leaf

        if plan.identity_policy == "cell-0-scale-style-anchor":
            first = plan.cells[0]
            await generate_cell(first, None)
            first_data = component_data[0]
            if first_data is None:
                raise ValueError("per-cell anchor component is missing")
            first_output = _per_cell_output(spec.output, first.row, first.column)
            identity_anchor = {
                "path": first_output.name,
                "sha256": sha256_hex(first_data),
                "bytes": len(first_data),
                "source_cell": 0,
                "usage": "style-and-scale-only",
            }
            await generate_parallel(plan.cells[1:], identity_anchor)
        else:
            await generate_parallel(plan.cells, None)

        if any(record is None for record in component_records) or any(
            data is None for data in component_data
        ):
            raise ValueError("per-cell generation did not produce every declared component")
        records = cast(list[dict[str, object]], component_records)
        canonical_cells = cast(list[bytes], component_data)

        precomposite = Image.new("RGBA", (spec.width, spec.height), (0, 0, 0, 0))
        for cell, data in zip(plan.cells, canonical_cells, strict=True):
            with Image.open(BytesIO(data)) as opened:
                view = opened.convert("RGBA")
            precomposite.alpha_composite(
                view,
                (cell.column * cell_width, cell.row * cell_height),
            )
        canonical, geometry_validation = normalize_canonical_grid(
            _image_png_bytes(precomposite),
            contract,
        )
        validate_canonical_grid(canonical, contract)
        with Image.open(BytesIO(canonical)) as opened:
            canonical_image = opened.convert("RGBA")
        background = (
            (255, 0, 255)
            if context.config.transparency_mode == TransparencyMode.CHROMA
            else (128, 128, 128)
        )
        raw_image = Image.new("RGB", canonical_image.size, background)
        raw_image.paste(canonical_image.convert("RGB"), mask=canonical_image.getchannel("A"))
        raw = _image_png_bytes(raw_image)
        source_validation = validate_generated_source(
            raw,
            width=spec.width,
            height=spec.height,
            contract=contract,
        )
        normalization = geometry_validation.get("grid_normalization")
        if not isinstance(normalization, dict):
            raise ValueError("per-cell composite normalization evidence is missing")
        bound_normalization = _bind_grid_normalization_to_raw(normalization, raw=raw)
        geometry_validation = {
            **geometry_validation,
            "grid_normalization": bound_normalization,
        }
        fallback_record = _per_cell_fallback_record(
            spec,
            plan=plan,
            contract=contract,
            mode=str(context.config.transparency_mode),
            sheet_failures=sheet_failures,
            sheet_exhaustion=sheet_exhaustion,
            components=records,
            identity_anchor=identity_anchor,
            normalization=bound_normalization,
            raw=raw,
            canonical=canonical,
            theme_identity=compiled.identity if compiled is not None else None,
        )
        metadata = {
            "stage": spec.stage,
            "spec_prompt_sha256": sha256_hex(spec.prompt.encode()),
            "transparency_mode": str(context.config.transparency_mode),
            **(spec.metadata or {}),
            "grid_contract": contract.as_dict(spec.width, spec.height),
            "per_cell_generation": fallback_record,
            **({"theme_compilation": compiled.identity} if compiled is not None else {}),
            **({"style_anchor": style.identity} if style is not None else {}),
        }
        component_inputs = _per_cell_component_inputs(records)
        theme_inputs = (
            [
                InputProvenance(
                    ref=str(compiled.identity["artifact_ref"]),
                    sha256=str(compiled.identity["artifact_sha256"]),
                    source="content",
                    bytes=compiled.artifact_bytes,
                    media_type="application/json",
                )
            ]
            if compiled is not None
            else []
        )
        style_inputs = [_style_anchor_input(style)] if style is not None else []
        raw_path = _retained_raw_path(spec)
        raw_sidecar = await write_artifact_with_provenance_async(
            raw_path,
            BinaryArtifact(data=raw, media_type="image/png"),
            ProvenanceInput(
                provider="local",
                model=_PER_CELL_GENERATION_VERSION,
                prompt=spec.prompt,
                refs=[str(record["raw_path"]) for record in records],
                inputs=[*component_inputs, *theme_inputs, *style_inputs],
                params={
                    "metadata": metadata,
                    "fallback": fallback_record,
                },
                validation={
                    "exact_contract_dimensions": True,
                    "output_width": spec.width,
                    "output_height": spec.height,
                    "output_sha256": sha256_hex(raw),
                    **source_validation,
                },
                component=_RECIPE_COMPONENT,
                tool=SoftwareIdentity(
                    name="per-cell-compositor",
                    version=_PER_CELL_GENERATION_VERSION,
                ),
                attempts=1,
                response={"sheet_exhaustion": sheet_exhaustion},
            ),
        )
        raw_record = await _read_provenance(Path(raw_sidecar))
        output_hash = sha256_hex(canonical)
        transparent_pixels, nontransparent_pixels = _alpha_counts(canonical)
        canonical_sidecar = await write_artifact_with_provenance_async(
            spec.output,
            BinaryArtifact(data=canonical, media_type="image/png"),
            ProvenanceInput(
                provider="local",
                model=_PER_CELL_GENERATION_VERSION,
                prompt=spec.prompt,
                refs=[raw_path.name, *[str(record["canonical_path"]) for record in records]],
                inputs=[
                    InputProvenance(
                        ref=raw_path.name,
                        sha256=sha256_hex(raw),
                        source="content",
                        bytes=len(raw),
                        media_type="image/png",
                    ),
                    *component_inputs,
                    *theme_inputs,
                    *style_inputs,
                ],
                params={
                    "transparency": {
                        "mode": str(context.config.transparency_mode),
                        "retained_raw_path": raw_path.name,
                        "raw_sha256": sha256_hex(raw),
                        "output_sha256": output_hash,
                        "processor": {
                            "kind": (f"{_PER_CELL_GENERATION_VERSION}+grid-cell-normalization"),
                            "version": GRID_NORMALIZATION_VERSION,
                        },
                        "source_provenance": _embedded_provenance(raw_record),
                        "grid_normalization": bound_normalization,
                        "per_cell_generation": fallback_record,
                    },
                    "metadata": metadata,
                },
                validation={
                    "alpha_nontrivial": True,
                    "transparent_pixels": transparent_pixels,
                    "nontransparent_pixels": nontransparent_pixels,
                    "dimensions_preserved": True,
                    "output_width": spec.width,
                    "output_height": spec.height,
                    "output_sha256": output_hash,
                    "per_cell_generation": fallback_record,
                    **geometry_validation,
                },
                component=_RECIPE_COMPONENT,
                tool=SoftwareIdentity(
                    name="per-cell-compositor",
                    version=_PER_CELL_GENERATION_VERSION,
                ),
                attempts=1,
                response={
                    "sheet_exhaustion": sheet_exhaustion,
                    "identity_anchor": identity_anchor,
                },
            ),
        )
        return str(spec.output), str(canonical_sidecar)

    async def _generate_tileset_material_atlas(
        self,
        context: StageContext,
        spec: _ImageSpec,
        *,
        sheet_failures: list[dict[str, object]],
        sheet_exhaustion: dict[str, object],
        force: bool,
    ) -> Sequence[str]:
        contract = _spec_grid_contract(spec)
        if (
            contract is None
            or contract.topology != "tileset"
            or (contract.rows, contract.columns) != (4, 12)
            or not spec.transparent
            or not _valid_tileset_material_failure_history(sheet_failures)
            or not _valid_tileset_sheet_exhaustion(sheet_exhaustion)
        ):
            raise ValueError(
                "tileset material synthesis requires six typed cross-cell sheet failures"
            )
        compiled = await _read_compiled_theme(context)
        style = await _read_style_anchor(context)
        plan = await _build_tileset_material_plan(
            context,
            spec,
            contract=contract,
            sheet_failures=sheet_failures,
            sheet_exhaustion=sheet_exhaustion,
            image_provider=self._images.provider,
            image_model=self._images.model,
            theme_identity=compiled.identity if compiled is not None else None,
            style=style,
            theme_directive=_tileset_material_theme_directive(compiled),
        )
        try:
            fill_record, fill, fill_regenerated = await self._generate_tileset_material_swatch(
                context,
                spec,
                plan=plan,
                role="fill",
                fill_anchor=None,
                force=force,
            )
        except Exception as error:
            raise RuntimeError(f"tileset material fill failed: {error}") from error

        child_results: dict[str, tuple[dict[str, object], bytes, bool]] = {}

        async def generate_child(role: str) -> None:
            try:
                child_results[role] = await self._generate_tileset_material_swatch(
                    context,
                    spec,
                    plan=plan,
                    role=role,
                    fill_anchor=fill,
                    force=force or fill_regenerated,
                )
            except Exception as error:
                raise RuntimeError(f"tileset material {role} failed: {error}") from error

        try:
            async with asyncio.TaskGroup() as group:
                for role in ("cap", "edge"):
                    group.create_task(generate_child(role), name=f"tileset-material:{role}")
        except ExceptionGroup as error:
            leaf = _actionable_exception(error)
            raise RuntimeError(f"tileset material swatch failed: {leaf}") from leaf
        if set(child_results) != {"cap", "edge"}:
            raise ValueError("tileset material synthesis did not produce both dependent swatches")
        cap_record, cap, _cap_regenerated = child_results["cap"]
        edge_record, edge, _edge_regenerated = child_results["edge"]
        wireframe = await asyncio.to_thread(plan.wireframe.read_bytes)
        canonical, synthesis = synthesize_tileset_from_materials(
            fill=fill,
            cap=cap,
            edge=edge,
            wireframe=wireframe,
            width=spec.width,
            height=spec.height,
        )
        final_grid = validate_canonical_grid(canonical, contract)
        background_rgb = (
            (255, 0, 255)
            if context.config.transparency_mode == TransparencyMode.CHROMA
            else (128, 128, 128)
        )
        retained_raw, flattening = flatten_tileset_to_background(
            canonical,
            background_rgb=background_rgb,
        )
        source_validation = validate_generated_source(
            retained_raw,
            width=spec.width,
            height=spec.height,
            contract=contract,
        )
        dependency = tileset_material_dependency_evidence(
            fill=fill,
            cap=cap,
            edge=edge,
        )
        components = [fill_record, cap_record, edge_record]
        fallback = _tileset_material_fallback_record(
            spec,
            plan=plan,
            contract=contract,
            mode=str(context.config.transparency_mode),
            sheet_failures=sheet_failures,
            sheet_exhaustion=sheet_exhaustion,
            components=components,
            dependency=dependency,
            synthesis=synthesis,
            flattening=flattening,
            retained_raw=retained_raw,
            canonical=canonical,
            final_grid=final_grid,
        )
        component_inputs = _tileset_material_component_inputs(components)
        theme_inputs = (
            [
                InputProvenance(
                    ref=str(compiled.identity["artifact_ref"]),
                    sha256=str(compiled.identity["artifact_sha256"]),
                    source="content",
                    bytes=compiled.artifact_bytes,
                    media_type="application/json",
                )
            ]
            if compiled is not None
            else []
        )
        style_inputs = [_style_anchor_input(style)] if style is not None else []
        world_input = _input_from_binding(
            cast(Mapping[str, object], plan.parent_contract["world_spec"]),
            media_type="application/json",
        )
        template_input = _input_from_binding(
            cast(Mapping[str, object], plan.parent_contract["wireframe"]),
            media_type="image/png",
        )
        raw_path = _retained_raw_path(spec)
        metadata = {
            "stage": spec.stage,
            "spec_prompt_sha256": sha256_hex(spec.prompt.encode()),
            "transparency_mode": str(context.config.transparency_mode),
            **(spec.metadata or {}),
            "grid_contract": contract.as_dict(spec.width, spec.height),
            "tileset_material_synthesis": fallback,
            **({"theme_compilation": compiled.identity} if compiled is not None else {}),
            **({"style_anchor": style.identity} if style is not None else {}),
        }
        raw_provenance = ProvenanceInput(
            provider="local",
            model=TILESET_MATERIAL_SYNTHESIS_VERSION,
            prompt=spec.prompt,
            refs=[str(component["canonical_path"]) for component in components],
            inputs=[world_input, template_input, *component_inputs, *theme_inputs, *style_inputs],
            params={"metadata": metadata, "fallback": fallback},
            validation={
                "exact_contract_dimensions": True,
                "output_width": spec.width,
                "output_height": spec.height,
                "output_sha256": sha256_hex(retained_raw),
                "tileset_material_synthesis": synthesis,
                "tileset_material_flattening": flattening,
                **source_validation,
            },
            component=_RECIPE_COMPONENT,
            tool=SoftwareIdentity(
                name="tileset-material-assembler",
                version=TILESET_MATERIAL_SYNTHESIS_VERSION,
            ),
            attempts=1,
            response={"sheet_exhaustion": sheet_exhaustion},
        )
        transparent_pixels, nontransparent_pixels = _alpha_counts(canonical)
        canonical_provenance = ProvenanceInput(
            provider="local",
            model=TILESET_MATERIAL_SYNTHESIS_VERSION,
            prompt=spec.prompt,
            refs=[raw_path.name, *[str(component["canonical_path"]) for component in components]],
            inputs=[
                InputProvenance(
                    ref=raw_path.name,
                    sha256=sha256_hex(retained_raw),
                    source="content",
                    bytes=len(retained_raw),
                    media_type="image/png",
                ),
                world_input,
                template_input,
                *component_inputs,
                *theme_inputs,
                *style_inputs,
            ],
            params={
                "transparency": {
                    "mode": str(context.config.transparency_mode),
                    "retained_raw_path": raw_path.name,
                    "raw_sha256": sha256_hex(retained_raw),
                    "output_sha256": sha256_hex(canonical),
                    "processor": {
                        "kind": TILESET_MATERIAL_SYNTHESIS_VERSION,
                        "version": TILESET_MATERIAL_SYNTHESIS_VERSION,
                    },
                    "tileset_material_synthesis": fallback,
                },
                "metadata": metadata,
            },
            validation={
                "alpha_nontrivial": True,
                "transparent_pixels": transparent_pixels,
                "nontransparent_pixels": nontransparent_pixels,
                "dimensions_preserved": True,
                "output_width": spec.width,
                "output_height": spec.height,
                "output_sha256": sha256_hex(canonical),
                "tileset_material_synthesis": synthesis,
                "tileset_material_flattening": flattening,
                "tileset_material_fallback": fallback,
                **final_grid,
            },
            component=_RECIPE_COMPONENT,
            tool=SoftwareIdentity(
                name="tileset-material-assembler",
                version=TILESET_MATERIAL_SYNTHESIS_VERSION,
            ),
            attempts=1,
            response={
                "sheet_exhaustion": sheet_exhaustion,
                "dependency_dag": dependency,
            },
        )
        sidecars = await write_artifact_bundle_with_provenance_async(
            (
                ArtifactBundleEntry(
                    path=raw_path,
                    artifact=BinaryArtifact(data=retained_raw, media_type="image/png"),
                    provenance=raw_provenance,
                ),
                ArtifactBundleEntry(
                    path=spec.output,
                    artifact=BinaryArtifact(data=canonical, media_type="image/png"),
                    provenance=canonical_provenance,
                ),
            )
        )
        return str(spec.output), str(sidecars[1])

    async def _generate_tileset_material_swatch(
        self,
        context: StageContext,
        parent: _ImageSpec,
        *,
        plan: _TilesetMaterialPlan,
        role: str,
        fill_anchor: bytes | None,
        force: bool,
    ) -> tuple[dict[str, object], bytes, bool]:
        if role not in {"fill", "cap", "edge"}:
            raise ValueError(f"unknown tileset material role: {role}")
        style = await _read_style_anchor(context)
        canonical_path = _tileset_material_output(parent.output, role)
        raw_path = canonical_path.with_name(f"{canonical_path.stem}.raw.png")
        references = [plan.world_concept]
        reference_roles = ["world-concept-style-reference"]
        if role != "fill":
            if fill_anchor is None:
                raise ValueError(f"tileset {role} requires the accepted FILL anchor")
            references.append(_tileset_material_output(parent.output, "fill"))
            reference_roles.append("fill-material-style-scale-anchor")
        reference_bindings = await _tileset_material_reference_bindings(
            references,
            roles=reference_roles,
        )
        component_contract = _tileset_material_component_contract(
            plan,
            role=role,
            prompt=plan.prompts[role],
            reference_bindings=reference_bindings,
            fill_anchor=fill_anchor,
        )
        if not force:
            cached = await asyncio.to_thread(
                _cached_tileset_material_component,
                canonical_path,
                raw_path,
                role=role,
                component_contract=component_contract,
                fill_anchor=fill_anchor,
            )
            if cached is not None:
                return cached, await asyncio.to_thread(canonical_path.read_bytes), False

        provider_path = canonical_path.parent / (
            f".{canonical_path.name}.provider-{uuid.uuid4().hex}.png"
        )
        references_payload = tuple(
            [await _image_reference(reference, portable=True) for reference in references]
        )

        def validate_provider(artifact: BinaryArtifact) -> dict[str, object]:
            return validate_tileset_material_swatch(
                artifact.data,
                role=cast(Any, role),
                fill_anchor=fill_anchor,
            )

        try:
            generated = await self._images.generate(
                ImageGenerationRequest(
                    prompt=plan.prompts[role],
                    artifact_path=provider_path,
                    input_references=references_payload,
                    aspect_ratio="1:1",
                    quality="high",
                    background="opaque",
                    moderation="low",
                    metadata={
                        "stage": f"tileset-material-{role}",
                        "parent_stage": parent.stage,
                        "tileset_material_component": component_contract,
                        **({"style_anchor": style.identity} if style is not None else {}),
                    },
                    timeout_seconds=context.config.capability_timeout_s,
                    cancellation=context.cancellation,
                    validate=validate_provider,
                    style_anchor=style.anchor if style is not None else None,
                    asset_kind="tileable_texture" if style is not None else None,
                )
            )
            upstream = await _read_provenance(Path(generated.provenance_path))
            embedded_upstream = _embedded_provenance(upstream)
            _assert_temp_path_absent(embedded_upstream, provider_path)
            normalized, normalization = normalize_png(
                generated.data,
                width=_TILESET_MATERIAL_SWATCH_SIZE,
                height=_TILESET_MATERIAL_SWATCH_SIZE,
            )
            canonical, canonicalization = canonicalize_tileset_material(
                normalized,
                role=cast(Any, role),
                fill_anchor=fill_anchor,
            )
            validation = validate_tileset_material_swatch(
                canonical,
                role=cast(Any, role),
                fill_anchor=fill_anchor,
            )
            source_hash = sha256_hex(generated.data)
            metadata = {
                "stage": f"tileset-material-{role}",
                "parent_stage": parent.stage,
                "tileset_material_component": component_contract,
                "tileset_material_parent": plan.parent_contract,
                **({"style_anchor": style.identity} if style is not None else {}),
            }
            raw_provenance = ProvenanceInput(
                provider=upstream.provider,
                model=upstream.model,
                seed=upstream.seed,
                prompt=upstream.prompt,
                refs=list(upstream.refs),
                inputs=[
                    *upstream.inputs,
                    *([_style_anchor_input(style)] if style is not None else []),
                    InputProvenance(
                        ref=f"provider-output:tileset-material-{role}",
                        sha256=source_hash,
                        source="content",
                        bytes=len(generated.data),
                        media_type=generated.media_type,
                    ),
                ],
                params={
                    **upstream.params,
                    "metadata": metadata,
                    "postprocess": [normalization.as_dict()],
                    "upstream_provenance": embedded_upstream,
                },
                validation={
                    **upstream.validation,
                    **validation,
                    **(
                        {"tileset_material_raw_canonicalization": canonicalization}
                        if isinstance(
                            canonicalization.get("cap_fill_lightness_recovery"),
                            Mapping,
                        )
                        else {}
                    ),
                    "exact_contract_dimensions": True,
                    "output_width": _TILESET_MATERIAL_SWATCH_SIZE,
                    "output_height": _TILESET_MATERIAL_SWATCH_SIZE,
                    "output_sha256": sha256_hex(normalized),
                },
                component=_RECIPE_COMPONENT,
                tool=SoftwareIdentity(
                    name=str(normalization.tool["name"]),
                    version=str(normalization.tool["version"]),
                ),
                attempts=upstream.attempts,
                response={
                    **(upstream.response or {}),
                    "source_artifact_sha256": source_hash,
                    "upstream_provenance": "inline",
                },
            )
            canonical_provenance = ProvenanceInput(
                provider="local",
                model=TILESET_MATERIAL_SYNTHESIS_VERSION,
                prompt=plan.prompts[role],
                refs=[
                    raw_path.name,
                    *[cast(str, binding["path"]) for binding in reference_bindings],
                ],
                inputs=[
                    InputProvenance(
                        ref=raw_path.name,
                        sha256=sha256_hex(normalized),
                        source="content",
                        bytes=len(normalized),
                        media_type="image/png",
                    ),
                    *([_style_anchor_input(style)] if style is not None else []),
                    *[
                        _input_from_binding(binding, media_type="image/png")
                        for binding in reference_bindings
                    ],
                ],
                params={
                    "metadata": metadata,
                    "tileset_material_canonicalization": canonicalization,
                },
                validation={
                    **validation,
                    "output_width": _TILESET_MATERIAL_SWATCH_SIZE,
                    "output_height": _TILESET_MATERIAL_SWATCH_SIZE,
                    "output_sha256": sha256_hex(canonical),
                    "tileset_material_canonicalization": canonicalization,
                },
                component=_RECIPE_COMPONENT,
                tool=SoftwareIdentity(
                    name="tileset-material-canonicalizer",
                    version=TILESET_MATERIAL_SYNTHESIS_VERSION,
                ),
                attempts=1,
                response={"dependency_role": role},
            )
            sidecars = await write_artifact_bundle_with_provenance_async(
                (
                    ArtifactBundleEntry(
                        path=raw_path,
                        artifact=BinaryArtifact(data=normalized, media_type="image/png"),
                        provenance=raw_provenance,
                    ),
                    ArtifactBundleEntry(
                        path=canonical_path,
                        artifact=BinaryArtifact(data=canonical, media_type="image/png"),
                        provenance=canonical_provenance,
                    ),
                )
            )
            record = await _tileset_material_component_record(
                role=role,
                raw_path=raw_path,
                canonical_path=canonical_path,
                raw_sidecar=sidecars[0],
                canonical_sidecar=sidecars[1],
                component_contract=component_contract,
                canonicalization=canonicalization,
                validation=validation,
            )
            return record, canonical, True
        finally:
            await asyncio.to_thread(provider_path.unlink, missing_ok=True)
            await asyncio.to_thread(Path(f"{provider_path}.meta.json").unlink, missing_ok=True)

    async def _derive_transparency(
        self, context: StageContext, spec: _ImageSpec, raw_path: Path
    ) -> Path:
        compiled = await _read_compiled_theme(context)
        style = await _read_style_anchor(context)
        character_profile = (
            await _read_character_profile(context) if _is_player_asset_stage(spec.stage) else None
        )
        grid_contract = _spec_grid_contract(spec)
        raw = await asyncio.to_thread(raw_path.read_bytes)
        raw_record = await _read_provenance(Path(f"{raw_path}.meta.json"))
        embedded_raw = _embedded_provenance(raw_record)
        mode = context.config.transparency_mode
        isolated_view_contract = (
            _isolated_view_contract_from_spec(spec) if spec.isolated_view else None
        )
        removal_record: ArtifactProvenance | None = None
        embedded_removal: dict[str, Any] | None = None
        removal_mask_used = False
        geometry_validation: dict[str, object] = {}
        if str(mode) == "chroma":
            output, _alpha = apply_chroma_transparency(raw)
            processor = "chroma-key"
            if spec.isolated_view:
                per_cell = _per_cell_contract_from_spec(spec)
                if per_cell is None and isolated_view_contract is None:
                    geometry_validation.update(validate_isolated_view_alpha(output))
            if grid_contract is not None:
                output, geometry_validation = normalize_canonical_grid(output, grid_contract)
        else:
            if self._background is None:
                raise RuntimeError("ai transparency requires the background-removal component")
            provider_path = spec.output.parent / (
                f".{spec.output.name}.removed-{uuid.uuid4().hex}.png"
            )

            def validate_removal(artifact: BinaryArtifact, _mask: object) -> dict[str, object]:
                validated_output, validated_alpha = compose_source_with_alpha(
                    raw,
                    removed_data=artifact.data,
                )
                transparent_pixels = validated_alpha.transparent_pixels
                nontransparent_pixels = validated_alpha.nontransparent_pixels
                facts = inspect_image(validated_output, expected_media_type="image/png")
                with Image.open(BytesIO(validated_output)) as validated_image:
                    alpha_extrema = validated_image.getchannel("A").getextrema()
                if alpha_extrema is None or alpha_extrema[0] == alpha_extrema[1]:
                    raise ValueError("transparency output alpha must not be uniform")
                if (facts.width, facts.height) != (spec.width, spec.height):
                    raise ValueError("background removal output dimensions changed")
                grid_facts: dict[str, object] = {}
                if spec.isolated_view:
                    per_cell = _per_cell_contract_from_spec(spec)
                    if per_cell is None:
                        grid_facts.update(validate_isolated_view_alpha(validated_output))
                    else:
                        cleaned_output, cleanup = canonicalize_isolated_view_alpha(validated_output)
                        isolated = validate_recoverable_isolated_view_alpha(cleaned_output)
                        grid_facts.update(isolated)
                        grid_facts.update(
                            _validate_recoverable_per_cell_scale(
                                isolated,
                                per_cell,
                                bbox_key="isolated_view_alpha_bbox",
                                height=spec.height,
                            )
                        )
                        grid_facts.update(
                            {
                                "per_cell_alpha_cleanup": cleanup,
                                "per_cell_fit_input_sha256": sha256_hex(validated_output),
                                "per_cell_fit_input_bytes": len(validated_output),
                            }
                        )
                elif grid_contract is not None:
                    _normalized, grid_facts = normalize_canonical_grid(
                        validated_output, grid_contract
                    )
                return {
                    "alpha_nontrivial": True,
                    "transparent_pixels": transparent_pixels,
                    "nontransparent_pixels": nontransparent_pixels,
                    "dimensions_preserved": True,
                    "output_width": facts.width,
                    "output_height": facts.height,
                    **grid_facts,
                }

            try:
                removed = await self._background.remove(
                    BackgroundRemovalRequest(
                        image_url=_data_url(raw),
                        artifact_path=provider_path,
                        output_mask=False,
                        metadata={
                            "stage": spec.stage,
                            **(
                                {"theme_compilation": compiled.identity}
                                if compiled is not None
                                else {}
                            ),
                            **({"style_anchor": style.identity} if style is not None else {}),
                            **(
                                {"character_profile": character_profile.identity}
                                if character_profile is not None
                                else {}
                            ),
                        },
                        timeout_seconds=context.config.capability_timeout_s,
                        cancellation=context.cancellation,
                        validate=validate_removal,
                    )
                )
                output, _alpha = compose_source_with_alpha(
                    raw,
                    removed_data=removed.data,
                )
                if grid_contract is not None:
                    output, geometry_validation = normalize_canonical_grid(output, grid_contract)
                removal_record = await _read_provenance(Path(removed.provenance_path))
                embedded_removal = _embedded_provenance(removal_record)
                _assert_temp_path_absent(embedded_removal, provider_path)
            finally:
                await asyncio.to_thread(provider_path.unlink, missing_ok=True)
                await asyncio.to_thread(Path(f"{provider_path}.meta.json").unlink, missing_ok=True)
            processor = "ai-background-removal"
        per_cell_fit: dict[str, object] | None = None
        per_cell_cleanup: dict[str, object] | None = None
        isolated_view_fit: dict[str, object] | None = None
        isolated_view_cleanup: dict[str, object] | None = None
        per_cell_contract = _per_cell_contract_from_spec(spec) if spec.isolated_view else None
        if per_cell_contract is not None:
            output, per_cell_validation, per_cell_fit, per_cell_cleanup = _normalize_per_cell_alpha(
                output,
                per_cell_contract,
            )
            if per_cell_fit is not None and embedded_removal is not None:
                per_cell_fit = _bind_per_cell_fit_to_removal(
                    per_cell_fit,
                    embedded_removal,
                    raw=raw,
                )
                per_cell_validation["per_cell_subject_fit"] = per_cell_fit
            geometry_validation.update(per_cell_validation)
            processor = f"{processor}+{ISOLATED_ALPHA_CLEANUP_VERSION}"
            if per_cell_fit is not None:
                processor = f"{processor}+{ISOLATED_SUBJECT_FIT_VERSION}"
        if isolated_view_contract is not None and str(mode) == str(TransparencyMode.CHROMA):
            (
                output,
                isolated_view_validation,
                isolated_view_fit,
                isolated_view_cleanup,
            ) = _normalize_isolated_fallback_alpha(output, isolated_view_contract)
            geometry_validation.update(isolated_view_validation)
            processor = f"{processor}+{ISOLATED_ALPHA_CLEANUP_VERSION}"
            if isolated_view_fit is not None:
                processor = f"{processor}+{ISOLATED_SUBJECT_FIT_VERSION}"
        if grid_contract is not None:
            processor = (
                "tileset-topology-mask"
                if grid_contract.topology == "tileset"
                else f"{processor}+grid-cell-normalization"
            )
        processor_version = (
            GRID_NORMALIZATION_VERSION
            if grid_contract is not None
            else ISOLATED_SUBJECT_FIT_VERSION
            if per_cell_fit is not None
            else ISOLATED_SUBJECT_FIT_VERSION
            if isolated_view_fit is not None
            else ISOLATED_ALPHA_CLEANUP_VERSION
            if per_cell_cleanup is not None or isolated_view_cleanup is not None
            else "1"
        )
        grid_normalization = geometry_validation.get("grid_normalization")
        transparent_pixels, nontransparent_pixels = _alpha_counts(output)
        raw_hash = sha256_hex(raw)
        if grid_contract is not None and isinstance(grid_normalization, dict):
            grid_normalization = _bind_grid_normalization_to_raw(
                grid_normalization,
                raw=raw,
            )
            geometry_validation = {
                **geometry_validation,
                "grid_normalization": grid_normalization,
            }
        output_hash = sha256_hex(output)
        provenance_provider = removal_record.provider if removal_record is not None else "local"
        provenance_model = removal_record.model if removal_record is not None else processor
        provenance_prompt = (
            removal_record.prompt
            if removal_record is not None
            else f"derive canonical transparency for {spec.stage}"
        )
        attempts = removal_record.attempts if removal_record is not None else 1
        removal_payload = (
            {
                "provider": removal_record.provider,
                "model": removal_record.model,
                "attempts": removal_record.attempts,
                "mask_used": removal_mask_used,
                "provenance": embedded_removal,
            }
            if removal_record is not None and embedded_removal is not None
            else None
        )
        return await write_artifact_with_provenance_async(
            spec.output,
            BinaryArtifact(data=output, media_type="image/png"),
            ProvenanceInput(
                provider=provenance_provider,
                model=provenance_model,
                prompt=provenance_prompt,
                refs=[raw_path.name],
                inputs=[
                    InputProvenance(
                        ref=raw_path.name,
                        sha256=raw_hash,
                        source="content",
                        bytes=len(raw),
                        media_type="image/png",
                    ),
                    *([_style_anchor_input(style)] if style is not None else []),
                    *(
                        [_character_profile_input(character_profile)]
                        if character_profile is not None
                        else []
                    ),
                ],
                params={
                    "transparency": {
                        "mode": str(mode),
                        "retained_raw_path": raw_path.name,
                        "raw_sha256": raw_hash,
                        "output_sha256": output_hash,
                        "processor": {"kind": processor, "version": processor_version},
                        # The matte algorithm is part of this artifact's lineage: without it a
                        # canonical output keyed by an earlier matte stays cache-valid forever
                        # and an improved matte never reaches the artifact.
                        **(
                            {"matte_version": CHROMA_MATTE_VERSION} if str(mode) == "chroma" else {}
                        ),
                        "source_provenance": embedded_raw,
                        **(
                            {"grid_normalization": grid_normalization}
                            if isinstance(grid_normalization, dict)
                            else {}
                        ),
                        **(
                            {"per_cell_alpha_cleanup": per_cell_cleanup}
                            if per_cell_cleanup is not None
                            else {}
                        ),
                        **(
                            {"per_cell_subject_fit": per_cell_fit}
                            if per_cell_fit is not None
                            else {}
                        ),
                        **(
                            {"isolated_view_alpha_cleanup": isolated_view_cleanup}
                            if isolated_view_cleanup is not None
                            else {}
                        ),
                        **(
                            {"isolated_view_subject_fit": isolated_view_fit}
                            if isolated_view_fit is not None
                            else {}
                        ),
                        **(
                            {
                                "character_climb_background_removal": geometry_validation[
                                    "character_climb_background_removal"
                                ]
                            }
                            if "character_climb_background_removal" in geometry_validation
                            else {}
                        ),
                        **({"removal": removal_payload} if removal_payload is not None else {}),
                    },
                    "metadata": {
                        "stage": spec.stage,
                        **(spec.metadata or {}),
                        **(
                            {"grid_contract": grid_contract.as_dict(spec.width, spec.height)}
                            if grid_contract is not None
                            else {}
                        ),
                        **(
                            {"theme_compilation": compiled.identity} if compiled is not None else {}
                        ),
                        **({"style_anchor": style.identity} if style is not None else {}),
                        **(
                            {"character_profile": character_profile.identity}
                            if character_profile is not None
                            else {}
                        ),
                    },
                },
                validation={
                    "alpha_nontrivial": True,
                    "transparent_pixels": transparent_pixels,
                    "nontransparent_pixels": nontransparent_pixels,
                    "dimensions_preserved": True,
                    "output_width": spec.width,
                    "output_height": spec.height,
                    "output_sha256": output_hash,
                    **geometry_validation,
                },
                component=_RECIPE_COMPONENT,
                tool=SoftwareIdentity(name=processor, version=processor_version),
                attempts=attempts,
                response={
                    "source_provenance": "inline",
                    "transparency": {
                        "processor": processor,
                        **({"removal_provenance": "inline"} if removal_payload is not None else {}),
                    },
                },
            ),
        )


async def _read_world_spec(context: StageContext) -> WorldSpec:
    path = context.run_dir / f"world_spec_{context.tag}.json"
    raw = await asyncio.to_thread(path.read_text, encoding="utf-8")
    return WorldSpec.model_validate_json(raw)


async def _read_village_spec(context: StageContext) -> VillageSpec:
    """The run's village bible, in whichever roster shape the run generated.

    Which shape is decided by the request, not by sniffing the file. A run that binds a game
    wrote a directed roster and must read one back: falling back to the undirected model on a
    parse failure would silently drop every resident's `body_kind`, `stance` and `holding`, and
    the stages downstream would then draw four unposed strangers without anything reporting why.
    """

    path = context.run_dir / f"village_spec_{context.tag}.json"
    raw = await asyncio.to_thread(path.read_text, encoding="utf-8")
    if "game" not in context.input:
        return VillageSpec.model_validate_json(raw)
    return DirectedVillageSpec.model_validate_json(raw)


async def _read_directed_village_spec(context: StageContext) -> DirectedVillageSpec:
    """The directed roster, for the stages that cannot run without one."""

    spec = await _read_village_spec(context)
    if not isinstance(spec, DirectedVillageSpec):
        raise ValueError("a game-directed village stage requires a directed village roster")
    return spec


def _theme_plan_path(context: StageContext) -> Path:
    return context.run_dir / f"theme_plan_{context.tag}.json"


def _style_anchor_path(context: StageContext) -> Path:
    return context.run_dir / f"style_anchor_{context.tag}.json"


def _game_contract_path(context: StageContext) -> Path:
    return context.run_dir / f"game_{context.tag}.json"


def _required_game_library_root(context: StageContext) -> Path:
    root = context.config.game_library_root
    if root is None:
        raise ValueError("game-directed scrolling generation requires game_library_root")
    return root


def _resolved_game_identity(resolved: ResolvedGameContract) -> dict[str, object]:
    return {
        **game_identity(resolved),
        "artifact_ref": f"sha256:{resolved.canonical_sha256}",
        "artifact_sha256": resolved.canonical_sha256,
        "artifact_bytes": len(resolved.canonical_bytes),
    }


def _valid_game_contract_cache(
    path: Path,
    sidecar: dict[str, Any],
    resolved: ResolvedGameContract,
    identity: Mapping[str, object],
) -> bool:
    try:
        if path.read_bytes() != resolved.canonical_bytes:
            return False
        GameContract.model_validate_json(resolved.canonical_bytes)
    except (OSError, ValueError):
        return False
    params = sidecar.get("params")
    return (
        sidecar.get("provider") == "local"
        and sidecar.get("model") == GAME_RESOLUTION_VERSION
        and sidecar.get("refs") == [resolved.binding.ref]
        and isinstance(params, Mapping)
        and params.get("stage") == "game-resolve"
        and params.get("game_contract") == dict(identity)
    )


async def _read_game_contract(context: StageContext) -> _GameContractContext | None:
    """The run's game contract, re-resolved and re-validated against what `game-resolve` wrote.

    Re-resolved on every read rather than cached in memory, exactly as the character profile and
    the compiled theme are. The read is a local digest-checked file, and the alternative - holding
    a parsed contract on the executor - would make a stage's direction depend on which other
    stages had already run in the same process.
    """

    if "game" not in context.input:
        return None
    resolved = await asyncio.to_thread(
        resolve_game_contract_binding,
        context.input["game"],
        game_library_root=_required_game_library_root(context),
    )
    path = _game_contract_path(context)
    identity = _resolved_game_identity(resolved)
    if not valid_artifact_pair(
        path,
        validator=lambda artifact, sidecar: _valid_game_contract_cache(
            artifact, sidecar, resolved, identity
        ),
        force=False,
    ):
        raise ValueError("resolved game contract is missing, stale, or invalid")
    return _GameContractContext(
        resolved=resolved,
        identity=identity,
        artifact_bytes=len(resolved.canonical_bytes),
    )


def _character_profile_path(context: StageContext) -> Path:
    return context.run_dir / f"character_profile_{context.tag}.json"


def _resolved_character_profile_identity(
    resolved: ResolvedCharacterProfile,
) -> dict[str, object]:
    return {
        **resolved.identity(),
        "resolution_version": PROFILE_RESOLUTION_VERSION,
        "artifact_ref": f"sha256:{resolved.canonical_sha256}",
        "artifact_sha256": resolved.canonical_sha256,
        "artifact_bytes": len(resolved.canonical_bytes),
    }


def _valid_character_profile_cache(
    path: Path,
    sidecar: dict[str, Any],
    resolved: ResolvedCharacterProfile,
    identity: Mapping[str, object],
) -> bool:
    try:
        if path.read_bytes() != resolved.canonical_bytes:
            return False
        CharacterProfile.model_validate_json(resolved.canonical_bytes)
    except (OSError, ValueError):
        return False
    params = sidecar.get("params")
    validation = sidecar.get("validation")
    inputs = sidecar.get("inputs")
    expected_media_type = (
        "application/toml" if resolved.source_path.suffix.lower() == ".toml" else "application/json"
    )
    return (
        sidecar.get("provider") == "local"
        and sidecar.get("model") == PROFILE_RESOLUTION_VERSION
        and sidecar.get("refs") == [resolved.binding.ref]
        and isinstance(params, Mapping)
        and params.get("stage") == "profile-resolve"
        and params.get("character_profile") == dict(identity)
        and validation
        == {
            "source_digest_verified": True,
            "canonical_digest_verified": True,
            "portable_reference_verified": True,
            "rights_status": resolved.profile.rights.status,
        }
        and inputs
        == [
            {
                "ref": resolved.binding.ref,
                "sha256": resolved.source_sha256,
                "source": "content",
                "bytes": len(resolved.source_bytes),
                "media_type": expected_media_type,
            }
        ]
    )


async def _read_character_profile(context: StageContext) -> _CharacterProfileContext | None:
    if "character_profile" not in context.input:
        return None
    resolved = await asyncio.to_thread(
        resolve_character_profile_binding,
        context.input["character_profile"],
        character_library_root=_required_character_library_root(context),
    )
    path = _character_profile_path(context)
    identity = _resolved_character_profile_identity(resolved)
    if not valid_artifact_pair(
        path,
        validator=lambda artifact, sidecar: _valid_character_profile_cache(
            artifact, sidecar, resolved, identity
        ),
        force=False,
    ):
        raise ValueError("resolved character profile is missing, stale, or invalid")
    return _CharacterProfileContext(
        profile=resolved.profile,
        identity=identity,
        artifact_bytes=len(resolved.canonical_bytes),
    )


def _required_character_library_root(context: StageContext) -> Path:
    root = context.config.character_library_root
    if root is None:
        raise ValueError("profile-enabled scrolling generation requires character_library_root")
    return root


async def _read_compiled_theme(context: StageContext) -> _CompiledThemeContext | None:
    if "theme" not in context.input:
        return None
    path = _theme_plan_path(context)
    request = build_theme_plan_request(
        str(context.input["prompt"]),
        parse_theme_handles(context.input["theme"]),
        path,
        timeout_seconds=context.config.capability_timeout_s,
        cancellation=context.cancellation,
    )
    if not valid_artifact_pair(
        path,
        validator=lambda artifact, sidecar: _valid_theme_plan_cache(artifact, sidecar, request),
        force=False,
    ):
        raise ValueError("compiled theme plan is missing, stale, or invalid")
    raw = await asyncio.to_thread(path.read_bytes)
    plan = request.parse(json.loads(raw))
    artifact_sha256 = sha256_hex(raw)
    return _CompiledThemeContext(
        plan=plan,
        identity={
            "schema_version": THEME_SCHEMA_VERSION,
            "compiler_version": THEME_COMPILER_VERSION,
            "theme_digest": request.metadata["theme_digest"],
            "theme_skill_name": request.metadata["theme_skill_name"],
            "theme_skill_sha256": request.metadata["theme_skill_sha256"],
            "artifact_ref": f"sha256:{artifact_sha256}",
            "artifact_sha256": artifact_sha256,
            "artifact_bytes": len(raw),
        },
        artifact_bytes=len(raw),
    )


def _style_selection_brief(
    context: StageContext,
    compiled: _CompiledThemeContext | None,
) -> str:
    brief = f"Source creative brief:\n{str(context.input['prompt']).strip()}"
    if compiled is None:
        return brief
    compiled_prose = "\n".join(compiled.plan.model_dump(mode="json").values())
    assert_no_raw_theme_control_leak(compiled_prose)
    return (
        f"{brief}\n\nCompiled visible content direction (content only; do not infer or alter "
        f"content intensity):\n{compiled_prose}"
    )


async def _read_style_anchor(context: StageContext) -> _StyleAnchorContext | None:
    if "style_anchor" not in context.input:
        return None
    compiled = await _read_compiled_theme(context)
    path = _style_anchor_path(context)
    request = build_image_style_compiler_request(
        prompt=_style_selection_brief(context, compiled),
        artifact_path=path,
        asset_kinds=_SCROLLING_IMAGE_ASSET_KINDS,
        timeout_seconds=context.config.capability_timeout_s,
        cancellation=context.cancellation,
    )
    if not _valid_style_anchor_pair(
        path,
        validator=lambda artifact, sidecar: _valid_style_anchor_cache(artifact, sidecar, request),
    ):
        raise ValueError("canonical style anchor is missing, stale, or invalid")
    raw = await asyncio.to_thread(path.read_bytes)
    anchor = CanonicalStyleAnchor.model_validate_json(raw)
    artifact_sha256 = sha256_hex(raw)
    return _StyleAnchorContext(
        anchor=anchor,
        identity={
            "schema_version": anchor.schema_version,
            "kind": anchor.kind,
            "anchor_sha256": canonical_style_anchor_digest(anchor),
            "style_mode": anchor.style_mode,
            "compiler_version": anchor.compiler_version,
            "compiler_sha256": anchor.compiler_sha256,
            "resource_sha256": anchor.resource_sha256,
            "skill_sha256": anchor.skill_sha256,
            "vocabulary_sha256": anchor.vocabulary_sha256,
            "artifact_ref": f"sha256:{artifact_sha256}",
            "artifact_sha256": artifact_sha256,
            "artifact_bytes": len(raw),
        },
        artifact_bytes=len(raw),
    )


def _valid_style_anchor_cache(
    path: Path,
    sidecar: dict[str, Any],
    request: StructuredGenerationRequest[CanonicalStyleAnchor],
) -> bool:
    try:
        anchor = CanonicalStyleAnchor.model_validate_json(path.read_text(encoding="utf-8"))
        if (
            request.parse(
                {
                    "schema_version": 1,
                    "kind": "image_style_selection_v1",
                    "style_mode": anchor.style_mode,
                }
            )
            != anchor
        ):
            return False
    except (OSError, ValueError, TypeError):
        return False
    params = sidecar.get("params")
    if not isinstance(params, dict):
        return False
    expected_params: dict[str, object] = {
        "schema_name": request.schema.name,
        "schema": dict(request.schema.json_schema),
        "strict": request.schema.strict,
        "require_parameters": True,
    }
    if request.system:
        expected_params["system"] = request.system
        expected_params["system_sha256"] = sha256_hex(request.system)
    if request.temperature is not None:
        expected_params["temperature"] = request.temperature
    if request.max_tokens is not None:
        expected_params["max_tokens"] = request.max_tokens
    if request.metadata:
        expected_params["metadata"] = dict(request.metadata)
    expected_params["artifact_value"] = "caller-canonicalized"
    expected_params["validated"] = True
    return sidecar.get("prompt") == request.prompt and params == expected_params


def _valid_style_anchor_pair(
    path: Path,
    *,
    validator: Callable[[Path, dict[str, Any]], bool],
) -> bool:
    if os.environ.get("STAGE_GEN_FORCE") == "1":
        return False
    try:
        raw = path.read_bytes()
        sidecar = json.loads(Path(f"{path}.meta.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    artifact = sidecar.get("artifact") if isinstance(sidecar, dict) else None
    return (
        bool(raw)
        and sidecar.get("schema_version") == 2
        and isinstance(artifact, dict)
        and artifact.get("bytes") == len(raw)
        and artifact.get("sha256") == sha256_hex(raw)
        and validator(path, sidecar)
    )


def _valid_theme_plan_cache(
    path: Path,
    sidecar: dict[str, Any],
    request: StructuredGenerationRequest[CompiledThemePlan],
) -> bool:
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
        request.parse(decoded)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
    params = sidecar.get("params")
    if not isinstance(params, dict):
        return False
    expected_params: dict[str, object] = {
        "schema_name": request.schema.name,
        "schema": dict(request.schema.json_schema),
        "strict": request.schema.strict,
        "require_parameters": True,
    }
    if request.system:
        expected_params["system"] = request.system
        expected_params["system_sha256"] = sha256_hex(request.system)
    if request.temperature is not None:
        expected_params["temperature"] = request.temperature
    if request.max_tokens is not None:
        expected_params["max_tokens"] = request.max_tokens
    if request.seed is not None:
        expected_params["seed"] = request.seed
    if request.metadata:
        expected_params["metadata"] = dict(request.metadata)
    return sidecar.get("prompt") == request.prompt and params == expected_params


def _valid_world_spec_cache(
    path: Path,
    sidecar: dict[str, Any],
    identity: Mapping[str, object] | None,
) -> bool:
    try:
        spec = WorldSpec.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    params = sidecar.get("params")
    if not isinstance(params, Mapping):
        return False
    if (
        params.get("artifact_value") != "caller-canonicalized"
        or params.get("validated") is not True
        or not _valid_world_spec_normalization(spec, sidecar)
    ):
        return False
    metadata = params.get("metadata")
    if identity is None:
        return not isinstance(metadata, Mapping) or "theme_compilation" not in metadata
    return _theme_identity_matches(sidecar, identity)


def _valid_world_spec_normalization(spec: WorldSpec, sidecar: Mapping[str, Any]) -> bool:
    validation = sidecar.get("validation")
    if not isinstance(validation, Mapping):
        return False
    record = validation.get("world_spec_normalization")
    if not isinstance(record, Mapping) or validation.get("world_spec_final_validation") is not True:
        return False
    transparent = [layer for layer in spec.layers if not layer.opaque]
    if not transparent:
        return False
    highest_z = max(layer.z_index for layer in transparent)
    candidates = [layer for layer in transparent if layer.z_index == highest_z]
    if len(candidates) != 1:
        return False
    target = candidates[0]
    input_parallax = record.get("input_parallax")
    if (
        isinstance(input_parallax, bool)
        or not isinstance(input_parallax, int | float)
        or not math.isfinite(input_parallax)
        or not 0 <= input_parallax <= 2
    ):
        return False
    changed = input_parallax != NEAR_FOREGROUND_PARALLAX
    target_index = next(index for index, layer in enumerate(spec.layers) if layer.id == target.id)
    return (
        record.get("version") == WORLD_SPEC_NORMALIZATION_VERSION
        and record.get("target_layer_id") == target.id
        and record.get("target_z_index") == target.z_index
        and record.get("output_parallax") == NEAR_FOREGROUND_PARALLAX
        and record.get("changed") is changed
        and record.get("changed_fields")
        == ([f"layers[{target_index}].parallax"] if changed else [])
        and record.get("layer_ids") == [layer.id for layer in spec.layers]
        and record.get("unchanged_layer_ids")
        == [layer.id for index, layer in enumerate(spec.layers) if index != target_index]
        and record.get("layer_order_preserved") is True
        and record.get("unrelated_layers_unchanged") is True
    )


def _village_spec_roster_record(spec: VillageSpec) -> dict[str, object]:
    """Record the roster the accepted bible actually carries, for the cache to re-check later.

    Written into the sidecar's validation block by the structured service, and re-derived from
    the artifact on disk by `_valid_village_spec_cache`. That pairing is what makes the cache
    check content-bound rather than path-bound: a `village_spec_<tag>.json` that was replaced,
    truncated, or hand-edited no longer re-derives the roster its own sidecar recorded, and the
    village is designed afresh instead of nine image stages being generated from a bible nobody
    validated. Names and role labels are enough on their own - the schema already refuses a
    roster with duplicates in either - and body plans are included because they are what the
    turnaround prompts are built from, so a changed plan means changed artwork.
    """

    return {
        "village_schema_name": VILLAGE_SPEC_SCHEMA_NAME,
        "village_npc_names": [npc.name for npc in spec.npcs],
        "village_npc_role_labels": [npc.role_label for npc in spec.npcs],
        "village_npc_body_plans": [npc.body_plan for npc in spec.npcs],
        "village_fixture_names": [fixture.name for fixture in spec.fixtures],
        "village_final_validation": True,
    }


def _valid_village_spec_cache(
    path: Path,
    sidecar: dict[str, Any],
    identity: Mapping[str, object] | None,
    *,
    directed: bool = False,
) -> bool:
    """Whether a village bible on disk may be reused, in the shape `_valid_world_spec_cache` uses.

    Existence is never the test. `AGENTS.md` requires cache reuse to validate content and
    lineage, and the stakes here are higher than for one image: the bible is the single input
    four turnaround prompts, four strip prompts and one fixture sheet are all derived from, so a
    stale or mismatched one silently mis-designs the whole village rather than one asset.

    So the file must re-parse as the roster model the run wrote - which re-runs every cross-field
    rule, including
    the distinguishability rules a hand-edit would be most likely to break - its sidecar must
    record that the caller canonicalized and validated the value, the recorded roster must be
    the roster the file still parses to, and the compiled-theme identity must match the theme
    this run compiled. A theme change changes the art direction the residents were designed
    against, so it has to invalidate them.
    """

    model, schema_name = village_spec_shape(directed=directed)
    try:
        spec = model.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    params = sidecar.get("params")
    if not isinstance(params, Mapping):
        return False
    if (
        params.get("schema_name") != schema_name
        or params.get("artifact_value") != "caller-canonicalized"
        or params.get("validated") is not True
        or not _valid_village_spec_roster(spec, sidecar)
    ):
        return False
    metadata = params.get("metadata")
    if identity is None:
        return not isinstance(metadata, Mapping) or "theme_compilation" not in metadata
    return _theme_identity_matches(sidecar, identity)


def _valid_village_spec_roster(spec: VillageSpec, sidecar: Mapping[str, Any]) -> bool:
    validation = sidecar.get("validation")
    if not isinstance(validation, Mapping):
        return False
    return all(
        validation.get(key) == value for key, value in _village_spec_roster_record(spec).items()
    )


def _theme_identity_matches(sidecar: Mapping[str, Any], expected: Mapping[str, object]) -> bool:
    params = sidecar.get("params")
    metadata = params.get("metadata") if isinstance(params, Mapping) else None
    actual = metadata.get("theme_compilation") if isinstance(metadata, Mapping) else None
    return actual == dict(expected)


def _optional_theme_identity_matches(
    sidecar: Mapping[str, Any], expected: Mapping[str, object] | None
) -> bool:
    params = sidecar.get("params")
    metadata = params.get("metadata") if isinstance(params, Mapping) else None
    if expected is None:
        return not isinstance(metadata, Mapping) or "theme_compilation" not in metadata
    return _theme_identity_matches(sidecar, expected)


def _style_identity_matches(
    sidecar: Mapping[str, Any], expected: Mapping[str, object] | None
) -> bool:
    params = sidecar.get("params")
    metadata = params.get("metadata") if isinstance(params, Mapping) else None
    actual = metadata.get("style_anchor") if isinstance(metadata, Mapping) else None
    return actual == (dict(expected) if expected is not None else None)


def _character_profile_identity_matches(
    sidecar: Mapping[str, Any], expected: Mapping[str, object] | None
) -> bool:
    params = sidecar.get("params")
    metadata = params.get("metadata") if isinstance(params, Mapping) else None
    actual = metadata.get("character_profile") if isinstance(metadata, Mapping) else None
    return actual == (dict(expected) if expected is not None else None)


def _style_anchor_input(style: _StyleAnchorContext) -> InputProvenance:
    return InputProvenance(
        ref=str(style.identity["artifact_ref"]),
        sha256=str(style.identity["artifact_sha256"]),
        source="content",
        bytes=style.artifact_bytes,
        media_type="application/json",
    )


def _character_profile_input(profile: _CharacterProfileContext) -> InputProvenance:
    return InputProvenance(
        ref=str(profile.identity["artifact_ref"]),
        sha256=str(profile.identity["artifact_sha256"]),
        source="content",
        bytes=profile.artifact_bytes,
        media_type="application/json",
    )


def _holds_run_build(stage: str) -> bool:
    """Whether a sheet's drawn build is contracted by the run's requested head count.

    The player's own sheets and the village residents; not the mobs. A run's head count describes
    its cast, and a creature's build is a fact about the creature - holding a snail to two heads
    tall would be meaningless.

    Only sheets that publish a scale reference qualify, because the build is derived from that
    reference. The five master states are excluded here for the same reason they are excluded
    from `measures_scale_reference`: they are re-sliced before publication, so `post-split` owns
    their measurement.
    """

    if not measures_scale_reference(stage):
        return False
    return _is_player_asset_stage(stage) or (
        stage.startswith("village-npc-") and (stage.endswith("-idle") or stage.endswith("-still"))
    )


def _painted_frame_height(data: bytes, *, frame: int, cell_width: int) -> int | None:
    """Painted height of one frame, in source pixels, or None when the frame is empty.

    Measured against the same alpha threshold the cell extractor uses, so the height agrees with
    what the runtime will actually draw rather than with the canvas the frame was authored on.
    """

    with Image.open(BytesIO(data)) as image:
        alpha = image.convert("RGBA").getchannel("A")
        left = frame * cell_width
        box = alpha.crop((left, 0, left + cell_width, alpha.height))
        bounds = box.point(lambda value: 255 if value > _PAINTED_ALPHA_THRESHOLD else 0).getbbox()
    if bounds is None:
        return None
    return bounds[3] - bounds[1]


def _is_player_asset_stage(stage: str) -> bool:
    """Whether this stage draws the player, and so must carry the authored character profile.

    Village residents are not the player and must never reach this branch. They cannot: every
    village stage name begins `village-`, so neither the equality nor the `character-` prefix
    can capture one. The predicate is left exactly as it was rather than gaining a village
    exclusion, because an exclusion would imply a village stage could otherwise match.
    """

    return stage == "character-concept" or stage.startswith("character-")


def _asset_kind_for_image_stage(stage: str) -> ImageAssetKind:
    # The concept branch has to lead: `village-npc-concept-0` is a three-view turnaround and
    # would otherwise be captured by the `village-npc-` sprite branch below, exactly as
    # `mob-concept-0` would be captured by `mob-`. `village-npc-` also covers the isolated-view
    # sub-stages a rescued turnaround generates, which are single sprites and not concept art.
    if stage == "concept" or stage.startswith(
        ("character-concept", "mob-concept-", "village-npc-concept-")
    ):
        return "concept_art"
    if stage.startswith("layer-"):
        return "environment_background"
    if stage.startswith(("character-", "mob-", "village-npc-")):
        return "character_sprite"
    if stage.startswith("tileset-material-"):
        return "tileable_texture"
    if stage in {"tileset", "items", "ladder", "village-fixtures"} or stage.startswith(
        "obstacles-"
    ):
        return "asset_sheet"
    if stage == "inventory":
        return "interface_art"
    if stage == "portal":
        return "effect_sheet"
    return "illustration"


def _append_compiled_directive(prompt: str, directive: str, hard_exclusions: str) -> str:
    return (
        f"{prompt.strip()}\n\nVisible content direction:\n{directive}\n\n"
        f"Binding visual constraints:\n{hard_exclusions}"
    )


def _append_binding_visual_constraints(prompt: str, constraints: str) -> str:
    return f"{prompt.strip()}\n\nBinding visual constraints:\n{constraints}"


def _themed_concept_prompt(concept: str) -> str:
    return (
        f"{concept.strip()}\n\nRecipe composition:\n"
        "Use a wide cinematic landscape canvas for a 2D scrolling-game scene, with clear "
        "distant, middle, and foreground depth. Fill the complete canvas opaquely."
    )


def _directive_for_image_stage(plan: CompiledThemePlan, stage: str) -> str:
    # The village stages take the same art direction as the hunting stages they are modelled on,
    # rather than falling through to the environment directive. A fixture sheet is a sheet of
    # props and a resident is a character; giving either the environment direction would brief
    # the image model on the run's landscape while it draws a market stall or a shopkeeper.
    if stage == "concept":
        return plan.concept
    if stage in {"items", "inventory", "ladder", "village-fixtures"} or stage.startswith(
        "obstacles-"
    ):
        return plan.items
    if stage == "portal":
        return plan.portals
    if stage.startswith(("character-", "mob-", "village-npc-")):
        return plan.characters
    return plan.environment


def _tileset_material_theme_directive(compiled: _CompiledThemeContext | None) -> str:
    if compiled is None:
        return ""
    return _append_binding_visual_constraints(
        _directive_for_image_stage(compiled.plan, "tileset"),
        compiled.plan.hard_exclusions,
    )


def _assert_no_raw_theme_controls_in_metadata(value: object) -> None:
    if isinstance(value, str):
        assert_no_raw_theme_control_leak(value)
    elif isinstance(value, Mapping):
        for key, nested in value.items():
            if isinstance(key, str):
                if key == "theme_compilation":
                    continue
                assert_no_raw_theme_control_leak(key)
                assert_no_raw_theme_control_leak(
                    f"{key}={json.dumps(nested, ensure_ascii=False, default=str)}"
                )
            _assert_no_raw_theme_controls_in_metadata(nested)
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        for nested in value:
            _assert_no_raw_theme_controls_in_metadata(nested)


def _template_root() -> Path:
    return image_template_dir()


async def _image_reference(path: Path, *, portable: bool = False) -> ImageReference:
    data = await asyncio.to_thread(path.read_bytes)
    return ImageReference(
        url=_data_url(data),
        provenance_ref=path.name if portable else str(path),
    )


async def _structured_reference(path: Path) -> StructuredReference:
    data = await asyncio.to_thread(path.read_bytes)
    return StructuredReference(url=_data_url(data), provenance_ref=str(path))


def _character_heads_tall(context: StageContext) -> float | None:
    """The build requested by the flat opt-in, or None when the run did not use it."""

    if "character_heads_tall" not in context.input:
        return None
    return parse_character_heads_tall(context.input["character_heads_tall"])


async def _actor_heads_tall(context: StageContext, *, body_kind: str | None = None) -> float | None:
    """The build any actor in this run is drawn to.

    A game contract, when one is bound, is the whole answer: it holds one table keyed on body
    kind, and the player and every resident resolve from it. That is the fix for the defect the
    flat `character_heads_tall` opt-in could not express - it named the *player's* build, so a
    village generated beside it had nothing to consult and the head-matching runtime rendered
    whatever the image model chose at whatever size that implied.

    `character_heads_tall` remains the answer for a run without a game, and the two never
    disagree because `parse_scrolling_preview_input` refuses a request carrying both.
    """

    game = await _read_game_contract(context)
    if game is None:
        return _character_heads_tall(context)
    return game.contract.heads_for(body_kind or game.contract.cast.player.body_kind)


def _spec_requested_heads(spec: _ImageSpec) -> float | None:
    """The build this exact sheet was drawn to, when its fan-out resolved one."""

    requested = (spec.metadata or {}).get("requested_heads_tall")
    if isinstance(requested, bool) or not isinstance(requested, (int, float)):
        return None
    return float(requested)


def _review_subject(stage: str) -> str:
    """Name the subject for the reviewer, without asserting anything about its design.

    The reviewer needs to know it is looking at one creature rather than a scene. It must not be
    told which way to expect it to face, or the answer stops being evidence.

    Village residents take the default and get no branch of their own. They are townsfolk, so
    "a game character" is the accurate description, and the `mob-` prefix cannot reach them.
    """

    if stage.startswith("mob-"):
        return "a creature"
    return "a game character"


def _actor_facing_review_path(spec: _ImageSpec) -> Path:
    return spec.output.with_name(f"{spec.output.stem}.facing-review.json")


def _actor_scale_reference_path(spec: _ImageSpec) -> Path:
    return spec.output.with_name(f"{spec.output.stem}.scale-reference.json")


async def _cached_actor_scale_reference(
    reference_path: Path, measured_sha256: str
) -> dict[str, object] | None:
    """Reuse a measurement already taken on these exact bytes, or None to measure afresh.

    Bound to the artifact digest rather than the path, so regenerated art never inherits the
    reference taken on the art it replaced. Every failure to read the pair fails closed.
    """

    sidecar = reference_path.with_name(f"{reference_path.name}.meta.json")
    try:
        recorded = json.loads(await asyncio.to_thread(sidecar.read_text, encoding="utf-8"))
        payload = json.loads(await asyncio.to_thread(reference_path.read_text, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    params = recorded.get("params") if isinstance(recorded, Mapping) else None
    metadata = params.get("metadata") if isinstance(params, Mapping) else None
    if not isinstance(metadata, Mapping) or metadata.get("measured_sha256") != measured_sha256:
        return None
    return payload if isinstance(payload, dict) else None


async def _cached_actor_facing_verdict(
    review_path: Path, reviewed_sha256: str
) -> ActorFacingVerdict | None:
    """Reuse a verdict already taken on these exact bytes, or None to review afresh.

    A resumed run reuses most of its artwork from cache, and without this it would pay a
    provider call per actor to re-ask a question whose answer cannot have changed. The verdict
    is keyed to the artifact digest rather than to the path, so regenerated art never inherits
    the reading taken on the art it replaced - the digest moves and the check falls through.

    Every failure to read the pair fails closed, back to a fresh review.
    """

    sidecar = review_path.with_name(f"{review_path.name}.meta.json")
    try:
        recorded = json.loads(await asyncio.to_thread(sidecar.read_text, encoding="utf-8"))
        payload = json.loads(await asyncio.to_thread(review_path.read_text, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    params = recorded.get("params") if isinstance(recorded, Mapping) else None
    metadata = params.get("metadata") if isinstance(params, Mapping) else None
    if not isinstance(metadata, Mapping):
        return None
    if metadata.get("reviewed_sha256") != reviewed_sha256:
        return None
    try:
        return parse_actor_facing(payload)
    except ValueError:
        return None


def _data_url(data: bytes) -> str:
    return f"data:image/png;base64,{base64.b64encode(data).decode('ascii')}"


def _validate_provider_asset(
    data: bytes, *, spec: _ImageSpec, contract: GridContract | None
) -> dict[str, object]:
    facts = inspect_image(data, expected_media_type="image/png")
    validation: dict[str, object] = {
        "stage": spec.stage,
        "source_width": facts.width,
        "source_height": facts.height,
    }
    if spec.isolated_view:
        per_cell = _per_cell_contract_from_spec(spec)
        isolated = validate_isolated_view_source(
            data,
            width=spec.width,
            height=spec.height,
            allow_recoverable_inset=per_cell is not None,
        )
        validation.update(isolated)
        if per_cell is not None:
            validation.update(
                _validate_recoverable_per_cell_scale(
                    isolated,
                    per_cell,
                    bbox_key="isolated_view_bbox",
                    height=spec.height,
                )
            )
    elif contract is not None:
        validation.update(
            validate_generated_source(
                data,
                width=spec.width,
                height=spec.height,
                contract=contract,
            )
        )
    return validation


def _valid_raw_asset_cache(
    path: Path,
    sidecar: dict[str, Any],
    *,
    spec: _ImageSpec,
    contract: GridContract | None,
) -> bool:
    if not _exact_image(path, spec.width, spec.height, alpha=False):
        return False
    if not _asset_metadata_matches(
        sidecar,
        expected=spec.metadata,
        contract=contract,
        width=spec.width,
        height=spec.height,
    ):
        return False
    # Reuse is only sound while the request that produced this artifact still stands. Sidecars
    # written before this record carry no digest and correctly fail closed.
    params = sidecar.get("params")
    recorded_metadata = params.get("metadata") if isinstance(params, dict) else None
    recorded_prompt = (
        recorded_metadata.get("spec_prompt_sha256")
        if isinstance(recorded_metadata, Mapping)
        else None
    )
    if recorded_prompt != sha256_hex(spec.prompt.encode()):
        return False
    if spec.isolated_view:
        try:
            per_cell = _per_cell_contract_from_spec(spec)
            isolated = validate_isolated_view_source(
                path.read_bytes(),
                width=spec.width,
                height=spec.height,
                allow_recoverable_inset=per_cell is not None,
            )
            if per_cell is not None:
                _validate_recoverable_per_cell_scale(
                    isolated,
                    per_cell,
                    bbox_key="isolated_view_bbox",
                    height=spec.height,
                )
        except (OSError, ValueError):
            return False
        return True
    if contract is None:
        return True
    try:
        validate_generated_source(
            path.read_bytes(),
            width=spec.width,
            height=spec.height,
            contract=contract,
        )
    except (OSError, ValueError):
        return False
    if _tileset_material_fallback_from_sidecar(sidecar) is not None:
        # The async entrypoint validates the complete swatch DAG before it can
        # return this cache. Never downgrade a synthesis cache to the generic
        # raw -> transparency derivation path.
        return False
    per_cell = _per_cell_record_from_raw_sidecar(sidecar)
    if per_cell is not None:
        recorded_theme = per_cell.get("theme_identity")
        return _valid_per_cell_fallback_cache(
            composite=spec.output,
            retained_raw=path,
            fallback=per_cell,
            contract=contract,
            width=spec.width,
            height=spec.height,
            expected_metadata=spec.metadata,
            theme_identity=(
                cast(Mapping[str, object], recorded_theme)
                if isinstance(recorded_theme, Mapping)
                else None
            ),
        )
    fallback = _fallback_record_from_raw_sidecar(sidecar)
    return fallback is None or _valid_isolated_view_fallback_cache(
        composite=spec.output,
        retained_raw=path,
        fallback=fallback,
        contract=contract,
        width=spec.width,
        height=spec.height,
        expected_metadata=spec.metadata,
    )


def _asset_metadata_matches(
    sidecar: Mapping[str, Any],
    *,
    expected: Mapping[str, object] | None,
    contract: GridContract | None,
    width: int,
    height: int,
) -> bool:
    if expected is None and contract is None:
        return True
    params = sidecar.get("params")
    metadata = params.get("metadata") if isinstance(params, Mapping) else None
    if not isinstance(metadata, Mapping):
        return False
    if expected is not None and any(metadata.get(key) != value for key, value in expected.items()):
        return False
    return contract is None or metadata.get("grid_contract") == contract.as_dict(width, height)


def _uses_prop_sheet_adapter(stage: str) -> bool:
    """Whether a 2-row x 4-column sheet stage runs through the bottom-anchored prop adapter.

    The village fixture sheet is an obstacle sheet whose props are stalls and wells: the same
    grid, the same layout prior, the same cell-0 style-and-scale anchor, the same bottom
    contact. It reuses `obstacles-v1` rather than declaring a second adapter so a fixture sheet
    cannot drift away from the obstacle sheets it is validated by - the per-cell fallback
    records, their cache validators and the composite geometry checks all key off the adapter
    name, and a second name would have to be admitted to every one of them separately.

    Kept as one predicate rather than repeating the test at each site because the sites are
    spread across generation, resume and two cache validators, and one of them silently missing
    the village stage would under-validate a cached fallback rather than fail loudly.
    """

    return stage.startswith("obstacles-") or stage == "village-fixtures"


def _per_cell_parent_contract(
    *,
    stage: str,
    prompt: str,
    source_specs: Sequence[Mapping[str, object]],
    reference_bindings: Sequence[Mapping[str, object]],
    identity_policy: str,
    sheet_theme: str | None = None,
) -> dict[str, object]:
    if stage == "items":
        adapter = "items-v1"
        anchor = "center"
        role_prefix = "item"
    elif _uses_prop_sheet_adapter(stage):
        adapter = "obstacles-v1"
        anchor = "bottom"
        role_prefix = "prop"
    else:
        raise ValueError(f"per-cell generation is not supported for {stage}")
    if len(source_specs) != 8:
        raise ValueError("per-cell parent contracts require exactly eight source specs")
    payload: dict[str, object] = {
        "version": _PER_CELL_GENERATION_VERSION,
        "adapter": adapter,
        "parent_stage": stage,
        "parent_prompt_sha256": sha256_hex(prompt.encode()),
        "layout": {
            "rows": 2,
            "columns": 4,
            "gutter": 8,
            "anchor": anchor,
        },
        "role_order": [f"{role_prefix}-{index}" for index in range(8)],
        "source_specs": [dict(source) for source in source_specs],
        "reference_bindings": [dict(binding) for binding in reference_bindings],
        "identity_policy": identity_policy,
        "sheet_theme": sheet_theme,
        "eligible_sheet_failure_codes": sorted(_PER_CELL_LAYOUT_CODES),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {**payload, "sha256": sha256_hex(encoded)}


async def _mob_strip_metadata(concept: Path) -> dict[str, object]:
    """Per-creature strip metadata, empty when its turnaround cannot be measured."""

    try:
        data = await asyncio.to_thread(concept.read_bytes)
        return {"maximum_frame_symmetry": side_view_symmetry_ceiling(data)}
    except (OSError, ValueError):
        return {}


def _spec_grid_contract(spec: _ImageSpec) -> GridContract | None:
    """The stage's contract, carrying any per-subject bound the spec measured for it.

    `contract_for_stage` knows the stage but not the creature. A head-on ceiling has to come
    from the subject's own turnaround - a dome's true side view is near-perfectly symmetric -
    so the measurement is taken when the spec is built and applied here, where every path that
    validates or re-validates the asset picks it up.
    """

    contract = contract_for_stage(spec.stage)
    if contract is None:
        return None
    ceiling = (spec.metadata or {}).get("maximum_frame_symmetry")
    if isinstance(ceiling, (int, float)) and not isinstance(ceiling, bool):
        return replace(contract, maximum_frame_symmetry=float(ceiling))
    return contract


def _eligible_per_cell_stage(spec: _ImageSpec) -> bool:
    contract = (spec.metadata or {}).get("per_cell_generation_contract")
    return (
        spec.transparent
        and (spec.stage == "items" or _uses_prop_sheet_adapter(spec.stage))
        and isinstance(contract, Mapping)
        and contract.get("version") == _PER_CELL_GENERATION_VERSION
        and contract.get("parent_stage") == spec.stage
        and contract.get("parent_prompt_sha256") == sha256_hex(spec.prompt.encode())
        and _valid_fallback_record_digest(contract)
    )


def _valid_per_cell_failure_history(value: object) -> bool:
    if not isinstance(value, list) or len(value) != 6:
        return False
    for expected_attempt, failure in enumerate(value, start=1):
        if not isinstance(failure, Mapping):
            return False
        code = failure.get("code")
        if (
            failure.get("attempt") != expected_attempt
            or code not in _PER_CELL_LAYOUT_CODES
            or not isinstance(failure.get("message"), str)
            or not str(failure["message"]).startswith(f"{code}:")
        ):
            return False
        has_coordinates = "row" in failure or "column" in failure
        if code not in _CELL_SCOPED_LAYOUT_CODES and has_coordinates:
            return False
        # An empty cell always names one; a painted frame names one only from the per-cell ring
        # check, never from the whole-sheet gutter check.
        if code == GRID_EMPTY_CELL_ERROR_CODE or (
            code == GRID_PAINTED_CELL_FRAME_ERROR_CODE and has_coordinates
        ):
            row = failure.get("row")
            column = failure.get("column")
            if (
                isinstance(row, bool)
                or not isinstance(row, int)
                or isinstance(column, bool)
                or not isinstance(column, int)
                or not 0 <= row < 2
                or not 0 <= column < 4
            ):
                return False
    return True


def _eligible_per_cell_fallback(
    spec: _ImageSpec,
    contract: GridContract | None,
    error: RetryExhaustedError,
    sheet_failures: object,
) -> bool:
    return (
        _eligible_per_cell_stage(spec)
        and contract is not None
        and contract.topology == "grid"
        and (contract.rows, contract.columns, contract.gutter) == (2, 4, 8)
        and error.attempts == 6
        and error.retries == 5
        and _valid_per_cell_failure_history(sheet_failures)
    )


async def _build_per_cell_adapter_plan(
    context: StageContext,
    spec: _ImageSpec,
) -> _PerCellAdapterPlan:
    recorded = (spec.metadata or {}).get("per_cell_generation_contract")
    if not isinstance(recorded, Mapping) or not _valid_fallback_record_digest(recorded):
        raise ValueError("per-cell parent contract is missing or invalid")
    bindings_value = recorded.get("reference_bindings")
    if not isinstance(bindings_value, list) or len(bindings_value) != len(spec.references):
        raise ValueError("per-cell parent reference bindings are incomplete")
    roles: list[str] = []
    for value in bindings_value:
        if not isinstance(value, Mapping) or not isinstance(value.get("role"), str):
            raise ValueError("per-cell parent reference role is invalid")
        roles.append(str(value["role"]))
    actual_bindings = await _per_cell_reference_bindings(spec.references, roles=roles)
    if actual_bindings != [dict(value) for value in bindings_value]:
        raise ValueError("per-cell parent reference bindings no longer match their artifacts")
    world_indexes = [
        index
        for index, binding in enumerate(actual_bindings)
        if binding.get("role") == "world-concept-style-reference"
    ]
    if len(world_indexes) != 1:
        raise ValueError("per-cell generation requires one world concept reference")
    world_concept = spec.references[world_indexes[0]]
    world = await _read_world_spec(context)
    if spec.stage == "items":
        source_specs = [item.model_dump(mode="json") for item in world.items]
        identity_policy = "independent-distinct-items"
        adapter = "items-v1"
        sheet_theme = None
        layout_prior = None
        scale_bands = ((0.34, 0.70),) * 8
        role_prefix = "item"
        subject_noun = "collectible"
    else:
        # The village fixture sheet shares this adapter, so it has to be resolved here too. Its
        # eight cells come from the village bible rather than the world bible; everything after
        # this - the layout prior, the scale bands, the cell-0 identity anchor - is identical,
        # which is the point of sharing the adapter at all.
        if spec.stage == "village-fixtures":
            village = await _read_village_spec(context)
            source_specs = [fixture.model_dump(mode="json") for fixture in village.fixtures]
            sheet_theme = village.fixtures_theme
            subject_noun = "village fixture"
        else:
            try:
                sheet_index = int(spec.stage.removeprefix("obstacles-"))
                sheet = world.obstacles[sheet_index]
            except (ValueError, IndexError) as error:
                raise ValueError(f"invalid obstacle sheet stage: {spec.stage}") from error
            source_specs = [prop.model_dump(mode="json") for prop in sheet.props]
            sheet_theme = sheet.sheet_theme
            subject_noun = "obstacle prop"
        identity_policy = "cell-0-scale-style-anchor"
        adapter = "obstacles-v1"
        prior_indexes = [
            index
            for index, binding in enumerate(actual_bindings)
            if binding.get("role") == "obstacle-layout-prior"
        ]
        if len(prior_indexes) != 1:
            raise ValueError("obstacle per-cell generation requires one layout prior")
        layout_prior = spec.references[prior_indexes[0]]
        scale_bands = (
            (0.34, 0.62),
            (0.45, 0.72),
            (0.38, 0.66),
            (0.50, 0.82),
            (0.30, 0.58),
            (0.44, 0.70),
            (0.52, 0.84),
            (0.40, 0.68),
        )
        role_prefix = "prop"
    expected = _per_cell_parent_contract(
        stage=spec.stage,
        prompt=spec.prompt,
        source_specs=source_specs,
        reference_bindings=actual_bindings,
        identity_policy=identity_policy,
        sheet_theme=sheet_theme,
    )
    if dict(recorded) != expected:
        raise ValueError("per-cell parent prompt, source, layout, or reference contract is stale")

    cells: list[_PerCellDefinition] = []
    for index, (source, scale) in enumerate(zip(source_specs, scale_bands, strict=True)):
        row, column = divmod(index, 4)
        name = str(source.get("name", ""))
        brief = str(source.get("brief", ""))
        if not name or not brief:
            raise ValueError(f"per-cell source {index} is incomplete")
        if adapter == "items-v1":
            kind = str(source.get("kind", ""))
            action = "stationary collectible pickup"
            silhouette = f"distinct {kind} silhouette for {name}"
            prompt = (
                f"Generate exactly one complete {subject_noun} for declared cell {index + 1} "
                f"(row {row + 1}, column {column + 1}): kind {kind}; name {name}; "
                f"description {brief}. Match the supplied world concept's visible style. "
                f"Keep one centered floating subject occupying {scale[0]:.0%} to "
                f"{scale[1]:.0%} of the canvas height, with generous clear padding and a "
                "uniform removable background. Preserve a distinctive readable silhouette. "
                "No ground, baseline, cast or contact shadow, text, label, border, panel, "
                "scenery, duplicate object, or cropped part."
            )
        else:
            action = "stationary environmental prop with flat ground contact"
            silhouette = f"distinct prop silhouette for {name}: {brief}"
            prompt = (
                f"Generate exactly one complete {subject_noun} for declared cell {index + 1} "
                f"(row {row + 1}, column {column + 1}) in the {sheet_theme} set: {name}; "
                f"description {brief}. Match the supplied world concept and use the cropped "
                "cell prior only for placement, scale, and flat bottom contact. Keep the prop "
                f"between {scale[0]:.0%} and {scale[1]:.0%} of the canvas height, centered "
                "horizontally and bottom-oriented with generous clear padding. When a cell-0 "
                "anchor is supplied, use it only for shared visual style and relative scale; "
                "do not copy its identity, object type, or silhouette. Use one distinct, "
                "complete prop on a uniform removable background. No ground plane, scenery, "
                "shadow, text, label, border, panel, connection, duplicate, or cropped part."
            )
        cells.append(
            _PerCellDefinition(
                index=index,
                row=row,
                column=column,
                role=f"{role_prefix}-{index}",
                prompt=prompt,
                source_spec=dict(source),
                action=action,
                silhouette=silhouette,
                minimum_height_fraction=scale[0],
                maximum_height_fraction=scale[1],
            )
        )
    return _PerCellAdapterPlan(
        adapter=adapter,
        parent_contract=expected,
        cells=tuple(cells),
        world_concept=world_concept,
        layout_prior=layout_prior,
        identity_policy=identity_policy,
    )


def _per_cell_output(output: Path, row: int, column: int) -> Path:
    return output.with_name(f".{output.stem}.cell-{row}-{column}.png")


def _per_cell_prior_output(output: Path, row: int, column: int) -> Path:
    return output.with_name(f".{output.stem}.cell-{row}-{column}.prior.png")


async def _per_cell_reference_bindings(
    paths: Sequence[Path],
    *,
    roles: Sequence[str],
) -> list[dict[str, object]]:
    if len(paths) != len(roles):
        raise ValueError("per-cell reference paths and roles must align")
    values: list[dict[str, object]] = []
    for path, role in zip(paths, roles, strict=True):
        data = await asyncio.to_thread(path.read_bytes)
        values.append(
            {
                "role": role,
                "path": path.name,
                "sha256": sha256_hex(data),
                "bytes": len(data),
            }
        )
    return values


async def _write_per_cell_prior(
    source: Path,
    *,
    output: Path,
    row: int,
    column: int,
    rows: int,
    columns: int,
) -> dict[str, object]:
    source_data = await asyncio.to_thread(source.read_bytes)
    with Image.open(BytesIO(source_data)) as opened:
        image = opened.convert("RGBA")
    if image.width % columns or image.height % rows:
        raise ValueError("per-cell layout prior dimensions do not divide into the declared grid")
    width = image.width // columns
    height = image.height // rows
    crop = image.crop((column * width, row * height, (column + 1) * width, (row + 1) * height))
    data = _image_png_bytes(crop)
    lineage: dict[str, object] = {
        "version": _PER_CELL_GENERATION_VERSION,
        "source_path": source.name,
        "source_sha256": sha256_hex(source_data),
        "source_bytes": len(source_data),
        "layout": {"rows": rows, "columns": columns},
        "cell": {"row": row, "column": column},
        "output_width": width,
        "output_height": height,
        "output_sha256": sha256_hex(data),
        "output_bytes": len(data),
    }
    cache_valid = valid_artifact_pair(
        output,
        validator=lambda path, meta: (
            _metadata_field(meta, "per_cell_layout_prior") == lineage
            and inspect_image(path.read_bytes(), expected_media_type="image/png").width == width
            and inspect_image(path.read_bytes(), expected_media_type="image/png").height == height
        ),
    )
    if not cache_valid:
        await write_artifact_with_provenance_async(
            output,
            BinaryArtifact(data=data, media_type="image/png"),
            ProvenanceInput(
                provider="local",
                model=_PER_CELL_GENERATION_VERSION,
                prompt=f"crop authoritative layout prior cell ({row},{column})",
                refs=[source.name],
                inputs=[
                    InputProvenance(
                        ref=source.name,
                        sha256=sha256_hex(source_data),
                        source="content",
                        bytes=len(source_data),
                        media_type="image/png",
                    )
                ],
                params={"metadata": {"per_cell_layout_prior": lineage}},
                validation={
                    "deterministic_crop": True,
                    "output_width": width,
                    "output_height": height,
                    "output_sha256": sha256_hex(data),
                },
                component=_RECIPE_COMPONENT,
                tool=SoftwareIdentity(
                    name="per-cell-layout-prior-crop",
                    version=_PER_CELL_GENERATION_VERSION,
                ),
                attempts=1,
            ),
        )
    sidecar = Path(f"{output}.meta.json")
    return {
        "path": output.name,
        "sha256": sha256_hex(data),
        "bytes": len(data),
        "provenance_path": sidecar.name,
        "provenance_sha256": sha256_hex(await asyncio.to_thread(sidecar.read_bytes)),
        "lineage": lineage,
    }


def _per_cell_component_contract(
    spec: _ImageSpec,
    *,
    plan: _PerCellAdapterPlan,
    cell: _PerCellDefinition,
    reference_bindings: Sequence[Mapping[str, object]],
    identity_anchor: Mapping[str, object] | None,
    prior: Mapping[str, object] | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "version": _PER_CELL_GENERATION_VERSION,
        "adapter": plan.adapter,
        "parent_stage": spec.stage,
        "parent_contract_sha256": plan.parent_contract["sha256"],
        "cell_index": cell.index,
        "row": cell.row,
        "column": cell.column,
        "semantic_role": cell.role,
        "source_spec": cell.source_spec,
        "action": cell.action,
        "silhouette": cell.silhouette,
        "prompt_sha256": sha256_hex(cell.prompt.encode()),
        "anchor": "bottom" if plan.adapter == "obstacles-v1" else "center",
        "scale_contract": {
            "minimum_height_fraction": cell.minimum_height_fraction,
            "maximum_height_fraction": cell.maximum_height_fraction,
        },
        "reference_bindings": [dict(binding) for binding in reference_bindings],
        "identity_anchor": dict(identity_anchor) if identity_anchor is not None else None,
        "layout_prior": dict(prior) if prior is not None else None,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {**payload, "sha256": sha256_hex(encoded)}


def _validate_per_cell_scale(
    validation: Mapping[str, object],
    contract: Mapping[str, object],
    *,
    bbox_key: str,
    height: int,
) -> dict[str, object]:
    minimum, maximum, fraction = _per_cell_scale_measurement(
        validation,
        contract,
        bbox_key=bbox_key,
        height=height,
    )
    if not minimum <= fraction <= maximum:
        raise ValueError(
            "per-cell subject height fraction "
            f"{fraction:.3f} is outside {minimum:.3f}..{maximum:.3f}"
        )
    return {
        "per_cell_subject_height_fraction": fraction,
        "per_cell_scale_contract_satisfied": True,
    }


def _validate_recoverable_per_cell_scale(
    validation: Mapping[str, object],
    contract: Mapping[str, object],
    *,
    bbox_key: str,
    height: int,
) -> dict[str, object]:
    minimum, maximum, fraction = _per_cell_scale_measurement(
        validation,
        contract,
        bbox_key=bbox_key,
        height=height,
    )
    if fraction < minimum:
        raise ValueError(
            "per-cell subject height fraction "
            f"{fraction:.3f} is outside {minimum:.3f}..{maximum:.3f}"
        )
    normalization_required = fraction > maximum
    return {
        "per_cell_subject_height_fraction": fraction,
        "per_cell_scale_contract_satisfied": not normalization_required,
        "per_cell_scale_normalization_required": normalization_required,
    }


def _per_cell_scale_measurement(
    validation: Mapping[str, object],
    contract: Mapping[str, object],
    *,
    bbox_key: str,
    height: int,
) -> tuple[float, float, float]:
    bbox = validation.get(bbox_key)
    scale = contract.get("scale_contract")
    if not isinstance(bbox, list) or len(bbox) != 4 or not isinstance(scale, Mapping):
        raise ValueError("per-cell subject scale evidence is incomplete")
    minimum = scale.get("minimum_height_fraction")
    maximum = scale.get("maximum_height_fraction")
    if not isinstance(minimum, (int, float)) or not isinstance(maximum, (int, float)):
        raise ValueError("per-cell subject scale contract is invalid")
    subject_height = int(bbox[3]) - int(bbox[1])
    fraction = subject_height / height
    return float(minimum), float(maximum), fraction


def _normalize_isolated_fallback_alpha(
    data: bytes,
    contract: Mapping[str, object],
) -> tuple[
    bytes,
    dict[str, object],
    dict[str, object] | None,
    dict[str, object],
]:
    if contract.get(
        "version"
    ) != _ISOLATED_VIEW_FALLBACK_VERSION or not _valid_fallback_record_digest(contract):
        raise ValueError("isolated-view fallback normalization contract is invalid")
    facts = inspect_image(data, expected_media_type="image/png")
    cleaned, cleanup = canonicalize_isolated_view_alpha(data)
    source_validation = validate_recoverable_isolated_view_alpha(cleaned)
    intrusion_sides = source_validation.get("isolated_view_alpha_inset_intrusion_sides")
    horizontally_centered = source_validation.get("isolated_view_alpha_horizontally_centered")
    gutter = source_validation.get("isolated_view_alpha_gutter")
    if (
        not isinstance(intrusion_sides, list)
        or any(not isinstance(side, str) for side in intrusion_sides)
        or not isinstance(horizontally_centered, bool)
        or isinstance(gutter, bool)
        or not isinstance(gutter, int)
    ):
        raise ValueError("isolated-view fallback geometry evidence is invalid")
    inset_normalization_required = bool(intrusion_sides)
    placement_normalization_required = not horizontally_centered
    fit_required = inset_normalization_required or placement_normalization_required
    maximum_height_fraction = (facts.height - gutter * 2) / facts.height
    output = cleaned
    fit_record: dict[str, object] | None = None
    if fit_required:
        output, fit = fit_isolated_view_alpha(
            data,
            maximum_height_fraction=maximum_height_fraction,
            anchor="center",
        )
        if fit.get("cleanup") != cleanup:
            raise ValueError("isolated-view fallback fit cleanup evidence is inconsistent")
        fit_record = _bind_isolated_view_fit_record(fit, contract)

    final_validation = validate_isolated_view_alpha(output)
    validation: dict[str, object] = {
        **final_validation,
        "isolated_view_alpha_cleanup": cleanup,
        "isolated_view_source_bbox": source_validation["isolated_view_alpha_bbox"],
        "isolated_view_source_margins": source_validation["isolated_view_alpha_margins"],
        "isolated_view_inset_normalization_required": inset_normalization_required,
        "isolated_view_placement_normalization_required": placement_normalization_required,
        "isolated_view_fit_required": fit_required,
        "isolated_view_fit_reasons": [
            reason
            for reason, required in (
                ("safe-inset-intrusion", inset_normalization_required),
                ("horizontal-centering", placement_normalization_required),
            )
            if required
        ],
        "isolated_view_inset_normalized": inset_normalization_required,
        "isolated_view_placement_normalized": placement_normalization_required,
        "isolated_view_maximum_height_fraction": maximum_height_fraction,
        **({"isolated_view_subject_fit": fit_record} if fit_record is not None else {}),
    }
    return output, validation, fit_record, cleanup


def _bind_isolated_view_fit_record(
    fit: Mapping[str, object],
    contract: Mapping[str, object],
) -> dict[str, object]:
    contract_sha256 = contract.get("sha256")
    if not _valid_sha256(contract_sha256):
        raise ValueError("isolated-view fallback fit contract binding is invalid")
    payload = {key: value for key, value in fit.items() if key != "sha256"}
    payload["isolated_view_contract_sha256"] = contract_sha256
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {**payload, "sha256": sha256_hex(encoded)}


def _normalize_per_cell_alpha(
    data: bytes,
    contract: Mapping[str, object],
) -> tuple[
    bytes,
    dict[str, object],
    dict[str, object] | None,
    dict[str, object],
]:
    facts = inspect_image(data, expected_media_type="image/png")
    cleaned, cleanup = canonicalize_isolated_view_alpha(data)
    source_validation = validate_recoverable_isolated_view_alpha(cleaned)
    source_scale = _validate_recoverable_per_cell_scale(
        source_validation,
        contract,
        bbox_key="isolated_view_alpha_bbox",
        height=facts.height,
    )
    intrusion_sides = source_validation.get("isolated_view_alpha_inset_intrusion_sides")
    if not isinstance(intrusion_sides, list) or any(
        not isinstance(side, str) for side in intrusion_sides
    ):
        raise ValueError("per-cell inset intrusion evidence is invalid")
    horizontally_centered = source_validation.get("isolated_view_alpha_horizontally_centered")
    if not isinstance(horizontally_centered, bool):
        raise ValueError("per-cell horizontal placement evidence is invalid")
    scale_normalization_required = source_scale["per_cell_scale_normalization_required"] is True
    inset_normalization_required = bool(intrusion_sides)
    placement_normalization_required = not horizontally_centered
    fit_required = (
        scale_normalization_required
        or inset_normalization_required
        or placement_normalization_required
    )

    output = cleaned
    fit_record: dict[str, object] | None = None
    if fit_required:
        scale = contract.get("scale_contract")
        anchor = contract.get("anchor")
        if not isinstance(scale, Mapping) or anchor not in {"center", "bottom"}:
            raise ValueError("per-cell subject fit contract is incomplete")
        maximum = scale.get("maximum_height_fraction")
        if isinstance(maximum, bool) or not isinstance(maximum, int | float):
            raise ValueError("per-cell subject fit maximum is invalid")
        output, fit = fit_isolated_view_alpha(
            data,
            maximum_height_fraction=float(maximum),
            anchor=cast(Any, anchor),
        )
        if fit.get("cleanup") != cleanup:
            raise ValueError("per-cell fit cleanup evidence is inconsistent")
        fit_record = _bind_per_cell_fit_record(fit, contract)

    final_validation = validate_isolated_view_alpha(output)
    final_scale = _validate_per_cell_scale(
        final_validation,
        contract,
        bbox_key="isolated_view_alpha_bbox",
        height=facts.height,
    )
    validation = {
        **final_validation,
        **final_scale,
        "per_cell_source_height_fraction": source_scale["per_cell_subject_height_fraction"],
        "per_cell_alpha_cleanup": cleanup,
        "per_cell_scale_normalization_required": scale_normalization_required,
        "per_cell_inset_normalization_required": inset_normalization_required,
        "per_cell_placement_normalization_required": placement_normalization_required,
        "per_cell_fit_required": fit_required,
        "per_cell_fit_reasons": [
            reason
            for reason, required in (
                ("oversize", scale_normalization_required),
                ("safe-inset-intrusion", inset_normalization_required),
                ("horizontal-centering", placement_normalization_required),
            )
            if required
        ],
        "per_cell_scale_normalized": scale_normalization_required,
        "per_cell_inset_normalized": inset_normalization_required,
        "per_cell_placement_normalized": placement_normalization_required,
        **({"per_cell_subject_fit": fit_record} if fit_record is not None else {}),
    }
    return output, validation, fit_record, cleanup


def _bind_per_cell_fit_record(
    fit: Mapping[str, object],
    contract: Mapping[str, object],
) -> dict[str, object]:
    scale = contract.get("scale_contract")
    contract_sha256 = contract.get("sha256")
    if not isinstance(scale, Mapping) or not _valid_sha256(contract_sha256):
        raise ValueError("per-cell subject fit contract binding is invalid")
    minimum = scale.get("minimum_height_fraction")
    maximum = scale.get("maximum_height_fraction")
    if (
        isinstance(minimum, bool)
        or not isinstance(minimum, int | float)
        or isinstance(maximum, bool)
        or not isinstance(maximum, int | float)
    ):
        raise ValueError("per-cell subject fit scale binding is invalid")
    payload = {key: value for key, value in fit.items() if key != "sha256"}
    payload.update(
        {
            "component_contract_sha256": contract_sha256,
            "minimum_height_fraction": float(minimum),
            "maximum_height_fraction": float(maximum),
        }
    )
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {**payload, "sha256": sha256_hex(encoded)}


def _bind_per_cell_fit_to_removal(
    fit: Mapping[str, object],
    removal: Mapping[str, object],
    *,
    raw: bytes,
) -> dict[str, object]:
    artifact = removal.get("artifact")
    inputs = removal.get("inputs")
    validation = removal.get("validation")
    if (
        not isinstance(artifact, Mapping)
        or not isinstance(inputs, list)
        or len(inputs) != 1
        or not isinstance(inputs[0], Mapping)
        or not isinstance(validation, Mapping)
        or artifact.get("media_type") != "image/png"
        or not _valid_sha256(artifact.get("sha256"))
        or not _positive_int(artifact.get("bytes"))
        or inputs[0].get("sha256") != sha256_hex(raw)
        or inputs[0].get("bytes") != len(raw)
        or validation.get("per_cell_fit_input_sha256") != fit.get("input_sha256")
        or validation.get("per_cell_fit_input_bytes") != fit.get("input_bytes")
        or validation.get("per_cell_alpha_cleanup") != fit.get("cleanup")
    ):
        raise ValueError("AI per-cell fit removal provenance is incomplete")
    payload = {key: value for key, value in fit.items() if key != "sha256"}
    payload.update(
        {
            "source_processor": "ai-background-removal",
            "removal_provenance_sha256": _canonical_mapping_sha256(removal),
            "removal_artifact_sha256": artifact["sha256"],
            "removal_artifact_bytes": artifact["bytes"],
        }
    )
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {**payload, "sha256": sha256_hex(encoded)}


def _canonical_mapping_sha256(value: Mapping[str, object]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return sha256_hex(encoded)


def _per_cell_contract_from_spec(spec: _ImageSpec) -> Mapping[str, object] | None:
    value = (spec.metadata or {}).get("per_cell_generation")
    return value if isinstance(value, Mapping) else None


def _isolated_view_contract_from_spec(spec: _ImageSpec) -> Mapping[str, object] | None:
    value = (spec.metadata or {}).get("isolated_view_fallback")
    if not isinstance(value, Mapping) or "view_index" not in value:
        return None
    return value


def _validate_per_cell_component_bytes(
    raw: bytes,
    canonical: bytes,
    contract: Mapping[str, object],
) -> None:
    raw_facts = inspect_image(raw, expected_media_type="image/png")
    alpha_facts = inspect_image(canonical, expected_media_type="image/png")
    if (raw_facts.width, raw_facts.height) != (alpha_facts.width, alpha_facts.height):
        raise ValueError("per-cell raw and canonical dimensions differ")
    raw_validation = validate_isolated_view_source(
        raw,
        width=raw_facts.width,
        height=raw_facts.height,
        allow_recoverable_inset=True,
    )
    alpha_validation = validate_isolated_view_alpha(canonical)
    _validate_recoverable_per_cell_scale(
        raw_validation,
        contract,
        bbox_key="isolated_view_bbox",
        height=raw_facts.height,
    )
    _validate_per_cell_scale(
        alpha_validation,
        contract,
        bbox_key="isolated_view_alpha_bbox",
        height=alpha_facts.height,
    )


def _parallax_layer_prompt(layer: WorldLayer) -> str:
    prompt = (
        f"Parallax layer '{layer.title}' for a 2D scrolling world. "
        f"{layer.description} Paint region: {layer.paint_region}."
    )
    if not layer.opaque and layer.z_index == 2 and 0 < layer.parallax < 1:
        prompt = (
            f"{prompt} INPUT SHAPE FOR HORIZONTAL REPEAT: keep the composition low-salience "
            "and evenly distributed across the full width. Use only gentle rolling silhouettes "
            "and small distributed foliage in the lower portion. Keep both horizontal end "
            "bands quiet and similarly sparse. Do not add houses, bridges, castles, large "
            "trees, focal landmarks, large clusters, or isolated edge vignettes."
        )
    elif layer.id == "near_foreground":
        prompt = (
            f"{prompt} INPUT SHAPE FOR HORIZONTAL REPEAT: use only small foliage silhouettes, "
            "short stems, and small leaves distributed evenly along the bottom band. Keep both "
            "horizontal end bands quiet and similarly sparse. Do not add large flowers, rocks, "
            "trunks, arches, focal clusters, landmarks, or a continuous ground plane."
        )
    if layer.opaque:
        return prompt
    return (
        f"{prompt} Render only sparse, isolated foreground framing elements confined to the "
        "declared paint region on a perfectly uniform neutral-grey background. Leave large "
        "connected background areas and generous negative space. Do not fill the full frame "
        "or create an edge-to-edge scene."
    )


def _is_turnaround_concept_stage(stage: str) -> bool:
    """Whether a stage draws a three-view turnaround that the view-by-view rescue can recover.

    A village resident's turnaround is a mob's turnaround with a shopkeeper in it: the identical
    1-row x 3-column contract, generated from the identical prompt builder, and failing in the
    identical way when the provider connects the three views across a seam. It is admitted here
    so that an exhausted resident sheet degrades into three separately generated views instead
    of failing the run - which is what the hunting turnarounds already do, and the difference
    would otherwise be invisible until a village run exhausted one.
    """

    return (
        stage == "character-concept"
        or stage.startswith("mob-concept-")
        or stage.startswith("village-npc-concept-")
    )


def _isolated_view_family(stage: str) -> str:
    """Name the sub-stage that one rescued turnaround view is generated under.

    The label is not cosmetic: it becomes the view spec's stage name, and that name is what
    `_asset_kind_for_image_stage`, `_review_subject` and `_is_player_asset_stage` all read. A
    resident's views labelled `mob-` would be reviewed as a creature and a resident's views
    labelled `character-` would pull in the player's authored profile, so the three families
    stay distinct here.
    """

    if stage == "character-concept":
        return "character"
    if stage.startswith("village-npc-concept-"):
        return "village-npc"
    return "mob"


def _eligible_isolated_view_fallback(
    spec: _ImageSpec,
    contract: GridContract | None,
    error: RetryExhaustedError,
) -> bool:
    concept_stage = _is_turnaround_concept_stage(spec.stage)
    return (
        concept_stage
        and spec.transparent
        and contract is not None
        and (contract.rows, contract.columns) == (1, 3)
        and error.attempts == 6
        and GRID_ISOLATION_ERROR_CODE in str(error.cause)
    )


def _eligible_tileset_material_fallback(
    spec: _ImageSpec,
    contract: GridContract | None,
    error: RetryExhaustedError,
    failures: object,
) -> bool:
    return (
        spec.stage == "tileset"
        and spec.transparent
        and (spec.width, spec.height) == (2400, 800)
        and contract is not None
        and contract.topology == "tileset"
        and (contract.rows, contract.columns, contract.gutter) == (4, 12, 2)
        and error.attempts == 6
        and error.retries == 5
        and _valid_tileset_material_failure_history(failures)
    )


def _resolved_grid_failure_history(
    error: RetryExhaustedError,
) -> list[dict[str, object]]:
    """Resolve only the current retry owner's typed, ordered grid-failure evidence."""

    if not error.failure_history:
        return []
    expected_error_type = f"{GridSourceLayoutError.__module__}.{GridSourceLayoutError.__qualname__}"
    failures: list[dict[str, object]] = []
    for failure in error.failure_history:
        if not isinstance(failure, RetryFailureRecord) or failure.error_type != expected_error_type:
            return []
        record = failure.as_dict()
        record.pop("error_type")
        failures.append(record)
    return failures


def _valid_tileset_material_failure_history(value: object) -> bool:
    """Accept an exhausted sheet history whose every attempt failed a declared grid contract.

    Material synthesis is the designed response to a provider that cannot deliver a valid grid
    sheet, so it is gated on *which* contract failed only to the extent that the failure must be
    one of the recipe's own typed grid-source codes. Admitting a single code would leave an
    exhausted run with no fallback whenever the provider happens to violate a sibling rule on
    one of its six attempts.
    """

    if not isinstance(value, list) or len(value) != 6:
        return False
    for expected_attempt, failure in enumerate(value, start=1):
        if not isinstance(failure, Mapping) or failure.get("attempt") != expected_attempt:
            return False
        code = failure.get("code")
        message = failure.get("message")
        if (
            code not in _TILESET_SHEET_FALLBACK_ERROR_CODES
            or not isinstance(message, str)
            or not message.startswith(f"{code}:")
        ):
            return False
        # Each code carries a fixed coordinate shape at its raise site: an empty cell always
        # names its own row and column, while cross-cell isolation and a uniform source describe
        # the whole sheet and never do. Holding each record to its own shape keeps the history
        # unforgeable now that more than one code is admitted. A painted frame is raised both
        # ways - per cell by the ring check, sheet-wide by the gutter check - so it is the one
        # code allowed either shape.
        has_coordinates = "row" in failure or "column" in failure
        if code not in _CELL_SCOPED_LAYOUT_CODES and has_coordinates:
            return False
        names_a_cell = code == GRID_EMPTY_CELL_ERROR_CODE or (
            code == GRID_PAINTED_CELL_FRAME_ERROR_CODE and has_coordinates
        )
        if names_a_cell and (
            not isinstance(failure.get("row"), int) or not isinstance(failure.get("column"), int)
        ):
            return False
    return True


def _valid_tileset_sheet_exhaustion(value: object) -> bool:
    return (
        isinstance(value, Mapping)
        and value.get("attempts") == 6
        and value.get("retries") == 5
        and _valid_sha256(value.get("request_prompt_sha256"))
    )


async def _build_tileset_material_plan(
    context: StageContext,
    spec: _ImageSpec,
    *,
    contract: GridContract,
    sheet_failures: Sequence[Mapping[str, object]],
    sheet_exhaustion: Mapping[str, object],
    image_provider: str,
    image_model: str,
    theme_identity: Mapping[str, object] | None,
    style: _StyleAnchorContext | None,
    theme_directive: str,
) -> _TilesetMaterialPlan:
    if (
        spec.stage != "tileset"
        or not spec.transparent
        or (spec.width, spec.height) != (2400, 800)
        or contract.topology != "tileset"
        or len(spec.references) != 2
    ):
        raise ValueError("tileset material plan requires the production tileset contract")
    wireframe = _template_root() / "wireframe.png"
    concept = context.run_dir / f"concept_{context.tag}.png"
    world_spec_path = context.run_dir / f"world_spec_{context.tag}.json"
    if (
        spec.references[0].resolve() != wireframe.resolve()
        or spec.references[1].resolve() != concept.resolve()
    ):
        raise ValueError(
            "tileset material plan requires the packaged wireframe and canonical world concept"
        )
    concept_pair_valid, world_spec_pair_valid = await asyncio.gather(
        asyncio.to_thread(valid_artifact_pair, concept),
        asyncio.to_thread(valid_artifact_pair, world_spec_path),
    )
    if not concept_pair_valid or not world_spec_pair_valid:
        raise ValueError(
            "tileset material plan requires provenance-bound world concept and world spec"
        )
    wireframe_data, concept_data, world_spec_data = await asyncio.gather(
        asyncio.to_thread(wireframe.read_bytes),
        asyncio.to_thread(concept.read_bytes),
        asyncio.to_thread(world_spec_path.read_bytes),
    )
    world = WorldSpec.model_validate_json(world_spec_data)
    visible_layers = [layer for layer in world.layers if layer.parallax <= 1]
    if not visible_layers:
        visible_layers = [layer for layer in world.layers if layer.opaque and layer.z_index == 0]
    if not visible_layers:
        raise ValueError("tileset material plan requires one visible world layer cue")
    selected = max(visible_layers, key=lambda layer: layer.z_index)
    ordered_layer_records = [layer.model_dump(mode="json") for layer in world.layers]
    world_description = (
        f"{world.world.name}. {world.world.one_liner} {world.world.narrative} "
        f"Canonical world-spec sha256: {sha256_hex(world_spec_data)}. "
        "Ordered layer contract: "
        f"{json.dumps(ordered_layer_records, sort_keys=True, separators=(',', ':'))}"
    )
    layer_description = (
        f"{selected.title}: {selected.description} Paint region: {selected.paint_region}."
    )
    base_prompts = {
        role: tileset_material_prompt(
            cast(Any, role),
            world_description=world_description,
            layer_description=layer_description,
            theme_directive=theme_directive,
        )
        for role in ("fill", "cap", "edge")
    }
    prompts = {
        role: (
            append_style_anchor_once(prompt, style.anchor, "tileable_texture")
            if style is not None
            else prompt
        )
        for role, prompt in base_prompts.items()
    }
    if theme_identity is not None:
        for prompt in prompts.values():
            assert_no_raw_theme_control_leak(prompt)
    wireframe_binding = _content_binding(
        wireframe,
        wireframe_data,
        role="version-locked-tileset-layout-prior",
    )
    concept_binding = _content_binding(
        concept,
        concept_data,
        role="world-concept-style-reference",
    )
    world_spec_binding = _content_binding(
        world_spec_path,
        world_spec_data,
        role="canonical-world-spec",
    )
    concept_sidecar = Path(f"{concept}.meta.json")
    world_sidecar = Path(f"{world_spec_path}.meta.json")
    concept_sidecar_data, world_sidecar_data = await asyncio.gather(
        asyncio.to_thread(concept_sidecar.read_bytes),
        asyncio.to_thread(world_sidecar.read_bytes),
    )
    concept_binding["provenance"] = {
        "path": concept_sidecar.name,
        "sha256": sha256_hex(concept_sidecar_data),
        "bytes": len(concept_sidecar_data),
    }
    world_spec_binding["provenance"] = {
        "path": world_sidecar.name,
        "sha256": sha256_hex(world_sidecar_data),
        "bytes": len(world_sidecar_data),
    }
    payload: dict[str, object] = {
        "version": TILESET_MATERIAL_SYNTHESIS_VERSION,
        "parent_stage": spec.stage,
        "parent_output": spec.output.name,
        "parent_prompt_sha256": sha256_hex(spec.prompt.encode()),
        "mode": str(context.config.transparency_mode),
        "contract": contract.as_dict(spec.width, spec.height),
        "semantic_contract": grid_semantic_contract(contract, spec.width, spec.height),
        "wireframe": wireframe_binding,
        "world_concept": concept_binding,
        "world_spec": world_spec_binding,
        "world_layers": ordered_layer_records,
        "selected_layer": selected.model_dump(mode="json"),
        "theme_identity": dict(theme_identity) if theme_identity is not None else None,
        "style_anchor": dict(style.identity) if style is not None else None,
        "sheet_reference_bindings": [wireframe_binding, concept_binding],
        "sheet_failures": [dict(failure) for failure in sheet_failures],
        "sheet_exhaustion": dict(sheet_exhaustion),
        "swatch_dimensions": [
            _TILESET_MATERIAL_SWATCH_SIZE,
            _TILESET_MATERIAL_SWATCH_SIZE,
        ],
        "swatch_role_order": ["fill", "cap", "edge"],
        "image_generation": {
            "provider": image_provider,
            "model": image_model,
            "aspect_ratio": "1:1",
            "quality": "high",
            "background": "opaque",
            "moderation": "low",
            "validated": True,
            "max_attempts": 6,
        },
        "swatch_prompt_sha256": {
            role: sha256_hex(prompt.encode()) for role, prompt in prompts.items()
        },
        "dependency_dag": [
            {"role": "fill", "depends_on": []},
            {"role": "cap", "depends_on": ["fill"]},
            {"role": "edge", "depends_on": ["fill"]},
        ],
        "failed_sheet_pixels_used": False,
        "independent_role_cell_calls": 0,
    }
    parent_contract = _record_with_digest(payload)
    return _TilesetMaterialPlan(
        parent_contract=parent_contract,
        wireframe=wireframe,
        world_concept=concept,
        world_spec=world_spec_path,
        layer_description=layer_description,
        prompts=prompts,
    )


def _content_binding(path: Path, data: bytes, *, role: str) -> dict[str, object]:
    return {
        "role": role,
        "path": path.name,
        "sha256": sha256_hex(data),
        "bytes": len(data),
    }


def _record_with_digest(payload: Mapping[str, object]) -> dict[str, object]:
    value = dict(payload)
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return {**value, "sha256": sha256_hex(encoded)}


def _tileset_material_output(output: Path, role: str) -> Path:
    return output.with_name(f".{output.stem}.material-{role}.png")


async def _tileset_material_reference_bindings(
    paths: Sequence[Path],
    *,
    roles: Sequence[str],
) -> list[dict[str, object]]:
    if len(paths) != len(roles):
        raise ValueError("tileset material reference paths and roles must align")
    data = await asyncio.gather(*(asyncio.to_thread(path.read_bytes) for path in paths))
    return await asyncio.gather(
        *(
            asyncio.to_thread(
                _content_binding_with_provenance,
                path,
                content,
                role=role,
            )
            for path, content, role in zip(paths, data, roles, strict=True)
        )
    )


def _content_binding_with_provenance(
    path: Path,
    data: bytes,
    *,
    role: str,
) -> dict[str, object]:
    if not valid_artifact_pair(path):
        raise ValueError(f"{role} artifact/provenance pair is invalid")
    sidecar = Path(f"{path}.meta.json")
    sidecar_data = sidecar.read_bytes()
    binding = _content_binding(path, data, role=role)
    binding["provenance"] = {
        "path": sidecar.name,
        "sha256": sha256_hex(sidecar_data),
        "bytes": len(sidecar_data),
    }
    return binding


def _input_from_binding(binding: Mapping[str, object], *, media_type: str) -> InputProvenance:
    path = binding.get("path")
    digest = binding.get("sha256")
    size = binding.get("bytes")
    if not isinstance(path, str) or not _valid_sha256(digest) or not _positive_int(size):
        raise ValueError("content binding is incomplete")
    return InputProvenance(
        ref=path,
        sha256=cast(str, digest),
        source="content",
        bytes=cast(int, size),
        media_type=media_type,
    )


def _retained_raw_path(spec: _ImageSpec) -> Path:
    if not spec.transparent:
        return spec.output
    return spec.output.with_name(f"{spec.output.stem}.raw.png")


def _isolated_view_output(output: Path, index: int) -> Path:
    return output.with_name(f".{output.stem}.view-{index}.png")


#: Fraction of the canvas an isolated view must keep clear on every side.
#:
#: Stated as a number because "generous empty padding" is an adjective and this is a measurement.
#: The clause it replaces said exactly that, sixth in a list of negatives, and a subject drawn to
#: the edge was the single most expensive failure mode in the fan-out: a mob turnaround for a hare
#: "with elongated ears and a flower-brush tail" exhausted six sheet attempts and then six per-view
#: attempts, twice in a row, every one of them rejected by the physical-border check. That check is
#: correct and unrecoverable - a subject touching the canvas edge has pixels cropped away, which no
#: inset repair can restore - so the only place to fix it is here, in the instruction.
#:
#: Ten percent, because the gutter the validator measures against is a small absolute band and a
#: model asked for "a margin" produces one just wide enough to fail it.
_ISOLATED_VIEW_EDGE_CLEARANCE = 0.10


def _isolated_view_prompt(parent_prompt: str, role: str) -> str:
    """Ask for one view, and lead with the framing that decides whether it is usable.

    The framing clause goes first and is phrased as a fraction of the canvas, for the same reason
    `_side_view_facing_directive` leads and is phrased as anatomy: the previous wording sat in the
    middle of a list of prohibitions and was doing no work. Extremities are named individually
    because they are what actually reaches the border - a torso drawn slightly large stays inside,
    a pair of ears on the same body does not - which is the same reason
    `_cell_containment_directive` takes an `appendages` argument rather than saying "the subject".

    The instruction to draw smaller is explicit. Faced with a subject that does not fit, a model
    will crop before it will scale, and cropping is the one outcome the validator cannot accept.
    """

    subject = parent_prompt.split("\n\n", 1)[0].strip()
    clearance = f"{_ISOLATED_VIEW_EDGE_CLEARANCE:.0%}"
    return (
        f"FRAMING, before anything else: the whole subject sits inside the middle of the canvas "
        f"with at least {clearance} of the width and height left as empty background on every "
        "side. No part of the subject - including ears, antennae, horns, tails, wings, cloaks, "
        f"hair, or outstretched limbs - may enter that {clearance} margin or touch any edge. If "
        "the subject does not fit, draw it smaller. Never crop any part of it.\n\n"
        f"Create exactly one {role}-view full-body identity study of the same subject and style "
        f"defined by this parent direction: {subject} Match the supplied identity references "
        "exactly. Show one complete centered subject only, on a uniform removable background. No "
        "ground plane, baseline, cast or contact shadow, text, label, arrow, border, panel, "
        "scenery, flourish, extra subject, or cropped body part."
    )


def _isolated_view_request_contract(
    spec: _ImageSpec,
    *,
    index: int,
    role: str,
    prompt: str,
    reference_bindings: Sequence[Mapping[str, object]],
    identity_anchor: Mapping[str, object] | None,
) -> dict[str, object]:
    parent_contract = (spec.metadata or {}).get("turnaround_prompt_reference_contract")
    payload: dict[str, object] = {
        "version": _ISOLATED_VIEW_FALLBACK_VERSION,
        "parent_stage": spec.stage,
        "view_index": index,
        "view_role": role,
        "prompt_sha256": sha256_hex(prompt.encode()),
        "parent_prompt_reference_contract": parent_contract,
        "reference_bindings": [dict(binding) for binding in reference_bindings],
        "identity_anchor": dict(identity_anchor) if identity_anchor is not None else None,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {**payload, "sha256": sha256_hex(encoded)}


def _isolated_view_component_record(
    *,
    index: int,
    role: str,
    raw_path: Path,
    raw: bytes,
    raw_record: ArtifactProvenance,
    canonical_path: Path,
    canonical: bytes,
    canonical_record: ArtifactProvenance,
    identity_anchor: Mapping[str, object] | None,
) -> dict[str, object]:
    raw_sidecar = Path(f"{raw_path}.meta.json")
    canonical_sidecar = Path(f"{canonical_path}.meta.json")
    return {
        "view_index": index,
        "view_role": role,
        "raw_path": raw_path.name,
        "raw_sha256": sha256_hex(raw),
        "raw_bytes": len(raw),
        "raw_provenance_path": raw_sidecar.name,
        "raw_provenance_sha256": sha256_hex(raw_sidecar.read_bytes()),
        "canonical_path": canonical_path.name,
        "canonical_sha256": sha256_hex(canonical),
        "canonical_bytes": len(canonical),
        "canonical_provenance_path": canonical_sidecar.name,
        "canonical_provenance_sha256": sha256_hex(canonical_sidecar.read_bytes()),
        "identity_anchor": dict(identity_anchor) if identity_anchor is not None else None,
        "generation": {
            "prompt": raw_record.prompt,
            "prompt_sha256": raw_record.prompt_sha256,
            "provider": raw_record.provider,
            "model": raw_record.model,
            "seed": raw_record.seed,
            "refs": list(raw_record.refs),
            "params": raw_record.params,
            "attempts": raw_record.attempts,
            "inputs": [item.model_dump(mode="json") for item in raw_record.inputs],
        },
        "transparency": {
            "prompt": canonical_record.prompt,
            "prompt_sha256": canonical_record.prompt_sha256,
            "provider": canonical_record.provider,
            "model": canonical_record.model,
            "seed": canonical_record.seed,
            "refs": list(canonical_record.refs),
            "params": canonical_record.params,
            "attempts": canonical_record.attempts,
            "inputs": [item.model_dump(mode="json") for item in canonical_record.inputs],
        },
    }


def _isolated_view_fallback_record(
    spec: _ImageSpec,
    *,
    contract: GridContract,
    mode: str,
    sheet_error: RetryExhaustedError,
    components: Sequence[Mapping[str, object]],
    raw: bytes,
    canonical: bytes,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "version": _ISOLATED_VIEW_FALLBACK_VERSION,
        "parent_stage": spec.stage,
        "mode": mode,
        "contract": contract.as_dict(spec.width, spec.height),
        "prompt_reference_contract": (
            (spec.metadata or {}).get("turnaround_prompt_reference_contract")
        ),
        "sheet_exhaustion": {
            "attempts": sheet_error.attempts,
            "retries": sheet_error.retries,
            "error_code": GRID_ISOLATION_ERROR_CODE,
            "reason": str(sheet_error.cause),
            "prompt_sha256": sha256_hex(spec.prompt.encode()),
        },
        "view_roles": list(_TURNAROUND_VIEW_ROLES),
        "components": [dict(component) for component in components],
        "identity_anchor_view": 0,
        "composite": {
            "raw_sha256": sha256_hex(raw),
            "raw_bytes": len(raw),
            "canonical_sha256": sha256_hex(canonical),
            "canonical_bytes": len(canonical),
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {**payload, "sha256": sha256_hex(encoded)}


def _isolated_view_component_inputs(
    components: Sequence[Mapping[str, object]],
) -> list[InputProvenance]:
    inputs: list[InputProvenance] = []
    for component in components:
        inputs.extend(
            (
                InputProvenance(
                    ref=str(component["raw_path"]),
                    sha256=str(component["raw_sha256"]),
                    source="content",
                    bytes=cast(int, component["raw_bytes"]),
                    media_type="image/png",
                ),
                InputProvenance(
                    ref=str(component["canonical_path"]),
                    sha256=str(component["canonical_sha256"]),
                    source="content",
                    bytes=cast(int, component["canonical_bytes"]),
                    media_type="image/png",
                ),
            )
        )
    return inputs


def _per_cell_component_record(
    *,
    cell: _PerCellDefinition,
    raw_path: Path,
    raw: bytes,
    raw_record: ArtifactProvenance,
    canonical_path: Path,
    canonical: bytes,
    canonical_record: ArtifactProvenance,
    cell_contract: Mapping[str, object],
    prior: Mapping[str, object] | None,
) -> dict[str, object]:
    raw_sidecar = Path(f"{raw_path}.meta.json")
    canonical_sidecar = Path(f"{canonical_path}.meta.json")
    return {
        "cell_index": cell.index,
        "row": cell.row,
        "column": cell.column,
        "semantic_role": cell.role,
        "source_spec": cell.source_spec,
        "action": cell.action,
        "silhouette": cell.silhouette,
        "component_contract": dict(cell_contract),
        "layout_prior": dict(prior) if prior is not None else None,
        "raw_path": raw_path.name,
        "raw_sha256": sha256_hex(raw),
        "raw_bytes": len(raw),
        "raw_provenance_path": raw_sidecar.name,
        "raw_provenance_sha256": sha256_hex(raw_sidecar.read_bytes()),
        "canonical_path": canonical_path.name,
        "canonical_sha256": sha256_hex(canonical),
        "canonical_bytes": len(canonical),
        "canonical_provenance_path": canonical_sidecar.name,
        "canonical_provenance_sha256": sha256_hex(canonical_sidecar.read_bytes()),
        "generation": {
            "prompt": raw_record.prompt,
            "prompt_sha256": raw_record.prompt_sha256,
            "provider": raw_record.provider,
            "model": raw_record.model,
            "seed": raw_record.seed,
            "refs": list(raw_record.refs),
            "params": raw_record.params,
            "attempts": raw_record.attempts,
            "inputs": [item.model_dump(mode="json") for item in raw_record.inputs],
        },
        "transparency": {
            "prompt": canonical_record.prompt,
            "prompt_sha256": canonical_record.prompt_sha256,
            "provider": canonical_record.provider,
            "model": canonical_record.model,
            "seed": canonical_record.seed,
            "refs": list(canonical_record.refs),
            "params": canonical_record.params,
            "attempts": canonical_record.attempts,
            "inputs": [item.model_dump(mode="json") for item in canonical_record.inputs],
        },
    }


def _per_cell_fallback_record(
    spec: _ImageSpec,
    *,
    plan: _PerCellAdapterPlan,
    contract: GridContract,
    mode: str,
    sheet_failures: Sequence[Mapping[str, object]],
    sheet_exhaustion: Mapping[str, object],
    components: Sequence[Mapping[str, object]],
    identity_anchor: Mapping[str, object] | None,
    normalization: Mapping[str, object],
    raw: bytes,
    canonical: bytes,
    theme_identity: Mapping[str, object] | None,
) -> dict[str, object]:
    identity_dag = [
        {
            "cell_index": cell.index,
            "depends_on": [0]
            if plan.identity_policy == "cell-0-scale-style-anchor" and cell.index > 0
            else [],
            "usage": "style-and-scale-only"
            if plan.identity_policy == "cell-0-scale-style-anchor" and cell.index > 0
            else "independent",
        }
        for cell in plan.cells
    ]
    payload: dict[str, object] = {
        "version": _PER_CELL_GENERATION_VERSION,
        "adapter": plan.adapter,
        "parent_stage": spec.stage,
        "mode": mode,
        "contract": contract.as_dict(spec.width, spec.height),
        "parent_contract": plan.parent_contract,
        "parent_prompt_sha256": sha256_hex(spec.prompt.encode()),
        "theme_identity": dict(theme_identity) if theme_identity is not None else None,
        "sheet_failures": [dict(failure) for failure in sheet_failures],
        "sheet_exhaustion": dict(sheet_exhaustion),
        "role_order": [cell.role for cell in plan.cells],
        "identity_policy": plan.identity_policy,
        "identity_anchor": dict(identity_anchor) if identity_anchor is not None else None,
        "identity_dag": identity_dag,
        "components": [dict(component) for component in components],
        "grid_normalization": dict(normalization),
        "composite": {
            "raw_sha256": sha256_hex(raw),
            "raw_bytes": len(raw),
            "canonical_sha256": sha256_hex(canonical),
            "canonical_bytes": len(canonical),
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {**payload, "sha256": sha256_hex(encoded)}


def _per_cell_component_inputs(
    components: Sequence[Mapping[str, object]],
) -> list[InputProvenance]:
    inputs: list[InputProvenance] = []
    for component in components:
        inputs.extend(
            (
                InputProvenance(
                    ref=str(component["raw_path"]),
                    sha256=str(component["raw_sha256"]),
                    source="content",
                    bytes=cast(int, component["raw_bytes"]),
                    media_type="image/png",
                ),
                InputProvenance(
                    ref=str(component["canonical_path"]),
                    sha256=str(component["canonical_sha256"]),
                    source="content",
                    bytes=cast(int, component["canonical_bytes"]),
                    media_type="image/png",
                ),
            )
        )
    return inputs


def _tileset_material_component_contract(
    plan: _TilesetMaterialPlan,
    *,
    role: str,
    prompt: str,
    reference_bindings: Sequence[Mapping[str, object]],
    fill_anchor: bytes | None,
) -> dict[str, object]:
    if role == "fill" and fill_anchor is not None:
        raise ValueError("FILL cannot depend on another material")
    if role != "fill" and fill_anchor is None:
        raise ValueError(f"{role.upper()} requires the accepted FILL anchor")
    image_generation = plan.parent_contract.get("image_generation")
    if not isinstance(image_generation, Mapping):
        raise ValueError("tileset material parent lacks image generation identity")
    payload: dict[str, object] = {
        "version": TILESET_MATERIAL_SYNTHESIS_VERSION,
        "parent_contract_sha256": plan.parent_contract["sha256"],
        "role": role,
        "prompt_sha256": sha256_hex(prompt.encode()),
        "dimensions": [
            _TILESET_MATERIAL_SWATCH_SIZE,
            _TILESET_MATERIAL_SWATCH_SIZE,
        ],
        "background": "opaque",
        "image_generation": dict(image_generation),
        "style_anchor": plan.parent_contract.get("style_anchor"),
        "reference_bindings": [dict(binding) for binding in reference_bindings],
        "depends_on": [] if role == "fill" else ["fill"],
        "fill_anchor": (
            {
                "path": _tileset_material_output(
                    Path(str(plan.parent_contract["parent_output"])), "fill"
                ).name,
                "sha256": sha256_hex(fill_anchor),
                "bytes": len(fill_anchor),
            }
            if fill_anchor is not None
            else None
        ),
        "provider_attempts": 6,
        "provider_retries": 5,
        "failed_sheet_pixels_used": False,
    }
    return _record_with_digest(payload)


async def _tileset_material_component_record(
    *,
    role: str,
    raw_path: Path,
    canonical_path: Path,
    raw_sidecar: Path,
    canonical_sidecar: Path,
    component_contract: Mapping[str, object],
    canonicalization: Mapping[str, object],
    validation: Mapping[str, object],
) -> dict[str, object]:
    raw, canonical, raw_meta, canonical_meta = await asyncio.gather(
        asyncio.to_thread(raw_path.read_bytes),
        asyncio.to_thread(canonical_path.read_bytes),
        asyncio.to_thread(raw_sidecar.read_bytes),
        asyncio.to_thread(canonical_sidecar.read_bytes),
    )
    return _tileset_material_component_record_from_bytes(
        role=role,
        raw_path=raw_path,
        canonical_path=canonical_path,
        raw=raw,
        canonical=canonical,
        raw_sidecar=raw_sidecar,
        canonical_sidecar=canonical_sidecar,
        raw_meta=raw_meta,
        canonical_meta=canonical_meta,
        component_contract=component_contract,
        canonicalization=canonicalization,
        validation=validation,
    )


def _tileset_material_component_record_from_bytes(
    *,
    role: str,
    raw_path: Path,
    canonical_path: Path,
    raw: bytes,
    canonical: bytes,
    raw_sidecar: Path,
    canonical_sidecar: Path,
    raw_meta: bytes,
    canonical_meta: bytes,
    component_contract: Mapping[str, object],
    canonicalization: Mapping[str, object],
    validation: Mapping[str, object],
) -> dict[str, object]:
    raw_record = json.loads(raw_meta)
    canonical_record = json.loads(canonical_meta)
    payload: dict[str, object] = {
        "role": role,
        "component_contract": dict(component_contract),
        "raw_path": raw_path.name,
        "raw_sha256": sha256_hex(raw),
        "raw_bytes": len(raw),
        "raw_provenance_path": raw_sidecar.name,
        "raw_provenance_sha256": sha256_hex(raw_meta),
        "canonical_path": canonical_path.name,
        "canonical_sha256": sha256_hex(canonical),
        "canonical_bytes": len(canonical),
        "canonical_provenance_path": canonical_sidecar.name,
        "canonical_provenance_sha256": sha256_hex(canonical_meta),
        "generation": _fallback_provenance_summary(raw_record),
        "canonical_generation": _fallback_provenance_summary(canonical_record),
        "canonicalization": dict(canonicalization),
        "validation": dict(validation),
    }
    return _record_with_digest(payload)


def _cached_tileset_material_component(
    canonical_path: Path,
    raw_path: Path,
    *,
    role: str,
    component_contract: Mapping[str, object],
    fill_anchor: bytes | None,
) -> dict[str, object] | None:
    raw_sidecar = Path(f"{raw_path}.meta.json")
    canonical_sidecar = Path(f"{canonical_path}.meta.json")
    if not valid_artifact_pair(raw_path) or not valid_artifact_pair(canonical_path):
        return None
    try:
        raw = raw_path.read_bytes()
        canonical = canonical_path.read_bytes()
        raw_meta = raw_sidecar.read_bytes()
        canonical_meta = canonical_sidecar.read_bytes()
        raw_record = json.loads(raw_meta)
        canonical_record = json.loads(canonical_meta)
        expected, canonicalization = canonicalize_tileset_material(
            raw,
            role=cast(Any, role),
            fill_anchor=fill_anchor,
        )
        validation = validate_tileset_material_swatch(
            canonical,
            role=cast(Any, role),
            fill_anchor=fill_anchor,
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    raw_params = raw_record.get("params")
    raw_metadata = raw_params.get("metadata") if isinstance(raw_params, Mapping) else None
    canonical_params = canonical_record.get("params")
    canonical_metadata = (
        canonical_params.get("metadata") if isinstance(canonical_params, Mapping) else None
    )
    canonical_validation = canonical_record.get("validation")
    if (
        expected != canonical
        or not isinstance(raw_metadata, Mapping)
        or not isinstance(canonical_metadata, Mapping)
        or raw_metadata.get("tileset_material_component") != component_contract
        or canonical_metadata.get("tileset_material_component") != component_contract
        or canonical_params.get("tileset_material_canonicalization") != canonicalization
        or not isinstance(canonical_validation, Mapping)
        or canonical_validation.get("tileset_material_canonicalization") != canonicalization
        or not _valid_tileset_material_component_provenance(
            raw_record,
            canonical_record,
            role=role,
            raw_path=raw_path,
            canonical_path=canonical_path,
            raw=raw,
            canonical=canonical,
            component_contract=component_contract,
            canonicalization=canonicalization,
        )
    ):
        return None
    return _tileset_material_component_record_from_bytes(
        role=role,
        raw_path=raw_path,
        canonical_path=canonical_path,
        raw=raw,
        canonical=canonical,
        raw_sidecar=raw_sidecar,
        canonical_sidecar=canonical_sidecar,
        raw_meta=raw_meta,
        canonical_meta=canonical_meta,
        component_contract=component_contract,
        canonicalization=canonicalization,
        validation=validation,
    )


def _valid_tileset_material_component_provenance(
    raw_value: Mapping[str, Any],
    canonical_value: Mapping[str, Any],
    *,
    role: str,
    raw_path: Path,
    canonical_path: Path,
    raw: bytes,
    canonical: bytes,
    component_contract: Mapping[str, object],
    canonicalization: Mapping[str, object],
) -> bool:
    """Require cache sidecars to preserve every generation and dependency binding."""

    try:
        raw_record = ArtifactProvenance.model_validate(raw_value)
        canonical_record = ArtifactProvenance.model_validate(canonical_value)
    except ValueError:
        return False
    generation = component_contract.get("image_generation")
    bindings = component_contract.get("reference_bindings")
    if not isinstance(generation, Mapping) or not isinstance(bindings, list):
        return False
    expected_refs: list[str] = []
    expected_inputs: list[tuple[str, str, int]] = []
    for binding in bindings:
        if not isinstance(binding, Mapping):
            return False
        path = binding.get("path")
        digest = binding.get("sha256")
        size = binding.get("bytes")
        if not isinstance(path, str) or not _valid_sha256(digest) or not _positive_int(size):
            return False
        expected_refs.append(path)
        expected_inputs.append((path, cast(str, digest), cast(int, size)))
    style_identity = component_contract.get("style_anchor")
    style_input: tuple[str, str, int] | None = None
    if style_identity is not None:
        if not isinstance(style_identity, Mapping):
            return False
        style_ref = style_identity.get("artifact_ref")
        style_digest = style_identity.get("artifact_sha256")
        style_bytes = style_identity.get("artifact_bytes")
        if (
            not isinstance(style_ref, str)
            or not _valid_sha256(style_digest)
            or not _positive_int(style_bytes)
        ):
            return False
        style_input = (style_ref, cast(str, style_digest), cast(int, style_bytes))
    prompt_digest = component_contract.get("prompt_sha256")
    request_params = {
        "n": 1,
        "validated": True,
        "aspect_ratio": generation.get("aspect_ratio"),
        "quality": generation.get("quality"),
        "background": generation.get("background"),
        "moderation": generation.get("moderation"),
    }
    raw_metadata = raw_record.params.get("metadata")
    upstream_value = raw_record.params.get("upstream_provenance")
    if isinstance(upstream_value, Mapping):
        upstream_value = {"seed": None, **upstream_value}
    try:
        upstream = ArtifactProvenance.model_validate(upstream_value)
    except ValueError:
        return False
    upstream_metadata = upstream.params.get("metadata")
    expected_raw_input_count = len(expected_inputs) + (1 if style_input is not None else 0) + 1
    if (
        raw_record.provider != generation.get("provider")
        or raw_record.model != generation.get("model")
        or raw_record.prompt_sha256 != prompt_digest
        or sha256_hex(raw_record.prompt.encode()) != prompt_digest
        or raw_record.refs != expected_refs
        or not isinstance(raw_metadata, Mapping)
        or raw_metadata.get("stage") != f"tileset-material-{role}"
        or raw_metadata.get("parent_stage") != "tileset"
        or raw_metadata.get("tileset_material_component") != component_contract
        or raw_metadata.get("style_anchor") != style_identity
        or raw_record.attempts != upstream.attempts
        or upstream.provider != generation.get("provider")
        or upstream.model != generation.get("model")
        or upstream.prompt != raw_record.prompt
        or upstream.prompt_sha256 != prompt_digest
        or upstream.refs != expected_refs
        or not isinstance(upstream_metadata, Mapping)
        or upstream_metadata.get("tileset_material_component") != component_contract
        or not _valid_tileset_material_style_binding(
            upstream.params.get("style_anchor"),
            style_identity,
        )
        or any(upstream.params.get(key) != value for key, value in request_params.items())
        or upstream.validation.get("tileset_material_source_valid") is not True
        or upstream.validation.get("tileset_material_role") != role
        or upstream.validation.get("caller") is not True
        or upstream.artifact is None
        or raw_record.artifact is None
        or raw_record.artifact.sha256 != sha256_hex(raw)
        or raw_record.artifact.bytes != len(raw)
        or (
            isinstance(
                canonicalization.get("cap_fill_lightness_recovery"),
                Mapping,
            )
            and raw_record.validation.get("tileset_material_raw_canonicalization")
            != canonicalization
        )
        or len(upstream.inputs) != len(expected_inputs)
        or len(raw_record.inputs) != expected_raw_input_count
    ):
        return False
    for index, (path, digest, size) in enumerate(expected_inputs):
        for item in (upstream.inputs[index], raw_record.inputs[index]):
            if (
                item.ref != path
                or item.sha256 != digest
                or item.bytes != size
                or item.source != "content"
                or item.media_type != "image/png"
            ):
                return False
    if style_input is not None:
        item = raw_record.inputs[len(expected_inputs)]
        if (
            item.ref != style_input[0]
            or item.sha256 != style_input[1]
            or item.bytes != style_input[2]
            or item.source != "content"
            or item.media_type != "application/json"
        ):
            return False
    provider_output = raw_record.inputs[-1]
    if (
        provider_output.ref != f"provider-output:tileset-material-{role}"
        or provider_output.sha256 != upstream.artifact.sha256
        or provider_output.bytes != upstream.artifact.bytes
        or provider_output.source != "content"
        or provider_output.media_type != "image/png"
    ):
        return False
    canonical_metadata = canonical_record.params.get("metadata")
    expected_canonical_inputs = [
        (raw_path.name, sha256_hex(raw), len(raw), "image/png"),
        *(
            [(style_input[0], style_input[1], style_input[2], "application/json")]
            if style_input is not None
            else []
        ),
        *[(path, digest, size, "image/png") for path, digest, size in expected_inputs],
    ]
    if (
        canonical_record.provider != "local"
        or canonical_record.model != TILESET_MATERIAL_SYNTHESIS_VERSION
        or canonical_record.prompt_sha256 != prompt_digest
        or sha256_hex(canonical_record.prompt.encode()) != prompt_digest
        or canonical_record.refs != [raw_path.name, *expected_refs]
        or canonical_record.attempts != 1
        or canonical_record.artifact is None
        or canonical_record.artifact.sha256 != sha256_hex(canonical)
        or canonical_record.artifact.bytes != len(canonical)
        or canonical_record.tool.name != "tileset-material-canonicalizer"
        or canonical_record.tool.version != TILESET_MATERIAL_SYNTHESIS_VERSION
        or not isinstance(canonical_metadata, Mapping)
        or canonical_metadata.get("tileset_material_component") != component_contract
        or canonical_metadata.get("style_anchor") != style_identity
        or canonical_record.params.get("tileset_material_canonicalization") != canonicalization
        or canonical_record.validation.get("tileset_material_source_valid") is not True
        or canonical_record.validation.get("tileset_material_role") != role
        or canonical_record.validation.get("tileset_material_canonicalization") != canonicalization
        or canonical_record.validation.get("output_sha256") != sha256_hex(canonical)
        or len(canonical_record.inputs) != len(expected_canonical_inputs)
    ):
        return False
    return all(
        item.ref == path
        and item.sha256 == digest
        and item.bytes == size
        and item.source == "content"
        and item.media_type == media_type
        for item, (path, digest, size, media_type) in zip(
            canonical_record.inputs,
            expected_canonical_inputs,
            strict=True,
        )
    )


def _valid_tileset_material_style_binding(
    value: object,
    identity: object,
) -> bool:
    if identity is None:
        return value is None
    if not isinstance(value, Mapping) or not isinstance(identity, Mapping):
        return False
    for key in (
        "anchor_sha256",
        "compiler_sha256",
        "compiler_version",
        "resource_sha256",
        "skill_sha256",
        "style_mode",
        "vocabulary_sha256",
    ):
        if value.get(key) != identity.get(key):
            return False
    return value.get("asset_kind") == "tileable_texture" and value.get("renderer_version") == 1


def _tileset_material_fallback_record(
    spec: _ImageSpec,
    *,
    plan: _TilesetMaterialPlan,
    contract: GridContract,
    mode: str,
    sheet_failures: Sequence[Mapping[str, object]],
    sheet_exhaustion: Mapping[str, object],
    components: Sequence[Mapping[str, object]],
    dependency: Mapping[str, object],
    synthesis: Mapping[str, object],
    flattening: Mapping[str, object],
    retained_raw: bytes,
    canonical: bytes,
    final_grid: Mapping[str, object],
) -> dict[str, object]:
    payload: dict[str, object] = {
        "version": TILESET_MATERIAL_SYNTHESIS_VERSION,
        "parent_stage": spec.stage,
        "mode": mode,
        "contract": contract.as_dict(spec.width, spec.height),
        "parent_prompt_sha256": sha256_hex(spec.prompt.encode()),
        "parent_contract": plan.parent_contract,
        "sheet_failures": [dict(failure) for failure in sheet_failures],
        "sheet_exhaustion": dict(sheet_exhaustion),
        "role_order": ["fill", "cap", "edge"],
        "identity_dag": [
            {"role": "fill", "depends_on": []},
            {"role": "cap", "depends_on": ["fill"]},
            {"role": "edge", "depends_on": ["fill"]},
        ],
        "components": [dict(component) for component in components],
        "dependency_evidence": dict(dependency),
        "synthesis": dict(synthesis),
        "flattening": dict(flattening),
        "final_grid": dict(final_grid),
        "composite": {
            "raw_sha256": sha256_hex(retained_raw),
            "raw_bytes": len(retained_raw),
            "canonical_sha256": sha256_hex(canonical),
            "canonical_bytes": len(canonical),
        },
        "failed_sheet_pixels_used": False,
        "independent_role_cell_calls": 0,
    }
    return _record_with_digest(payload)


def _tileset_material_component_inputs(
    components: Sequence[Mapping[str, object]],
) -> list[InputProvenance]:
    inputs: list[InputProvenance] = []
    for component in components:
        for prefix in ("raw", "canonical"):
            inputs.append(
                InputProvenance(
                    ref=str(component[f"{prefix}_path"]),
                    sha256=str(component[f"{prefix}_sha256"]),
                    source="content",
                    bytes=cast(int, component[f"{prefix}_bytes"]),
                    media_type="image/png",
                )
            )
    return inputs


def _image_png_bytes(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", compress_level=9, optimize=False)
    return output.getvalue()


def _prompt_for_transparency(prompt: str, mode: object | None) -> str:
    if mode is None:
        return prompt.strip()
    if str(mode) == "chroma":
        fragment = (
            "Render all exterior background pixels as exact solid #FF00FF, without shadows "
            "or subject-coloured magenta spill. The key is a degraded fallback."
        )
    else:
        fragment = (
            "Isolate the foreground cleanly on neutral grey or a naturally isolated plain "
            "background suitable for a dedicated background-removal pass."
        )
    return f"{prompt.strip()}\n\n{fragment}"


def _effective_image_prompt(
    spec: _ImageSpec,
    compiled: _CompiledThemeContext | None,
    mode: object | None,
    game: _GameContractContext | None = None,
) -> str:
    """Rebuild the exact text `_generate_image_asset` sends, for cache and resume comparison.

    This is a second copy of the assembly inlined in `_generate_image_asset`, and the two must
    stay identical clause for clause and in the same order. When they drift, nothing fails
    loudly: the recorded prompt digest simply stops matching the recomputed one, every resume
    check misses, and the stage silently regenerates from scratch on every run.

    That is not hypothetical. Adding the game art-direction clause to the generator without
    adding it here made the tileset's material-synthesis resume unmatchable, so an accepted
    atlas already on disk was rediscarded and rebuilt every run - six sheet attempts, three
    fresh swatches and a fresh composition, about twenty-seven minutes, re-rolling two
    stochastic variant contracts each time. The artifact was valid the whole time.
    """

    prompt = spec.prompt
    if compiled is not None:
        prompt = (
            _append_binding_visual_constraints(prompt, compiled.plan.hard_exclusions)
            if spec.compiled_creative_base
            else _append_compiled_directive(
                prompt,
                _directive_for_image_stage(
                    compiled.plan,
                    spec.theme_family or spec.stage,
                ),
                compiled.plan.hard_exclusions,
            )
        )
    if game is not None:
        prompt = append_game_art_direction_once(prompt, game.contract)
    return _prompt_for_transparency(prompt, mode)


_TURNAROUND_LAYOUT_VERSION = "isolated-turnaround-thirds-v1"
_TURNAROUND_LAYOUT_RULES = (
    "Render exactly three complete views left-to-right: front, side, back. Treat the canvas "
    "as an exact 1-row x 3-column grid. Each view is an independent isolated subject, "
    "centered wholly inside its exact third with generous internal padding on every side. "
    "Leave wide, uninterrupted clear separator bands of the uniform mode background at both "
    "internal seams. No foreground pixel from one third may touch or connect to another. "
    "Forbid any shared ground plane, shared baseline, visible baseline, cast or contact shadow, "
    "vines, flourishes, labels, arrows, panels, borders, scenery, or other foreground connection "
    "across seams. Keep all three views floating independently on the uniform mode background."
)


def _turnaround_prompt(subject: str) -> str:
    return f"Three-view concept turnaround for {subject.strip()}.\n\n{_TURNAROUND_LAYOUT_RULES}"


def _turnaround_prompt_reference_contract(
    prompt: str,
    *,
    reference_bindings: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    bindings = [dict(binding) for binding in reference_bindings]
    payload: dict[str, object] = {
        "version": _TURNAROUND_LAYOUT_VERSION,
        "prompt": prompt.strip(),
        "layout": {"rows": 1, "columns": 3, "gutter": 8},
        "reference_bindings": bindings,
        "layout_reference": None,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {
        "version": _TURNAROUND_LAYOUT_VERSION,
        "sha256": sha256_hex(encoded),
        "prompt_sha256": sha256_hex(prompt.strip().encode()),
        "layout": payload["layout"],
        "reference_bindings": bindings,
        "layout_reference": None,
    }


def _side_view_facing_directive() -> str:
    """State the facing contract once, first, and as anatomy rather than as an adjective.

    Both strip prompts already asked for a "side view facing right" - and roughly half of a
    run's strips still arrived facing left, including five separate provider calls for one
    character that split three to two. The clause was doing no work: it sat sixth in a list of
    layout constraints, and "facing right" names a direction without saying what about the
    subject points there.

    So it leads now, it is phrased as where the face and the head end sit, and it separates the
    subject's facing from the strip's reading order - frames always advance rightwards across
    the sheet, which is a different fact that the wording could otherwise be read as. The
    direction comes from the same constant the facing review checks against, so the instruction
    and the gate cannot drift apart.
    """

    facing = REQUIRED_SIDE_VIEW_FACING
    opposite = "left" if facing == "right" else "right"
    return (
        f"FACING, before anything else: every frame is a side profile whose subject faces the "
        f"{facing} edge of the image. The eyes, face, and front of the body point {facing}; the "
        f"back, tail, or rear end is on the {opposite}. The subject reads as moving toward the "
        f"{facing} edge. This is about the subject's own body, not the sheet: the frames run "
        f"left to right across the sheet whichever way the subject faces. Never draw it facing "
        f"{opposite}, and never turn it to face the viewer. "
    )


def _cell_containment_directive(*, grid: str, subject: str, appendages: str) -> str:
    """State the cell containment contract with the same weight as the facing one.

    This clause and the facing clause are both contractual and both enforced - crossing a cell
    boundary fails `scrolling-grid-cross-cell-isolation-v1`, which is unrecoverable and burns
    all six provider attempts. When facing was promoted to a leading labelled directive this
    was left as a trailing sub-clause of a run-on sentence, and `character-attack` - the one
    pose carrying a horizontally extended weapon - began failing isolation where it had passed.
    Both now lead as labelled constraints, and the extended-reach case is named outright rather
    than left to be inferred from "including weapons".
    """

    return (
        f"CELL CONTAINMENT, equally binding: strict {grid} equal cells, and each {subject}'s "
        f"whole silhouette - including {appendages} - sits inside its own cell with clear "
        "margin on every side. Nothing may touch or cross a cell boundary, and no two cells "
        "may share connected artwork: this is a sheet of separate subjects, never one scene "
        "arranged across a grid. If an extended reach - a thrust weapon, a stretched limb, a "
        "spread wing, a trailing vine - would come near a boundary, scale that subject down "
        "until it fits with room to spare. A smaller subject that fits is correct; a larger "
        "one that touches a boundary is not. "
    )


def _mob_strip_prompt(name: str, state: str) -> str:
    """Give mob strips the cell discipline character strips already state explicitly.

    Mob strips share the character template but previously carried none of its instructions,
    which is why they arrived with template borders painted in, a different camera angle per
    frame, and silhouettes wide enough to connect across cells and fail grid isolation.
    """

    entry = mob_strip_state(state)
    containment = _cell_containment_directive(
        grid="4x1",
        subject="frame",
        appendages=entry.appendages,
    )
    return (
        f"{entry.lead_directive}"
        f"Four-frame {entry.state} animation strip for the supplied creature {name}: "
        f"{entry.motion}. "
        f"{_side_view_facing_directive()}"
        f"{containment}"
        "CONSISTENCY: fixed identity, scale, and ground baseline across all four frames. "
        "CLEAN PLATE: do not render template lines, labels, borders, or shadows."
    )


def _npc_idle_strip_prompt(npc: VillageNpc) -> str:
    """Give a resident's idle strip the mob strip's directives verbatim, with a settled motion.

    Every clause outside the motion phrase is the same object the mob and character strips are
    built from, called rather than restated. That is deliberate: the facing and containment
    wordings above were arrived at against measured failures - half a run's strips arriving
    mirrored, and `character-attack` failing cell isolation once the containment clause was
    demoted to a sub-clause - and a paraphrase here would quietly opt the village out of both
    corrections while looking equivalent.

    The motion is the one thing that genuinely differs. A resident is standing in a town, not
    breathing at the camera between fights, so the phases are a weight shift, a breath and a
    small gesture; the planted-feet clause is kept because a four-frame strip whose subject
    drifts across the cells has no fixed anchor for the runtime to stand on the terrain.
    """

    containment = _cell_containment_directive(
        grid="4x1",
        subject="frame",
        appendages="tools, aprons, cloaks, and carried goods",
    )
    return (
        f"Four-frame idle animation strip for the supplied village resident {npc.name}, "
        f"{npc.role_label}: four visibly distinct phases of a settled standing idle - weight "
        f"shift, breath, and a small gesture; the feet stay planted. "
        f"{_side_view_facing_directive()}"
        f"{containment}"
        "CONSISTENCY: fixed identity, scale, and ground baseline across all four frames. "
        "CLEAN PLATE: do not render template lines, labels, borders, or shadows."
    )


def _resident_still_prompt(
    npc: DirectedVillageNpc,
    *,
    game: _GameContractContext,
) -> str:
    """The whole prompt for one forward-facing resident still.

    Written as a sibling of `_npc_idle_strip_prompt` rather than a variant of it, because almost
    nothing survives the change of shape. There is no facing directive - the FACING clause exists
    to stop a side view coming back mirrored, and a front view has no mirror to come back in - and
    no cell-containment directive, because containment is about a subject's limbs crossing into
    the neighbouring cell and there is no neighbouring cell.

    What is stated instead is the thing a single portrait can get wrong: the camera. An image
    model handed "a village baker" and a turnaround reference will happily return the three-
    quarter view it liked best in that reference, so the view is named first, as anatomy - where
    the eyes point - for the same reason `_side_view_facing_directive` names it as anatomy.

    The pose and the held object arrive already rendered by `resident_still_subject` from the
    vocabulary's own sentences, so they are not restated here.
    """

    subject = resident_still_subject(npc, vocabulary=game.vocabulary)
    return (
        "VIEW, before anything else: a single front view. The subject faces the viewer "
        "directly - both eyes, the full face, and the front of the body point out of the image "
        "at the camera. This is not a side profile and not a three-quarter turn; the shoulders "
        "are square to the viewer.\n\n"
        f"One complete standing figure, centred, drawn once: {subject}\n\n"
        "The whole figure is inside the frame from the crown of the head to the soles of the "
        "feet, with the feet resting on an implied ground line at the bottom edge and a small "
        "margin of empty space on every side. Draw exactly one figure - no second view, no "
        "turnaround, no animation frames, no duplicate of the same person elsewhere in the "
        "image.\n\n"
        "CLEAN PLATE: a single flat background colour behind the figure, no scenery, no props "
        "other than what the figure holds, no ground shadow, no border, no text, and no labels."
    )


def _village_fixtures_prompt(spec: VillageSpec) -> str:
    """Ask for the settlement's furniture as an obstacle sheet, because that is what it is.

    The wording tracks the obstacle-sheet prompt clause for clause, including the clean-plate
    line, for the same reason the spec shape does: this sheet is validated by the identical
    2-row x 4-column grid contract and rescued by the identical per-cell fallback, and a prompt
    that drifted from the one those were tuned against would fail them in ways only a generated
    sheet reveals. Only the subject noun and the named appendages change - a market stall's
    awning and its hanging goods are what reach across a cell boundary here, where a tree's
    branches and a banner do on an obstacle sheet.
    """

    return (
        f"Eight complete isolated village fixtures for {spec.fixtures_theme} in a strict 2-row "
        "x 4-column grid, one fixture per equal cell, ordered left-to-right across each row. "
        + _cell_containment_directive(
            grid="2-row x 4-column",
            subject="fixture",
            appendages="awnings, poles, ropes, and hanging goods",
        )
        + "CLEAN PLATE: do not render template lines, labels, borders, or shadows. "
        + "The fixtures are: "
        + "; ".join(
            f"cell {index + 1} {fixture.name}: {fixture.brief}"
            for index, fixture in enumerate(spec.fixtures)
        )
    )


def _character_strip_prompt(state: str) -> str:
    motion = {
        "idle": "four visibly distinct phases of a subtle breathing cycle; feet stay planted",
        "walk": "four alternating-leg phases forming one clean walk cycle",
        "run": "four sprint phases including airborne frames and exaggerated stride",
        "jump": "anticipation crouch, push-off, airborne apex, and landing impact",
        "crawl": "four hands-and-knees phases with a low horizontal torso",
        "attack": "anticipation, swing, impact, and recovery",
    }[state]
    containment = _cell_containment_directive(
        grid="4x1",
        subject="frame",
        appendages="weapons, cloaks, hair, and outstretched limbs",
    )
    return (
        f"Four-frame {state} animation strip for the supplied character: {motion}. "
        f"{_side_view_facing_directive()}"
        f"{containment}"
        "CONSISTENCY: fixed identity, scale, head rail, and feet baseline across all four "
        "frames. "
        "CLEAN PLATE: do not render template lines, labels, borders, or shadows."
    )


def _ratio(width: int, height: int) -> str:
    divisor = _gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


_PROVIDER_ASPECT_BY_REDUCED_RATIO = {
    "1:1": "1:1",
    "3:2": "3:2",
    "2:3": "2:3",
    "4:3": "4:3",
    "3:4": "3:4",
    "16:9": "16:9",
    "9:16": "9:16",
    "7:3": "21:9",
    "3:1": "21:9",
    "2:1": "16:9",
    "1:4": "9:16",
}


def _provider_aspect_ratio(width: int, height: int) -> str:
    ratio = _ratio(width, height)
    try:
        return _PROVIDER_ASPECT_BY_REDUCED_RATIO[ratio]
    except KeyError as error:
        raise ValueError(
            f"scrolling-preview canvas {width}x{height} has no verified provider aspect ratio"
        ) from error


def _gcd(left: int, right: int) -> int:
    while right:
        left, right = right, left % right
    return abs(left) or 1


def _exact_image(path: Path, width: int, height: int, *, alpha: bool) -> bool:
    try:
        data = path.read_bytes()
        facts = inspect_image(data, expected_media_type="image/png")
        if alpha:
            _alpha_counts(data)
    except (OSError, ValueError):
        return False
    return (facts.width, facts.height) == (width, height) and (facts.has_alpha if alpha else True)


def _slice_master(data: bytes) -> tuple[bytes, ...]:
    with Image.open(BytesIO(data)) as image:
        image.load()
        if image.size != (2400, 3440):
            raise ValueError("character master sheet must be 2400x3440")
        outputs: list[bytes] = []
        for row in range(5):
            strip = image.crop((0, row * 688, 2400, (row + 1) * 688))
            stream = BytesIO()
            strip.save(stream, format="PNG", compress_level=9, optimize=False)
            outputs.append(stream.getvalue())
        return tuple(outputs)


def _compose_master_rows(source_bytes: Sequence[bytes]) -> tuple[bytes, int, int]:
    if len(source_bytes) != len(_STATES):
        raise ValueError("character master requires exactly five source strips")
    master = Image.new("RGBA", (2400, 3440), (0, 0, 0, 0))
    for row, data in enumerate(source_bytes):
        facts = inspect_image(data, expected_media_type="image/png")
        if (facts.width, facts.height) != (2400, 800):
            raise ValueError("character master source strip must be 2400x800")
        fitted, _validation = remap_canonical_grid(
            data,
            width=2400,
            height=688,
            contract=GridContract(rows=1, columns=4, gutter=8, anchor="bottom"),
        )
        with Image.open(BytesIO(fitted)) as image:
            image.load()
            master.alpha_composite(image.convert("RGBA"), (0, row * 688))
    alpha = master.getchannel("A").tobytes()
    transparent_pixels = sum(value < 255 for value in alpha)
    nontransparent_pixels = sum(value > 0 for value in alpha)
    if transparent_pixels == 0 or nontransparent_pixels == 0:
        raise ValueError("character master must contain nontrivial alpha")
    output = BytesIO()
    master.save(output, format="PNG", compress_level=9, optimize=False)
    return output.getvalue(), transparent_pixels, nontransparent_pixels


def _source_hashes_match(sidecar: dict[str, object], expected: list[dict[str, str]]) -> bool:
    params = sidecar.get("params")
    transparency = params.get("transparency") if isinstance(params, dict) else None
    return isinstance(transparency, dict) and transparency.get("source_hashes") == expected


def _source_hash_matches(sidecar: dict[str, object], expected: str) -> bool:
    params = sidecar.get("params")
    transparency = params.get("transparency") if isinstance(params, dict) else None
    return isinstance(transparency, dict) and transparency.get("source_sha256") == expected


def _metadata_field(sidecar: Mapping[str, Any], key: str) -> object:
    params = sidecar.get("params")
    metadata = params.get("metadata") if isinstance(params, Mapping) else None
    return metadata.get(key) if isinstance(metadata, Mapping) else None


def _valid_character_state_grid(path: Path) -> bool:
    try:
        validate_canonical_grid(
            path.read_bytes(), GridContract(rows=1, columns=4, gutter=8, anchor="bottom")
        )
    except (OSError, ValueError):
        return False
    return True


def _valid_transparency_cache(
    path: Path,
    sidecar: dict[str, Any],
    *,
    raw_path: Path,
    mode: object,
    width: int,
    height: int,
    contract: GridContract | None = None,
    expected_metadata: Mapping[str, object] | None = None,
) -> bool:
    if not _exact_image(path, width, height, alpha=True):
        return False
    try:
        canonical = path.read_bytes()
        raw = raw_path.read_bytes()
    except OSError:
        return False
    params = sidecar.get("params")
    transparency = params.get("transparency") if isinstance(params, dict) else None
    validation = sidecar.get("validation")
    artifact = sidecar.get("artifact")
    if not isinstance(transparency, dict) or not isinstance(validation, dict):
        return False
    retained = transparency.get("retained_raw_path")
    if not isinstance(retained, str):
        return False
    retained_path = Path(retained)
    if not retained_path.is_absolute():
        retained_path = path.parent / retained_path
    valid = (
        transparency.get("mode") == str(mode)
        and retained_path.resolve() == raw_path.resolve()
        and transparency.get("raw_sha256") == sha256_hex(raw)
        and isinstance(artifact, dict)
        and transparency.get("output_sha256") == artifact.get("sha256")
        and validation.get("alpha_nontrivial") is True
        and validation.get("dimensions_preserved") is True
        and validation.get("output_width") == width
        and validation.get("output_height") == height
        and isinstance(validation.get("transparent_pixels"), int)
        and int(validation["transparent_pixels"]) > 0
        and isinstance(validation.get("nontransparent_pixels"), int)
        and int(validation["nontransparent_pixels"]) > 0
    )
    if not valid:
        return False
    if not _asset_metadata_matches(
        sidecar,
        expected=expected_metadata,
        contract=contract,
        width=width,
        height=height,
    ):
        return False
    per_cell_contract = (
        expected_metadata.get("per_cell_generation")
        if isinstance(expected_metadata, Mapping)
        else None
    )
    if isinstance(per_cell_contract, Mapping) and not _valid_per_cell_transparency_evidence(
        raw=raw,
        canonical=canonical,
        canonical_sidecar=sidecar,
        mode=mode,
        contract=per_cell_contract,
        width=width,
        height=height,
    ):
        return False
    isolated_view_contract = (
        expected_metadata.get("isolated_view_fallback")
        if isinstance(expected_metadata, Mapping)
        else None
    )
    if (
        isinstance(isolated_view_contract, Mapping)
        and str(mode) == str(TransparencyMode.CHROMA)
        and not _valid_isolated_view_transparency_evidence(
            raw=raw,
            canonical=canonical,
            canonical_sidecar=sidecar,
            mode=mode,
            contract=isolated_view_contract,
            width=width,
            height=height,
        )
    ):
        return False
    # The per-cell and isolated-view paths above re-derive the canonical bytes, so a changed
    # matte already invalidates them. The plain chroma path compares digests only, so it must
    # bind the matte version explicitly or a pre-existing artifact outlives the matte that made
    # it. Sidecars written before this record carry no version and correctly fail closed.
    if (
        str(mode) == str(TransparencyMode.CHROMA)
        and not isinstance(per_cell_contract, Mapping)
        and not isinstance(isolated_view_contract, Mapping)
        and transparency.get("matte_version") != CHROMA_MATTE_VERSION
    ):
        return False
    if contract is not None:
        try:
            validate_canonical_grid(canonical, contract)
        except (OSError, ValueError):
            return False
        normalization = validation.get("grid_normalization")
        processor = transparency.get("processor")
        if (
            not isinstance(processor, Mapping)
            or processor.get("version") != GRID_NORMALIZATION_VERSION
            or transparency.get("grid_normalization") != normalization
            or not _valid_grid_normalization_evidence(
                normalization,
                canonical=canonical,
                raw=raw,
                width=width,
                height=height,
                contract=contract,
            )
        ):
            return False
    raw_sidecar_path = Path(f"{raw_path}.meta.json")
    if raw_sidecar_path.is_file():
        try:
            raw_sidecar_value = json.loads(raw_sidecar_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
    else:
        raw_sidecar_value = None
    raw_fallback = (
        _fallback_record_from_raw_sidecar(raw_sidecar_value)
        if isinstance(raw_sidecar_value, dict)
        else None
    )
    canonical_tileset_material = transparency.get("tileset_material_synthesis")
    raw_tileset_material = (
        _tileset_material_fallback_from_sidecar(raw_sidecar_value)
        if isinstance(raw_sidecar_value, dict)
        else None
    )
    if canonical_tileset_material is not None or raw_tileset_material is not None:
        # Full verification needs the world/template contract and is owned by
        # `_tileset_material_resume_record` before this generic cache path.
        return False
    canonical_per_cell = transparency.get("per_cell_generation")
    raw_per_cell = (
        _per_cell_record_from_raw_sidecar(raw_sidecar_value)
        if isinstance(raw_sidecar_value, dict)
        else None
    )
    if canonical_per_cell is not None or raw_per_cell is not None:
        recorded_theme = (
            canonical_per_cell.get("theme_identity")
            if isinstance(canonical_per_cell, Mapping)
            else None
        )
        return (
            contract is not None
            and isinstance(canonical_per_cell, Mapping)
            and canonical_per_cell == raw_per_cell
            and _valid_per_cell_fallback_cache(
                composite=path,
                retained_raw=raw_path,
                fallback=canonical_per_cell,
                contract=contract,
                width=width,
                height=height,
                expected_metadata=expected_metadata,
                theme_identity=(
                    cast(Mapping[str, object], recorded_theme)
                    if isinstance(recorded_theme, Mapping)
                    else None
                ),
            )
        )
    canonical_fallback = transparency.get("isolated_view_fallback")
    if canonical_fallback is None and raw_fallback is None:
        return True
    return (
        contract is not None
        and isinstance(canonical_fallback, Mapping)
        and canonical_fallback == raw_fallback
        and _valid_isolated_view_fallback_cache(
            composite=path,
            retained_raw=raw_path,
            fallback=canonical_fallback,
            contract=contract,
            width=width,
            height=height,
            expected_metadata=expected_metadata,
        )
    )


def _valid_isolated_view_transparency_evidence(
    *,
    raw: bytes,
    canonical: bytes,
    canonical_sidecar: Mapping[str, Any],
    mode: object,
    contract: Mapping[str, object],
    width: int,
    height: int,
) -> bool:
    if str(mode) != str(TransparencyMode.CHROMA):
        return False
    try:
        validate_isolated_view_source(raw, width=width, height=height)
        validate_isolated_view_alpha(canonical)
    except (OSError, ValueError):
        return False
    params = canonical_sidecar.get("params")
    transparency = params.get("transparency") if isinstance(params, Mapping) else None
    validation = canonical_sidecar.get("validation")
    if not isinstance(transparency, Mapping) or not isinstance(validation, Mapping):
        return False
    cleanup = transparency.get("isolated_view_alpha_cleanup")
    validation_cleanup = validation.get("isolated_view_alpha_cleanup")
    fit = transparency.get("isolated_view_subject_fit")
    validation_fit = validation.get("isolated_view_subject_fit")
    processor = transparency.get("processor")
    if (
        contract.get("version") != _ISOLATED_VIEW_FALLBACK_VERSION
        or not _valid_fallback_record_digest(contract)
        or not isinstance(cleanup, Mapping)
        or cleanup != validation_cleanup
        or not _valid_per_cell_cleanup_record(cleanup, width=width, height=height)
        or (fit is None) != (validation_fit is None)
        or (fit is not None and (not isinstance(fit, Mapping) or fit != validation_fit))
        or not isinstance(processor, Mapping)
    ):
        return False
    try:
        normalization_input, _alpha = apply_chroma_transparency(raw)
        expected, expected_validation, expected_fit, expected_cleanup = (
            _normalize_isolated_fallback_alpha(normalization_input, contract)
        )
    except (OSError, ValueError):
        return False
    expected_kind = f"chroma-key+{ISOLATED_ALPHA_CLEANUP_VERSION}"
    if expected_fit is not None:
        expected_kind = f"{expected_kind}+{ISOLATED_SUBJECT_FIT_VERSION}"
    return (
        canonical == expected
        and dict(cleanup) == expected_cleanup
        and (
            (fit is None and expected_fit is None)
            or (isinstance(fit, Mapping) and expected_fit is not None and dict(fit) == expected_fit)
        )
        and processor.get("kind") == expected_kind
        and processor.get("version")
        == (
            ISOLATED_SUBJECT_FIT_VERSION
            if expected_fit is not None
            else ISOLATED_ALPHA_CLEANUP_VERSION
        )
        and all(validation.get(key) == value for key, value in expected_validation.items())
    )


def _valid_per_cell_transparency_evidence(
    *,
    raw: bytes,
    canonical: bytes,
    canonical_sidecar: Mapping[str, Any],
    mode: object,
    contract: Mapping[str, object],
    width: int,
    height: int,
) -> bool:
    try:
        raw_validation = validate_isolated_view_source(
            raw,
            width=width,
            height=height,
            allow_recoverable_inset=True,
        )
        _validate_recoverable_per_cell_scale(
            raw_validation,
            contract,
            bbox_key="isolated_view_bbox",
            height=height,
        )
        canonical_validation = validate_isolated_view_alpha(canonical)
        _validate_per_cell_scale(
            canonical_validation,
            contract,
            bbox_key="isolated_view_alpha_bbox",
            height=height,
        )
    except (OSError, ValueError):
        return False

    params = canonical_sidecar.get("params")
    transparency = params.get("transparency") if isinstance(params, Mapping) else None
    validation = canonical_sidecar.get("validation")
    if not isinstance(transparency, Mapping) or not isinstance(validation, Mapping):
        return False
    cleanup = transparency.get("per_cell_alpha_cleanup")
    validation_cleanup = validation.get("per_cell_alpha_cleanup")
    fit = transparency.get("per_cell_subject_fit")
    validation_fit = validation.get("per_cell_subject_fit")
    if (
        not isinstance(cleanup, Mapping)
        or cleanup != validation_cleanup
        or not _valid_per_cell_cleanup_record(cleanup, width=width, height=height)
        or (fit is None) != (validation_fit is None)
        or (fit is not None and (not isinstance(fit, Mapping) or fit != validation_fit))
    ):
        return False

    try:
        if str(mode) == str(TransparencyMode.CHROMA):
            normalization_input, _alpha = apply_chroma_transparency(raw)
            expected, expected_validation, expected_fit, expected_cleanup = (
                _normalize_per_cell_alpha(normalization_input, contract)
            )
            return (
                canonical == expected
                and dict(cleanup) == expected_cleanup
                and (
                    (fit is None and expected_fit is None)
                    or (
                        isinstance(fit, Mapping)
                        and expected_fit is not None
                        and dict(fit) == expected_fit
                    )
                )
                and validation.get("per_cell_source_height_fraction")
                == expected_validation.get("per_cell_source_height_fraction")
                and validation.get("per_cell_scale_normalization_required")
                == expected_validation.get("per_cell_scale_normalization_required")
                and validation.get("per_cell_inset_normalization_required")
                == expected_validation.get("per_cell_inset_normalization_required")
                and validation.get("per_cell_placement_normalization_required")
                == expected_validation.get("per_cell_placement_normalization_required")
                and validation.get("per_cell_fit_required")
                == expected_validation.get("per_cell_fit_required")
                and validation.get("per_cell_fit_reasons")
                == expected_validation.get("per_cell_fit_reasons")
            )
    except (OSError, ValueError):
        return False

    if str(mode) != str(TransparencyMode.AI):
        return False
    if not _valid_ai_per_cell_cleanup_evidence(
        cleanup,
        raw=raw,
        canonical=canonical,
        canonical_sidecar=canonical_sidecar,
        fit=fit if isinstance(fit, Mapping) else None,
    ):
        return False
    if fit is None:
        return (
            cleanup.get("output_sha256") == sha256_hex(canonical)
            and cleanup.get("output_bytes") == len(canonical)
            and validation.get("per_cell_fit_required") is False
        )
    if not isinstance(fit, Mapping):
        return False
    if not _valid_per_cell_fit_geometry(
        fit,
        cleanup=cleanup,
        canonical_validation=canonical_validation,
        contract=contract,
        width=width,
        height=height,
    ):
        return False
    payload = {key: value for key, value in fit.items() if key != "sha256"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return fit.get("sha256") == sha256_hex(encoded) and _valid_ai_per_cell_fit_evidence(
        fit,
        raw=raw,
        canonical=canonical,
        canonical_sidecar=canonical_sidecar,
        width=width,
        height=height,
        cleanup=cleanup,
        contract=contract,
    )


def _valid_per_cell_cleanup_record(
    cleanup: Mapping[str, object],
    *,
    width: int,
    height: int,
) -> bool:
    payload = {key: value for key, value in cleanup.items() if key != "sha256"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    input_bbox = _strict_bbox(cleanup.get("input_bbox"), width=width, height=height)
    output_bbox = _strict_bbox(cleanup.get("output_bbox"), width=width, height=height)
    removed_coordinates = cleanup.get("removed_coordinates")
    removed_pixels = cleanup.get("removed_pixels")
    dominant_pixels = cleanup.get("dominant_pixels")
    removed_fraction = cleanup.get("removed_fraction_of_dominant")
    thresholds = cleanup.get("thresholds")
    input_components = cleanup.get("input_components")
    output_components = cleanup.get("output_components")
    input_count = cleanup.get("input_component_count")
    output_count = cleanup.get("output_component_count")
    removed_count = cleanup.get("removed_component_count")
    if (
        cleanup.get("version") != ISOLATED_ALPHA_CLEANUP_VERSION
        or cleanup.get("sha256") != sha256_hex(encoded)
        or cleanup.get("canvas") != [width, height]
        or not _valid_sha256(cleanup.get("input_sha256"))
        or not _positive_int(cleanup.get("input_bytes"))
        or not _valid_sha256(cleanup.get("output_sha256"))
        or not _positive_int(cleanup.get("output_bytes"))
        or input_bbox is None
        or output_bbox is None
        or isinstance(removed_pixels, bool)
        or not isinstance(removed_pixels, int)
        or not 0 <= removed_pixels <= 16
        or isinstance(dominant_pixels, bool)
        or not isinstance(dominant_pixels, int)
        or dominant_pixels <= 0
        or isinstance(removed_fraction, bool)
        or not isinstance(removed_fraction, int | float)
        or float(removed_fraction) != round(removed_pixels / dominant_pixels, 12)
        or float(removed_fraction) > 0.001
        or thresholds
        != {
            "connectivity": 8,
            "alpha_positive_minimum": 1,
            "maximum_removed_pixels": 16,
            "maximum_removed_fraction_of_dominant": 0.001,
        }
        or not isinstance(input_components, list)
        or not isinstance(output_components, list)
        or isinstance(input_count, bool)
        or not isinstance(input_count, int)
        or input_count != len(input_components)
        or isinstance(output_count, bool)
        or not isinstance(output_count, int)
        or output_count != len(output_components)
        or isinstance(removed_count, bool)
        or not isinstance(removed_count, int)
        or removed_count != input_count - output_count
        or not isinstance(removed_coordinates, list)
        or len(removed_coordinates) != removed_pixels
        or cleanup.get("physical_border_clear_after_cleanup") is not True
        or cleanup.get("interior_components_preserved") is not True
    ):
        return False
    parsed_coordinates: list[tuple[int, int]] = []
    for coordinate in removed_coordinates:
        if (
            not isinstance(coordinate, list)
            or len(coordinate) != 2
            or any(isinstance(value, bool) or not isinstance(value, int) for value in coordinate)
        ):
            return False
        x, y = cast(list[int], coordinate)
        if not (0 <= x < width and 0 <= y < height):
            return False
        if x not in {0, width - 1} and y not in {0, height - 1}:
            return False
        parsed_coordinates.append((x, y))
    if parsed_coordinates != sorted(
        set(parsed_coordinates),
        key=lambda item: item[1] * width + item[0],
    ):
        return False
    if not _valid_cleanup_components(
        input_components,
        width=width,
        height=height,
        expected_dominant_pixels=dominant_pixels,
        allow_border=True,
    ) or not _valid_cleanup_components(
        output_components,
        width=width,
        height=height,
        expected_dominant_pixels=dominant_pixels,
        allow_border=False,
    ):
        return False
    input_border = cleanup.get("input_border_flags")
    output_border = cleanup.get("output_border_flags")
    expected_sides = ("left", "top", "right", "bottom")
    return (
        isinstance(input_border, Mapping)
        and set(input_border) == set(expected_sides)
        and all(isinstance(input_border[side], bool) for side in expected_sides)
        and isinstance(output_border, Mapping)
        and set(output_border) == set(expected_sides)
        and all(output_border[side] is False for side in expected_sides)
    )


def _valid_cleanup_components(
    components: list[object],
    *,
    width: int,
    height: int,
    expected_dominant_pixels: int,
    allow_border: bool,
) -> bool:
    if not components:
        return False
    for index, component in enumerate(components):
        if not isinstance(component, Mapping):
            return False
        bbox = _strict_bbox(component.get("bbox"), width=width, height=height)
        pixels = component.get("pixels")
        border_sides = component.get("border_sides")
        if (
            bbox is None
            or isinstance(pixels, bool)
            or not isinstance(pixels, int)
            or pixels <= 0
            or component.get("order") != index
            or component.get("dominant") is not (index == 0)
            or not isinstance(border_sides, list)
            or any(side not in {"left", "top", "right", "bottom"} for side in border_sides)
            or len(border_sides) != len(set(cast(list[str], border_sides)))
            or component.get("touches_border") is not bool(border_sides)
            or (not allow_border and border_sides)
            or (index == 0 and pixels != expected_dominant_pixels)
            or (index == 0 and border_sides)
        ):
            return False
    return True


def _valid_per_cell_fit_geometry(
    fit: Mapping[str, object],
    *,
    cleanup: Mapping[str, object],
    canonical_validation: Mapping[str, object],
    contract: Mapping[str, object],
    width: int,
    height: int,
) -> bool:
    source_bbox = _strict_bbox(fit.get("source_bbox"), width=width, height=height)
    original_bbox = _strict_bbox(fit.get("original_bbox"), width=width, height=height)
    target_bbox = _strict_bbox(fit.get("target_bbox"), width=width, height=height)
    scale = contract.get("scale_contract")
    minimum = scale.get("minimum_height_fraction") if isinstance(scale, Mapping) else None
    maximum = scale.get("maximum_height_fraction") if isinstance(scale, Mapping) else None
    if (
        source_bbox is None
        or original_bbox is None
        or target_bbox is None
        or isinstance(minimum, bool)
        or not isinstance(minimum, int | float)
        or isinstance(maximum, bool)
        or not isinstance(maximum, int | float)
    ):
        return False
    gutter = max(2, min(width, height) // 20)
    source_width = source_bbox[2] - source_bbox[0]
    source_height = source_bbox[3] - source_bbox[1]
    source_fraction = source_height / height
    available_width = width - gutter * 2
    available_height = height - gutter * 2
    maximum_height = min(available_height, max(1, int(height * float(maximum))))
    scale_factor = min(
        1.0,
        available_width / source_width,
        maximum_height / source_height,
    )
    target_width = max(1, min(available_width, round(source_width * scale_factor)))
    target_height = max(1, min(maximum_height, round(source_height * scale_factor)))
    target_left = (width - target_width) // 2
    anchor = contract.get("anchor")
    target_top = (
        (height - target_height) // 2
        if anchor == "center"
        else height - gutter - target_height
        if anchor == "bottom"
        else None
    )
    if target_top is None:
        return False
    target_fraction = (target_bbox[3] - target_bbox[1]) / height
    placement = fit.get("placement")
    target_size = fit.get("target_size")
    source_margins = {
        "left": source_bbox[0],
        "top": source_bbox[1],
        "right": width - source_bbox[2],
        "bottom": height - source_bbox[3],
    }
    original_margins = {
        "left": original_bbox[0],
        "top": original_bbox[1],
        "right": width - original_bbox[2],
        "bottom": height - original_bbox[3],
    }
    source_intrusion = {side: margin < gutter for side, margin in source_margins.items()}
    original_intrusion = {side: margin < gutter for side, margin in original_margins.items()}
    side_order = ("left", "top", "right", "bottom")
    transform = fit.get("transform")
    return (
        fit.get("version") == ISOLATED_SUBJECT_FIT_VERSION
        and fit.get("applied") is True
        and fit.get("canvas") == [width, height]
        and fit.get("cleanup") == cleanup
        and fit.get("input_sha256") == cleanup.get("input_sha256")
        and fit.get("input_bytes") == cleanup.get("input_bytes")
        and fit.get("cleaned_input_sha256") == cleanup.get("output_sha256")
        and fit.get("cleaned_input_bytes") == cleanup.get("output_bytes")
        and fit.get("original_bbox") == cleanup.get("input_bbox")
        and fit.get("source_bbox") == cleanup.get("output_bbox")
        and fit.get("source_height_fraction") == round(source_fraction, 6)
        and fit.get("target_bbox") == canonical_validation.get("isolated_view_alpha_bbox")
        and fit.get("target_height_fraction") == round(target_fraction, 6)
        and fit.get("minimum_height_fraction") == float(minimum)
        and fit.get("maximum_height_fraction") == float(maximum)
        and fit.get("scale_factor") == round(scale_factor, 9)
        and placement == [target_left, target_top]
        and target_size == [target_width, target_height]
        and target_bbox[0] >= target_left
        and target_bbox[1] >= target_top
        and target_bbox[2] <= target_left + target_width
        and target_bbox[3] <= target_top + target_height
        and fit.get("anchor") == anchor
        and fit.get("anchor_coordinate") == (height // 2 if anchor == "center" else height - gutter)
        and fit.get("component_contract_sha256") == contract.get("sha256")
        and fit.get("resample") == "lanczos"
        and fit.get("premultiplied_alpha") is True
        and fit.get("aspect_preserved") is True
        and fit.get("role_anchor_preserved") is True
        and fit.get("original_margins") == original_margins
        and fit.get("source_margins") == source_margins
        and fit.get("original_inset_intrusion") == original_intrusion
        and fit.get("source_inset_intrusion") == source_intrusion
        and fit.get("original_inset_intrusion_sides")
        == [side for side in side_order if original_intrusion[side]]
        and fit.get("source_inset_intrusion_sides")
        == [side for side in side_order if source_intrusion[side]]
        and transform
        == {
            "crop_bbox": list(source_bbox),
            "scale_factor": round(scale_factor, 9),
            "target_size": [target_width, target_height],
            "placement": [target_left, target_top],
            "resample": "lanczos",
            "premultiplied_alpha": True,
        }
        and source_fraction >= float(minimum)
        and _valid_sha256(fit.get("input_sha256"))
        and _positive_int(fit.get("input_bytes"))
    )


def _valid_ai_per_cell_cleanup_evidence(
    cleanup: Mapping[str, object],
    *,
    raw: bytes,
    canonical: bytes,
    canonical_sidecar: Mapping[str, Any],
    fit: Mapping[str, object] | None,
) -> bool:
    params = canonical_sidecar.get("params")
    transparency = params.get("transparency") if isinstance(params, Mapping) else None
    removal = transparency.get("removal") if isinstance(transparency, Mapping) else None
    provenance = removal.get("provenance") if isinstance(removal, Mapping) else None
    artifact = provenance.get("artifact") if isinstance(provenance, Mapping) else None
    inputs = provenance.get("inputs") if isinstance(provenance, Mapping) else None
    removal_validation = provenance.get("validation") if isinstance(provenance, Mapping) else None
    return (
        isinstance(removal, Mapping)
        and removal.get("mask_used") is False
        and isinstance(provenance, Mapping)
        and removal.get("provider")
        == provenance.get("provider")
        == canonical_sidecar.get("provider")
        and removal.get("model") == provenance.get("model") == canonical_sidecar.get("model")
        and removal.get("attempts")
        == provenance.get("attempts")
        == canonical_sidecar.get("attempts")
        and isinstance(artifact, Mapping)
        and artifact.get("media_type") == "image/png"
        and _valid_sha256(artifact.get("sha256"))
        and _positive_int(artifact.get("bytes"))
        and isinstance(inputs, list)
        and len(inputs) == 1
        and isinstance(inputs[0], Mapping)
        and inputs[0].get("sha256") == sha256_hex(raw)
        and inputs[0].get("bytes") == len(raw)
        and isinstance(removal_validation, Mapping)
        and removal_validation.get("per_cell_alpha_cleanup") == cleanup
        and removal_validation.get("per_cell_fit_input_sha256") == cleanup.get("input_sha256")
        and removal_validation.get("per_cell_fit_input_bytes") == cleanup.get("input_bytes")
        and removal_validation.get("isolated_view_alpha_bbox") == cleanup.get("output_bbox")
        and (
            (
                fit is None
                and cleanup.get("output_sha256") == sha256_hex(canonical)
                and cleanup.get("output_bytes") == len(canonical)
            )
            or (
                fit is not None
                and fit.get("cleanup") == cleanup
                and fit.get("input_sha256") == cleanup.get("input_sha256")
                and fit.get("input_bytes") == cleanup.get("input_bytes")
                and fit.get("cleaned_input_sha256") == cleanup.get("output_sha256")
                and fit.get("cleaned_input_bytes") == cleanup.get("output_bytes")
            )
        )
    )


def _valid_ai_per_cell_fit_evidence(
    fit: Mapping[str, object],
    *,
    raw: bytes,
    canonical: bytes,
    canonical_sidecar: Mapping[str, Any],
    width: int,
    height: int,
    cleanup: Mapping[str, object],
    contract: Mapping[str, object],
) -> bool:
    params = canonical_sidecar.get("params")
    transparency = params.get("transparency") if isinstance(params, Mapping) else None
    removal = transparency.get("removal") if isinstance(transparency, Mapping) else None
    provenance = removal.get("provenance") if isinstance(removal, Mapping) else None
    artifact = provenance.get("artifact") if isinstance(provenance, Mapping) else None
    inputs = provenance.get("inputs") if isinstance(provenance, Mapping) else None
    removal_validation = provenance.get("validation") if isinstance(provenance, Mapping) else None
    source_bbox = _strict_bbox(fit.get("source_bbox"), width=width, height=height)
    source_fraction = (
        (source_bbox[3] - source_bbox[1]) / height if source_bbox is not None else None
    )
    removal_fraction = (
        removal_validation.get("per_cell_subject_height_fraction")
        if isinstance(removal_validation, Mapping)
        else None
    )
    scale = contract.get("scale_contract")
    maximum = scale.get("maximum_height_fraction") if isinstance(scale, Mapping) else None
    if isinstance(maximum, bool) or not isinstance(maximum, int | float):
        return False
    scale_normalization_required = source_fraction is not None and source_fraction > float(maximum)
    return (
        isinstance(removal, Mapping)
        and removal.get("mask_used") is False
        and isinstance(provenance, Mapping)
        and removal.get("provider")
        == provenance.get("provider")
        == canonical_sidecar.get("provider")
        and removal.get("model") == provenance.get("model") == canonical_sidecar.get("model")
        and removal.get("attempts")
        == provenance.get("attempts")
        == canonical_sidecar.get("attempts")
        and isinstance(artifact, Mapping)
        and artifact.get("media_type") == "image/png"
        and _valid_sha256(artifact.get("sha256"))
        and _positive_int(artifact.get("bytes"))
        and fit.get("source_processor") == "ai-background-removal"
        and fit.get("removal_provenance_sha256") == _canonical_mapping_sha256(provenance)
        and fit.get("removal_artifact_sha256") == artifact.get("sha256")
        and fit.get("removal_artifact_bytes") == artifact.get("bytes")
        and isinstance(inputs, list)
        and len(inputs) == 1
        and isinstance(inputs[0], Mapping)
        and inputs[0].get("sha256") == sha256_hex(raw)
        and inputs[0].get("bytes") == len(raw)
        and isinstance(removal_validation, Mapping)
        and removal_validation.get("per_cell_alpha_cleanup") == cleanup
        and removal_validation.get("per_cell_fit_input_sha256") == fit.get("input_sha256")
        and removal_validation.get("per_cell_fit_input_bytes") == fit.get("input_bytes")
        and removal_validation.get("isolated_view_alpha_bbox") == fit.get("source_bbox")
        and isinstance(source_fraction, float)
        and not isinstance(removal_fraction, bool)
        and isinstance(removal_fraction, int | float)
        and math.isclose(
            float(removal_fraction),
            source_fraction,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        and removal_validation.get("per_cell_scale_normalization_required")
        is scale_normalization_required
        and removal_validation.get("per_cell_scale_contract_satisfied")
        is not scale_normalization_required
        and removal_validation.get("output_width") == width
        and removal_validation.get("output_height") == height
        and fit.get("output_sha256") == sha256_hex(canonical)
        and fit.get("output_bytes") == len(canonical)
    )


def _strict_bbox(
    value: object,
    *,
    width: int,
    height: int,
) -> tuple[int, int, int, int] | None:
    if (
        not isinstance(value, list)
        or len(value) != 4
        or any(isinstance(item, bool) or not isinstance(item, int) for item in value)
    ):
        return None
    left, top, right, bottom = cast(list[int], value)
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        return None
    return left, top, right, bottom


def _valid_grid_normalization_evidence(
    value: object,
    *,
    canonical: bytes,
    raw: bytes,
    width: int,
    height: int,
    contract: GridContract,
) -> bool:
    if not isinstance(value, Mapping):
        return False
    transforms = value.get("transforms")
    cell_width, cell_height = contract.cell_size(width, height)
    if (
        value.get("version") != GRID_NORMALIZATION_VERSION
        or value.get("input_sha256") != sha256_hex(raw)
        or value.get("input_bytes") != len(raw)
        or value.get("input_role") != "retained-raw-artifact"
        or not _valid_sha256(value.get("normalization_input_sha256"))
        or not _positive_int(value.get("normalization_input_bytes"))
        or value.get("output_sha256") != sha256_hex(canonical)
        or value.get("output_bytes") != len(canonical)
        or value.get("source_canvas") != [width, height]
        or value.get("target_canvas") != [width, height]
        or value.get("rows") != contract.rows
        or value.get("columns") != contract.columns
        or value.get("gutter") != contract.gutter
        or value.get("topology") != contract.topology
        or value.get("transform_count") != contract.rows * contract.columns
        or not isinstance(transforms, list)
        or len(transforms) != contract.rows * contract.columns
        or value.get("exact_gutters_cleared") is not True
        or value.get("cross_cell_contamination") is not False
        or value.get("semantic_contract") != grid_semantic_contract(contract, width, height)
        or (contract.topology == "tileset" and value.get("semantic_mask") != "tileset-12x4-v1")
    ):
        return False
    for index, transform in enumerate(transforms):
        if not isinstance(transform, Mapping):
            return False
        row, column = divmod(index, contract.columns)
        source_bbox = transform.get("source_bbox")
        target_bbox = transform.get("target_bbox")
        if (
            transform.get("row") != row
            or transform.get("column") != column
            or transform.get("aspect_preserved") is not True
            or transform.get("anchor") != contract.anchor
            or transform.get("semantic_role") != grid_semantic_role(contract, row, column)
            or not _valid_cell_bbox(source_bbox, cell_width, cell_height, gutter=0)
            or not _valid_cell_bbox(
                target_bbox,
                cell_width,
                cell_height,
                gutter=contract.gutter,
            )
        ):
            return False
        source = cast(list[int], source_bbox)
        target = cast(list[int], target_bbox)
        source_size = [source[2] - source[0], source[3] - source[1]]
        target_size = [target[2] - target[0], target[3] - target[1]]
        if (
            transform.get("source_size") != source_size
            or transform.get("target_size") != target_size
            or transform.get("resampled") != (source_size != target_size)
            or abs(target_size[0] * source_size[1] - target_size[1] * source_size[0])
            > source_size[0] + source_size[1]
        ):
            return False
    return True


def _bind_grid_normalization_to_raw(value: dict[str, object], *, raw: bytes) -> dict[str, object]:
    """Bind normalization evidence to the retained provider artifact bytes."""

    return {
        **value,
        "normalization_input_sha256": value.get("input_sha256"),
        "normalization_input_bytes": value.get("input_bytes"),
        "input_sha256": sha256_hex(raw),
        "input_bytes": len(raw),
        "input_role": "retained-raw-artifact",
    }


def _valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _positive_int(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value > 0


def _fallback_record_from_raw_sidecar(
    sidecar: Mapping[str, Any],
) -> Mapping[str, object] | None:
    params = sidecar.get("params")
    metadata = params.get("metadata") if isinstance(params, Mapping) else None
    if not isinstance(metadata, Mapping) or "isolated_view_fallback" not in metadata:
        return None
    value = metadata.get("isolated_view_fallback")
    if isinstance(value, Mapping) and "view_index" in value and "components" not in value:
        # A per-view request contract is component cache metadata, not a
        # resumable parent fallback record.
        return None
    return value if isinstance(value, Mapping) else {}


def _per_cell_record_from_raw_sidecar(
    sidecar: Mapping[str, Any],
) -> Mapping[str, object] | None:
    params = sidecar.get("params")
    metadata = params.get("metadata") if isinstance(params, Mapping) else None
    if not isinstance(metadata, Mapping) or "per_cell_generation" not in metadata:
        return None
    value = metadata.get("per_cell_generation")
    if isinstance(value, Mapping) and "cell_index" in value and "components" not in value:
        # Component request contracts and parent fallback records intentionally
        # share the provenance key; only the parent record owns resume state.
        return None
    return value if isinstance(value, Mapping) else {}


def _tileset_material_fallback_from_sidecar(
    sidecar: Mapping[str, Any],
) -> Mapping[str, object] | None:
    params = sidecar.get("params")
    if not isinstance(params, Mapping):
        return None
    metadata = params.get("metadata")
    metadata_value: object | None = None
    if isinstance(metadata, Mapping) and "tileset_material_synthesis" in metadata:
        metadata_value = metadata.get("tileset_material_synthesis")
    transparency = params.get("transparency")
    transparency_value: object | None = None
    if isinstance(transparency, Mapping) and "tileset_material_synthesis" in transparency:
        transparency_value = transparency.get("tileset_material_synthesis")
    if metadata_value is not None and transparency_value is not None:
        if metadata_value != transparency_value:
            return {}
        return metadata_value if isinstance(metadata_value, Mapping) else {}
    value = metadata_value if metadata_value is not None else transparency_value
    if value is not None:
        return value if isinstance(value, Mapping) else {}
    return None


def _tileset_material_parent_from_component_sidecar(
    sidecar: Mapping[str, Any],
) -> Mapping[str, object] | None:
    params = sidecar.get("params")
    metadata = params.get("metadata") if isinstance(params, Mapping) else None
    if not isinstance(metadata, Mapping) or "tileset_material_parent" not in metadata:
        return None
    value = metadata.get("tileset_material_parent")
    return value if isinstance(value, Mapping) else {}


async def _tileset_material_resume_record(
    context: StageContext,
    spec: _ImageSpec,
    *,
    contract: GridContract | None,
    mode: object | None,
    image_provider: str,
    image_model: str,
    theme_identity: Mapping[str, object] | None,
    style: _StyleAnchorContext | None,
) -> Mapping[str, object] | None:
    if (
        spec.stage != "tileset"
        or not spec.transparent
        or (spec.width, spec.height) != (2400, 800)
        or contract is None
        or contract.topology != "tileset"
        or mode is None
    ):
        return None
    raw_path = _retained_raw_path(spec)
    material_sidecar_paths: list[Path] = []
    for role in ("fill", "cap", "edge"):
        material = _tileset_material_output(spec.output, role)
        material_raw = material.with_name(f"{material.stem}.raw.png")
        material_sidecar_paths.extend(
            (Path(f"{material_raw}.meta.json"), Path(f"{material}.meta.json"))
        )
    sidecar_paths = (
        Path(f"{raw_path}.meta.json"),
        Path(f"{spec.output}.meta.json"),
        *material_sidecar_paths,
    )
    sidecars: list[dict[str, Any]] = []
    for path in sidecar_paths:
        try:
            raw = await asyncio.to_thread(path.read_text, encoding="utf-8")
            value = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            sidecars.append(value)
    if not sidecars:
        return None
    candidates: list[tuple[Mapping[str, object], Mapping[str, object] | None]] = []
    for sidecar in sidecars:
        fallback = _tileset_material_fallback_from_sidecar(sidecar)
        if fallback is not None:
            parent = fallback.get("parent_contract")
            if isinstance(parent, Mapping):
                candidates.append((parent, fallback))
        parent = _tileset_material_parent_from_component_sidecar(sidecar)
        if parent is not None:
            candidates.append((parent, None))
    compiled = await _read_compiled_theme(context)
    if (compiled.identity if compiled is not None else None) != (
        dict(theme_identity) if theme_identity is not None else None
    ):
        return None
    game = await _read_game_contract(context)
    effective_sheet_prompt_sha256 = sha256_hex(
        _effective_image_prompt(spec, compiled, mode, game).encode()
    )
    theme_directive = _tileset_material_theme_directive(compiled)
    for recorded_parent, fallback in candidates:
        failures = recorded_parent.get("sheet_failures")
        exhaustion = recorded_parent.get("sheet_exhaustion")
        if (
            not _valid_fallback_record_digest(recorded_parent)
            or not _valid_tileset_material_failure_history(failures)
            or not _valid_tileset_sheet_exhaustion(exhaustion)
            or cast(Mapping[str, object], exhaustion).get("request_prompt_sha256")
            != effective_sheet_prompt_sha256
        ):
            continue
        try:
            plan = await _build_tileset_material_plan(
                context,
                spec,
                contract=contract,
                sheet_failures=cast(Sequence[Mapping[str, object]], failures),
                sheet_exhaustion=cast(Mapping[str, object], exhaustion),
                image_provider=image_provider,
                image_model=image_model,
                theme_identity=theme_identity,
                style=style,
                theme_directive=theme_directive,
            )
        except (OSError, ValueError):
            continue
        if plan.parent_contract != recorded_parent:
            continue
        if fallback is not None and await asyncio.to_thread(
            _valid_tileset_material_parent_cache,
            spec,
            contract=contract,
            mode=mode,
            plan=plan,
            fallback=fallback,
        ):
            return {"cache_complete": True}
        return {
            "sheet_failures": [dict(value) for value in cast(list[Mapping[str, object]], failures)],
            "sheet_exhaustion": dict(cast(Mapping[str, object], exhaustion)),
        }
    return None


def _valid_tileset_material_parent_cache(
    spec: _ImageSpec,
    *,
    contract: GridContract,
    mode: object,
    plan: _TilesetMaterialPlan,
    fallback: Mapping[str, object],
) -> bool:
    if (
        fallback.get("version") != TILESET_MATERIAL_SYNTHESIS_VERSION
        or fallback.get("parent_stage") != "tileset"
        or fallback.get("mode") != str(mode)
        or fallback.get("contract") != contract.as_dict(spec.width, spec.height)
        or fallback.get("parent_prompt_sha256") != sha256_hex(spec.prompt.encode())
        or fallback.get("parent_contract") != plan.parent_contract
        or fallback.get("role_order") != ["fill", "cap", "edge"]
        or not _valid_tileset_material_failure_history(fallback.get("sheet_failures"))
        or not _valid_tileset_sheet_exhaustion(fallback.get("sheet_exhaustion"))
        or not _valid_fallback_record_digest(fallback)
    ):
        return False
    raw_path = _retained_raw_path(spec)
    raw_meta_path = Path(f"{raw_path}.meta.json")
    canonical_meta_path = Path(f"{spec.output}.meta.json")
    try:
        raw = raw_path.read_bytes()
        canonical = spec.output.read_bytes()
        raw_meta = json.loads(raw_meta_path.read_text(encoding="utf-8"))
        canonical_meta = json.loads(canonical_meta_path.read_text(encoding="utf-8"))
        wireframe = plan.wireframe.read_bytes()
    except (OSError, json.JSONDecodeError):
        return False
    if (
        not valid_artifact_pair(raw_path, transparency_mode=cast(TransparencyMode, mode))
        or not valid_artifact_pair(spec.output, transparency_mode=cast(TransparencyMode, mode))
        or _tileset_material_fallback_from_sidecar(raw_meta) != fallback
        or _tileset_material_fallback_from_sidecar(canonical_meta) != fallback
        or not _valid_tileset_material_parent_provenance(
            raw_meta,
            canonical_meta,
            spec=spec,
            plan=plan,
            fallback=fallback,
            raw=raw,
            canonical=canonical,
        )
    ):
        return False
    recorded_components = fallback.get("components")
    if not isinstance(recorded_components, list) or len(recorded_components) != 3:
        return False
    fill_path = _tileset_material_output(spec.output, "fill")
    try:
        fill = fill_path.read_bytes()
    except OSError:
        return False
    actual_records: list[dict[str, object]] = []
    for index, role in enumerate(("fill", "cap", "edge")):
        canonical_path = _tileset_material_output(spec.output, role)
        component_raw = canonical_path.with_name(f"{canonical_path.stem}.raw.png")
        reference_paths = [plan.world_concept]
        reference_roles = ["world-concept-style-reference"]
        if role != "fill":
            reference_paths.append(fill_path)
            reference_roles.append("fill-material-style-scale-anchor")
        try:
            bindings = [
                _content_binding_with_provenance(
                    path,
                    path.read_bytes(),
                    role=binding_role,
                )
                for path, binding_role in zip(reference_paths, reference_roles, strict=True)
            ]
        except (OSError, ValueError):
            return False
        component_contract = _tileset_material_component_contract(
            plan,
            role=role,
            prompt=plan.prompts[role],
            reference_bindings=bindings,
            fill_anchor=None if role == "fill" else fill,
        )
        record = _cached_tileset_material_component(
            canonical_path,
            component_raw,
            role=role,
            component_contract=component_contract,
            fill_anchor=None if role == "fill" else fill,
        )
        if record is None or record != recorded_components[index]:
            return False
        actual_records.append(record)
    try:
        cap = _tileset_material_output(spec.output, "cap").read_bytes()
        edge = _tileset_material_output(spec.output, "edge").read_bytes()
        expected_canonical, synthesis = synthesize_tileset_from_materials(
            fill=fill,
            cap=cap,
            edge=edge,
            wireframe=wireframe,
            width=spec.width,
            height=spec.height,
        )
        expected_raw, flattening = flatten_tileset_to_background(
            expected_canonical,
            background_rgb=(
                (255, 0, 255) if str(mode) == str(TransparencyMode.CHROMA) else (128, 128, 128)
            ),
        )
        final_grid = validate_canonical_grid(expected_canonical, contract)
        dependency = tileset_material_dependency_evidence(
            fill=fill,
            cap=cap,
            edge=edge,
        )
        expected_fallback = _tileset_material_fallback_record(
            spec,
            plan=plan,
            contract=contract,
            mode=str(mode),
            sheet_failures=cast(Sequence[Mapping[str, object]], fallback["sheet_failures"]),
            sheet_exhaustion=cast(Mapping[str, object], fallback["sheet_exhaustion"]),
            components=actual_records,
            dependency=dependency,
            synthesis=synthesis,
            flattening=flattening,
            retained_raw=expected_raw,
            canonical=expected_canonical,
            final_grid=final_grid,
        )
    except (OSError, ValueError):
        return False
    return raw == expected_raw and canonical == expected_canonical and fallback == expected_fallback


def _valid_tileset_material_parent_provenance(
    raw_value: Mapping[str, Any],
    canonical_value: Mapping[str, Any],
    *,
    spec: _ImageSpec,
    plan: _TilesetMaterialPlan,
    fallback: Mapping[str, object],
    raw: bytes,
    canonical: bytes,
) -> bool:
    try:
        raw_record = ArtifactProvenance.model_validate(raw_value)
        canonical_record = ArtifactProvenance.model_validate(canonical_value)
    except ValueError:
        return False
    components = fallback.get("components")
    if not isinstance(components, list) or len(components) != 3:
        return False
    component_paths: list[str] = []
    component_bindings: list[tuple[str, str, int]] = []
    for component in components:
        if not isinstance(component, Mapping):
            return False
        canonical_path = component.get("canonical_path")
        if not isinstance(canonical_path, str):
            return False
        component_paths.append(canonical_path)
        for prefix in ("raw", "canonical"):
            path = component.get(f"{prefix}_path")
            digest = component.get(f"{prefix}_sha256")
            size = component.get(f"{prefix}_bytes")
            if not isinstance(path, str) or not _valid_sha256(digest) or not _positive_int(size):
                return False
            component_bindings.append((path, cast(str, digest), cast(int, size)))
    world = plan.parent_contract.get("world_spec")
    wireframe = plan.parent_contract.get("wireframe")
    if not isinstance(world, Mapping) or not isinstance(wireframe, Mapping):
        return False
    try:
        world_binding = _binding_tuple(world)
        wireframe_binding = _binding_tuple(wireframe)
    except ValueError:
        return False
    raw_metadata = raw_record.params.get("metadata")
    canonical_metadata = canonical_record.params.get("metadata")
    transparency = canonical_record.params.get("transparency")
    if (
        raw_record.provider != "local"
        or raw_record.model != TILESET_MATERIAL_SYNTHESIS_VERSION
        or raw_record.prompt != spec.prompt
        or raw_record.prompt_sha256 != sha256_hex(spec.prompt.encode())
        or raw_record.refs != component_paths
        or raw_record.attempts != 1
        or raw_record.artifact is None
        or raw_record.artifact.sha256 != sha256_hex(raw)
        or raw_record.artifact.bytes != len(raw)
        or raw_record.tool.name != "tileset-material-assembler"
        or raw_record.tool.version != TILESET_MATERIAL_SYNTHESIS_VERSION
        or not isinstance(raw_metadata, Mapping)
        or raw_metadata.get("tileset_material_synthesis") != fallback
        or raw_metadata.get("style_anchor") != plan.parent_contract.get("style_anchor")
        or raw_metadata.get("theme_compilation") != plan.parent_contract.get("theme_identity")
        or raw_record.params.get("fallback") != fallback
        or raw_record.validation.get("output_sha256") != sha256_hex(raw)
        or raw_record.validation.get("tileset_material_synthesis") != fallback.get("synthesis")
        or raw_record.validation.get("tileset_material_flattening") != fallback.get("flattening")
        or canonical_record.provider != "local"
        or canonical_record.model != TILESET_MATERIAL_SYNTHESIS_VERSION
        or canonical_record.prompt != spec.prompt
        or canonical_record.prompt_sha256 != sha256_hex(spec.prompt.encode())
        or canonical_record.refs != [_retained_raw_path(spec).name, *component_paths]
        or canonical_record.attempts != 1
        or canonical_record.artifact is None
        or canonical_record.artifact.sha256 != sha256_hex(canonical)
        or canonical_record.artifact.bytes != len(canonical)
        or canonical_record.tool.name != "tileset-material-assembler"
        or canonical_record.tool.version != TILESET_MATERIAL_SYNTHESIS_VERSION
        or not isinstance(canonical_metadata, Mapping)
        or canonical_metadata.get("tileset_material_synthesis") != fallback
        or canonical_metadata.get("style_anchor") != plan.parent_contract.get("style_anchor")
        or canonical_metadata.get("theme_compilation") != plan.parent_contract.get("theme_identity")
        or not isinstance(transparency, Mapping)
        or transparency.get("tileset_material_synthesis") != fallback
        or transparency.get("processor")
        != {
            "kind": TILESET_MATERIAL_SYNTHESIS_VERSION,
            "version": TILESET_MATERIAL_SYNTHESIS_VERSION,
        }
        or transparency.get("raw_sha256") != sha256_hex(raw)
        or transparency.get("output_sha256") != sha256_hex(canonical)
        or canonical_record.validation.get("output_sha256") != sha256_hex(canonical)
        or canonical_record.validation.get("tileset_material_fallback") != fallback
    ):
        return False
    expected_raw_inputs = [world_binding, wireframe_binding, *component_bindings]
    expected_canonical_inputs = [
        (_retained_raw_path(spec).name, sha256_hex(raw), len(raw)),
        *expected_raw_inputs,
    ]
    if not _provenance_inputs_start_with(raw_record.inputs, expected_raw_inputs):
        return False
    if not _provenance_inputs_start_with(canonical_record.inputs, expected_canonical_inputs):
        return False
    return _valid_tileset_theme_input(raw_record, plan) and _valid_tileset_theme_input(
        canonical_record,
        plan,
    )


def _binding_tuple(binding: Mapping[str, object]) -> tuple[str, str, int]:
    path = binding.get("path")
    digest = binding.get("sha256")
    size = binding.get("bytes")
    if not isinstance(path, str) or not _valid_sha256(digest) or not _positive_int(size):
        raise ValueError("invalid tileset material content binding")
    return path, cast(str, digest), cast(int, size)


def _provenance_inputs_start_with(
    inputs: Sequence[InputProvenance],
    expected: Sequence[tuple[str, str, int]],
) -> bool:
    return len(inputs) >= len(expected) and all(
        item.ref == path
        and item.sha256 == digest
        and item.bytes == size
        and item.source == "content"
        for item, (path, digest, size) in zip(inputs, expected, strict=False)
    )


def _valid_tileset_theme_input(
    record: ArtifactProvenance,
    plan: _TilesetMaterialPlan,
) -> bool:
    base_inputs = 9 if record.refs and record.refs[0] == _retained_raw_name(plan) else 8
    expected: list[tuple[str, str, int | None]] = []
    for key in ("theme_identity", "style_anchor"):
        identity = plan.parent_contract.get(key)
        if identity is None:
            continue
        if not isinstance(identity, Mapping):
            return False
        ref = identity.get("artifact_ref")
        digest = identity.get("artifact_sha256")
        size = identity.get("artifact_bytes")
        if (
            not isinstance(ref, str)
            or not _valid_sha256(digest)
            or (size is not None and not _positive_int(size))
        ):
            return False
        expected.append((ref, cast(str, digest), cast(int | None, size)))
    if len(record.inputs) != base_inputs + len(expected):
        return False
    for item, (ref, digest, size) in zip(record.inputs[base_inputs:], expected, strict=True):
        if (
            item.ref != ref
            or item.sha256 != digest
            or item.source != "content"
            or item.media_type != "application/json"
            or (size is not None and item.bytes != size)
        ):
            return False
    return True


def _retained_raw_name(plan: _TilesetMaterialPlan) -> str:
    output = Path(str(plan.parent_contract["parent_output"]))
    return f"{output.stem}.raw.png"


def _valid_per_cell_record_structure(
    fallback: Mapping[str, object],
    *,
    spec: _ImageSpec,
    contract: GridContract,
    mode: object,
    theme_identity: Mapping[str, object] | None,
) -> bool:
    parent_contract = (spec.metadata or {}).get("per_cell_generation_contract")
    if not isinstance(parent_contract, Mapping):
        return False
    adapter = "items-v1" if spec.stage == "items" else "obstacles-v1"
    role_prefix = "item" if spec.stage == "items" else "prop"
    role_order = [f"{role_prefix}-{index}" for index in range(8)]
    identity_policy = (
        "independent-distinct-items" if spec.stage == "items" else "cell-0-scale-style-anchor"
    )
    exhaustion = fallback.get("sheet_exhaustion")
    components = fallback.get("components")
    composite = fallback.get("composite")
    normalization = fallback.get("grid_normalization")
    if (
        not _eligible_per_cell_stage(spec)
        or fallback.get("version") != _PER_CELL_GENERATION_VERSION
        or fallback.get("adapter") != adapter
        or fallback.get("parent_stage") != spec.stage
        or fallback.get("mode") != str(mode)
        or fallback.get("contract") != contract.as_dict(spec.width, spec.height)
        or fallback.get("parent_contract") != parent_contract
        or fallback.get("parent_prompt_sha256") != sha256_hex(spec.prompt.encode())
        or fallback.get("theme_identity")
        != (dict(theme_identity) if theme_identity is not None else None)
        or fallback.get("role_order") != role_order
        or fallback.get("identity_policy") != identity_policy
        or not _valid_per_cell_failure_history(fallback.get("sheet_failures"))
        or not isinstance(exhaustion, Mapping)
        or exhaustion.get("attempts") != 6
        or exhaustion.get("retries") != 5
        or not _valid_sha256(exhaustion.get("request_prompt_sha256"))
        or not isinstance(components, list)
        or len(components) != 8
        or not isinstance(composite, Mapping)
        or not isinstance(normalization, Mapping)
        or not _valid_fallback_record_digest(fallback)
    ):
        return False
    source_specs = parent_contract.get("source_specs")
    if not isinstance(source_specs, list) or len(source_specs) != 8:
        return False
    anchor = fallback.get("identity_anchor")
    if spec.stage == "items" and anchor is not None:
        return False
    if _uses_prop_sheet_adapter(spec.stage) and not isinstance(anchor, Mapping):
        return False
    for index, value in enumerate(components):
        if not isinstance(value, Mapping):
            return False
        row, column = divmod(index, 4)
        canonical = _per_cell_output(spec.output, row, column)
        raw = canonical.with_name(f"{canonical.stem}.raw.png")
        component_contract = value.get("component_contract")
        if (
            value.get("cell_index") != index
            or value.get("row") != row
            or value.get("column") != column
            or value.get("semantic_role") != role_order[index]
            or value.get("source_spec") != source_specs[index]
            or value.get("raw_path") != raw.name
            or value.get("canonical_path") != canonical.name
            or value.get("raw_provenance_path") != f"{raw.name}.meta.json"
            or value.get("canonical_provenance_path") != f"{canonical.name}.meta.json"
            or not _valid_sha256(value.get("raw_sha256"))
            or not _positive_int(value.get("raw_bytes"))
            or not _valid_sha256(value.get("canonical_sha256"))
            or not _positive_int(value.get("canonical_bytes"))
            or not _valid_sha256(value.get("raw_provenance_sha256"))
            or not _valid_sha256(value.get("canonical_provenance_sha256"))
            or not isinstance(component_contract, Mapping)
            or component_contract.get("version") != _PER_CELL_GENERATION_VERSION
            or component_contract.get("parent_contract_sha256") != parent_contract.get("sha256")
            or component_contract.get("cell_index") != index
            or component_contract.get("semantic_role") != role_order[index]
            or component_contract.get("source_spec") != source_specs[index]
            or not _valid_fallback_record_digest(component_contract)
        ):
            return False
        prior = value.get("layout_prior")
        if spec.stage == "items" and prior is not None:
            return False
        if _uses_prop_sheet_adapter(spec.stage):
            expected_prior = _per_cell_prior_output(spec.output, row, column)
            if (
                not isinstance(prior, Mapping)
                or prior.get("path") != expected_prior.name
                or not _valid_sha256(prior.get("sha256"))
                or not _positive_int(prior.get("bytes"))
                or prior.get("provenance_path") != f"{expected_prior.name}.meta.json"
                or not _valid_sha256(prior.get("provenance_sha256"))
            ):
                return False
    return True


def _per_cell_resume_record(
    raw_path: Path,
    *,
    spec: _ImageSpec,
    contract: GridContract | None,
    mode: object | None,
    theme_identity: Mapping[str, object] | None,
) -> Mapping[str, object] | None:
    if contract is None or mode is None or not _eligible_per_cell_stage(spec):
        return None
    sidecar_value: dict[str, Any] | None = None

    def retain_sidecar(_path: Path, sidecar: dict[str, Any]) -> bool:
        nonlocal sidecar_value
        sidecar_value = sidecar
        return _asset_metadata_matches(
            sidecar,
            expected=spec.metadata,
            contract=contract,
            width=spec.width,
            height=spec.height,
        ) and (theme_identity is None or _theme_identity_matches(sidecar, theme_identity))

    if (
        not valid_artifact_pair(
            raw_path,
            transparency_mode=cast(TransparencyMode, mode),
            validator=retain_sidecar,
        )
        or sidecar_value is None
    ):
        return None
    fallback = _per_cell_record_from_raw_sidecar(sidecar_value)
    if fallback is None or not _valid_per_cell_record_structure(
        fallback,
        spec=spec,
        contract=contract,
        mode=mode,
        theme_identity=theme_identity,
    ):
        return None
    if _valid_per_cell_fallback_cache(
        composite=spec.output,
        retained_raw=raw_path,
        fallback=fallback,
        contract=contract,
        width=spec.width,
        height=spec.height,
        expected_metadata=spec.metadata,
        theme_identity=theme_identity,
    ):
        return None
    return fallback


def _valid_per_cell_fallback_cache(
    *,
    composite: Path,
    retained_raw: Path,
    fallback: Mapping[str, object],
    contract: GridContract,
    width: int,
    height: int,
    expected_metadata: Mapping[str, object] | None,
    theme_identity: Mapping[str, object] | None,
) -> bool:
    parent_contract = (expected_metadata or {}).get("per_cell_generation_contract")
    if not isinstance(parent_contract, Mapping):
        return False
    parent_prompt_sha256 = parent_contract.get("parent_prompt_sha256")
    parent_stage = parent_contract.get("parent_stage")
    if not isinstance(parent_prompt_sha256, str) or not isinstance(parent_stage, str):
        return False
    adapter = "items-v1" if parent_stage == "items" else "obstacles-v1"
    role_prefix = "item" if parent_stage == "items" else "prop"
    identity_policy = (
        "independent-distinct-items" if parent_stage == "items" else "cell-0-scale-style-anchor"
    )
    sheet_exhaustion = fallback.get("sheet_exhaustion")
    source_specs = parent_contract.get("source_specs")
    identity_anchor = fallback.get("identity_anchor")
    expected_identity_dag = [
        {
            "cell_index": index,
            "depends_on": [0]
            if identity_policy == "cell-0-scale-style-anchor" and index > 0
            else [],
            "usage": "style-and-scale-only"
            if identity_policy == "cell-0-scale-style-anchor" and index > 0
            else "independent",
        }
        for index in range(8)
    ]
    if (
        fallback.get("parent_prompt_sha256") != parent_prompt_sha256
        or fallback.get("version") != _PER_CELL_GENERATION_VERSION
        or fallback.get("adapter") != adapter
        or fallback.get("parent_stage") != parent_stage
        or fallback.get("parent_contract") != parent_contract
        or parent_contract.get("version") != _PER_CELL_GENERATION_VERSION
        or parent_contract.get("adapter") != adapter
        or parent_contract.get("parent_stage") != parent_stage
        or parent_contract.get("role_order") != [f"{role_prefix}-{index}" for index in range(8)]
        or parent_contract.get("identity_policy") != identity_policy
        or parent_contract.get("eligible_sheet_failure_codes") != sorted(_PER_CELL_LAYOUT_CODES)
        or not _valid_fallback_record_digest(parent_contract)
        or fallback.get("contract") != contract.as_dict(width, height)
        or fallback.get("theme_identity")
        != (dict(theme_identity) if theme_identity is not None else None)
        or fallback.get("role_order") != [f"{role_prefix}-{index}" for index in range(8)]
        or fallback.get("identity_policy") != identity_policy
        or fallback.get("identity_dag") != expected_identity_dag
        or (parent_stage == "items" and identity_anchor is not None)
        or (_uses_prop_sheet_adapter(parent_stage) and not isinstance(identity_anchor, Mapping))
        or not isinstance(source_specs, list)
        or len(source_specs) != 8
        or not _valid_per_cell_failure_history(fallback.get("sheet_failures"))
        or not isinstance(sheet_exhaustion, Mapping)
        or sheet_exhaustion.get("attempts") != 6
        or sheet_exhaustion.get("retries") != 5
        or not _valid_sha256(sheet_exhaustion.get("request_prompt_sha256"))
        or not _valid_fallback_record_digest(fallback)
    ):
        return False
    try:
        raw = retained_raw.read_bytes()
        canonical = composite.read_bytes()
        mode = TransparencyMode(str(fallback.get("mode")))
    except (OSError, ValueError):
        return False
    composite_record = fallback.get("composite")
    normalization = fallback.get("grid_normalization")
    if (
        not isinstance(composite_record, Mapping)
        or composite_record.get("raw_sha256") != sha256_hex(raw)
        or composite_record.get("raw_bytes") != len(raw)
        or composite_record.get("canonical_sha256") != sha256_hex(canonical)
        or composite_record.get("canonical_bytes") != len(canonical)
        or not _valid_grid_normalization_evidence(
            normalization,
            canonical=canonical,
            raw=raw,
            width=width,
            height=height,
            contract=contract,
        )
    ):
        return False
    components = fallback.get("components")
    if not isinstance(components, list) or len(components) != 8:
        return False
    cell_width, cell_height = contract.cell_size(width, height)
    for index, value in enumerate(components):
        if not isinstance(value, Mapping):
            return False
        row, column = divmod(index, 4)
        canonical_path = _per_cell_output(composite, row, column)
        raw_path = canonical_path.with_name(f"{canonical_path.stem}.raw.png")
        raw_meta = Path(f"{raw_path}.meta.json")
        canonical_meta = Path(f"{canonical_path}.meta.json")
        try:
            component_raw = raw_path.read_bytes()
            component_canonical = canonical_path.read_bytes()
            raw_meta_bytes = raw_meta.read_bytes()
            canonical_meta_bytes = canonical_meta.read_bytes()
            raw_sidecar = json.loads(raw_meta_bytes)
            canonical_sidecar = json.loads(canonical_meta_bytes)
        except (OSError, json.JSONDecodeError):
            return False
        component_contract = value.get("component_contract")
        expected_role = f"{role_prefix}-{index}"
        expected_anchor = (
            identity_anchor
            if identity_policy == "cell-0-scale-style-anchor" and index > 0
            else None
        )
        if (
            not isinstance(component_contract, Mapping)
            or value.get("cell_index") != index
            or value.get("row") != row
            or value.get("column") != column
            or value.get("semantic_role") != expected_role
            or value.get("source_spec") != source_specs[index]
            or value.get("raw_path") != raw_path.name
            or value.get("canonical_path") != canonical_path.name
            or value.get("raw_provenance_path") != raw_meta.name
            or value.get("canonical_provenance_path") != canonical_meta.name
            or value.get("raw_sha256") != sha256_hex(component_raw)
            or value.get("raw_bytes") != len(component_raw)
            or value.get("canonical_sha256") != sha256_hex(component_canonical)
            or value.get("canonical_bytes") != len(component_canonical)
            or value.get("raw_provenance_sha256") != sha256_hex(raw_meta_bytes)
            or value.get("canonical_provenance_sha256") != sha256_hex(canonical_meta_bytes)
            or not valid_artifact_pair(raw_path, transparency_mode=mode)
            or not valid_artifact_pair(canonical_path, transparency_mode=mode)
            or not isinstance(raw_sidecar, dict)
            or not isinstance(canonical_sidecar, dict)
            or not _valid_per_cell_transparency_evidence(
                raw=component_raw,
                canonical=component_canonical,
                canonical_sidecar=canonical_sidecar,
                mode=mode,
                contract=component_contract,
                width=cell_width,
                height=cell_height,
            )
            or value.get("generation") != _fallback_provenance_summary(raw_sidecar)
            or value.get("transparency") != _fallback_provenance_summary(canonical_sidecar)
            or _metadata_field(raw_sidecar, "per_cell_generation") != component_contract
            or _metadata_field(canonical_sidecar, "per_cell_generation") != component_contract
            or component_contract.get("version") != _PER_CELL_GENERATION_VERSION
            or component_contract.get("adapter") != adapter
            or component_contract.get("parent_stage") != parent_stage
            or component_contract.get("parent_contract_sha256") != parent_contract.get("sha256")
            or component_contract.get("cell_index") != index
            or component_contract.get("row") != row
            or component_contract.get("column") != column
            or component_contract.get("semantic_role") != expected_role
            or component_contract.get("source_spec") != source_specs[index]
            or component_contract.get("identity_anchor") != expected_anchor
            or component_contract.get("layout_prior") != value.get("layout_prior")
            or not _valid_sha256(component_contract.get("prompt_sha256"))
            or not _valid_fallback_record_digest(component_contract)
        ):
            return False
        try:
            raw_validation = validate_isolated_view_source(
                component_raw,
                width=cell_width,
                height=cell_height,
                allow_recoverable_inset=True,
            )
            alpha_validation = validate_isolated_view_alpha(component_canonical)
            _validate_recoverable_per_cell_scale(
                raw_validation,
                component_contract,
                bbox_key="isolated_view_bbox",
                height=cell_height,
            )
            _validate_per_cell_scale(
                alpha_validation,
                component_contract,
                bbox_key="isolated_view_alpha_bbox",
                height=cell_height,
            )
        except ValueError:
            return False
        transparency_params = canonical_sidecar.get("params")
        transparency = (
            transparency_params.get("transparency")
            if isinstance(transparency_params, Mapping)
            else None
        )
        bindings = component_contract.get("reference_bindings")
        raw_inputs = raw_sidecar.get("inputs")
        if (
            not isinstance(transparency, Mapping)
            or transparency.get("raw_sha256") != sha256_hex(component_raw)
            or transparency.get("output_sha256") != sha256_hex(component_canonical)
            or not isinstance(bindings, list)
            or not isinstance(raw_inputs, list)
            or raw_sidecar.get("refs")
            != [binding.get("path") for binding in bindings if isinstance(binding, Mapping)]
        ):
            return False
        for binding in bindings:
            if not isinstance(binding, Mapping) or not isinstance(binding.get("path"), str):
                return False
            reference_path = composite.parent / str(binding["path"])
            try:
                reference_data = reference_path.read_bytes()
            except OSError:
                return False
            if (
                binding.get("sha256") != sha256_hex(reference_data)
                or binding.get("bytes") != len(reference_data)
                or not any(
                    isinstance(item, Mapping)
                    and Path(str(item.get("ref", ""))).name == binding.get("path")
                    and item.get("sha256") == binding.get("sha256")
                    and item.get("bytes") == binding.get("bytes")
                    for item in raw_inputs
                )
            ):
                return False
        prior = value.get("layout_prior")
        if prior is not None:
            if not isinstance(prior, Mapping) or not isinstance(prior.get("path"), str):
                return False
            prior_path = composite.parent / str(prior["path"])
            prior_meta = Path(f"{prior_path}.meta.json")
            try:
                prior_data = prior_path.read_bytes()
                prior_meta_data = prior_meta.read_bytes()
            except OSError:
                return False
            if (
                prior.get("sha256") != sha256_hex(prior_data)
                or prior.get("bytes") != len(prior_data)
                or prior.get("provenance_sha256") != sha256_hex(prior_meta_data)
                or not valid_artifact_pair(prior_path)
            ):
                return False
        elif _uses_prop_sheet_adapter(parent_stage):
            return False
    if _uses_prop_sheet_adapter(parent_stage):
        first = components[0]
        if not isinstance(first, Mapping) or not isinstance(identity_anchor, Mapping):
            return False
        if identity_anchor != {
            "path": first.get("canonical_path"),
            "sha256": first.get("canonical_sha256"),
            "bytes": first.get("canonical_bytes"),
            "source_cell": 0,
            "usage": "style-and-scale-only",
        }:
            return False
    return True


def _valid_isolated_view_fallback_cache(
    *,
    composite: Path,
    retained_raw: Path,
    fallback: Mapping[str, object],
    contract: GridContract,
    width: int,
    height: int,
    expected_metadata: Mapping[str, object] | None,
) -> bool:
    parent_stage = fallback.get("parent_stage")
    if (
        fallback.get("version") != _ISOLATED_VIEW_FALLBACK_VERSION
        or not isinstance(parent_stage, str)
        or not _is_turnaround_concept_stage(parent_stage)
        or fallback.get("contract") != contract.as_dict(width, height)
        or fallback.get("prompt_reference_contract")
        != (expected_metadata or {}).get("turnaround_prompt_reference_contract")
        or fallback.get("view_roles") != list(_TURNAROUND_VIEW_ROLES)
        or fallback.get("identity_anchor_view") != 0
        or not _valid_fallback_record_digest(fallback)
    ):
        return False
    sheet = fallback.get("sheet_exhaustion")
    composite_record = fallback.get("composite")
    components = fallback.get("components")
    prompt_reference_contract = fallback.get("prompt_reference_contract")
    parent_reference_bindings = (
        prompt_reference_contract.get("reference_bindings")
        if isinstance(prompt_reference_contract, Mapping)
        else None
    )
    if (
        not isinstance(sheet, Mapping)
        or sheet.get("attempts") != 6
        or sheet.get("retries") != 5
        or sheet.get("error_code") != GRID_ISOLATION_ERROR_CODE
        or GRID_ISOLATION_ERROR_CODE not in str(sheet.get("reason", ""))
        or not isinstance(components, list)
        or len(components) != 3
        or not isinstance(composite_record, Mapping)
        or not isinstance(parent_reference_bindings, list)
        or len(parent_reference_bindings) != 1
        or not isinstance(parent_reference_bindings[0], Mapping)
    ):
        return False
    parent_reference = cast(Mapping[str, object], parent_reference_bindings[0])
    expected_world_binding = {
        "path": parent_reference.get("path"),
        "sha256": parent_reference.get("sha256"),
        "bytes": parent_reference.get("bytes"),
    }
    try:
        raw = retained_raw.read_bytes()
        canonical = composite.read_bytes()
        mode = TransparencyMode(str(fallback.get("mode")))
    except (OSError, ValueError):
        return False
    if (
        composite_record.get("raw_sha256") != sha256_hex(raw)
        or composite_record.get("raw_bytes") != len(raw)
        or composite_record.get("canonical_sha256") != sha256_hex(canonical)
        or composite_record.get("canonical_bytes") != len(canonical)
    ):
        return False
    cell_width, cell_height = contract.cell_size(width, height)
    anchor: dict[str, object] | None = None
    for index, value in enumerate(components):
        if not isinstance(value, Mapping):
            return False
        expected_canonical = _isolated_view_output(composite, index)
        expected_raw = expected_canonical.with_name(f"{expected_canonical.stem}.raw.png")
        raw_meta = Path(f"{expected_raw}.meta.json")
        canonical_meta = Path(f"{expected_canonical}.meta.json")
        try:
            component_raw = expected_raw.read_bytes()
            component_canonical = expected_canonical.read_bytes()
            raw_meta_bytes = raw_meta.read_bytes()
            canonical_meta_bytes = canonical_meta.read_bytes()
            raw_sidecar = json.loads(raw_meta_bytes)
            canonical_sidecar = json.loads(canonical_meta_bytes)
        except (OSError, json.JSONDecodeError):
            return False
        expected_anchor = None if index == 0 else anchor
        if (
            value.get("view_index") != index
            or value.get("view_role") != _TURNAROUND_VIEW_ROLES[index]
            or value.get("raw_path") != expected_raw.name
            or value.get("canonical_path") != expected_canonical.name
            or value.get("raw_provenance_path") != raw_meta.name
            or value.get("canonical_provenance_path") != canonical_meta.name
            or value.get("raw_sha256") != sha256_hex(component_raw)
            or value.get("raw_bytes") != len(component_raw)
            or value.get("canonical_sha256") != sha256_hex(component_canonical)
            or value.get("canonical_bytes") != len(component_canonical)
            or value.get("raw_provenance_sha256") != sha256_hex(raw_meta_bytes)
            or value.get("canonical_provenance_sha256") != sha256_hex(canonical_meta_bytes)
            or value.get("identity_anchor") != expected_anchor
            or not valid_artifact_pair(expected_raw, transparency_mode=mode)
            or not valid_artifact_pair(expected_canonical, transparency_mode=mode)
            or not isinstance(raw_sidecar, dict)
            or not isinstance(canonical_sidecar, dict)
            or value.get("generation") != _fallback_provenance_summary(raw_sidecar)
            or value.get("transparency") != _fallback_provenance_summary(canonical_sidecar)
        ):
            return False
        try:
            validate_isolated_view_source(
                component_raw,
                width=cell_width,
                height=cell_height,
            )
            validate_isolated_view_alpha(component_canonical)
        except ValueError:
            return False
        raw_params = raw_sidecar.get("params")
        raw_metadata = raw_params.get("metadata") if isinstance(raw_params, Mapping) else None
        view_contract = (
            raw_metadata.get("isolated_view_fallback")
            if isinstance(raw_metadata, Mapping)
            else None
        )
        expected_reference_bindings = [expected_world_binding]
        if expected_anchor is not None:
            expected_reference_bindings.append(
                {
                    "path": expected_anchor["path"],
                    "sha256": expected_anchor["sha256"],
                    "bytes": expected_anchor["bytes"],
                }
            )
        if (
            not isinstance(view_contract, Mapping)
            or view_contract.get("version") != _ISOLATED_VIEW_FALLBACK_VERSION
            or view_contract.get("view_index") != index
            or view_contract.get("view_role") != _TURNAROUND_VIEW_ROLES[index]
            or view_contract.get("identity_anchor") != expected_anchor
            or view_contract.get("reference_bindings") != expected_reference_bindings
            or not _valid_fallback_record_digest(view_contract)
        ):
            return False
        if str(mode) == str(TransparencyMode.CHROMA) and not (
            _valid_isolated_view_transparency_evidence(
                raw=component_raw,
                canonical=component_canonical,
                canonical_sidecar=canonical_sidecar,
                mode=mode,
                contract=view_contract,
                width=cell_width,
                height=cell_height,
            )
        ):
            return False
        canonical_params = canonical_sidecar.get("params")
        transparency = (
            canonical_params.get("transparency") if isinstance(canonical_params, Mapping) else None
        )
        if (
            not isinstance(transparency, Mapping)
            or transparency.get("raw_sha256") != sha256_hex(component_raw)
            or transparency.get("output_sha256") != sha256_hex(component_canonical)
        ):
            return False
        if index == 0:
            anchor = {
                "path": expected_canonical.name,
                "sha256": sha256_hex(component_canonical),
                "bytes": len(component_canonical),
                "source_view": 0,
            }
        else:
            references = raw_sidecar.get("refs")
            inputs = raw_sidecar.get("inputs")
            if (
                anchor is None
                or not isinstance(references, list)
                or not any(
                    isinstance(reference, str) and Path(reference).name == str(anchor["path"])
                    for reference in references
                )
                or not isinstance(inputs, list)
                or not any(
                    isinstance(item, Mapping)
                    and Path(str(item.get("ref", ""))).name == str(anchor["path"])
                    and item.get("sha256") == anchor["sha256"]
                    and item.get("bytes") == anchor["bytes"]
                    for item in inputs
                )
            ):
                return False
    return True


def _valid_fallback_record_digest(value: Mapping[str, object]) -> bool:
    digest = value.get("sha256")
    payload = {key: nested for key, nested in value.items() if key != "sha256"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return digest == sha256_hex(encoded)


def _fallback_provenance_summary(sidecar: Mapping[str, Any]) -> dict[str, object]:
    return {
        "prompt": sidecar.get("prompt"),
        "prompt_sha256": sidecar.get("prompt_sha256"),
        "provider": sidecar.get("provider"),
        "model": sidecar.get("model"),
        "seed": sidecar.get("seed"),
        "refs": sidecar.get("refs"),
        "params": sidecar.get("params"),
        "attempts": sidecar.get("attempts"),
        "inputs": sidecar.get("inputs"),
    }


def _valid_cell_bbox(
    value: object,
    width: int,
    height: int,
    *,
    gutter: int,
) -> bool:
    if (
        not isinstance(value, list)
        or len(value) != 4
        or any(isinstance(item, bool) or not isinstance(item, int) for item in value)
    ):
        return False
    left, top, right, bottom = cast(list[int], value)
    return gutter <= left < right <= width - gutter and gutter <= top < bottom <= height - gutter


def _alpha_counts(data: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(data)) as image:
        image.load()
        if "A" not in image.convert("RGBA").getbands():
            raise ValueError("image has no alpha channel")
        alpha = image.convert("RGBA").getchannel("A").tobytes()
    transparent_pixels = sum(value < 255 for value in alpha)
    nontransparent_pixels = sum(value > 0 for value in alpha)
    if transparent_pixels == 0 or nontransparent_pixels == 0:
        raise ValueError("image must contain transparent and nontransparent pixels")
    return transparent_pixels, nontransparent_pixels


async def _read_provenance(path: Path) -> ArtifactProvenance:
    raw = await asyncio.to_thread(path.read_text, encoding="utf-8")
    return ArtifactProvenance.model_validate_json(raw)


def _embedded_provenance(record: ArtifactProvenance) -> dict[str, Any]:
    sanitized = sanitize_for_persistence(
        record.model_dump(mode="json", by_alias=True, exclude_none=True)
    )
    if not isinstance(sanitized, dict):
        raise TypeError("embedded provenance must be an object")
    return sanitized


def _assert_temp_path_absent(value: dict[str, Any], temporary_path: Path) -> None:
    rendered = json.dumps(value, ensure_ascii=False)
    if str(temporary_path) in rendered or temporary_path.name in rendered:
        raise ValueError("temporary artifact path cannot be persisted in provenance")


def _actionable_exception(group: ExceptionGroup[Exception]) -> Exception:
    for error in group.exceptions:
        if isinstance(error, ExceptionGroup):
            return _actionable_exception(error)
        return error
    return RuntimeError("parallel generation failed")
