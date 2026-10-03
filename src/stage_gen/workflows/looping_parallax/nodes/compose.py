"""Compose the layers: one manifest of placement and repeat geometry, and a preview frame."""

from __future__ import annotations

import hashlib
from typing import Any

from gnode import Ctx, NodeFailure, node
from stage_gen.components.sideview_layers.parallax import (
    ParallaxLayer,
    ParallaxLayerConstruction,
    ParallaxSpec,
    PreparedParallaxLayer,
    parallax_manifest,
    render_parallax,
)
from stage_gen.media.codec import decode_rgba

#: What a seam layer ended as, by the candidate ``select`` took: the repaint, the
#: reflection, or the supplied layer because it already looped.
_SEAM_OUTCOMES: tuple[ParallaxLayerConstruction, ...] = (
    "seam_repaint",
    "mirror_repeat",
    "admitted",
)


@node(
    "compose",
    inputs={"layers": "image{}"},
    params={"specs": list, "canvas": dict, "constructions": dict},
    outputs={"manifest": "json", "preview": "image/png"},
    view="views/parallax.html",
    version=1,
)
def compose(ctx: Ctx) -> dict[str, Any]:
    """Place every layer by its order, offsets and scroll factor; draw it at scroll 0."""

    canvas = ctx.params["canvas"]
    spec = ParallaxSpec(
        width=canvas["width"],
        height=canvas["height"],
        layers=[
            ParallaxLayer(
                layer_id=entry["layer_id"],
                source=f"{entry['layer_id']}.png",
                order=entry["order"],
                parallax=entry["parallax"],
                offset_x=entry["offset_x"],
                offset_y=entry["offset_y"],
                repeat_x=entry["repeat_x"],
                repeat_y=entry["repeat_y"],
                loop_construction=entry["loop_construction"],
                description=entry.get("description") or None,
            )
            for entry in ctx.params["specs"]
        ],
    )
    chosen = ctx.inputs["layers"]
    prepared: dict[str, PreparedParallaxLayer] = {}
    for layer in spec.layers:
        if layer.layer_id not in chosen:
            raise NodeFailure(f"layer {layer.layer_id} has no picture to compose")
        data = chosen[layer.layer_id].read_bytes()
        image = decode_rgba(data)
        construction: ParallaxLayerConstruction = "mirror_repeat"
        if layer.loop_construction == "seam_repaint":
            construction = _SEAM_OUTCOMES[int(ctx.params["constructions"][layer.layer_id])]
        prepared[layer.layer_id] = PreparedParallaxLayer(
            data=data,
            width=image.width,
            height=image.height,
            source_sha256=hashlib.sha256(data).hexdigest(),
            construction=construction,
        )
    manifest = parallax_manifest(spec, prepared)
    return {
        "manifest": ctx.out.json(manifest),
        "preview": ctx.out.bytes(render_parallax(spec, prepared), "image/png"),
    }
