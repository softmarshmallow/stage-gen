"""Scrolling layers: a painted layer admitted, made to loop, then trimmed and placed.

A layer is painted from its references (a paid edit), admitted against the host's floors by a
judge that draws it again when it fails, made to repeat on x by its declared construction (a
generative construction repaints the seam in one more paid edit and falls back to a
deterministic one when that is refused), and published: trimmed to its alpha box with its
placement resolved from the raster it actually received.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from gnode import Ctx, Group, StepRef, node
from stage_gen.components.sideview_layers.models import LayerRequest
from stage_gen.components.sideview_layers.pipeline import loop_layer as construct_loop
from stage_gen.components.sideview_layers.publish import (
    LayerGate,
    admit_layer_candidate,
    bounded_repeat_preview,
)
from stage_gen.components.sideview_layers.publish import (
    publish_layer as publish_loop_unit,
)
from stage_gen.media import LOOP_METHODS, LoopConstruction
from stage_gen.media.loop_construction import SeamConditioning

#: Takes a painted layer gets before the run stops on it.
LAYER_TAKES = 6


@node(
    "admit_layer",
    inputs={"image": "image"},
    params={
        "transparent": bool,
        "minimum_transparent_fraction": {"type": "number", "default": 0.0},
        "minimum_visible_fraction": {"type": "number", "default": 0.0},
        "minimum_transparent_edge_fraction": {"type": "number", "default": 0.0},
    },
    judge=True,
    version=1,
)
def admit_layer(ctx: Ctx) -> dict[str, Any]:
    """The painted layer is the canvas size and clears the host's floors, or it is drawn again."""

    gate = LayerGate(
        minimum_transparent_fraction=ctx.params["minimum_transparent_fraction"],
        minimum_visible_fraction=ctx.params["minimum_visible_fraction"],
        minimum_transparent_edge_fraction=ctx.params["minimum_transparent_edge_fraction"],
    )
    try:
        facts = admit_layer_candidate(
            ctx.read.bytes("image"), transparent=ctx.params["transparent"], gate=gate
        )
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("admission", facts)
    ctx.fact("verdict", "accept")
    return {}


_LOOP_PARAMS: dict[str, Any] = {
    "construction": str,
    "fallback": str,
    "alpha_mode": ("opaque", "transparent"),
    "label": str,
}
_LOOP_OUTPUTS = {"image": "image/png", "report": "json", "edit": "image/png?"}


async def _loop(ctx: Ctx, *, repaint: bool) -> dict[str, Any]:
    construction = ctx.params["construction"]
    alpha_mode = ctx.params["alpha_mode"]
    if LOOP_METHODS[construction].is_generative != repaint:
        kind = "repaints" if repaint else "constructs"
        raise ctx.fail(f"a {construction} loop is not one this step {kind}")

    async def paint(conditioning: SeamConditioning) -> tuple[bytes, int]:
        # The brief may name the canvas it will see: how wide the span to paint is, and how
        # much finished artwork stands either side of it.
        prompt = (
            ctx.params["prompt"]
            .replace("{editable_span}", str(conditioning.editable_span))
            .replace("{context_span}", str(conditioning.context_span))
        )
        made = await ctx.image_edit(
            image=ctx.out.bytes(conditioning.conditioning_png, "image/png"),
            mask=ctx.out.bytes(conditioning.mask_png, "image/png"),
            prompt=prompt,
            size=f"{conditioning.width}x{conditioning.height}",
            background="transparent" if alpha_mode == "transparent" else "opaque",
        )
        return made.image.read_bytes(), 1

    outcome = await construct_loop(
        ctx.read.bytes("raw"),
        construction=construction,
        fallback=ctx.params["fallback"],
        alpha_mode=alpha_mode,
        label=ctx.params["label"],
        paint=paint if repaint else None,
    )
    ctx.fact("construction", outcome.record.get("construction"))
    ctx.fact("provider_operations", outcome.provider_operations)
    outputs: dict[str, Any] = {
        "image": ctx.out.bytes(outcome.looped, "image/png"),
        "report": ctx.out.json(outcome.record),
    }
    if repaint and outcome.edit_data is not None:
        outputs["edit"] = ctx.out.bytes(outcome.edit_data, "image/png")
    return outputs


@node("loop_layer", inputs={"raw": "image"}, params=_LOOP_PARAMS, outputs=_LOOP_OUTPUTS, version=1)
async def loop_layer(ctx: Ctx) -> dict[str, Any]:
    """Admit the painted layer as a loop, or construct one deterministically."""

    return await _loop(ctx, repaint=False)


@node(
    "repaint_loop_layer",
    inputs={"raw": "image"},
    params={**_LOOP_PARAMS, "prompt": str},
    outputs=_LOOP_OUTPUTS,
    calls={"image.edit": 1},
    version=1,
)
async def repaint_loop_layer(ctx: Ctx) -> dict[str, Any]:
    """Admit the painted layer as a loop, or repaint its seam (one paid edit) to make one.

    ``{editable_span}`` and ``{context_span}`` in the brief become the conditioning canvas's
    pixel spans. A refused repaint falls back to the declared deterministic construction.
    """

    return await _loop(ctx, repaint=True)


@node(
    "publish_layer",
    inputs={"loop": "image"},
    params={"layer": dict, "place_opaque": {"type": "boolean", "default": True}},
    outputs={"image": "image/png", "validation": "json", "preview": "image/png"},
    version=1,
)
def publish_layer(ctx: Ctx) -> dict[str, Any]:
    """Trim the loop unit to its alpha box, keep its period, and resolve its placement."""

    layer = LayerRequest.model_validate(ctx.params["layer"])
    published, record = publish_loop_unit(
        layer, ctx.read.bytes("loop"), place_opaque=ctx.params["place_opaque"]
    )
    return {
        "image": ctx.out.bytes(published, "image/png"),
        "validation": ctx.out.json(record),
        "preview": ctx.out.bytes(bounded_repeat_preview(published), "image/png"),
    }


def add_layer_steps(
    group: Group,
    *,
    nodes: str,
    references: Sequence[str],
    prompt: str,
    size: str,
    layer: Mapping[str, Any],
    construction: str,
    fallback: str,
    label: str,
    loop_prompt: str,
    gate: LayerGate,
    place_opaque: bool,
) -> dict[str, StepRef]:
    """Write one layer's paint, judge, loop and publish into ``group``.

    ``nodes`` is the game's module that re-exports this family's types (``./nodes/layers.py``);
    ``references`` are project paths, the first shown as the picture being edited.
    """

    if not references:
        raise ValueError(f"layer {label} paints from at least one reference")
    transparent = layer["alpha_mode"] == "transparent"
    generate = group.step(
        "generate",
        title="Paint the layer",
        uses="gnode/image.edit@1",
        with_={
            "image": references[0],
            "references": list(references[1:]),
            "prompt": prompt,
            "size": size,
            "background": "transparent" if transparent else "opaque",
        },
        requires=["transparent_background"] if transparent else [],
        view=True,
    )
    admit = group.step(
        "admit",
        title="Admit the painting",
        uses=f"{nodes}#admit_layer",
        judges="generate",
        with_={
            "image": generate.outputs.image,
            "transparent": transparent,
            "minimum_transparent_fraction": gate.minimum_transparent_fraction,
            "minimum_visible_fraction": gate.minimum_visible_fraction,
            "minimum_transparent_edge_fraction": gate.minimum_transparent_edge_fraction,
        },
        on_reject={"regenerate": {"max": LAYER_TAKES, "then": "fail"}},
    )
    generative = LOOP_METHODS[cast(LoopConstruction, construction)].is_generative
    looping: dict[str, Any] = {
        "raw": generate.outputs.image,
        "construction": construction,
        "fallback": fallback,
        "alpha_mode": layer["alpha_mode"],
        "label": label,
    }
    if generative:
        looped = group.step(
            "loop",
            title="Repaint the seam",
            uses=f"{nodes}#repaint_loop_layer",
            with_={**looping, "prompt": loop_prompt},
            requires=["mask", *(["transparent_background"] if transparent else [])],
            view=True,
        )
    else:
        looped = group.step(
            "loop",
            title="Make it repeat",
            uses=f"{nodes}#loop_layer",
            with_=looping,
            view=True,
        )
    published = group.step(
        "publish",
        title="Trim and place it",
        uses=f"{nodes}#publish_layer",
        with_={"loop": looped.outputs.image, "layer": dict(layer), "place_opaque": place_opaque},
        view=True,
    )
    return {"generate": generate, "admit": admit, "loop": looped, "publish": published}


__all__ = [
    "LAYER_TAKES",
    "add_layer_steps",
    "admit_layer",
    "loop_layer",
    "publish_layer",
    "repaint_loop_layer",
]
