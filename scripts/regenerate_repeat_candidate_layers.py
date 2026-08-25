#!/usr/bin/env python3
"""Regenerate selected canonical scrolling layers as low-salience repeat candidates.

This is an explicit proof harness, not a recipe or component API.  It deliberately calls the
scrolling-preview executor's existing image-asset path so the proof keeps the recipe's prompt
bindings, normalization, transparency processing, provenance, and cache validation behavior.
Existing canonical artifacts are moved to an operator-owned backup before any provider call.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import stat
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stage_gen.components.background_removal import BackgroundRemovalService
from stage_gen.config import (
    CapabilityName,
    StageGenConfig,
    TransparencyMode,
    assert_capabilities,
    load_config,
    parse_transparency_mode,
)
from stage_gen.contracts import load_recipe_run_summary
from stage_gen.media import inspect_image
from stage_gen.orchestration.runtime import (
    create_background_removal_service,
    create_image_service,
    create_structured_service,
)
from stage_gen.recipes.base import StageContext
from stage_gen.recipes.scrolling_preview.cache import valid_artifact_pair
from stage_gen.recipes.scrolling_preview.executor import (
    ScrollingPreviewExecutor,
    _asset_metadata_matches,
    _exact_image,
    _ImageSpec,
    _parallax_layer_prompt,
    _read_compiled_theme,
    _read_game_contract,
    _read_style_anchor,
    _retained_raw_path,
    _spec_grid_contract,
    _valid_raw_asset_cache,
    _valid_transparency_cache,
)
from stage_gen.recipes.scrolling_preview.models import WorldLayer, WorldSpec
from stage_gen.reliability import (
    assert_safe_path_segment,
    redact_secrets,
    sanitize_for_persistence,
    sha256_hex,
)

_WIDTH = 2400
_HEIGHT = 800
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_FAL_BASE_URL = "https://fal.run"
_KIND = "repeat_candidate_layer_regeneration_proof"

_SKY_BACKDROP_PROMPT = (
    "Paint an opaque full-canvas vertical sky color wash for a 2D side-scrolling game, "
    "not a composed sky scene. Every horizontal position and every x-axis column must be "
    "visually interchangeable: the only large-scale change may run vertically from a "
    "slightly deeper soft blue at the top to a slightly lighter soft blue at the bottom. "
    "Use only extremely subtle, homogeneous fine painted grain with no identifiable shape. "
    "No horizontal lighting gradient or left-to-right color change. No clouds, cloud wisps, "
    "patches, streaks, bands, rays, focal cloud masses, sun, moon, mountains, skyline, "
    "buildings, landmarks, silhouettes, vignettes, text, borders, or watermarks."
)

_PROMPTS = {
    "backdrop_sky": _SKY_BACKDROP_PROMPT,
    "painted_sky_backdrop": _SKY_BACKDROP_PROMPT,
    "far_vale": (
        "Do not compose a landscape, horizon, or distant scene. Leave the upper three quarters "
        "of the full 3:1 canvas as one clean key background. In only the lower quarter, paint a "
        "homogeneous low-salience blue-cyan translucent airbrush mist wash. Its upper transition "
        "must be one perfectly straight, level, very soft horizontal fade with no dark outline, "
        "undulation, ridge, scallop, peak, or local height change. Every x-axis column, every "
        "one-twelfth-width window, and both horizontal ends must be visually interchangeable in "
        "opacity, palette, lighting, density, and scale. Use only extremely subtle uniform fine "
        "grain, with no locally identifiable shape. No hills, mountains, valleys, trees, "
        "buildings, castle, windmill, bridge, arches, roads, water horizon, clouds, objects, "
        "motifs, landmarks, clusters, warm accents, vignettes, characters, text, borders, or "
        "watermarks."
    ),
    "middle_country": (
        "Do not compose a landscape or scene. Paint one continuous, dense, low-contrast "
        "cool-green stippled meadow-texture fringe for a 2D side-scrolling game, confined to the "
        "bottom twentieth of the canvas. Treat it as a texture band rather than individual "
        "plants: no legible stems, blades, tufts, isolated vertical protrusions, gaps, or local "
        "clusters, and no warm red, brown, or high-contrast accents. Keep a nearly level shallow "
        "silhouette. Every one-twelfth-width window and both horizontal ends must be visually "
        "interchangeable in height, density, palette, and contrast. No hill peaks, valleys, "
        "bushes, paths, flowers, rocks, houses, bridges, castles, trees, recognizable motifs, "
        "focal landmarks, edge vignettes, characters, text, borders, or watermarks. Leave the "
        "rest as one clean key background."
    ),
    "near_foreground": (
        "Do not compose a foreground scene or arrange plant clusters. Paint a homogeneous, "
        "low-salience transparent micro-grass fringe for a 2D side-scrolling game, confined to "
        "the bottom tenth of the canvas. Use many tiny, short, visually interchangeable blades "
        "with irregular micro-spacing and no repeating rhythm. Every local window and both "
        "horizontal ends must have similar height, scale, and density. No tall plants, broad "
        "leaves, identifiable species, isolated stems, large flowers, rocks, trunks, arches, "
        "recognizable motifs, focal clusters, landmarks, characters, continuous ground plane, "
        "text, borders, shadows, or watermarks. Leave the rest as one clean key background."
    ),
}


@dataclass(frozen=True, slots=True)
class BackupMove:
    source: Path
    destination: Path


@dataclass(frozen=True, slots=True)
class LayerRegeneration:
    name: str
    transparent: bool
    original_spec: _ImageSpec
    replacement_spec: _ImageSpec
    moves: tuple[BackupMove, ...]


@dataclass(frozen=True, slots=True)
class RegenerationPlan:
    run_dir: Path
    backup_dir: Path
    tag: str
    transparency_mode: TransparencyMode
    context: StageContext
    layers: tuple[LayerRegeneration, ...]


@dataclass(frozen=True, slots=True)
class CliOptions:
    run_dir: Path
    backup_dir: Path
    game_library_root: Path
    layers: tuple[str, ...]
    dry_run: bool


class ImageAssetRegenerator(Protocol):
    async def _generate_image_asset(
        self, context: StageContext, spec: _ImageSpec, *, force: bool = False
    ) -> Sequence[str]: ...


class AsyncClosable(Protocol):
    async def aclose(self) -> None: ...


@dataclass(frozen=True, slots=True)
class LiveBundle:
    executor: ImageAssetRegenerator
    resources: tuple[AsyncClosable, ...]

    async def aclose(self) -> None:
        first_error: BaseException | None = None
        for resource in self.resources:
            try:
                await resource.aclose()
            except BaseException as error:
                if first_error is None:
                    first_error = error
        if first_error is not None:
            raise first_error


def prepare_regeneration(
    run_dir: Path,
    layer_names: Sequence[str],
    backup_dir: Path,
    config: StageGenConfig,
) -> RegenerationPlan:
    """Validate the existing run, every source pair, and every backup destination."""

    resolved_run_dir = _validated_existing_directory(run_dir, "run directory")
    resolved_backup_dir = _validated_backup_root(
        backup_dir,
        run_dir=resolved_run_dir,
    )
    names = tuple(layer_names)
    if not names:
        raise ValueError("at least one --layer is required")
    if len(names) != len(set(names)):
        raise ValueError("--layer values must be unique")
    unsupported = sorted(set(names) - set(_PROMPTS))
    if unsupported:
        raise ValueError(
            "unsupported layer selection; allowed layers are " + ", ".join(sorted(_PROMPTS))
        )

    summary = load_recipe_run_summary(
        _validated_regular_file_within(
            resolved_run_dir,
            resolved_run_dir / "run.json",
            "run summary",
        )
    )
    if summary.recipe != "scrolling-preview":
        raise ValueError("run summary is not for scrolling-preview")
    tag = assert_safe_path_segment(summary.tag, "run tag")
    if summary.run_dir != resolved_run_dir.name:
        raise ValueError("run summary run_dir does not match the requested run directory")
    if resolved_run_dir.name != tag:
        raise ValueError("run directory name does not match the run tag")
    raw_input = summary.input
    prompt = raw_input.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("run summary input requires a non-empty prompt")
    mode = parse_transparency_mode(
        raw_input.get("transparency_mode"),
        "run input.transparency_mode",
    )
    world_path = resolved_run_dir / f"world_spec_{tag}.json"
    _require_valid_pair(world_path, "world specification")
    try:
        world = WorldSpec.model_validate_json(world_path.read_bytes())
    except (OSError, ValueError) as error:
        raise ValueError("world specification is not valid canonical JSON") from error
    layer_by_name = {layer.id: layer for layer in world.layers}

    concept = resolved_run_dir / f"concept_{tag}.png"
    _require_valid_pair(concept, "world concept")
    try:
        concept_facts = inspect_image(concept.read_bytes(), expected_media_type="image/png")
    except (OSError, ValueError) as error:
        raise ValueError("world concept is not a valid PNG") from error
    if (concept_facts.width, concept_facts.height) != (1536, 1024):
        raise ValueError("world concept must be exactly 1536x1024")

    context_input = cast(
        dict[str, Any],
        {**raw_input, "prompt": prompt.strip(), "transparency_mode": mode.value},
    )
    run_config = config.model_copy(
        update={"out_dir": resolved_run_dir.parent, "transparency_mode": mode}
    )
    context = StageContext(
        input=context_input,
        tag=tag,
        run_dir=resolved_run_dir,
        config=run_config,
    )

    layer_plans: list[LayerRegeneration] = []
    for name in names:
        layer = layer_by_name.get(name)
        if layer is None:
            raise ValueError(f"world specification does not contain layer {name!r}")
        transparent = not layer.opaque
        if layer.opaque == transparent:
            raise ValueError(f"world layer {name!r} opacity does not match the proof contract")
        output = resolved_run_dir / f"layer_{tag}_{name}.png"
        metadata = _layer_metadata(layer)
        original_spec = _ImageSpec(
            stage=f"layer-{name}",
            prompt=_parallax_layer_prompt(layer),
            output=output,
            width=_WIDTH,
            height=_HEIGHT,
            references=(concept,),
            transparent=transparent,
            metadata=metadata,
        )
        replacement_spec = _ImageSpec(
            stage=f"layer-{name}",
            prompt=_PROMPTS[name],
            output=output,
            width=_WIDTH,
            height=_HEIGHT,
            references=(concept,),
            transparent=transparent,
            metadata=metadata,
            portable_references=True,
        )
        _require_existing_layer_integrity(original_spec, mode)

        layer_backup = resolved_backup_dir / name
        if layer_backup.exists() or layer_backup.is_symlink():
            raise ValueError(f"backup destination already exists for layer {name!r}")
        sources = list(_artifact_pair_paths(output))
        raw_path = _retained_raw_path(original_spec)
        if raw_path != output:
            sources.extend(_artifact_pair_paths(raw_path))
        moves = tuple(
            BackupMove(source=source, destination=layer_backup / source.name) for source in sources
        )
        if any(move.destination.exists() or move.destination.is_symlink() for move in moves):
            raise ValueError(f"backup output collision for layer {name!r}")
        layer_plans.append(
            LayerRegeneration(
                name=name,
                transparent=transparent,
                original_spec=original_spec,
                replacement_spec=replacement_spec,
                moves=moves,
            )
        )

    return RegenerationPlan(
        run_dir=resolved_run_dir,
        backup_dir=resolved_backup_dir,
        tag=tag,
        transparency_mode=mode,
        context=context,
        layers=tuple(layer_plans),
    )


async def execute_regeneration(
    plan: RegenerationPlan,
    executor: ImageAssetRegenerator,
) -> dict[str, object]:
    """Move every old pair first, then regenerate each exact canonical target atomically."""

    await asyncio.to_thread(_move_all_to_backup, plan)
    records: list[dict[str, object]] = []
    try:
        for layer in plan.layers:
            spec = layer.replacement_spec
            _require_outputs_absent(spec)
            artifacts = await executor._generate_image_asset(plan.context, spec, force=False)
            _require_existing_layer_cache(spec, plan.transparency_mode)
            records.append(
                {
                    "layer": layer.name,
                    "status": "regenerated",
                    "transparent": layer.transparent,
                    "output": spec.output.name,
                    "raw": _retained_raw_path(spec).name,
                    "prompt_sha256": sha256_hex(spec.prompt.encode()),
                    "artifacts": [Path(value).name for value in artifacts],
                    "backups": [move.destination.name for move in layer.moves],
                }
            )
    except BaseException as error:
        try:
            await asyncio.to_thread(_rollback_failed_regeneration, plan)
        except BaseException as rollback_error:
            raise BaseExceptionGroup(
                "layer regeneration failed and rollback was incomplete",
                [error, rollback_error],
            ) from None
        raise
    return _report(plan, records, dry_run=False)


def dry_run_report(plan: RegenerationPlan) -> dict[str, object]:
    records = [
        {
            "layer": layer.name,
            "status": "planned",
            "transparent": layer.transparent,
            "output": layer.replacement_spec.output.name,
            "raw": _retained_raw_path(layer.replacement_spec).name,
            "prompt_sha256": sha256_hex(layer.replacement_spec.prompt.encode()),
            "backups": [move.destination.name for move in layer.moves],
        }
        for layer in plan.layers
    ]
    return _report(plan, records, dry_run=True)


def create_live_bundle(
    config: StageGenConfig,
    *,
    transparency_mode: TransparencyMode,
    needs_transparency: bool,
) -> LiveBundle:
    if config.transparency_mode is not transparency_mode:
        raise ValueError("regeneration config transparency mode does not match the run")
    needs_background = needs_transparency and transparency_mode is TransparencyMode.AI
    assert_capabilities(
        config,
        (
            CapabilityName.IMAGE_GENERATION,
            *((CapabilityName.BACKGROUND_REMOVAL,) if needs_background else ()),
        ),
    )
    api_key = config.open_router_api_key
    if api_key is None:  # Kept explicit for type narrowing after capability validation.
        raise ValueError("OpenRouter configuration was not loaded")
    image = create_image_service(
        api_key=api_key,
        model=config.image_model,
        base_url=config.open_router_base_url or _OPENROUTER_BASE_URL,
    )
    structured = create_structured_service(
        api_key=api_key,
        model=config.text_model,
        base_url=config.open_router_base_url or _OPENROUTER_BASE_URL,
    )
    background: BackgroundRemovalService | None = None
    if needs_background:
        if config.fal_key is None:
            raise ValueError("FAL configuration was not loaded")
        background = create_background_removal_service(
            api_key=config.fal_key,
            model=config.background_removal_model,
            base_url=config.fal_base_url or _FAL_BASE_URL,
        )
    executor = ScrollingPreviewExecutor(
        image_service=image,
        structured_service=structured,
        background_service=background,
    )
    resources: tuple[AsyncClosable, ...] = (
        image,
        structured,
        *((background,) if background is not None else ()),
    )
    return LiveBundle(executor=executor, resources=resources)


async def run_live(
    plan: RegenerationPlan,
    bundle_factory: Callable[..., LiveBundle] = create_live_bundle,
) -> dict[str, object]:
    await validate_context_bindings(plan)
    bundle = bundle_factory(
        plan.context.config,
        transparency_mode=plan.transparency_mode,
        needs_transparency=any(layer.transparent for layer in plan.layers),
    )
    try:
        report = await execute_regeneration(plan, bundle.executor)
    except BaseException as error:
        try:
            await bundle.aclose()
        except BaseException as close_error:
            error.add_note(f"service close also failed: {type(close_error).__name__}")
        raise
    await bundle.aclose()
    return report


async def validate_context_bindings(plan: RegenerationPlan) -> None:
    """Fail before backup if the run's creative-direction bindings are stale or unavailable."""

    await _read_compiled_theme(plan.context)
    await _read_style_anchor(plan.context)
    await _read_game_contract(plan.context)


def _layer_metadata(layer: WorldLayer) -> dict[str, object]:
    return {
        "stage": f"layer-{layer.id}",
        "opaque": layer.opaque,
        "z_index": layer.z_index,
        "parallax": layer.parallax,
    }


def _require_existing_layer_integrity(
    spec: _ImageSpec,
    transparency_mode: TransparencyMode,
) -> None:
    """Validate the superseded pair without requiring today's replacement prompt.

    Prompt drift is the reason this maintenance harness exists.  The source still has to be an
    exact, content-bound artifact pair owned by the selected layer, and a transparent canonical
    must remain bound to its retained raw bytes and the run's declared transparency mode.
    """

    contract = _spec_grid_contract(spec)
    raw_path = _retained_raw_path(spec)
    mode = transparency_mode if spec.transparent else None
    if not valid_artifact_pair(
        raw_path,
        transparency_mode=mode,
        validator=lambda path, sidecar: (
            _exact_image(path, spec.width, spec.height, alpha=False)
            and _asset_metadata_matches(
                sidecar,
                expected=spec.metadata,
                contract=contract,
                width=spec.width,
                height=spec.height,
            )
            and _valid_reference_bindings(
                sidecar,
                spec,
                allow_legacy_absolute=True,
            )
        ),
        force=False,
    ):
        raise ValueError(f"existing raw artifact pair is invalid for layer {spec.stage!r}")
    if spec.transparent and not valid_artifact_pair(
        spec.output,
        transparency_mode=transparency_mode,
        validator=lambda path, sidecar: _valid_transparency_cache(
            path,
            sidecar,
            raw_path=raw_path,
            mode=transparency_mode,
            width=spec.width,
            height=spec.height,
            contract=contract,
            expected_metadata=spec.metadata,
        ),
        force=False,
    ):
        raise ValueError(
            f"existing canonical transparency lineage is invalid for layer {spec.stage!r}"
        )


def _require_existing_layer_cache(
    spec: _ImageSpec,
    transparency_mode: TransparencyMode,
) -> None:
    """Require the regenerated pair to carry the exact replacement-spec cache identity."""

    contract = _spec_grid_contract(spec)
    raw_path = _retained_raw_path(spec)
    mode = transparency_mode if spec.transparent else None
    if not valid_artifact_pair(
        raw_path,
        transparency_mode=mode,
        validator=lambda path, sidecar: (
            _valid_raw_asset_cache(
                path,
                sidecar,
                spec=spec,
                contract=contract,
            )
            and _valid_reference_bindings(
                sidecar,
                spec,
                allow_legacy_absolute=False,
            )
        ),
        force=False,
    ):
        raise ValueError(f"regenerated raw artifact pair is invalid for layer {spec.stage!r}")
    if spec.transparent and not valid_artifact_pair(
        spec.output,
        transparency_mode=transparency_mode,
        validator=lambda path, sidecar: _valid_transparency_cache(
            path,
            sidecar,
            raw_path=raw_path,
            mode=transparency_mode,
            width=spec.width,
            height=spec.height,
            contract=contract,
            expected_metadata=spec.metadata,
        ),
        force=False,
    ):
        raise ValueError(f"regenerated canonical artifact pair is invalid for layer {spec.stage!r}")


def _valid_reference_bindings(
    sidecar: dict[str, Any],
    spec: _ImageSpec,
    *,
    allow_legacy_absolute: bool,
) -> bool:
    refs = sidecar.get("refs")
    references = sidecar.get("references")
    inputs = sidecar.get("inputs")
    if (
        not isinstance(refs, list)
        or refs != references
        or len(refs) != len(spec.references)
        or not isinstance(inputs, list)
    ):
        return False

    expected: list[dict[str, object]] = []
    for index, path in enumerate(spec.references):
        try:
            data = path.read_bytes()
            facts = inspect_image(data, expected_media_type="image/png")
        except (OSError, ValueError):
            return False
        portable_ref = path.name
        legacy_ref = str(path)
        observed_ref = refs[index]
        if not isinstance(observed_ref, str) or observed_ref not in {
            portable_ref,
            *((legacy_ref,) if allow_legacy_absolute else ()),
        }:
            return False
        expected.append(
            {
                "ref": observed_ref,
                "sha256": sha256_hex(data),
                "source": "content",
                "bytes": len(data),
                "media_type": facts.media_type,
            }
        )
    return all(
        sum(isinstance(value, dict) and value == item for value in inputs) == 1 for item in expected
    )


def _require_valid_pair(path: Path, label: str) -> None:
    _validated_regular_file_within(path.parent, path, label)
    _validated_regular_file_within(path.parent, Path(f"{path}.meta.json"), f"{label} provenance")
    if not valid_artifact_pair(path, force=False):
        raise ValueError(f"{label} artifact pair is missing, stale, or invalid")


def _artifact_pair_paths(path: Path) -> tuple[Path, Path]:
    return path, Path(f"{path}.meta.json")


def _require_outputs_absent(spec: _ImageSpec) -> None:
    paths = [*_artifact_pair_paths(spec.output)]
    raw = _retained_raw_path(spec)
    if raw != spec.output:
        paths.extend(_artifact_pair_paths(raw))
    collisions = [path.name for path in paths if path.exists() or path.is_symlink()]
    if collisions:
        raise ValueError("regeneration output collision: " + ", ".join(collisions))


def _move_all_to_backup(plan: RegenerationPlan) -> None:
    moved: list[BackupMove] = []
    plan.backup_dir.mkdir(parents=True, exist_ok=True)
    try:
        for layer in plan.layers:
            layer_dir = plan.backup_dir / layer.name
            layer_dir.mkdir()
            for move in layer.moves:
                if move.destination.exists() or move.destination.is_symlink():
                    raise ValueError(f"backup output collision: {move.destination.name}")
                shutil.move(str(move.source), str(move.destination))
                moved.append(move)
    except Exception as error:
        rollback_errors: list[Exception] = []
        for move in reversed(moved):
            try:
                if move.source.exists() or move.source.is_symlink():
                    raise ValueError(f"rollback source collision: {move.source.name}")
                shutil.move(str(move.destination), str(move.source))
            except Exception as rollback_error:
                rollback_errors.append(rollback_error)
        if rollback_errors:
            raise ExceptionGroup(
                "backup move failed and rollback was incomplete",
                [error, *rollback_errors],
            ) from None
        raise


def _rollback_failed_regeneration(plan: RegenerationPlan) -> None:
    """Preserve partial outputs, then restore every superseded canonical pair."""

    for layer in plan.layers:
        spec = layer.replacement_spec
        generated_paths = [*_artifact_pair_paths(spec.output)]
        raw = _retained_raw_path(spec)
        if raw != spec.output:
            generated_paths.extend(_artifact_pair_paths(raw))
        present = [path for path in generated_paths if path.exists() or path.is_symlink()]
        if present:
            failed_dir = plan.backup_dir / "_failed_generation" / layer.name
            failed_dir.mkdir(parents=True, exist_ok=True)
            for path in present:
                destination = failed_dir / path.name
                if destination.exists() or destination.is_symlink():
                    raise ValueError(f"failed-output backup collision: {destination.name}")
                shutil.move(str(path), str(destination))

    restored: list[BackupMove] = []
    try:
        for layer in reversed(plan.layers):
            for move in reversed(layer.moves):
                if move.source.exists() or move.source.is_symlink():
                    raise ValueError(f"rollback source collision: {move.source.name}")
                if not move.destination.is_file() or move.destination.is_symlink():
                    raise ValueError(f"rollback backup is missing: {move.destination.name}")
                shutil.move(str(move.destination), str(move.source))
                restored.append(move)
    except Exception as error:
        recovery_errors: list[Exception] = []
        for move in reversed(restored):
            try:
                if move.destination.exists() or move.destination.is_symlink():
                    raise ValueError(f"recovery backup collision: {move.destination.name}")
                shutil.move(str(move.source), str(move.destination))
            except Exception as recovery_error:
                recovery_errors.append(recovery_error)
        if recovery_errors:
            raise ExceptionGroup(
                "regeneration rollback failed and recovery was incomplete",
                [error, *recovery_errors],
            ) from None
        raise


def _report(
    plan: RegenerationPlan,
    layers: list[dict[str, object]],
    *,
    dry_run: bool,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": _KIND,
        "ok": True,
        "dry_run": dry_run,
        "tag": plan.tag,
        "run_dir": str(plan.run_dir),
        "backup_dir": str(plan.backup_dir),
        "transparency_mode": str(plan.transparency_mode),
        "layers": layers,
    }


def _recovery_state(plan: RegenerationPlan) -> list[dict[str, object]]:
    return [
        {
            "layer": layer.name,
            "source_files_present": [
                move.source.name for move in layer.moves if move.source.is_file()
            ],
            "backup_files_present": [
                move.destination.name for move in layer.moves if move.destination.is_file()
            ],
        }
        for layer in plan.layers
    ]


def _validated_existing_directory(path_value: str | Path, label: str) -> Path:
    path = Path(path_value).absolute()
    cursor = Path(path.anchor)
    try:
        metadata = cursor.lstat()
    except FileNotFoundError as error:  # pragma: no cover - platform invariant
        raise ValueError(f"{label} does not exist") from error
    for part in path.parts[1:]:
        cursor /= part
        try:
            metadata = cursor.lstat()
        except FileNotFoundError as error:
            raise ValueError(f"{label} does not exist") from error
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"{label} contains a symlink")
        if cursor != path and not stat.S_ISDIR(metadata.st_mode):
            raise ValueError(f"{label} parent is not a directory")
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"{label} must be a directory")
    if path.resolve(strict=True) != path:
        raise ValueError(f"{label} escapes its lexical path")
    return path


def _validated_regular_file_within(root: Path, path: Path, label: str) -> Path:
    lexical_root = root.absolute()
    lexical_path = path.absolute()
    try:
        lexical_path.relative_to(lexical_root)
    except ValueError as error:
        raise ValueError(f"{label} escapes its root") from error
    try:
        metadata = lexical_path.lstat()
    except FileNotFoundError as error:
        raise ValueError(f"{label} does not exist") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{label} must be a regular non-symlink file")
    if lexical_path.resolve(strict=True) != lexical_path:
        raise ValueError(f"{label} escapes its root")
    return lexical_path


def _validated_backup_root(path_value: Path, *, run_dir: Path) -> Path:
    path = path_value.absolute()
    if "\x00" in str(path_value):
        raise ValueError("backup directory contains a null byte")
    cursor = Path(path.anchor)
    metadata = cursor.lstat()
    missing = False
    for part in path.parts[1:]:
        cursor /= part
        if missing:
            continue
        try:
            metadata = cursor.lstat()
        except FileNotFoundError:
            missing = True
            continue
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError("backup directory contains a symlink")
        if cursor != path and not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("backup directory parent is not a directory")
    if not missing and not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("backup directory must be a directory")
    if path.resolve(strict=False) != path:
        raise ValueError("backup directory escapes its lexical path")
    if _is_relative_to(path, run_dir) or _is_relative_to(run_dir, path):
        raise ValueError("backup directory must be outside and must not contain the run directory")
    return path


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _parse_args(argv: Sequence[str] | None = None) -> CliOptions:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--backup-dir",
        type=Path,
        required=True,
        help="Operator-owned backup root outside the run directory.",
    )
    parser.add_argument(
        "--game-library-root",
        type=Path,
        required=True,
        help="Workspace root used to resolve the run's portable authored game binding.",
    )
    parser.add_argument(
        "--layer",
        dest="layers",
        action="append",
        choices=tuple(sorted(_PROMPTS)),
        required=True,
        help="Canonical layer to regenerate; repeat for multiple layers.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parsed = parser.parse_args(argv)
    return CliOptions(
        run_dir=cast(Path, parsed.run_dir),
        backup_dir=cast(Path, parsed.backup_dir),
        game_library_root=cast(Path, parsed.game_library_root),
        layers=tuple(cast(list[str], parsed.layers)),
        dry_run=cast(bool, parsed.dry_run),
    )


def main(argv: Sequence[str] | None = None) -> int:
    options = _parse_args(argv)
    secrets: tuple[str, ...] = ()
    plan: RegenerationPlan | None = None
    try:
        config = load_config().model_copy(
            update={"game_library_root": options.game_library_root.resolve()}
        )
        secrets = tuple(value for value in (config.open_router_api_key, config.fal_key) if value)
        plan = prepare_regeneration(
            options.run_dir,
            options.layers,
            options.backup_dir,
            config,
        )
        if options.dry_run:
            asyncio.run(validate_context_bindings(plan))
            report = dry_run_report(plan)
        else:
            report = asyncio.run(run_live(plan))
    except Exception as error:
        report = {
            "schema_version": 1,
            "kind": _KIND,
            "ok": False,
            "error": {
                "type": type(error).__name__,
                "message": redact_secrets(str(error), secrets)[:2000],
            },
            **(
                {
                    "tag": plan.tag,
                    "run_dir": str(plan.run_dir),
                    "backup_dir": str(plan.backup_dir),
                    "recovery_state": _recovery_state(plan),
                }
                if plan is not None
                else {}
            ),
        }
    safe = sanitize_for_persistence(report, secrets)
    if not isinstance(safe, dict):  # pragma: no cover - fixed report shapes
        safe = {
            "schema_version": 1,
            "kind": _KIND,
            "ok": False,
            "error": {"type": "TypeError", "message": "report sanitization failed"},
        }
    print(json.dumps(safe, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if safe.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
