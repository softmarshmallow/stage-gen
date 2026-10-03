"""Stage Gen's gnode plugin: the first-party image routes, and the adapters that call them.

gnode composes its command line from ``gnode.plugins`` entry points. This one contributes
the image routes Stage Gen has verified (``image.generate`` and ``image.edit`` on OpenAI,
fal and OpenRouter), priced and featured from the same catalog the asset pipelines plan
against, and, when a run is live, the capability handlers that call them through the
routed image service: the one retry owner, the credential admission and the exact-route
check that every Stage Gen image call already goes through.
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
    Plugin,
    Route,
    RoutePrice,
    RouteTable,
    Store,
)
from stage_gen.config import StageGenConfig, load_config
from stage_gen.image_product import ImageProvider
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
        routes=image_routes(config),
        capabilities=lambda store: image_capabilities(config, store),
        workflows=published_workflows(),
    )


__all__ = ["image_capabilities", "image_routes", "plugin", "published_workflows"]
