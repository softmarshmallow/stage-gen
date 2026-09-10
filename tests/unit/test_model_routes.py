from __future__ import annotations

from dataclasses import replace
from typing import Literal

import pytest

from gnode import (
    ExactSize2DV1,
    ImageRouteRequirementsV1,
    ModelRef,
    RouteCatalog,
    RouteContractV1,
    RouteResolutionError,
)
from stage_gen.config import StageGenConfig
from stage_gen.image_product import ImageProvider
from stage_gen.model_routes import (
    FAL_IMAGE_CONDITIONED_REPAIR_ROUTE_ID,
    FAL_IMAGE_EDIT_ROUTE_ID,
    FAL_IMAGE_GENERATION_ROUTE_ID,
    FAL_SUNBURST_MODEL,
    IMAGE_CONDITIONED_REPAIR_MODALITY_SPEC_VERSION,
    IMAGE_CONDITIONED_REPAIR_OPERATION,
    IMAGE_CONDITIONED_REPAIR_POLICY_ID,
    IMAGE_MASKED_EDIT_POLICY_ID,
    IMAGE_MODALITY_SPEC_VERSION,
    IMAGE_NATIVE_EDIT_POLICY_ID,
    IMAGE_NATIVE_GENERATION_POLICY_ID,
    IMAGE_OPAQUE_EDIT_POLICY_ID,
    IMAGE_OPAQUE_GENERATION_POLICY_ID,
    IMAGE_OPERATION,
    IMAGE_ROUTE_CATALOG,
    IMAGE_TRANSPARENT_EDIT_POLICY_ID,
    IMAGE_TRANSPARENT_GENERATION_POLICY_ID,
    IMAGE_WORKLOAD_POLICIES,
    OPENAI_IMAGE_CONDITIONED_REPAIR_ROUTE_ID,
    OPENAI_IMAGE_EDIT_ROUTE_ID,
    OPENAI_IMAGE_GENERATION_ROUTE_ID,
    OPENAI_SUNBURST_MODEL,
    OPENROUTER_IMAGE_CONDITIONED_REPAIR_ROUTE_ID,
    OPENROUTER_IMAGE_GENERATION_ROUTE_ID,
    OPENROUTER_IMAGE_REFERENCE_ROUTE_ID,
    OPENROUTER_SUNBURST_MODEL,
    SUNBURST_PRODUCT_ID,
    configured_image_route_catalog,
    configured_image_workload_resolver,
    image_policy_id_for,
    image_route_catalog,
    image_workload_policies,
    resolve_configured_conditioned_repair_route,
    resolve_configured_image_route,
    resolve_image_route,
    sunburst_exact_size_for_aspect_ratio,
)


@pytest.mark.parametrize(
    ("provider", "expected_route", "expected_references", "expected_mask"),
    [
        (None, OPENROUTER_IMAGE_CONDITIONED_REPAIR_ROUTE_ID, 2, False),
        (ImageProvider.OPENAI, OPENAI_IMAGE_CONDITIONED_REPAIR_ROUTE_ID, 1, True),
        (ImageProvider.FAL, FAL_IMAGE_CONDITIONED_REPAIR_ROUTE_ID, 1, True),
        (
            ImageProvider.OPENROUTER,
            OPENROUTER_IMAGE_CONDITIONED_REPAIR_ROUTE_ID,
            2,
            False,
        ),
    ],
)
def test_conditioned_repair_policy_seals_truthful_provider_transport(
    provider: ImageProvider | None,
    expected_route: str,
    expected_references: int,
    expected_mask: bool,
) -> None:
    resolved = resolve_configured_conditioned_repair_route(
        StageGenConfig(image_provider_override=provider),
        width=1024,
        height=1024,
    )

    assert resolved.policy.policy_id == IMAGE_CONDITIONED_REPAIR_POLICY_ID
    assert resolved.route.route_id == expected_route
    assert resolved.route.operation == IMAGE_CONDITIONED_REPAIR_OPERATION
    assert "conditioned_repair" in resolved.request.required_features
    assert "data_url_reference_input" in resolved.route.features
    assert "data_url_reference_input" in resolved.request.required_features
    assert resolved.request.output_options["quality"] == "max"
    assert resolved.request.output_options["background"] == "auto"
    assert resolved.request.output_options["output_format"] == "png"
    assert resolved.request.output_options["reference_count"] == expected_references
    assert resolved.request.output_options["reference_delivery"] == "data_url"
    assert resolved.request.output_options["mask_present"] is expected_mask
    assert resolved.request.output_options["size"] == "1024x1024"
    assert resolved.request.exact_size == ExactSize2DV1(width=1024, height=1024)
    if expected_mask:
        assert resolved.route.operation_variant == "native_mask_edit"
        assert "native_mask_input" in resolved.request.required_features
    else:
        assert resolved.route.operation_variant == "reference_conditioned_edit"
        assert "reference_guidance" in resolved.request.required_features


def test_conditioned_repair_never_falls_back_from_a_missing_selected_route() -> None:
    catalog = RouteCatalog(
        tuple(
            route
            for route in IMAGE_ROUTE_CATALOG.routes
            if route.route_id != FAL_IMAGE_CONDITIONED_REPAIR_ROUTE_ID
        )
    )

    with pytest.raises(RouteResolutionError, match="selects unregistered route"):
        resolve_configured_conditioned_repair_route(
            StageGenConfig(image_provider_override=ImageProvider.FAL),
            width=1024,
            height=1024,
            catalog=catalog,
        )


def _requirements(
    *,
    operation_variant: Literal["generation", "edit"] = "generation",
    background: Literal["auto", "opaque", "transparent"] = "transparent",
    output_format: Literal["png", "jpeg", "webp"] = "png",
    size: str | None = "1536x1024",
    aspect_ratio: str | None = None,
    resolution: Literal["512", "1K", "2K", "4K"] | None = None,
    output_compression: int | None = None,
    reference_count: int | None = None,
    mask_present: bool = False,
    reference_delivery: Literal["data_url", "hosted_url", "mixed"] | None = None,
) -> ImageRouteRequirementsV1:
    if reference_count is None:
        reference_count = 1 if operation_variant == "edit" else 0
    return ImageRouteRequirementsV1(
        operation_variant=operation_variant,
        background=background,
        output_format=output_format,
        size=size,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        output_compression=output_compression,
        reference_count=reference_count,
        mask_present=mask_present,
        reference_delivery=reference_delivery,
    )


def test_catalog_contains_only_explicit_sunburst_routes() -> None:
    routes = IMAGE_ROUTE_CATALOG.routes

    assert {route.route_id for route in routes} == {
        OPENAI_IMAGE_GENERATION_ROUTE_ID,
        OPENAI_IMAGE_EDIT_ROUTE_ID,
        FAL_IMAGE_GENERATION_ROUTE_ID,
        FAL_IMAGE_EDIT_ROUTE_ID,
        OPENROUTER_IMAGE_GENERATION_ROUTE_ID,
        OPENROUTER_IMAGE_REFERENCE_ROUTE_ID,
        OPENAI_IMAGE_CONDITIONED_REPAIR_ROUTE_ID,
        FAL_IMAGE_CONDITIONED_REPAIR_ROUTE_ID,
        OPENROUTER_IMAGE_CONDITIONED_REPAIR_ROUTE_ID,
    }
    assert {route.product_id for route in routes} == {SUNBURST_PRODUCT_ID}
    assert {route.operation for route in routes} == {
        IMAGE_OPERATION,
        IMAGE_CONDITIONED_REPAIR_OPERATION,
    }
    assert {
        route.modality_spec_version for route in routes if route.operation == IMAGE_OPERATION
    } == {IMAGE_MODALITY_SPEC_VERSION}
    assert {
        route.modality_spec_version
        for route in routes
        if route.operation == IMAGE_CONDITIONED_REPAIR_OPERATION
    } == {IMAGE_CONDITIONED_REPAIR_MODALITY_SPEC_VERSION}
    assert all("flare" not in route.route_id for route in routes)
    assert all("responses" not in route.surface for route in routes)
    assert {
        route.adapter_behavior_version
        for route in routes
        if route.operation == IMAGE_OPERATION and route.model.provider == "openrouter"
    } == {"3"}

    exact = {route.route_id: (route.model, route.surface, route.endpoint) for route in routes}
    assert exact[OPENAI_IMAGE_GENERATION_ROUTE_ID] == (
        ModelRef(OPENAI_SUNBURST_MODEL, "openai"),
        "openai-images",
        "https://api.openai.com/v1/images/generations",
    )
    assert exact[OPENAI_IMAGE_EDIT_ROUTE_ID] == (
        ModelRef(OPENAI_SUNBURST_MODEL, "openai"),
        "openai-images",
        "https://api.openai.com/v1/images/edits",
    )
    assert exact[FAL_IMAGE_GENERATION_ROUTE_ID] == (
        ModelRef(FAL_SUNBURST_MODEL, "fal"),
        "fal-run",
        "https://fal.run/openai/gpt-image-2.5/sunburst/text-to-image",
    )
    assert exact[FAL_IMAGE_EDIT_ROUTE_ID] == (
        ModelRef(FAL_SUNBURST_MODEL, "fal"),
        "fal-run",
        "https://fal.run/openai/gpt-image-2.5/sunburst/edit",
    )
    assert exact[OPENROUTER_IMAGE_GENERATION_ROUTE_ID] == (
        ModelRef(OPENROUTER_SUNBURST_MODEL, "openrouter"),
        "openrouter-images",
        "https://openrouter.ai/api/v1/images",
    )
    assert exact[OPENROUTER_IMAGE_REFERENCE_ROUTE_ID] == (
        ModelRef(OPENROUTER_SUNBURST_MODEL, "openrouter"),
        "openrouter-images",
        "https://openrouter.ai/api/v1/images",
    )
    assert exact[OPENAI_IMAGE_CONDITIONED_REPAIR_ROUTE_ID] == (
        ModelRef(OPENAI_SUNBURST_MODEL, "openai"),
        "openai-images",
        "https://api.openai.com/v1/images/edits",
    )
    assert exact[FAL_IMAGE_CONDITIONED_REPAIR_ROUTE_ID] == (
        ModelRef(FAL_SUNBURST_MODEL, "fal"),
        "fal-run",
        "https://fal.run/openai/gpt-image-2.5/sunburst/edit",
    )
    assert exact[OPENROUTER_IMAGE_CONDITIONED_REPAIR_ROUTE_ID] == (
        ModelRef(OPENROUTER_SUNBURST_MODEL, "openrouter"),
        "openrouter-images",
        "https://openrouter.ai/api/v1/images",
    )
    repair_routes = [
        route for route in routes if route.operation == IMAGE_CONDITIONED_REPAIR_OPERATION
    ]
    assert {route.adapter_id for route in repair_routes} == {"stage-gen-image-repeat-repair-v1"}
    assert {route.operation_variant for route in repair_routes} == {
        "native_mask_edit",
        "reference_conditioned_edit",
    }

    native_routes = [
        route
        for route in routes
        if route.operation == IMAGE_OPERATION and route.model.provider in {"openai", "fal"}
    ]
    assert all("custom_exact_size" in route.features for route in native_routes)
    assert {
        (
            constraints.width_multiple,
            constraints.height_multiple,
            constraints.min_area,
            constraints.max_area,
            constraints.max_edge,
            constraints.max_aspect_ratio,
        )
        for route in native_routes
        if (constraints := route.exact_size_constraints) is not None
    } == {(16, 16, 655_360, 8_294_400, 3_840, 3.0)}

    openrouter_routes = [
        route
        for route in routes
        if route.operation == IMAGE_OPERATION and route.model.provider == "openrouter"
    ]
    assert all("custom_exact_size" not in route.features for route in openrouter_routes)
    assert {
        (size.width, size.height)
        for route in openrouter_routes
        if route.exact_size_constraints is not None
        for size in route.exact_size_constraints.allowed_sizes or ()
    } == {
        (1024, 1024),
        (1152, 2496),
        (1712, 2560),
        (2064, 1008),
        (2496, 1152),
        (2560, 1440),
        (2560, 1712),
    }


def test_configured_catalog_seals_custom_material_endpoints_without_credentials() -> None:
    config = StageGenConfig(
        openai_base_url="https://openai.example.test/v1/",
        fal_base_url="https://fal.example.test/",
        open_router_base_url="https://openrouter.example.test/api/v1/",
    )
    routes = configured_image_route_catalog(config)

    assert routes.route(OPENAI_IMAGE_GENERATION_ROUTE_ID).endpoint == (
        "https://openai.example.test/v1/images/generations"
    )
    assert routes.route(FAL_IMAGE_GENERATION_ROUTE_ID).endpoint.startswith(
        "https://fal.example.test/"
    )
    assert routes.route(OPENROUTER_IMAGE_GENERATION_ROUTE_ID).endpoint == (
        "https://openrouter.example.test/api/v1/images"
    )


def test_configured_catalog_refuses_a_credential_embedded_in_a_base_url() -> None:
    credential = "credential-host-fragment"
    config = StageGenConfig(
        openai_api_key=credential,
        openai_base_url=f"https://{credential}.example.test/v1",
    )

    with pytest.raises(ValueError, match="must not contain configured credential values") as error:
        configured_image_route_catalog(config)

    assert credential not in str(error.value)


@pytest.mark.parametrize(
    ("policy_id", "requirements", "route_id"),
    [
        (
            IMAGE_TRANSPARENT_GENERATION_POLICY_ID,
            _requirements(),
            OPENAI_IMAGE_GENERATION_ROUTE_ID,
        ),
        (
            IMAGE_TRANSPARENT_EDIT_POLICY_ID,
            _requirements(operation_variant="edit", mask_present=True),
            OPENAI_IMAGE_EDIT_ROUTE_ID,
        ),
    ],
)
def test_transparent_workloads_default_to_openai_images(
    policy_id: str,
    requirements: ImageRouteRequirementsV1,
    route_id: str,
) -> None:
    resolved = resolve_image_route(requirements, policy_id=policy_id)

    assert resolved.route.route_id == route_id
    assert resolved.route.model == ModelRef(OPENAI_SUNBURST_MODEL, "openai")
    assert resolved.route.surface == "openai-images"
    assert resolved.request.output_options["quality_goal"] == "maximum_verified"
    assert resolved.request.output_options["quality"] == "max"
    assert resolved.request.output_options["moderation_goal"] == "low_when_supported"
    assert resolved.request.output_options["moderation"] == "low"
    assert resolved.request.output_options["prompt_policy"] == "authored_verbatim"
    assert resolved.request.output_options["size"] == "1536x1024"
    assert resolved.request.exact_size == ExactSize2DV1(width=1536, height=1024)


@pytest.mark.parametrize(
    ("policy_id", "requirements", "route_id"),
    [
        (
            IMAGE_TRANSPARENT_GENERATION_POLICY_ID,
            _requirements(),
            FAL_IMAGE_GENERATION_ROUTE_ID,
        ),
        (
            IMAGE_TRANSPARENT_EDIT_POLICY_ID,
            _requirements(operation_variant="edit", mask_present=True),
            FAL_IMAGE_EDIT_ROUTE_ID,
        ),
    ],
)
def test_fal_override_admits_transparency_and_omits_unsupported_moderation(
    policy_id: str,
    requirements: ImageRouteRequirementsV1,
    route_id: str,
) -> None:
    resolved = resolve_image_route(
        requirements,
        policy_id=policy_id,
        provider_override=ImageProvider.FAL,
    )

    assert resolved.route.route_id == route_id
    assert resolved.route.model == ModelRef(FAL_SUNBURST_MODEL, "fal")
    assert "transparent_background" in resolved.route.features
    assert "custom_exact_size" in resolved.route.features
    assert resolved.request.output_options["quality"] == "max"
    assert "moderation" not in resolved.request.output_options
    if requirements.mask_present:
        assert "masked_edit" in resolved.route.features
        assert resolved.request.output_options["input_fidelity"] == "omitted"


@pytest.mark.parametrize(
    ("policy_id", "requirements", "route_id"),
    [
        (
            IMAGE_OPAQUE_GENERATION_POLICY_ID,
            _requirements(background="opaque", size="2560x1440"),
            OPENROUTER_IMAGE_GENERATION_ROUTE_ID,
        ),
        (
            IMAGE_OPAQUE_EDIT_POLICY_ID,
            _requirements(
                operation_variant="edit",
                background="opaque",
                size="2560x1440",
            ),
            OPENROUTER_IMAGE_REFERENCE_ROUTE_ID,
        ),
    ],
)
def test_designated_opaque_workloads_keep_current_openrouter_default(
    policy_id: str,
    requirements: ImageRouteRequirementsV1,
    route_id: str,
) -> None:
    resolved = resolve_image_route(requirements, policy_id=policy_id)

    assert resolved.route.route_id == route_id
    assert resolved.route.model == ModelRef(OPENROUTER_SUNBURST_MODEL, "openrouter")
    assert resolved.request.output_options["quality"] == "max"
    assert resolved.request.output_options["moderation"] == "low"


@pytest.mark.parametrize(
    ("provider", "expected_route"),
    [
        (ImageProvider.OPENAI, OPENAI_IMAGE_EDIT_ROUTE_ID),
        (ImageProvider.FAL, FAL_IMAGE_EDIT_ROUTE_ID),
        (ImageProvider.OPENROUTER, OPENROUTER_IMAGE_REFERENCE_ROUTE_ID),
    ],
)
def test_one_scalar_provider_override_switches_the_matching_action_only(
    provider: ImageProvider,
    expected_route: str,
) -> None:
    resolved = resolve_image_route(
        _requirements(
            operation_variant="edit",
            background="opaque",
            size="2560x1440",
        ),
        policy_id=IMAGE_OPAQUE_EDIT_POLICY_ID,
        provider_override=provider,
    )

    assert resolved.route.route_id == expected_route
    assert resolved.route.model.provider == provider.value
    assert resolved.route.operation_variant == "edit"


def test_openrouter_transparent_override_refuses_without_falling_back_to_fal() -> None:
    with pytest.raises(
        RouteResolutionError,
        match=r"openrouter.*unsupported.*transparent_background",
    ):
        resolve_image_route(
            _requirements(),
            policy_id=IMAGE_TRANSPARENT_GENERATION_POLICY_ID,
            provider_override=ImageProvider.OPENROUTER,
        )


def test_openrouter_masked_edit_refuses_without_falling_back_to_openai() -> None:
    with pytest.raises(RouteResolutionError, match=r"unsupported.*masked_edit"):
        resolve_image_route(
            _requirements(operation_variant="edit", background="opaque", mask_present=True),
            policy_id=IMAGE_OPAQUE_EDIT_POLICY_ID,
            provider_override=ImageProvider.OPENROUTER,
        )


def test_hosted_edit_reference_is_admitted_only_by_routes_that_can_fetch_it() -> None:
    requirements = _requirements(
        operation_variant="edit",
        background="auto",
        size="1024x1024",
        reference_delivery="hosted_url",
    )

    with pytest.raises(RouteResolutionError, match="hosted_url_reference_input"):
        resolve_image_route(requirements, policy_id=IMAGE_NATIVE_EDIT_POLICY_ID)

    for provider in (ImageProvider.FAL, ImageProvider.OPENROUTER):
        resolved = resolve_image_route(
            requirements,
            policy_id=IMAGE_NATIVE_EDIT_POLICY_ID,
            provider_override=provider,
        )
        assert "hosted_url_reference_input" in resolved.route.features
        assert resolved.request.output_options["reference_delivery"] == "hosted_url"


def test_openrouter_seals_only_its_canary_backed_png_output() -> None:
    resolved = resolve_image_route(
        _requirements(
            background="opaque",
            output_format="png",
            size="2560x1440",
        ),
        policy_id=IMAGE_OPAQUE_GENERATION_POLICY_ID,
    )

    assert "png_output" in resolved.route.features
    assert "jpeg_output" not in resolved.route.features
    assert "webp_output" not in resolved.route.features
    assert resolved.request.output_options["output_format"] == "png"

    for output_format in ("jpeg", "webp"):
        with pytest.raises(RouteResolutionError, match=f"missing features {output_format}_output"):
            resolve_image_route(
                _requirements(
                    background="opaque",
                    output_format=output_format,
                    output_compression=80,
                    size="2560x1440",
                ),
                policy_id=IMAGE_OPAQUE_GENERATION_POLICY_ID,
            )


def test_unverified_resolution_ladder_is_refused_by_every_sunburst_route() -> None:
    requirements = _requirements(
        background="opaque",
        size=None,
        aspect_ratio="16:9",
        resolution="2K",
    )
    for provider in (ImageProvider.OPENROUTER, ImageProvider.OPENAI, ImageProvider.FAL):
        with pytest.raises(RouteResolutionError, match=r"unsupported.*resolution_ladder"):
            resolve_image_route(
                requirements,
                policy_id=IMAGE_OPAQUE_GENERATION_POLICY_ID,
                provider_override=provider,
            )


@pytest.mark.parametrize("provider", [ImageProvider.OPENAI, ImageProvider.FAL])
def test_native_routes_normalize_verified_aspect_to_an_exact_canvas(
    provider: ImageProvider,
) -> None:
    resolved = resolve_image_route(
        _requirements(size=None, aspect_ratio="16:9"),
        policy_id=IMAGE_TRANSPARENT_GENERATION_POLICY_ID,
        provider_override=provider,
    )

    assert resolved.request.output_options["aspect_ratio"] == "16:9"
    assert resolved.request.output_options["size"] == "2048x1152"
    assert resolved.request.exact_size == ExactSize2DV1(width=2048, height=1152)
    assert "exact_size" in resolved.request.required_features
    assert "flexible_size" not in resolved.request.required_features


@pytest.mark.parametrize("provider", [ImageProvider.OPENAI, ImageProvider.FAL])
def test_native_routes_refuse_unverified_aspect_only_requests(provider: ImageProvider) -> None:
    with pytest.raises(RouteResolutionError, match="no verified exact size for aspect ratio 5:4"):
        resolve_image_route(
            _requirements(size=None, aspect_ratio="5:4"),
            policy_id=IMAGE_TRANSPARENT_GENERATION_POLICY_ID,
            provider_override=provider,
        )


def test_route_contract_refuses_aspect_ratio_outside_its_envelope() -> None:
    with pytest.raises(RouteResolutionError, match=r"aspect ratio 100:1; maximum is 3:1"):
        resolve_image_route(
            _requirements(
                background="opaque",
                size=None,
                aspect_ratio="100:1",
            ),
            policy_id=IMAGE_OPAQUE_GENERATION_POLICY_ID,
            provider_override=ImageProvider.OPENROUTER,
        )


@pytest.mark.parametrize(
    ("size", "pattern"),
    [
        ("640x360", r"height 360 is not a multiple of 16.*area 230400 is below minimum"),
        ("1025x1024", r"width 1025 is not a multiple of 16"),
    ],
)
def test_fal_invalid_exact_size_refuses_during_planning(size: str, pattern: str) -> None:
    with pytest.raises(RouteResolutionError, match=pattern):
        resolve_image_route(
            _requirements(size=size),
            policy_id=IMAGE_TRANSPARENT_GENERATION_POLICY_ID,
            provider_override=ImageProvider.FAL,
        )


def test_unverified_openrouter_custom_size_refuses_without_fallback() -> None:
    requirements = _requirements(background="opaque", size="2880x960")

    assert image_policy_id_for(requirements) == IMAGE_NATIVE_GENERATION_POLICY_ID
    assert (
        resolve_image_route(
            requirements,
            policy_id=image_policy_id_for(requirements),
        ).route.model.provider
        == "openai"
    )
    assert (
        resolve_image_route(
            requirements,
            policy_id=image_policy_id_for(requirements),
            provider_override=ImageProvider.FAL,
        ).route.model.provider
        == "fal"
    )
    with pytest.raises(RouteResolutionError, match=r"openrouter.*unsupported.*exact size"):
        resolve_image_route(
            requirements,
            policy_id=image_policy_id_for(requirements),
            provider_override=ImageProvider.OPENROUTER,
        )


def test_conditioned_repair_refuses_unverified_openrouter_exact_size() -> None:
    for provider in (ImageProvider.OPENAI, ImageProvider.FAL):
        resolved = resolve_configured_conditioned_repair_route(
            StageGenConfig(image_provider_override=provider),
            width=1536,
            height=1024,
        )
        assert resolved.request.exact_size == ExactSize2DV1(width=1536, height=1024)

    with pytest.raises(RouteResolutionError, match=r"openrouter.*unsupported.*exact size"):
        resolve_configured_conditioned_repair_route(
            StageGenConfig(image_provider_override=ImageProvider.OPENROUTER),
            width=1536,
            height=1024,
        )


def test_shipped_custom_canvas_passes_native_provider_admission() -> None:
    requirements = _requirements(background="opaque", size="1280x720")
    policy_id = image_policy_id_for(requirements)

    assert resolve_image_route(requirements, policy_id=policy_id).route.model.provider == "openai"
    assert (
        resolve_image_route(
            requirements,
            policy_id=policy_id,
            provider_override=ImageProvider.FAL,
        ).route.model.provider
        == "fal"
    )


def test_missing_selected_route_refuses_offline() -> None:
    without_fal_generation = RouteCatalog(
        tuple(
            route
            for route in IMAGE_ROUTE_CATALOG.routes
            if route.route_id != FAL_IMAGE_GENERATION_ROUTE_ID
        )
    )

    with pytest.raises(RouteResolutionError, match="unregistered route"):
        resolve_image_route(
            _requirements(),
            policy_id=IMAGE_TRANSPARENT_GENERATION_POLICY_ID,
            provider_override=ImageProvider.FAL,
            catalog=without_fal_generation,
        )


def test_public_policy_map_rewrites_every_action_with_one_scalar_override() -> None:
    assert image_workload_policies() is IMAGE_WORKLOAD_POLICIES
    fal = image_workload_policies(ImageProvider.FAL)

    assert set(fal) == set(IMAGE_WORKLOAD_POLICIES)
    for policy_id, policy in fal.items():
        expected = (
            FAL_IMAGE_CONDITIONED_REPAIR_ROUTE_ID
            if policy_id == IMAGE_CONDITIONED_REPAIR_POLICY_ID
            else FAL_IMAGE_EDIT_ROUTE_ID
            if policy_id.endswith(".edit")
            else FAL_IMAGE_GENERATION_ROUTE_ID
        )
        assert policy.route_id == expected
        assert IMAGE_WORKLOAD_POLICIES[policy_id].route_id != expected

    assert (
        image_workload_policies(ImageProvider.OPENROUTER)[
            IMAGE_TRANSPARENT_GENERATION_POLICY_ID
        ].route_id
        == OPENROUTER_IMAGE_GENERATION_ROUTE_ID
    )
    with pytest.raises(RouteResolutionError, match="provider override"):
        image_workload_policies("fal")  # type: ignore[arg-type]


def test_unregistered_policy_and_mismatched_action_refuse_offline() -> None:
    with pytest.raises(RouteResolutionError, match="unregistered image workload policy"):
        resolve_image_route(_requirements(), policy_id="image.unknown.generation")
    with pytest.raises(RouteResolutionError, match="requires edit"):
        resolve_image_route(_requirements(), policy_id=IMAGE_NATIVE_EDIT_POLICY_ID)
    with pytest.raises(RouteResolutionError, match="does not admit transparent"):
        resolve_image_route(_requirements(), policy_id=IMAGE_OPAQUE_GENERATION_POLICY_ID)


def test_reference_count_limit_refuses_before_provider_construction() -> None:
    with pytest.raises(
        RouteResolutionError,
        match=r"reference_count_max 16.*below requested 17",
    ):
        resolve_image_route(
            _requirements(operation_variant="edit", reference_count=17),
            policy_id=IMAGE_TRANSPARENT_EDIT_POLICY_ID,
            provider_override=ImageProvider.FAL,
        )


def test_model_override_must_match_the_registered_selected_route() -> None:
    matched = resolve_image_route(
        _requirements(),
        policy_id=IMAGE_TRANSPARENT_GENERATION_POLICY_ID,
        model_override=OPENAI_SUNBURST_MODEL,
    )
    assert matched.route.model.model == OPENAI_SUNBURST_MODEL

    with pytest.raises(RouteResolutionError, match="unregistered Sunburst model override"):
        resolve_image_route(
            _requirements(),
            policy_id=IMAGE_TRANSPARENT_GENERATION_POLICY_ID,
            model_override="gpt-image-unregistered",
        )
    with pytest.raises(RouteResolutionError, match="does not match selected route"):
        resolve_image_route(
            _requirements(),
            policy_id=IMAGE_TRANSPARENT_GENERATION_POLICY_ID,
            model_override=OPENROUTER_SUNBURST_MODEL,
        )


def test_configured_resolution_uses_one_provider_switch_and_refuses_unknown_models() -> None:
    resolved = resolve_configured_image_route(
        StageGenConfig(image_provider_override=ImageProvider.FAL),
        _requirements(),
        policy_id=IMAGE_TRANSPARENT_GENERATION_POLICY_ID,
    )
    assert resolved.route.route_id == FAL_IMAGE_GENERATION_ROUTE_ID

    with pytest.raises(RouteResolutionError, match="unregistered Sunburst model override"):
        resolve_configured_image_route(
            StageGenConfig(openai_image_model="gpt-image-unregistered"),
            _requirements(),
            policy_id=IMAGE_TRANSPARENT_GENERATION_POLICY_ID,
        )


def test_masked_edit_policy_defaults_capable_and_openrouter_refuses_without_fallback() -> None:
    requirements = _requirements(
        operation_variant="edit",
        background="opaque",
        mask_present=True,
    )
    assert image_policy_id_for(requirements) == IMAGE_MASKED_EDIT_POLICY_ID
    assert (
        resolve_image_route(requirements, policy_id=IMAGE_MASKED_EDIT_POLICY_ID).route.route_id
        == OPENAI_IMAGE_EDIT_ROUTE_ID
    )
    assert (
        resolve_image_route(
            requirements,
            policy_id=IMAGE_MASKED_EDIT_POLICY_ID,
            provider_override=ImageProvider.FAL,
        ).route.route_id
        == FAL_IMAGE_EDIT_ROUTE_ID
    )
    with pytest.raises(RouteResolutionError, match=r"unsupported.*masked_edit"):
        resolve_image_route(
            requirements,
            policy_id=IMAGE_MASKED_EDIT_POLICY_ID,
            provider_override=ImageProvider.OPENROUTER,
        )


def test_configured_workload_callback_keeps_exact_policy_and_provider() -> None:
    resolve = configured_image_workload_resolver(
        StageGenConfig(image_provider_override=ImageProvider.FAL)
    )
    request = resolve(_requirements(background="transparent"))

    assert request.policy_id == IMAGE_TRANSPARENT_GENERATION_POLICY_ID
    policy = image_workload_policies(ImageProvider.FAL)[request.policy_id]
    assert IMAGE_ROUTE_CATALOG.route(policy.route_id).model.provider == "fal"


@pytest.mark.parametrize(
    ("aspect_ratio", "size"),
    [("1:1", "1024x1024"), ("16:9", "2048x1152"), ("21:9", "2688x1152")],
)
def test_verified_aspect_ratios_have_exact_sunburst_canvases(aspect_ratio: str, size: str) -> None:
    assert sunburst_exact_size_for_aspect_ratio(aspect_ratio) == size


def test_unverified_aspect_ratio_has_no_invented_sunburst_canvas() -> None:
    with pytest.raises(RouteResolutionError, match="no verified exact size"):
        sunburst_exact_size_for_aspect_ratio("5:4")


def test_material_options_change_output_identity() -> None:
    first = resolve_image_route(
        _requirements(size="1536x1024"),
        policy_id=IMAGE_TRANSPARENT_GENERATION_POLICY_ID,
    )
    second = resolve_image_route(
        _requirements(size="1024x1024"),
        policy_id=IMAGE_TRANSPARENT_GENERATION_POLICY_ID,
    )

    assert first.behavior_fingerprint == second.behavior_fingerprint
    assert first.output_fingerprint != second.output_fingerprint


def test_operational_metadata_does_not_change_route_or_output_identity() -> None:
    original = resolve_image_route(
        _requirements(),
        policy_id=IMAGE_TRANSPARENT_GENERATION_POLICY_ID,
    )
    changed_routes = tuple(
        replace(
            route,
            estimated_duration_seconds=999.0,
            estimated_cost_low_usd=4.0,
            estimated_cost_high_usd=5.0,
            requests_per_minute=7,
            verified_on="2026-09-10",
            evidence_ref="issue://operational-refresh",
        )
        if route.route_id == OPENAI_IMAGE_GENERATION_ROUTE_ID
        else route
        for route in IMAGE_ROUTE_CATALOG.routes
    )
    refreshed = resolve_image_route(
        _requirements(),
        policy_id=IMAGE_TRANSPARENT_GENERATION_POLICY_ID,
        catalog=RouteCatalog(changed_routes),
    )

    assert refreshed.route.estimated_cost_high_usd == 5.0
    assert refreshed.route_contract_fingerprint == original.route_contract_fingerprint
    assert refreshed.behavior_fingerprint == original.behavior_fingerprint
    assert refreshed.output_fingerprint == original.output_fingerprint


def test_inactive_catalog_route_does_not_affect_exact_policy_selection() -> None:
    original = resolve_image_route(
        _requirements(background="opaque", size="2560x1440"),
        policy_id=IMAGE_OPAQUE_GENERATION_POLICY_ID,
    )
    inactive = RouteContractV1(
        route_id="image.unrelated.provider.generation",
        product_id="unrelated-image-product",
        operation=IMAGE_OPERATION,
        operation_variant="generation",
        model=ModelRef("unrelated-image-model", "unrelated"),
        modality_spec_version=IMAGE_MODALITY_SPEC_VERSION,
        surface="unrelated-images",
        endpoint="https://images.example.test/v1/generate",
        adapter_id="unrelated-image-v1",
        adapter_behavior_version="1",
        features=frozenset({"text_to_image"}),
        resource_id="unrelated-image",
        estimated_duration_seconds=1.0,
        estimated_cost_low_usd=0.0,
        estimated_cost_high_usd=0.0,
    )
    expanded = resolve_image_route(
        _requirements(background="opaque", size="2560x1440"),
        policy_id=IMAGE_OPAQUE_GENERATION_POLICY_ID,
        catalog=RouteCatalog((*IMAGE_ROUTE_CATALOG.routes, inactive)),
    )

    assert expanded.route.route_id == original.route.route_id
    assert expanded.route_contract_fingerprint == original.route_contract_fingerprint
    assert expanded.output_fingerprint == original.output_fingerprint


def test_pacing_factory_values_are_operational_only() -> None:
    default = resolve_image_route(
        _requirements(background="opaque", size="2560x1440"),
        policy_id=IMAGE_OPAQUE_GENERATION_POLICY_ID,
        catalog=image_route_catalog(
            openai_requests_per_minute=150,
            openrouter_requests_per_minute=150,
        ),
    )
    throttled = resolve_image_route(
        _requirements(background="opaque", size="2560x1440"),
        policy_id=IMAGE_OPAQUE_GENERATION_POLICY_ID,
        catalog=image_route_catalog(openai_requests_per_minute=3, openrouter_requests_per_minute=5),
    )

    assert default.route.requests_per_minute == 150
    assert throttled.route.requests_per_minute == 5
    assert throttled.route_contract_fingerprint == default.route_contract_fingerprint
    assert throttled.output_fingerprint == default.output_fingerprint


def test_custom_base_urls_are_normalized_and_sealed_as_material_endpoints() -> None:
    production = resolve_image_route(
        _requirements(),
        policy_id=IMAGE_TRANSPARENT_GENERATION_POLICY_ID,
    )
    custom = resolve_image_route(
        _requirements(),
        policy_id=IMAGE_TRANSPARENT_GENERATION_POLICY_ID,
        catalog=image_route_catalog(
            openai_base_url=" https://openai-gateway.example.test/v1/ ",
            fal_base_url="https://fal-gateway.example.test/",
            openrouter_base_url="https://openrouter-gateway.example.test/api/v1/",
        ),
    )

    assert custom.route.endpoint == "https://openai-gateway.example.test/v1/images/generations"
    assert custom.behavior_fingerprint != production.behavior_fingerprint
    assert custom.output_fingerprint != production.output_fingerprint

    with pytest.raises(ValueError, match="without query or fragment"):
        image_route_catalog(openai_base_url="https://gateway.example.test/v1?tenant=secret")
    with pytest.raises(ValueError, match="arbitrary gateway paths"):
        image_route_catalog(
            openai_base_url="https://gateway.example.test/token/private-credential/v1"
        )
    with pytest.raises(ValueError, match="must use HTTPS"):
        image_route_catalog(openai_base_url="http://gateway.example.test/v1")
    with pytest.raises(ValueError, match="non-secret HTTP"):
        image_route_catalog(openai_base_url="https://:443/v1")
    for invalid_port in ("bad", "99999"):
        with pytest.raises(ValueError, match="valid network port"):
            image_route_catalog(openai_base_url=f"https://gateway.example.test:{invalid_port}/v1")

    loopback = image_route_catalog(openai_base_url="http://127.0.0.1:8765/v1")
    assert loopback.route(OPENAI_IMAGE_GENERATION_ROUTE_ID).endpoint == (
        "http://127.0.0.1:8765/v1/images/generations"
    )
