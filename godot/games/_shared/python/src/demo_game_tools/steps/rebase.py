"""Motion rebase: how much larger or smaller each state's drawing is than the baseline's.

Separate states are separate drawings, so nothing in their pixels ties their scale together.
A plate shows every frame of every state at one uniform scale; a vision model reads a
multiplier per state from it, and a judge holds the reading to the plate (coverage, the
baseline at one, plausible bounds), drawing it again when it fails. A second pass applies the
first reading, composes the plate again and asks only for the residual, and the two multiply.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from demo_game_tools.kits.sideview_actor.motion_rebase import (
    MotionRebaseError,
    admit_first_pass_record,
    build_motion_rebase_plate,
    build_motion_rebase_verification_plate,
    evaluate_motion_rebase,
    evaluate_motion_rebase_correction,
    motion_rebase_json_schema,
    motion_rebase_prompt,
    motion_rebase_verification_prompt,
    parse_motion_rebase,
)
from gnode import Ctx, Group, StepRef, node
from stage_gen.media.sprite_sheets import split_atlas_columns

#: Readings a pass gets before the run stops on it.
REBASE_TAKES = 6
#: The judge is told to answer only in the schema; the words are part of the request.
JUDGE_SYSTEM_PROMPT = (
    "You are a sprite-sheet scale judge. Return only the strict structured object."
)

_SUBJECT = {
    "atlases": "image{}",
}
_PARAMS: dict[str, Any] = {
    "states": {"type": "array", "items": {"type": "string"}},
    "baseline_state": str,
    #: Each state's atlas grid, ``{state: [columns, rows]}``.
    "geometry": dict,
}


def _frames(ctx: Ctx) -> dict[str, tuple[bytes, ...]]:
    atlases = ctx.inputs["atlases"]
    frames: dict[str, tuple[bytes, ...]] = {}
    for state in ctx.params["states"]:
        if state not in atlases:
            raise ctx.fail(f"the rebase has no atlas for {state}")
        columns, rows = ctx.params["geometry"][state]
        frames[state] = split_atlas_columns(atlases[state].read_bytes(), columns, rows)
    return frames


def _plate(ctx: Ctx) -> Any:
    return build_motion_rebase_plate(_frames(ctx), baseline_state=ctx.params["baseline_state"])


@node("rebase_schema", outputs={"schema": "json"}, version=1)
def rebase_schema(ctx: Ctx) -> dict[str, Any]:
    """The answer a reading must have: one multiplier per state."""

    return {"schema": ctx.out.json(motion_rebase_json_schema())}


@node("rebase_plate", inputs=_SUBJECT, params=_PARAMS, outputs={"plate": "image/png"}, version=1)
def rebase_plate(ctx: Ctx) -> dict[str, Any]:
    """Every frame of every state at one uniform source scale, banded by state."""

    composed = _plate(ctx)
    ctx.fact("frame_count", len(composed.frames))
    return {"plate": ctx.out.bytes(composed.png, "image/png")}


def _first_pass_record(ctx: Ctx, reading: object) -> dict[str, object]:
    return evaluate_motion_rebase(
        parse_motion_rebase(reading),
        published_states=list(ctx.params["states"]),
        plate=_plate(ctx),
        baseline_state=ctx.params["baseline_state"],
    )


def _admitted_first_pass(ctx: Ctx, frames: dict[str, tuple[bytes, ...]]) -> dict[str, float]:
    baseline = ctx.params["baseline_state"]
    return admit_first_pass_record(
        ctx.read.json("first_pass"),
        published_states=list(ctx.params["states"]),
        plate=build_motion_rebase_plate(frames, baseline_state=baseline),
        baseline_state=baseline,
    )


def _verified_record(ctx: Ctx, reading: object) -> dict[str, object]:
    frames = _frames(ctx)
    baseline = ctx.params["baseline_state"]
    first_pass = _admitted_first_pass(ctx, frames)
    return evaluate_motion_rebase_correction(
        parse_motion_rebase(reading),
        first_pass=first_pass,
        published_states=list(ctx.params["states"]),
        plate=build_motion_rebase_plate(frames, baseline_state=baseline),
        verification_plate=build_motion_rebase_verification_plate(
            frames, first_pass, baseline_state=baseline
        ),
        baseline_state=baseline,
    )


def _judge(ctx: Ctx, evaluate: Callable[[Ctx, object], dict[str, object]]) -> dict[str, Any]:
    try:
        record = evaluate(ctx, ctx.read.json("reading"))
    except (MotionRebaseError, ValueError) as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("states", record["states"])
    ctx.fact("verdict", "accept")
    return {}


@node(
    "rebase_admit",
    inputs={**_SUBJECT, "reading": "json"},
    params=_PARAMS,
    judge=True,
    version=1,
)
def rebase_admit(ctx: Ctx) -> dict[str, Any]:
    """The reading covers every state, holds the baseline at one and stays in bounds."""

    return _judge(ctx, _first_pass_record)


@node(
    "rebase_record",
    inputs={**_SUBJECT, "reading": "json"},
    params=_PARAMS,
    outputs={"record": "json"},
    version=1,
)
def rebase_record(ctx: Ctx) -> dict[str, Any]:
    """The admitted reading, recorded against the plate it was read from."""

    return {"record": ctx.out.json(_first_pass_record(ctx, ctx.read.json("reading")))}


@node(
    "rebase_verify_plate",
    inputs={**_SUBJECT, "first_pass": "json"},
    params=_PARAMS,
    outputs={"plate": "image/png"},
    version=1,
)
def rebase_verify_plate(ctx: Ctx) -> dict[str, Any]:
    """Every frame drawn already rebased by the first pass, for the residual."""

    frames = _frames(ctx)
    composed = build_motion_rebase_verification_plate(
        frames, _admitted_first_pass(ctx, frames), baseline_state=ctx.params["baseline_state"]
    )
    return {"plate": ctx.out.bytes(composed.png, "image/png")}


@node(
    "rebase_verify_admit",
    inputs={**_SUBJECT, "first_pass": "json", "reading": "json"},
    params=_PARAMS,
    judge=True,
    version=1,
)
def rebase_verify_admit(ctx: Ctx) -> dict[str, Any]:
    """The residual reading, multiplied into the first pass, stays in bounds."""

    return _judge(ctx, _verified_record)


@node(
    "rebase_verify_record",
    inputs={**_SUBJECT, "first_pass": "json", "reading": "json"},
    params=_PARAMS,
    outputs={"record": "json"},
    version=1,
)
def rebase_verify_record(ctx: Ctx) -> dict[str, Any]:
    """The two passes multiplied: each state's final multiplier, recorded."""

    return {"record": ctx.out.json(_verified_record(ctx, ctx.read.json("reading")))}


def add_rebase_steps(
    group: Group,
    *,
    nodes: str,
    display_name: str,
    states: Sequence[str],
    baseline_state: str,
    geometry: Mapping[str, tuple[int, int]],
    atlases: Mapping[str, Any],
) -> dict[str, StepRef]:
    """Write one actor's two rebase passes into ``group``; ``atlases`` maps state to a
    reference to its published atlas."""

    subject = {
        "atlases": dict(atlases),
        "states": list(states),
        "baseline_state": baseline_state,
        "geometry": {state: list(geometry[state]) for state in states},
    }
    answer = group.step("schema", title="The reading's shape", uses=f"{nodes}#rebase_schema")
    plate_ = group.step(
        "plate", title="Lay out every frame", uses=f"{nodes}#rebase_plate", with_=subject
    )
    judge = group.step(
        "judge",
        title="Read each state's scale",
        uses="gnode/structured.generate@1",
        with_={
            "prompt": motion_rebase_prompt(display_name, list(states)),
            "system": JUDGE_SYSTEM_PROMPT,
            "schema": answer.outputs.schema,
            "context": [plate_.outputs.plate],
        },
    )
    group.step(
        "admit",
        title="Hold the reading to the plate",
        uses=f"{nodes}#rebase_admit",
        judges="judge",
        with_={**subject, "reading": judge.outputs.json},
        on_reject={"regenerate": {"max": REBASE_TAKES, "then": "fail"}},
    )
    first_pass = group.step(
        "first_pass",
        title="Record the reading",
        uses=f"{nodes}#rebase_record",
        with_={**subject, "reading": judge.outputs.json},
    )
    verify_plate_ = group.step(
        "verify_plate",
        title="Lay them out rebased",
        uses=f"{nodes}#rebase_verify_plate",
        with_={**subject, "first_pass": first_pass.outputs.record},
    )
    verify = group.step(
        "verify",
        title="Read the residual",
        uses="gnode/structured.generate@1",
        with_={
            "prompt": motion_rebase_verification_prompt(display_name, list(states)),
            "system": JUDGE_SYSTEM_PROMPT,
            "schema": answer.outputs.schema,
            "context": [verify_plate_.outputs.plate],
        },
    )
    group.step(
        "verified",
        title="Hold the residual",
        uses=f"{nodes}#rebase_verify_admit",
        judges="verify",
        with_={**subject, "first_pass": first_pass.outputs.record, "reading": verify.outputs.json},
        on_reject={"regenerate": {"max": REBASE_TAKES, "then": "fail"}},
    )
    record = group.step(
        "record",
        title="Record both passes",
        uses=f"{nodes}#rebase_verify_record",
        with_={**subject, "first_pass": first_pass.outputs.record, "reading": verify.outputs.json},
    )
    return {
        "first_pass": first_pass,
        "record": record,
        "plate": plate_,
        "verify_plate": verify_plate_,
    }


__all__ = [
    "JUDGE_SYSTEM_PROMPT",
    "REBASE_TAKES",
    "add_rebase_steps",
    "rebase_admit",
    "rebase_plate",
    "rebase_record",
    "rebase_schema",
    "rebase_verify_admit",
    "rebase_verify_plate",
    "rebase_verify_record",
]
