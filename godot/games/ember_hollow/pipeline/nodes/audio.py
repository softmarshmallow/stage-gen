"""Ember Hollow's tracks and clips: the judge each one meets, publication, and adoption.

A music loop must be long enough and loud enough; a sound clip must not be silent or
clipped and must be as long as it was asked to be. Both are measured with ffmpeg. An
auditioned take, picked by ear, is adopted through the same gate instead of drawn: the
routes have no seed, so a redraw of a brief the user already chose is a different sound.
"""

from __future__ import annotations

import hashlib
from typing import Any

from ember_hollow_pipeline import build
from gnode import Ctx, node

_GATE = {"gate": ("music", "sound"), "args": dict}


@node(
    "admit_audio",
    inputs={"audio": "audio"},
    params=_GATE,
    tools=["ffmpeg"],
    judge=True,
    version=1,
)
def admit_audio(ctx: Ctx) -> dict[str, Any]:
    """The track or clip passes its gate, or it is composed again."""

    try:
        facts = build.gate_audio(
            ctx.params["gate"],
            ctx.read.bytes("audio"),
            ctx.params["args"],
            ffmpeg=ctx.tool("ffmpeg").executable,
        )
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("admission", facts)
    ctx.fact("verdict", "accept")
    return {}


@node(
    "publish_audio",
    inputs={"source": "audio"},
    params={**_GATE, "head": dict},
    outputs={"audio": "audio/mpeg", "validation": "json"},
    tools=["ffmpeg"],
    version=1,
)
def publish_audio(ctx: Ctx) -> dict[str, Any]:
    """The admitted bytes, unchanged, and the record of their length and peak."""

    data = ctx.read.bytes("source")
    record = build.finish_audio(
        ctx.params["gate"],
        data,
        ctx.params["args"],
        head=ctx.params["head"],
        ffmpeg=ctx.tool("ffmpeg").executable,
    )
    return {"audio": ctx.out.bytes(data, "audio/mpeg"), "validation": ctx.out.json(record)}


@node(
    "adopt_audio",
    inputs={"take": "audio?"},
    params={**_GATE, "path": str, "sha256": str},
    outputs={"audio": "audio/mpeg"},
    tools=["ffmpeg"],
    version=1,
)
def adopt_audio(ctx: Ctx) -> dict[str, Any]:
    """An auditioned take, picked by ear, adopted through the gate a fresh draw meets."""

    path = ctx.params["path"]
    if "take" not in ctx.inputs:
        raise ctx.fail(
            f"the take {path} is not on disk: auditioned takes are kept beside the package, "
            "not in git, so copy it into the package before building"
        )
    data = ctx.read.bytes("take")
    found = hashlib.sha256(data).hexdigest()
    if found != ctx.params["sha256"]:
        raise ctx.fail(
            f"the take {path} does not match its declared sha256: "
            f"declared {ctx.params['sha256']}, found {found}"
        )
    try:
        facts = build.gate_audio(
            ctx.params["gate"], data, ctx.params["args"], ffmpeg=ctx.tool("ffmpeg").executable
        )
    except ValueError as error:
        raise ctx.fail(f"the take {path} does not pass its gate: {error}") from None
    ctx.fact("adoption", {"adopted_from": path, "adopted_sha256": found, **facts})
    return {"audio": ctx.out.bytes(data, "audio/mpeg")}


__all__ = ["admit_audio", "adopt_audio", "publish_audio"]
