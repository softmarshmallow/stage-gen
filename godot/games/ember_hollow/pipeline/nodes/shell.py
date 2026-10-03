"""The screens around the game: the opening's plates and clips, the title, the loading screen.

A plate is held to its layout's pixel gate (true alpha or edge to edge, and the regions
text sits on kept quiet) and drawn again when it fails, then clamped and published with
evidence a reviewer reads. A clip is filmed or adopted from an auditioned take through
one admission (length, rectangle, codec, motion), recorded, and published in the one
codec the host plays, measured again after the encoder. Reviews are evidence, never gates.
"""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from typing import Any, cast

from demo_game_tools.kits.screen_art.layouts import SHELL_LAYOUTS
from demo_game_tools.kits.screen_art.plates import (
    canonicalize_shell_plate,
    shell_plate_evidence,
    validate_shell_plate,
)
from ember_hollow_pipeline.shell.clips import match_title_verdict, shell_clip_record
from ember_hollow_pipeline.shell.nodes import (
    CLIP_PUBLISHED_CODEC,
    CLIP_SOURCE_CODEC,
    SHELL_CLIP_ENCODER,
    SHELL_CLIP_PUBLISHED_KIND,
    SHELL_CLIP_REVIEW_CHECKS,
    SHELL_CLIP_VALIDATION_KIND,
    SHELL_OPENING_ENDING_KIND,
    SHELL_VALIDATION_KIND,
    _parse_review,
    clip_review_prompt,
    plate_review_prompt,
)
from ember_hollow_pipeline.shell.nodes import (
    shell_review_schema as answer_schema,
)
from gnode import Ctx, node
from stage_gen.components.video_clip import (
    CLIP_REVIEW_CELL_WIDTH,
    CLIP_REVIEW_COLUMNS,
    admit_clip_bytes,
    admit_clip_file,
    clip_sample_times,
)
from stage_gen.media import (
    contact_sheet,
    extract_frame_png,
    run_process,
    scratch_clip,
    theora_transcode_args,
)

_PLATE = {"layout": str, "alpha_policy": str, "measured_regions": list}
_CLIP = {"layout": str, "seconds": float}


def _check_plate(ctx: Ctx, data: bytes) -> dict[str, object]:
    return validate_shell_plate(
        data,
        layout=SHELL_LAYOUTS[ctx.params["layout"]],
        alpha_policy=ctx.params["alpha_policy"],
        measured_regions=tuple(ctx.params["measured_regions"]),
    )


@node("admit_shell_plate", inputs={"image": "image"}, params=_PLATE, judge=True, version=1)
def admit_shell_plate(ctx: Ctx) -> dict[str, Any]:
    """The plate fills or cuts out as its policy says and keeps its text regions quiet."""

    try:
        facts = _check_plate(ctx, ctx.read.bytes("image"))
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("admission", facts)
    ctx.fact("verdict", "accept")
    return {}


@node(
    "publish_shell_plate",
    inputs={"raw": "image"},
    params={**_PLATE, "role": str, "screen": str},
    outputs={"image": "image/png", "validation": "json", "evidence": "image/png"},
    version=1,
)
def publish_shell_plate(ctx: Ctx) -> dict[str, Any]:
    """The clamped plate, its measured regions, and the outlined evidence for review."""

    data = ctx.read.bytes("raw")
    record = _check_plate(ctx, data)
    canonical, rewrite = canonicalize_shell_plate(data, alpha_policy=ctx.params["alpha_policy"])
    validation = {
        "schema_version": 1,
        "kind": SHELL_VALIDATION_KIND,
        "role": ctx.params["role"],
        "screen": ctx.params["screen"],
        **record,
        **rewrite,
    }
    return {
        "image": ctx.out.bytes(canonical, "image/png"),
        "validation": ctx.out.json(validation),
        "evidence": ctx.out.bytes(shell_plate_evidence(canonical, record), "image/png"),
    }


@node(
    "shell_review_schema",
    params={"clip": bool},
    outputs={"schema": "json"},
    version=1,
)
def shell_review_schema(ctx: Ctx) -> dict[str, Any]:
    """A review's answer shape: the questions the measurement cannot decide."""

    schema = (
        answer_schema(checks=SHELL_CLIP_REVIEW_CHECKS) if ctx.params["clip"] else answer_schema()
    )
    return {"schema": ctx.out.json(schema)}


@node(
    "shell_review_brief",
    inputs={"record": "json"},
    params={"role": str, "screen": str, "brief": str, "seconds": float, "clip": bool},
    outputs={"brief": "json"},
    version=1,
)
def shell_review_brief(ctx: Ctx) -> dict[str, Any]:
    """What the reviewer is asked, given what the gate already measured."""

    params = ctx.params
    record = cast(dict[str, object], ctx.read.json("record"))
    # The prompts read a role's name, screen, length and authored brief, nothing else.
    authored = SimpleNamespace(prompt=params["brief"])
    role = SimpleNamespace(
        role=params["role"],
        screen=params["screen"],
        seconds=params["seconds"],
        plate=authored,
        clip=authored,
    )
    prompt = (
        clip_review_prompt(cast(Any, role), record)
        if params["clip"]
        else plate_review_prompt(cast(Any, role), record)
    )
    return {"brief": ctx.out.json({"prompt": prompt})}


@node("admit_shell_review", inputs={"review": "json"}, judge=True, version=1)
def admit_shell_review(ctx: Ctx) -> dict[str, Any]:
    """The review names its checks and findings in the shape asked for, or it is asked again."""

    try:
        _parse_review(ctx.read.json("review"))
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("verdict", "accept")
    return {}


@node("shell_review_record", inputs={"review": "json"}, outputs={"verdict": "json"}, version=1)
def shell_review_record(ctx: Ctx) -> dict[str, Any]:
    """The accepted review, as the evidence the manifest names."""

    return {"verdict": ctx.out.json(_parse_review(ctx.read.json("review")))}


# ------------------------------------------------------------------------------- clips


async def _admit(ctx: Ctx, data: bytes) -> dict[str, object]:
    layout = SHELL_LAYOUTS[ctx.params["layout"]]
    return await admit_clip_bytes(
        data,
        expected_seconds=ctx.params["seconds"],
        expected_size=layout.canvas,
        expected_codec=CLIP_SOURCE_CODEC,
        ffmpeg=ctx.tool("ffmpeg").executable,
        ffprobe=ctx.tool("ffprobe").executable,
    )


@node(
    "admit_clip",
    inputs={"clip": "video"},
    params=_CLIP,
    tools=["ffmpeg", "ffprobe"],
    judge=True,
    version=1,
)
async def admit_clip(ctx: Ctx) -> dict[str, Any]:
    """The clip is as long, as large and in the codec asked, and it moves; or it is refilmed."""

    try:
        facts = await _admit(ctx, ctx.read.bytes("clip"))
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("admission", facts)
    ctx.fact("verdict", "accept")
    return {}


@node(
    "adopt_clip",
    inputs={"take": "video?"},
    params={**_CLIP, "path": str, "sha256": str},
    outputs={"clip": "video/mp4"},
    tools=["ffmpeg", "ffprobe"],
    version=1,
)
async def adopt_clip(ctx: Ctx) -> dict[str, Any]:
    """An auditioned shot, picked by eye, admitted exactly as a fresh draw is."""

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
        facts = await _admit(ctx, data)
    except ValueError as error:
        raise ctx.fail(f"the take {path} does not pass the clip admission: {error}") from None
    ctx.fact("adoption", {"adopted_from": path, "adopted_sha256": found, **facts})
    return {"clip": ctx.out.bytes(data, "video/mp4")}


@node(
    "clip_record",
    inputs={"clip": "video"},
    params={**_CLIP, "role": str, "shot_id": str},
    outputs={"validation": "json"},
    tools=["ffmpeg", "ffprobe"],
    version=1,
)
async def clip_record(ctx: Ctx) -> dict[str, Any]:
    """The admission restated over the clip that will be published, as a record."""

    layout = SHELL_LAYOUTS[ctx.params["layout"]]
    facts = await admit_clip_file(
        ctx.inputs["clip"].path,
        expected_seconds=ctx.params["seconds"],
        expected_size=layout.canvas,
        expected_codec=CLIP_SOURCE_CODEC,
        ffmpeg=ctx.tool("ffmpeg").executable,
        ffprobe=ctx.tool("ffprobe").executable,
    )
    record = {
        "schema_version": 1,
        "kind": SHELL_CLIP_VALIDATION_KIND,
        "role": ctx.params["role"],
        "shot_id": ctx.params["shot_id"],
        **shell_clip_record(facts, layout=layout, seconds=ctx.params["seconds"]),
    }
    # In the order it was built: the clip review quotes this record to the reviewer, and
    # a reordered record is a different question.
    data = (json.dumps(record, indent=2) + "\n").encode("utf-8")
    return {"validation": ctx.out.bytes(data, "application/json")}


@node(
    "publish_clip",
    inputs={"clip": "video"},
    params={**_CLIP, "role": str},
    outputs={"clip": "video/ogg", "contact": "image/png", "published": "json"},
    tools=["ffmpeg", "ffprobe", "ffmpeg-theora"],
    version=1,
)
async def publish_clip(ctx: Ctx) -> dict[str, Any]:
    """Transcode into the one codec the host plays, then measure it again.

    The transform is fixed (no crop, trim, scale or filter) and everything the admission
    checked before it is checked again after, so nothing the encoder did can hide.
    """

    layout = SHELL_LAYOUTS[ctx.params["layout"]]
    seconds = ctx.params["seconds"]
    ffmpeg, ffprobe = ctx.tool("ffmpeg").executable, ctx.tool("ffprobe").executable
    theora = ctx.tool("ffmpeg-theora").executable
    version = await run_process(theora, ["-version"], 60.0)
    encoder = next((line.strip() for line in version.stdout.splitlines() if line.strip()), "")
    if not encoder.lower().startswith("ffmpeg version"):
        raise ctx.fail("the theora encoder did not report a recognizable version")
    async with scratch_clip(b"\0", suffix=".ogv") as scratch:
        await run_process(theora, theora_transcode_args(ctx.inputs["clip"].path, scratch), 900.0)
        published = await admit_clip_file(
            scratch,
            expected_seconds=seconds,
            expected_size=layout.canvas,
            expected_codec=CLIP_PUBLISHED_CODEC,
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
        )
        frames = [
            await extract_frame_png(scratch, at_seconds=at, ffmpeg=ffmpeg)
            for at in clip_sample_times(seconds)
        ]
        data = scratch.read_bytes()
    record = {
        "schema_version": 1,
        "kind": SHELL_CLIP_PUBLISHED_KIND,
        "role": ctx.params["role"],
        "encoder": SHELL_CLIP_ENCODER,
        "encoder_version": encoder,
        **shell_clip_record({}, layout=layout, seconds=seconds, published_facts=published),
    }
    sheet = contact_sheet(frames, columns=CLIP_REVIEW_COLUMNS, cell_width=CLIP_REVIEW_CELL_WIDTH)
    return {
        "clip": ctx.out.bytes(data, "video/ogg"),
        "contact": ctx.out.bytes(sheet, "image/png"),
        "published": ctx.out.json(record),
    }


@node(
    "measure_ending",
    inputs={"clip": "video", "backdrop": "image"},
    outputs={"ending": "json"},
    tools=["ffmpeg"],
    version=1,
)
async def measure_ending(ctx: Ctx) -> dict[str, Any]:
    """The opening's last published frame against the title backdrop it claims to end on."""

    last = await extract_frame_png(
        ctx.inputs["clip"].path, from_end=True, ffmpeg=ctx.tool("ffmpeg").executable
    )
    verdict = match_title_verdict(last, ctx.read.bytes("backdrop"))
    return {
        "ending": ctx.out.json({"schema_version": 1, "kind": SHELL_OPENING_ENDING_KIND, **verdict})
    }


@node(
    "publish_typeface",
    inputs={"face": "file"},
    params={"sha256": str},
    outputs={"typeface": "file"},
    version=1,
)
def publish_typeface(ctx: Ctx) -> dict[str, Any]:
    """The authored face, republished so the manifest may bind it."""

    data = ctx.read.bytes("face")
    found = hashlib.sha256(data).hexdigest()
    if found != ctx.params["sha256"]:
        raise ctx.fail(
            f"the typeface does not match its declared sha256: "
            f"declared {ctx.params['sha256']}, found {found}"
        )
    return {"typeface": ctx.out.bytes(data, "application/octet-stream")}


__all__ = [
    "adopt_clip",
    "admit_clip",
    "admit_shell_plate",
    "admit_shell_review",
    "clip_record",
    "measure_ending",
    "publish_clip",
    "publish_shell_plate",
    "publish_typeface",
    "shell_review_brief",
    "shell_review_record",
    "shell_review_schema",
]
