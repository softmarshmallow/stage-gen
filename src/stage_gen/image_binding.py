"""Apply application-owned image output policy to an exact planned route."""

from gnode import ImageGenerationRequest, ResolvedBindingV1, apply_resolved_image_binding


def apply_stage_gen_image_binding(
    request: ImageGenerationRequest,
    binding: ResolvedBindingV1,
) -> ImageGenerationRequest:
    """Validate Stage Gen's quality policy, then invoke the model-neutral binder."""

    options = binding.request.output_options
    if options.get("quality_goal") != "maximum_verified" or options.get("quality") != "max":
        raise ValueError("Stage Gen image routes require maximum_verified quality mapped to max")
    if options.get("operation_variant") == "edit":
        if options.get("input_fidelity") != "omitted":
            raise ValueError("Stage Gen Sunburst edits must omit input_fidelity")
    elif "input_fidelity" in options:
        raise ValueError("Stage Gen generation routes cannot declare input_fidelity")
    return apply_resolved_image_binding(
        request,
        binding,
        allowed_extension_options=frozenset({"input_fidelity"}),
    )
