"""Placeholder oblique-survival art, drawn locally, and the manifest it fills.

A dry run writes node stubs at the declared ports, never artifacts, so nothing
in a rehearsal can be loaded by a consumer. This writer draws a whole package's
worth of flat placeholder shapes with PIL and then builds the real manifest over
them, which is how a consumer -- the Godot host, the CLI's own integration test
-- is exercised end to end without a provider call.

It deliberately mimics the real pipeline's awkward part: each sprite is drawn to
fill its own canvas, so every prop has a different ``px_per_meter`` and the
manifest's scale arithmetic is exercised for real.

It lives under ``tests/`` rather than in the recipe because what it produces is
a fixture, not a run: a directory that looks like generated work but is not, and
it must never be listed as one. Nothing here is evidence about generated art.
"""

from __future__ import annotations

import math
from io import BytesIO
from pathlib import Path
from typing import Any, Final

from PIL import Image, ImageDraw, ImageFilter

from stage_gen.recipes.oblique_survival.layout import Layout
from stage_gen.recipes.oblique_survival.manifest import (
    FIXTURE_CANVAS,
    FIXTURE_STRIP,
    MOTION_BOTTOM_GUTTER_PX,
    Manifest,
    alpha_bbox,
    biome_splat_ref,
    build_manifest,
    concept_ref,
    decal_ref,
    dust_ref,
    fire_ref,
    forage_ref,
    ground_ref,
    icons_ref,
    item_ref,
    layout_ref,
    macro_ref,
    manifest_bytes,
    prop_look_ref,
    prop_ref,
    road_ref,
    splat_ref,
    state_ref,
    water_ref,
    weather_ref,
)
from stage_gen.recipes.oblique_survival.models import Package

_INK = (36, 30, 28, 255)


def _fixture_sprite(kind: str, *, height_fraction: float = 0.86, seed: int = 0) -> bytes:
    size = FIXTURE_CANVAS
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    bottom = int(size * 0.94)
    top = bottom - int(size * height_fraction)
    mid = size // 2
    span = bottom - top

    if kind == "tree":
        trunk = span // 12
        draw.rectangle([mid - trunk, top + span // 3, mid + trunk, bottom], fill=(126, 96, 70, 255))
        for tier in range(4):
            width = int(span * (0.42 - tier * 0.07))
            y = top + int(span * (0.06 + tier * 0.2))
            draw.polygon(
                [
                    (mid, y),
                    (mid - width, y + int(span * 0.26)),
                    (mid + width, y + int(span * 0.26)),
                ],
                fill=(86, 132, 92, 255),
                outline=_INK,
            )
    elif kind == "stump":
        trunk = span // 2
        draw.rectangle(
            [mid - trunk, top, mid + trunk, bottom], fill=(126, 96, 70, 255), outline=_INK
        )
        draw.ellipse(
            [mid - trunk, top - trunk // 3, mid + trunk, top + trunk // 3],
            fill=(168, 134, 96, 255),
            outline=_INK,
        )
    elif kind == "bush":
        for index in range(7):
            rand = ((seed + index * 37) % 41) / 41.0
            radius = int(span * (0.17 + rand * 0.08))
            cx = mid + int((rand - 0.5) * span * 0.52)
            cy = bottom - radius - int(span * (0.06 + rand * 0.5))
            draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                fill=(74, 116, 80, 255),
                outline=_INK,
            )
    elif kind == "berries":
        for index in range(7):
            rand = ((seed + index * 37) % 41) / 41.0
            radius = int(span * (0.17 + rand * 0.08))
            cx = mid + int((rand - 0.5) * span * 0.52)
            cy = bottom - radius - int(span * (0.06 + rand * 0.5))
            draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                fill=(74, 116, 80, 255),
                outline=_INK,
            )
            draw.ellipse(
                [cx - radius // 4, cy - radius // 4, cx + radius // 4, cy + radius // 4],
                fill=(96, 30, 56, 255),
            )
    elif kind == "rock":
        draw.polygon(
            [
                (mid - span // 2, bottom),
                (mid - int(span * 0.42), top + int(span * 0.3)),
                (mid - int(span * 0.1), top),
                (mid + int(span * 0.34), top + int(span * 0.18)),
                (mid + span // 2, bottom),
            ],
            fill=(126, 126, 122, 255),
            outline=_INK,
        )
    elif kind in {"grass", "grass_cut"}:
        blades = 9
        for index in range(blades):
            rand = ((seed + index * 53) % 47) / 47.0
            lean = int((rand - 0.5) * span * 0.9)
            tip = top + int(span * rand * 0.25)
            base_x = mid + int((index - blades // 2) * span * 0.06)
            draw.line(
                [(base_x, bottom), (base_x + lean, tip)],
                fill=(178, 176, 108, 255),
                width=max(3, span // 40),
            )
    elif kind == "campfire":
        for index in range(7):
            angle = index / 7.0 * math.tau
            cx = mid + int(math.cos(angle) * span * 0.44)
            cy = bottom - int(span * 0.24) + int(math.sin(angle) * span * 0.12)
            radius = span // 8
            draw.ellipse(
                [cx - radius, cy - radius // 2, cx + radius, cy + radius // 2],
                fill=(140, 138, 132, 255),
                outline=_INK,
            )
        draw.polygon(
            [
                (mid - span // 3, bottom - span // 4),
                (mid, top),
                (mid + span // 3, bottom - span // 4),
            ],
            fill=(88, 66, 48, 255),
            outline=_INK,
        )
    elif kind == "campfire_lit":
        for index in range(7):
            angle = index / 7.0 * math.tau
            cx = mid + int(math.cos(angle) * span * 0.44)
            cy = bottom - int(span * 0.24) + int(math.sin(angle) * span * 0.12)
            radius = span // 8
            draw.ellipse(
                [cx - radius, cy - radius // 2, cx + radius, cy + radius // 2],
                fill=(140, 138, 132, 255),
                outline=_INK,
            )
        draw.polygon(
            [
                (mid - span // 3, bottom - span // 4),
                (mid, top),
                (mid + span // 3, bottom - span // 4),
            ],
            fill=(48, 36, 30, 255),
            outline=_INK,
        )
        draw.ellipse(
            [mid - span // 4, bottom - span // 2, mid + span // 4, bottom - span // 4],
            fill=(214, 108, 40, 255),
        )
    elif kind == "tent":
        draw.polygon(
            [(mid - span // 2, bottom), (mid, top), (mid + span // 2, bottom)],
            fill=(146, 132, 108, 255),
            outline=_INK,
        )
        draw.polygon(
            [(mid - span // 8, bottom), (mid, top + span // 3), (mid + span // 8, bottom)],
            fill=(52, 44, 38, 255),
        )
    elif kind in {"player", "mob"}:
        _draw_figure(draw, mid, top, bottom, kind=kind, phase=0.0)
    elif kind == "log":
        draw.rectangle(
            [mid - span // 2, bottom - span // 3, mid + span // 2, bottom],
            fill=(120, 88, 58, 255),
            outline=_INK,
        )
        draw.ellipse(
            [mid + span // 3, bottom - span // 3, mid + span // 2 + span // 6, bottom],
            fill=(186, 152, 110, 255),
            outline=_INK,
        )
    elif kind == "berry":
        for dx, dy in ((-1, 0), (1, 0), (0, -1)):
            radius = span // 3
            cx = mid + dx * radius
            cy = bottom - radius + dy * radius
            draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                fill=(96, 30, 56, 255),
                outline=_INK,
            )
    elif kind == "stone":
        draw.polygon(
            [
                (mid - span // 2, bottom),
                (mid - span // 3, bottom - span // 2),
                (mid + span // 6, bottom - span // 2 - span // 8),
                (mid + span // 2, bottom),
            ],
            fill=(126, 126, 122, 255),
            outline=_INK,
        )
    else:
        draw.ellipse([mid - span // 2, top, mid + span // 2, bottom], fill=(150, 90, 160, 255))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _draw_figure(
    draw: ImageDraw.ImageDraw, mid: int, top: int, bottom: int, *, kind: str, phase: float
) -> None:
    span = bottom - top
    if kind == "mob":
        body_top = bottom - int(span * 0.62)
        draw.ellipse(
            [mid - int(span * 0.46), body_top, mid + int(span * 0.46), bottom - int(span * 0.12)],
            fill=(158, 150, 116, 255),
            outline=_INK,
        )
        draw.ellipse(
            [
                mid + int(span * 0.28),
                body_top + int(span * 0.06),
                mid + int(span * 0.62),
                body_top + int(span * 0.34),
            ],
            fill=(120, 112, 90, 255),
            outline=_INK,
        )
        for leg in range(3):
            offset = int((leg - 1) * span * 0.26)
            swing = int(math.sin(phase * math.tau + leg) * span * 0.08)
            draw.line(
                [(mid + offset, bottom - int(span * 0.18)), (mid + offset + swing, bottom)],
                fill=_INK,
                width=max(3, span // 26),
            )
        return
    head = int(span * 0.11)
    draw.ellipse(
        [mid - head, top, mid + head, top + head * 2], fill=(226, 206, 180, 255), outline=_INK
    )
    draw.polygon(
        [(mid - head * 2, top + head), (mid + head * 2, top + head), (mid, top - head // 2)],
        fill=(62, 52, 44, 255),
        outline=_INK,
    )
    torso_top = top + head * 2
    torso_bottom = bottom - int(span * 0.34)
    draw.polygon(
        [
            (mid - int(span * 0.15), torso_bottom),
            (mid - int(span * 0.11), torso_top),
            (mid + int(span * 0.11), torso_top),
            (mid + int(span * 0.17), torso_bottom),
        ],
        fill=(112, 104, 126, 255),
        outline=_INK,
    )
    swing = int(math.sin(phase * math.tau) * span * 0.12)
    draw.line(
        [(mid - int(span * 0.04), torso_bottom), (mid - int(span * 0.06) + int(swing), bottom)],
        fill=_INK,
        width=max(4, span // 24),
    )
    draw.line(
        [(mid + int(span * 0.04), torso_bottom), (mid + int(span * 0.06) - int(swing), bottom)],
        fill=_INK,
        width=max(4, span // 24),
    )


def _fixture_strip(kind: str, state: str) -> bytes:
    """A four-cell single-row strip with a bottom gutter, as the repack leaves it."""

    width, height = FIXTURE_STRIP
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    cell = width // 4
    for index in range(4):
        frame = Image.new("RGBA", (cell, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame)
        bottom = height - MOTION_BOTTOM_GUTTER_PX
        lift = 0
        # A low six-legged creature drawn at figure height would be wider than
        # its own cell, so the base fraction is per kind and the per-state
        # adjustments are relative to it.
        span_fraction = 0.82 if kind != "mob" else 0.34
        if state == "gather":
            span_fraction -= 0.16 if index in (1, 2) else 0.0
        elif state == "hurt":
            lift = int(height * 0.02 * (1 if index in (1, 2) else 0))
        elif state == "attack":
            span_fraction += 0.05 if index in (2, 3) else 0.0
        top = bottom - int(height * span_fraction)
        _draw_figure(draw, cell // 2, top - lift, bottom - lift, kind=kind, phase=index / 4.0)
        image.alpha_composite(frame, (index * cell, 0))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _fixture_ground(biome_id: str) -> bytes:
    """A 2048 plate that is exactly mirror-symmetric, as mirror_repeat_2d leaves it."""

    quarter = 512
    rand = _fixture_rand(biome_id)
    base = {
        "forest_floor": (96, 88, 64),
        "road": (118, 108, 92),
        "water": (34, 52, 56),
        "ice": (196, 206, 216),
    }.get(biome_id, (168, 156, 112))
    tile = Image.new("RGB", (quarter, quarter), base)
    draw = ImageDraw.Draw(tile)
    for _ in range(900):
        x = int(rand() * quarter)
        y = int(rand() * quarter)
        radius = 2 + int(rand() * 7)
        shift = int((rand() - 0.5) * 46)
        draw.ellipse(
            [x - radius, y - radius, x + radius, y + radius],
            fill=(
                max(0, min(255, base[0] + shift)),
                max(0, min(255, base[1] + shift)),
                max(0, min(255, base[2] + shift)),
            ),
        )
    left = Image.new("RGB", (quarter * 2, quarter))
    left.paste(tile, (0, 0))
    left.paste(tile.transpose(Image.Transpose.FLIP_LEFT_RIGHT), (quarter, 0))
    full = Image.new("RGB", (quarter * 2, quarter * 2))
    full.paste(left, (0, 0))
    full.paste(left.transpose(Image.Transpose.FLIP_TOP_BOTTOM), (0, quarter))
    buffer = BytesIO()
    full.save(buffer, format="PNG")
    return buffer.getvalue()


def _fixture_rand(token: str) -> Any:
    state = abs(hash(token)) % 2147483647 or 7

    def rand() -> float:
        nonlocal state
        state = (state * 48271) % 2147483647
        return state / 2147483647.0

    return rand


def _fixture_macro() -> bytes:
    """Soft blobs around mid-grey, mirrored like the real plate would be."""

    quarter = 512
    rand = _fixture_rand("macro")
    tile = Image.new("RGB", (quarter, quarter), (128, 128, 128))
    draw = ImageDraw.Draw(tile)
    for _ in range(14):
        x = int(rand() * quarter)
        y = int(rand() * quarter)
        radius = int(quarter * (0.12 + rand() * 0.16))
        shift = int((rand() - 0.5) * 40)
        tint = int((rand() - 0.5) * 16)
        draw.ellipse(
            [x - radius, y - radius, x + radius, y + radius],
            fill=(128 + shift - tint, 128 + shift + tint, 128 + shift - tint // 2),
        )
    tile = tile.filter(ImageFilter.GaussianBlur(28))
    left = Image.new("RGB", (quarter * 2, quarter))
    left.paste(tile, (0, 0))
    left.paste(tile.transpose(Image.Transpose.FLIP_LEFT_RIGHT), (quarter, 0))
    full = Image.new("RGB", (quarter * 2, quarter * 2))
    full.paste(left, (0, 0))
    full.paste(left.transpose(Image.Transpose.FLIP_TOP_BOTTOM), (0, quarter))
    buffer = BytesIO()
    full.save(buffer, format="PNG")
    return buffer.getvalue()


def _fixture_pieces(columns: int, rows: int, cell_px: int) -> bytes:
    """One small flat shape per cell, well inside its cell."""

    image = Image.new("RGBA", (columns * cell_px, rows * cell_px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    rand = _fixture_rand("pieces")
    palette = [(150, 110, 60, 255), (120, 120, 116, 255), (90, 110, 60, 255), (200, 170, 90, 255)]
    for index in range(columns * rows):
        cx = (index % columns) * cell_px + cell_px // 2
        cy = (index // columns) * cell_px + cell_px // 2
        rx = int(cell_px * (0.12 + rand() * 0.16))
        ry = int(cell_px * (0.10 + rand() * 0.14))
        colour = palette[index % len(palette)]
        if index % 3 == 0:
            draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=colour)
        elif index % 3 == 1:
            draw.polygon([(cx - rx, cy + ry), (cx, cy - ry), (cx + rx, cy + ry // 2)], fill=colour)
        else:
            draw.rounded_rectangle(
                [cx - rx, cy - ry // 2, cx + rx, cy + ry // 2], radius=8, fill=colour
            )
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _fixture_look(summer: bytes) -> bytes:
    """The summer stub with a pale cap over the top third of its painted bounds."""

    from PIL import ImageChops, ImageOps

    with Image.open(BytesIO(summer)) as opened:
        base = opened.convert("RGBA")
    box = alpha_bbox(summer)
    if box is None:
        return summer
    left, top, right, bottom = box
    band = max(1, (bottom - top) // 3)
    gradient = ImageOps.invert(Image.linear_gradient("L")).resize((max(1, right - left), band))
    mask = Image.new("L", base.size, 0)
    mask.paste(gradient, (left, top))
    mask = ImageChops.multiply(mask, base.getchannel("A"))
    cap = Image.new("RGBA", base.size, (232, 238, 250, 255))
    base.paste(cap, (0, 0), mask)
    buffer = BytesIO()
    base.save(buffer, format="PNG")
    return buffer.getvalue()


def _fixture_decal(decal_id: str) -> bytes:
    size = FIXTURE_CANVAS
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    centre = size // 2
    for step in range(centre, 0, -8):
        alpha = int(255 * (1.0 - step / centre) ** 1.6)
        draw.ellipse(
            [centre - step, centre - step, centre + step, centre + step],
            fill=(86, 68, 50, alpha),
        )
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _fixture_fire(columns: int, rows: int, cell_px: int) -> bytes:
    image = Image.new("RGBA", (columns * cell_px, rows * cell_px), (0, 0, 0, 0))
    frames = columns * rows
    for index in range(frames):
        phase = index / frames
        cell = Image.new("RGBA", (cell_px, cell_px), (0, 0, 0, 0))
        draw = ImageDraw.Draw(cell)
        mid = cell_px // 2
        base = int(cell_px * 0.95)
        for layer, colour in (
            (1.0, (232, 150, 46, 255)),
            (0.68, (246, 202, 96, 255)),
            (0.36, (252, 244, 214, 255)),
        ):
            wobble = math.sin(phase * math.tau + layer * 2.0) * cell_px * 0.05
            tip = base - int(cell_px * 0.78 * layer)
            width = int(cell_px * 0.26 * layer)
            draw.polygon(
                [
                    (mid - width, base),
                    (mid + int(wobble), tip),
                    (mid + width, base),
                ],
                fill=colour,
            )
        image.alpha_composite(cell, ((index % columns) * cell_px, (index // columns) * cell_px))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _fixture_dust(kinds: tuple[str, ...]) -> bytes:
    size = FIXTURE_CANVAS
    half = size // 2
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    palette = {
        "dust": (196, 186, 168, 255),
        "leaves": (58, 78, 46, 255),
        "chips": (196, 166, 118, 255),
        "sparkle": (250, 196, 96, 255),
    }
    for index, kind in enumerate(kinds[:4]):
        cx = (index % 2) * half + half // 2
        cy = (index // 2) * half + half // 2
        draw = ImageDraw.Draw(image)
        rand = _fixture_rand(kind)
        for _ in range(5):
            radius = int(half * (0.13 + rand() * 0.11))
            ox = int((rand() - 0.5) * half * 0.42)
            oy = int((rand() - 0.5) * half * 0.34)
            draw.ellipse(
                [cx + ox - radius, cy + oy - radius, cx + ox + radius, cy + oy + radius],
                fill=palette.get(kind, (200, 200, 200, 255)),
            )
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _fixture_drops() -> bytes:
    """A tapering streak in the left half, a drop in the right."""

    size = FIXTURE_CANVAS
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    cx = size // 4
    draw.polygon(
        [(cx - 9, 80), (cx + 9, 80), (cx + 2, 940), (cx - 2, 940)], fill=(236, 232, 220, 255)
    )
    cx = size * 3 // 4
    draw.ellipse(
        [cx - 44, size // 2 - 44, cx + 44, size // 2 + 44],
        fill=(196, 214, 222, 255),
        outline=(60, 70, 80, 255),
        width=6,
    )
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _fixture_splash(kinds: tuple[str, ...]) -> bytes:
    size = FIXTURE_CANVAS
    half = size // 2
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    pale = (196, 214, 222, 255)
    ink = (60, 70, 80, 255)
    for index, kind in enumerate(kinds[:4]):
        cx = (index % 2) * half + half // 2
        cy = (index // 2) * half + half // 2
        if kind == "bead":
            draw.ellipse([cx - 40, cy - 40, cx + 40, cy + 40], fill=pale, outline=ink, width=6)
            continue
        draw.ellipse([cx - 150, cy - 70, cx + 150, cy + 70], outline=pale, width=22)
        draw.ellipse([cx - 150, cy - 70, cx + 150, cy + 70], outline=ink, width=5)
        if kind == "crown":
            for dx in (-60, 0, 60):
                draw.ellipse(
                    [cx + dx - 18, cy - 130, cx + dx + 18, cy - 60],
                    fill=pale,
                    outline=ink,
                    width=4,
                )
        if kind == "spray":
            for dx, dy in ((-200, -20), (200, 10), (-40, 120), (90, -120)):
                draw.ellipse(
                    [cx + dx - 16, cy + dy - 10, cx + dx + 16, cy + dy + 10],
                    fill=pale,
                    outline=ink,
                    width=4,
                )
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _fixture_strike() -> bytes:
    size = FIXTURE_CANVAS
    half = size // 2
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    rand = _fixture_rand("strike")
    for index in range(4):
        x0 = (index % 2) * half
        y0 = (index // 2) * half
        points = []
        x = x0 + half // 2
        for step in range(7):
            y = y0 + int(half * (0.05 + 0.13 * step))
            x += int((rand() - 0.5) * half * 0.12)
            points.append((x, y))
        draw.line(points, fill=(52, 46, 40, 255), width=22, joint="curve")
        draw.line(points, fill=(250, 246, 226, 255), width=12, joint="curve")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


_FIXTURE_PROP_SHAPES: Final = {
    ("pine", "sapling"): "tree",
    ("pine", "grown"): "tree",
    ("pine", "old"): "tree",
    ("pine", "stump"): "stump",
    ("thorn_bush", "full"): "berries",
    ("thorn_bush", "picked"): "bush",
    ("moss_boulder", "whole"): "rock",
    ("moss_boulder", "cracked"): "rock",
    ("moss_boulder", "split"): "rock",
    ("moss_boulder", "rubble"): "rock",
    ("grass_tuft", "standing"): "grass",
    ("grass_tuft", "cut"): "grass_cut",
    ("campfire", "unlit"): "campfire",
    ("campfire", "lit"): "campfire_lit",
    ("canvas_tent", "pitched"): "tent",
}


def write_fixture(package: Package, run_dir: Path, layout: Layout) -> Manifest:
    """Draw a complete placeholder package plus its manifest. No provider calls."""

    def write(ref: str, data: bytes) -> None:
        path = run_dir / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    for prop in package.props:
        for state in prop.states:
            shape = _FIXTURE_PROP_SHAPES.get((prop.prop_id, state), prop.family)
            # A stump is a fraction of its tree; every other state fills its own
            # canvas, exactly as a per-state provider call would.
            fraction = 0.86
            if state in {"stump", "cut"}:
                fraction = 0.86 * (0.22 if state == "stump" else 0.34)
            elif state == "sapling":
                fraction = 0.86 * 0.4
            elif state == "rubble":
                fraction = 0.86 * 0.45
            write(
                prop_ref(prop.prop_id, state),
                _fixture_sprite(shape, height_fraction=fraction, seed=len(prop.prop_id) * 7),
            )
    # A season look is the summer stub with its top whitened: the same shape,
    # the way a paintover would leave it.
    for look in package.seasons.looks if package.seasons is not None else ():
        for prop in package.props:
            for state in prop.states:
                summer = (run_dir / prop_ref(prop.prop_id, state)).read_bytes()
                write(prop_look_ref(prop.prop_id, state, look.look_id), _fixture_look(summer))
    for item in package.items:
        write(item_ref(item.item_id), _fixture_sprite(item.item_id, height_fraction=0.7))
    for actor in package.actors:
        kind = "player" if actor.role == "player" else "mob"
        write(concept_ref(actor.actor_id), _fixture_sprite(kind))
        for motion in actor.states:
            write(state_ref(actor.actor_id, motion.state), _fixture_strip(kind, motion.state))
    for biome in package.biomes:
        write(ground_ref(biome.biome_id), _fixture_ground(biome.biome_id))
    if package.macro is not None:
        write(macro_ref(), _fixture_macro())
    if package.road is not None:
        write(road_ref(package.road.road_id), _fixture_ground("road"))
    if package.forage is not None:
        write(forage_ref(), _fixture_pieces(package.forage.columns, package.forage.rows, 256))
    write(
        icons_ref(),
        _fixture_pieces(package.icons.columns, package.icons.rows, package.icons.cell_px),
    )
    if package.water is not None:
        write(water_ref(), _fixture_ground("water"))
    for decal in package.decals:
        write(decal_ref(decal.decal_id), _fixture_decal(decal.decal_id))
    write(
        fire_ref(),
        _fixture_fire(package.fire.columns, package.fire.rows, 256),
    )
    write(dust_ref(), _fixture_dust(package.dust.kinds))
    for condition in package.weather:
        cid = condition.condition_id
        if condition.drops is not None:
            write(weather_ref(cid, "drops"), _fixture_drops())
        if condition.ground is not None:
            write(weather_ref(cid, "ground"), _fixture_splash(condition.ground.kinds))
        if condition.strike is not None:
            write(weather_ref(cid, "strike"), _fixture_strike())
        if condition.ice is not None:
            write(weather_ref(cid, "ice"), _fixture_ground("ice"))
        # No fixture audio: a placeholder clip would be a fake listening verdict.
    write(splat_ref(), layout.splat_png)
    write(biome_splat_ref(), layout.biome_splat_png)
    write(layout_ref(), manifest_bytes(layout.as_record()))
    return build_manifest(package, run_dir, run_id=run_dir.name, graph_sha256=None, scope="fixture")
