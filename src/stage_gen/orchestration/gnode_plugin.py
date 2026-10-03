"""Stage Gen's gnode plugin: the first-party routes, and the adapters that call them.

gnode composes its command line from ``gnode.plugins`` entry points. This one contributes
the image routes Stage Gen has verified (``image.generate`` and ``image.edit`` on OpenAI,
fal and OpenRouter), priced and featured from the same catalog the asset pipelines plan
against, and, when a run is live, the capability handlers that call them through the
routed image service: the one retry owner, the credential admission and the exact-route
check that every Stage Gen image call already goes through.

It also contributes ``video.generate`` on fal's first-and-last-frame route, as a long
job: one submission to fal's queue, whose handle gnode keeps, so a run that stops while
the clip renders collects it next time instead of paying for it again; and
``structured.generate`` on the configured text model through OpenRouter, whose answer is
held to the step's JSON Schema inside the structured service's one retry owner.
"""

from __future__ import annotations

import base64
import io
import json
import tempfile
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema
import yaml
from PIL import Image

from gnode import (
    BinaryArtifact,
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
    StructuredGenerationRequest,
    StructuredOutputSchema,
    StructuredReference,
    VideoGenerationRequest,
    VideoReference,
    canonicalize_strict_json_schema,
    retry_with_backoff,
)
from gnode.providers.fal import (
    FAL_ENDPOINT_VIDEO_MODEL,
    FalEndpointVideoBackend,
    FalVideoJobFailed,
)
from gnode.providers.openrouter import (
    OpenRouterProviderRouting,
    OpenRouterStructuredRequestPolicy,
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
from stage_gen.orchestration.runtime import create_structured_service
from stage_gen.orchestration.services import OPENROUTER_BASE_URL
from stage_gen.pipeline.structured_transport import (
    decode_completion_wrapper,
    inline_local_schema_refs,
    known_cost,
)

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


def _opaque(artifact: BinaryArtifact) -> dict[str, Any]:
    """An opaque picture was asked for: a pixel with any transparency draws it again."""

    with Image.open(io.BytesIO(artifact.data)) as picture:
        if picture.convert("RGBA").getchannel("A").getextrema() != (255, 255):
            raise ValueError("the picture asked for as opaque has transparent pixels")
    return {"opaque": True}


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
                        validate=_opaque if background == "opaque" else None,
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


# ------------------------------------------------------------------------ structured

#: The configured text model's price per call on OpenRouter, from its universe calibration
#: (2026-09-02): a call is cents unless it is long, and the dearest seen stayed under 0.60.
_STRUCTURED_PRICE = RoutePrice(0.02, 0.60)
_STRUCTURED_MAX_TOKENS = 16_000
_STRUCTURED_TIMEOUT_SECONDS = 1_800
#: The long edge a picture in a call's context is reduced to before it is sent.
_CONTEXT_LONG_EDGE = 1_600

StructuredServiceFactory = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class _StructuredRoute:
    """One structured model on OpenRouter, with the request settings it is called with."""

    price: RoutePrice
    #: Reasoning, image detail and provider routing; they change the answer, so they are
    #: part of the route's identity.
    policy: OpenRouterStructuredRequestPolicy | None = None
    #: Pictures are reduced to this long edge and flattened onto the step's matte; ``None``
    #: sends each picture's file exactly as it is.
    long_edge: int | None = _CONTEXT_LONG_EDGE
    timeout_seconds: float = _STRUCTURED_TIMEOUT_SECONDS

    def contract(self) -> dict[str, Any]:
        contract: dict[str, Any] = {"adapter": "openrouter-structured", "adapter_behavior": 1}
        if self.policy is not None:
            contract["request_policy"] = self.policy.snapshot()
        if self.long_edge is None:
            contract["pictures"] = "unchanged"
        return contract


#: Structured models verified beyond the configured text model. The vision judge reads a
#: portrait at high detail with high reasoning, through OpenAI only, and is shown every
#: picture as it is: the face workflow's admission, geometry and still review were
#: calibrated on it (2026-09-13). A call cost USD 0.07 to 0.39 then; the worst case keeps the
#: reservation those runs held per attempt.
_VERIFIED_STRUCTURED = {
    "openai/gpt-6-astra": _StructuredRoute(
        price=RoutePrice(0.05, 1.50),
        policy=OpenRouterStructuredRequestPolicy(
            reasoning_effort="high",
            image_detail="high",
            provider=OpenRouterProviderRouting(only=("openai",), allow_fallbacks=False),
        ),
        long_edge=None,
        timeout_seconds=900,
    ),
}


def _structured_table(config: StageGenConfig) -> dict[str, _StructuredRoute]:
    """Every structured model by name: the configured text model, then the verified ones."""

    return {config.text_model: _StructuredRoute(_STRUCTURED_PRICE), **_VERIFIED_STRUCTURED}


def structured_routes(config: StageGenConfig) -> list[Route]:
    """Each structured model, answering to a JSON Schema, with pictures in its context."""

    return [
        Route(
            capability="structured.generate",
            model=model,
            provider="openrouter",
            price=settings.price,
            features=frozenset({"structured_output", "image_input"}),
            concurrency=4,
            contract=settings.contract(),
        )
        for model, settings in _structured_table(config).items()
    ]


def _context_picture(file: FileValue, matte: str, long_edge: int | None) -> StructuredReference:
    """A picture of the context as a data URL: the file itself, or reduced to ``long_edge``
    and flattened onto ``matte`` as a PNG."""

    if file.location is None:
        raise _NotSent(f"{file.name} has no bytes to send")
    if long_edge is None:
        return StructuredReference(_data_url(file), file.name)
    with Image.open(file.location) as opened:
        picture = opened.convert("RGBA")
    picture.thumbnail((long_edge, long_edge), Image.Resampling.LANCZOS)
    ground = Image.new("RGBA", picture.size, matte)
    ground.alpha_composite(picture)
    buffer = io.BytesIO()
    ground.convert("RGB").save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return StructuredReference(f"data:image/png;base64,{encoded}", file.name)


def _context_text(file: FileValue) -> str:
    if file.location is None:
        raise _NotSent(f"{file.name} has no bytes to send")
    return f"--- {file.name} ---\n{Path(file.location).read_text(encoding='utf-8')}"


@dataclass(frozen=True, slots=True)
class StructuredQuestion:
    """One structured call as the model is asked it: the prompt with its text context
    after it, the system prompt, the JSON Schema the answer is held to, the pictures in
    the order they are shown, and the most tokens the answer may take."""

    prompt: str
    system: str | None
    schema: dict[str, Any]
    name: str
    pictures: tuple[FileValue, ...]
    matte: str
    max_tokens: int

    @classmethod
    def of(cls, request: Mapping[str, Any]) -> StructuredQuestion:
        prompt = request.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise _NotSent("a structured call needs its prompt as text")
        schema_file = request.get("schema")
        if not isinstance(schema_file, FileValue) or schema_file.location is None:
            raise _NotSent("a structured call needs its schema as a JSON file")
        schema = json.loads(Path(schema_file.location).read_text(encoding="utf-8"))
        if not isinstance(schema, dict):
            raise _NotSent("a structured call's schema is a JSON object")
        context = [f for f in request.get("context") or [] if isinstance(f, FileValue)]
        texts = [_context_text(f) for f in context if not f.kind.startswith("image")]
        name = str(schema.get("title") or Path(schema_file.name).stem)
        system = request.get("system")
        return cls(
            prompt="\n\n".join([prompt, *texts]),
            system=system if isinstance(system, str) and system.strip() else None,
            schema=schema,
            name="".join(c if c.isalnum() else "_" for c in name)[:64],
            pictures=tuple(f for f in context if f.kind.startswith("image")),
            matte=str(request.get("matte") or "#ffffff"),
            max_tokens=int(request.get("max_tokens") or _STRUCTURED_MAX_TOKENS),
        )

    def sent_schema(self) -> dict[str, Any]:
        """The schema as the provider is sent it: local references inlined, canonical."""

        return canonicalize_strict_json_schema(inline_local_schema_refs(self.schema))


def structured_job(
    config: StageGenConfig,
    store: Store,
    *,
    factory: StructuredServiceFactory = create_structured_service,
) -> CapabilityHandler:
    """``structured.generate``: one answer held to the step's JSON Schema.

    The schema check runs inside the structured service's retry owner, so an answer that
    does not fit is drawn again there; what the answer means is the workflow's judges' to
    say. Pictures in ``context`` are reduced and shown; text and JSON follow the prompt.
    """

    del store
    table = _structured_table(config)

    async def handle(route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
        del take
        settings = table.get(route.model)
        try:
            if settings is None or settings.contract() != dict(route.contract):
                raise _NotSent(f"{route.route_id} is not a structured route Stage Gen calls")
            ask = StructuredQuestion.of(request)
            pictures = tuple(
                _context_picture(f, ask.matte, settings.long_edge) for f in ask.pictures
            )
            if not config.open_router_api_key:
                raise _NotSent("OPENROUTER_API_KEY is not set")
        except _NotSent as error:
            raise CallRefused(str(error)) from error
        schema = ask.schema
        validator = jsonschema.Draft202012Validator(schema)

        def parse(value: object) -> object:
            decoded = decode_completion_wrapper(value, Counter())
            problems = sorted(validator.iter_errors(decoded), key=lambda e: list(e.path))
            if problems:
                where = "/".join(str(part) for part in problems[0].path) or "the answer"
                raise ValueError(f"{where}: {problems[0].message}"[:500])
            return decoded

        service = factory(
            api_key=config.open_router_api_key,
            model=route.model,
            base_url=config.open_router_base_url or OPENROUTER_BASE_URL,
            request_policy=settings.policy,
        )
        try:
            with tempfile.TemporaryDirectory(prefix="gnode-structured-") as scratch:
                result = await service.generate(
                    StructuredGenerationRequest(
                        prompt=ask.prompt,
                        system=ask.system,
                        references=pictures,
                        artifact_path=Path(scratch) / "answer.json",
                        schema=StructuredOutputSchema(
                            name=ask.name,
                            json_schema=inline_local_schema_refs(schema),
                            description=str(schema.get("description") or "") or None,
                        ),
                        parse=parse,
                        max_tokens=ask.max_tokens,
                        timeout_seconds=settings.timeout_seconds,
                    )
                )
        finally:
            await service.aclose()
        data = {"json": result.value, "attempts": result.attempts}
        return CallRecord({}, data, known_cost(result.response_metadata.usage))

    return handle


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
        routes=image_routes(config).merged(
            RouteTable([*video_routes(), *structured_routes(config)])
        ),
        capabilities=lambda store: {
            **image_capabilities(config, store),
            "video.generate": video_job(config, store),
            "structured.generate": structured_job(config, store),
        },
        workflows=published_workflows(),
    )


__all__ = [
    "StructuredQuestion",
    "image_capabilities",
    "image_routes",
    "plugin",
    "published_workflows",
    "structured_job",
    "structured_routes",
    "video_job",
    "video_routes",
]
