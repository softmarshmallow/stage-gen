from __future__ import annotations

from dataclasses import replace

import pytest

from gnode import (
    ExactSize2DV1,
    ExactSizeConstraints2DV1,
    ModelRef,
    ResolvedBindingV1,
    RouteCatalog,
    RouteCatalogError,
    RouteContractV1,
    RouteResolutionError,
    WorkloadPolicyV1,
    WorkloadRequestV1,
)


def _route(
    *,
    route_id: str = "gpt-image-2.5-sunburst/openai/images",
    product_id: str = "gpt-image-2.5-sunburst",
    provider: str = "openai",
    model: str = "gpt-image-2.5-sunburst",
    surface: str = "images_api",
    endpoint: str = "https://api.openai.test/v1/images/generations",
    features: frozenset[str] = frozenset({"reference_images", "transparent_background"}),
    limits: tuple[tuple[str, float], ...] = (("reference_images_max", 16.0),),
    resource_id: str = "openai-image",
    cost_low: float = 0.04,
    cost_high: float = 0.20,
    duration: float = 120.0,
    requests_per_minute: int | None = 150,
    verified_on: str = "2026-09-10",
    exact_size_constraints: ExactSizeConstraints2DV1 | None = None,
) -> RouteContractV1:
    return RouteContractV1(
        route_id=route_id,
        product_id=product_id,
        operation="image_generation",
        operation_variant="generate",
        model=ModelRef(model=model, provider=provider),
        modality_spec_version="image-generation-v1",
        surface=surface,
        endpoint=endpoint,
        adapter_id=f"gnode.providers.{provider}.image",
        adapter_behavior_version="1",
        features=features,
        limits=limits,
        exact_size_constraints=exact_size_constraints,
        resource_id=resource_id,
        estimated_duration_seconds=duration,
        estimated_cost_low_usd=cost_low,
        estimated_cost_high_usd=cost_high,
        requests_per_minute=requests_per_minute,
        rate_limit_owner=("provider_adapter" if requests_per_minute else "none"),
        verified_on=verified_on,
        evidence_ref=f"provider-contract:{provider}",
    )


def _fal_route() -> RouteContractV1:
    return _route(
        route_id="gpt-image-2.5-sunburst/fal/queue",
        provider="fal",
        model="fal-ai/gpt-image-2.5-sunburst",
        surface="queue_api",
        endpoint="https://queue.fal.test/fal-ai/gpt-image-2.5-sunburst",
        resource_id="fal-image",
        cost_low=0.03,
        cost_high=0.19,
    )


def _openrouter_route() -> RouteContractV1:
    return _route(
        route_id="gpt-image-2.5-sunburst/openrouter/chat",
        provider="openrouter",
        model="openai/gpt-image-2.5-sunburst",
        surface="chat_completions",
        endpoint="https://openrouter.test/api/v1/chat/completions",
        features=frozenset({"reference_images"}),
        resource_id="openrouter-image",
        cost_low=0.01,
        cost_high=0.10,
    )


def _request(
    *,
    policy_id: str = "hero-image",
    features: frozenset[str] = frozenset({"transparent_background"}),
    limits: tuple[tuple[str, float], ...] = (),
    exact_size: ExactSize2DV1 | None = None,
    output_options: dict[str, object] | None = None,
) -> WorkloadRequestV1:
    return WorkloadRequestV1(
        policy_id=policy_id,
        operation="image_generation",
        modality_spec_version="image-generation-v1",
        required_features=features,
        required_limits=limits,
        exact_size=exact_size,
        output_options=output_options or {"background": "transparent", "quality": "sunburst"},
    )


def _policy(
    route_id: str, *, policy_id: str = "hero-image", product_id: str = "gpt-image-2.5-sunburst"
) -> WorkloadPolicyV1:
    return WorkloadPolicyV1(
        policy_id=policy_id,
        policy_version="1",
        product_id=product_id,
        route_id=route_id,
    )


def test_policy_selects_one_exact_capable_route_after_product_filtering() -> None:
    fal = _fal_route()
    resolved = RouteCatalog([_openrouter_route(), _route(), fal]).resolve(
        _request(), _policy(fal.route_id)
    )

    assert resolved.route is fal
    assert str(resolved.route.model) == "fal-ai/gpt-image-2.5-sunburst@fal"
    assert resolved.to_binding().features == frozenset(
        {"reference_images", "transparent_background"}
    )


def test_selected_unsupported_route_refuses_without_falling_back() -> None:
    fal = _fal_route()
    openrouter = _openrouter_route()
    catalog = RouteCatalog([fal, openrouter])

    with pytest.raises(RouteResolutionError, match="missing features transparent_background"):
        catalog.resolve(_request(), _policy(openrouter.route_id))

    assert catalog.resolve(_request(), _policy(fal.route_id)).route.route_id == fal.route_id


def test_registration_order_and_cheaper_routes_cannot_choose_a_route() -> None:
    selected = _route(cost_low=9.0, cost_high=10.0)
    cheaper = _fal_route()
    request = _request()
    policy = _policy(selected.route_id)

    forward = RouteCatalog([selected, cheaper]).resolve(request, policy)
    reverse = RouteCatalog([cheaper, selected]).resolve(request, policy)

    assert forward.route.route_id == selected.route_id
    assert reverse.route.route_id == selected.route_id
    assert forward.output_fingerprint == reverse.output_fingerprint


def test_adding_an_unused_route_has_no_effect_on_resolution() -> None:
    selected = _route()
    request = _request()
    policy = _policy(selected.route_id)

    alone = RouteCatalog([selected]).resolve(request, policy)
    with_unused = RouteCatalog([selected, _fal_route()]).resolve(request, policy)

    assert alone == with_unused


@pytest.mark.parametrize(
    ("policy", "pattern"),
    [
        (_policy("gpt-image-2.5-sunburst/fal/missing"), "unregistered route"),
        (
            _policy(
                "gpt-image-2.5-sunburst/openai/images",
                product_id="another-image-product",
            ),
            "no route declares product another-image-product",
        ),
    ],
)
def test_missing_route_or_product_refuses_deterministically(
    policy: WorkloadPolicyV1, pattern: str
) -> None:
    with pytest.raises(RouteResolutionError, match=pattern):
        RouteCatalog([_route()]).resolve(_request(), policy)


def test_wrong_operation_or_modality_spec_refuses_the_selected_route() -> None:
    route = _route()
    catalog = RouteCatalog([route])
    policy = _policy(route.route_id)

    wrong_operation = replace(_request(), operation="image_edit")
    with pytest.raises(RouteResolutionError, match="no route declares product"):
        catalog.resolve(wrong_operation, policy)

    wrong_spec = replace(_request(), modality_spec_version="image-generation-v2")
    with pytest.raises(RouteResolutionError, match="image-generation-v2"):
        catalog.resolve(wrong_spec, policy)


def test_policy_identity_must_match_the_workload() -> None:
    with pytest.raises(RouteResolutionError, match="workload policy mismatch"):
        RouteCatalog([_route()]).resolve(
            _request(policy_id="hero-image"),
            _policy(_route().route_id, policy_id="background-image"),
        )


@pytest.mark.parametrize(
    ("route", "workload", "policy", "pattern"),
    [
        (
            _route(),
            _request(policy_id="other-policy"),
            _policy(_route().route_id),
            "workload policy mismatch",
        ),
        (
            _route(),
            _request(),
            _policy("gpt-image-2.5-sunburst/fal/queue"),
            "not supplied route",
        ),
        (
            _route(),
            _request(),
            _policy(_route().route_id, product_id="other-product"),
            "not policy product",
        ),
        (
            _route(),
            replace(_request(), operation="image_edit"),
            _policy(_route().route_id),
            "not workload operation",
        ),
        (
            _route(),
            replace(_request(), modality_spec_version="image-generation-v2"),
            _policy(_route().route_id),
            "not workload modality spec",
        ),
    ],
)
def test_resolved_binding_constructor_refuses_identity_contradictions(
    route: RouteContractV1,
    workload: WorkloadRequestV1,
    policy: WorkloadPolicyV1,
    pattern: str,
) -> None:
    with pytest.raises(RouteResolutionError, match=pattern):
        ResolvedBindingV1(route=route, request=workload, policy=policy)


@pytest.mark.parametrize(
    ("workload", "pattern"),
    [
        (_request(features=frozenset({"masked_edit"})), "missing features masked_edit"),
        (
            _request(limits=(("reference_images_max", 17.0),)),
            "below requested 17",
        ),
        (
            _request(limits=(("output_pixels_max", 1.0),)),
            "declares no output_pixels_max",
        ),
        (
            _request(exact_size=ExactSize2DV1(width=1024, height=1024)),
            "declares no exact_size_constraints",
        ),
    ],
)
def test_resolved_binding_constructor_refuses_unadmitted_capabilities(
    workload: WorkloadRequestV1,
    pattern: str,
) -> None:
    route = _route()

    with pytest.raises(RouteResolutionError, match=pattern):
        ResolvedBindingV1(route=route, request=workload, policy=_policy(route.route_id))


def test_required_limits_fail_closed_and_enforce_the_route_ceiling() -> None:
    route = _route()
    catalog = RouteCatalog([route])
    policy = _policy(route.route_id)

    catalog.resolve(_request(limits=(("reference_images_max", 16.0),)), policy)
    with pytest.raises(RouteResolutionError, match="below requested 17"):
        catalog.resolve(_request(limits=(("reference_images_max", 17.0),)), policy)
    with pytest.raises(RouteResolutionError, match="declares no output_pixels_max"):
        catalog.resolve(_request(limits=(("output_pixels_max", 1.0),)), policy)


def test_exact_size_constraints_admit_valid_extent_and_report_every_failure() -> None:
    constraints = ExactSizeConstraints2DV1(
        width_multiple=16,
        height_multiple=16,
        min_area=655_360,
        max_area=8_294_400,
        max_edge=3_840,
        max_aspect_ratio=3.0,
    )
    route = _route(exact_size_constraints=constraints)
    catalog = RouteCatalog([route])
    policy = _policy(route.route_id)

    catalog.resolve(_request(exact_size=ExactSize2DV1(width=1280, height=720)), policy)

    cases = (
        (ExactSize2DV1(width=641, height=1024), "width 641 is not a multiple of 16"),
        (ExactSize2DV1(width=1024, height=1025), "height 1025 is not a multiple of 16"),
        (ExactSize2DV1(width=640, height=368), "area 235520 is below minimum 655360"),
        (ExactSize2DV1(width=3840, height=2304), "area 8847360 exceeds maximum 8294400"),
        (ExactSize2DV1(width=3856, height=2048), "longest edge 3856 exceeds maximum 3840"),
        (ExactSize2DV1(width=3088, height=1024), "aspect ratio 3.01562:1 exceeds maximum 3:1"),
    )
    for size, failure in cases:
        with pytest.raises(RouteResolutionError, match=failure):
            catalog.resolve(_request(exact_size=size), policy)


@pytest.mark.parametrize(
    "size",
    [
        ExactSize2DV1(width=1280, height=512),
        ExactSize2DV1(width=512, height=1280),
        ExactSize2DV1(width=3840, height=2160),
        ExactSize2DV1(width=2160, height=3840),
        ExactSize2DV1(width=3072, height=1024),
        ExactSize2DV1(width=1024, height=3072),
    ],
)
def test_exact_size_constraint_boundaries_are_inclusive_and_orientation_neutral(
    size: ExactSize2DV1,
) -> None:
    constraints = ExactSizeConstraints2DV1(
        width_multiple=16,
        height_multiple=16,
        min_area=655_360,
        max_area=8_294_400,
        max_edge=3_840,
        max_aspect_ratio=3.0,
    )
    route = _route(exact_size_constraints=constraints)

    RouteCatalog([route]).resolve(
        _request(exact_size=size),
        _policy(route.route_id),
    )


def test_exact_size_admission_fails_closed_and_supports_an_explicit_allowlist() -> None:
    unrestricted = _route()
    with pytest.raises(RouteResolutionError, match="declares no exact_size_constraints"):
        RouteCatalog([unrestricted]).resolve(
            _request(exact_size=ExactSize2DV1(width=1024, height=1024)),
            _policy(unrestricted.route_id),
        )

    only_square = ExactSizeConstraints2DV1(allowed_sizes=(ExactSize2DV1(width=1024, height=1024),))
    route = _route(exact_size_constraints=only_square)
    catalog = RouteCatalog([route])
    policy = _policy(route.route_id)
    catalog.resolve(_request(exact_size=ExactSize2DV1(width=1024, height=1024)), policy)
    with pytest.raises(RouteResolutionError, match="1536x1024 is not an allowed exact size"):
        catalog.resolve(
            _request(exact_size=ExactSize2DV1(width=1536, height=1024)),
            policy,
        )


def test_size_constraints_change_contract_identity_but_not_output_identity() -> None:
    base_constraints = ExactSizeConstraints2DV1(max_edge=3_840)
    changed_constraints = ExactSizeConstraints2DV1(max_edge=4_096)
    base = _route(exact_size_constraints=base_constraints)
    changed = replace(base, exact_size_constraints=changed_constraints)
    request = _request(
        exact_size=ExactSize2DV1(width=1024, height=1024),
        output_options={"size": "1024x1024"},
    )
    policy = _policy(base.route_id)

    base_resolved = RouteCatalog([base]).resolve(request, policy)
    changed_resolved = RouteCatalog([changed]).resolve(request, policy)
    assert changed.behavior_fingerprint == base.behavior_fingerprint
    assert changed.contract_fingerprint != base.contract_fingerprint
    assert changed_resolved.output_fingerprint == base_resolved.output_fingerprint


def test_duplicate_catalog_identities_are_refused_independent_of_order() -> None:
    route = _route()
    duplicate_id = replace(route, endpoint="https://api.openai.test/v1/responses")
    with pytest.raises(RouteCatalogError, match="route ids more than once"):
        RouteCatalog([duplicate_id, route])

    alias = replace(route, route_id="gpt-image-2.5-sunburst/openai/images-alias")
    with pytest.raises(RouteCatalogError, match="one material route multiple ids"):
        RouteCatalog([alias, route])


@pytest.mark.parametrize(
    "changed",
    [
        replace(_route(), endpoint="https://api.openai.test/v1/responses"),
        replace(_route(), surface="responses_api"),
        replace(_route(), adapter_behavior_version="2"),
        replace(_route(), operation_variant="edit"),
        replace(_route(), model=ModelRef(model="gpt-image-2.5-flare", provider="openai")),
    ],
)
def test_material_behavior_changes_always_change_output_identity(
    changed: RouteContractV1,
) -> None:
    base = _route()

    assert changed.behavior_fingerprint != base.behavior_fingerprint
    assert (
        RouteCatalog([changed]).resolve(_request(), _policy(changed.route_id)).output_fingerprint
        != RouteCatalog([base]).resolve(_request(), _policy(base.route_id)).output_fingerprint
    )


def test_output_options_are_canonical_and_output_affecting() -> None:
    route = _route()
    catalog = RouteCatalog([route])
    policy = _policy(route.route_id)
    first = _request(
        output_options={
            "quality": "sunburst",
            "background": "transparent",
            "dimensions": {"width": 1024, "height": 1024},
        }
    )
    reordered = _request(
        output_options={
            "dimensions": {"height": 1024, "width": 1024},
            "background": "transparent",
            "quality": "sunburst",
        }
    )
    opaque = _request(
        features=frozenset(),
        output_options={"background": "opaque", "quality": "sunburst"},
    )

    assert (
        catalog.resolve(first, policy).output_fingerprint
        == catalog.resolve(reordered, policy).output_fingerprint
    )
    assert (
        catalog.resolve(first, policy).output_fingerprint
        != catalog.resolve(opaque, policy).output_fingerprint
    )


def test_operational_metadata_never_changes_behavior_or_output_fingerprints() -> None:
    base = _route()
    operational_change = replace(
        base,
        resource_id="alternate-openai-image",
        estimated_duration_seconds=999.0,
        estimated_cost_low_usd=8.0,
        estimated_cost_high_usd=9.0,
        requests_per_minute=2,
        verified_on="2030-01-01",
        evidence_ref="newer-provider-contract",
    )
    request = _request()
    policy = _policy(base.route_id)

    assert operational_change.behavior_fingerprint == base.behavior_fingerprint
    assert operational_change.contract_fingerprint == base.contract_fingerprint
    assert (
        RouteCatalog([operational_change]).resolve(request, policy).output_fingerprint
        == RouteCatalog([base]).resolve(request, policy).output_fingerprint
    )


def test_route_alias_and_policy_revision_do_not_redefine_material_output() -> None:
    base = _route()
    alias = replace(base, route_id="gpt-image-2.5-sunburst/openai/images-v2-name")
    request = _request()

    assert base.behavior_fingerprint == alias.behavior_fingerprint
    assert (
        RouteCatalog([base]).resolve(request, _policy(base.route_id)).output_fingerprint
        == RouteCatalog([alias])
        .resolve(
            request,
            replace(_policy(alias.route_id), policy_version="27"),
        )
        .output_fingerprint
    )


def test_routes_reject_secret_bearing_endpoints_and_noncanonical_options() -> None:
    with pytest.raises(ValueError, match="query or fragment"):
        _route(endpoint="https://api.openai.test/v1/images?api_key=secret")
    for endpoint in ("file:///private/provider", "/relative/provider", "ftp://provider.test"):
        with pytest.raises(ValueError, match=r"non-secret HTTP\(S\) endpoint"):
            _route(endpoint=endpoint)
    with pytest.raises(ValueError, match=r"non-secret HTTP\(S\) endpoint"):
        _route(endpoint="https://:443/images")
    for endpoint in (
        "https://api.openai.test:bad/images",
        "https://api.openai.test:99999/images",
    ):
        with pytest.raises(ValueError, match="valid network port"):
            _route(endpoint=endpoint)
    with pytest.raises(ValueError, match="finite JSON numbers"):
        _request(output_options={"guidance": float("nan")})
    with pytest.raises(ValueError, match="lower_snake_case"):
        _request(output_options={"outputFormat": "png"})
