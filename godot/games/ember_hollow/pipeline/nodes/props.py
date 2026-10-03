"""A prop's ground anchor, placed by an agent that looks at its own proposals.

The agent is handed the baseline sprite and a tool that redraws it standing on a one-metre
ground grid at the scene camera's pitch, with its proposed anchor cross and footprint
ellipse; it adjusts until the ellipse sits under the object, picks a motion hint, and
submits. A submission outside the painted silhouette or above its lower third is handed
back as the tool's answer and the episode goes on.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from typing import Any

from ember_hollow_pipeline.anchor import (
    ANCHOR_MAX_STEPS,
    ANCHOR_SYSTEM,
    RENDER_PARAMETERS,
    SUBMIT_SCHEMA,
    AnchorSubject,
    admit,
    anchor_record,
    instructions,
    render,
)
from gnode import Ctx, Tool, ToolInvocationError, ToolResult, node


def _data_url(data: bytes, media_type: str) -> str:
    return f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"


@node(
    "place_anchor",
    inputs={"sprite": "image", "validation": "json"},
    params={"subject": dict},
    outputs={"anchor": "json"},
    calls={"agent.turn": ANCHOR_MAX_STEPS},
    version=1,
)
async def place_anchor(ctx: Ctx) -> dict[str, Any]:
    """Try placements with the render tool, judge them by eye, and submit one."""

    subject = AnchorSubject(**ctx.params["subject"])
    sprite = ctx.read.bytes("sprite")
    validation: Mapping[str, Any] = ctx.read.json("validation")

    def draw(arguments: Mapping[str, object]) -> ToolResult:
        try:
            text, plate = render(subject, sprite, validation, arguments)
        except (KeyError, ValueError) as error:
            raise ToolInvocationError(str(error)) from None
        return ToolResult(text=text, images=(_data_url(plate, "image/jpeg"),))

    placed: dict[str, object] = {}

    def check(value: object) -> None:
        placed.clear()
        placed.update(admit(value, validation))

    agent = ctx.agent(
        system=ANCHOR_SYSTEM,
        tools=(
            Tool(
                name="render_with_placement",
                description=(
                    "Draw the prop standing on a one-metre ground grid with your proposed "
                    "anchor cross and footprint ellipse, and return the picture."
                ),
                parameters=RENDER_PARAMETERS,
                handler=draw,
            ),
        ),
    )
    await agent.run(
        instructions(subject, validation),
        max_steps=ANCHOR_MAX_STEPS,
        images=[_data_url(sprite, "image/png")],
        submit=SUBMIT_SCHEMA,
        check=check,
    )
    return {"anchor": ctx.out.json(anchor_record(subject, placed, validation))}


__all__ = ["place_anchor"]
