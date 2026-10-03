"""Soundtrack: one generated track per authored brief, its container and length admitted.

The track is drawn from its prompt; a judge refuses a payload that is not a playable MP3 and
draws it again; a local step measures it, refuses one shorter than a usable loop, and records
the measured clip against what was asked for. Nobody has listened to it yet: the record says
so.
"""

from __future__ import annotations

from typing import Any

from gnode import Ctx, Group, StepRef, node
from stage_gen.media import probe_audio, validate_music_payload

#: Draws a track gets before the run stops on it.
TRACK_TAKES = 6
#: The shortest track that still loops as background music.
MINIMUM_TRACK_SECONDS = 15.0
SOUNDTRACK_VALIDATION_KIND = "soundtrack-validation-v1"


@node("admit_track", inputs={"audio": "audio"}, judge=True, version=1)
def admit_track(ctx: Ctx) -> dict[str, Any]:
    """A playable MP3 payload, or it is drawn again."""

    try:
        facts = validate_music_payload(ctx.read.bytes("audio"))
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("payload", facts)
    ctx.fact("verdict", "accept")
    return {}


@node(
    "record_track",
    inputs={"audio": "audio"},
    params={
        "track_id": str,
        "target_duration_seconds": float,
        "instrumental": bool,
        "seamless_loop": bool,
    },
    outputs={"validation": "json"},
    tools=["ffprobe"],
    version=1,
)
async def record_track(ctx: Ctx) -> dict[str, Any]:
    """Measure the track, refuse one too short to loop, and record it against the brief."""

    probe = await probe_audio(
        ctx.inputs["audio"].path, ffprobe=ctx.tool("ffprobe").executable, timeout_seconds=120
    )
    if probe.duration_seconds < MINIMUM_TRACK_SECONDS:
        raise ctx.fail(
            f"the {ctx.params['track_id']} track is shorter than {MINIMUM_TRACK_SECONDS:g} seconds"
        )
    target = ctx.params["target_duration_seconds"]
    return {
        "validation": ctx.out.json(
            {
                "schema_version": 1,
                "kind": SOUNDTRACK_VALIDATION_KIND,
                "track_id": ctx.params["track_id"],
                "format_name": probe.format_name,
                "duration_seconds": round(probe.duration_seconds, 3),
                "target_duration_seconds": target,
                "target_delta_seconds": round(probe.duration_seconds - target, 3),
                "bit_rate": probe.bit_rate,
                "instrumental_intent": ctx.params["instrumental"],
                "seamless_loop_intent": ctx.params["seamless_loop"],
                "container_valid": True,
                "listening_verdict": "not_performed",
            }
        )
    }


def add_track_steps(
    group: Group,
    *,
    nodes: str,
    track_id: str,
    prompt: str,
    target_duration_seconds: float,
    instrumental: bool,
    seamless_loop: bool,
) -> dict[str, StepRef]:
    """Write one track's draw, judge and record into ``group``."""

    draw = group.step(
        "generate",
        title="Compose the track",
        uses="gnode/music.generate@1",
        with_={"prompt": prompt},
        view=True,
    )
    group.step(
        "admit",
        title="Admit the payload",
        uses=f"{nodes}#admit_track",
        judges="generate",
        with_={"audio": draw.outputs.audio},
        on_reject={"regenerate": {"max": TRACK_TAKES, "then": "fail"}},
    )
    record = group.step(
        "record",
        title="Measure it",
        uses=f"{nodes}#record_track",
        with_={
            "audio": draw.outputs.audio,
            "track_id": track_id,
            "target_duration_seconds": float(target_duration_seconds),
            "instrumental": instrumental,
            "seamless_loop": seamless_loop,
        },
    )
    return {"generate": draw, "record": record}


__all__ = [
    "MINIMUM_TRACK_SECONDS",
    "SOUNDTRACK_VALIDATION_KIND",
    "TRACK_TAKES",
    "add_track_steps",
    "admit_track",
    "record_track",
]
