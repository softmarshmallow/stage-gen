"""The runner's one-shot audio: generated clips, spoken lines, and pinned takes.

A clip is drawn from its authored prompt, verbatim, and a spoken line read from its authored
text by its cast voice. A judge refuses a draw that is not a playable, unclipped MP3 (or a
line longer than its ceiling) and draws it again; nothing is ever trimmed. A local step
measures what was kept and records it; a clip must also run its authored length. A pinned
take is a reviewed audition from the package, republished with its sidecar under the same
gates a fresh draw meets.
"""

from __future__ import annotations

from typing import Any

from gnode import Ctx, node
from iron_petal_unit_pipeline.admission import listening_verdict
from stage_gen.components.sound_effect import DURATION_TOLERANCE_SECONDS, admission_facts
from stage_gen.components.speech import speech_admission_facts
from stage_gen.media import measure_level_and_duration, measure_peak_dbfs, probe_audio

_TIMEOUT_SECONDS = 120
_LINE_CEILING: dict[str, Any] = {"type": ["number", "null"], "default": None}


async def _clip_facts(ctx: Ctx, data: bytes) -> dict[str, object]:
    peak = await measure_peak_dbfs(
        data, ffmpeg=ctx.tool("ffmpeg").executable, timeout_seconds=_TIMEOUT_SECONDS
    )
    return admission_facts(data, peak)


async def _line_facts(ctx: Ctx, data: bytes, max_seconds: float | None) -> dict[str, object]:
    measured = await measure_level_and_duration(
        data, ffmpeg=ctx.tool("ffmpeg").executable, timeout_seconds=_TIMEOUT_SECONDS
    )
    return speech_admission_facts(data, measured, max_seconds=max_seconds)


@node("admit_clip", inputs={"audio": "audio"}, tools=["ffmpeg"], judge=True, version=1)
async def admit_clip(ctx: Ctx) -> dict[str, Any]:
    """A playable MP3 with a live, unclipped peak, or it is drawn again."""

    try:
        facts = await _clip_facts(ctx, ctx.read.bytes("audio"))
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("admission", facts)
    ctx.fact("verdict", "accept")
    return {}


@node(
    "admit_line",
    inputs={"audio": "audio"},
    params={"max_seconds": _LINE_CEILING},
    tools=["ffmpeg"],
    judge=True,
    version=1,
)
async def admit_line(ctx: Ctx) -> dict[str, Any]:
    """A playable, unclipped read no longer than its ceiling, or it is read again."""

    try:
        facts = await _line_facts(ctx, ctx.read.bytes("audio"), ctx.params["max_seconds"])
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("admission", facts)
    ctx.fact("verdict", "accept")
    return {}


@node(
    "record_clip",
    inputs={"audio": "audio"},
    params={"effect_id": str, "duration_seconds": float, "pinned": bool},
    outputs={"validation": "json"},
    tools=["ffmpeg", "ffprobe"],
    version=1,
)
async def record_clip(ctx: Ctx) -> dict[str, Any]:
    """Measure the clip, refuse one that misses its authored length, and record it."""

    effect_id = ctx.params["effect_id"]
    authored = ctx.params["duration_seconds"]
    probe = await probe_audio(
        ctx.inputs["audio"].path,
        ffprobe=ctx.tool("ffprobe").executable,
        timeout_seconds=_TIMEOUT_SECONDS,
    )
    delta = probe.duration_seconds - authored
    if abs(delta) > DURATION_TOLERANCE_SECONDS:
        raise ctx.fail(
            f"generated clip {effect_id} runs {probe.duration_seconds:.3f}s against an "
            f"authored {authored:.3f}s"
        )
    level = await _clip_facts(ctx, ctx.read.bytes("audio"))
    return {
        "validation": ctx.out.json(
            {
                "schema_version": 1,
                "kind": "sideview-runner-sound-effect-validation-v1",
                "effect_id": effect_id,
                "format_name": probe.format_name,
                "duration_seconds": round(probe.duration_seconds, 3),
                "authored_duration_seconds": authored,
                "duration_delta_seconds": round(delta, 3),
                "peak_dbfs": level["peak_dbfs"],
                "clipped": level["clipped"],
                "container_valid": True,
                "listening_verdict": listening_verdict(pinned=ctx.params["pinned"]),
            }
        )
    }


@node(
    "record_line",
    inputs={"audio": "audio"},
    params={"effect_id": str, "voice_id": str, "max_seconds": _LINE_CEILING, "pinned": bool},
    outputs={"validation": "json"},
    tools=["ffmpeg", "ffprobe"],
    version=1,
)
async def record_line(ctx: Ctx) -> dict[str, Any]:
    """Measure the read and record it; its length is measured, never authored."""

    max_seconds = ctx.params["max_seconds"]
    probe = await probe_audio(
        ctx.inputs["audio"].path,
        ffprobe=ctx.tool("ffprobe").executable,
        timeout_seconds=_TIMEOUT_SECONDS,
    )
    facts = await _line_facts(ctx, ctx.read.bytes("audio"), max_seconds)
    return {
        "validation": ctx.out.json(
            {
                "schema_version": 1,
                "kind": "sideview-runner-speech-validation-v1",
                "effect_id": ctx.params["effect_id"],
                "voice_id": ctx.params["voice_id"],
                "format_name": probe.format_name,
                "duration_seconds": round(probe.duration_seconds, 3),
                "max_seconds": max_seconds,
                "peak_dbfs": facts["peak_dbfs"],
                "clipped": facts["clipped"],
                "container_valid": True,
                "listening_verdict": listening_verdict(pinned=ctx.params["pinned"]),
            }
        )
    }


@node(
    "republish_take",
    inputs={"audio": "audio", "provenance": "json"},
    params={"spoken": bool, "max_seconds": _LINE_CEILING},
    outputs={"audio": "audio/mpeg", "provenance": "json"},
    tools=["ffmpeg"],
    version=1,
)
async def republish_take(ctx: Ctx) -> dict[str, Any]:
    """Install a reviewed take, sidecar and all, after the gates a fresh draw meets.

    The sidecar is the take's provenance and is kept verbatim: rewriting it would claim this
    run made what a person chose. A pinned take that clips is a package error, not a shipped
    one.
    """

    data = ctx.read.bytes("audio")
    if ctx.params["spoken"]:
        await _line_facts(ctx, data, ctx.params["max_seconds"])
    else:
        await _clip_facts(ctx, data)
    return {"audio": ctx.inputs["audio"], "provenance": ctx.inputs["provenance"]}


__all__ = [
    "admit_clip",
    "admit_line",
    "record_clip",
    "record_line",
    "republish_take",
]
