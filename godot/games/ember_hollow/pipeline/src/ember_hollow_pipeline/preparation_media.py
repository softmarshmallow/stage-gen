"""Deterministic seasonal alignment, review rasters and biome gate policy for Ember Hollow."""

from __future__ import annotations

import math
from collections.abc import Sequence
from io import BytesIO
from typing import Final, TypedDict

from PIL import Image, ImageDraw

from ember_hollow_pipeline import gates
from ember_hollow_pipeline import manifest as manifest_module
from ember_hollow_pipeline.models import (
    Biome,
)

#: A season look is measured against its summer twin as FRACTIONS of their
#: canvases (a summer sprite cut to 512 px and a paintover drawn at 1024 are
#: the same drawing at two pixel scales; the first winter run refused sixteen
#: honest looks on that arithmetic). Scale and placement are then corrected,
#: not refused: the look is resized to the summer's painted width and its
#: foot set on the summer's, on a canvas the summer's size, so the state's
#: ruler and anchor hold by construction. What cannot be corrected is the
#: shape: a look whose width-to-height changed past this band is a different
#: drawing. A cap adds height and not width, so the band leans below one.
LOOK_ASPECT_RATIO: Final = (0.72, 1.2)


def _look_drift(summer: bytes, candidate: bytes) -> tuple[dict[str, float], list[str]]:
    """Measure a season look against its summer sprite; the reasons refuse it."""

    a = manifest_module.measure_sprite(summer)
    b = manifest_module.measure_sprite(candidate)
    box_a = manifest_module.alpha_bbox(summer) or (0, 0, 1, 1)
    box_b = manifest_module.alpha_bbox(candidate) or (0, 0, 1, 1)
    width_a = (box_a[2] - box_a[0]) / max(1.0, float(a["width_px"]))
    width_b = (box_b[2] - box_b[0]) / max(1.0, float(b["width_px"]))
    height_a = float(a["bbox_height_px"]) / max(1.0, float(a["height_px"]))
    height_b = float(b["bbox_height_px"]) / max(1.0, float(b["height_px"]))
    width_ratio = width_b / max(1e-6, width_a)
    height_ratio = height_b / max(1e-6, height_a)
    aspect_ratio = width_ratio / max(1e-6, height_ratio)
    contact_shift = abs(
        float(b["ground_contact_y_normalized"] or 0.0)
        - float(a["ground_contact_y_normalized"] or 0.0)
    )
    drift = {
        "width_ratio": round(width_ratio, 4),
        "height_ratio": round(height_ratio, 4),
        "aspect_ratio": round(aspect_ratio, 4),
        "contact_shift": round(contact_shift, 4),
    }
    reasons: list[str] = []
    if not b.get("painted"):
        reasons.append("the look is an empty canvas")
    elif not LOOK_ASPECT_RATIO[0] <= aspect_ratio <= LOOK_ASPECT_RATIO[1]:
        reasons.append(
            f"the look's width-to-height is {aspect_ratio:.2f} times the summer"
            " sprite's; it must stay "
            f"within [{LOOK_ASPECT_RATIO[0]}, {LOOK_ASPECT_RATIO[1]}] to be the same drawing"
        )
    return drift, reasons


def _normalise_look(summer: bytes, candidate: bytes) -> tuple[bytes, dict[str, float]]:
    """Put a season look on its summer twin's canvas at the summer's scale.

    Resized so its painted width equals the summer's, then set with its
    painted bottom-centre on the summer's. A cap rises from there: when it
    would pass the canvas top, the canvas grows upward by that much (the
    manifest reads the look's own height and contact row, so a taller
    canvas costs nothing). Returns the canvas and what was done.
    """

    with Image.open(BytesIO(summer)) as opened:
        canvas_w, canvas_h = opened.size
    box_a = manifest_module.alpha_bbox(summer)
    box_b = manifest_module.alpha_bbox(candidate)
    with Image.open(BytesIO(candidate)) as opened:
        look = opened.convert("RGBA")
    if box_a is None or box_b is None:
        return candidate, {"scale": 1.0, "grown_top_px": 0}
    scale = (box_a[2] - box_a[0]) / max(1, box_b[2] - box_b[0])
    resized = look.resize(
        (max(1, round(look.width * scale)), max(1, round(look.height * scale))),
        Image.Resampling.LANCZOS,
    )
    left = round(box_b[0] * scale)
    right = round(box_b[2] * scale)
    top = round(box_b[1] * scale)
    bottom = round(box_b[3] * scale)
    target_centre = (box_a[0] + box_a[2]) / 2.0
    offset_x = round(target_centre - (left + right) / 2.0)
    offset_y = round(box_a[3] - bottom)
    grow = max(0, -(offset_y + top))
    out = Image.new("RGBA", (canvas_w, canvas_h + grow), (0, 0, 0, 0))
    offset_y += grow
    # Crop the source to what lands on the canvas: a look wider than the
    # summer's padding is clipped at the sides, never at the top.
    src_x = max(0, -offset_x)
    src_y = max(0, -offset_y)
    dst_x = max(0, offset_x)
    dst_y = max(0, offset_y)
    width = min(resized.width - src_x, out.width - dst_x)
    height = min(resized.height - src_y, out.height - dst_y)
    if width > 0 and height > 0:
        out.alpha_composite(
            resized.crop((src_x, src_y, src_x + width, src_y + height)), dest=(dst_x, dst_y)
        )
    buffer = BytesIO()
    out.save(buffer, format="PNG")
    return buffer.getvalue(), {"scale": round(scale, 4), "grown_top_px": grow}


def _jpeg(image: Image.Image, quality: int = 88) -> bytes:
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def plate_busyness_max(biome: Biome) -> float:
    """A fabric plate is judged against the reference's own busyness, a field
    against the speckle limit (gates.FABRIC_BUSYNESS_MAX, GROUND_BUSYNESS_MAX)."""

    return gates.FABRIC_BUSYNESS_MAX if biome.material == "fabric" else gates.GROUND_BUSYNESS_MAX


class PlateGateBands(TypedDict, total=False):
    """The bands ``gates.gate_ground_texture`` takes beyond the canvas and texel size."""

    busyness_max: float
    luma_range: tuple[float, float]


def plate_gate_kwargs(biome: Biome) -> PlateGateBands:
    """The plate gate's bands for this biome's material: a fabric is allowed
    the reference's busyness and arrives darker (gates.FABRIC_LUMA_RANGE)."""

    kwargs: PlateGateBands = {"busyness_max": plate_busyness_max(biome)}
    if biome.material == "fabric":
        kwargs["luma_range"] = gates.FABRIC_LUMA_RANGE
    return kwargs


def _anchor_overlay(
    sprite: bytes,
    *,
    anchor: tuple[float, float],
    radius_meters: float,
    px_per_meter: float,
    pitch_degrees: float,
) -> bytes:
    """Draw the prop standing on a metre grid with its anchor and footprint marked.

    This is what the placement agent actually looks at. The grid is squashed by
    the cosine of the camera pitch, so the ellipse the agent sees is the ellipse
    the runtime will draw, and "is the footprint under the object" becomes a
    question about a picture instead of about two numbers.
    """

    with Image.open(BytesIO(sprite)) as opened:
        card = opened.convert("RGBA")
    width, height = card.size
    squash = max(0.15, math.cos(math.radians(pitch_degrees)))
    plate = Image.new("RGBA", (width, height), (26, 27, 31, 255))
    draw = ImageDraw.Draw(plate)

    anchor_px = (anchor[0] * width, anchor[1] * height)
    step = max(8.0, px_per_meter)
    grid = (70, 74, 82, 255)
    horizon = int(anchor_px[1])
    for index in range(-12, 13):
        offset = index * step
        x = int(anchor_px[0] + offset)
        draw.line([(x, 0), (x, height)], fill=grid, width=1)
        y = int(anchor_px[1] + offset * squash)
        if 0 <= y < height:
            draw.line([(0, y), (width, y)], fill=grid, width=1)
    del horizon

    plate.alpha_composite(card, (0, 0))

    radius_px = max(3.0, radius_meters * px_per_meter)
    marker = Image.new("RGBA", plate.size, (0, 0, 0, 0))
    mark = ImageDraw.Draw(marker)
    mark.ellipse(
        [
            anchor_px[0] - radius_px,
            anchor_px[1] - radius_px * squash,
            anchor_px[0] + radius_px,
            anchor_px[1] + radius_px * squash,
        ],
        outline=(90, 226, 150, 255),
        width=max(2, int(width / 220)),
    )
    arm = max(6.0, radius_px * 0.5)
    mark.line(
        [(anchor_px[0] - arm, anchor_px[1]), (anchor_px[0] + arm, anchor_px[1])],
        fill=(90, 226, 150, 255),
        width=max(2, int(width / 260)),
    )
    mark.line(
        [(anchor_px[0], anchor_px[1] - arm), (anchor_px[0], anchor_px[1] + arm)],
        fill=(90, 226, 150, 255),
        width=max(2, int(width / 260)),
    )
    plate.alpha_composite(marker, (0, 0))
    return _jpeg(plate)


def _contact_sheet(assets: Sequence[tuple[str, bytes]], columns: int = 4, cell: int = 384) -> bytes:
    """One labelled grid of every asset in a family, at equal cell size.

    The reviewer is asked about the set, so the set has to be one picture. Cells
    are equal-sized and each asset is fitted inside its own cell, which means the
    sheet answers questions about pitch, style and clean edges but deliberately
    not about relative scale -- the gallery view in the viewer answers that one,
    at true scale, where it can actually be seen.
    """

    if not assets:
        assets = [("nothing published", b"")]
    rows = (len(assets) + columns - 1) // columns
    label_h = 26
    sheet = Image.new("RGBA", (columns * cell, rows * (cell + label_h)), (22, 23, 27, 255))
    draw = ImageDraw.Draw(sheet)
    for index, (label, data) in enumerate(assets):
        column = index % columns
        row = index // columns
        x0 = column * cell
        y0 = row * (cell + label_h)
        draw.rectangle([x0, y0, x0 + cell - 1, y0 + cell + label_h - 1], outline=(60, 63, 70, 255))
        if data:
            with Image.open(BytesIO(data)) as opened:
                art = opened.convert("RGBA")
            art.thumbnail((cell - 16, cell - 16), Image.Resampling.LANCZOS)
            sheet.alpha_composite(art, (x0 + (cell - art.width) // 2, y0 + (cell - art.height) - 8))
        draw.text((x0 + 8, y0 + cell + 6), f"{index + 1}. {label}", fill=(226, 222, 214, 255))
    buffer = BytesIO()
    sheet.convert("RGB").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
