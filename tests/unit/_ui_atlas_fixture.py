"""Synthetic nine-slice sheets for the UI atlas gate and the fake image service.

A perfect sheet is what the format promises: ornamented corners, flat uniform edge bands, a
flat centre, and one silhouette per body with only value moving between states. The knobs
break exactly one promise each so a test can name the failure it expects.
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw

from stage_gen.components.game_ui import AtlasRole


def atlas_sheet(
    role: AtlasRole,
    *,
    medallion: bool = False,
    band_gradient: bool = False,
    band_tassel: bool = False,
    drift_px: int = 0,
    drop_last: bool = False,
    band_alpha: int = 255,
    exterior_glow: bool = False,
) -> bytes:
    width, height = role.canvas
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    insets = role.declared_insets
    cells = role.cells[:-1] if drop_last else role.cells
    for index, rect in enumerate(cells):
        shift = 18 * index
        body = (52 + shift, 68 + shift, 96 + shift, 255)
        band = (150 + shift // 2, 120 + shift // 2, 70, 255)
        corner = (230, 190, 90, 255)
        cell_width = rect.width + (drift_px if index == 1 else 0)
        x0, y0 = rect.x, rect.y
        x1, y1 = x0 + cell_width - 1, y0 + rect.height - 1
        draw.rectangle((x0, y0, x1, y1), fill=band)
        draw.rectangle(
            (x0 + insets.left, y0 + insets.top, x1 - insets.right, y1 - insets.bottom),
            fill=body,
        )
        for corner_box in (
            (x0, y0, x0 + insets.left - 1, y0 + insets.top - 1),
            (x1 - insets.right + 1, y0, x1, y0 + insets.top - 1),
            (x0, y1 - insets.bottom + 1, x0 + insets.left - 1, y1),
            (x1 - insets.right + 1, y1 - insets.bottom + 1, x1, y1),
        ):
            draw.rectangle(corner_box, fill=corner)
            cx0, cy0, cx1, cy1 = corner_box
            draw.ellipse((cx0 + 6, cy0 + 6, cx1 - 6, cy1 - 6), fill=(120, 40, 40, 255))
        if medallion and index == 0:
            # Mid-band: past any inset widening, so it is what a stretched strip cannot rebuild.
            mid = (x0 + x1) // 2
            draw.ellipse(
                (mid - 24, y0 + 4, mid + 24, y0 + insets.top - 4), fill=(255, 240, 200, 255)
            )
        if band_tassel:
            # Ornament hanging from the top band into the content, well past the corner caps:
            # the band itself stays plain, so the insets do not widen over it, and the content
            # rect cannot exclude it by construction. Only a measured safe rect can.
            tx, ty = x0 + insets.left + 200, y0 + insets.top
            draw.ellipse((tx, ty, tx + 48, ty + 24), fill=(230, 190, 90, 255))
        if band_gradient and index == 0:
            # A band that brightens along its length: one strip cannot rebuild it, and its two
            # ends no longer meet, so neither fill can admit it.
            start, end = x0 + insets.left, x1 - insets.right
            for x in range(start, end + 1, 4):
                lift = int(120 * (x - start) / max(1, end - start))
                draw.rectangle(
                    (x, y0, min(x + 3, end), y0 + insets.top - 1),
                    fill=(min(255, band[0] + lift), min(255, band[1] + lift), band[2], 255),
                )
        if band_alpha != 255 and index == 0:
            draw.rectangle(
                (x0 + insets.left, y0, x1 - insets.right, y0 + insets.top - 1),
                fill=(band[0], band[1], band[2], band_alpha),
            )
    if exterior_glow:
        draw.rectangle((0, 0, 32, 32), fill=(255, 255, 255, 40))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
