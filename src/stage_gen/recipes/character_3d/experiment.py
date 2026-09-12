"""Offline admission for explicitly authored run configuration."""

from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation
from typing import Any

EPISODE_LIMIT_MAXIMA = {
    "agent_episode_max_steps": 32,
    "agent_review_max_steps": 32,
    "agent_episode_max_total_tokens": 4000000,
    "agent_review_max_total_tokens": 4000000,
}


def episode_limits(
    limits: dict[str, Any], *, read_only: bool = False, rig: bool = False
) -> dict[str, int]:
    """Resolve finite per-episode caps; omitted fields retain historical defaults.

    Total tokens count repeated context in successful model turns, as enforced
    by ToolLoopService. They are separate from shared paid-dispatch/USD limits.
    """
    prefix = "agent_review" if read_only else "agent_episode"
    return {
        "max_steps": limits.get(prefix + "_max_steps", 6 if read_only else 16),
        "max_total_tokens": limits.get(prefix + "_max_total_tokens", 750000 if rig else 450000),
    }


def validate_experiment(value: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "experiment_id",
        "profile",
        "pricing",
        "agent_route",
        "parts",
        "limits",
    }
    optional = {
        "claim",
        "scope",
        "pipeline_mode",
        "reference",
        "assembly_input",
        "budget_context",
        "budget_account",
        "brief",
        "upstream",
        "review_input",
        "rigging",
        "partition_preset",
        "review_quality_bar",
    }
    if (
        not isinstance(value, dict)
        or not required <= value.keys()
        or value.keys() - required - optional
    ):
        raise ValueError("Invalid experiment fields")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("Unsupported experiment schema")
    mode = value.get("pipeline_mode", "assembly")
    if mode not in {"assembly", "rig", "parts_to_rig", "brief_to_rig", "rig_review_calibration"}:
        raise ValueError("Unknown pipeline mode")
    if "review_quality_bar" in value:
        from stage_gen.recipes.character_3d.quality_bar import quality_bar_level

        quality_bar_level(value)
    if "rigging" in value:
        rigging = value["rigging"]
        if mode not in {"rig", "parts_to_rig", "brief_to_rig"} or not isinstance(rigging, dict):
            raise ValueError("Provider rigging requires a character rig lane")
        if (
            set(rigging)
            != {"strategy", "route", "reservation_usd", "poll_interval_seconds", "preservation"}
            or rigging["strategy"] != "provider"
        ):
            raise ValueError("Invalid provider rigging configuration")
        from gnode import ModelRef

        route = ModelRef.parse(rigging["route"])
        if route.provider != "tripo":
            raise ValueError("The v1 provider-rig adapter supports only the declared Tripo route")
        try:
            reservation = Decimal(str(rigging["reservation_usd"]))
        except InvalidOperation:
            raise ValueError("Invalid provider rig reservation") from None
        if (
            type(rigging["reservation_usd"]) not in {str, int, float}
            or not reservation.is_finite()
            or (not 0 < reservation <= 10)
        ):
            raise ValueError("Provider rig reservation must be positive and at most 10")
        interval = rigging["poll_interval_seconds"]
        if (
            type(interval) not in {int, float}
            or not math.isfinite(interval)
            or (not 1 <= interval <= 30)
        ):
            raise ValueError("Rig polling interval must be from 1 through 30 seconds")
        if rigging["preservation"] not in {"audit", "restore_normals"}:
            raise ValueError("Unsupported preservation policy")
    if "partition_preset" in value:
        if "rigging" not in value:
            raise ValueError("Partition presets require the provider-rig lane")
        from stage_gen.recipes.character_3d.partitions import partition_plan

        partition_plan(value["partition_preset"])
    if not isinstance(value["experiment_id"], str) or not re.fullmatch(
        "[a-z][a-z0-9_]{0,95}", value["experiment_id"]
    ):
        raise ValueError("Experiment identity must use lower_snake_case")
    limits = value["limits"]
    required_limits = {
        "max_usd",
        "max_dispatches",
        "max_wall_seconds",
        "max_worker_calls",
        "max_assembly_revisions",
        "max_review_rounds",
    }
    if (
        not isinstance(limits, dict)
        or not required_limits <= limits.keys()
        or limits.keys()
        - required_limits
        - {
            "max_rig_revisions",
            "agent_max_usd",
            "agent_input_token_reserve",
            "agent_max_text_bytes",
            "agent_recent_image_limit",
            "agent_review_holdback_usd",
        }
        - EPISODE_LIMIT_MAXIMA.keys()
    ):
        raise ValueError("Invalid run budget fields")
    try:
        amount = Decimal(str(limits["max_usd"]))
    except (InvalidOperation, ValueError):
        raise ValueError("Run USD budget must be a positive finite decimal") from None
    if (
        type(limits["max_usd"]) not in {str, int, float}
        or not amount.is_finite()
        or (not 0 < amount <= 1000)
    ):
        raise ValueError("Run USD budget must be greater than zero and at most1000")
    for key, maximum in (
        ("max_dispatches", 256),
        ("max_worker_calls", 1000),
        ("max_assembly_revisions", 32),
        ("max_rig_revisions", 32),
        ("max_review_rounds", 3),
        ("agent_input_token_reserve", 1000000),
        ("agent_max_text_bytes", 1048576),
        ("agent_recent_image_limit", 64),
        *EPISODE_LIMIT_MAXIMA.items(),
    ):
        count = limits.get(key, 6)
        if type(count) is not int or not 1 <= count <= maximum:
            raise ValueError(f"{key} must be an integer from 1 through {maximum}")
    seconds = limits["max_wall_seconds"]
    if (
        type(seconds) not in {float, int}
        or not math.isfinite(seconds)
        or (not 0 < seconds <= 14400)
    ):
        raise ValueError("Run deadline must be positive, finite and no more than 4 hours")
    parts = value["parts"]
    if (
        not isinstance(parts, list)
        or len(parts) > 16
        or (mode in {"assembly", "parts_to_rig"} and (not parts))
    ):
        raise ValueError("Assembly requires 1 through 16 explicit parts")
    names = set()
    for part in parts:
        if not isinstance(part, dict) or set(part) != {"part_id", "role", "source"}:
            raise ValueError("Each part requires part_id, role and source")
        for key in ("part_id", "role"):
            if not isinstance(part[key], str) or not re.fullmatch(
                "[a-z][a-z0-9_]{0,63}", part[key]
            ):
                raise ValueError("Part identities and roles must use lower_snake_case")
        if part["part_id"] in names:
            raise ValueError("Duplicate part identity")
        names.add(part["part_id"])
    if (mode == "rig") != ("assembly_input" in value):
        raise ValueError("Exactly rig-only runs declare assembly_input")
    if (mode == "rig_review_calibration") != ("review_input" in value):
        raise ValueError("Exactly review calibration runs declare review_input")
    if mode == "rig_review_calibration":
        source = value["review_input"]
        if (
            parts
            or "reference" in value
            or "budget_account" not in value
            or (limits["max_review_rounds"] != 1)
            or (not isinstance(source, dict))
            or (set(source) != {"path", "sha256"})
            or (not isinstance(source["path"], str))
            or (not source["path"])
            or ("\\" in source["path"])
            or ("\x00" in source["path"])
            or any(item in {"", ".", ".."} for item in source["path"].split("/"))
            or (not isinstance(source["sha256"], str))
            or (not re.fullmatch("[a-f0-9]{64}", source["sha256"]))
        ):
            raise ValueError(
                "Review calibration requires one neutral subject, one review, e"
                "mpty parts and a shared budget; no canonical reference or gene"
                "ration inputs"
            )
    if "agent_max_usd" in limits:
        try:
            agent_amount = Decimal(str(limits["agent_max_usd"]))
        except InvalidOperation:
            raise ValueError("Invalid agent budget") from None
        if not agent_amount.is_finite() or not 0 < agent_amount <= amount:
            raise ValueError("Agent budget must fit within total run budget")
    if "agent_review_holdback_usd" in limits:
        raw = limits["agent_review_holdback_usd"]
        try:
            holdback = Decimal(str(raw))
        except (InvalidOperation, ValueError):
            raise ValueError("agent_review_holdback_usd must be finite and nonnegative") from None
        ceiling = Decimal(str(limits.get("agent_max_usd", limits["max_usd"])))
        if (
            type(raw) not in {str, int, float}
            or not holdback.is_finite()
            or (not 0 <= holdback < ceiling)
        ):
            raise ValueError("agent_review_holdback_usd must be nonnegative and below agent budget")
    if "budget_account" in value:
        spec = value["budget_account"]
        if not isinstance(spec, dict) or set(spec) != {
            "root",
            "account_id",
            "ceiling_usd",
            "historical_liability_usd",
        }:
            raise ValueError("Invalid shared budget account")
        if not isinstance(spec["account_id"], str) or not re.fullmatch(
            "[a-z][a-z0-9_-]{0,95}", spec["account_id"]
        ):
            raise ValueError("Budget account must be a portable lowercase identity")
        root = spec["root"]
        if (
            not isinstance(root, str)
            or not root
            or "\\" in root
            or ("\x00" in root)
            or any(part in {"", ".", ".."} for part in root.split("/"))
        ):
            raise ValueError("Budget storage must be a portable relative path")
        for key in ("ceiling_usd", "historical_liability_usd"):
            try:
                money = Decimal(str(spec[key]))
            except InvalidOperation:
                raise ValueError("Invalid shared budget amount") from None
            if not money.is_finite() or money < 0:
                raise ValueError("Shared budget amounts must be finite and nonnegative")
        if Decimal(str(spec["historical_liability_usd"])) + amount > Decimal(
            str(spec["ceiling_usd"])
        ):
            raise ValueError("The run allocation does not fit the declared session budget")
    if mode == "brief_to_rig":
        if (
            parts
            or "brief" not in value
            or "upstream" not in value
            or ("budget_account" not in value)
        ):
            raise ValueError(
                "Brief mode requires a brief, upstream plan and budget account, without raw parts"
            )
        if not isinstance(value["brief"], dict) or set(value["brief"]) != {
            "description",
            "rights_basis",
        }:
            raise ValueError("Brief requires description and rights_basis")
        if any(not isinstance(item, str) or not item.strip() for item in value["brief"].values()):
            raise ValueError("Brief and rights basis must be nonempty text")
        required_upstream = {
            "max_reference_generations",
            "max_crops",
            "mesh_params",
            "poll_interval_seconds",
        }
        if not isinstance(value["upstream"], dict) or set(value["upstream"]) != required_upstream:
            raise ValueError("Invalid upstream configuration")
        for key, operation_ceiling in (("max_reference_generations", 16), ("max_crops", 128)):
            if (
                type(value["upstream"][key]) is not int
                or not 1 <= value["upstream"][key] <= operation_ceiling
            ):
                raise ValueError("Invalid upstream operation limit")
        if (
            type(value["upstream"]["poll_interval_seconds"]) not in {int, float}
            or not 1 <= value["upstream"]["poll_interval_seconds"] <= 30
        ):
            raise ValueError("Mesh polling interval must be from 1 through 30 seconds")
        if "agent_max_usd" not in limits:
            raise ValueError("Brief mode requires a separate agent budget slice")
    elif "brief" in value or "upstream" in value:
        raise ValueError("Only brief_to_rig declares upstream generation")
    return value
