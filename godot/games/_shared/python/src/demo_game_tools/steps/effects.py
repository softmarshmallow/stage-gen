"""Screen effects: the cut-in's frame and portraits, and the ground-dust atlas.

A cut-in frame is painted (or drawn procedurally) and admitted; each portrait is painted from
its references and, when it has one, the drawn subject it copies, then placed inside the
frame's band by an agent that renders candidate placements and looks at them. Every plate is
canonicalized (its transparent exterior cleared, nothing else rewritten) with evidence a
reviewer judges; the review is recorded, never a gate. The dust atlas is painted, admitted by
the gate that measures its four clouds, and canonicalized.
"""

from __future__ import annotations

import base64
import io
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

from PIL import Image

from demo_game_tools.kits.effects_art.cut_in import (
    CUT_IN_FRAME,
    CUT_IN_PORTRAIT,
    admit_cut_in_placement,
    compose_hold_frame,
    cut_in_evidence,
    cut_in_plate_contract,
    draw_procedural_frame,
    mask_reveal_facts,
    placement_transform,
    validate_frame_plate,
    validate_portrait_plate,
)
from demo_game_tools.kits.effects_art.cut_in import canonicalize_plate as clear_plate_exterior
from demo_game_tools.kits.effects_art.directions import (
    CUT_IN_PLATES_BY_ROLE,
    FX_CUT_IN_PLACE_MAX_STEPS,
    PLACE_SYSTEM,
    PLACEMENT_PARAMETERS,
    REVIEW_SYSTEM,
    START_SCALE,
    cut_in_review_prompt,
    derive_sprite_dust_validation,
    dust_content_task,
    frame_content_task,
    fx_cut_in_place_schema,
    fx_cut_in_review_schema,
    mask_facts,
    parse_placement,
    place_content_task,
    portrait_content_task,
    render_data_url,
    subject_content_task,
    validation_version_for,
)
from demo_game_tools.kits.effects_art.models import (
    CutInPortraitSubject,
    EffectArtwork,
)
from demo_game_tools.kits.effects_art.sprite import SPRITE_CANVAS, validate_dust_atlas
from gnode import Ctx, Group, StepRef, Tool, ToolInvocationError, ToolResult, node
from stage_gen.canonical import content_sha256

#: Draws a plate gets before the run stops on it.
PLATE_TAKES = 6
REVIEW_MAX_TOKENS = 1800


def _png(data: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


@node("draw_frame", outputs={"image": "image/png"}, version=1)
def draw_frame(ctx: Ctx) -> dict[str, Any]:
    """The procedural torn-strip frame: white fill, black rim."""

    return {"image": ctx.out.bytes(draw_procedural_frame(), "image/png")}


@node(
    "admit_plate",
    inputs={"image": "image"},
    params={"role": ("frame", "portrait")},
    judge=True,
    version=1,
)
def admit_plate(ctx: Ctx) -> dict[str, Any]:
    """A frame or portrait plate the cut-in's pixel gate accepts, or it is drawn again."""

    validate = validate_frame_plate if ctx.params["role"] == "frame" else validate_portrait_plate
    try:
        facts = validate(ctx.read.bytes("image"))
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("admission", facts)
    ctx.fact("verdict", "accept")
    return {}


@node(
    "place_portrait",
    inputs={"portrait": "image", "frame": "image"},
    params={"instructions": str},
    outputs={"placement": "json"},
    calls={"agent.turn": FX_CUT_IN_PLACE_MAX_STEPS},
    version=1,
)
async def place_portrait(ctx: Ctx) -> dict[str, Any]:
    """Try placements with the render tool, judge them by eye, and submit one."""

    raw, frame = ctx.read.bytes("portrait"), ctx.read.bytes("frame")
    portrait_sha256, frame_sha256 = content_sha256(raw), content_sha256(frame)
    with Image.open(io.BytesIO(frame)) as opened:
        reveal = mask_reveal_facts(opened.convert("RGBA").getchannel("A"))
    centre_x, centre_y = cast(list[float], reveal["centroid"])
    start = {"scale": START_SCALE, "x": round(centre_x, 4), "y": round(centre_y, 4)}

    def render(arguments: Mapping[str, object]) -> ToolResult:
        try:
            scale, x, y = placement_transform(arguments)
        except ValueError as error:
            raise ToolInvocationError(str(error)) from None
        composed = compose_hold_frame(frame, raw, placement={"scale": scale, "x": x, "y": y})
        return ToolResult(
            text=f"Rendered the composition at scale={scale:g}, x={x:g}, y={y:g}.",
            images=(render_data_url(composed),),
        )

    placed: dict[str, object] = {}

    def check(value: object) -> None:
        placed.clear()
        placed.update(
            admit_cut_in_placement(
                parse_placement(value), portrait_sha256=portrait_sha256, frame_sha256=frame_sha256
            )
        )

    starting = compose_hold_frame(frame, raw, placement=start)
    agent = ctx.agent(
        system=(
            f"{PLACE_SYSTEM} Image 1 is the portrait plate (its transparent exterior may "
            "render as flat black or white). Image 2 is the frame plate. Image 3 is the "
            f"composition at the starting placement scale={start['scale']:g}, "
            f"x={start['x']:g}, y={start['y']:g}. Units: scale is the portrait's display "
            "height as a fraction of the frame height; x and y are the portrait canvas "
            "centre in frame-canvas units (0-1 inside the canvas; the centre may sit "
            f"outside it). {mask_facts(reveal)}"
        ),
        tools=(
            Tool(
                name="render_with_placement",
                description=(
                    "Render the cut-in hold frame with the portrait at the given placement "
                    "and return the picture to look at."
                ),
                parameters=PLACEMENT_PARAMETERS,
                handler=render,
            ),
        ),
    )
    await agent.run(
        ctx.params["instructions"],
        max_steps=FX_CUT_IN_PLACE_MAX_STEPS,
        images=[_png(raw), _png(frame), render_data_url(starting)],
        submit=fx_cut_in_place_schema(),
        check=check,
    )
    return {"placement": ctx.out.json(dict(placed))}


@node(
    "canonicalize_plate",
    inputs={
        "raw": "image",
        "frame": "image?",
        "frame_record": "json?",
        "placement": "json?",
    },
    params={
        "role": ("frame", "portrait"),
        "portrait_id": {"type": ["string", "null"], "default": None},
    },
    outputs={"image": "image/png", "validation": "json", "evidence": "image/png"},
    version=1,
)
def canonicalize_plate(ctx: Ctx) -> dict[str, Any]:
    """Clear the plate's transparent exterior; a portrait is composed at its placement."""

    raw = ctx.read.bytes("raw")
    plate = CUT_IN_PLATES_BY_ROLE[ctx.params["role"]]
    placement: dict[str, object] | None = None
    frame: bytes | None = None
    frame_record: dict[str, Any] | None = None
    if plate.role == "portrait":
        if not {"frame", "frame_record", "placement"} <= set(ctx.inputs):
            raise ctx.fail("a portrait needs the frame's plate and record and its placement")
        frame = ctx.read.bytes("frame")
        frame_record = ctx.read.json("frame_record")
        record = ctx.read.json("placement")
        placement = admit_cut_in_placement(
            record, portrait_sha256=content_sha256(raw), frame_sha256=content_sha256(frame)
        )
        for key in ("portrait_sha256", "frame_sha256"):
            if record.get(key) != placement[key]:
                raise ctx.fail("the placement was judged over other plates")
    canonical, facts = clear_plate_exterior(raw, plate, placement=placement)
    if frame_record is not None:
        facts["frame_geometry"] = dict(frame_record["geometry"])
    validation = {
        "schema_version": 1,
        "kind": validation_version_for(plate.role),
        "plate": plate.role,
        "portrait_id": ctx.params["portrait_id"],
        "geometry": cut_in_plate_contract(facts),
        "facts": {"source": facts["source"], "canonical": facts["canonical"]},
        "pixel_rewrite": facts["pixel_rewrite"],
    }
    return {
        "image": ctx.out.bytes(canonical, "image/png"),
        "validation": ctx.out.json(validation),
        "evidence": ctx.out.bytes(cut_in_evidence(canonical, facts, frame_data=frame), "image/png"),
    }


@node("review_schema", outputs={"schema": "json"}, version=1)
def review_schema(ctx: Ctx) -> dict[str, Any]:
    """What a cut-in review answers: the questions the pixel gate cannot decide."""

    return {"schema": ctx.out.json(fx_cut_in_review_schema())}


@node("admit_dust", inputs={"image": "image"}, judge=True, version=1)
def admit_dust(ctx: Ctx) -> dict[str, Any]:
    """Four solid, separable clouds, or the atlas is drawn again."""

    try:
        facts = validate_dust_atlas(ctx.read.bytes("image"))
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("admission", facts)
    ctx.fact("verdict", "accept")
    return {}


@node(
    "canonicalize_dust",
    inputs={"raw": "image"},
    outputs={"image": "image/png", "validation": "json"},
    version=1,
)
def canonicalize_dust(ctx: Ctx) -> dict[str, Any]:
    """Clear the exterior, lift the body opaque and erase the specks the gate measured."""

    canonical, record, _facts = derive_sprite_dust_validation(ctx.read.bytes("raw"))
    return {"image": ctx.out.bytes(canonical, "image/png"), "validation": ctx.out.json(record)}


def _paint(group: Group, *, prompt: str, pictures: Sequence[Any], size: tuple[int, int]) -> StepRef:
    """A transparent painting: an edit of its first picture when it has any."""

    with_: dict[str, Any] = {
        "prompt": prompt,
        "size": f"{size[0]}x{size[1]}",
        "background": "transparent",
    }
    if pictures:
        with_["image"] = pictures[0]
        with_["references"] = list(pictures[1:])
    return group.step(
        "generate",
        title="Paint the plate",
        uses="gnode/image.edit@1" if pictures else "gnode/image.generate@1",
        with_=with_,
        requires=["transparent_background"],
        view=True,
    )


def _review(group: Group, *, nodes: str, prompt: str, pictures: Sequence[Any]) -> StepRef:
    answer = group.step("review_schema", title="The review's shape", uses=f"{nodes}#review_schema")
    return group.step(
        "review",
        title="Review the plate",
        uses="gnode/structured.generate@1",
        with_={
            "prompt": prompt,
            "system": REVIEW_SYSTEM,
            "schema": answer.outputs.schema,
            "context": list(pictures),
            "max_tokens": REVIEW_MAX_TOKENS,
        },
    )


def add_cut_in_steps(
    frame_group: Group,
    portrait_group: Callable[[str], Group],
    *,
    nodes: str,
    fx: EffectArtwork,
    style_prompt: Callable[[str], str],
    reference_path: Callable[[str], str],
    subject_image: Callable[[CutInPortraitSubject], Any] | None = None,
) -> dict[str, dict[str, StepRef]]:
    """Write the frame into ``frame_group`` and each portrait into ``portrait_group(id)``.

    ``reference_path`` turns an authored reference id into a project path;
    ``subject_image`` turns a portrait's drawn subject into a reference to its picture.
    """

    if fx.cut_in is None:
        return {}
    sources = {entry.reference_id: entry.source for entry in fx.references}

    def authored(reference_ids: Sequence[str]) -> list[str]:
        return [reference_path(sources[reference_id]) for reference_id in reference_ids]

    steps: dict[str, dict[str, StepRef]] = {}
    frame = fx.cut_in.frame
    if frame.mode == "generated_v1":
        frame_raw = _paint(
            frame_group,
            prompt=style_prompt(frame_content_task(frame.prompt or "", frame.shape)),
            pictures=authored(frame.reference_ids),
            size=CUT_IN_FRAME.canvas,
        )
        frame_group.step(
            "admit",
            title="Admit the frame",
            uses=f"{nodes}#admit_plate",
            judges="generate",
            with_={"image": frame_raw.outputs.image, "role": "frame"},
            on_reject={"regenerate": {"max": PLATE_TAKES, "then": "fail"}},
        )
    else:
        frame_raw = frame_group.step("draw", title="Draw the frame", uses=f"{nodes}#draw_frame")
    frame_plate = frame_group.step(
        "canonicalize",
        title="Clear the frame's exterior",
        uses=f"{nodes}#canonicalize_plate",
        with_={"raw": frame_raw.outputs.image, "role": "frame"},
        view=True,
    )
    steps["frame"] = {"plate": frame_plate}
    if frame.mode == "generated_v1":
        steps["frame"]["review"] = _review(
            frame_group,
            nodes=nodes,
            prompt=cut_in_review_prompt(CUT_IN_FRAME, frame.prompt or "", frame.shape),
            pictures=[frame_plate.outputs.evidence, *authored(frame.reference_ids)],
        )
    for portrait in fx.cut_in.portraits:
        group = portrait_group(portrait.portrait_id)
        subject = portrait.subject
        if subject is not None and subject_image is None:
            raise ValueError(
                f"cut_in portrait {portrait.portrait_id} takes its identity from the "
                f"{subject.actor_id!r} {subject.kind} plate, which this game does not draw"
            )
        drawn = [] if subject is None else [cast(Callable[..., Any], subject_image)(subject)]
        raw = _paint(
            group,
            prompt=style_prompt(
                portrait_content_task(portrait.prompt)
                if subject is None
                else subject_content_task(portrait.prompt)
            ),
            pictures=[*drawn, *authored(portrait.reference_ids)],
            size=CUT_IN_PORTRAIT.canvas,
        )
        group.step(
            "admit",
            title="Admit the portrait",
            uses=f"{nodes}#admit_plate",
            judges="generate",
            with_={"image": raw.outputs.image, "role": "portrait"},
            on_reject={"regenerate": {"max": PLATE_TAKES, "then": "fail"}},
        )
        placed = group.step(
            "place",
            title="Place it in the frame",
            uses=f"{nodes}#place_portrait",
            with_={
                "portrait": raw.outputs.image,
                "frame": frame_plate.outputs.image,
                "instructions": place_content_task(
                    portrait.portrait_id, portrait.prompt, subject=subject
                ),
            },
        )
        plate = group.step(
            "canonicalize",
            title="Compose it in the frame",
            uses=f"{nodes}#canonicalize_plate",
            with_={
                "raw": raw.outputs.image,
                "frame": frame_plate.outputs.image,
                "frame_record": frame_plate.outputs.validation,
                "placement": placed.outputs.placement,
                "role": "portrait",
                "portrait_id": portrait.portrait_id,
            },
            view=True,
        )
        review = _review(
            group,
            nodes=nodes,
            prompt=cut_in_review_prompt(CUT_IN_PORTRAIT, portrait.prompt, subject=subject),
            pictures=[plate.outputs.evidence, *drawn, *authored(portrait.reference_ids)],
        )
        steps[portrait.portrait_id] = {"plate": plate, "place": placed, "review": review}
    return steps


def add_dust_steps(
    group: Group,
    *,
    nodes: str,
    fx: EffectArtwork,
    style_prompt: Callable[[str], str],
    reference_path: Callable[[str], str],
) -> dict[str, StepRef] | None:
    """Write the dust atlas's paint, gate and canonicalization into ``group``."""

    dust = None if fx.sprite is None else fx.sprite.dust
    if dust is None:
        return None
    sources = {entry.reference_id: entry.source for entry in fx.references}
    raw = _paint(
        group,
        prompt=style_prompt(dust_content_task(dust.prompt)),
        pictures=[reference_path(sources[reference_id]) for reference_id in dust.reference_ids],
        size=SPRITE_CANVAS,
    )
    group.step(
        "admit",
        title="Admit the atlas",
        uses=f"{nodes}#admit_dust",
        judges="generate",
        with_={"image": raw.outputs.image},
        on_reject={"regenerate": {"max": PLATE_TAKES, "then": "fail"}},
    )
    atlas = group.step(
        "canonicalize",
        title="Lift and clean the atlas",
        uses=f"{nodes}#canonicalize_dust",
        with_={"raw": raw.outputs.image},
        view=True,
    )
    return {"generate": raw, "atlas": atlas}


__all__ = [
    "PLATE_TAKES",
    "add_cut_in_steps",
    "add_dust_steps",
    "admit_dust",
    "admit_plate",
    "canonicalize_dust",
    "canonicalize_plate",
    "draw_frame",
    "place_portrait",
    "review_schema",
]
