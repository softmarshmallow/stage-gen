from __future__ import annotations

from dataclasses import replace

import pytest

from gnode import (
    ImageGenerationRequest,
    ImageGenerationResult,
    ImageReference,
    ImageRouteRequirementsV1,
    ModelRef,
    ProviderResponseMetadata,
    ResolvedBindingV1,
    RouteContractV1,
)
from stage_gen.config import ConfigError, StageGenConfig
from stage_gen.image_product import ImageProvider
from stage_gen.model_routes import (
    FAL_IMAGE_EDIT_ROUTE_ID,
    FAL_IMAGE_GENERATION_ROUTE_ID,
    IMAGE_NATIVE_EDIT_POLICY_ID,
    IMAGE_NATIVE_GENERATION_POLICY_ID,
    IMAGE_OPAQUE_EDIT_POLICY_ID,
    IMAGE_OPAQUE_GENERATION_POLICY_ID,
    OPENAI_IMAGE_EDIT_ROUTE_ID,
    OPENAI_IMAGE_GENERATION_ROUTE_ID,
    OPENROUTER_IMAGE_GENERATION_ROUTE_ID,
    OPENROUTER_IMAGE_REFERENCE_ROUTE_ID,
    SUNBURST_PRODUCT_ID,
    resolve_image_route,
)
from stage_gen.orchestration.image_routing import (
    ImageRoutingError,
    RoutedImageGenerationService,
)

_REFERENCE = ImageReference("data:image/png;base64,AAAA", "fixture://reference")


class _FakeImageService:
    def __init__(
        self,
        route: RouteContractV1,
        *,
        endpoint_override: str | None = None,
    ) -> None:
        self.provider = route.model.provider
        self.model = route.model.model
        self.adapter_id = route.adapter_id
        self.adapter_behavior_version = route.adapter_behavior_version
        self._endpoint_override = endpoint_override
        self.requests: list[ImageGenerationRequest] = []
        self.close_count = 0

    def endpoint_for(self, request: ImageGenerationRequest) -> str:
        if self._endpoint_override is not None:
            return self._endpoint_override
        assert request.resolved_binding is not None
        return request.resolved_binding.route.endpoint

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        self.requests.append(request)
        return ImageGenerationResult(
            data=b"provider-output",
            media_type="image/png",
            provider=self.provider,
            model=self.model,
            attempts=1,
            provenance_path="out.png.meta.json",
            response_metadata=ProviderResponseMetadata(),
        )

    async def aclose(self) -> None:
        self.close_count += 1


class _RecordingFactory:
    def __init__(
        self,
        *,
        provider_override: str | None = None,
        adapter_override: str | None = None,
        endpoint_override: str | None = None,
    ) -> None:
        self.provider_override = provider_override
        self.adapter_override = adapter_override
        self.endpoint_override = endpoint_override
        self.routes: list[RouteContractV1] = []
        self.services: list[_FakeImageService] = []

    def __call__(
        self,
        route: RouteContractV1,
        config: StageGenConfig,
    ) -> _FakeImageService:
        del config
        self.routes.append(route)
        service = _FakeImageService(route, endpoint_override=self.endpoint_override)
        if self.provider_override is not None:
            service.provider = self.provider_override
        if self.adapter_override is not None:
            service.adapter_id = self.adapter_override
        self.services.append(service)
        return service


def _config(**updates: object) -> StageGenConfig:
    values: dict[str, object] = {
        "openai_api_key": "openai-secret",
        "fal_key": "fal-secret",
        "open_router_api_key": "openrouter-secret",
    }
    values.update(updates)
    return StageGenConfig.model_validate(values)


def _request_and_binding(
    *,
    provider: ImageProvider,
    edit: bool,
    background: str,
) -> tuple[ImageGenerationRequest, ResolvedBindingV1]:
    references = (_REFERENCE,) if edit else ()
    request = ImageGenerationRequest(
        prompt="An original painted game asset.",
        artifact_path="out.png",
        input_references=references,
        quality="max",
        background=background,  # type: ignore[arg-type]
        output_format="png",
        size="1024x1024",
    )
    if background == "opaque":
        policy_id = IMAGE_OPAQUE_EDIT_POLICY_ID if edit else IMAGE_OPAQUE_GENERATION_POLICY_ID
    else:
        policy_id = IMAGE_NATIVE_EDIT_POLICY_ID if edit else IMAGE_NATIVE_GENERATION_POLICY_ID
    binding = resolve_image_route(
        ImageRouteRequirementsV1.from_request(request),
        policy_id=policy_id,
        provider_override=provider,
    )
    return replace(request, resolved_binding=binding), binding


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "edit", "background", "route_id"),
    [
        (ImageProvider.OPENAI, False, "transparent", OPENAI_IMAGE_GENERATION_ROUTE_ID),
        (ImageProvider.OPENAI, True, "transparent", OPENAI_IMAGE_EDIT_ROUTE_ID),
        (ImageProvider.FAL, False, "transparent", FAL_IMAGE_GENERATION_ROUTE_ID),
        (ImageProvider.FAL, True, "transparent", FAL_IMAGE_EDIT_ROUTE_ID),
        (ImageProvider.OPENROUTER, False, "opaque", OPENROUTER_IMAGE_GENERATION_ROUTE_ID),
        (ImageProvider.OPENROUTER, True, "opaque", OPENROUTER_IMAGE_REFERENCE_ROUTE_ID),
    ],
)
async def test_dispatches_each_registered_route_without_fallback(
    provider: ImageProvider,
    edit: bool,
    background: str,
    route_id: str,
) -> None:
    request, _binding = _request_and_binding(
        provider=provider,
        edit=edit,
        background=background,
    )
    factory = _RecordingFactory()
    router = RoutedImageGenerationService(
        _config(image_provider_override=provider), service_factory=factory
    )

    result = await router.generate(request)

    assert [route.route_id for route in factory.routes] == [route_id]
    assert result.provider == provider.value
    assert len(factory.services[0].requests) == 1
    await router.aclose()


@pytest.mark.asyncio
async def test_applies_exact_bound_options_reuses_route_and_closes_once() -> None:
    planned, binding = _request_and_binding(
        provider=ImageProvider.FAL,
        edit=False,
        background="transparent",
    )
    drifted = replace(
        planned,
        quality="low",
        background="opaque",
        output_format="jpeg",
        size="512x512",
        aspect_ratio="2:3",
    )
    factory = _RecordingFactory()
    router = RoutedImageGenerationService(
        _config(image_provider_override=ImageProvider.FAL), service_factory=factory
    )

    await router.generate(planned)
    await router.generate(planned)

    assert len(factory.routes) == 1
    assert len(factory.services[0].requests) == 2
    applied = factory.services[0].requests[0]
    assert applied.resolved_binding is binding
    assert applied.quality == "max"
    assert applied.background == "transparent"
    assert applied.output_format == "png"
    assert applied.size == "1024x1024"
    assert applied.aspect_ratio is None

    with pytest.raises(ImageRoutingError, match=r"semantic option|exact image size"):
        await router.generate(drifted)
    assert len(factory.services[0].requests) == 2

    await router.aclose()
    await router.aclose()
    assert factory.services[0].close_count == 1
    with pytest.raises(ImageRoutingError, match="closed"):
        await router.generate(planned)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider", [ImageProvider.OPENAI, ImageProvider.FAL, ImageProvider.OPENROUTER]
)
async def test_generation_and_edit_share_one_resource_service(provider: ImageProvider) -> None:
    background = "opaque" if provider is ImageProvider.OPENROUTER else "transparent"
    generation, generation_binding = _request_and_binding(
        provider=provider,
        edit=False,
        background=background,
    )
    edit, edit_binding = _request_and_binding(
        provider=provider,
        edit=True,
        background=background,
    )
    assert generation_binding.route.resource_id == edit_binding.route.resource_id
    assert generation_binding.route.route_id != edit_binding.route.route_id
    factory = _RecordingFactory()
    router = RoutedImageGenerationService(
        _config(image_provider_override=provider), service_factory=factory
    )

    await router.generate(generation)
    await router.generate(edit)

    assert [route.route_id for route in factory.routes] == [generation_binding.route.route_id]
    assert len(factory.services) == 1
    assert len(factory.services[0].requests) == 2
    await router.aclose()
    assert factory.services[0].close_count == 1


@pytest.mark.asyncio
async def test_refuses_request_without_resolved_binding() -> None:
    factory = _RecordingFactory()
    router = RoutedImageGenerationService(_config(), service_factory=factory)

    with pytest.raises(ImageRoutingError, match="missing its resolved binding"):
        await router.generate(
            ImageGenerationRequest(prompt="Original asset", artifact_path="out.png")
        )

    assert factory.routes == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "background", "config_update", "missing"),
    [
        (ImageProvider.OPENAI, "transparent", {"openai_api_key": None}, "OPENAI_API_KEY"),
        (ImageProvider.FAL, "transparent", {"fal_key": None}, "FAL_KEY"),
        (
            ImageProvider.OPENROUTER,
            "opaque",
            {"open_router_api_key": None},
            "OPENROUTER_API_KEY",
        ),
    ],
)
async def test_missing_credential_names_only_the_selected_provider(
    provider: ImageProvider,
    background: str,
    config_update: dict[str, object],
    missing: str,
) -> None:
    request, _binding = _request_and_binding(
        provider=provider,
        edit=False,
        background=background,
    )
    factory = _RecordingFactory()
    router = RoutedImageGenerationService(
        _config(image_provider_override=provider, **config_update),
        service_factory=factory,
    )

    with pytest.raises(ConfigError) as caught:
        await router.generate(request)

    assert caught.value.missing == (missing,)
    assert factory.routes == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    ["provider", "model", "surface", "endpoint", "adapter_id", "operation_variant"],
)
async def test_refuses_material_route_identity_mismatch(field: str) -> None:
    request, binding = _request_and_binding(
        provider=ImageProvider.OPENAI,
        edit=False,
        background="transparent",
    )
    route = binding.route
    if field == "provider":
        route = replace(route, model=ModelRef(route.model.model, "fal"))
    elif field == "model":
        route = replace(route, model=ModelRef("other-model", route.model.provider))
    elif field == "surface":
        route = replace(route, surface="other-surface")
    elif field == "endpoint":
        route = replace(route, endpoint="https://api.openai.com/v1/images/other")
    elif field == "adapter_id":
        route = replace(route, adapter_id="other-image-adapter-v1")
    else:
        route = replace(route, operation_variant="edit")
    forged = ResolvedBindingV1(
        route=route,
        request=binding.request,
        policy=binding.policy,
    )
    factory = _RecordingFactory()
    router = RoutedImageGenerationService(_config(), service_factory=factory)

    with pytest.raises(ImageRoutingError, match="material identity"):
        await router.generate(replace(request, resolved_binding=forged))

    assert factory.routes == []


@pytest.mark.asyncio
async def test_refuses_unregistered_route_and_custom_base_url() -> None:
    request, binding = _request_and_binding(
        provider=ImageProvider.OPENAI,
        edit=False,
        background="transparent",
    )
    custom_route = replace(binding.route, route_id="image.sunburst.openai.custom")
    custom_binding = ResolvedBindingV1(
        route=custom_route,
        request=binding.request,
        policy=replace(binding.policy, route_id=custom_route.route_id),
    )
    factory = _RecordingFactory()

    with pytest.raises(ImageRoutingError, match="unregistered image route"):
        await RoutedImageGenerationService(_config(), service_factory=factory).generate(
            replace(request, resolved_binding=custom_binding)
        )
    with pytest.raises(ImageRoutingError, match="material identity"):
        await RoutedImageGenerationService(
            _config(openai_base_url="https://proxy.example.test/v1"),
            service_factory=factory,
        ).generate(request)

    assert factory.routes == []


@pytest.mark.asyncio
async def test_refuses_factory_provider_or_model_mismatch_before_dispatch() -> None:
    request, _binding = _request_and_binding(
        provider=ImageProvider.OPENAI,
        edit=False,
        background="transparent",
    )
    factory = _RecordingFactory(provider_override="fal")
    router = RoutedImageGenerationService(_config(), service_factory=factory)

    with pytest.raises(ImageRoutingError, match="factory returned a different provider or model"):
        await router.generate(request)

    assert factory.services[0].requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (_RecordingFactory(adapter_override="wrong-adapter"), "provider adapter"),
        (
            _RecordingFactory(endpoint_override="https://wrong.example/images"),
            "endpoint does not match",
        ),
    ],
)
async def test_refuses_factory_adapter_or_endpoint_mismatch_before_dispatch(
    factory: _RecordingFactory,
    message: str,
) -> None:
    request, _binding = _request_and_binding(
        provider=ImageProvider.OPENAI,
        edit=False,
        background="transparent",
    )
    router = RoutedImageGenerationService(_config(), service_factory=factory)

    with pytest.raises(ImageRoutingError, match=message):
        await router.generate(request)

    assert factory.services[0].requests == []


@pytest.mark.asyncio
async def test_refuses_forged_openrouter_transparent_binding_before_dispatch() -> None:
    request, binding = _request_and_binding(
        provider=ImageProvider.OPENROUTER,
        edit=False,
        background="opaque",
    )
    options = dict(binding.request.output_options)
    options["background"] = "transparent"
    forged = ResolvedBindingV1(
        route=binding.route,
        request=replace(binding.request, output_options=options),
        policy=binding.policy,
    )
    factory = _RecordingFactory()
    router = RoutedImageGenerationService(_config(), service_factory=factory)

    with pytest.raises(ImageRoutingError, match="semantic option background"):
        await router.generate(replace(request, resolved_binding=forged))

    assert factory.routes == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("edit", "changes", "message"),
    [
        (False, {"quality_goal": "maximum_verified", "quality": "high"}, "mapped to max"),
        (False, {"input_fidelity": "omitted"}, "cannot declare input_fidelity"),
        (True, {"input_fidelity": "high"}, "must omit input_fidelity"),
    ],
)
async def test_stage_gen_policy_options_are_refused_before_dispatch(
    edit: bool,
    changes: dict[str, object],
    message: str,
) -> None:
    request, binding = _request_and_binding(
        provider=ImageProvider.OPENAI,
        edit=edit,
        background="transparent",
    )
    forged = ResolvedBindingV1(
        route=binding.route,
        request=replace(
            binding.request,
            output_options={**dict(binding.request.output_options), **changes},
        ),
        policy=binding.policy,
    )
    factory = _RecordingFactory()
    router = RoutedImageGenerationService(_config(), service_factory=factory)

    with pytest.raises(ImageRoutingError, match=message):
        await router.generate(replace(request, resolved_binding=forged))

    assert factory.routes == []


def test_router_identity_does_not_impersonate_a_selected_provider() -> None:
    router = RoutedImageGenerationService(_config(), service_factory=_RecordingFactory())

    assert router.provider == "routed"
    assert router.model == SUNBURST_PRODUCT_ID
    assert router.supports_native_alpha is False
    assert router.adapter_id == "stage-gen-routed-image-v1"
    assert router.adapter_behavior_version == "1"

    request, binding = _request_and_binding(
        provider=ImageProvider.OPENAI,
        edit=False,
        background="transparent",
    )
    assert router.endpoint_for(request) == binding.route.endpoint
