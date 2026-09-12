"""Application-owned operation bindings, reviewed before qualification."""

from gnode import Binding, BindingTable, ModelRef
from stage_gen.image_product import QUALITY_IMAGE_PRODUCT


def default_bindings() -> BindingTable:
    return BindingTable(
        [
            Binding(
                operation="reference_image",
                model=ModelRef(QUALITY_IMAGE_PRODUCT.openrouter_model, "openrouter"),
                resource_id="upstream-images",
                estimated_duration_seconds=180,
                estimated_cost_low_usd=0,
                estimated_cost_high_usd=3,
                features=frozenset({"text_input", "reference_images", "opaque_image"}),
                limits=(("reference_count", 16),),
                verified_on="2026-09-11",
            ),
            Binding(
                operation="part_mesh",
                model=ModelRef.parse("P2-20260801@tripo"),
                resource_id="upstream-meshes",
                estimated_duration_seconds=600,
                estimated_cost_low_usd=1.2,
                estimated_cost_high_usd=2.5,
                features=frozenset(
                    {"multiview", "textured_mesh", "quad_request", "native_fbx_or_glb"}
                ),
                limits=(("reference_count", 4), ("quad_face_limit", 25000)),
                verified_on="2026-09-11",
            ),
            Binding(
                operation="body_rig",
                model=ModelRef.parse("v1.0-20240301@tripo"),
                resource_id="provider-rig",
                estimated_duration_seconds=180,
                estimated_cost_low_usd=0.25,
                estimated_cost_high_usd=0.25,
                features=frozenset(
                    {
                        "biped",
                        "rig_check",
                        "generation_task_input",
                        "local_glb_input",
                        "native_fbx_or_glb",
                    }
                ),
                limits=(("input_bytes", 150_000_000),),
                verified_on="2026-09-11",
            ),
            Binding(
                operation="tool_loop",
                model=ModelRef.parse("openai/gpt-6-astra@openrouter"),
                resource_id="agent",
                estimated_duration_seconds=300,
                estimated_cost_low_usd=0,
                estimated_cost_high_usd=12,
                features=frozenset({"tool_use", "image_input"}),
                max_in_flight=1,
                verified_on="2026-09-11",
            ),
        ]
    )
