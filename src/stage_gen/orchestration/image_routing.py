"""Application-owned dispatch for image requests sealed to an exact route."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace
from typing import Protocol, Self

from gnode import (
    ImageGenerationRequest,
    ImageGenerationResult,
    ImageGenerationService,
    ImageModelV1,
    ImageRouteRequirementsV1,
    ResolvedBindingV1,
    RouteContractV1,
    RouteResolutionError,
)
from gnode.providers.fal import FalImageBackend
from gnode.providers.openai import OPENAI_BASE_URL, OpenAIImageBackend
from gnode.providers.openrouter import OPENROUTER_BASE_URL, OpenRouterImageBackend
from stage_gen.config import ConfigError, StageGenConfig
from stage_gen.identity import IMAGE_GENERATION_COMPONENT, STAGE_GEN_TOOL
from stage_gen.image_binding import apply_stage_gen_image_binding
from stage_gen.model_routes import (
    FAL_IMAGE_EDIT_ROUTE_ID,
    FAL_IMAGE_GENERATION_ROUTE_ID,
    FAL_SUNBURST_EDIT_ENDPOINT,
    FAL_SUNBURST_TEXT_TO_IMAGE_ENDPOINT,
    OPENAI_IMAGE_EDIT_ROUTE_ID,
    OPENAI_IMAGE_GENERATION_ROUTE_ID,
    OPENAI_SUNBURST_MODEL,
    OPENROUTER_IMAGE_GENERATION_ROUTE_ID,
    OPENROUTER_IMAGE_REFERENCE_ROUTE_ID,
    OPENROUTER_SUNBURST_MODEL,
    SUNBURST_PRODUCT_ID,
    configured_image_route_catalog,
    image_workload_policies,
)
from stage_gen.orchestration.route_context import current_resolved_binding

_FAL_BASE_URL = "https://fal.run"
_SUPPORTED_ROUTE_IDS = frozenset(
    {
        OPENAI_IMAGE_GENERATION_ROUTE_ID,
        OPENAI_IMAGE_EDIT_ROUTE_ID,
        FAL_IMAGE_GENERATION_ROUTE_ID,
        FAL_IMAGE_EDIT_ROUTE_ID,
        OPENROUTER_IMAGE_GENERATION_ROUTE_ID,
        OPENROUTER_IMAGE_REFERENCE_ROUTE_ID,
    }
)


class ImageRoutingError(ValueError):
    """A request does not carry one exact registered runtime route."""


class ImageGenerationClient(Protocol):
    """The retry-owning image service surface consumed by application handlers."""

    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str: ...

    @property
    def adapter_id(self) -> str: ...

    @property
    def adapter_behavior_version(self) -> str: ...

    def endpoint_for(self, request: ImageGenerationRequest) -> str: ...

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult: ...

    async def aclose(self) -> None: ...


type ImageServiceFactory = Callable[[RouteContractV1, StageGenConfig], ImageGenerationClient]


class RoutedImageGenerationService(ImageGenerationService):
    """Dispatch only to the exact route sealed into each image request.

    Credentials are admission inputs for the already-selected provider. They
    never participate in discovery, fallback, or route selection.
    """

    def __init__(
        self,
        config: StageGenConfig,
        *,
        service_factory: ImageServiceFactory | None = None,
    ) -> None:
        self._config = config
        self._service_factory = service_factory or _default_image_service_factory
        self._services: dict[str, tuple[RouteContractV1, ImageGenerationClient]] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    @property
    def provider(self) -> str:
        """Identify the application router without pretending one provider was selected."""

        return "routed"

    @property
    def model(self) -> str:
        """Return the product identity shared by every registered route."""

        return SUNBURST_PRODUCT_ID

    @property
    def supports_native_alpha(self) -> bool:
        """Route capability is request-bound; the router has no ambient alpha claim."""

        return False

    @property
    def adapter_id(self) -> str:
        """Identify the application router rather than an unselected adapter."""

        return "stage-gen-routed-image-v1"

    @property
    def adapter_behavior_version(self) -> str:
        return "1"

    def endpoint_for(self, request: ImageGenerationRequest) -> str:
        """Return the endpoint sealed into this request without constructing a provider."""

        contextual = current_resolved_binding()
        binding = request.resolved_binding or contextual
        if binding is None:
            raise ImageRoutingError("image request is missing its resolved binding")
        if (
            request.resolved_binding is not None
            and contextual is not None
            and request.resolved_binding != contextual
        ):
            raise ImageRoutingError("image request binding disagrees with its planned node")
        return _registered_route(binding, self._config).endpoint

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        del exc_type, exc, traceback
        await self.aclose()

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        contextual = current_resolved_binding()
        binding = request.resolved_binding or contextual
        if binding is None:
            raise ImageRoutingError("image request is missing its resolved binding")
        if (
            request.resolved_binding is not None
            and contextual is not None
            and request.resolved_binding != contextual
        ):
            raise ImageRoutingError("image request binding disagrees with its planned node")
        request = replace(request, resolved_binding=binding)
        route = _registered_route(binding, self._config)
        try:
            applied = apply_stage_gen_image_binding(request, binding)
        except ValueError as error:
            raise ImageRoutingError(str(error)) from error
        _validate_applied_request(route, applied)
        service = await self._service(route)
        _validate_service_route(service, route, applied)
        result = await service.generate(applied)
        if (result.provider, result.model) != (route.model.provider, route.model.model):
            raise ImageRoutingError("image service returned a different provider or model")
        return result

    async def _service(self, route: RouteContractV1) -> ImageGenerationClient:
        async with self._lock:
            if self._closed:
                raise ImageRoutingError("routed image service is closed")
            entry = self._services.get(route.resource_id)
            if entry is None:
                require_image_route_credential(self._config, route.model.provider)
                service = self._service_factory(route, self._config)
                if (service.provider, service.model) != (
                    route.model.provider,
                    route.model.model,
                ):
                    raise ImageRoutingError(
                        "image service factory returned a different provider or model"
                    )
                _validate_service_adapter(service, route)
                self._services[route.resource_id] = (route, service)
                return service

            composed_route, service = entry
            if (
                composed_route.model != route.model
                or composed_route.adapter_id != route.adapter_id
                or composed_route.adapter_behavior_version != route.adapter_behavior_version
                or composed_route.surface != route.surface
                or composed_route.resource_id != route.resource_id
            ):
                raise ImageRoutingError(
                    "image routes sharing a resource must use one provider adapter"
                )
            return service

    async def aclose(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            services = tuple(service for _route, service in self._services.values())
            self._services.clear()
        first_error: BaseException | None = None
        closed: set[int] = set()
        for service in services:
            if id(service) in closed:
                continue
            closed.add(id(service))
            try:
                await service.aclose()
            except BaseException as error:
                if first_error is None:
                    first_error = error
        if first_error is not None:
            raise first_error


def _registered_route(binding: ResolvedBindingV1, config: StageGenConfig) -> RouteContractV1:
    route = binding.route
    if route.route_id not in _SUPPORTED_ROUTE_IDS:
        raise ImageRoutingError(f"unregistered image route: {route.route_id}")
    catalog = configured_image_route_catalog(config)
    try:
        expected = catalog.route(route.route_id)
        admitted = catalog.resolve(binding.request, binding.policy)
        checked_in_policy = image_workload_policies(config.image_provider_override)[
            binding.policy.policy_id
        ]
    except (KeyError, RouteResolutionError) as error:
        raise ImageRoutingError(str(error)) from error
    if binding.policy != checked_in_policy:
        raise ImageRoutingError("resolved image binding does not use a checked-in policy")
    if admitted.route.route_id != route.route_id:
        raise ImageRoutingError("resolved image policy selects a different route")
    if route.material_identity() != expected.material_identity():
        raise ImageRoutingError("resolved image route material identity is not registered")
    if route.contract_fingerprint != expected.contract_fingerprint:
        raise ImageRoutingError("resolved image route capability contract is not registered")
    _validate_config_identity(expected, config)
    return expected


def _validate_config_identity(route: RouteContractV1, config: StageGenConfig) -> None:
    provider = route.model.provider
    if provider == "openai":
        if (
            config.openai_image_model is not None
            and config.openai_image_model != OPENAI_SUNBURST_MODEL
        ):
            raise ImageRoutingError("configured OpenAI image model is not the registered route")
    elif provider == "fal":
        pass
    elif provider == "openrouter":
        if config.image_model is not None and config.image_model != OPENROUTER_SUNBURST_MODEL:
            raise ImageRoutingError("configured OpenRouter image model is not the registered route")
    else:
        raise ImageRoutingError(f"unsupported image provider: {provider}")

    base_url = {
        "openai": config.openai_base_url or OPENAI_BASE_URL,
        "fal": config.fal_base_url or _FAL_BASE_URL,
        "openrouter": config.open_router_base_url or OPENROUTER_BASE_URL,
    }[provider]
    if not route.endpoint.startswith(f"{base_url.strip().rstrip('/')}/"):
        raise ImageRoutingError("registered image endpoint does not match its provider base URL")


def _validate_applied_request(
    route: RouteContractV1,
    request: ImageGenerationRequest,
) -> None:
    requirements = ImageRouteRequirementsV1.from_request(request)
    if requirements.operation_variant != route.operation_variant:
        raise ImageRoutingError("resolved image route operation does not match the request")
    missing = sorted(requirements.required_features - route.features)
    if missing:
        raise ImageRoutingError(f"resolved image route does not support: {', '.join(missing)}")
    reference_limit = route.limit("reference_count_max")
    if requirements.reference_count and (
        reference_limit is None or requirements.reference_count > reference_limit
    ):
        raise ImageRoutingError("resolved image route does not admit the reference count")


def _validate_service_adapter(
    service: ImageGenerationClient,
    route: RouteContractV1,
) -> None:
    try:
        identity = (service.adapter_id, service.adapter_behavior_version)
    except Exception:
        raise ImageRoutingError("image service factory returned no adapter identity") from None
    if identity != (route.adapter_id, route.adapter_behavior_version):
        raise ImageRoutingError("image service factory returned a different provider adapter")


def _validate_service_route(
    service: ImageGenerationClient,
    route: RouteContractV1,
    request: ImageGenerationRequest,
) -> None:
    _validate_service_adapter(service, route)
    try:
        endpoint = service.endpoint_for(request)
    except Exception:
        raise ImageRoutingError("image service endpoint preflight failed") from None
    if endpoint.rstrip("/") != route.endpoint.rstrip("/"):
        raise ImageRoutingError("image service endpoint does not match the sealed route")


def require_image_route_credential(config: StageGenConfig, provider: str) -> None:
    """Require the credential for one already-selected image route provider."""

    credential = {
        "openai": ("OPENAI_API_KEY", config.openai_api_key),
        "fal": ("FAL_KEY", config.fal_key),
        "openrouter": ("OPENROUTER_API_KEY", config.open_router_api_key),
    }.get(provider)
    if credential is None:
        raise ImageRoutingError(f"unsupported image provider: {provider}")
    name, value = credential
    if value is None or not value.strip():
        raise ConfigError((name,))


def _default_image_service_factory(
    route: RouteContractV1,
    config: StageGenConfig,
) -> ImageGenerationClient:
    provider = route.model.provider
    backend: ImageModelV1
    if provider == "openai":
        assert config.openai_api_key is not None
        backend = OpenAIImageBackend(
            api_key=config.openai_api_key,
            model=route.model.model,
            supports_native_alpha="transparent_background" in route.features,
            base_url=config.openai_base_url or OPENAI_BASE_URL,
            images_per_minute=config.openai_image_ipm,
        )
    elif provider == "fal":
        assert config.fal_key is not None
        backend = FalImageBackend(
            api_key=config.fal_key,
            model=route.model.model,
            supports_native_alpha="transparent_background" in route.features,
            base_url=config.fal_base_url or _FAL_BASE_URL,
            text_to_image_endpoint=FAL_SUNBURST_TEXT_TO_IMAGE_ENDPOINT,
            edit_endpoint=FAL_SUNBURST_EDIT_ENDPOINT,
        )
    elif provider == "openrouter":
        assert config.open_router_api_key is not None
        backend = OpenRouterImageBackend(
            api_key=config.open_router_api_key,
            model=route.model.model,
            base_url=config.open_router_base_url or OPENROUTER_BASE_URL,
            images_per_minute=config.openrouter_image_ipm,
        )
    else:
        raise ImageRoutingError(f"unsupported image provider: {provider}")
    return ImageGenerationService(
        backend,
        component=IMAGE_GENERATION_COMPONENT,
        tool=STAGE_GEN_TOOL,
    )


__all__ = [
    "ImageGenerationClient",
    "ImageRoutingError",
    "ImageServiceFactory",
    "RoutedImageGenerationService",
    "apply_stage_gen_image_binding",
    "require_image_route_credential",
]
