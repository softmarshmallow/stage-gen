from __future__ import annotations

from io import BytesIO
from typing import ClassVar, Literal

import pytest
from PIL import Image

from gnode import (
    ImageGenerationRequest,
    ImageModelV1,
    ProviderImage,
    ProviderResponseMetadata,
    RouteContractV1,
    classify_image_reference_delivery,
)
from gnode.providers.fal import FAL_IMAGE_ADAPTER_BEHAVIOR_VERSION, FAL_IMAGE_ADAPTER_ID
from gnode.providers.openai import (
    OPENAI_IMAGE_ADAPTER_BEHAVIOR_VERSION,
    OPENAI_IMAGE_ADAPTER_ID,
)
from gnode.providers.openrouter import (
    OPENROUTER_IMAGE_ADAPTER_BEHAVIOR_VERSION,
    OPENROUTER_IMAGE_ADAPTER_ID,
)
from stage_gen.components.image_repeat import ImageConditionedRepairRequest
from stage_gen.config import ConfigError, StageGenConfig
from stage_gen.image_product import ImageProvider
from stage_gen.media import inspect_image
from stage_gen.model_routes import (
    FAL_IMAGE_CONDITIONED_REPAIR_ROUTE_ID,
    OPENAI_IMAGE_CONDITIONED_REPAIR_ROUTE_ID,
    OPENROUTER_IMAGE_CONDITIONED_REPAIR_ROUTE_ID,
)
from stage_gen.providers import RoutedImageRepeatRepairBackend

from .._helpers import png_bytes

CANVAS = (1024, 1024)
_ADAPTER_BY_PROVIDER = {
    "openai": (OPENAI_IMAGE_ADAPTER_ID, OPENAI_IMAGE_ADAPTER_BEHAVIOR_VERSION),
    "fal": (FAL_IMAGE_ADAPTER_ID, FAL_IMAGE_ADAPTER_BEHAVIOR_VERSION),
    "openrouter": (OPENROUTER_IMAGE_ADAPTER_ID, OPENROUTER_IMAGE_ADAPTER_BEHAVIOR_VERSION),
}


class RecordingImageModel:
    spec_version: ClassVar[Literal[1]] = 1
    supports_native_alpha = True

    def __init__(
        self,
        route: RouteContractV1,
        credential: str,
        *,
        error: Exception | None = None,
        endpoint: str | None = None,
        output_size: tuple[int, int] | None = None,
        reported_reference_delivery: str | None = None,
    ) -> None:
        self.provider = route.model.provider
        self.model = route.model.model
        self.secrets: tuple[str, ...] = (credential,)
        self.adapter_id, self.adapter_behavior_version = _ADAPTER_BY_PROVIDER[self.provider]
        self.endpoint = endpoint or route.endpoint
        self.output_size = output_size
        self.reported_reference_delivery = reported_reference_delivery
        self.error = error
        self.requests: list[ImageGenerationRequest] = []
        self.closed = False

    def endpoint_for(self, request: ImageGenerationRequest) -> str:
        del request
        return self.endpoint

    async def generate_once(self, request: ImageGenerationRequest) -> ProviderImage:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        params: dict[str, object] = {
            "operation": "edit",
            "endpoint": self.endpoint,
            "quality": request.quality,
            "background": request.background,
            "output_format": request.output_format,
            "size": request.size,
            "input_reference_count": len(request.input_references),
            "mask_present": request.mask_reference is not None,
            "reference_delivery": self.reported_reference_delivery
            or classify_image_reference_delivery(
                (
                    *request.input_references,
                    *((request.mask_reference,) if request.mask_reference is not None else ()),
                )
            ),
        }
        if request.moderation is not None:
            params["moderation"] = request.moderation
        return ProviderImage(
            data=png_bytes(
                size=self.output_size or CANVAS,
                color=(32, 80, 120, 192),
            ),
            media_type="image/png",
            response_metadata=ProviderResponseMetadata(request_id="repeat-edit-1"),
            applied_params=params,
        )

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "route_id", "transport", "credential"),
    [
        (
            ImageProvider.OPENAI,
            OPENAI_IMAGE_CONDITIONED_REPAIR_ROUTE_ID,
            "native_mask_edit",
            "openai-key",
        ),
        (
            ImageProvider.FAL,
            FAL_IMAGE_CONDITIONED_REPAIR_ROUTE_ID,
            "native_mask_edit",
            "fal-key",
        ),
        (
            ImageProvider.OPENROUTER,
            OPENROUTER_IMAGE_CONDITIONED_REPAIR_ROUTE_ID,
            "reference_conditioned_edit",
            "openrouter-key",
        ),
    ],
)
async def test_conditioned_repair_uses_one_exact_provider_route(
    provider: ImageProvider,
    route_id: str,
    transport: str,
    credential: str,
) -> None:
    config = _config(provider)
    models: list[RecordingImageModel] = []

    def factory(route: RouteContractV1, _config: StageGenConfig) -> ImageModelV1:
        model = RecordingImageModel(route, credential)
        models.append(model)
        return model

    backend = RoutedImageRepeatRepairBackend(config, model_factory=factory)
    mask = _binary_mask(CANVAS)
    prompt = "Continue the game foliage naturally without changing either endpoint."
    result = await backend.edit_once(
        ImageConditionedRepairRequest(
            prompt=prompt,
            conditioning_image=png_bytes(size=CANVAS, color=(12, 24, 36, 128)),
            mask_image=mask,
            width=CANVAS[0],
            height=CANVAS[1],
            axis="x",
            context_span_px=2,
            repair_span_px=4,
            metadata={"proof": "unit"},
        )
    )

    assert backend.capability == "image.conditioned.repair"
    assert backend.transport == transport
    resolved_route = backend.resolve_route(width=CANVAS[0], height=CANVAS[1])
    assert resolved_route.policy_id == "image.conditioned.repair"
    assert resolved_route.route_id == route_id
    assert resolved_route.provider == provider.value
    assert resolved_route.effective_output_options["quality"] == "max"
    assert resolved_route.effective_output_options["size"] == "1024x1024"
    assert len(models) == 1
    model = models[0]
    assert len(model.requests) == 1
    request = model.requests[0]
    assert request.prompt == prompt
    assert request.quality == "max"
    assert request.background == "auto"
    assert request.output_format == "png"
    assert request.size == "1024x1024"
    assert request.resolved_binding is not None
    assert request.resolved_binding.to_snapshot() == resolved_route
    assert result.resolved_route == resolved_route
    if provider in {ImageProvider.OPENAI, ImageProvider.FAL}:
        assert len(request.input_references) == 1
        assert request.mask_reference is not None
        if provider is ImageProvider.OPENAI:
            native_mask = _decode_data_url(request.mask_reference.url)
            with Image.open(BytesIO(native_mask)) as image:
                image.load()
                assert image.mode == "RGBA"
                assert image.getchannel("A").getpixel((0, 0)) == 255
                assert image.getchannel("A").getpixel((3, 0)) == 0
        else:
            assert _decode_data_url(request.mask_reference.url) == mask
    else:
        assert len(request.input_references) == 2
        assert request.mask_reference is None
        assert _decode_data_url(request.input_references[1].url) == mask
    assert result.media_type == "image/png"
    assert result.response_metadata.request_id == "repeat-edit-1"
    facts = inspect_image(result.data, expected_media_type="image/png")
    assert (facts.width, facts.height) == CANVAS


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", list(ImageProvider))
async def test_default_composition_constructs_only_the_selected_provider(
    provider: ImageProvider,
) -> None:
    backend = RoutedImageRepeatRepairBackend(_config(provider))

    assert backend.provider == provider.value
    assert backend.resolve_route(width=CANVAS[0], height=CANVAS[1]).provider == provider.value
    await backend.aclose()


@pytest.mark.parametrize(
    ("provider", "missing_name"),
    [
        (ImageProvider.OPENAI, "OPENAI_API_KEY"),
        (ImageProvider.FAL, "FAL_KEY"),
        (ImageProvider.OPENROUTER, "OPENROUTER_API_KEY"),
    ],
)
def test_only_the_selected_route_credential_can_admit_repair(
    provider: ImageProvider,
    missing_name: str,
) -> None:
    config = StageGenConfig(
        image_provider_override=provider,
        openai_api_key=None if provider is ImageProvider.OPENAI else "unused-openai",
        fal_key=None if provider is ImageProvider.FAL else "unused-fal",
        open_router_api_key=(None if provider is ImageProvider.OPENROUTER else "unused-openrouter"),
    )

    with pytest.raises(ConfigError, match=missing_name):
        RoutedImageRepeatRepairBackend(config)


@pytest.mark.asyncio
async def test_routed_repair_backend_makes_no_nested_retry_or_fallback() -> None:
    models: list[RecordingImageModel] = []

    def factory(route: RouteContractV1, _config: StageGenConfig) -> ImageModelV1:
        model = RecordingImageModel(route, "openai-key", error=RuntimeError("provider failed"))
        models.append(model)
        return model

    backend = RoutedImageRepeatRepairBackend(
        _config(ImageProvider.OPENAI),
        model_factory=factory,
    )
    with pytest.raises(RuntimeError, match="provider failed"):
        await backend.edit_once(
            ImageConditionedRepairRequest(
                prompt="Repair one seam.",
                conditioning_image=png_bytes(size=CANVAS),
                mask_image=_binary_mask(CANVAS),
                width=CANVAS[0],
                height=CANVAS[1],
                axis="x",
                context_span_px=2,
                repair_span_px=4,
                metadata={},
            )
        )

    assert len(models) == 1
    assert len(models[0].requests) == 1


def test_injected_model_must_match_the_sealed_route() -> None:
    def factory(route: RouteContractV1, _config: StageGenConfig) -> ImageModelV1:
        model = RecordingImageModel(route, "openai-key")
        model.model = "different-model"
        return model

    with pytest.raises(ValueError, match="does not match the resolved route"):
        RoutedImageRepeatRepairBackend(
            _config(ImageProvider.OPENAI),
            model_factory=factory,
        )


def test_injected_adapter_identity_must_match_before_dispatch() -> None:
    def factory(route: RouteContractV1, _config: StageGenConfig) -> ImageModelV1:
        model = RecordingImageModel(route, "openai-key")
        model.adapter_id = "wrong-adapter"
        return model

    with pytest.raises(ValueError, match="provider adapter"):
        RoutedImageRepeatRepairBackend(
            _config(ImageProvider.OPENAI),
            model_factory=factory,
        )


@pytest.mark.asyncio
async def test_endpoint_mismatch_refuses_before_provider_dispatch() -> None:
    models: list[RecordingImageModel] = []

    def factory(route: RouteContractV1, _config: StageGenConfig) -> ImageModelV1:
        model = RecordingImageModel(route, "openai-key", endpoint="https://wrong.example/edit")
        models.append(model)
        return model

    backend = RoutedImageRepeatRepairBackend(
        _config(ImageProvider.OPENAI),
        model_factory=factory,
    )
    with pytest.raises(ValueError, match="endpoint does not match"):
        await backend.edit_once(_repair_request())
    assert models[0].requests == []


@pytest.mark.asyncio
async def test_wrong_provider_dimensions_are_refused_without_resizing() -> None:
    def factory(route: RouteContractV1, _config: StageGenConfig) -> ImageModelV1:
        return RecordingImageModel(route, "openai-key", output_size=(1024, 1008))

    backend = RoutedImageRepeatRepairBackend(
        _config(ImageProvider.OPENAI),
        model_factory=factory,
    )
    with pytest.raises(ValueError, match="wrong dimensions"):
        await backend.edit_once(_repair_request())


@pytest.mark.asyncio
async def test_reported_reference_delivery_must_match_sealed_route() -> None:
    def factory(route: RouteContractV1, _config: StageGenConfig) -> ImageModelV1:
        return RecordingImageModel(
            route,
            "openai-key",
            reported_reference_delivery="hosted_url",
        )

    backend = RoutedImageRepeatRepairBackend(
        _config(ImageProvider.OPENAI),
        model_factory=factory,
    )
    with pytest.raises(ValueError, match="different reference delivery"):
        await backend.edit_once(_repair_request())


def _config(provider: ImageProvider) -> StageGenConfig:
    return StageGenConfig(
        image_provider_override=provider,
        openai_api_key="openai-key" if provider is ImageProvider.OPENAI else None,
        fal_key="fal-key" if provider is ImageProvider.FAL else None,
        open_router_api_key=("openrouter-key" if provider is ImageProvider.OPENROUTER else None),
    )


def _repair_request() -> ImageConditionedRepairRequest:
    return ImageConditionedRepairRequest(
        prompt="Repair one seam.",
        conditioning_image=png_bytes(size=CANVAS),
        mask_image=_binary_mask(CANVAS),
        width=CANVAS[0],
        height=CANVAS[1],
        axis="x",
        context_span_px=2,
        repair_span_px=4,
        metadata={},
    )


def _binary_mask(size: tuple[int, int]) -> bytes:
    image = Image.new("L", size, 0)
    image.paste(255, (2, 0, size[0] - 2, size[1]))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _decode_data_url(value: str) -> bytes:
    import base64

    prefix = "data:image/png;base64,"
    assert value.startswith(prefix)
    return base64.b64decode(value.removeprefix(prefix), validate=True)
