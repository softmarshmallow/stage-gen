"""Find where each delivered node actually ran, across a series of runs of one package.

A package's current run usually restores most nodes from the cache, so the time, tries and
prompt of a node live in whichever earlier run executed it. A node is taken from the newest
listed run where it ran (a cache miss that succeeded) and produced exactly the bytes the
delivering run holds; anything else is refused rather than guessed.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..record import model_name, provider_name
from ..record import node as make_node

KINDS = {"image_generation": "Image model", "structured_generation": "Language model"}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def outputs_of(n: dict) -> dict[str, str]:
    return {
        a["artifact_ref"]: a["sha256"]
        for a in n["artifacts"]
        if not a["artifact_ref"].endswith(".meta.json")
    }


class Lineage:
    def __init__(self, runs: list[Path]):
        self.summaries = [
            (d, {n["node_id"]: n for n in load(d / "execution-summary.json")["nodes"]})
            for d in runs
        ]
        self.last, self.delivered = self.summaries[-1]

    def where_it_ran(self, node_id: str) -> tuple[Path, dict, dict]:
        """(run folder, summary entry, plan entry) of the run that produced the delivered bytes."""
        want = outputs_of(self.delivered[node_id])
        for run_dir, nodes in reversed(self.summaries):
            n = nodes.get(node_id)
            if n and n["cache"] == "miss" and n["status"] == "succeeded" and outputs_of(n) == want:
                plan = next(
                    p
                    for p in load(run_dir / "execution-plan.json")["nodes"]
                    if p["node_id"] == node_id
                )
                return run_dir, n, plan
        raise ValueError(
            f"{node_id}: none of the listed runs produced the bytes {self.last.name} delivered"
        )


def record_node(
    node_id: str, run_dir: Path, n: dict, plan: dict, kinds: dict[str, str] = KINDS, **fields
) -> dict:
    """A record node from the run where it ran: its summary entry and its plan entry."""
    return make_node(
        node_id,
        type_id=plan["type_id"],
        kind=kinds.get(plan["operation"], "Local"),
        description=plan.get("description", ""),
        provider=provider_name(plan.get("provider")),
        model=model_name(plan.get("model")),
        retry_owner=plan.get("retry_owner"),
        max_attempts=plan.get("max_attempts"),
        state=n["status"],
        attempts=n.get("attempts"),
        duration_ms=n.get("duration_ms"),
        cost_usd=n.get("known_cost_usd") or None,
        provider_operations=n.get("provider_operations"),
        cache=n["cache"],
        record_ref=f"{run_dir.name}/execution-summary.json",
        **fields,
    )


def models_of(nodes: dict[str, dict]) -> list[dict]:
    """The models a record's nodes called, with their roles and how many nodes each served."""
    models: dict[str, dict] = {}
    for n in nodes.values():
        if n["model"]:
            entry = models.setdefault(
                n["model"],
                {
                    "name": n["model"],
                    "provider": n["provider"],
                    "roles": set(),
                    "nodes": 0,
                    "called_by": [],
                },
            )
            entry["roles"].add(n["kind"])
            entry["nodes"] += 1
    return [{**m, "roles": sorted(m["roles"])} for m in models.values()]
