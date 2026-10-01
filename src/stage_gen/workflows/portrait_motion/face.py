"""Contained face-motion workflow around the existing N-card graph.

Each provider graph owns its immutable plan, retries, receipts, and provenance.
This parent owns the original canvas, deterministic crop, and offset-only output.
It never repairs a refused child decision or resubmits an ambiguous provider job.
"""

from __future__ import annotations

import importlib.metadata
import io
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from gnode import (
    ArtifactProvenance,
    ImageGenerationService,
    StructuredGenerationService,
    atomic_write_json,
    sha256_hex,
    write_graph,
)
from stage_gen.components.portrait_motion import PortraitMotionSpec
from stage_gen.components.portrait_motion.face_crop import Transform, create_working_crop
from stage_gen.components.portrait_motion.face_playback import (
    build_face_combinations,
    encode_face_preview,
)
from stage_gen.components.portrait_motion.models import PortraitMotionResult
from stage_gen.components.portrait_motion.nodes import STAGES
from stage_gen.components.portrait_motion.processing import png_bytes
from stage_gen.components.portrait_motion.storage import RunStore, json_bytes
from stage_gen.config import StageGenConfig

from . import pipeline as core
from .face_location import (
    BUDGET_USD,
    ROUTE_MODEL,
    load_locator_plan,
    prepare_locator,
    run_locator,
    verify_locator,
)
from .services import PortraitServiceFactory

KIND = "portrait-face-motion-plan-v1"
PADDING_FRACTION = 0.35
REQUIRED_STAGES = ["face_location", "face_crop", *STAGES, "face_reconstruction"]


def _face_spec(spec: PortraitMotionSpec) -> None:
    if spec.width != spec.height or spec.columns != spec.rows:
        raise ValueError("Face working canvas and atlas cards must be square")


def is_face_run(run: Path) -> bool:
    return RunStore(run, tool=core.TOOL).read("plan.json").get("kind") == KIND


def _picture(path: Path) -> Image.Image:
    with Image.open(io.BytesIO(path.read_bytes())) as image:
        image.load()
        if image.format != "PNG" or image.mode not in {"RGB", "RGBA"}:
            raise ValueError("Face motion requires an RGB or RGBA PNG")
        if max(image.size) > 16383:
            raise ValueError("Original canvas exceeds the native WebP dimension limit")
        return image.copy()


def prepare_face_run(
    source: Path,
    run: Path,
    spec: PortraitMotionSpec,
    profile: core.RuntimeProfile | None = None,
    *,
    config: StageGenConfig | None = None,
) -> dict[str, Any]:
    """Prepare both route contracts offline; face location occurs only during run."""
    _face_spec(spec)
    profile, config = profile or core.RuntimeProfile(), config or StageGenConfig()
    if source.absolute().resolve() != source.absolute():
        raise ValueError("Source must not traverse a symlink")
    sidecar = Path(str(source) + ".meta.json")
    if sidecar.is_symlink():
        raise ValueError("Source provenance must not be a symlink")
    data = source.read_bytes()
    origin = ArtifactProvenance.model_validate_json(sidecar.read_bytes())
    if (
        origin.artifact is None
        or origin.artifact.sha256 != sha256_hex(data)
        or origin.artifact.bytes != len(data)
    ):
        raise ValueError("Source must have matching canonical provenance")
    picture = _picture(source)
    origin_document = origin.model_dump(mode="json")
    plan = {
        "schema_version": 1,
        "kind": KIND,
        "source": {
            "ref": "inputs/source.png",
            "sha256": sha256_hex(data),
            "origin_sha256": sha256_hex(json_bytes(origin_document)),
            "size": list(picture.size),
        },
        "spec": spec.model_dump(mode="json"),
        "profile": profile.model_dump(mode="json"),
        "image_routing": core._image_routing_snapshot(config),
        "request_policy": core.request_policy().snapshot(),
        "implementation": core.implementation(),
        "dependencies": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "scipy", "pillow", "pydantic", "httpx")
        },
        "padding_fraction": PADDING_FRACTION,
        "required_stages": REQUIRED_STAGES,
        "image_jobs": 1,
        "structured_jobs": 4,
        "max_service_attempts": 6,
        "semantic_regenerations": 0,
        "locator_budget_usd": BUDGET_USD,
        "publication_authorized": False,
    }
    # The inner source is not known yet. This graph seals its route requirements,
    # not a promise that the complete sprite will be submitted to repainting.
    graph = core.graph_for(plan)
    store = RunStore(run, tool=core.TOOL)
    store.root.mkdir(parents=True, exist_ok=False)
    store.write_json(
        "inputs/source-origin.json",
        origin_document,
        inputs=[],
        params={},
        prompt="Preserve original source provenance and rights.",
    )
    store.write(
        "inputs/source.png",
        data,
        "image/png",
        inputs=["inputs/source-origin.json"],
        params={"ownership": "run_input_import"},
        prompt="Import unchanged original pixels into the face-motion run.",
        rights=origin.rights,
    )
    prepare_locator(store.path("inputs/source.png"), store.path("locator"))
    plan["locator_plan_sha256"] = store.digest("locator/plan.json")
    # Include the locator identity in the sealed parent preflight graph as well.
    graph = core.graph_for(plan)
    atomic_write_json(store.path("plan.json"), plan)
    write_graph(store.path("route-preflight.json"), graph)
    return {
        "status": "prepared",
        "required_stages": REQUIRED_STAGES,
        "source_size": list(picture.size),
        "working_size": [spec.width, spec.height],
        "max_provider_operations": 6 + profile.max_provider_operations,
        "budget_usd": BUDGET_USD + profile.budget_usd,
    }


def load_face_plan(run: Path) -> tuple[RunStore, dict[str, Any], core.PortraitMotionGraph]:
    store = RunStore(run, tool=core.TOOL)
    plan = store.read("plan.json")
    if (plan.get("schema_version"), plan.get("kind")) != (1, KIND):
        raise ValueError("Unsupported face-motion plan")
    if plan["implementation"] != core.implementation():
        raise ValueError("Implementation changed after preparation; prepare a fresh run")
    if (
        plan["request_policy"] != core.request_policy().snapshot()
        or plan["required_stages"] != REQUIRED_STAGES
        or plan["padding_fraction"] != PADDING_FRACTION
        or plan["locator_budget_usd"] != BUDGET_USD
        or plan["publication_authorized"] is not False
    ):
        raise ValueError("Prepared face-motion policy changed")
    expected_dependencies = {
        name: importlib.metadata.version(name)
        for name in ("numpy", "scipy", "pillow", "pydantic", "httpx")
    }
    if plan["dependencies"] != expected_dependencies:
        raise ValueError("Prepared runtime dependencies changed")
    for ref in ("inputs/source.png", "inputs/source-origin.json"):
        store.verify_artifact(ref)
    if (
        plan["source"]["ref"] != "inputs/source.png"
        or store.digest("inputs/source.png") != plan["source"]["sha256"]
        or store.digest("inputs/source-origin.json") != plan["source"]["origin_sha256"]
        or list(_picture(store.path("inputs/source.png")).size) != plan["source"]["size"]
    ):
        raise ValueError("Prepared original changed")
    spec = PortraitMotionSpec.model_validate(plan["spec"])
    _face_spec(spec)
    graph = core.graph_for(plan)
    if (
        core.PortraitMotionGraph.model_validate_json(
            store.path("route-preflight.json").read_bytes()
        )
        != graph
    ):
        raise ValueError("Prepared route preflight changed")
    locator_store, locator_plan, _ = load_locator_plan(store.path("locator"))
    if (
        store.digest("locator/plan.json") != plan["locator_plan_sha256"]
        or locator_plan["source"]["sha256"] != plan["source"]["sha256"]
        or locator_store.read("inputs/source-origin.json")
        != ArtifactProvenance.model_validate_json(
            store.path("inputs/source.png.meta.json").read_bytes()
        ).model_dump(mode="json")
    ):
        raise ValueError("Prepared locator input or plan changed")
    return store, plan, graph


def _crop(
    store: RunStore,
    plan: dict[str, Any],
    location: dict[str, Any],
    *,
    write: bool,
) -> Transform:
    source = _picture(store.path("inputs/source.png"))
    box = [
        value * source.size[index % 2] / 1000 for index, value in enumerate(location["bbox_xyxy"])
    ]
    spec = PortraitMotionSpec.model_validate(plan["spec"])
    work, transform = create_working_crop(
        source,
        box,
        (spec.width, spec.height),
        PADDING_FRACTION,
    )
    artifacts = {
        "crop/transform.json": (json_bytes(transform), "application/json"),
        "crop/work.png": (png_bytes(work), "image/png"),
    }
    rights = ArtifactProvenance.model_validate_json(
        store.path("inputs/source.png.meta.json").read_bytes()
    ).rights
    for ref, (data, media_type) in artifacts.items():
        if write and not store.path(ref).exists():
            store.write(
                ref,
                data,
                media_type,
                inputs=["inputs/source.png", "locator/locator/location.json"],
                params={"padding_fraction": PADDING_FRACTION},
                prompt="Deterministically crop the located face; retain inverse coordinates.",
                rights=rights,
            )
        store.verify_artifact(ref)
        if store.path(ref).read_bytes() != data:
            raise ValueError("Retained face crop differs from the located source")
    return transform


def _child(store: RunStore, plan: dict[str, Any]) -> None:
    child_store, child_plan, _ = core.load_plan(store.path("portrait"))
    if (
        child_plan["source"]["sha256"] != store.digest("crop/work.png")
        or child_plan["spec"] != plan["spec"]
        or child_plan["profile"] != plan["profile"]
        or child_plan["image_routing"] != plan["image_routing"]
    ):
        raise ValueError("Inner portrait run does not belong to the prepared face crop")
    expected_origin = ArtifactProvenance.model_validate_json(
        store.path("crop/work.png.meta.json").read_bytes()
    ).model_dump(mode="json")
    if child_store.read("inputs/source-origin.json") != expected_origin:
        raise ValueError("Inner portrait source provenance changed")


def _result(location: dict[str, Any], inner: dict[str, Any] | None) -> dict[str, Any]:
    accepted = inner is not None and inner["status"] in {"complete", "partial"}
    result = PortraitMotionResult(
        status=inner["status"] if inner is not None else "refused",
        reason=inner["reason"]
        if inner is not None
        else "Face not locatable: " + location["reason"],
        admitted_features=inner["admitted_features"] if inner else [],
        accepted_features=inner["accepted_features"] if accepted and inner else [],
        preview_ref="render/animation.webp" if accepted else None,
        manifest_ref="render/manifest.json" if accepted else None,
        required_stages=REQUIRED_STAGES,
    ).model_dump(mode="json")
    result.update(
        face_location_ref="locator/locator/location.json",
        portrait_run_ref="portrait" if inner is not None else None,
    )
    return result


def _output_refs(spec: PortraitMotionSpec, features: list[str]) -> list[str]:
    eyes = ["rest", *(s.state_id for s in spec.states if s.feature_group == "eyes")]
    mouths = ["rest", *(s.state_id for s in spec.states if s.feature_group == "mouth")]
    return [
        *[
            f"render/patches/{s.state_id}-{f}.png"
            for s in spec.states
            for f in features
            if s.feature_group == ("mouth" if f == "mouth" else "eyes")
        ],
        *[f"render/states/{eye}--{mouth}.png" for eye in eyes for mouth in mouths],
        "render/animation.webp",
        "render/exactness.json",
        "render/manifest.json",
    ]


def _render(
    store: RunStore,
    plan: dict[str, Any],
    transform: Transform,
    inner: dict[str, Any],
) -> list[str]:
    spec = PortraitMotionSpec.model_validate(plan["spec"])
    donors = {
        state.state_id: _picture(store.path(f"portrait/registration/{state.state_id}-donor.png"))
        for state in spec.states
    }
    features = inner["accepted_features"]
    masks = {}
    for feature in features:
        with Image.open(store.path(f"portrait/composition/mask-{feature}.png")) as mask:
            masks[feature] = np.asarray(mask, dtype=np.float64) / 255
    frames = build_face_combinations(
        _picture(store.path("inputs/source.png")),
        donors,
        masks,
        spec,
        transform,
    )
    animation, playback = encode_face_preview(frames, spec)
    inputs = [
        "inputs/source.png",
        "crop/transform.json",
        "portrait/terminal/manifest.json",
        *[f"portrait/registration/{s.state_id}-donor.png" for s in spec.states],
        *[f"portrait/composition/mask-{f}.png" for f in features],
    ]
    patches, combinations = [], []
    for (state, feature), picture in frames.patches.items():
        ref = f"render/patches/{state}-{feature}.png"
        store.write(
            ref,
            png_bytes(picture),
            "image/png",
            inputs=inputs,
            params={"offset_xy": list(frames.offset_xy), "feather_already_baked": True},
            prompt="Isolate the native face patch for integer offset-only RGB placement.",
        )
        patches.append(
            {"state_id": state, "feature_id": feature, "ref": ref, "sha256": store.digest(ref)}
        )
    for (eyes, mouth), picture in frames.combinations.items():
        ref = f"render/states/{eyes}--{mouth}.png"
        store.write(
            ref,
            png_bytes(picture),
            "image/png",
            inputs=inputs,
            params={},
            prompt="Replace selected face pixels at the original offset, preserving source alpha.",
        )
        combinations.append({"eyes": eyes, "mouth": mouth, "ref": ref, "sha256": store.digest(ref)})
    store.write(
        "render/animation.webp",
        animation,
        "image/webp",
        inputs=inputs,
        params=playback,
        prompt="Encode the original-resolution states with lossless visible RGBA and held timing.",
    )
    store.write_json(
        "render/exactness.json",
        {**frames.exactness, **playback},
        inputs=inputs,
        params={},
        prompt="Record deterministic native pixel, alpha, exterior, rest, and decode checks.",
    )
    refs = _output_refs(spec, features)
    store.write_json(
        "render/manifest.json",
        {
            "schema_version": 1,
            "kind": "portrait-face-motion-v1",
            "source_ref": "inputs/source.png",
            "source_size": plan["source"]["size"],
            "transform_ref": "crop/transform.json",
            "offset_xy": list(frames.offset_xy),
            "patch_size": list(frames.crop_size),
            "features": features,
            "patches": patches,
            "combinations": combinations,
            "preview_ref": "render/animation.webp",
            "playback": playback,
            "timeline": [segment.model_dump(mode="json") for segment in spec.playback],
            "patch_application": "replace_selected_rgb_preserve_original_alpha",
            "feather_already_baked": True,
            "semantic_acceptance": "inherited_from_face_still_review",
            "temporal_review": "not_performed",
            "publication_authorized": False,
        },
        inputs=[*inputs, *refs[:-1]],
        params={},
        prompt="Describe contained native face patches and original-resolution playback.",
    )
    return refs


def _finish(store: RunStore, result: dict[str, Any], refs: list[str]) -> None:
    records = {}
    for ref in refs:
        store.verify_artifact(ref)
        for item in (ref, ref + ".meta.json"):
            records[item] = store.digest(item)
    decisions = ["locator/locator/location.json", "locator/locator/result.json"]
    if result["portrait_run_ref"] is not None:
        decisions += ["portrait/terminal/manifest.json", "portrait/terminal/result.json"]
    store.write_json(
        "terminal/result.json",
        result,
        inputs=["plan.json", *decisions, *refs],
        params={},
        prompt="Retain the face workflow terminal result without expanding child acceptance.",
    )
    store.write_json(
        "terminal/checkpoint.json",
        {"result": result, "files": records},
        inputs=["plan.json", *decisions, "terminal/result.json", *records],
        params={},
        prompt="Commit the complete local face workflow checkpoint after child verification.",
    )


def verify_face_run(run: Path) -> dict[str, Any]:
    store, plan, _ = load_face_plan(run)
    location = verify_locator(store.path("locator"))
    inner = None
    refs: list[str] = []
    if location["status"] == "located":
        transform = _crop(store, plan, location, write=False)
        _child(store, plan)
        inner = core.verify_run(store.path("portrait"))
        refs = ["crop/transform.json", "crop/work.png"]
        if inner["status"] in {"complete", "partial"}:
            refs += _output_refs(
                PortraitMotionSpec.model_validate(plan["spec"]), inner["accepted_features"]
            )
            manifest = store.read("render/manifest.json")
            if (
                manifest["features"] != inner["accepted_features"]
                or manifest["offset_xy"] != transform["crop_box_xyxy"][:2]
                or manifest["source_size"] != plan["source"]["size"]
                or manifest["temporal_review"] != "not_performed"
                or manifest["publication_authorized"] is not False
                or manifest["timeline"] != plan["spec"]["playback"]
            ):
                raise ValueError("Native manifest contradicts its child or coordinates")
    expected = _result(location, inner)
    store.verify_artifact("terminal/result.json")
    store.verify_artifact("terminal/checkpoint.json")
    checkpoint = store.read("terminal/checkpoint.json")
    if checkpoint["result"] != expected or store.read("terminal/result.json") != expected:
        raise ValueError("Terminal acceptance contradicts verified child decisions")
    records = {}
    for ref in refs:
        store.verify_artifact(ref)
        for item in (ref, ref + ".meta.json"):
            records[item] = store.digest(item)
    if checkpoint["files"] != records:
        raise ValueError("Native output checkpoint is incomplete or changed")
    return {
        **expected,
        "verified_stages": REQUIRED_STAGES if inner else ["face_location"],
        "locator": location,
        "portrait": inner,
        "provider_operations_total": location["provider_attempts"]
        + (inner["provider_operations_total"] if inner else 0),
        "reported_cost_usd": (location.get("reported_cost_usd") or 0)
        + (inner["reported_cost_usd"] if inner else 0),
    }


async def run_face_pipeline(
    run: Path,
    *,
    image_service: ImageGenerationService | None = None,
    structured_service: StructuredGenerationService[dict[str, Any]] | None = None,
    locator_service: StructuredGenerationService[dict[str, Any]] | None = None,
    live: bool = False,
    dotenv: Path | None = None,
    service_factory: PortraitServiceFactory | None = None,
) -> dict[str, Any]:
    store, plan, graph = load_face_plan(run)
    route = graph.resolved_route_for("atlas")
    for service in (structured_service, locator_service):
        if service is not None and (service.provider, service.model) != ("openrouter", ROUTE_MODEL):
            raise ValueError("Injected structured service route must match the prepared binding")
    if image_service is not None and (image_service.provider, image_service.model) != (
        route.provider,
        route.model,
    ):
        raise ValueError("Injected image service route must match the prepared binding")
    if live:
        if any(
            service is not None for service in (image_service, structured_service, locator_service)
        ):
            raise ValueError("Live composition cannot mix caller-injected services")
        if service_factory is None:
            raise ValueError("Live portrait execution requires an injected service_factory")
        # Require all downstream keys before paying to locate the face.
        service_factory.admit(plan, graph, dotenv)
    with core._run_lock(store):
        if store.path("terminal/checkpoint.json").exists():
            return {**verify_face_run(run), "provider_operations_this_invocation": 0}
        location = await run_locator(
            store.path("locator"),
            service=locator_service or structured_service,
            live=live,
            dotenv=dotenv,
            service_factory=service_factory,
        )
        if location["status"] not in {"located", "not_locatable"}:
            return {
                "status": "failed",
                "reason": "Face locator did not complete",
                "locator": location,
            }
        inner, refs = None, []
        operations = location["provider_operations_this_invocation"]
        if location["status"] == "located":
            transform = _crop(store, plan, location, write=True)
            if not store.path("portrait").exists():
                core.prepare_run(
                    store.path("crop/work.png"),
                    store.path("portrait"),
                    PortraitMotionSpec.model_validate(plan["spec"]),
                    core.RuntimeProfile.model_validate(plan["profile"]),
                    config=core._image_config(plan),
                )
            _child(store, plan)
            inner = await core.run_pipeline(
                store.path("portrait"),
                image_service=image_service,
                structured_service=structured_service,
                live=live,
                dotenv=dotenv,
                service_factory=service_factory,
            )
            operations += inner["provider_operations_this_invocation"]
            if inner["status"] == "failed":
                return {
                    **_result(location, inner),
                    "portrait": inner,
                    "provider_operations_this_invocation": operations,
                }
            refs = ["crop/transform.json", "crop/work.png"]
            if inner["status"] in {"complete", "partial"}:
                refs += _render(store, plan, transform, inner)
        _finish(store, _result(location, inner), refs)
        result = {**verify_face_run(run), "provider_operations_this_invocation": operations}
        atomic_write_json(store.path("execution.json"), result)
        return result
