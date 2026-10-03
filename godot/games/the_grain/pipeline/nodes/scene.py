"""A dialogue scene's plans, briefs, judges, finished images and the bundle the host plays.

Each actor's plan is the model's staging locks inside the authored frame; a draft that does
not fit is asked for again. A face's brief is composed from the accepted plan and ends with
the style anchor's clause. Every image is held to its provider canvas (native alpha that is
really there, or chroma that keys) and drawn again when it fails, then finished at the
runtime canvas. The package step reads the scene again from its own files, lays out every
member the bundle binds, and writes ``bundle.json``.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from gnode import Ctx, node
from stage_gen.media import probe_audio, validate_music_payload
from the_grain_pipeline.dialogue_scene.build import (
    canonical_sprite,
    check_scene_image,
    complete_plan,
    expression_brief,
    normalize_backdrop,
)
from the_grain_pipeline.dialogue_scene.identity import canonical_json_bytes
from the_grain_pipeline.dialogue_scene.manifest import dialogue_bundle
from the_grain_pipeline.dialogue_scene.models import MINIMUM_TRACK_SECONDS, DialogueScenePlan
from the_grain_pipeline.dialogue_scene.scene_request import (
    ResolvedDialogueScene,
    read_scene_document,
    resolve_dialogue_scene,
)
from the_grain_pipeline.dialogue_scene.schema import dialogue_plan_json_schema

_FRAME = {"frame": dict}


def _judged(ctx: Ctx, check: Any) -> dict[str, Any]:
    try:
        facts = check()
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("admission", facts)
    ctx.fact("verdict", "accept")
    return {}


def _lay_out(root: Path, files: dict[str, Any]) -> None:
    for key, file in files.items():
        relative = PurePosixPath(key)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"{key!r} is not a relative path inside the scene")
        target = root.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        file.copy_to(target)


@node("plan_schema", outputs={"schema": "json"}, version=1)
def plan_schema(ctx: Ctx) -> dict[str, Any]:
    """The plan answer's shape: the shared staging locks."""

    return {"schema": ctx.out.json(dialogue_plan_json_schema())}


@node("admit_plan", inputs={"draft": "json"}, params=_FRAME, judge=True, version=1)
def admit_plan(ctx: Ctx) -> dict[str, Any]:
    """The draft's staging locks fit inside the actor's authored frame, or it is asked again."""

    return _judged(
        ctx,
        lambda: {"kind": complete_plan(ctx.params["frame"], ctx.read.json("draft")).kind},
    )


@node("plan_record", inputs={"draft": "json"}, params=_FRAME, outputs={"plan": "json"}, version=1)
def plan_record(ctx: Ctx) -> dict[str, Any]:
    """The actor's plan: the accepted staging locks inside the authored frame."""

    plan = complete_plan(ctx.params["frame"], ctx.read.json("draft"))
    return {"plan": ctx.out.json(plan.model_dump(mode="json", exclude_none=True))}


@node(
    "face_brief",
    inputs={"plan": "json", "clauses": "json"},
    params={
        "base": bool,
        "expression_id": str,
        "transparency_mode": ("native", "chroma"),
        "has_identity_plate": bool,
    },
    outputs={"brief": "json"},
    version=1,
)
def face_brief(ctx: Ctx) -> dict[str, Any]:
    """One face's brief, composed from the accepted plan, ending with the style clause."""

    brief = expression_brief(
        DialogueScenePlan.model_validate(ctx.read.json("plan")),
        base=ctx.params["base"],
        expression_id=ctx.params["expression_id"],
        transparency_mode=ctx.params["transparency_mode"],
        has_identity_plate=ctx.params["has_identity_plate"],
    )
    clause = ctx.read.json("clauses")["character_sprite"]
    return {"brief": ctx.out.json({"prompt": f"{brief.rstrip()}\n\n{clause}"})}


@node(
    "admit_scene_image",
    inputs={"image": "image"},
    params={
        "width": int,
        "height": int,
        "alpha": bool,
        "chroma": bool,
        "recipe_contract": str,
    },
    judge=True,
    version=1,
)
def admit_scene_image(ctx: Ctx) -> dict[str, Any]:
    """The provider canvas, native alpha that is really there, chroma that keys."""

    params = ctx.params
    return _judged(
        ctx,
        lambda: check_scene_image(
            ctx.read.bytes("image"),
            width=params["width"],
            height=params["height"],
            alpha=params["alpha"],
            chroma=params["chroma"],
            recipe_contract=params["recipe_contract"],
        ),
    )


@node(
    "sprite",
    inputs={"source": "image"},
    params={"transparency_mode": ("native", "chroma")},
    outputs={"image": "image/png"},
    version=1,
)
def sprite(ctx: Ctx) -> dict[str, Any]:
    """The runtime sprite: native alpha fitted to the canvas, or chroma keyed and cleaned."""

    data = canonical_sprite(
        ctx.read.bytes("source"), transparency_mode=ctx.params["transparency_mode"]
    )
    return {"image": ctx.out.bytes(data, "image/png")}


@node("backdrop", inputs={"raw": "image"}, outputs={"image": "image/png"}, version=1)
def backdrop(ctx: Ctx) -> dict[str, Any]:
    """The provider's opaque backdrop, fitted to the runtime canvas."""

    return {"image": ctx.out.bytes(normalize_backdrop(ctx.read.bytes("raw")), "image/png")}


@node(
    "admit_scene_track",
    inputs={"audio": "audio"},
    tools=["ffprobe"],
    judge=True,
    version=1,
)
async def admit_scene_track(ctx: Ctx) -> dict[str, Any]:
    """A playable MP3 long enough to sit under a scene, or it is composed again."""

    try:
        facts = validate_music_payload(ctx.read.bytes("audio"))
        probe = await probe_audio(
            ctx.inputs["audio"].path, ffprobe=ctx.tool("ffprobe").executable, timeout_seconds=120
        )
        if probe.duration_seconds < MINIMUM_TRACK_SECONDS:
            raise ValueError(
                f"the track is {probe.duration_seconds:.1f}s, under the "
                f"{MINIMUM_TRACK_SECONDS}s floor"
            )
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("payload", {**facts, "duration_seconds": round(probe.duration_seconds, 3)})
    ctx.fact("verdict", "accept")
    return {}


def _scene(ctx: Ctx) -> ResolvedDialogueScene:
    root = ctx.work_path("scene")
    _lay_out(root, dict(ctx.inputs["scene"]))
    return resolve_dialogue_scene(read_scene_document(root), root=root)


@node(
    "scene_package",
    inputs={
        "scene": "file{}",
        "published": "file{}",
        "records": "file{}",
        "plans": "json{}",
        "anchor": "json",
    },
    outputs={"files": "file{}"},
    tools=["ffprobe"],
    version=1,
)
async def scene_package(ctx: Ctx) -> dict[str, Any]:
    """Every member the bundle binds, laid out, and ``bundle.json`` binding them by digest."""

    resolved = _scene(ctx)
    scene_files = dict(ctx.inputs["scene"])
    published = dict(ctx.inputs["published"])
    run = ctx.work_path("run")
    _lay_out(run, {**published, **dict(ctx.inputs["records"])})
    plate = resolved.style_reference
    written: dict[str, bytes] = {
        "request.json": resolved.request_bytes,
        "style-anchor.json": ctx.read.bytes("anchor"),
        **{
            f"characters/{actor.asset_prefix}.json": actor.profile.canonical_bytes
            for actor in resolved.actors
        },
    }
    for scenario in resolved.scenarios:
        slug = scenario.declarations.scenario_id.replace("_", "-")
        written[f"scenarios/{slug}.json"] = scenario.program_bytes
        written[f"scenarios/{slug}.validation.json"] = canonical_json_bytes(
            scenario.admission.model_dump(mode="json")
        )
    plans = ctx.inputs["plans"]
    for actor in resolved.actors:
        if actor.asset_prefix not in plans:
            raise ctx.fail(f"no plan was written for {actor.actor_id}")
        written[f"plans/{actor.asset_prefix}.json"] = plans[actor.asset_prefix].read_bytes()
    for relative, data in written.items():
        target = run / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    _lay_out(run, {"assets/style-plate.png": scene_files[plate.source]})
    bundle = await dialogue_bundle(
        run, tag=resolved.scene_id, ffprobe=ctx.tool("ffprobe").executable
    )
    bound = {
        "request.json",
        bundle.style_reference.path,
        *(asset.path for asset in bundle.assets),
        *(file.path for actor in bundle.actors for file in (actor.character_profile, actor.plan)),
        *(
            file.path
            for scenario in bundle.scenarios
            for file in (scenario.program, scenario.validation)
        ),
    }
    unbound = sorted(set(published) - bound)
    if unbound:
        raise ctx.fail(f"published files the bundle does not bind: {unbound}")
    files: dict[str, Any] = {
        path: published[path]
        if path in published
        else ctx.out.bytes((run / path).read_bytes(), _kind(path))
        for path in sorted(bound)
    }
    files["bundle.json"] = ctx.out.bytes(canonical_json_bytes(bundle) + b"\n", "application/json")
    ctx.fact("files", len(files))
    return {"files": files}


_KINDS = {".png": "image/png", ".mp3": "audio/mpeg", ".json": "application/json"}


def _kind(path: str) -> str:
    return _KINDS.get(PurePosixPath(path).suffix, "application/octet-stream")


__all__ = [
    "admit_plan",
    "admit_scene_image",
    "admit_scene_track",
    "backdrop",
    "face_brief",
    "plan_record",
    "plan_schema",
    "scene_package",
    "sprite",
]
