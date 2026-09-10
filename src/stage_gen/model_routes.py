"""Checked-in Stage Gen policy for quality-first Sunburst image routes."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from ipaddress import ip_address
from types import MappingProxyType
from typing import Literal
from urllib.parse import urlsplit

from gnode import (
    ExactSize2DV1,
    ExactSizeConstraints2DV1,
    ImageRouteRequirementsV1,
    ModelRef,
    ResolvedBindingV1,
    RouteCatalog,
    RouteContractV1,
    RouteResolutionError,
    WorkloadPolicyV1,
    WorkloadRequestV1,
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

from .config import StageGenConfig
from .image_product import (
    QUALITY_IMAGE_EXACT_SIZE_BY_ASPECT_RATIO,
    QUALITY_IMAGE_PRODUCT,
    ImageProvider,
)

SUNBURST_PRODUCT_ID = QUALITY_IMAGE_PRODUCT.product_id
IMAGE_OPERATION = "image_generation"
IMAGE_MODALITY_SPEC_VERSION = "image-generation-v1"
IMAGE_CONDITIONED_REPAIR_OPERATION = "image_conditioned_repair"
IMAGE_CONDITIONED_REPAIR_MODALITY_SPEC_VERSION = "image-conditioned-repair-v1"
IMAGE_POLICY_VERSION = "1"

OPENAI_SUNBURST_MODEL = QUALITY_IMAGE_PRODUCT.openai_model
FAL_SUNBURST_MODEL = QUALITY_IMAGE_PRODUCT.fal_model
OPENROUTER_SUNBURST_MODEL = QUALITY_IMAGE_PRODUCT.openrouter_model
FAL_SUNBURST_TEXT_TO_IMAGE_ENDPOINT = QUALITY_IMAGE_PRODUCT.fal_text_to_image_endpoint
FAL_SUNBURST_EDIT_ENDPOINT = QUALITY_IMAGE_PRODUCT.fal_edit_endpoint

OPENAI_IMAGE_GENERATION_ROUTE_ID = "image.sunburst.openai.images.generation"
OPENAI_IMAGE_EDIT_ROUTE_ID = "image.sunburst.openai.images.edit"
FAL_IMAGE_GENERATION_ROUTE_ID = "image.sunburst.fal.text-to-image"
FAL_IMAGE_EDIT_ROUTE_ID = "image.sunburst.fal.edit"
OPENROUTER_IMAGE_GENERATION_ROUTE_ID = "image.sunburst.openrouter.images.generation"
OPENROUTER_IMAGE_REFERENCE_ROUTE_ID = "image.sunburst.openrouter.images.reference"
OPENAI_IMAGE_CONDITIONED_REPAIR_ROUTE_ID = "image.sunburst.openai.images.conditioned_repair"
FAL_IMAGE_CONDITIONED_REPAIR_ROUTE_ID = "image.sunburst.fal.conditioned_repair"
OPENROUTER_IMAGE_CONDITIONED_REPAIR_ROUTE_ID = "image.sunburst.openrouter.images.conditioned_repair"

type ImageWorkloadResolver = Callable[[ImageRouteRequirementsV1], WorkloadRequestV1]

IMAGE_NATIVE_GENERATION_POLICY_ID = "image.native.generation"
IMAGE_NATIVE_EDIT_POLICY_ID = "image.native.edit"
IMAGE_MASKED_EDIT_POLICY_ID = "image.masked.edit"
IMAGE_CONDITIONED_REPAIR_POLICY_ID = "image.conditioned.repair"
IMAGE_TRANSPARENT_GENERATION_POLICY_ID = "image.transparent.generation"
IMAGE_TRANSPARENT_EDIT_POLICY_ID = "image.transparent.edit"
IMAGE_OPAQUE_GENERATION_POLICY_ID = "image.opaque.generation"
IMAGE_OPAQUE_EDIT_POLICY_ID = "image.opaque.edit"

_EVIDENCE_REF = "docs/models/gpt-image-2.5.md"
_VERIFIED_ON = "2026-09-09"
_REFERENCE_LIMIT = (("reference_count_max", 16.0),)
SUNBURST_EXACT_SIZE_BY_ASPECT_RATIO = QUALITY_IMAGE_EXACT_SIZE_BY_ASPECT_RATIO
_OPENROUTER_VERIFIED_EXACT_SIZE_STRINGS = frozenset(
    {
        "1024x1024",
        "1152x2496",
        "1712x2560",
        "2064x1008",
        "2496x1152",
        "2560x1440",
        "2560x1712",
    }
)


def _exact_size(value: str | None) -> ExactSize2DV1 | None:
    if value is None or value == "auto":
        return None
    width, height = (int(edge) for edge in value.split("x"))
    return ExactSize2DV1(width=width, height=height)


_SUNBURST_CUSTOM_EXACT_SIZE_CONSTRAINTS = ExactSizeConstraints2DV1(
    width_multiple=16,
    height_multiple=16,
    min_area=655_360,
    max_area=8_294_400,
    max_edge=3_840,
    max_aspect_ratio=3.0,
)
_OPENROUTER_VERIFIED_EXACT_SIZES = tuple(
    ExactSize2DV1(
        width=int(size.split("x")[0]),
        height=int(size.split("x")[1]),
    )
    for size in sorted(_OPENROUTER_VERIFIED_EXACT_SIZE_STRINGS)
)
_OPENROUTER_VERIFIED_EXACT_SIZE_CONSTRAINTS = ExactSizeConstraints2DV1(
    width_multiple=16,
    height_multiple=16,
    min_area=655_360,
    max_area=8_294_400,
    max_edge=3_840,
    max_aspect_ratio=3.0,
    allowed_sizes=_OPENROUTER_VERIFIED_EXACT_SIZES,
)

_NATIVE_IMAGE_FEATURES = frozenset(
    {
        "authored_prompt_passthrough",
        "auto_background",
        "custom_exact_size",
        "exact_size",
        "flexible_size",
        "jpeg_output",
        "maximum_quality",
        "opaque_background",
        "png_output",
        "transparent_background",
        "webp_output",
    }
)
_CONDITIONED_REPAIR_COMMON_FEATURES = frozenset(
    {
        "authored_prompt_passthrough",
        "conditioned_repair",
        "data_url_reference_input",
        "flexible_size",
        "local_alpha_reconstruction",
        "local_immutable_restoration",
        "maximum_quality",
        "png_output",
    }
)
_OPENROUTER_IMAGE_FEATURES = frozenset(
    {
        "authored_prompt_passthrough",
        "auto_background",
        "data_url_reference_input",
        "exact_size",
        "flexible_size",
        "hosted_url_reference_input",
        "maximum_quality",
        "opaque_background",
        "png_output",
    }
)


def _normalized_base_url(
    value: str,
    label: str,
    *,
    allowed_paths: frozenset[str],
) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if (
        not normalized
        or parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"{label} must be a non-secret HTTP(S) URL without query or fragment")
    try:
        _ = parsed.port
    except ValueError as error:
        raise ValueError(f"{label} must use a valid network port") from error
    if parsed.scheme == "http" and not _is_loopback_host(parsed.hostname or ""):
        raise ValueError(f"{label} must use HTTPS unless it targets a loopback host")
    if parsed.path not in allowed_paths:
        allowed = ", ".join(repr(path or "/") for path in sorted(allowed_paths))
        raise ValueError(
            f"{label} path must be one of {allowed}; arbitrary gateway paths cannot be "
            "sealed into portable route records"
        )
    return normalized


def _is_loopback_host(host: str) -> bool:
    normalized = host.rstrip(".").lower()
    if normalized == "localhost":
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def image_route_catalog(
    *,
    openai_base_url: str = "https://api.openai.com/v1",
    fal_base_url: str = "https://fal.run",
    openrouter_base_url: str = "https://openrouter.ai/api/v1",
    openai_requests_per_minute: int = 150,
    openrouter_requests_per_minute: int = 150,
) -> RouteCatalog:
    """Build the immutable catalog; pacing inputs are operational, not output identity."""

    openai_base = _normalized_base_url(
        openai_base_url,
        "OpenAI image base URL",
        allowed_paths=frozenset({"", "/v1"}),
    )
    fal_base = _normalized_base_url(
        fal_base_url,
        "Fal image base URL",
        allowed_paths=frozenset({""}),
    )
    openrouter_base = _normalized_base_url(
        openrouter_base_url,
        "OpenRouter image base URL",
        allowed_paths=frozenset({"", "/api/v1", "/v1"}),
    )

    return RouteCatalog(
        (
            RouteContractV1(
                route_id=OPENAI_IMAGE_GENERATION_ROUTE_ID,
                product_id=SUNBURST_PRODUCT_ID,
                operation=IMAGE_OPERATION,
                operation_variant="generation",
                model=ModelRef(OPENAI_SUNBURST_MODEL, ImageProvider.OPENAI.value),
                modality_spec_version=IMAGE_MODALITY_SPEC_VERSION,
                surface="openai-images",
                endpoint=f"{openai_base}/images/generations",
                adapter_id=OPENAI_IMAGE_ADAPTER_ID,
                adapter_behavior_version=OPENAI_IMAGE_ADAPTER_BEHAVIOR_VERSION,
                features=_NATIVE_IMAGE_FEATURES | {"text_to_image"},
                exact_size_constraints=_SUNBURST_CUSTOM_EXACT_SIZE_CONSTRAINTS,
                resource_id="openai-image",
                estimated_duration_seconds=120.0,
                estimated_cost_low_usd=0.18,
                estimated_cost_high_usd=0.25,
                requests_per_minute=openai_requests_per_minute,
                rate_limit_owner="provider_adapter",
                verified_on=_VERIFIED_ON,
                evidence_ref=_EVIDENCE_REF,
            ),
            RouteContractV1(
                route_id=OPENAI_IMAGE_EDIT_ROUTE_ID,
                product_id=SUNBURST_PRODUCT_ID,
                operation=IMAGE_OPERATION,
                operation_variant="edit",
                model=ModelRef(OPENAI_SUNBURST_MODEL, ImageProvider.OPENAI.value),
                modality_spec_version=IMAGE_MODALITY_SPEC_VERSION,
                surface="openai-images",
                endpoint=f"{openai_base}/images/edits",
                adapter_id=OPENAI_IMAGE_ADAPTER_ID,
                adapter_behavior_version=OPENAI_IMAGE_ADAPTER_BEHAVIOR_VERSION,
                features=_NATIVE_IMAGE_FEATURES
                | {"data_url_reference_input", "masked_edit", "reference_images"},
                limits=_REFERENCE_LIMIT,
                exact_size_constraints=_SUNBURST_CUSTOM_EXACT_SIZE_CONSTRAINTS,
                resource_id="openai-image",
                estimated_duration_seconds=120.0,
                estimated_cost_low_usd=0.18,
                estimated_cost_high_usd=0.25,
                requests_per_minute=openai_requests_per_minute,
                rate_limit_owner="provider_adapter",
                verified_on=_VERIFIED_ON,
                evidence_ref=_EVIDENCE_REF,
            ),
            RouteContractV1(
                route_id=FAL_IMAGE_GENERATION_ROUTE_ID,
                product_id=SUNBURST_PRODUCT_ID,
                operation=IMAGE_OPERATION,
                operation_variant="generation",
                model=ModelRef(FAL_SUNBURST_MODEL, ImageProvider.FAL.value),
                modality_spec_version=IMAGE_MODALITY_SPEC_VERSION,
                surface="fal-run",
                endpoint=f"{fal_base}/{FAL_SUNBURST_TEXT_TO_IMAGE_ENDPOINT}",
                adapter_id=FAL_IMAGE_ADAPTER_ID,
                adapter_behavior_version=FAL_IMAGE_ADAPTER_BEHAVIOR_VERSION,
                features=_NATIVE_IMAGE_FEATURES | {"text_to_image"},
                exact_size_constraints=_SUNBURST_CUSTOM_EXACT_SIZE_CONSTRAINTS,
                resource_id="fal-image",
                estimated_duration_seconds=120.0,
                estimated_cost_low_usd=0.16464,
                estimated_cost_high_usd=0.50,
                rate_limit_owner="none",
                verified_on=_VERIFIED_ON,
                evidence_ref=_EVIDENCE_REF,
            ),
            RouteContractV1(
                route_id=FAL_IMAGE_EDIT_ROUTE_ID,
                product_id=SUNBURST_PRODUCT_ID,
                operation=IMAGE_OPERATION,
                operation_variant="edit",
                model=ModelRef(FAL_SUNBURST_MODEL, ImageProvider.FAL.value),
                modality_spec_version=IMAGE_MODALITY_SPEC_VERSION,
                surface="fal-run",
                endpoint=f"{fal_base}/{FAL_SUNBURST_EDIT_ENDPOINT}",
                adapter_id=FAL_IMAGE_ADAPTER_ID,
                adapter_behavior_version=FAL_IMAGE_ADAPTER_BEHAVIOR_VERSION,
                features=_NATIVE_IMAGE_FEATURES
                | {
                    "data_url_reference_input",
                    "hosted_url_reference_input",
                    "masked_edit",
                    "reference_images",
                },
                limits=_REFERENCE_LIMIT,
                exact_size_constraints=_SUNBURST_CUSTOM_EXACT_SIZE_CONSTRAINTS,
                resource_id="fal-image",
                estimated_duration_seconds=120.0,
                estimated_cost_low_usd=0.16464,
                estimated_cost_high_usd=0.50,
                rate_limit_owner="none",
                verified_on=_VERIFIED_ON,
                evidence_ref=_EVIDENCE_REF,
            ),
            RouteContractV1(
                route_id=OPENROUTER_IMAGE_GENERATION_ROUTE_ID,
                product_id=SUNBURST_PRODUCT_ID,
                operation=IMAGE_OPERATION,
                operation_variant="generation",
                model=ModelRef(OPENROUTER_SUNBURST_MODEL, ImageProvider.OPENROUTER.value),
                modality_spec_version=IMAGE_MODALITY_SPEC_VERSION,
                surface="openrouter-images",
                endpoint=f"{openrouter_base}/images",
                adapter_id=OPENROUTER_IMAGE_ADAPTER_ID,
                adapter_behavior_version=OPENROUTER_IMAGE_ADAPTER_BEHAVIOR_VERSION,
                features=_OPENROUTER_IMAGE_FEATURES | {"text_to_image"},
                exact_size_constraints=_OPENROUTER_VERIFIED_EXACT_SIZE_CONSTRAINTS,
                resource_id="openrouter-image",
                estimated_duration_seconds=120.0,
                estimated_cost_low_usd=0.14,
                estimated_cost_high_usd=0.30,
                requests_per_minute=openrouter_requests_per_minute,
                rate_limit_owner="provider_adapter",
                verified_on=_VERIFIED_ON,
                evidence_ref=_EVIDENCE_REF,
            ),
            RouteContractV1(
                route_id=OPENROUTER_IMAGE_REFERENCE_ROUTE_ID,
                product_id=SUNBURST_PRODUCT_ID,
                operation=IMAGE_OPERATION,
                operation_variant="edit",
                model=ModelRef(OPENROUTER_SUNBURST_MODEL, ImageProvider.OPENROUTER.value),
                modality_spec_version=IMAGE_MODALITY_SPEC_VERSION,
                surface="openrouter-images",
                endpoint=f"{openrouter_base}/images",
                adapter_id=OPENROUTER_IMAGE_ADAPTER_ID,
                adapter_behavior_version=OPENROUTER_IMAGE_ADAPTER_BEHAVIOR_VERSION,
                features=_OPENROUTER_IMAGE_FEATURES | {"reference_images"},
                limits=_REFERENCE_LIMIT,
                exact_size_constraints=_OPENROUTER_VERIFIED_EXACT_SIZE_CONSTRAINTS,
                resource_id="openrouter-image",
                estimated_duration_seconds=120.0,
                estimated_cost_low_usd=0.14,
                estimated_cost_high_usd=0.30,
                requests_per_minute=openrouter_requests_per_minute,
                rate_limit_owner="provider_adapter",
                verified_on=_VERIFIED_ON,
                evidence_ref=_EVIDENCE_REF,
            ),
            RouteContractV1(
                route_id=OPENAI_IMAGE_CONDITIONED_REPAIR_ROUTE_ID,
                product_id=SUNBURST_PRODUCT_ID,
                operation=IMAGE_CONDITIONED_REPAIR_OPERATION,
                operation_variant="native_mask_edit",
                model=ModelRef(OPENAI_SUNBURST_MODEL, ImageProvider.OPENAI.value),
                modality_spec_version=IMAGE_CONDITIONED_REPAIR_MODALITY_SPEC_VERSION,
                surface="openai-images",
                endpoint=f"{openai_base}/images/edits",
                adapter_id="stage-gen-image-repeat-repair-v1",
                adapter_behavior_version="1",
                features=_CONDITIONED_REPAIR_COMMON_FEATURES
                | {"native_mask_input", "transparent_background"},
                limits=(("reference_count_max", 1.0),),
                exact_size_constraints=_SUNBURST_CUSTOM_EXACT_SIZE_CONSTRAINTS,
                resource_id="openai-image",
                estimated_duration_seconds=120.0,
                estimated_cost_low_usd=0.18,
                estimated_cost_high_usd=0.25,
                requests_per_minute=openai_requests_per_minute,
                rate_limit_owner="provider_adapter",
                verified_on=_VERIFIED_ON,
                evidence_ref=_EVIDENCE_REF,
            ),
            RouteContractV1(
                route_id=FAL_IMAGE_CONDITIONED_REPAIR_ROUTE_ID,
                product_id=SUNBURST_PRODUCT_ID,
                operation=IMAGE_CONDITIONED_REPAIR_OPERATION,
                operation_variant="native_mask_edit",
                model=ModelRef(FAL_SUNBURST_MODEL, ImageProvider.FAL.value),
                modality_spec_version=IMAGE_CONDITIONED_REPAIR_MODALITY_SPEC_VERSION,
                surface="fal-run",
                endpoint=f"{fal_base}/{FAL_SUNBURST_EDIT_ENDPOINT}",
                adapter_id="stage-gen-image-repeat-repair-v1",
                adapter_behavior_version="1",
                features=_CONDITIONED_REPAIR_COMMON_FEATURES
                | {"native_mask_input", "transparent_background"},
                limits=(("reference_count_max", 1.0),),
                exact_size_constraints=_SUNBURST_CUSTOM_EXACT_SIZE_CONSTRAINTS,
                resource_id="fal-image",
                estimated_duration_seconds=120.0,
                estimated_cost_low_usd=0.16464,
                estimated_cost_high_usd=0.50,
                rate_limit_owner="none",
                verified_on=_VERIFIED_ON,
                evidence_ref=_EVIDENCE_REF,
            ),
            RouteContractV1(
                route_id=OPENROUTER_IMAGE_CONDITIONED_REPAIR_ROUTE_ID,
                product_id=SUNBURST_PRODUCT_ID,
                operation=IMAGE_CONDITIONED_REPAIR_OPERATION,
                operation_variant="reference_conditioned_edit",
                model=ModelRef(OPENROUTER_SUNBURST_MODEL, ImageProvider.OPENROUTER.value),
                modality_spec_version=IMAGE_CONDITIONED_REPAIR_MODALITY_SPEC_VERSION,
                surface="openrouter-images",
                endpoint=f"{openrouter_base}/images",
                adapter_id="stage-gen-image-repeat-repair-v1",
                adapter_behavior_version="1",
                features=_CONDITIONED_REPAIR_COMMON_FEATURES | {"reference_guidance"},
                limits=(("reference_count_max", 2.0),),
                exact_size_constraints=_OPENROUTER_VERIFIED_EXACT_SIZE_CONSTRAINTS,
                resource_id="openrouter-image",
                estimated_duration_seconds=120.0,
                estimated_cost_low_usd=0.14,
                estimated_cost_high_usd=0.30,
                requests_per_minute=openrouter_requests_per_minute,
                rate_limit_owner="provider_adapter",
                verified_on=_VERIFIED_ON,
                evidence_ref=_EVIDENCE_REF,
            ),
        )
    )


IMAGE_ROUTE_CATALOG = image_route_catalog()


def configured_image_route_catalog(config: StageGenConfig) -> RouteCatalog:
    """Build host route facts without using credentials for selection or transport.

    Credential values are compared only to reject accidental embedding in the
    portable endpoint identity; they never alter which route is registered.
    """

    custom_base_urls = tuple(
        value
        for value in (
            config.openai_base_url,
            config.fal_base_url,
            config.open_router_base_url,
        )
        if value is not None
    )
    for base_url in custom_base_urls:
        lowered = base_url.lower()
        if any(secret.lower() in lowered for secret in config.secret_values()):
            raise ValueError("provider base URLs must not contain configured credential values")

    return image_route_catalog(
        openai_base_url=config.openai_base_url or "https://api.openai.com/v1",
        fal_base_url=config.fal_base_url or "https://fal.run",
        openrouter_base_url=config.open_router_base_url or "https://openrouter.ai/api/v1",
        openai_requests_per_minute=config.openai_image_ipm,
        openrouter_requests_per_minute=config.openrouter_image_ipm,
    )


@dataclass(frozen=True, slots=True)
class _ImagePolicyRule:
    default_provider: ImageProvider
    operation_variant: Literal["generation", "edit"]
    allowed_backgrounds: frozenset[str]


_IMAGE_POLICY_RULES = MappingProxyType(
    {
        IMAGE_NATIVE_GENERATION_POLICY_ID: _ImagePolicyRule(
            ImageProvider.OPENAI,
            "generation",
            frozenset({"auto", "opaque", "transparent"}),
        ),
        IMAGE_NATIVE_EDIT_POLICY_ID: _ImagePolicyRule(
            ImageProvider.OPENAI,
            "edit",
            frozenset({"auto", "opaque", "transparent"}),
        ),
        IMAGE_MASKED_EDIT_POLICY_ID: _ImagePolicyRule(
            ImageProvider.OPENAI,
            "edit",
            frozenset({"auto", "opaque", "transparent"}),
        ),
        IMAGE_CONDITIONED_REPAIR_POLICY_ID: _ImagePolicyRule(
            ImageProvider.OPENROUTER,
            "edit",
            frozenset({"auto"}),
        ),
        IMAGE_TRANSPARENT_GENERATION_POLICY_ID: _ImagePolicyRule(
            ImageProvider.OPENAI,
            "generation",
            frozenset({"transparent"}),
        ),
        IMAGE_TRANSPARENT_EDIT_POLICY_ID: _ImagePolicyRule(
            ImageProvider.OPENAI,
            "edit",
            frozenset({"transparent"}),
        ),
        IMAGE_OPAQUE_GENERATION_POLICY_ID: _ImagePolicyRule(
            ImageProvider.OPENROUTER,
            "generation",
            frozenset({"opaque"}),
        ),
        IMAGE_OPAQUE_EDIT_POLICY_ID: _ImagePolicyRule(
            ImageProvider.OPENROUTER,
            "edit",
            frozenset({"opaque"}),
        ),
    }
)

_ROUTE_ID_BY_PROVIDER_AND_VARIANT = MappingProxyType(
    {
        (ImageProvider.OPENAI, "generation"): OPENAI_IMAGE_GENERATION_ROUTE_ID,
        (ImageProvider.OPENAI, "edit"): OPENAI_IMAGE_EDIT_ROUTE_ID,
        (ImageProvider.FAL, "generation"): FAL_IMAGE_GENERATION_ROUTE_ID,
        (ImageProvider.FAL, "edit"): FAL_IMAGE_EDIT_ROUTE_ID,
        (ImageProvider.OPENROUTER, "generation"): OPENROUTER_IMAGE_GENERATION_ROUTE_ID,
        (ImageProvider.OPENROUTER, "edit"): OPENROUTER_IMAGE_REFERENCE_ROUTE_ID,
    }
)
_CONDITIONED_REPAIR_ROUTE_ID_BY_PROVIDER = MappingProxyType(
    {
        ImageProvider.OPENAI: OPENAI_IMAGE_CONDITIONED_REPAIR_ROUTE_ID,
        ImageProvider.FAL: FAL_IMAGE_CONDITIONED_REPAIR_ROUTE_ID,
        ImageProvider.OPENROUTER: OPENROUTER_IMAGE_CONDITIONED_REPAIR_ROUTE_ID,
    }
)


def _route_id_for_policy(policy_id: str, provider: ImageProvider) -> str:
    if policy_id == IMAGE_CONDITIONED_REPAIR_POLICY_ID:
        return _CONDITIONED_REPAIR_ROUTE_ID_BY_PROVIDER[provider]
    return _ROUTE_ID_BY_PROVIDER_AND_VARIANT[
        (provider, _IMAGE_POLICY_RULES[policy_id].operation_variant)
    ]


def _checked_in_policy(policy_id: str, rule: _ImagePolicyRule) -> WorkloadPolicyV1:
    return WorkloadPolicyV1(
        policy_id=policy_id,
        policy_version=IMAGE_POLICY_VERSION,
        product_id=SUNBURST_PRODUCT_ID,
        route_id=_route_id_for_policy(policy_id, rule.default_provider),
    )


IMAGE_WORKLOAD_POLICIES = MappingProxyType(
    {
        policy_id: _checked_in_policy(policy_id, rule)
        for policy_id, rule in _IMAGE_POLICY_RULES.items()
    }
)


def image_workload_policies(
    provider_override: ImageProvider | None = None,
) -> Mapping[str, WorkloadPolicyV1]:
    """Return every exact image policy under one optional scalar provider override."""

    if provider_override is None:
        return IMAGE_WORKLOAD_POLICIES
    if not isinstance(provider_override, ImageProvider):
        raise RouteResolutionError("image provider override must be openai, fal, or openrouter")
    return MappingProxyType(
        {
            policy_id: WorkloadPolicyV1(
                policy_id=policy.policy_id,
                policy_version=policy.policy_version,
                product_id=policy.product_id,
                route_id=_route_id_for_policy(policy_id, provider_override),
            )
            for policy_id, policy in IMAGE_WORKLOAD_POLICIES.items()
        }
    )


def resolve_image_route(
    requirements: ImageRouteRequirementsV1,
    *,
    policy_id: str,
    provider_override: ImageProvider | None = None,
    model_override: str | None = None,
    catalog: RouteCatalog = IMAGE_ROUTE_CATALOG,
) -> ResolvedBindingV1:
    """Resolve one exact checked-in image route, without discovery or fallback."""

    if policy_id == IMAGE_CONDITIONED_REPAIR_POLICY_ID:
        raise RouteResolutionError(
            "image.conditioned.repair uses its dedicated provider-neutral resolver"
        )

    try:
        rule = _IMAGE_POLICY_RULES[policy_id]
        policy = image_workload_policies(provider_override)[policy_id]
    except KeyError as error:
        raise RouteResolutionError(f"unregistered image workload policy: {policy_id}") from error
    if requirements.operation_variant != rule.operation_variant:
        raise RouteResolutionError(
            f"image workload policy {policy_id} requires {rule.operation_variant}, "
            f"received {requirements.operation_variant}"
        )
    if requirements.background not in rule.allowed_backgrounds:
        raise RouteResolutionError(
            f"image workload policy {policy_id} does not admit {requirements.background} background"
        )
    if requirements.quality_goal != "maximum_verified":
        raise RouteResolutionError("Stage Gen image routes require maximum_verified quality")
    if requirements.moderation_goal not in {None, "low_when_supported"}:
        raise RouteResolutionError("Stage Gen image moderation goal is unsupported")

    provider = provider_override or rule.default_provider
    if not isinstance(provider, ImageProvider):
        raise RouteResolutionError("image provider override must be openai, fal, or openrouter")
    effective_size = requirements.size
    normalized_exact_size = False
    if (
        provider in {ImageProvider.OPENAI, ImageProvider.FAL}
        and requirements.aspect_ratio not in {None, "auto"}
        and effective_size in {None, "auto"}
    ):
        if effective_size == "auto":
            raise RouteResolutionError(
                f"{provider.value} Sunburst cannot combine auto size with a fixed aspect ratio"
            )
        assert requirements.aspect_ratio is not None
        effective_size = sunburst_exact_size_for_aspect_ratio(requirements.aspect_ratio)
        normalized_exact_size = True
    route_id = policy.route_id
    selected = catalog.route(route_id)
    if selected.model.provider != provider.value:
        raise RouteResolutionError(
            f"selected route {route_id} does not belong to provider {provider.value}"
        )
    if selected.operation_variant != requirements.operation_variant:
        raise RouteResolutionError(
            f"selected route {route_id} does not implement {requirements.operation_variant}"
        )
    if requirements.aspect_ratio not in {None, "auto"}:
        assert requirements.aspect_ratio is not None
        ratio_width_text, ratio_height_text = requirements.aspect_ratio.split(":")
        ratio_width, ratio_height = int(ratio_width_text), int(ratio_height_text)
        maximum = (
            selected.exact_size_constraints.max_aspect_ratio
            if selected.exact_size_constraints is not None
            else None
        )
        ratio = max(ratio_width, ratio_height) / min(ratio_width, ratio_height)
        if maximum is not None and ratio > maximum:
            raise RouteResolutionError(
                f"selected route {route_id} does not admit aspect ratio "
                f"{requirements.aspect_ratio}; maximum is {maximum:g}:1"
            )
    _require_registered_model_override(
        catalog,
        selected=selected,
        model_override=model_override,
    )

    options = requirements.semantic_options()
    required_features = requirements.required_features
    if normalized_exact_size:
        assert effective_size is not None
        options["size"] = effective_size
        required_features = (required_features - {"flexible_size"}) | {"exact_size"}
    options["quality"] = "max"
    if requirements.moderation_goal == "low_when_supported" and provider in {
        ImageProvider.OPENAI,
        ImageProvider.OPENROUTER,
    }:
        options["moderation"] = "low"
    if requirements.operation_variant == "edit":
        options["input_fidelity"] = "omitted"
    required_limits = (
        (("reference_count_max", float(requirements.reference_count)),)
        if requirements.reference_count
        else ()
    )
    request = WorkloadRequestV1(
        policy_id=policy_id,
        operation=IMAGE_OPERATION,
        modality_spec_version=IMAGE_MODALITY_SPEC_VERSION,
        required_features=required_features,
        required_limits=required_limits,
        exact_size=_exact_size(effective_size),
        output_options=options,
    )
    return catalog.resolve(request, policy)


def resolve_configured_image_route(
    config: StageGenConfig,
    requirements: ImageRouteRequirementsV1,
    *,
    policy_id: str,
    catalog: RouteCatalog | None = None,
) -> ResolvedBindingV1:
    """Resolve one host-configured route; arbitrary model overrides stay closed."""

    selected_catalog = configured_image_route_catalog(config) if catalog is None else catalog
    try:
        policy = image_workload_policies(config.image_provider_override)[policy_id]
    except KeyError as error:
        raise RouteResolutionError(f"unregistered image workload policy: {policy_id}") from error
    provider = selected_catalog.route(policy.route_id).model.provider
    model_override = {
        ImageProvider.OPENAI.value: config.openai_image_model,
        ImageProvider.FAL.value: FAL_SUNBURST_MODEL,
        ImageProvider.OPENROUTER.value: config.image_model,
    }[provider]
    return resolve_image_route(
        requirements,
        policy_id=policy_id,
        provider_override=config.image_provider_override,
        model_override=model_override,
        catalog=selected_catalog,
    )


def _configured_conditioned_repair_selection(
    config: StageGenConfig,
    *,
    catalog: RouteCatalog | None = None,
) -> tuple[RouteCatalog, ImageProvider, WorkloadPolicyV1, RouteContractV1]:
    selected_catalog = configured_image_route_catalog(config) if catalog is None else catalog
    provider = config.image_provider_override or ImageProvider.OPENROUTER
    if not isinstance(provider, ImageProvider):
        raise RouteResolutionError("image provider override must be openai, fal, or openrouter")
    policy = image_workload_policies(config.image_provider_override)[
        IMAGE_CONDITIONED_REPAIR_POLICY_ID
    ]
    try:
        route = selected_catalog.route(policy.route_id)
    except (KeyError, RouteResolutionError) as error:
        raise RouteResolutionError(
            f"policy {policy.policy_id} selects unregistered route {policy.route_id}"
        ) from error
    if route.model.provider != provider.value:
        raise RouteResolutionError(
            f"selected route {route.route_id} does not belong to provider {provider.value}"
        )
    _require_registered_model_override(
        selected_catalog,
        selected=route,
        model_override={
            ImageProvider.OPENAI: config.openai_image_model,
            ImageProvider.FAL: FAL_SUNBURST_MODEL,
            ImageProvider.OPENROUTER: config.image_model,
        }[provider],
    )
    return selected_catalog, provider, policy, route


def configured_conditioned_repair_route_contract(
    config: StageGenConfig,
    *,
    catalog: RouteCatalog | None = None,
) -> RouteContractV1:
    """Return the exact configured repair route before request-size admission."""

    return _configured_conditioned_repair_selection(config, catalog=catalog)[3]


def resolve_configured_conditioned_repair_route(
    config: StageGenConfig,
    *,
    width: int,
    height: int,
    catalog: RouteCatalog | None = None,
) -> ResolvedBindingV1:
    """Resolve one exact-size image-repeat repair provider operation.

    OpenAI Images and Fal receive one conditioning image plus a real mask. OpenRouter
    has no mask field, so its admitted request carries the conditioning canvas and mask
    as two ordinary references. In both cases the component, not the provider, restores
    immutable pixels and accepts the repaired seam.
    """

    selected_catalog, provider, policy, _route = _configured_conditioned_repair_selection(
        config,
        catalog=catalog,
    )
    native_mask = provider in {ImageProvider.OPENAI, ImageProvider.FAL}
    reference_count = 1 if native_mask else 2
    repair_transport = "native_mask_edit" if native_mask else "reference_conditioned_edit"
    required_features = set(_CONDITIONED_REPAIR_COMMON_FEATURES)
    required_features.add("data_url_reference_input")
    required_features.add("native_mask_input" if native_mask else "reference_guidance")
    output_options: dict[str, object] = {
        "alpha_policy": "local_reconstruction",
        "aspect_ratio": "auto",
        "background": "auto",
        "guide_delivery": "mask_field" if native_mask else "image_reference",
        "immutable_region_policy": "local_reimposition",
        "input_fidelity": "omitted",
        "mask_present": native_mask,
        "mask_semantics": "white_edit_black_preserve",
        "operation_variant": repair_transport,
        "output_format": "png",
        "prompt_policy": "authored_verbatim",
        "quality": "max",
        "quality_goal": "maximum_verified",
        "reference_count": reference_count,
        "reference_delivery": "data_url",
        "repair_transport": repair_transport,
        "size": f"{width}x{height}",
    }
    if provider in {ImageProvider.OPENAI, ImageProvider.OPENROUTER}:
        output_options["moderation"] = "low"
        output_options["moderation_goal"] = "low_when_supported"
    request = WorkloadRequestV1(
        policy_id=IMAGE_CONDITIONED_REPAIR_POLICY_ID,
        operation=IMAGE_CONDITIONED_REPAIR_OPERATION,
        modality_spec_version=IMAGE_CONDITIONED_REPAIR_MODALITY_SPEC_VERSION,
        required_features=frozenset(required_features),
        required_limits=(("reference_count_max", float(reference_count)),),
        exact_size=ExactSize2DV1(width=width, height=height),
        output_options=output_options,
    )
    return selected_catalog.resolve(request, policy)


def image_policy_id_for(requirements: ImageRouteRequirementsV1) -> str:
    """Map provider-neutral image intent to its checked-in policy family."""

    if requirements.mask_present:
        return IMAGE_MASKED_EDIT_POLICY_ID
    if requirements.background == "transparent":
        return (
            IMAGE_TRANSPARENT_EDIT_POLICY_ID
            if requirements.operation_variant == "edit"
            else IMAGE_TRANSPARENT_GENERATION_POLICY_ID
        )
    if requirements.background == "opaque":
        exact_size = _exact_size(requirements.size)
        if exact_size is not None and exact_size not in _OPENROUTER_VERIFIED_EXACT_SIZES:
            return (
                IMAGE_NATIVE_EDIT_POLICY_ID
                if requirements.operation_variant == "edit"
                else IMAGE_NATIVE_GENERATION_POLICY_ID
            )
        return (
            IMAGE_OPAQUE_EDIT_POLICY_ID
            if requirements.operation_variant == "edit"
            else IMAGE_OPAQUE_GENERATION_POLICY_ID
        )
    return (
        IMAGE_NATIVE_EDIT_POLICY_ID
        if requirements.operation_variant == "edit"
        else IMAGE_NATIVE_GENERATION_POLICY_ID
    )


def configured_image_workload_resolver(
    config: StageGenConfig,
    *,
    catalog: RouteCatalog | None = None,
) -> ImageWorkloadResolver:
    """Return a pure planner callback for recipe and shared-component builders."""

    selected_catalog = configured_image_route_catalog(config) if catalog is None else catalog

    def resolve(requirements: ImageRouteRequirementsV1) -> WorkloadRequestV1:
        return resolve_configured_image_route(
            config,
            requirements,
            policy_id=image_policy_id_for(requirements),
            catalog=selected_catalog,
        ).request

    return resolve


def sunburst_exact_size_for_aspect_ratio(aspect_ratio: str) -> str | None:
    """Return the verified exact Sunburst canvas for a named aspect ratio."""

    if aspect_ratio == "auto":
        return None
    try:
        return SUNBURST_EXACT_SIZE_BY_ASPECT_RATIO[aspect_ratio]
    except KeyError as error:
        supported = ", ".join(SUNBURST_EXACT_SIZE_BY_ASPECT_RATIO)
        raise RouteResolutionError(
            f"Sunburst has no verified exact size for aspect ratio {aspect_ratio}; "
            f"supported ratios are {supported}"
        ) from error


def _require_registered_model_override(
    catalog: RouteCatalog,
    *,
    selected: RouteContractV1,
    model_override: str | None,
) -> None:
    if model_override is None:
        return
    registered = {
        route.model.model for route in catalog.routes if route.product_id == SUNBURST_PRODUCT_ID
    }
    if model_override not in registered:
        raise RouteResolutionError(f"unregistered Sunburst model override: {model_override}")
    if selected.model.model != model_override:
        raise RouteResolutionError(
            f"model override {model_override} does not match selected route {selected.route_id}"
        )


__all__ = [
    "FAL_IMAGE_EDIT_ROUTE_ID",
    "FAL_IMAGE_CONDITIONED_REPAIR_ROUTE_ID",
    "FAL_IMAGE_GENERATION_ROUTE_ID",
    "FAL_SUNBURST_MODEL",
    "FAL_SUNBURST_EDIT_ENDPOINT",
    "FAL_SUNBURST_TEXT_TO_IMAGE_ENDPOINT",
    "IMAGE_CONDITIONED_REPAIR_MODALITY_SPEC_VERSION",
    "IMAGE_CONDITIONED_REPAIR_OPERATION",
    "IMAGE_MODALITY_SPEC_VERSION",
    "IMAGE_CONDITIONED_REPAIR_POLICY_ID",
    "IMAGE_MASKED_EDIT_POLICY_ID",
    "IMAGE_NATIVE_EDIT_POLICY_ID",
    "IMAGE_NATIVE_GENERATION_POLICY_ID",
    "IMAGE_OPAQUE_EDIT_POLICY_ID",
    "IMAGE_OPAQUE_GENERATION_POLICY_ID",
    "IMAGE_OPERATION",
    "IMAGE_POLICY_VERSION",
    "IMAGE_ROUTE_CATALOG",
    "IMAGE_TRANSPARENT_EDIT_POLICY_ID",
    "IMAGE_TRANSPARENT_GENERATION_POLICY_ID",
    "IMAGE_WORKLOAD_POLICIES",
    "ImageWorkloadResolver",
    "OPENAI_IMAGE_EDIT_ROUTE_ID",
    "OPENAI_IMAGE_CONDITIONED_REPAIR_ROUTE_ID",
    "OPENAI_IMAGE_GENERATION_ROUTE_ID",
    "OPENAI_SUNBURST_MODEL",
    "OPENROUTER_IMAGE_GENERATION_ROUTE_ID",
    "OPENROUTER_IMAGE_CONDITIONED_REPAIR_ROUTE_ID",
    "OPENROUTER_IMAGE_REFERENCE_ROUTE_ID",
    "OPENROUTER_SUNBURST_MODEL",
    "SUNBURST_PRODUCT_ID",
    "SUNBURST_EXACT_SIZE_BY_ASPECT_RATIO",
    "configured_image_route_catalog",
    "configured_conditioned_repair_route_contract",
    "configured_image_workload_resolver",
    "image_policy_id_for",
    "image_route_catalog",
    "image_workload_policies",
    "resolve_configured_image_route",
    "resolve_configured_conditioned_repair_route",
    "resolve_image_route",
    "sunburst_exact_size_for_aspect_ratio",
]
