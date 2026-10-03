"""The runner's catalog: props, items and projectiles, each a trimmed cut-out.

A catalog asset is painted at a square canvas; a judge refuses one without real negative
space, or whose trim and measured extent cannot be taken, and draws it again. Publishing
trims it to its alpha box, and a prop also loses a proven short sparse tail below the broad
foot gameplay registers.
"""

from __future__ import annotations

from typing import Any

from gnode import Ctx, node
from iron_petal_unit_pipeline.admission import (
    admit_catalog_candidate,
    admit_transparent_sprite,
    canonicalize_runner_catalog_sprite,
)

#: The canvas a catalog asset is drawn at.
CATALOG_SIZE = (1024, 1024)
_FAMILY = ("prop", "item", "projectile")


@node("admit_catalog", inputs={"image": "image"}, params={"family": _FAMILY}, judge=True, version=1)
def admit_catalog(ctx: Ctx) -> dict[str, Any]:
    """A square cut-out whose trim and painted extent can be measured, or it is redrawn."""

    try:
        facts = admit_catalog_candidate(ctx.read.bytes("image"), family=ctx.params["family"])
        source = facts["source"]
        assert isinstance(source, dict)
        if (source["width"], source["height"]) != CATALOG_SIZE:
            raise ValueError(f"a catalog asset is drawn at {CATALOG_SIZE[0]}x{CATALOG_SIZE[1]}")
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("admission", facts)
    ctx.fact("verdict", "accept")
    return {}


@node(
    "publish_catalog",
    inputs={"raw": "image"},
    params={"family": _FAMILY, "entity_id": str},
    outputs={"image": "image/png", "validation": "json"},
    version=1,
)
def publish_catalog(ctx: Ctx) -> dict[str, Any]:
    """Trim the asset to its alpha box, and a prop's proven sparse tail with it."""

    source = ctx.read.bytes("raw")
    family = ctx.params["family"]
    published, trim, sparse_tail_trim = canonicalize_runner_catalog_sprite(source, family=family)
    return {
        "image": ctx.out.bytes(published, "image/png"),
        "validation": ctx.out.json(
            {
                "schema_version": 3,
                "kind": "sideview-runner-catalog-validation-v3",
                "family": family,
                "entity_id": ctx.params["entity_id"],
                "source_validation": admit_transparent_sprite(source),
                "trim": trim,
                "sparse_tail_trim": sparse_tail_trim,
            }
        ),
    }


__all__ = ["CATALOG_SIZE", "admit_catalog", "publish_catalog"]
