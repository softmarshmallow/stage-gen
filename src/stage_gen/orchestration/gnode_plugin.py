"""Stage Gen's gnode plugin: the first-party routes, and the adapters that call them.

gnode composes its command line from ``gnode.plugins`` entry points. This one contributes
the image routes Stage Gen has verified (``image.generate`` and ``image.edit`` on OpenAI,
fal and OpenRouter), priced and featured from the same catalog the asset pipelines plan
against, and, when a run is live, the capability handlers that call them through the
routed image service: the one retry owner, the credential admission and the exact-route
check that every Stage Gen image call already goes through.

It also contributes ``video.generate`` on fal's first-and-last-frame route, as a long
job: one submission to fal's queue, whose handle gnode keeps, so a run that stops while
the clip renders collects it next time instead of paying for it again.
"""

from __future__ import annotations

import base64
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import yaml

from gnode import (
    CallRecord,
    CallRefused,
    CapabilityHandler,
    FileValue,
    ImageGenerationRequest,
    ImageReference,
    ImageRouteRequirementsV1,
    JobLog,
    LongJob,
    NonRetryableError,
    Plugin,
    Route,
    RoutePrice,
    RouteTable,
    Store,
    VideoGenerationRequest,
    VideoReference,
    retry_with_backoff,
)
from gnode.providers.fal import (
    FAL_ENDPOINT_VIDEO_MODEL,
    FalEndpointVideoBackend,
    FalVideoJobFailed,
)
from stage_gen.config import StageGenConfig, load_config
from stage_gen.image_product import ImageProvider
from stage_gen.media.video import probe_video, scratch_clip
from stage_gen.model_routes import (
    configured_image_route_catalog,
    image_policy_id_for,
    resolve_image_route,
)
from stage_gen.orchestration.image_routing import RoutedImageGenerationService

#: How long one edit may take before the service gives up on it.
_TIMEOUT_SECONDS = 600

#: Each catalog variant, and the gnode capability that serves it.
_CAPABILITIES = {"generation": "image.generate", "edit": "image.edit"}
#: Catalog features, in the names workflows write under ``requires:``.
_FEATURE_NAMES = {
    "masked_edit": "mask",
    "transparent_background": "alpha",
    "data_url_reference_input": "image_input",
    "reference_images": "image_input",
}

ImageServiceFactory = Callable[[StageGenConfig], RoutedImageGenerationService]


class _NotSent(ValueError):
    """A call refused before any request left: its hold is released, not charged."""


def image_routes(config: StageGenConfig) -> RouteTable:
    """Every verified image route, as gnode prices and checks it offline."""

    routes = []
    for contract in configured_image_route_catalog(config).routes:
        capability = _CAPABILITIES.get(contract.operation_variant)
        if capability is None:
            continue
        features = set(contract.features)
        features |= {_FEATURE_NAMES[f] for f in contract.features if f in _FEATURE_NAMES}
        routes.append(
            Route(
                capability=capability,
                model=contract.model.model,
                provider=contract.model.provider,
                price=RoutePrice(contract.estimated_cost_low_usd, contract.estimated_cost_high_usd),
                features=frozenset(features),
                requests_per_minute=(
                    contract.requests_per_minute
                    if contract.rate_limit_owner == "scheduler"
                    else None
                ),
                contract={
                    "route_id": contract.route_id,
                    "adapter": contract.adapter_id,
                    "adapter_behavior": contract.adapter_behavior_version,
                    "surface": contract.surface,
                },
            )
        )
    return RouteTable(routes)


def _data_url(file: FileValue) -> str:
    if file.location is None:
        raise _NotSent(f"{file.name} has no bytes to send")
    data = Path(file.location).read_bytes()
    media = file.kind if file.kind.startswith("image/") else "image/png"
    return f"data:{media};base64,{base64.b64encode(data).decode('ascii')}"


def _image_handler(
    config: StageGenConfig, store: Store, factory: ImageServiceFactory, variant: str
) -> CapabilityHandler:
    async def handle(route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
        del take
        try:
            return await _call(route, request)
        except _NotSent as error:
            raise CallRefused(str(error)) from error

    async def _call(route: Route, request: Mapping[str, Any]) -> CallRecord:
        prompt = request.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise _NotSent("an image call needs its prompt as text")
        references = [
            *([request["image"]] if isinstance(request.get("image"), FileValue) else []),
            *[item for item in request.get("references") or [] if isinstance(item, FileValue)],
        ]
        mask = request.get("mask") if isinstance(request.get("mask"), FileValue) else None
        background = str(request.get("background") or "auto")
        size = request.get("size")
        requirements = ImageRouteRequirementsV1(
            operation_variant=variant,  # type: ignore[arg-type]
            background=background,  # type: ignore[arg-type]
            output_format="png",
            size=str(size) if size else None,
            reference_count=len(references),
            mask_present=mask is not None,
        )
        try:
            binding = resolve_image_route(
                requirements,
                policy_id=image_policy_id_for(requirements),
                provider_override=ImageProvider(route.provider),
                model_override=route.model,
                catalog=configured_image_route_catalog(config),
            )
        except ValueError as error:
            raise _NotSent(f"{route.route_id} cannot serve this call: {error}") from error
        if (binding.route.model.model, binding.route.model.provider) != (
            route.model,
            route.provider,
        ):
            raise _NotSent(f"{route.route_id} resolved to a different route")
        with tempfile.TemporaryDirectory(prefix="gnode-image-") as scratch:
            async with factory(config) as images:
                result = await images.generate(
                    ImageGenerationRequest(
                        prompt=prompt,
                        artifact_path=Path(scratch) / "image.png",
                        input_references=tuple(
                            ImageReference(_data_url(item), f"reference-{index}")
                            for index, item in enumerate(references)
                        ),
                        mask_reference=None
                        if mask is None
                        else ImageReference(_data_url(mask), "mask"),
                        background=background,  # type: ignore[arg-type]
                        output_format="png",
                        size=str(size) if size else None,
                        timeout_seconds=_TIMEOUT_SECONDS,
                        resolved_binding=binding,
                    )
                )
        image = store.put_bytes(result.data, kind="image/png", name="image")
        usage = result.response_metadata.usage or {}
        cost = usage.get("cost")
        reported = (
            float(cost) if isinstance(cost, int | float) and not isinstance(cost, bool) else None
        )
        # No reported cost keeps the whole worst case charged: never less than it may have cost.
        return CallRecord({"image": image}, {"attempts": result.attempts}, reported)

    return handle


def image_capabilities(
    config: StageGenConfig,
    store: Store,
    *,
    factory: ImageServiceFactory = RoutedImageGenerationService,
) -> dict[str, CapabilityHandler]:
    """The live handlers: credentials are checked when a call is made, never before."""

    return {
        "image.generate": _image_handler(config, store, factory, "generation"),
        "image.edit": _image_handler(config, store, factory, "edit"),
    }


# ----------------------------------------------------------------------------- video

#: fal's published price per second of clip, by resolution, read on 2026-09-15 from
#: https://fal.ai/models/google/gemini-omni-flash/v1.1/image-to-video; the worst case
#: carries a quarter more, for what a published price does not promise.
_VIDEO_PRICE_PER_SECOND = {"360p": 0.03, "720p": 0.10, "1080p": 0.15, "4k": 0.30}
_VIDEO_MARGIN = 1.25
#: Whole seconds the route draws, and the longest prompt it takes.
_VIDEO_SECONDS = range(3, 11)
_VIDEO_PROMPT_CHARS = 20_000
_VIDEO_ASPECTS = {"9:16", "16:9"}
_VIDEO_SHORT_SIDE = {"360p": 360, "720p": 720, "1080p": 1080, "4k": 2160}
#: How long one run waits for a submitted clip before leaving it to the next run.
_VIDEO_COLLECT_SECONDS = 1_500

VideoQueueFactory = Callable[[StageGenConfig], FalEndpointVideoBackend]


def video_routes() -> list[Route]:
    """The first-and-last-frame clip route, priced per second by resolution."""

    tiers = {
        name: (price, round(price * _VIDEO_MARGIN, 6))
        for name, price in _VIDEO_PRICE_PER_SECOND.items()
    }
    return [
        Route(
            capability="video.generate",
            model=FAL_ENDPOINT_VIDEO_MODEL,
            provider="fal",
            price=RoutePrice(
                min(low for low, _ in tiers.values()),
                max(high for _, high in tiers.values()),
                unit="second",
                max_units=max(_VIDEO_SECONDS),
                by="resolution",
                tiers=tiers,
            ),
            features=frozenset({"first_last_frame"}),
            concurrency=1,
            contract={"adapter": "fal-queue", "adapter_behavior": 1},
        )
    ]


def _video_queue(config: StageGenConfig) -> FalEndpointVideoBackend:
    if not config.fal_key:
        raise _NotSent("FAL_KEY is not set")
    return FalEndpointVideoBackend(
        api_key=config.fal_key, base_url=config.fal_base_url or "https://fal.run"
    )


def _video_request(request: Mapping[str, Any]) -> VideoGenerationRequest:
    """The clip asked for, or ``_NotSent`` naming what this route cannot draw."""

    prompt = request.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise _NotSent("a clip needs its prompt as text")
    if len(prompt) > _VIDEO_PROMPT_CHARS:
        raise _NotSent(f"the prompt is longer than {_VIDEO_PROMPT_CHARS} characters")
    first, last = request.get("first_frame"), request.get("last_frame")
    if not isinstance(first, FileValue):
        raise _NotSent("this route draws from a first frame")
    seconds = request.get("duration")
    if not isinstance(seconds, int | float) or seconds not in _VIDEO_SECONDS:
        raise _NotSent(f"this route draws whole seconds from 3 to 10, not {seconds}")
    resolution, aspect = request.get("resolution", "720p"), request.get("aspect_ratio", "9:16")
    if resolution not in _VIDEO_PRICE_PER_SECOND or aspect not in _VIDEO_ASPECTS:
        raise _NotSent(f"this route draws no {resolution} clip at {aspect}")
    start = VideoReference(_data_url(first), "first_frame")
    end = VideoReference(_data_url(last), "last_frame") if isinstance(last, FileValue) else None
    return VideoGenerationRequest(
        prompt=prompt,
        artifact_path="video.mp4",
        start_frame=start,
        end_frame=end,
        duration_seconds=float(seconds),
        resolution=resolution,
        aspect_ratio=str(aspect),
    )


async def _checked_clip(data: bytes, request: VideoGenerationRequest) -> dict[str, Any]:
    """The clip's size and length, refused unless they are what was asked for."""

    async with scratch_clip(data) as path:
        probe = await probe_video(path)
    short = _VIDEO_SHORT_SIDE[str(request.resolution)]
    size = (short, short * 16 // 9) if request.aspect_ratio == "9:16" else (short * 16 // 9, short)
    if (probe.width, probe.height) != size:
        raise ValueError(f"the clip is {probe.width}x{probe.height}, not {size[0]}x{size[1]}")
    seconds = float(request.duration_seconds or 0)
    if abs(probe.duration_seconds - seconds) > 1 / probe.frames_per_second + 0.01:
        raise ValueError(f"the clip runs {probe.duration_seconds:.3f} s, not {seconds:g} s")
    return {
        "width": probe.width,
        "height": probe.height,
        "duration_seconds": round(probe.duration_seconds, 6),
        "fps": round(probe.frames_per_second, 6),
    }


def video_job(
    config: StageGenConfig, store: Store, *, factory: VideoQueueFactory = _video_queue
) -> LongJob:
    """``video.generate`` on fal's queue: submitted once, collected, then checked.

    The submission alone is retried, and only when fal answered that it took nothing.
    A job fal failed, or a clip of the wrong size or length, fails the step: drawing
    again is a new paid job, which the next run makes only because someone ran it.
    """

    async def start(route: Route, request: Mapping[str, Any], take: int, log: JobLog) -> CallRecord:
        del route, take
        try:
            clip = _video_request(request)
            backend = factory(config)
        except _NotSent as error:
            raise CallRefused(str(error)) from error

        async def submit(_: object) -> dict[str, str]:
            log.submitting()
            try:
                return await backend.submit(clip)
            except NonRetryableError as error:
                if error.code != "video_submission_uncertain":
                    log.settled()
                raise
            except Exception:
                log.settled()  # fal answered, and took nothing
                raise

        try:
            handle = await retry_with_backoff(submit, label="fal video submission")
            log.submitted(handle)
            return await _collect(backend, clip, handle, log)
        finally:
            await backend.aclose()

    async def collect(
        route: Route,
        request: Mapping[str, Any],
        take: int,
        handle: Mapping[str, Any],
        log: JobLog,
    ) -> CallRecord:
        del route, take
        backend = factory(config)
        try:
            return await _collect(backend, _video_request(request), handle, log)
        finally:
            await backend.aclose()

    async def _collect(
        backend: FalEndpointVideoBackend,
        clip: VideoGenerationRequest,
        handle: Mapping[str, Any],
        log: JobLog,
    ) -> CallRecord:
        try:
            video = await backend.collect(handle, deadline_seconds=_VIDEO_COLLECT_SECONDS)
            facts = await _checked_clip(video.data, clip)
        except (FalVideoJobFailed, ValueError) as error:
            if not isinstance(error, NonRetryableError):
                log.settled()  # the job is over: nothing is left to collect
            raise
        file = store.put_bytes(video.data, kind="video/mp4", name="video")
        cost = (video.response_metadata.usage or {}).get("cost")
        reported = (
            float(cost) if isinstance(cost, int | float) and not isinstance(cost, bool) else None
        )
        data = {"request_id": handle.get("request_id"), "facts": facts}
        return CallRecord({"video": file}, data, reported)

    return LongJob(start, collect)


def published_workflows() -> dict[str, Path]:
    """Every first-party workflow written as a workflow file, by id."""

    root = Path(__file__).resolve().parent.parent / "workflows"
    found: dict[str, Path] = {}
    for path in sorted(root.glob("*/workflow.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        found[str(document["id"])] = path
    return found


def plugin() -> Plugin:
    """The ``gnode.plugins`` entry point."""

    config = load_config()
    return Plugin(
        name="stage_gen",
        routes=image_routes(config).merged(RouteTable(video_routes())),
        capabilities=lambda store: {
            **image_capabilities(config, store),
            "video.generate": video_job(config, store),
        },
        workflows=published_workflows(),
    )


__all__ = [
    "image_capabilities",
    "image_routes",
    "plugin",
    "published_workflows",
    "video_job",
    "video_routes",
]
