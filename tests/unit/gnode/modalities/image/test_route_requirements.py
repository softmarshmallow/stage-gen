from __future__ import annotations

from dataclasses import replace

import pytest

from gnode import (
    ImageGenerationRequest,
    ImageReference,
    ImageRouteRequirementsV1,
    ModelRef,
    ResolvedBindingV1,
    RouteCatalog,
    RouteContractV1,
    WorkloadPolicyV1,
    WorkloadRequestV1,
    apply_resolved_image_binding,
)


def _resolved(*, options: dict[str, object] | None = None) -> ResolvedBindingV1:
    route = RouteContractV1(
        route_id="image.sunburst.openai.images.edit",
        product_id="gpt-image-2.5-sunburst",
        operation="image_generation",
        operation_variant="edit",
        model=ModelRef("gpt-image-2.5-sunburst", "openai"),
        modality_spec_version="image-generation-v1",
        surface="openai-images",
        endpoint="https://api.openai.test/v1/images/edits",
        adapter_id="gnode-openai-image-v1",
        adapter_behavior_version="1",
        features=frozenset(
            {
                "authored_prompt_passthrough",
                "exact_size",
                "maximum_quality",
                "masked_edit",
                "png_output",
                "reference_images",
                "data_url_reference_input",
                "transparent_background",
            }
        ),
        limits=(("reference_count_max", 16.0),),
        resource_id="openai-image",
        estimated_duration_seconds=120,
        estimated_cost_low_usd=0.18,
        estimated_cost_high_usd=0.25,
    )
    request = WorkloadRequestV1(
        policy_id="image.transparent.edit",
        operation="image_generation",
        modality_spec_version="image-generation-v1",
        required_features=route.features,
        required_limits=(("reference_count_max", 1.0),),
        output_options=options
        or {
            "operation_variant": "edit",
            "quality_goal": "maximum_verified",
            "quality": "max",
            "background": "transparent",
            "output_format": "png",
            "size": "1536x1024",
            "reference_count": 1,
            "reference_delivery": "data_url",
            "mask_present": True,
            "moderation_goal": "low_when_supported",
            "moderation": "low",
            "prompt_policy": "authored_verbatim",
        },
    )
    policy = WorkloadPolicyV1(
        policy_id=request.policy_id,
        policy_version="1",
        product_id=route.product_id,
        route_id=route.route_id,
    )
    return RouteCatalog((route,)).resolve(request, policy)


def test_requirements_derive_instance_capabilities_from_exact_intent() -> None:
    exact = ImageRouteRequirementsV1(
        operation_variant="edit",
        background="transparent",
        output_format="png",
        size="1536x1024",
        reference_count=2,
        mask_present=True,
    )
    flexible = ImageRouteRequirementsV1(
        operation_variant="generation",
        background="opaque",
        output_format="jpeg",
        aspect_ratio="16:9",
        resolution="2K",
    )

    assert {
        "reference_images",
        "masked_edit",
        "transparent_background",
        "png_output",
        "exact_size",
        "maximum_quality",
        "authored_prompt_passthrough",
    } <= exact.required_features
    assert "text_to_image" in flexible.required_features
    assert "flexible_size" in flexible.required_features
    assert "resolution_ladder" in flexible.required_features
    assert "exact_size" not in flexible.required_features


def test_requirements_refuse_mismatched_exact_size_and_aspect_ratio() -> None:
    with pytest.raises(ValueError, match="exact image size does not match aspect_ratio"):
        ImageRouteRequirementsV1(
            operation_variant="generation",
            background="opaque",
            output_format="png",
            size="1536x1024",
            aspect_ratio="16:9",
        )


def test_requirements_accept_equivalent_exact_size_and_aspect_ratio() -> None:
    requirements = ImageRouteRequirementsV1(
        operation_variant="generation",
        background="opaque",
        output_format="png",
        size="1536x1024",
        aspect_ratio="3:2",
    )

    assert requirements.size == "1536x1024"
    assert requirements.aspect_ratio == "3:2"


def test_requirements_leave_product_aspect_envelopes_to_the_route_catalog() -> None:
    requirements = ImageRouteRequirementsV1(
        operation_variant="generation",
        background="opaque",
        output_format="png",
        aspect_ratio="100:1",
    )

    assert requirements.aspect_ratio == "100:1"


def test_request_refuses_compression_for_a_noncompressible_output() -> None:
    with pytest.raises(ValueError, match="requires explicit jpeg or webp"):
        ImageGenerationRequest(
            prompt="Opaque atlas.",
            artifact_path="unused.png",
            output_format="png",
            output_compression=80,
        )


def test_requirements_refuse_resolution_with_exact_size_but_allow_auto_size() -> None:
    with pytest.raises(ValueError, match="resolution cannot be combined with an exact size"):
        ImageRouteRequirementsV1(
            operation_variant="generation",
            background="opaque",
            output_format="png",
            size="2048x1152",
            aspect_ratio="16:9",
            resolution="2K",
        )

    flexible = ImageRouteRequirementsV1(
        operation_variant="generation",
        background="opaque",
        output_format="png",
        size="auto",
        aspect_ratio="16:9",
        resolution="2K",
    )
    assert "flexible_size" in flexible.required_features
    assert "resolution_ladder" in flexible.required_features


def test_request_derivation_distinguishes_generation_edit_and_mask() -> None:
    reference = ImageReference("data:image/png;base64,AA==")
    request = ImageGenerationRequest(
        prompt="Preserve the subject.",
        artifact_path="unused.png",
        input_references=(reference,),
        mask_reference=reference,
        quality="max",
        background="transparent",
        output_format="png",
        size="1536x1024",
        moderation="low",
    )

    requirements = ImageRouteRequirementsV1.from_request(request)

    assert requirements.operation_variant == "edit"
    assert requirements.reference_count == 1
    assert requirements.mask_present is True
    assert requirements.reference_delivery == "data_url"
    assert "data_url_reference_input" in requirements.required_features
    assert requirements.quality_goal == "maximum_verified"
    assert requirements.moderation_goal == "low_when_supported"


def test_request_derivation_classifies_hosted_and_mixed_reference_delivery() -> None:
    hosted = ImageRouteRequirementsV1.from_request(
        ImageGenerationRequest(
            prompt="Use the hosted reference.",
            artifact_path="unused.png",
            input_references=(ImageReference("https://assets.example/reference.png"),),
            quality="max",
        )
    )
    mixed = ImageRouteRequirementsV1.from_request(
        ImageGenerationRequest(
            prompt="Use both references.",
            artifact_path="unused.png",
            input_references=(ImageReference("https://assets.example/reference.png"),),
            mask_reference=ImageReference("data:image/png;base64,AA=="),
            quality="max",
        )
    )

    assert hosted.reference_delivery == "hosted_url"
    assert hosted.required_features >= {"hosted_url_reference_input"}
    assert mixed.reference_delivery == "mixed"
    assert mixed.required_features >= {
        "data_url_reference_input",
        "hosted_url_reference_input",
    }


def test_request_derivation_is_not_tied_to_a_host_quality_policy() -> None:
    requirements = ImageRouteRequirementsV1.from_request(
        ImageGenerationRequest(
            prompt="Draft preview.",
            artifact_path="unused.png",
            quality="low",
        )
    )

    assert requirements.quality_goal is None
    assert "quality_goal" not in requirements.semantic_options()
    assert "maximum_quality" not in requirements.required_features


def test_apply_resolved_binding_sets_only_sealed_provider_values() -> None:
    reference = ImageReference("data:image/png;base64,AA==")
    request = ImageGenerationRequest(
        prompt="Preserve the subject.",
        artifact_path="unused.png",
        input_references=(reference,),
        mask_reference=reference,
        quality="max",
        background="transparent",
        output_format="png",
        size="1536x1024",
        moderation="low",
    )
    resolved = _resolved()

    bound = apply_resolved_image_binding(request, resolved)

    assert bound.quality == "max"
    assert bound.background == "transparent"
    assert bound.output_format == "png"
    assert bound.size == "1536x1024"
    assert bound.moderation == "low"
    assert bound.resolved_binding is resolved


def test_apply_resolved_binding_refuses_semantic_or_unknown_option_drift() -> None:
    reference = ImageReference("data:image/png;base64,AA==")
    request = ImageGenerationRequest(
        prompt="Preserve the subject.",
        artifact_path="unused.png",
        input_references=(reference,),
        mask_reference=reference,
        quality="max",
        background="transparent",
        output_format="png",
        size="1536x1024",
        moderation="low",
    )

    with pytest.raises(ValueError, match="reference_count"):
        apply_resolved_image_binding(
            request,
            _resolved(options={**dict(_resolved().request.output_options), "reference_count": 2}),
        )
    with pytest.raises(ValueError, match="unknown options"):
        apply_resolved_image_binding(
            request,
            _resolved(options={**dict(_resolved().request.output_options), "surprise": True}),
        )
    with pytest.raises(ValueError, match=r"operation[_ ]variant"):
        apply_resolved_image_binding(
            replace(request, input_references=(), mask_reference=None),
            _resolved(),
        )
