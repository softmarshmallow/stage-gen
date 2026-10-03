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
    MusicGenerationRequest,
    NonRetryableError,
    Plugin,
    Route,
    RoutePrice,
    RouteTable,
    SoundEffectGenerationRequest,
    SpeechGenerationRequest,
    Store,
    StructuredGenerationRequest,
    StructuredOutputSchema,
    StructuredReference,
    ToolCall,
    ToolLoopMessage,
    ToolLoopStepRequest,
    ToolSpec,
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
    OPENROUTER_BASE_URL,
    OpenRouterProviderRouting,
    OpenRouterStructuredRequestPolicy,
    OpenRouterToolLoopBackend,
)
from gnode.providers.tripo import VIEWS as TRIPO_VIEWS
from gnode.providers.tripo import TripoBackend, TripoTaskFailed
from stage_gen.config import StageGenConfig, load_config
from stage_gen.image_product import ImageProvider
from stage_gen.media.video import probe_video, scratch_clip
from stage_gen.model_routes import (
    configured_image_route_catalog,
    image_policy_id_for,
    resolve_image_route,
)
from stage_gen.orchestration.image_routing import RoutedImageGenerationService
from stage_gen.orchestration.runtime import (
    create_music_service,
    create_sound_effect_service,
    create_speech_service,
    create_structured_service,
)
from stage_gen.orchestration.structured_transport import (
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


# ----------------------------------------------------------------------------- meshes

#: Tripo's multiview mesh and its automatic rig, verified 2026-09-11. A mesh is Tripo's
#: credits at USD 0.01 each, 120 to 250 for a textured quad mesh; a rig is 25 credits, with
#: a free riggability check before it.
_MESH_MODEL, _RIG_MODEL = "P2-20260801", "v1.0-20240301"
#: How long a run waits for a Tripo task before leaving it to the next run.
_MESH_COLLECT_SECONDS = 1_200
_RIG_COLLECT_SECONDS = 600
#: The most faces a quad mesh may ask for on the verified route.
_QUAD_FACE_LIMIT = 25_000

TripoFactory = Callable[[StageGenConfig], TripoBackend]


def mesh_routes() -> list[Route]:
    """``mesh.generate`` and ``mesh.rig`` on Tripo."""

    return [
        Route(
            capability="mesh.generate",
            model=_MESH_MODEL,
            provider="tripo",
            price=RoutePrice(1.20, 2.50),
            features=frozenset({"multiview", "textured_mesh", "quad", "pbr"}),
            concurrency=1,
            contract={"adapter": "tripo-multiview", "adapter_behavior": 1},
        ),
        Route(
            capability="mesh.rig",
            model=_RIG_MODEL,
            provider="tripo",
            price=RoutePrice(0.25, 0.50),
            features=frozenset({"biped", "rig_check", "glb_input"}),
            concurrency=1,
            contract={"adapter": "tripo-rig", "adapter_behavior": 1},
        ),
    ]


def _file_bytes(file: FileValue) -> bytes:
    assert file.location is not None
    return Path(file.location).read_bytes()


def _tripo(config: StageGenConfig) -> TripoBackend:
    if not config.tripo_api_key:
        raise _NotSent("TRIPO_API_KEY is not set")
    return TripoBackend(api_key=config.tripo_api_key)


def _mesh_views(request: Mapping[str, Any]) -> dict[str, tuple[bytes, str]]:
    views = request.get("views")
    if not isinstance(views, Mapping) or not views:
        raise _NotSent("a mesh call needs its views, by name")
    unknown = sorted(set(views) - set(TRIPO_VIEWS))
    if unknown or "front" not in views:
        raise _NotSent(f"a multiview task takes front and any of back, left, right; not {unknown}")
    found: dict[str, tuple[bytes, str]] = {}
    for name, file in views.items():
        if not isinstance(file, FileValue) or file.location is None:
            raise _NotSent(f"the {name} view has no bytes to send")
        if file.kind not in {"image/png", "image/jpeg"}:
            raise _NotSent(f"the {name} view is {file.kind}; Tripo takes PNG or JPEG")
        found[str(name)] = (Path(file.location).read_bytes(), file.kind)
    return found


def _mesh_params(request: Mapping[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {
        "quad": bool(request.get("quad", False)),
        "texture": bool(request.get("texture", True)),
        "pbr": bool(request.get("pbr", False)),
    }
    limit = request.get("face_limit")
    if limit is not None:
        if not isinstance(limit, int) or not 48 <= limit <= _QUAD_FACE_LIMIT:
            raise _NotSent(f"face_limit is 48 to {_QUAD_FACE_LIMIT}")
        params["face_limit"] = limit
    return params


def mesh_job(config: StageGenConfig, store: Store, *, factory: TripoFactory = _tripo) -> LongJob:
    """``mesh.generate`` on Tripo: views uploaded, one task posted, its model collected.

    Uploads are free and retried. The task is posted once: an uncertain post stays on
    record and stops the next run for a person; a task Tripo failed is over, and drawing
    again is a new take.
    """

    async def start(route: Route, request: Mapping[str, Any], take: int, log: JobLog) -> CallRecord:
        del take
        try:
            views = _mesh_views(request)
            params = _mesh_params(request)
            backend = factory(config)
        except _NotSent as error:
            raise CallRefused(str(error)) from error
        try:
            inputs = await backend.mesh_inputs(views)
            log.submitting()
            try:
                handle = await backend.submit_mesh(model=route.model, inputs=inputs, params=params)
            except NonRetryableError as error:
                if error.code != "tripo_submission_uncertain":
                    log.settled()
                raise
            log.submitted(handle)
            return await _collect(backend, handle, log)
        finally:
            await backend.aclose()

    async def collect(
        route: Route, request: Mapping[str, Any], take: int, handle: Mapping[str, Any], log: JobLog
    ) -> CallRecord:
        del route, request, take
        backend = factory(config)
        try:
            return await _collect(backend, handle, log)
        finally:
            await backend.aclose()

    async def _collect(backend: TripoBackend, handle: Mapping[str, Any], log: JobLog) -> CallRecord:
        try:
            result = await backend.collect(handle, deadline_seconds=_MESH_COLLECT_SECONDS)
        except (TripoTaskFailed, ValueError):
            log.settled()  # the task is over: nothing is left to collect
            raise
        files = sorted(result.files, key=lambda f: f.media_type != "model/fbx")
        if not files:
            log.settled()
            raise ValueError("the Tripo task made no model")
        chosen = files[0]
        model = store.put_bytes(chosen.data, kind=chosen.media_type, name="model")
        data = {"task_id": handle.get("task_id"), "facts": {"model_kind": chosen.media_type}}
        return CallRecord({"model": model}, data, result.cost_usd)

    return LongJob(start, collect)


def rig_job(config: StageGenConfig, store: Store, *, factory: TripoFactory = _tripo) -> LongJob:
    """``mesh.rig`` on Tripo: a free riggability check, then one rig task, collected.

    A doubted model is rigged only when the step allows it (``allow_negative_check``); the
    check's verdict is kept as facts either way.
    """

    async def start(route: Route, request: Mapping[str, Any], take: int, log: JobLog) -> CallRecord:
        del take
        model = request.get("model")
        try:
            if not isinstance(model, FileValue) or model.location is None:
                raise _NotSent("a rig call needs its model")
            if model.kind != "model/gltf-binary":
                raise _NotSent(f"Tripo rigs a GLB, not {model.kind}")
            backend = factory(config)
        except _NotSent as error:
            raise CallRefused(str(error)) from error
        rig_type = str(request.get("rig_type") or "biped")
        params = {
            "rig_type": rig_type,
            "spec": str(request.get("skeleton") or "mixamo"),
            "out_format": "glb",
        }
        glb = _file_bytes(model)
        try:
            check = await backend.check_rig(glb, deadline_seconds=_RIG_COLLECT_SECONDS)
            doubted = check["riggable"] is not True or check["rig_type"] != rig_type
            if doubted and not request.get("allow_negative_check"):
                raise CallRefused(
                    f"Tripo's check doubts this model (riggable={check['riggable']}, "
                    f"rig_type={check['rig_type']})"
                )
            log.submitting()
            try:
                handle = await backend.submit_rig(
                    model=route.model,
                    file_token=check["file_token"],
                    params={**params, "out_format": "glb"},
                )
            except NonRetryableError as error:
                if error.code != "tripo_submission_uncertain":
                    log.settled()
                raise
            handle = {
                **handle,
                "check": {k: check[k] for k in ("task_id", "riggable", "rig_type")},
                "advisory_override": doubted,
            }
            log.submitted(handle)
            return await _collect(backend, handle, log)
        finally:
            await backend.aclose()

    async def collect(
        route: Route, request: Mapping[str, Any], take: int, handle: Mapping[str, Any], log: JobLog
    ) -> CallRecord:
        del route, request, take
        backend = factory(config)
        try:
            return await _collect(backend, handle, log)
        finally:
            await backend.aclose()

    async def _collect(backend: TripoBackend, handle: Mapping[str, Any], log: JobLog) -> CallRecord:
        try:
            result = await backend.collect(handle, deadline_seconds=_RIG_COLLECT_SECONDS)
        except (TripoTaskFailed, ValueError):
            log.settled()
            raise
        glbs = [f for f in result.files if f.media_type == "model/gltf-binary"]
        if len(glbs) != 1:
            log.settled()
            raise ValueError("the Tripo rig task made no single GLB")
        rigged = store.put_bytes(glbs[0].data, kind="model/gltf-binary", name="model")
        check = handle.get("check") or {}
        facts = {
            "riggable": check.get("riggable"),
            "checked_rig_type": check.get("rig_type"),
            "advisory_override": bool(handle.get("advisory_override")),
        }
        data = {"task_id": handle.get("task_id"), "facts": facts}
        return CallRecord({"model": rigged}, data, result.cost_usd)

    return LongJob(start, collect)


# ----------------------------------------------------------------------------- agents

#: One agent turn on the vision judge's model: its tokens at USD 10 per million in and 50 per
#: million out (2026-09-11). A turn with a full picture window and a long answer stays under
#: the worst case; most cost cents.
_AGENT_PRICE = RoutePrice(0.01, 1.50)
#: A turn on the configured text model: a games' placement episode of six looks was held at
#: USD 0.60, so a turn at a tenth of a dollar.
_TEXT_AGENT_PRICE = RoutePrice(0.003, 0.10)
_AGENT_TIMEOUT_SECONDS = 600
AgentBackendFactory = Callable[..., Any]


def agent_routes(config: StageGenConfig | None = None) -> list[Route]:
    """``agent.turn`` on the verified vision judge, with its request settings, and on the
    configured text model with the provider's own defaults (the games' placement agents)."""

    model = "openai/gpt-6-astra"
    policy = _VERIFIED_STRUCTURED[model].policy
    assert policy is not None
    routes = [
        Route(
            capability="agent.turn",
            model=model,
            provider="openrouter",
            price=_AGENT_PRICE,
            features=frozenset({"tool_use", "image_input"}),
            concurrency=1,
            contract={
                "adapter": "openrouter-tool-loop",
                "adapter_behavior": 1,
                "request_policy": policy.snapshot(),
            },
        )
    ]
    text_model = (config or StageGenConfig()).text_model
    if text_model != model:
        routes.append(
            Route(
                capability="agent.turn",
                model=text_model,
                provider="openrouter",
                price=_TEXT_AGENT_PRICE,
                features=frozenset({"tool_use", "image_input"}),
                contract={"adapter": "openrouter-tool-loop", "adapter_behavior": 1},
            )
        )
    return routes


def _turn_picture(file: Any) -> str:
    if not isinstance(file, FileValue) or file.location is None:
        raise _NotSent("an agent picture has no bytes to send")
    return _data_url(file)


def _turn_messages(request: Mapping[str, Any]) -> tuple[ToolLoopMessage, ...]:
    """The transcript as the provider takes it: a tool's pictures follow its run of results
    as one user message, since only user messages carry pictures."""

    system = request.get("system")
    messages = [ToolLoopMessage("system", str(system))] if system else []
    held: list[str] = []
    for entry in request.get("messages") or []:
        role = entry.get("role")
        if role != "tool" and held:
            messages.append(ToolLoopMessage("user", "Pictures the tools returned.", tuple(held)))
            held = []
        if role == "user":
            pictures = tuple(_turn_picture(file) for file in entry.get("images") or [])
            messages.append(ToolLoopMessage("user", str(entry.get("content", "")), pictures))
        elif role == "assistant":
            calls = tuple(
                ToolCall(str(call.get("id")), str(call.get("name")), call.get("arguments") or {})
                for call in entry.get("tool_calls") or []
            )
            messages.append(
                ToolLoopMessage("assistant", str(entry.get("content") or ""), (), calls)
            )
        elif role == "tool":
            messages.append(
                ToolLoopMessage(
                    "tool",
                    str(entry.get("content", "")),
                    tool_call_id=str(entry.get("tool_call_id")),
                )
            )
            held.extend(_turn_picture(file) for file in entry.get("images") or [])
        else:
            raise _NotSent(f"an agent transcript has no {role!r} messages")
    if held:
        messages.append(ToolLoopMessage("user", "Pictures the tools returned.", tuple(held)))
    return tuple(messages)


def agent_turn_job(
    config: StageGenConfig,
    store: Store,
    *,
    factory: AgentBackendFactory = OpenRouterToolLoopBackend,
) -> CapabilityHandler:
    """``agent.turn``: one model turn of a node's agent, its tool calls returned to it."""

    del store
    routes = {route.route_id: route for route in agent_routes(config)}

    async def handle(route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
        del take
        try:
            if routes.get(route.route_id) is None or dict(routes[route.route_id].contract) != dict(
                route.contract
            ):
                raise _NotSent(f"{route.route_id} is not an agent route Stage Gen calls")
            if not config.open_router_api_key:
                raise _NotSent("OPENROUTER_API_KEY is not set")
            step = ToolLoopStepRequest(
                messages=_turn_messages(request),
                tools=tuple(
                    ToolSpec(str(t["name"]), str(t["description"]), t["parameters"])
                    for t in request.get("tools") or []
                ),
                max_tokens=request.get("max_tokens"),
                tool_choice="auto" if request.get("tool_choice") == "auto" else "required",
            )
        except (_NotSent, ValueError, KeyError) as error:
            raise CallRefused(str(error)) from error
        verified = _VERIFIED_STRUCTURED.get(route.model)
        policy = verified.policy if verified is not None else None
        backend = factory(
            api_key=config.open_router_api_key,
            model=route.model,
            base_url=config.open_router_base_url or OPENROUTER_BASE_URL,
            request_policy=policy,
        )

        async def turn(_: object) -> Any:
            return await backend.step(step)

        try:
            answered = await retry_with_backoff(
                turn, label="agent turn", timeout_s=_AGENT_TIMEOUT_SECONDS
            )
        finally:
            await backend.aclose()
        data = {
            "text": answered.text,
            "tool_calls": [
                {"id": call.call_id, "name": call.name, "arguments": dict(call.arguments)}
                for call in answered.tool_calls
            ],
        }
        return CallRecord({}, data, known_cost(answered.response_metadata.usage))

    return handle


# ----------------------------------------------------------------------------- audio

#: Each audio capability's worst case a call: a track, a short effect, a bark. Measured in
#: the runner spikes (2026-08-20 music, 2026-09-02 effects, 2026-09-03 speech).
_MUSIC_PRICE = RoutePrice(0.05, 0.50)
_SOUND_PRICE = RoutePrice(0.001, 0.10)
_SPEECH_PRICE = RoutePrice(0.001, 0.05)
_MUSIC_TIMEOUT_SECONDS, _CLIP_TIMEOUT_SECONDS = 900, 120


def audio_routes(config: StageGenConfig | None = None) -> list[Route]:
    """``music.generate``, ``sound.generate`` and ``speech.generate`` on the configured models."""

    settings = config or StageGenConfig()
    return [
        Route(
            capability="music.generate",
            model=settings.music_model,
            provider="openrouter",
            price=_MUSIC_PRICE,
            contract={"adapter": "openrouter-music", "adapter_behavior": 1},
        ),
        Route(
            capability="sound.generate",
            model=settings.sound_effect_model,
            provider="elevenlabs",
            price=_SOUND_PRICE,
            features=frozenset({"exact_duration"}),
            contract={"adapter": "elevenlabs-sound-effect", "adapter_behavior": 1},
        ),
        Route(
            capability="speech.generate",
            model=settings.speech_model,
            provider="elevenlabs",
            price=_SPEECH_PRICE,
            features=frozenset({"audio_tags", "stability"}),
            contract={"adapter": "elevenlabs-speech", "adapter_behavior": 1},
        ),
    ]


AudioServiceFactory = Callable[..., Any]


def _audio_record(store: Store, result: Any) -> CallRecord:
    audio = store.put_bytes(result.data, kind="audio/mpeg", name="audio")
    return CallRecord({"audio": audio}, {"attempts": result.attempts}, None)


def _number(request: Mapping[str, Any], name: str) -> float | None:
    value = request.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _NotSent(f"{name} is a number")
    return float(value)


def music_job(
    config: StageGenConfig, store: Store, *, factory: AudioServiceFactory = create_music_service
) -> CapabilityHandler:
    """``music.generate``: one track from its prompt; what it must be is the steps' to judge."""

    async def handle(route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
        del take
        prompt = request.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise CallRefused("a music call needs its prompt as text")
        if not config.open_router_api_key:
            raise CallRefused("OPENROUTER_API_KEY is not set")
        service = factory(
            api_key=config.open_router_api_key,
            model=route.model,
            base_url=config.open_router_base_url or OPENROUTER_BASE_URL,
        )
        with tempfile.TemporaryDirectory(prefix="gnode-music-") as scratch:
            result = await service.generate(
                MusicGenerationRequest(
                    prompt=prompt,
                    artifact_path=Path(scratch) / "track.mp3",
                    output_format="mp3",
                    timeout_seconds=_MUSIC_TIMEOUT_SECONDS,
                )
            )
        return _audio_record(store, result)

    return handle


def sound_job(
    config: StageGenConfig,
    store: Store,
    *,
    factory: AudioServiceFactory = create_sound_effect_service,
) -> CapabilityHandler:
    """``sound.generate``: one effect at its exact length, its prompt sent verbatim."""

    async def handle(route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
        del take
        try:
            prompt = request.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip():
                raise _NotSent("a sound call needs its prompt as text")
            if not config.elevenlabs_api_key:
                raise _NotSent("ELEVENLABS_API_KEY is not set")
            duration = _number(request, "duration")
            influence = _number(request, "prompt_influence")
        except _NotSent as error:
            raise CallRefused(str(error)) from error
        service = factory(api_key=config.elevenlabs_api_key, model=route.model)
        with tempfile.TemporaryDirectory(prefix="gnode-sound-") as scratch:
            result = await service.generate(
                SoundEffectGenerationRequest(
                    prompt=prompt,
                    artifact_path=Path(scratch) / "clip.mp3",
                    duration_seconds=duration,
                    prompt_influence=influence,
                    loop=bool(request.get("loop", False)),
                    output_format="mp3",
                    timeout_seconds=_CLIP_TIMEOUT_SECONDS,
                )
            )
        return _audio_record(store, result)

    return handle


def speech_job(
    config: StageGenConfig,
    store: Store,
    *,
    factory: AudioServiceFactory = create_speech_service,
) -> CapabilityHandler:
    """``speech.generate``: one line in the provider voice the step names, read verbatim."""

    async def handle(route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
        del take
        try:
            text, voice = request.get("text"), request.get("voice")
            if not isinstance(text, str) or not text.strip():
                raise _NotSent("a speech call needs its text")
            if not isinstance(voice, str) or not voice.strip():
                raise _NotSent("a speech call needs its provider voice")
            if not config.elevenlabs_api_key:
                raise _NotSent("ELEVENLABS_API_KEY is not set")
            stability = _number(request, "stability")
            language = request.get("language_code")
        except _NotSent as error:
            raise CallRefused(str(error)) from error
        service = factory(api_key=config.elevenlabs_api_key, model=route.model)
        with tempfile.TemporaryDirectory(prefix="gnode-speech-") as scratch:
            result = await service.generate(
                SpeechGenerationRequest(
                    text=text,
                    voice=voice,
                    artifact_path=Path(scratch) / "line.mp3",
                    stability=stability,
                    language_code=str(language) if language else None,
                    output_format="mp3",
                    timeout_seconds=_CLIP_TIMEOUT_SECONDS,
                )
            )
        return _audio_record(store, result)

    return handle


def published_workflows() -> dict[str, Path]:
    """Every first-party workflow written as a workflow file, by id.

    A workflow folder may hold more than its ``workflow.yaml`` (character-3d's reviewer
    calibration shares its node types); every workflow file in it is published.
    """

    root = Path(__file__).resolve().parent.parent / "workflows"
    found: dict[str, Path] = {}
    for path in sorted(root.glob("*/*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(document, dict) and document.get("gnode") == "workflow/v1":
            found[str(document["id"])] = path
    return found


def plugin() -> Plugin:
    """The ``gnode.plugins`` entry point."""

    config = load_config()
    return Plugin(
        name="stage_gen",
        routes=image_routes(config).merged(
            RouteTable(
                [
                    *video_routes(),
                    *structured_routes(config),
                    *agent_routes(config),
                    *mesh_routes(),
                    *audio_routes(config),
                ]
            )
        ),
        capabilities=lambda store: {
            **image_capabilities(config, store),
            "video.generate": video_job(config, store),
            "structured.generate": structured_job(config, store),
            "agent.turn": agent_turn_job(config, store),
            "mesh.generate": mesh_job(config, store),
            "mesh.rig": rig_job(config, store),
            "music.generate": music_job(config, store),
            "sound.generate": sound_job(config, store),
            "speech.generate": speech_job(config, store),
        },
        workflows=published_workflows(),
    )


__all__ = [
    "StructuredQuestion",
    "agent_routes",
    "agent_turn_job",
    "audio_routes",
    "music_job",
    "sound_job",
    "speech_job",
    "mesh_job",
    "mesh_routes",
    "rig_job",
    "image_capabilities",
    "image_routes",
    "plugin",
    "published_workflows",
    "structured_job",
    "structured_routes",
    "video_job",
    "video_routes",
]
