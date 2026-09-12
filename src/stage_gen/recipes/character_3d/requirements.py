"""Offline validation of recipe-owned review and part requirements."""

from __future__ import annotations

import math
from datetime import date
from typing import Any
from urllib.parse import urlsplit

from gnode import ModelRef
from stage_gen.components.character_3d.agent_backend import ModelPricing
from stage_gen.components.character_3d.studio import VIEWS
from stage_gen.recipes.character_3d.profiles import (
    anthro_cat,
    articulation,
    diagnostic_samples,
    fixed_human,
    humanoid,
)

DEFAULT_REVIEW_VIEWS = ("front", "back", "left", "right", "three_quarter")
MAX_REVIEW_IMAGES = 60
AGENT_FEATURES = ("tool_use", "image_input")
AGENT_PARAMETERS = frozenset({"tools", "tool_choice", "max_tokens", "structured_outputs"})


def validate_agent_metadata(
    route: str, pricing_record: dict[str, Any], limits: dict[str, Any] | None = None
) -> tuple[str, ...]:
    """Validate the retained catalog record, without network or capability inference.

    The current backend sends strict function tools, required tool_choice and
    max_tokens, with text/image messages. It does not send response_format,
    temperature or a reasoning override. The caller verifies this record's file
    hash; passing metadata does not establish live endpoint availability.
    """
    parsed_route = ModelRef.parse(route)
    if parsed_route.provider != "openrouter":
        raise ValueError("This agent runtime requires an OpenRouter route")
    if not isinstance(pricing_record, dict):
        raise ValueError("Retained agent metadata must be an object")
    model = pricing_record.get("model")
    if not isinstance(model, dict) or model.get("id") != parsed_route.model:
        raise ValueError("Agent route differs from the retained metadata model ID")
    source = pricing_record.get("source_url")
    if not isinstance(source, str):
        raise ValueError("Retained agent metadata needs its public source URL")
    parsed = urlsplit(source)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "openrouter.ai"
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Retained agent metadata source must be public OpenRouter HTTPS")
    checked_at = pricing_record.get("checked_at")
    try:
        valid_date = (
            isinstance(checked_at, str) and date.fromisoformat(checked_at).isoformat() == checked_at
        )
    except ValueError:
        valid_date = False
    if not valid_date or not isinstance(checked_at, str):
        raise ValueError("Retained agent metadata needs its ISO checked_at date")
    architecture = model.get("architecture")
    if not isinstance(architecture, dict):
        raise ValueError("Retained agent metadata lacks modality support")
    inputs = set(names(architecture.get("input_modalities"), "Agent input modalities"))
    outputs = set(names(architecture.get("output_modalities"), "Agent output modalities"))
    if not {"text", "image"} <= inputs or "text" not in outputs:
        raise ValueError("Agent metadata must declare text/image input and text output")
    supported = set(names(model.get("supported_parameters"), "Agent supported parameters"))
    if missing := (AGENT_PARAMETERS - supported):
        raise ValueError("Agent metadata lacks required parameters: " + ", ".join(sorted(missing)))
    try:
        pricing = ModelPricing(snapshot=model, checked_at=checked_at, source_url=source)
    except (TypeError, ValueError):
        raise ValueError(
            "Retained agent pricing is malformed or has an unsupported source"
        ) from None
    reserve = (limits or {}).get("agent_input_token_reserve", 65536)
    if type(reserve) is not int or not 1 <= reserve <= 1000000:
        raise ValueError("Agent input token reservation must be a bounded positive integer")
    if pricing.context_length < reserve + 8192:
        raise ValueError("Agent metadata context cannot cover the configured token reservation")
    provider_metadata = model.get("top_provider")
    if provider_metadata is not None and (not isinstance(provider_metadata, dict)):
        raise ValueError("Agent metadata top_provider must be an object when supplied")
    maximum = (provider_metadata or {}).get("max_completion_tokens")
    if maximum is not None and (type(maximum) is not int or maximum < 8192):
        raise ValueError("Agent metadata completion limit is below the configured output bound")
    return AGENT_FEATURES


def _compiled_motion_inventory(profile: dict[str, Any]) -> dict[str, Any]:
    """Ask the existing compiler for its authored clip set before any rig build."""
    compiler = articulation(profile)
    if compiler in (humanoid, fixed_human):
        return {"clips": compiler.motion_clips()}
    if compiler is anthro_cat:
        neutral_tail = {
            name: {"head": [0, 0, 0], "tail": [0, 0, 1]} for name in compiler.TAIL_BONES
        }
        articulation_settings = profile.get("articulation", {})
        if not isinstance(articulation_settings, dict) or "tail_wag" not in articulation_settings:
            raise ValueError("Cat profile must explicitly configure tail_wag")
        return {
            "clips": compiler.motion_clips(neutral_tail, tail_wag=articulation_settings["tail_wag"])
        }
    raise ValueError("Registered profile lacks an offline motion inventory adapter")


def _validate_evidence_limit(review: dict[str, Any], pose_count: int) -> None:
    count = len(review.get("required_views", DEFAULT_REVIEW_VIEWS)) * (
        pose_count + len(review.get("target_character_height_pixels", []))
    )
    if count > MAX_REVIEW_IMAGES:
        raise ValueError(
            "Mandatory evidence exceeds the bounded review image allowance before dispatch"
        )


def names(value: object, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
        or (len(set(value)) != len(value))
    ):
        raise ValueError(f"{label} must be a nonempty list of unique names")
    return value


def validate_requirements(profile: dict[str, Any], experiment: dict[str, Any]) -> None:
    if (
        experiment.get("rigging", {}).get("strategy") == "provider"
        and profile.get("profile_id") != "sd_human_fixed_hands_v1"
    ):
        raise ValueError("Provider rigging v1 supports only the fixed-hand SD human profile")
    if profile.get("profile_id") == "sd_human_fixed_hands_v1":
        target_height = profile.get("target_height")
        if (
            isinstance(target_height, bool)
            or not isinstance(target_height, int | float)
            or (not math.isfinite(target_height))
            or (target_height <= 0)
        ):
            raise ValueError("Fixed-hand profile target_height must be finite and positive")
        required_controls = names(
            profile.get("required_joint_semantics"), "Required joint semantics"
        )
        if set(required_controls) != set(fixed_human.PARENTS):
            raise ValueError("Fixed-hand profile control inventory differs from its version")
        if (
            experiment.get("pipeline_mode") != "rig_review_calibration"
            and experiment.get("rigging", {}).get("strategy") != "provider"
        ):
            raise ValueError("Fixed-hand v1 requires the configured provider rig strategy")
    review = profile.get("review", {})
    if not isinstance(review, dict):
        raise ValueError("Profile review must be an object")
    for key in ("assembly_criteria", "rig_criteria", "required_views", "required_diagnostics"):
        if key in review:
            names(review[key], key)
    if set(review.get("required_views", [])) - VIEWS.keys():
        raise ValueError("Profile requests an unsupported review view")
    sizes = review.get("target_character_height_pixels", [])
    if "target_character_height_pixels" in review and (not isinstance(sizes, list) or not sizes):
        raise ValueError("Gameplay review sizes must be a nonempty unique list")
    for size in [*sizes, review.get("inspection_height_pixels", 512)]:
        if type(size) is not int or not 64 <= size <= 1024:
            raise ValueError("Review character height must be an integer from 64 through 1024")
    if len(set(sizes)) != len(sizes):
        raise ValueError("Gameplay review sizes must be a nonempty unique list")
    if "required_parts" in profile:
        required = set(names(profile["required_parts"], "required_parts"))
        if experiment.get("pipeline_mode") in {"brief_to_rig", "rig_review_calibration"}:
            roles = required
        elif experiment.get("pipeline_mode") == "rig":
            roles = set(experiment["assembly_input"]["part_roles"].values())
        else:
            roles = {part["role"] for part in experiment["parts"]}
        if not required <= roles:
            raise ValueError(
                "Inputs are missing required part roles: " + ", ".join(sorted(required - roles))
            )
    _validate_evidence_limit(review, 1)
    if experiment.get("pipeline_mode", "assembly") == "assembly":
        return
    names(review.get("required_diagnostics"), "required_diagnostics")
    motion = review.get("required_motion")
    if not isinstance(motion, str) or not motion.strip():
        raise ValueError("Rig review needs one required_motion clip")
    optional = review.get("optional_diagnostics", [])
    if not isinstance(optional, list):
        raise ValueError("optional_diagnostics must be a list")
    if optional:
        names(optional, "optional_diagnostics")
    plan = _compiled_motion_inventory(profile)
    if motion not in {clip["name"] for clip in plan["clips"]}:
        raise ValueError("Profile requires an unimplemented motion clip: " + motion)
    poses = diagnostic_samples(profile, plan)
    _validate_evidence_limit(review, len(poses))
