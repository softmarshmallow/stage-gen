#!/usr/bin/env python3
"""Run an explicit image-repeat admission and repair proof on canonical game layers."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, cast

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gnode import (
    assert_safe_path_segment,
    atomic_write_json,
    redact_secrets,
    sanitize_for_persistence,
)
from stage_gen.components.image_repeat import (
    ImageRepeatAdmissionRequest,
    ImageRepeatDeterministicValidationError,
    ImageRepeatRepairRequest,
    ImageRepeatResult,
    ImageRepeatSemanticValidationError,
    ImageRepeatService,
    MaskedImageEditBackend,
)
from stage_gen.components.structured_generation import (
    StructuredGenerationService,
)
from stage_gen.config import (
    CapabilityName,
    StageGenConfig,
    load_config,
)
from stage_gen.contracts import load_recipe_run_summary
from stage_gen.orchestration.image_repeat_reviewer import (
    StructuredIntendedLoopReviewer,
)
from stage_gen.providers.openrouter import (
    OpenRouterMaskedImageEditBackend,
    OpenRouterStructuredBackend,
)

type Axis = Literal["x", "y"]
type CoveragePolicy = Literal["continuous", "sparse_allowed"]

_DEFAULT_LAYERS = ("playfield", "near_foreground")
_LAYER_NAME_RE = re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")
_REPAIR_MODEL = "openai/gpt-image-2"
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass(frozen=True, slots=True)
class LayerPolicy:
    coverage_policy: CoveragePolicy
    intended_behavior: str
    repair_prompt: str


@dataclass(frozen=True, slots=True)
class LayerPlan:
    name: str
    source: Path
    source_provenance: Path
    policy: LayerPolicy


@dataclass(frozen=True, slots=True)
class ProofPlan:
    run_dir: Path
    tag: str
    layers: tuple[LayerPlan, ...]


@dataclass(frozen=True, slots=True)
class CliOptions:
    run_dir: Path
    layers: tuple[str, ...]
    axis: Axis
    context_span_px: int
    repair_span_px: int
    artifact_label: str | None
    report_path: Path | None
    repair_on_rejection: bool


class ImageRepeatOperations(Protocol):
    async def admit(self, request: ImageRepeatAdmissionRequest) -> ImageRepeatResult: ...

    async def repair(self, request: ImageRepeatRepairRequest) -> ImageRepeatResult: ...


def layer_policy(name: str) -> LayerPolicy:
    """Return generic game-layer semantics without camera or runtime workarounds."""

    if name == "near_foreground":
        return LayerPolicy(
            coverage_policy="sparse_allowed",
            intended_behavior=(
                "low-salience near-foreground micro-foliage fringe with transparent space, "
                "no recognizable landmark or focal motif, and small irregular forms that "
                "repeat naturally along the declared axis"
            ),
            repair_prompt=(
                "Continue only the tiny irregular micro-foliage, transparency, palette, and "
                "density naturally between the supplied endpoint contexts. Do not introduce "
                "a tall plant, cluster, landmark, focal motif, or spacing rhythm."
            ),
        )
    if name in {"middle_country", "middle_vale"}:
        return LayerPolicy(
            coverage_policy="continuous",
            intended_behavior=(
                "homogeneous dense low-contrast thin distant meadow texture fringe with no "
                "recognizable landmark, individual plant, focal motif, warm accent, or rhythmic "
                "cluster, repeating naturally along the declared axis"
            ),
            repair_prompt=(
                "Continue the dense low-contrast cool-green meadow texture band at exactly the "
                "same full height, upper silhouette, opacity, palette, and even density between "
                "the supplied endpoint contexts. Keep solid texture coverage through the entire "
                "masked span with no transparent gap. Do not introduce legible stems, tufts, "
                "warm accents, a hill peak, tree, bush, rock, landmark, focal motif, or rhythm."
            ),
        )
    if name == "far_vale":
        return LayerPolicy(
            coverage_policy="sparse_allowed",
            intended_behavior=(
                "homogeneous low-salience distant atmospheric haze ribbon with transparent "
                "space, no recognizable landscape form, landmark, focal motif, or rhythmic "
                "cluster, repeating naturally along the declared axis"
            ),
            repair_prompt=(
                "Continue only the shallow blue-cyan atmospheric haze ribbon, feathered alpha, "
                "palette, lighting, and density naturally between the supplied endpoint "
                "contexts. Do not introduce a gap, hill, peak, tree, building, landmark, focal "
                "motif, warm accent, or spacing rhythm."
            ),
        )
    if name == "playfield":
        return LayerPolicy(
            coverage_policy="continuous",
            intended_behavior=(
                "continuous structural playfield layer with terrain and environmental forms "
                "that repeats naturally along the declared axis"
            ),
            repair_prompt=(
                "Continue the playfield terrain, environmental structures, surface rhythm, "
                "palette, lighting, and transparency naturally between the supplied endpoint "
                "contexts."
            ),
        )
    return LayerPolicy(
        coverage_policy="continuous",
        intended_behavior=(
            "continuous game-art layer whose structures, texture, lighting, and transparency "
            "repeat naturally along the declared axis"
        ),
        repair_prompt=(
            "Continue the layer structures, texture, lighting, palette, and transparency "
            "naturally between the supplied endpoint contexts."
        ),
    )


def prepare_proof(run_dir: Path, layer_names: Sequence[str]) -> ProofPlan:
    """Resolve only canonical run artifacts before any provider is constructed."""

    resolved_run_dir = run_dir.resolve()
    if not resolved_run_dir.is_dir():
        raise ValueError("run directory does not exist or is not a directory")
    names = tuple(layer_names) or _DEFAULT_LAYERS
    if len(names) != len(set(names)):
        raise ValueError("layer names must be unique")
    for name in names:
        if _LAYER_NAME_RE.fullmatch(name) is None:
            raise ValueError(f"unsafe layer name: {name!r}")
    tag = _read_run_tag(resolved_run_dir)
    plans: list[LayerPlan] = []
    for name in names:
        source = resolved_run_dir / f"layer_{tag}_{name}.png"
        source_provenance = Path(f"{source}.meta.json")
        if not source.is_file() or not source_provenance.is_file():
            raise ValueError(
                f"canonical layer or provenance is missing for layer {name!r} and tag {tag!r}"
            )
        plans.append(
            LayerPlan(
                name=name,
                source=source,
                source_provenance=source_provenance,
                policy=layer_policy(name),
            )
        )
    return ProofPlan(run_dir=resolved_run_dir, tag=tag, layers=tuple(plans))


async def execute_proof(
    plan: ProofPlan,
    service: ImageRepeatOperations,
    *,
    axis: Axis = "x",
    context_span_px: int = 192,
    repair_span_px: int = 512,
    artifact_label: str | None = None,
    repair_on_rejection: bool = False,
    timeout_seconds: float | None = None,
    secrets: tuple[str, ...] = (),
) -> dict[str, object]:
    """Admit an unchanged layer or explicitly repair a typed rejection."""

    layer_records: list[dict[str, object]] = []
    layer_successes: list[bool] = []
    for layer in plan.layers:
        record, succeeded = await _execute_layer(
            plan,
            layer,
            service,
            axis=axis,
            context_span_px=context_span_px,
            repair_span_px=repair_span_px,
            artifact_label=artifact_label,
            repair_on_rejection=repair_on_rejection,
            timeout_seconds=timeout_seconds,
            secrets=secrets,
        )
        layer_records.append(record)
        layer_successes.append(succeeded)
    return {
        "schema_version": 1,
        "kind": "image_repeat_game_proof",
        "ok": bool(layer_successes) and all(layer_successes),
        "tag": plan.tag,
        "axis": axis,
        "context_span_px": context_span_px,
        "repair_span_px": repair_span_px,
        "repair_on_rejection": repair_on_rejection,
        **({"artifact_label": artifact_label} if artifact_label is not None else {}),
        "layers": layer_records,
    }


async def _execute_layer(
    plan: ProofPlan,
    layer: LayerPlan,
    service: ImageRepeatOperations,
    *,
    axis: Axis,
    context_span_px: int,
    repair_span_px: int,
    artifact_label: str | None,
    repair_on_rejection: bool,
    timeout_seconds: float | None,
    secrets: tuple[str, ...],
) -> tuple[dict[str, object], bool]:
    stem = layer.source.stem
    output_stem = stem if artifact_label is None else f"{stem}.{artifact_label}"
    admission = ImageRepeatAdmissionRequest(
        source_path=layer.source,
        source_provenance_path=layer.source_provenance,
        source_ref=layer.source.name,
        output_dir=plan.run_dir,
        artifact_name=f"{output_stem}.repeat.png",
        manifest_name=f"{output_stem}.repeat.json",
        axis=axis,
        intended_behavior=layer.policy.intended_behavior,
        alpha_policy="preserve",
        coverage_policy=layer.policy.coverage_policy,
        metadata={
            "proof": "image_repeat_game_v1",
            "layer": layer.name,
            "operation": "admission",
            "automatic_repair": False,
        },
    )
    can_request_repair = True
    admitted = False
    try:
        admission_record = _success_record(await service.admit(admission))
        admitted = True
    except ImageRepeatDeterministicValidationError as error:
        admission_record = _deterministic_rejection(error)
    except ImageRepeatSemanticValidationError as error:
        admission_record = _semantic_rejection(error)
    except Exception as error:
        admission_record = _error_record(error, secrets)
        can_request_repair = False

    if admitted:
        return (
            {
                "name": layer.name,
                "source": layer.source.name,
                "coverage_policy": layer.policy.coverage_policy,
                "admission": admission_record,
                "repair_requested_explicitly": False,
                "repair": {
                    "status": "not_run",
                    "reason": "unchanged source passed deterministic and semantic admission",
                },
            },
            True,
        )

    if not can_request_repair:
        return (
            {
                "name": layer.name,
                "source": layer.source.name,
                "coverage_policy": layer.policy.coverage_policy,
                "admission": admission_record,
                "repair_requested_explicitly": False,
                "repair": {
                    "status": "not_run",
                    "reason": "admission operation failed before a typed gate result",
                },
            },
            False,
        )

    if not repair_on_rejection:
        return (
            {
                "name": layer.name,
                "source": layer.source.name,
                "coverage_policy": layer.policy.coverage_policy,
                "admission": admission_record,
                "repair_requested_explicitly": False,
                "repair": {
                    "status": "not_run",
                    "reason": "caller did not explicitly request repair after admission rejection",
                },
            },
            False,
        )

    repair = ImageRepeatRepairRequest(
        source_path=layer.source,
        source_provenance_path=layer.source_provenance,
        source_ref=layer.source.name,
        output_dir=plan.run_dir,
        artifact_name=f"{output_stem}.repaired.repeat.png",
        manifest_name=f"{output_stem}.repaired.repeat.json",
        axis=axis,
        intended_behavior=layer.policy.intended_behavior,
        prompt=layer.policy.repair_prompt,
        context_span_px=context_span_px,
        repair_span_px=repair_span_px,
        alpha_policy="preserve",
        coverage_policy=layer.policy.coverage_policy,
        metadata={
            "proof": "image_repeat_game_v1",
            "layer": layer.name,
            "operation": "explicit_repair",
            "automatic_repair": False,
        },
        timeout_seconds=timeout_seconds,
    )
    repaired = False
    try:
        repair_record = _success_record(await service.repair(repair))
        repaired = True
    except ImageRepeatDeterministicValidationError as error:
        repair_record = _deterministic_rejection(error)
    except ImageRepeatSemanticValidationError as error:
        repair_record = _semantic_rejection(error)
    except Exception as error:
        repair_record = _error_record(error, secrets)
    return (
        {
            "name": layer.name,
            "source": layer.source.name,
            "coverage_policy": layer.policy.coverage_policy,
            "admission": admission_record,
            "repair_requested_explicitly": True,
            "repair": repair_record,
        },
        repaired,
    )


def _success_record(result: ImageRepeatResult) -> dict[str, object]:
    return {
        "status": "accepted",
        "decision": result.decision,
        "artifact": Path(result.artifact_path).name,
        "artifact_provenance": Path(result.provenance_path).name,
        "manifest": Path(result.manifest_path).name,
        "manifest_provenance": Path(result.manifest_provenance_path).name,
        "period_px": result.period_px,
        "provider": result.provider,
        "model": result.model,
        "attempts": result.attempts,
        "deterministic": result.deterministic_report.model_dump(mode="json"),
        "semantic": result.semantic_review.model_dump(mode="json", exclude_none=True),
    }


def _deterministic_rejection(
    error: ImageRepeatDeterministicValidationError,
) -> dict[str, object]:
    return {
        "status": "rejected",
        "gate": "deterministic",
        "failure_codes": list(error.report.failure_codes),
        "deterministic": error.report.model_dump(mode="json"),
        "automatic_repair": False,
    }


def _semantic_rejection(error: ImageRepeatSemanticValidationError) -> dict[str, object]:
    return {
        "status": "rejected",
        "gate": "semantic",
        "verdict": error.review.verdict,
        "confidence": error.review.confidence,
        "failure_codes": list(error.review.failure_codes),
        "evidence": error.review.evidence,
        "automatic_repair": False,
    }


def _error_record(error: Exception, secrets: tuple[str, ...]) -> dict[str, object]:
    return {
        "status": "error",
        "error_type": type(error).__name__,
        "message": redact_secrets(str(error), secrets)[:2000],
    }


def _read_run_tag(run_dir: Path) -> str:
    summary_path = run_dir / "run.json"
    if summary_path.is_symlink():
        raise ValueError("run.json must not be a symlink")
    if not summary_path.is_file():
        raise ValueError("run.json is required for an image-repeat game proof")
    summary = load_recipe_run_summary(summary_path, label="run.json")
    if summary.recipe != "scrolling-preview":
        raise ValueError("run.json is not for scrolling-preview")
    if summary.run_dir != run_dir.name:
        raise ValueError("run.json run_dir does not match the requested run directory")
    tag = summary.tag
    if run_dir.name != tag:
        raise ValueError("run directory name does not match the run tag")
    return assert_safe_path_segment(tag, "run tag")


async def _run_live(
    plan: ProofPlan,
    options: CliOptions,
    config: StageGenConfig,
) -> dict[str, object]:
    api_key = config.open_router_api_key
    if api_key is None:
        raise ValueError("OpenRouter configuration was not loaded")
    base_url = config.open_router_base_url or _OPENROUTER_BASE_URL
    structured_backend = OpenRouterStructuredBackend(
        api_key=api_key,
        model=config.text_model,
        base_url=base_url,
    )
    reviewer = StructuredIntendedLoopReviewer(
        StructuredGenerationService[object](structured_backend),
        provider=structured_backend.provider,
        model=structured_backend.model,
        secrets=structured_backend.secrets,
        timeout_seconds=config.capability_timeout_s,
    )
    repair_backend = OpenRouterMaskedImageEditBackend(
        api_key=api_key,
        model=_REPAIR_MODEL,
        base_url=base_url,
    )
    try:
        service = ImageRepeatService(
            reviewer,
            repair_backend=cast(MaskedImageEditBackend, repair_backend),
        )
    except Exception:
        await reviewer.aclose()
        await repair_backend.aclose()
        raise
    async with service:
        return await execute_proof(
            plan,
            service,
            axis=options.axis,
            context_span_px=options.context_span_px,
            repair_span_px=options.repair_span_px,
            artifact_label=options.artifact_label,
            repair_on_rejection=options.repair_on_rejection,
            timeout_seconds=config.capability_timeout_s,
            secrets=(api_key,),
        )


def _parse_args(argv: Sequence[str] | None) -> CliOptions:
    parser = argparse.ArgumentParser(
        description=(
            "Prove explicit single-axis repeat admission and repair on canonical game layers."
        )
    )
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument(
        "--layer",
        action="append",
        dest="layers",
        help=(
            "Canonical layer name; repeat for multiple layers "
            "(defaults to playfield and near_foreground)."
        ),
    )
    parser.add_argument("--axis", choices=("x", "y"), default="x")
    parser.add_argument("--context-span-px", type=int, default=192)
    parser.add_argument("--repair-span-px", type=int, default=512)
    parser.add_argument(
        "--artifact-label",
        help="Safe label for a preserved proof attempt, such as regenerated-v1.",
    )
    parser.add_argument(
        "--repair-on-rejection",
        action="store_true",
        help=(
            "Explicitly request endpoint-conditioned repair after a typed admission rejection; "
            "the default is to stop at the rejection."
        ),
    )
    parser.add_argument("--report", dest="report_path", type=Path)
    parsed = parser.parse_args(argv)
    layers = tuple(cast(list[str] | None, parsed.layers) or _DEFAULT_LAYERS)
    artifact_label = cast(str | None, parsed.artifact_label)
    if artifact_label is not None and _LAYER_NAME_RE.fullmatch(artifact_label) is None:
        parser.error("--artifact-label must contain lowercase letters, digits, '_' or '-'")
    return CliOptions(
        run_dir=cast(Path, parsed.run_dir),
        layers=layers,
        axis=cast(Axis, parsed.axis),
        context_span_px=cast(int, parsed.context_span_px),
        repair_span_px=cast(int, parsed.repair_span_px),
        artifact_label=artifact_label,
        report_path=cast(Path | None, parsed.report_path),
        repair_on_rejection=cast(bool, parsed.repair_on_rejection),
    )


def main(argv: Sequence[str] | None = None) -> int:
    options = _parse_args(argv)
    secrets: tuple[str, ...] = ()
    try:
        plan = prepare_proof(options.run_dir, options.layers)
        config = load_config(
            require=(
                CapabilityName.STRUCTURED_GENERATION,
                CapabilityName.IMAGE_GENERATION,
            )
        )
        if config.open_router_api_key is not None:
            secrets = (config.open_router_api_key,)
        report = asyncio.run(_run_live(plan, options, config))
    except Exception as error:
        report = {
            "schema_version": 1,
            "kind": "image_repeat_game_proof",
            "ok": False,
            "error": _error_record(error, secrets),
        }
    safe = sanitize_for_persistence(report, secrets)
    if not isinstance(safe, dict):
        safe = {
            "schema_version": 1,
            "kind": "image_repeat_game_proof",
            "ok": False,
            "error": {"status": "error", "message": "report sanitization failed"},
        }
    if options.report_path is not None:
        try:
            atomic_write_json(options.report_path, safe)
        except Exception as error:
            safe["ok"] = False
            safe["report_write_error"] = redact_secrets(str(error), secrets)[:2000]
    print(json.dumps(safe, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if safe.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
