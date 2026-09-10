"""Route-bound one-attempt adapters for image-repeat conditioned repair."""

from __future__ import annotations

import base64
from collections.abc import Callable
from io import BytesIO
from typing import Literal

from PIL import Image, ImageOps, UnidentifiedImageError

from gnode import (
    ImageGenerationRequest,
    ImageModelV1,
    ImageReference,
    ProviderImage,
    ResolvedBindingV1,
    ResolvedRouteSnapshotV1,
    RouteContractV1,
    classify_image_reference_delivery,
    inspect_image,
    sha256_hex,
)
from gnode.providers.fal import (
    FAL_IMAGE_ADAPTER_BEHAVIOR_VERSION,
    FAL_IMAGE_ADAPTER_ID,
    FalImageBackend,
)
from gnode.providers.openai import (
    OPENAI_BASE_URL,
    OPENAI_IMAGE_ADAPTER_BEHAVIOR_VERSION,
    OPENAI_IMAGE_ADAPTER_ID,
    OpenAIImageBackend,
)
from gnode.providers.openrouter import (
    OPENROUTER_BASE_URL,
    OPENROUTER_IMAGE_ADAPTER_BEHAVIOR_VERSION,
    OPENROUTER_IMAGE_ADAPTER_ID,
    OpenRouterImageBackend,
)
from stage_gen.components.image_repeat.models import (
    IMAGE_CONDITIONED_REPAIR_CAPABILITY,
    ImageConditionedRepairRequest,
    ImageConditionedRepairTransport,
    ProviderImageRepeatEdit,
)
from stage_gen.config import ConfigError, StageGenConfig
from stage_gen.model_routes import (
    FAL_SUNBURST_EDIT_ENDPOINT,
    FAL_SUNBURST_TEXT_TO_IMAGE_ENDPOINT,
    configured_conditioned_repair_route_contract,
    resolve_configured_conditioned_repair_route,
)

_FAL_BASE_URL = "https://fal.run"

type ImageRepeatModelFactory = Callable[[RouteContractV1, StageGenConfig], ImageModelV1]

_UNDERLYING_ADAPTER_BY_PROVIDER = {
    "openai": (OPENAI_IMAGE_ADAPTER_ID, OPENAI_IMAGE_ADAPTER_BEHAVIOR_VERSION),
    "fal": (FAL_IMAGE_ADAPTER_ID, FAL_IMAGE_ADAPTER_BEHAVIOR_VERSION),
    "openrouter": (OPENROUTER_IMAGE_ADAPTER_ID, OPENROUTER_IMAGE_ADAPTER_BEHAVIOR_VERSION),
}


class RoutedImageRepeatRepairBackend:
    """Execute the one exact conditioned-repair route selected by host policy.

    Construction resolves the model-capability policy first and then preflights
    only that route's credential. ``edit_once`` performs exactly one provider
    attempt; :class:`ImageRepeatService` remains the sole retry owner.
    """

    capability: Literal["image.conditioned.repair"] = IMAGE_CONDITIONED_REPAIR_CAPABILITY

    def __init__(
        self,
        config: StageGenConfig,
        *,
        model_factory: ImageRepeatModelFactory | None = None,
    ) -> None:
        route = configured_conditioned_repair_route_contract(config)
        credential = _selected_credential(config, route.model.provider)
        backend = (model_factory or _default_model_factory)(route, config)
        if (backend.provider, backend.model) != (
            route.model.provider,
            route.model.model,
        ):
            raise ValueError("image-repeat model factory does not match the resolved route")
        if backend.secrets != (credential,):
            raise ValueError("image-repeat model factory does not use the selected credential")
        try:
            adapter_identity = (backend.adapter_id, backend.adapter_behavior_version)
        except Exception:
            raise ValueError("image-repeat model factory has no valid adapter identity") from None
        if adapter_identity != _UNDERLYING_ADAPTER_BY_PROVIDER[route.model.provider]:
            raise ValueError("image-repeat model factory does not match the provider adapter")

        self._config = config
        self._backend = backend
        self.provider = route.model.provider
        self.model = route.model.model
        self.transport: ImageConditionedRepairTransport = (
            "native_mask_edit"
            if route.operation_variant == "native_mask_edit"
            else "reference_conditioned_edit"
        )
        self.secrets = backend.secrets

    def resolve_route(self, *, width: int, height: int) -> ResolvedRouteSnapshotV1:
        binding = resolve_configured_conditioned_repair_route(
            self._config,
            width=width,
            height=height,
        )
        if _repair_transport(binding) != self.transport:
            raise ValueError("resolved image-repeat transport changed after composition")
        return binding.to_snapshot()

    async def edit_once(
        self,
        request: ImageConditionedRepairRequest,
    ) -> ProviderImageRepeatEdit:
        if request.cancellation is not None:
            request.cancellation.raise_if_cancelled()
        _validate_request_media(request)
        binding = resolve_configured_conditioned_repair_route(
            self._config,
            width=request.width,
            height=request.height,
        )
        if binding.to_snapshot() != self.resolve_route(width=request.width, height=request.height):
            raise ValueError("resolved image-repeat route is not deterministic")
        conditioning = ImageReference(
            _png_data_url(request.conditioning_image),
            f"sha256:{sha256_hex(request.conditioning_image)}",
        )
        semantic_mask = ImageReference(
            _png_data_url(request.mask_image),
            f"sha256:{sha256_hex(request.mask_image)}",
        )
        input_references: tuple[ImageReference, ...]
        if self.transport == "native_mask_edit":
            input_references = (conditioning,)
            native_mask = (
                _openai_alpha_mask(request.mask_image, request.width, request.height)
                if self.provider == "openai"
                else request.mask_image
            )
            mask_reference = ImageReference(
                _png_data_url(native_mask),
                semantic_mask.provenance_ref,
            )
        else:
            input_references = (conditioning, semantic_mask)
            mask_reference = None

        provider_request = ImageGenerationRequest(
            prompt=request.prompt,
            artifact_path="provider-owned-image-repeat-attempt.png",
            input_references=input_references,
            mask_reference=mask_reference,
            aspect_ratio="auto",
            size=f"{request.width}x{request.height}",
            quality="max",
            background="auto",
            output_format="png",
            moderation=(
                "low" if binding.request.output_options.get("moderation") == "low" else None
            ),
            metadata={
                "component": "image_repeat",
                "operation": "conditioned_repair",
                "repair_transport": self.transport,
                "immutable_regions_reimposed_locally": True,
                **dict(request.metadata),
            },
            cancellation=request.cancellation,
            resolved_binding=binding,
        )
        _validate_backend_preflight(binding, self._backend, provider_request)
        generated = await self._backend.generate_once(provider_request)
        _validate_applied_route(binding, provider_request, generated)
        if request.cancellation is not None:
            request.cancellation.raise_if_cancelled()
        validated = _validate_png(generated.data, request.width, request.height)
        return ProviderImageRepeatEdit(
            data=validated,
            media_type="image/png",
            resolved_route=binding.to_snapshot(),
            response_metadata=generated.response_metadata,
        )

    async def aclose(self) -> None:
        await self._backend.aclose()


def _repair_transport(binding: ResolvedBindingV1) -> ImageConditionedRepairTransport:
    options = binding.request.output_options
    if (
        options.get("quality") != "max"
        or options.get("background") != "auto"
        or options.get("output_format") != "png"
        or options.get("prompt_policy") != "authored_verbatim"
        or options.get("immutable_region_policy") != "local_reimposition"
        or options.get("alpha_policy") != "local_reconstruction"
        or options.get("reference_delivery") != "data_url"
    ):
        raise ValueError("resolved image-repeat route has incompatible output policy")
    mask_present = options.get("mask_present")
    reference_count = options.get("reference_count")
    if (
        binding.route.operation_variant == "native_mask_edit"
        and options.get("repair_transport") == "native_mask_edit"
        and mask_present is True
        and reference_count == 1
    ):
        if binding.route.model.provider not in {"openai", "fal"}:
            raise ValueError("resolved image-repeat mask route uses an unsupported provider")
        return "native_mask_edit"
    if (
        binding.route.operation_variant == "reference_conditioned_edit"
        and options.get("repair_transport") == "reference_conditioned_edit"
        and mask_present is False
        and reference_count == 2
    ):
        if binding.route.model.provider != "openrouter":
            raise ValueError("resolved reference-conditioned repair route is not OpenRouter")
        return "reference_conditioned_edit"
    raise ValueError("resolved image-repeat route has incompatible repair semantics")


def _selected_credential(config: StageGenConfig, provider: str) -> str:
    credential = {
        "openai": ("OPENAI_API_KEY", config.openai_api_key),
        "fal": ("FAL_KEY", config.fal_key),
        "openrouter": ("OPENROUTER_API_KEY", config.open_router_api_key),
    }.get(provider)
    if credential is None:
        raise ValueError(f"unsupported image-repeat provider: {provider}")
    name, value = credential
    if value is None or not value.strip():
        raise ConfigError((name,))
    return value


def _default_model_factory(route: RouteContractV1, config: StageGenConfig) -> ImageModelV1:
    provider = route.model.provider
    if provider == "openai":
        assert config.openai_api_key is not None
        return OpenAIImageBackend(
            api_key=config.openai_api_key,
            model=route.model.model,
            supports_native_alpha="transparent_background" in route.features,
            base_url=config.openai_base_url or OPENAI_BASE_URL,
            images_per_minute=config.openai_image_ipm,
        )
    if provider == "fal":
        assert config.fal_key is not None
        return FalImageBackend(
            api_key=config.fal_key,
            model=route.model.model,
            supports_native_alpha="transparent_background" in route.features,
            base_url=config.fal_base_url or _FAL_BASE_URL,
            text_to_image_endpoint=FAL_SUNBURST_TEXT_TO_IMAGE_ENDPOINT,
            edit_endpoint=FAL_SUNBURST_EDIT_ENDPOINT,
        )
    if provider == "openrouter":
        assert config.open_router_api_key is not None
        return OpenRouterImageBackend(
            api_key=config.open_router_api_key,
            model=route.model.model,
            base_url=config.open_router_base_url or OPENROUTER_BASE_URL,
            images_per_minute=config.openrouter_image_ipm,
        )
    raise ValueError(f"unsupported image-repeat provider: {provider}")


def _validate_request_media(request: ImageConditionedRepairRequest) -> None:
    conditioning = inspect_image(request.conditioning_image, expected_media_type="image/png")
    mask = inspect_image(request.mask_image, expected_media_type="image/png")
    expected = (request.width, request.height)
    if (conditioning.width, conditioning.height) != expected:
        raise ValueError("image-repeat conditioning dimensions do not match the request")
    if (mask.width, mask.height) != expected:
        raise ValueError("image-repeat mask dimensions do not match the request")
    with Image.open(BytesIO(request.mask_image)) as decoded:
        decoded.load()
        values = {index for index, count in enumerate(decoded.convert("L").histogram()) if count}
    if not values or not values.issubset({0, 255}) or values != {0, 255}:
        raise ValueError("image-repeat mask must contain both binary preserve and edit regions")


def _validate_backend_preflight(
    binding: ResolvedBindingV1,
    backend: ImageModelV1,
    request: ImageGenerationRequest,
) -> None:
    if (backend.provider, backend.model) != (
        binding.route.model.provider,
        binding.route.model.model,
    ):
        raise ValueError("image-repeat provider backend does not match the resolved route")
    if (backend.adapter_id, backend.adapter_behavior_version) != _UNDERLYING_ADAPTER_BY_PROVIDER[
        binding.route.model.provider
    ]:
        raise ValueError("image-repeat provider adapter changed after composition")
    try:
        endpoint = backend.endpoint_for(request)
    except Exception:
        raise ValueError("image-repeat provider endpoint preflight failed") from None
    if endpoint.rstrip("/") != binding.route.endpoint.rstrip("/"):
        raise ValueError("image-repeat provider endpoint does not match the resolved route")


def _validate_applied_route(
    binding: ResolvedBindingV1,
    request: ImageGenerationRequest,
    generated: ProviderImage,
) -> None:
    params = generated.applied_params
    if params is None:
        raise ValueError("image-repeat provider did not report applied route parameters")
    if params.get("operation") != "edit":
        raise ValueError("image-repeat provider reported a different operation")
    endpoint = params.get("endpoint")
    if not isinstance(endpoint, str) or endpoint.rstrip("/") != binding.route.endpoint.rstrip("/"):
        raise ValueError("image-repeat provider reported a different endpoint")
    for name in ("quality", "background", "output_format", "moderation", "size"):
        expected = binding.request.output_options.get(name)
        if expected is not None and params.get(name) != expected:
            raise ValueError(f"image-repeat provider reported a different {name}")
    expected_references = binding.request.output_options.get("reference_count")
    if params.get("input_reference_count") != expected_references:
        raise ValueError("image-repeat provider reported a different reference count")
    expected_delivery = binding.request.output_options.get("reference_delivery")
    if params.get("reference_delivery") != expected_delivery:
        raise ValueError("image-repeat provider reported a different reference delivery")
    expected_mask = binding.request.output_options.get("mask_present")
    if params.get("mask_present", False) is not expected_mask:
        raise ValueError("image-repeat provider reported different mask semantics")
    if len(request.input_references) != expected_references:
        raise ValueError("image-repeat request disagrees with its resolved reference count")
    if (
        classify_image_reference_delivery(
            (
                *request.input_references,
                *((request.mask_reference,) if request.mask_reference is not None else ()),
            )
        )
        != expected_delivery
    ):
        raise ValueError("image-repeat request disagrees with its resolved reference delivery")
    if (request.mask_reference is not None) is not expected_mask:
        raise ValueError("image-repeat request disagrees with its resolved mask semantics")


def _openai_alpha_mask(data: bytes, width: int, height: int) -> bytes:
    """Compile white-edit/black-preserve intent to OpenAI's transparent-edit mask."""

    try:
        with Image.open(BytesIO(data)) as decoded:
            decoded.load()
            luminance = decoded.convert("L")
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError("image-repeat mask is not a decodable PNG") from error
    if luminance.size != (width, height):
        raise ValueError("image-repeat mask dimensions changed during compilation")
    native = Image.new("RGBA", luminance.size, (0, 0, 0, 255))
    native.putalpha(ImageOps.invert(luminance))
    return _encode_png(native)


def _png_data_url(data: bytes) -> str:
    inspect_image(data, expected_media_type="image/png")
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def _validate_png(data: bytes, width: int, height: int) -> bytes:
    facts = inspect_image(data, expected_media_type="image/png")
    if (facts.width, facts.height) != (width, height):
        raise ValueError("conditioned image repair returned the wrong dimensions")
    return data


def _encode_png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", compress_level=9, optimize=False)
    return output.getvalue()


__all__ = ["ImageRepeatModelFactory", "RoutedImageRepeatRepairBackend"]
