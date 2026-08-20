"""Recipe-specific execution composed from reusable component services."""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image
from PIL import __version__ as pillow_version

from stage_gen.components import (
    BackgroundRemovalRequest,
    BackgroundRemovalService,
    ImageGenerationRequest,
    ImageGenerationService,
    ImageReference,
    StructuredGenerationRequest,
    StructuredGenerationService,
    StructuredOutputSchema,
    StructuredReference,
)
from stage_gen.contracts import (
    ArtifactProvenance,
    BinaryArtifact,
    InputProvenance,
    ProvenanceInput,
    SoftwareIdentity,
)
from stage_gen.media import (
    apply_chroma_transparency,
    compose_source_with_alpha,
    inspect_image,
    normalize_png,
)
from stage_gen.recipes.base import StageContext
from stage_gen.recipes.scrolling_preview.cache import valid_artifact_pair
from stage_gen.recipes.scrolling_preview.manifest import write_scrolling_preview_manifest
from stage_gen.recipes.scrolling_preview.models import WorldSpec
from stage_gen.reliability import (
    sanitize_for_persistence,
    sha256_hex,
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


@dataclass(frozen=True, slots=True)
class _CompiledThemeContext:
    plan: CompiledThemePlan
    identity: dict[str, object]
    artifact_bytes: int


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
            "theme-compile": self._theme_compile,
            "concept": self._concept,
            "world-spec": self._world_spec,
            "wave-a": self._wave_a,
            "wave-b": self._wave_b,
            "post-split": self._post_split,
            "manifest": self._manifest,
            "maintenance-regenerate-tileset": self._regenerate_tileset,
        }
        try:
            handler = handlers[stage_name]
        except KeyError as error:
            raise ValueError(f"unknown scrolling-preview stage: {stage_name}") from error
        return await handler(context)

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
            validator=lambda path, sidecar: _valid_theme_plan_cache(
                path,
                sidecar,
                request,
                expected_model=context.config.text_model,
            ),
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
        if valid_artifact_pair(
            output,
            validator=lambda path, sidecar: _valid_world_spec_cache(
                path,
                sidecar,
                compiled.identity if compiled is not None else None,
            ),
        ):
            return (str(output), f"{output}.meta.json")
        prompt = str(context.input["prompt"])
        concept = context.run_dir / f"concept_{context.tag}.png"
        reference = await _structured_reference(concept)

        def parse(value: object) -> WorldSpec:
            spec = WorldSpec.model_validate(value)
            if len(spec.mobs) != 8:
                raise ValueError(f"mobs length {len(spec.mobs)} != requested 8")
            if len(spec.obstacles) != 3:
                raise ValueError(f"obstacles length {len(spec.obstacles)} != requested 3")
            return spec

        planner_instruction = (
            "Design a side-scrolling world bible with exactly 8 ascending, anatomy-distinct "
            "mobs; exactly 3 uniquely themed obstacle sheets with 8 props each; exactly 8 "
            "semantically distinct items; and 1-5 parallax layers with exactly one opaque "
            "z=0/parallax=0 backdrop."
        )
        request_prompt = f'WORLD PROMPT: "{prompt}"\n{planner_instruction}'
        request_metadata: dict[str, object] = {"stage": "world-spec", "user_prompt": prompt}
        if compiled is not None:
            request_prompt = _append_compiled_directive(
                (f"Validated compiled concept:\n{compiled.plan.concept}\n\n{planner_instruction}"),
                compiled.plan.world_spec,
                compiled.plan.hard_exclusions,
            )
            request_metadata = {"stage": "world-spec", "theme_compilation": compiled.identity}

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
                metadata=request_metadata,
                timeout_seconds=context.config.capability_timeout_s,
                cancellation=context.cancellation,
            )
        )
        return (str(output), generated.provenance_path)

    async def _wave_a(self, context: StageContext) -> Sequence[str]:
        spec = await _read_world_spec(context)
        concept = context.run_dir / f"concept_{context.tag}.png"
        templates = _template_root()
        image_specs: list[_ImageSpec] = []
        for layer in spec.layers:
            image_specs.append(
                _ImageSpec(
                    stage=f"layer-{layer.id}",
                    prompt=(
                        f"Parallax layer '{layer.title}' for a 2D scrolling world. "
                        f"{layer.description} Paint region: {layer.paint_region}."
                    ),
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
        image_specs.extend(
            [
                self._tileset_spec(context),
                _ImageSpec(
                    "character-concept",
                    "Player-character front, side, and back concept turnaround on one baseline.",
                    context.run_dir / f"character_concept_{context.tag}.png",
                    2400,
                    800,
                    (concept,),
                ),
                _ImageSpec(
                    "items",
                    "Eight distinct collectible items in a strict horizontal sheet: "
                    + "; ".join(f"{item.name}: {item.brief}" for item in spec.items),
                    context.run_dir / f"items_{context.tag}.png",
                    2400,
                    800,
                    (templates / "obstacle_template.png", concept),
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
                    "Entry and exit portal landmarks in two equal horizontal cells.",
                    context.run_dir / f"portal_{context.tag}.png",
                    2048,
                    1024,
                    (concept,),
                ),
            ]
        )
        for index, mob in enumerate(spec.mobs):
            image_specs.append(
                _ImageSpec(
                    f"mob-concept-{index}",
                    f"Creature turnaround for {mob.name}, {mob.body_plan}. {mob.brief}",
                    context.run_dir / f"mob_concept_{context.tag}_{index}.png",
                    2400,
                    800,
                    (concept,),
                    metadata={"slot": index, "tier_label": mob.tier_label},
                )
            )
        for index, sheet in enumerate(spec.obstacles):
            image_specs.append(
                _ImageSpec(
                    f"obstacles-{index}",
                    f"Eight props for {sheet.sheet_theme}: "
                    + "; ".join(f"{prop.name}: {prop.brief}" for prop in sheet.props),
                    context.run_dir / f"obstacles_{context.tag}_{index}.png",
                    2400,
                    800,
                    (templates / "obstacle_template.png", concept),
                    metadata={"sheet_theme": sheet.sheet_theme, "slot": index},
                )
            )
        return await self._fan_out(context, image_specs)

    def _tileset_spec(self, context: StageContext) -> _ImageSpec:
        """Return the production tileset contract shared by the recipe and maintenance CLI."""

        return _ImageSpec(
            "tileset",
            "Ground tileset, strict 12x4 cell layout matching the supplied wireframe.",
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
                "Four-frame attack strip: anticipation, swing, impact, recovery.",
                context.run_dir / f"character_{context.tag}_attack.png",
                2400,
                800,
                (template, character),
            ),
        ]
        for index, mob in enumerate(spec.mobs):
            concept = context.run_dir / f"mob_concept_{context.tag}_{index}.png"
            image_specs.extend(
                [
                    _ImageSpec(
                        f"mob-idle-{index}",
                        f"Four-frame looping idle strip for {mob.name}; preserve exact identity.",
                        context.run_dir / f"mob_{context.tag}_{index}_idle.png",
                        2400,
                        800,
                        (concept, template),
                    ),
                    _ImageSpec(
                        f"mob-hurt-{index}",
                        f"Four-frame impact, stagger, settling, recovery strip for {mob.name}.",
                        context.run_dir / f"mob_{context.tag}_{index}_hurt.png",
                        2400,
                        800,
                        (concept, template),
                    ),
                ]
            )
        generated = await self._fan_out(context, (*strip_specs, *image_specs))
        master = await self._compose_character_master(context)
        strip_prefix = f"character_{context.tag}_combined_strip_"
        published = tuple(
            path for path in generated if not Path(path).name.startswith(strip_prefix)
        )
        return (*master, *published)

    async def _compose_character_master(self, context: StageContext) -> Sequence[str]:
        compiled = await _read_compiled_theme(context)
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
        if valid_artifact_pair(
            output,
            transparency_mode=context.config.transparency_mode,
            validator=lambda path, meta: (
                _exact_image(path, 2400, 3440, alpha=True)
                and _source_hashes_match(meta, source_hashes)
                and _optional_theme_identity_matches(
                    meta,
                    compiled.identity if compiled is not None else None,
                )
            ),
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
                + ([_theme_plan_input(compiled)] if compiled is not None else []),
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
                        "composite_strategy": "per-row",
                        "states": list(_STATES),
                        "rows": 5,
                        "cols": 4,
                        "cellW": 600,
                        "cellH": 688,
                        "strip_gen_height": 800,
                        "strip_crop_bottom_px": 112,
                        "composite_offsets_y": [row * 688 for row in range(5)],
                        **(
                            {"theme_compilation": compiled.identity} if compiled is not None else {}
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
                    and _optional_theme_identity_matches(
                        meta,
                        compiled.identity if compiled is not None else None,
                    )
                ),
            ):
                output_hash = sha256_hex(data)
                transparent_pixels, nontransparent_pixels = _alpha_counts(data)
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
                            )
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
                        },
                        component=_RECIPE_COMPONENT,
                        tool=SoftwareIdentity(name="Pillow", version=pillow_version),
                        attempts=1,
                    ),
                )
            else:
                sidecar = Path(f"{output}.meta.json")
            artifacts.extend((str(output), str(sidecar)))
        return artifacts

    async def _manifest(self, context: StageContext) -> Sequence[str]:
        result = await write_scrolling_preview_manifest(
            run_dir=context.run_dir,
            tag=context.tag,
            transparency_mode=context.config.transparency_mode,
        )
        return result.artifacts

    async def _fan_out(self, context: StageContext, specs: Sequence[_ImageSpec]) -> Sequence[str]:
        results: list[Sequence[str] | None] = [None] * len(specs)

        async def run(index: int, spec: _ImageSpec) -> None:
            results[index] = await self._generate_image_asset(context, spec)

        try:
            async with asyncio.TaskGroup() as group:
                for index, spec in enumerate(specs):
                    group.create_task(run(index, spec), name=f"scrolling-preview:{spec.stage}")
        except ExceptionGroup as error:
            leaf = _actionable_exception(error)
            raise RuntimeError(str(leaf)) from leaf
        return tuple(path for result in results if result is not None for path in result)

    async def _generate_image_asset(
        self, context: StageContext, spec: _ImageSpec, *, force: bool = False
    ) -> Sequence[str]:
        compiled = await _read_compiled_theme(context)
        mode = context.config.transparency_mode if spec.transparent else None
        raw_path = (
            spec.output.with_name(f"{spec.output.stem}.raw.png")
            if mode is not None
            else spec.output
        )
        if valid_artifact_pair(
            raw_path,
            transparency_mode=mode,
            validator=lambda path, meta: (
                _exact_image(path, spec.width, spec.height, alpha=False)
                and _optional_theme_identity_matches(
                    meta,
                    compiled.identity if compiled is not None else None,
                )
            ),
            force=force,
        ):
            if mode is None:
                return (str(spec.output), f"{spec.output}.meta.json")
            if valid_artifact_pair(
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
                    )
                    and _optional_theme_identity_matches(
                        meta,
                        compiled.identity if compiled is not None else None,
                    )
                ),
                force=force,
            ):
                return (str(spec.output), f"{spec.output}.meta.json")
            canonical = await self._derive_transparency(context, spec, raw_path)
            return (str(spec.output), str(canonical))

        references = tuple([await _image_reference(path) for path in spec.references])
        provider_path = raw_path.parent / f".{raw_path.name}.provider-{uuid.uuid4().hex}.png"
        prompt = spec.prompt
        request_metadata: dict[str, object] = {
            "stage": spec.stage,
            "requested_width": spec.width,
            "requested_height": spec.height,
            **({"transparency_mode": str(mode)} if mode is not None else {}),
            **(spec.metadata or {}),
        }
        if compiled is not None:
            if spec.compiled_creative_base:
                prompt = _append_binding_visual_constraints(prompt, compiled.plan.hard_exclusions)
            else:
                prompt = _append_compiled_directive(
                    prompt,
                    _directive_for_image_stage(compiled.plan, spec.stage),
                    compiled.plan.hard_exclusions,
                )
            request_metadata["theme_compilation"] = compiled.identity
        effective_prompt = _prompt_for_transparency(prompt, mode)
        if compiled is not None:
            assert_no_raw_theme_control_leak(effective_prompt)
            _assert_no_raw_theme_controls_in_metadata(request_metadata)
        try:
            generated = await self._images.generate(
                ImageGenerationRequest(
                    prompt=effective_prompt,
                    artifact_path=provider_path,
                    input_references=references,
                    aspect_ratio=_ratio(spec.width, spec.height),
                    quality="high",
                    background="opaque",
                    moderation="low",
                    metadata=request_metadata,
                    timeout_seconds=context.config.capability_timeout_s,
                    cancellation=context.cancellation,
                    validate=lambda artifact: _validate_provider_png(artifact.data, spec.stage),
                )
            )
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
                        InputProvenance(
                            ref=f"provider-output:{spec.stage}",
                            sha256=source_hash,
                            source="content",
                            bytes=len(generated.data),
                            media_type=generated.media_type,
                        ),
                        *([_theme_plan_input(compiled)] if compiled is not None else []),
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
                                {"theme_compilation": compiled.identity}
                                if compiled is not None
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

    async def _derive_transparency(
        self, context: StageContext, spec: _ImageSpec, raw_path: Path
    ) -> Path:
        compiled = await _read_compiled_theme(context)
        raw = await asyncio.to_thread(raw_path.read_bytes)
        raw_record = await _read_provenance(Path(f"{raw_path}.meta.json"))
        embedded_raw = _embedded_provenance(raw_record)
        mode = context.config.transparency_mode
        removal_record: ArtifactProvenance | None = None
        embedded_removal: dict[str, Any] | None = None
        removal_mask_used = False
        if str(mode) == "chroma":
            output, alpha = apply_chroma_transparency(raw)
            processor = "chroma-key"
        else:
            if self._background is None:
                raise RuntimeError("ai transparency requires the background-removal component")
            provider_path = spec.output.parent / (
                f".{spec.output.name}.removed-{uuid.uuid4().hex}.png"
            )
            try:
                removed = await self._background.remove(
                    BackgroundRemovalRequest(
                        image_url=_data_url(raw),
                        artifact_path=provider_path,
                        output_mask=True,
                        metadata={"stage": spec.stage},
                        timeout_seconds=context.config.capability_timeout_s,
                        cancellation=context.cancellation,
                    )
                )
                output, alpha = compose_source_with_alpha(
                    raw,
                    removed_data=removed.data,
                    mask_data=removed.mask.data if removed.mask is not None else None,
                )
                removal_mask_used = removed.mask is not None
                removal_record = await _read_provenance(Path(removed.provenance_path))
                embedded_removal = _embedded_provenance(removal_record)
                _assert_temp_path_absent(embedded_removal, provider_path)
            finally:
                await asyncio.to_thread(provider_path.unlink, missing_ok=True)
                await asyncio.to_thread(Path(f"{provider_path}.meta.json").unlink, missing_ok=True)
            processor = "ai-background-removal"
        raw_hash = sha256_hex(raw)
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
                    *([_theme_plan_input(compiled)] if compiled is not None else []),
                ],
                params={
                    "transparency": {
                        "mode": str(mode),
                        "retained_raw_path": raw_path.name,
                        "raw_sha256": raw_hash,
                        "output_sha256": output_hash,
                        "processor": {"kind": processor, "version": "1"},
                        "source_provenance": embedded_raw,
                        **({"removal": removal_payload} if removal_payload is not None else {}),
                    },
                    "metadata": {
                        "stage": spec.stage,
                        **(
                            {"theme_compilation": compiled.identity} if compiled is not None else {}
                        ),
                    },
                },
                validation={
                    "alpha_nontrivial": True,
                    "transparent_pixels": alpha.transparent_pixels,
                    "nontransparent_pixels": alpha.nontransparent_pixels,
                    "dimensions_preserved": True,
                    "output_width": spec.width,
                    "output_height": spec.height,
                    "output_sha256": output_hash,
                },
                component=_RECIPE_COMPONENT,
                tool=SoftwareIdentity(name=processor, version="1"),
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


def _theme_plan_path(context: StageContext) -> Path:
    return context.run_dir / f"theme_plan_{context.tag}.json"


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
        validator=lambda artifact, sidecar: _valid_theme_plan_cache(
            artifact,
            sidecar,
            request,
            expected_model=context.config.text_model,
        ),
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


def _valid_theme_plan_cache(
    path: Path,
    sidecar: dict[str, Any],
    request: StructuredGenerationRequest[CompiledThemePlan],
    *,
    expected_model: str,
) -> bool:
    try:
        request.parse(json.loads(path.read_text(encoding="utf-8")))
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
    return (
        sidecar.get("model") == expected_model
        and sidecar.get("prompt") == request.prompt
        and params == expected_params
    )


def _valid_world_spec_cache(
    path: Path,
    sidecar: Mapping[str, Any],
    identity: Mapping[str, object] | None,
) -> bool:
    try:
        WorldSpec.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return _optional_theme_identity_matches(sidecar, identity)


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


def _theme_plan_input(compiled: _CompiledThemeContext) -> InputProvenance:
    return InputProvenance(
        ref=str(compiled.identity["artifact_ref"]),
        sha256=str(compiled.identity["artifact_sha256"]),
        source="content",
        bytes=compiled.artifact_bytes,
        media_type="application/json",
    )


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
    if stage == "concept":
        return plan.concept
    if stage in {"items", "inventory"} or stage.startswith("obstacles-"):
        return plan.items
    if stage == "portal":
        return plan.portals
    if stage.startswith(("character-", "mob-")):
        return plan.characters
    return plan.environment


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


async def _image_reference(path: Path) -> ImageReference:
    data = await asyncio.to_thread(path.read_bytes)
    return ImageReference(url=_data_url(data), provenance_ref=str(path))


async def _structured_reference(path: Path) -> StructuredReference:
    data = await asyncio.to_thread(path.read_bytes)
    return StructuredReference(url=_data_url(data), provenance_ref=str(path))


def _data_url(data: bytes) -> str:
    return f"data:image/png;base64,{base64.b64encode(data).decode('ascii')}"


def _validate_provider_png(data: bytes, stage: str) -> dict[str, object]:
    facts = inspect_image(data, expected_media_type="image/png")
    return {"stage": stage, "source_width": facts.width, "source_height": facts.height}


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


def _character_strip_prompt(state: str) -> str:
    motion = {
        "idle": "four visibly distinct phases of a subtle breathing cycle; feet stay planted",
        "walk": "four alternating-leg phases forming one clean walk cycle",
        "run": "four sprint phases including airborne frames and exaggerated stride",
        "jump": "anticipation crouch, push-off, airborne apex, and landing impact",
        "crawl": "four hands-and-knees phases with a low horizontal torso",
    }[state]
    return (
        f"Four-frame {state} animation strip for the supplied character: {motion}. "
        "Strict 4x1 equal cells, side view facing right, fixed identity, scale, head rail, "
        "and feet baseline. Do not render template lines, labels, borders, or shadows."
    )


def _ratio(width: int, height: int) -> str:
    divisor = _gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


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
        with Image.open(BytesIO(data)) as image:
            image.load()
            if image.size != (2400, 800):
                raise ValueError("character master source strip must be 2400x800")
            master.alpha_composite(image.convert("RGBA").crop((0, 0, 2400, 688)), (0, row * 688))
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


def _valid_transparency_cache(
    path: Path,
    sidecar: dict[str, Any],
    *,
    raw_path: Path,
    mode: object,
    width: int,
    height: int,
) -> bool:
    if not _exact_image(path, width, height, alpha=True):
        return False
    try:
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
    return (
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
