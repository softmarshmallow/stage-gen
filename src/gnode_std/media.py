"""Bodies of the free standard node types: local, deterministic picture and file work."""

from __future__ import annotations

import io
import json
from typing import Any

from PIL import Image, ImageOps

from gnode import Ctx, NodeFailure

#: The largest picture a standard node makes; past it a layer is not a texture but a mistake.
MAX_EDGE_PX = 16_384


def _picture(ctx: Ctx, name: str) -> Image.Image:
    picture = ctx.read.image(name)
    if not isinstance(picture, Image.Image):
        raise NodeFailure(f"{name} did not read as a picture")
    return picture if picture.mode == "RGBA" else picture.convert("RGBA")


def _png(picture: Image.Image) -> bytes:
    buffer = io.BytesIO()
    picture.save(buffer, format="PNG")
    return buffer.getvalue()


def mirror_repeat(ctx: Ctx) -> dict[str, Any]:
    """Reflect a picture onto itself along x, y or both, so its edges repeat exactly."""

    picture = _picture(ctx, "image")
    axis = ctx.params["axis"]
    if "x" in axis:
        if picture.width * 2 > MAX_EDGE_PX:
            raise NodeFailure(f"mirroring {picture.width} px on x exceeds {MAX_EDGE_PX} px")
        wide = Image.new("RGBA", (picture.width * 2, picture.height))
        wide.paste(picture, (0, 0))
        wide.paste(ImageOps.mirror(picture), (picture.width, 0))
        picture = wide
    if "y" in axis:
        if picture.height * 2 > MAX_EDGE_PX:
            raise NodeFailure(f"mirroring {picture.height} px on y exceeds {MAX_EDGE_PX} px")
        tall = Image.new("RGBA", (picture.width, picture.height * 2))
        tall.paste(picture, (0, 0))
        tall.paste(ImageOps.flip(picture), (0, picture.height))
        picture = tall
    return {"image": ctx.out.bytes(_png(picture), "image/png")}


def check_alpha(ctx: Ctx) -> dict[str, Any]:
    """Judge whether a picture is transparent where it should be, or fully opaque."""

    alpha = _picture(ctx, "image").getchannel("A")
    low, high = alpha.getextrema()
    transparent = low == 0
    ctx.fact("alpha_min", low)
    ctx.fact("alpha_max", high)
    wanted = ctx.params["expect"]
    accepted = transparent if wanted == "transparent" else low == 255
    ctx.fact("verdict", "accept" if accepted else "reject")
    return {}


def check_size(ctx: Ctx) -> dict[str, Any]:
    """Judge a picture's size against the width and height asked for."""

    picture = _picture(ctx, "image")
    ctx.fact("width", picture.width)
    ctx.fact("height", picture.height)
    width, height = ctx.params.get("width"), ctx.params.get("height")
    accepted = (width is None or picture.width == width) and (
        height is None or picture.height == height
    )
    ctx.fact("verdict", "accept" if accepted else "reject")
    return {}


def resize(ctx: Ctx) -> dict[str, Any]:
    """Scale a picture to fit: by its longest side, or to a width and height."""

    picture = _picture(ctx, "image")
    longest = ctx.params.get("longest_side")
    width, height = ctx.params.get("width"), ctx.params.get("height")
    if longest is not None:
        scale = longest / max(picture.size)
        size = (max(1, round(picture.width * scale)), max(1, round(picture.height * scale)))
    elif width is not None and height is not None:
        size = (width, height)
    else:
        raise NodeFailure("resize takes longest_side, or width and height")
    resized = picture.resize(size, Image.Resampling.LANCZOS)
    return {"image": ctx.out.bytes(_png(resized), "image/png")}


def crop(ctx: Ctx) -> dict[str, Any]:
    """Cut a box out of a picture: ``box`` as [x0, y0, x1, y1] from 0 to 1, padded."""

    picture = _picture(ctx, "image")
    box = ctx.params.get("box")
    if box is None and "region" in ctx.inputs and ctx.inputs["region"] is not None:
        marks = ctx.read.annotations("region").get("annotations", [])
        boxes = [mark["box"] for mark in marks if mark.get("shape") == "box"]
        if not boxes:
            raise NodeFailure("the region has no box to crop to")
        box = boxes[0]
    if box is None or len(box) != 4:
        raise NodeFailure("crop takes box: [x0, y0, x1, y1], or a region with a box mark")
    pad = float(ctx.params.get("padding", 0.0))
    x0, y0, x1, y1 = (float(value) for value in box)
    dx, dy = (x1 - x0) * pad, (y1 - y0) * pad
    left = max(0, round((x0 - dx) * picture.width))
    top = max(0, round((y0 - dy) * picture.height))
    right = min(picture.width, round((x1 + dx) * picture.width))
    bottom = min(picture.height, round((y1 + dy) * picture.height))
    if right <= left or bottom <= top:
        raise NodeFailure(f"the box {box} is empty on a {picture.width}x{picture.height} picture")
    cut = picture.crop((left, top, right, bottom))
    ctx.fact("box_px", [left, top, right, bottom])
    return {"image": ctx.out.bytes(_png(cut), "image/png")}


def pad(ctx: Ctx) -> dict[str, Any]:
    """Centre a picture on a transparent canvas of the asked size."""

    picture = _picture(ctx, "image")
    width, height = ctx.params["width"], ctx.params["height"]
    if picture.width > width or picture.height > height:
        raise NodeFailure(
            f"a {picture.width}x{picture.height} picture does not fit {width}x{height}"
        )
    canvas = Image.new("RGBA", (width, height))
    canvas.paste(picture, ((width - picture.width) // 2, (height - picture.height) // 2))
    return {"image": ctx.out.bytes(_png(canvas), "image/png")}


def json_merge(ctx: Ctx) -> dict[str, Any]:
    """Merge JSON objects in order; a later key wins."""

    merged: dict[str, Any] = {}
    for document in ctx.inputs["documents"]:
        value = json.loads(document.read_bytes())
        if not isinstance(value, dict):
            raise NodeFailure("json.merge merges objects")
        merged.update(value)
    return {"json": ctx.out.json(merged)}


def files_copy(ctx: Ctx) -> dict[str, Any]:
    """Pass one file through unchanged: a stable name for something other steps made."""

    file = ctx.inputs["file"]
    return {"file": ctx.out.bytes(file.read_bytes(), file.kind)}


BODIES = {
    "image.mirror_repeat": mirror_repeat,
    "image.check_alpha": check_alpha,
    "image.check_size": check_size,
    "image.resize": resize,
    "image.crop": crop,
    "image.pad": pad,
    "json.merge": json_merge,
    "files.copy": files_copy,
}
