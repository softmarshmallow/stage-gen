"""The gallery manifest: one terminal status per entity, written whatever happened.

This is a provider-free reduce that runs after the scheduler, not a node. A
package that vanishes because one image failed is useless for exploration, so
the manifest is always written: entities that were admitted, entities whose
image was rejected by review, and entities whose branch never reached a record
all appear, each with the reason it ended where it did.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from stage_gen.recipes.universe.universe_graph import (
    INPUT_POSTER_PROXY_REF,
    INPUT_UNIVERSE_REF,
    MANIFEST_REF,
    node_safe,
)
from stage_gen.recipes.universe.universe_types import MANIFEST_KIND

if TYPE_CHECKING:
    from pathlib import Path

    from gnode import RunSummary
    from stage_gen.recipes.universe.universe_graph import UniverseGraph
    from stage_gen.recipes.universe.universe_request import AdmittedUniverse

#: How a branch can end. ``admitted`` and ``rejected`` are review outcomes; the
#: rest are the stage at which the branch stopped.
ENTITY_STATUSES = (
    "admitted",
    "rejected",
    "direction_failed",
    "generation_failed",
    "review_failed",
    "unknown",
)


def finalize_gallery(
    run_dir: Path,
    graph: UniverseGraph,
    summary: RunSummary,
    admitted: AdmittedUniverse,
) -> dict[str, object]:
    """Reduce one finished gallery run into its manifest, provider untouched."""

    traces = {trace.node_id: trace for trace in summary.nodes}
    entries: list[dict[str, object]] = []
    counts: dict[str, int] = {}
    global_direction_failed = (
        "direction-global" in traces and traces["direction-global"].status.value == "failed"
    )
    for entity in admitted.proposal.entities:
        entity_id = entity.entity_id
        safe = node_safe(entity_id)
        record_ref = f"package/entities/{entity_id}.json"
        image_ref = f"package/entities/{entity_id}.png"
        review_ref = f"production/review/reviews/{entity_id}.json"
        status = "unknown"
        reason = ""
        if (run_dir / record_ref).is_file():
            status = str(json.loads((run_dir / record_ref).read_bytes())["status"])
        else:
            for stage, node_id in (
                ("direction_failed", f"direction-{safe}"),
                ("generation_failed", f"image-{safe}"),
                ("review_failed", f"review-{safe}"),
            ):
                trace = traces.get(node_id)
                if trace is not None and trace.status.value == "failed":
                    status = stage
                    reason = trace.error or ""
                    break
            # A failed global direction skips every entity branch, so the
            # branches themselves show no failure of their own to report.
            if status == "unknown" and global_direction_failed:
                status = "direction_failed"
                reason = traces["direction-global"].error or ""
        counts[status] = counts.get(status, 0) + 1
        entries.append(
            {
                "entity_id": entity_id,
                "display_name": entity.display_name,
                "primary_class": entity.primary_class,
                "status": status,
                "reason": reason,
                "image": image_ref if (run_dir / image_ref).is_file() else None,
                "record": record_ref if (run_dir / record_ref).is_file() else None,
                "review": review_ref if (run_dir / review_ref).is_file() else None,
            }
        )
    manifest: dict[str, object] = {
        "schema_version": 1,
        "kind": MANIFEST_KIND,
        "universe_id": admitted.universe_id,
        "title": admitted.title,
        "medium_id": graph.medium_id,
        "graph_sha256": graph.graph_sha256,
        "invocation_id": summary.invocation_id,
        "closed_in_graph": bool(summary.ok),
        # Run-relative, because the run carries the bytes its manifest names.
        "inputs": {
            "universe_path": INPUT_UNIVERSE_REF,
            "universe_sha256": admitted.universe_sha256,
            "poster_proxy_path": INPUT_POSTER_PROXY_REF,
        },
        "semantic_run": {
            "universe_sha256": admitted.universe_sha256,
            "poster_sha256": admitted.poster_sha256,
        },
        "sample_ledger_sha256": graph.sample_ledger_sha256,
        "counts": dict(sorted(counts.items())),
        "entity_count": len(entries),
        "entities": entries,
        "duration_ms": summary.duration_ms,
        "provider_operation_counts": summary.provider_operation_counts,
        "known_cost_usd": summary.known_cost_usd,
        "publication_authorized": False,
        "publication_gate": "all entities admitted and a separate human rights review",
    }
    (run_dir / MANIFEST_REF).write_bytes(
        (
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
            + "\n"
        ).encode("utf-8")
    )
    return manifest


__all__ = ["ENTITY_STATUSES", "finalize_gallery"]
