"""Seam nodes: does a layer loop already, repaint its wrap, and judge the repaint.

A seam layer is shown to the provider as ``[ end of the layer | start of the layer ]``, so
the wrap sits in the middle of the canvas and is repainted as ordinary interior; the
return is then registered against both ends and cut back into the layer. The judge reads
the same repeat gate the deterministic constructions pass, with the joins the cut made.
"""

from __future__ import annotations

import json
from typing import Any

from gnode import Ctx, node
from stage_gen.components.image_repeat import (
    ImageRepeatDeterministicReport,
    ImageRepeatStitch,
    ImageRepeatValidationPolicy,
    validate_image_repeat,
)
from stage_gen.components.sideview_layers.contract import LOOP_REPAINT_SPAN_PX
from stage_gen.components.sideview_layers.pipeline import (
    assemble_loop,
    layer_repeat_policies,
    loop_conditioning,
    recorded_stitches,
)
from stage_gen.media.codec import decode_rgba
from stage_gen.media.loop_construction import RegistrationError


def _repeat(
    data: bytes, *, transparent: bool, stitches: tuple[ImageRepeatStitch, ...] = ()
) -> ImageRepeatDeterministicReport:
    alpha_policy, coverage = layer_repeat_policies("transparent" if transparent else "opaque")
    return validate_image_repeat(
        data,
        axis="x",
        alpha_policy=alpha_policy,
        coverage_policy=coverage,
        validation_policy=ImageRepeatValidationPolicy(),
        stitches=stitches,
    )


@node(
    "loops_already",
    inputs={"image": "image"},
    params={"transparent": bool},
    judge=True,
    version=1,
)
def loops_already(ctx: Ctx) -> dict[str, Any]:
    """Accept a layer whose right edge already runs into its left: it needs no repaint."""

    report = _repeat(ctx.inputs["image"].read_bytes(), transparent=ctx.params["transparent"])
    ctx.fact("failure_codes", list(report.failure_codes))
    ctx.fact("verdict", "accept" if report.verdict == "pass" else "reject")
    return {}


@node(
    "seam_repaint",
    inputs={"image": "image"},
    params={"transparent": bool, "description": {"type": "string", "default": ""}},
    outputs={"image": "image/png?", "edit": "image/png", "report": "json"},
    calls={"image.edit": 1},
    resources=["prompts/seam.md"],
    version=1,
)
async def seam_repaint(ctx: Ctx) -> dict[str, Any]:
    """Repaint the wrap through one image edit, and cut the return back into the layer.

    A return that does not register against both ends is a different composition, not a
    displaced copy: no loop is assembled, and the report says why, for the judge.
    """

    source = ctx.inputs["image"].read_bytes()
    transparent = ctx.params["transparent"]
    conditioning = loop_conditioning("seam_repaint", source)
    result = await ctx.capability(
        "image.edit",
        image=ctx.out.bytes(conditioning.conditioning_png, "image/png"),
        mask=ctx.out.bytes(conditioning.mask_png, "image/png"),
        prompt=ctx.prompt(
            "prompts/seam.md",
            span_px=LOOP_REPAINT_SPAN_PX,
            description=" ".join(ctx.params["description"].split()),
        ),
        background="transparent" if transparent else "opaque",
        size=f"{conditioning.width}x{conditioning.height}",
    )
    edit = result.image.read_bytes()
    outputs: dict[str, Any] = {"edit": ctx.out.bytes(edit, "image/png")}
    try:
        looped, record = assemble_loop("seam_repaint", source, edit, conditioning=conditioning)
    except RegistrationError as error:
        outputs["report"] = ctx.out.json({"construction": "seam_repaint", "rejection": str(error)})
        return outputs
    record["construction"] = "seam_repaint"
    outputs["image"] = ctx.out.bytes(looped, "image/png")
    outputs["report"] = ctx.out.json(record)
    return outputs


@node(
    "seam_check",
    inputs={"image": "image?", "source": "image", "report": "json"},
    params={"transparent": bool},
    judge=True,
    version=1,
)
def seam_check(ctx: Ctx) -> dict[str, Any]:
    """Accept a repainted loop that keeps the layer's size and passes the repeat gate."""

    record = json.loads(ctx.inputs["report"].read_bytes())
    image = ctx.inputs.get("image")
    if image is None:
        ctx.fact("reason", record.get("rejection", "no loop was assembled"))
        ctx.fact("verdict", "reject")
        return {}
    data = image.read_bytes()
    size = decode_rgba(data).size
    expected = decode_rgba(ctx.inputs["source"].read_bytes()).size
    if size != expected:
        ctx.fact("reason", f"the loop is {size[0]}x{size[1]}, not {expected[0]}x{expected[1]}")
        ctx.fact("verdict", "reject")
        return {}
    report = _repeat(
        data, transparent=ctx.params["transparent"], stitches=recorded_stitches(record)
    )
    ctx.fact("failure_codes", list(report.failure_codes))
    ctx.fact("verdict", "accept" if report.verdict == "pass" else "reject")
    return {}
