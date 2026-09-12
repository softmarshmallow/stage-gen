"""Pinned standard Tripo API usage valuation, never an invoice or ledger migration.

Only fresh adapter receipts containing successful terminal usage can be valued.
Legacy credit counters, running tasks and missing billing retain unknown liability.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any

from gnode import BindingTable
from stage_gen.components.character_3d.io import (
    canonical_digest,
    confined,
    digest,
    read_json,
)
from stage_gen.components.character_3d.provider_contracts import (
    OperationStore,
    identifier,
    validate_plan,
    verify_result,
)

JsonObject = dict[str, Any]
PRICING_PATH = "models/tripo-api-pricing-2026-09-10.json"
PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def pricing_metadata() -> tuple[JsonObject, dict[str, str]]:
    from stage_gen.components.character_3d.package_resources import resource

    path = resource(PRICING_PATH)
    record = read_json(path)
    if (
        type(record.get("schema_version")) is not int
        or record["schema_version"] != 1
        or record.get("provider") != "tripo"
        or (record.get("checked_on") != "2026-09-10")
        or (record.get("api_root") != "https://openapi.tripo3d.ai/v3")
        or (record.get("route") != "P2-20260801@tripo")
        or (record.get("usd_per_credit") != "0.01")
        or (record.get("value_basis") != "standard_api_usage_value")
    ):
        raise ValueError("Pinned Tripo API pricing metadata differs")
    return (record, {"path": PRICING_PATH, "sha256": digest(path)})


def credits_value(value: object) -> tuple[Decimal, Decimal] | None:
    """Return exact (credits, USD) for the documented numeric credit field.

    The adapter parses JSON fractions as Decimal. Floats are accepted for injected
    transports and normalized through their decimal spelling, never multiplied as
    floats. Booleans, strings, non-finite/negative values and sub-cent credits are
    not usage. The existing adapter's billion-credit sanity bound is retained.
    """
    if type(value) not in (int, float, Decimal):
        return None
    try:
        credits = Decimal(str(value))
        if not credits.is_finite() or not 0 <= credits < Decimal("1e9"):
            return None
        with localcontext() as context:
            context.prec = max(32, len(credits.as_tuple().digits) + 4)
            if credits * 100 != (credits * 100).to_integral_value():
                return None
            return (credits, credits * Decimal("0.01"))
    except InvalidOperation:
        return None


def terminal_usage(
    plan: JsonObject,
    task_id: str,
    response: JsonObject,
    artifacts: Sequence[JsonObject],
    output_fields: Sequence[str],
) -> JsonObject | None:
    """Make a URL-free receipt from this successful query, not earlier state."""
    if response.get("task_id") != task_id:
        raise ValueError("Tripo usage task lineage differs")
    pricing, pricing_ref = pricing_metadata()
    if response.get("status") != "success" or plan["route"] != pricing["route"]:
        return None
    value = credits_value(response.get("credits_consumed"))
    if value is None:
        return None
    credits, usd = value
    return {
        "schema_version": 1,
        "provider": "tripo",
        "api_root": pricing["api_root"],
        "route": plan["route"],
        "plan_sha256": plan["plan_sha256"],
        "task_id": task_id,
        "task_status": "success",
        "credits_consumed": str(credits),
        "standard_api_usage_usd": str(usd),
        "value_basis": pricing["value_basis"],
        "pricing": pricing_ref,
        "artifacts_sha256": canonical_digest(artifacts),
        "output_fields": list(output_fields),
    }


def mesh_cost(
    store: OperationStore,
    plan: JsonObject,
    *,
    input_root: Path,
    bindings: BindingTable | None = None,
) -> Decimal | None:
    """Validate immutable plan/task/output lineage before returning known USD.

    Call with the operation lock held. Missing legacy/invalid usage returns None;
    changed lineage raises and must retain the existing reservation. This never
    writes or settles an account and cannot release a historical terminal hold.
    """
    validate_plan(plan, input_root, bindings)
    if store.read("plan.json") != plan or plan["operation"] != "part_mesh":
        raise ValueError("Tripo usage plan lineage differs")
    result = verify_result(store, plan)
    if result is None or "terminal_usage" not in result:
        return None
    usage = result["terminal_usage"]
    if not isinstance(usage, dict):
        return None
    if type(usage.get("schema_version")) is not int or usage["schema_version"] != 1:
        raise ValueError("Tripo usage schema differs")
    state = store.read("state.json") or {}
    task_id = identifier(result.get("task_id"))
    if (
        result.get("status") != "raw_parts_collected"
        or not result.get("artifacts")
        or state.get("status") != "raw_parts_collected"
        or (state.get("plan_sha256") != plan["plan_sha256"])
        or (state.get("task_id") != task_id)
        or (type(state.get("paid_submissions")) is not int)
        or (state["paid_submissions"] != 1)
        or (usage.get("task_id") != task_id)
        or (usage.get("plan_sha256") != plan["plan_sha256"])
        or (usage.get("artifacts_sha256") != canonical_digest(result["artifacts"]))
    ):
        raise ValueError("Tripo usage task or output lineage differs")
    if usage.get("task_status") != "success":
        return None
    try:
        if not isinstance(usage.get("credits_consumed"), str):
            return None
        credits = Decimal(usage["credits_consumed"])
    except InvalidOperation:
        return None
    fields = []
    for artifact in result["artifacts"]:
        metadata = read_json(confined(store.path, artifact["provenance_path"]))
        params = metadata.get("params", {})
        if (
            not isinstance(params, dict)
            or not isinstance(metadata.get("artifact"), dict)
            or metadata.get("provider") != "tripo"
            or (metadata.get("model") != plan["route"].removesuffix("@tripo"))
            or (metadata.get("prompt") != plan["prompt"])
            or (
                metadata.get("inputs")
                != [
                    {"ref": item["path"], "sha256": item["sha256"], "source": "reference"}
                    for item in plan["inputs"]
                ]
            )
            or (metadata.get("artifact", {}).get("sha256") != artifact["sha256"])
            or (params.get("plan_sha256") != plan["plan_sha256"])
            or (params.get("task_id") != task_id)
            or (params.get("request") != plan["params"])
            or (not isinstance(params.get("provider_result_field"), str))
            or (not params["provider_result_field"])
        ):
            raise ValueError("Tripo usage artifact provenance differs")
        fields.append(params["provider_result_field"])
    if len(set(fields)) != len(fields) or usage.get("output_fields") != fields:
        raise ValueError("Tripo usage output fields differ")
    expected = terminal_usage(
        plan,
        task_id,
        {"task_id": task_id, "status": "success", "credits_consumed": credits},
        result["artifacts"],
        fields,
    )
    if expected is None:
        return None
    if usage != expected:
        raise ValueError("Tripo usage valuation or pinned pricing lineage differs")
    return Decimal(expected["standard_api_usage_usd"])
