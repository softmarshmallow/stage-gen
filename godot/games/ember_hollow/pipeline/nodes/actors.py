"""An actor's two rebase passes (the shared steps) and the record this game publishes.

Every strip is a separate draw, so nothing ties their scales together; the shared steps
read each strip's multiplier off one plate and verify the residual. The record is laid
out as this game's manifest reads it: one entry per strip, plus the evidence.
"""

from __future__ import annotations

from typing import Any, cast

from demo_game_tools.steps.rebase import (
    rebase_admit,
    rebase_plate,
    rebase_record,
    rebase_schema,
    rebase_verify_admit,
    rebase_verify_plate,
    rebase_verify_record,
)
from gnode import Ctx, node


@node(
    "publish_rebase",
    inputs={"record": "json"},
    params={"actor_id": str, "baseline_state": str},
    outputs={"rebase": "json"},
    version=1,
)
def publish_rebase(ctx: Ctx) -> dict[str, Any]:
    """Each strip's final multiplier, as a list the manifest reads, beside the evidence."""

    record = cast(dict[str, Any], ctx.read.json("record"))
    states = cast(dict[str, float], record.get("states") or {})
    return {
        "rebase": ctx.out.json(
            {
                "schema_version": 1,
                "kind": "oblique-survival-rebase-v1",
                "actor_id": ctx.params["actor_id"],
                "baseline_state": record.get("baseline_state", ctx.params["baseline_state"]),
                "states": [
                    {"state": state, "multiplier": multiplier}
                    for state, multiplier in sorted(states.items())
                ],
                "record": record,
            }
        )
    }


__all__ = [
    "publish_rebase",
    "rebase_admit",
    "rebase_plate",
    "rebase_record",
    "rebase_schema",
    "rebase_verify_admit",
    "rebase_verify_plate",
    "rebase_verify_record",
]
