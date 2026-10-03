"""The style anchor's steps: its answer shape, its judge, and the record every image reads.

A selection that does not name an approved mode with a treatment for every asset kind the
build draws is refused and asked again; the accepted one is materialized into
``style-anchor.json`` and the clause each kind's prompts end with.
"""

from __future__ import annotations

from typing import Any, cast

from gnode import Ctx, node
from stage_gen.image_style import ImageAssetKind
from the_grain_pipeline.style import style_anchor, style_clauses, style_schema

_KINDS = {"asset_kinds": {"type": "array", "items": {"type": "string"}}}


def _kinds(ctx: Ctx) -> list[ImageAssetKind]:
    return cast(list[ImageAssetKind], list(ctx.params["asset_kinds"]))


@node("selection_schema", outputs={"schema": "json"}, version=1)
def selection_schema(ctx: Ctx) -> dict[str, Any]:
    """The selection's answer shape: one approved style mode."""

    return {"schema": ctx.out.json(style_schema())}


@node("admit_style", inputs={"selection": "json"}, params=_KINDS, judge=True, version=1)
def admit_style(ctx: Ctx) -> dict[str, Any]:
    """The selection names an approved mode that treats every kind drawn, or is asked again."""

    try:
        anchor = style_anchor(ctx.read.json("selection"), _kinds(ctx))
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("style_mode", anchor.style_mode)
    ctx.fact("verdict", "accept")
    return {}


@node(
    "style_record",
    inputs={"selection": "json"},
    params=_KINDS,
    outputs={"anchor": "json", "clauses": "json"},
    version=1,
)
def style_record(ctx: Ctx) -> dict[str, Any]:
    """The canonical anchor, and the clause each asset kind's prompts end with."""

    kinds = _kinds(ctx)
    anchor = style_anchor(ctx.read.json("selection"), kinds)
    return {
        "anchor": ctx.out.json(anchor.model_dump(mode="json")),
        "clauses": ctx.out.json(style_clauses(anchor, kinds)),
    }


__all__ = ["admit_style", "selection_schema", "style_record"]
