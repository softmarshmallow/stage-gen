"""The inventory panel's pixel gate: a transparent exterior around an opaque core and slots.

A painted panel is admitted when its canvas border is clear and its panel core and every
slot interior are opaque; canonicalization clears the exterior and clamps the core and the
slots at the admitted boundary, and the evidence composes the result over a checkerboard.
The steps that paint and review a panel live with the games (``demo_game_tools.steps``).
"""

from __future__ import annotations

import io
from typing import cast

from PIL import Image, ImageDraw

from demo_game_tools.kits.ui_art.models import (
    INVENTORY_CANVAS_HEIGHT,
    INVENTORY_CANVAS_WIDTH,
    INVENTORY_PANEL_HEIGHT,
    INVENTORY_PANEL_LEFT,
    INVENTORY_PANEL_TOP,
    INVENTORY_PANEL_WIDTH,
    INVENTORY_SLOT_COLUMNS,
    INVENTORY_SLOT_GUTTER,
    INVENTORY_SLOT_LEFT,
    INVENTORY_SLOT_ROWS,
    INVENTORY_SLOT_SIZE,
    INVENTORY_SLOT_TOP,
)

INVENTORY_PANEL_VALIDATION_VERSION = "prepared-ui-inventory-validation-v2"
#: What the judge is asked that the pixel gate cannot decide.
INVENTORY_REVIEW_CHECKS = (
    "style_coherence",
    "slot_readability",
    "visual_hierarchy",
    "exterior_silhouette",
    "no_items_or_text",
)


def validate_inventory_panel_image(data: bytes) -> dict[str, object]:
    """Admit a painted panel: transparent exterior, opaque core, opaque slot interiors."""

    with Image.open(io.BytesIO(data)) as opened:
        if "A" not in opened.getbands():
            raise ValueError("inventory panel output must carry an alpha channel")
        image = opened.convert("RGBA")
    if image.size != (INVENTORY_CANVAS_WIDTH, INVENTORY_CANVAS_HEIGHT):
        raise ValueError(
            "inventory panel output must be exactly "
            f"{INVENTORY_CANVAS_WIDTH}x{INVENTORY_CANVAS_HEIGHT}"
        )
    alpha = image.getchannel("A")
    extrema = cast(tuple[int, int], alpha.getextrema())
    opaque_admission_min = 250
    transparent_admission_max = 16
    if extrema[0] > transparent_admission_max or extrema[1] < opaque_admission_min:
        raise ValueError("inventory panel must contain transparent exterior and opaque artwork")
    border = [
        *alpha.crop((0, 0, alpha.width, 1)).get_flattened_data(),
        *alpha.crop((0, alpha.height - 1, alpha.width, alpha.height)).get_flattened_data(),
        *alpha.crop((0, 0, 1, alpha.height)).get_flattened_data(),
        *alpha.crop((alpha.width - 1, 0, alpha.width, alpha.height)).get_flattened_data(),
    ]
    if max(border) > transparent_admission_max:
        raise ValueError("inventory panel exterior must remain transparent at the canvas border")

    transparent_pixels = sum(alpha.histogram()[: transparent_admission_max + 1])
    transparent_pixel_fraction = transparent_pixels / (alpha.width * alpha.height)
    if transparent_pixel_fraction < 0.1:
        raise ValueError("inventory panel must retain meaningful transparent exterior space")

    core_inset = 32
    core = alpha.crop(
        (
            INVENTORY_PANEL_LEFT + core_inset,
            INVENTORY_PANEL_TOP + core_inset,
            INVENTORY_PANEL_LEFT + INVENTORY_PANEL_WIDTH - core_inset,
            INVENTORY_PANEL_TOP + INVENTORY_PANEL_HEIGHT - core_inset,
        )
    )
    core_min = cast(tuple[int, int], core.getextrema())[0]
    if core_min < opaque_admission_min:
        raise ValueError(
            "inventory panel middle must be fully opaque; transparent or translucent pixels found"
        )

    slot_alpha_minima: list[int] = []
    slot_inset = 24
    for row in range(INVENTORY_SLOT_ROWS):
        for column in range(INVENTORY_SLOT_COLUMNS):
            left = (
                INVENTORY_SLOT_LEFT
                + column * (INVENTORY_SLOT_SIZE + INVENTORY_SLOT_GUTTER)
                + slot_inset
            )
            top = (
                INVENTORY_SLOT_TOP
                + row * (INVENTORY_SLOT_SIZE + INVENTORY_SLOT_GUTTER)
                + slot_inset
            )
            interior = alpha.crop(
                (
                    left,
                    top,
                    left + INVENTORY_SLOT_SIZE - 2 * slot_inset,
                    top + INVENTORY_SLOT_SIZE - 2 * slot_inset,
                )
            )
            slot_alpha_minima.append(cast(tuple[int, int], interior.getextrema())[0])
    if any(value < opaque_admission_min for value in slot_alpha_minima):
        raise ValueError(
            "every inventory slot interior must be visually opaque before normalization"
        )

    return {
        "width": image.width,
        "height": image.height,
        "alpha_min": extrema[0],
        "alpha_max": extrema[1],
        "border_alpha_max": max(border),
        "transparent_pixel_fraction": round(transparent_pixel_fraction, 6),
        "panel_core_alpha_min": core_min,
        "slot_interior_alpha_minima": slot_alpha_minima,
        "opaque_admission_min": opaque_admission_min,
        "transparent_admission_max": transparent_admission_max,
        "all_slot_interiors_opaque": True,
        "pixel_rewrite_performed": False,
    }


def canonicalize_inventory_panel_image(data: bytes) -> tuple[bytes, dict[str, object]]:
    """Normalize only the admitted alpha boundary: clear the exterior, clamp the core."""

    source_facts = validate_inventory_panel_image(data)
    with Image.open(io.BytesIO(data)) as opened:
        image = opened.convert("RGBA")
    alpha = image.getchannel("A")

    transparent_admission_max = cast(int, source_facts["transparent_admission_max"])
    alpha = alpha.point(lambda value: 0 if value <= transparent_admission_max else value)
    core_inset = 32
    alpha.paste(
        255,
        (
            INVENTORY_PANEL_LEFT + core_inset,
            INVENTORY_PANEL_TOP + core_inset,
            INVENTORY_PANEL_LEFT + INVENTORY_PANEL_WIDTH - core_inset,
            INVENTORY_PANEL_TOP + INVENTORY_PANEL_HEIGHT - core_inset,
        ),
    )
    image.putalpha(alpha)
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=False)
    canonical_data = output.getvalue()
    canonical_facts = validate_inventory_panel_image(canonical_data)
    return canonical_data, {
        "source": source_facts,
        "canonical": canonical_facts,
        "pixel_rewrite_performed": True,
        "pixel_rewrite": "alpha_boundary_normalization_v1",
    }


def checkerboard(size: tuple[int, int]) -> Image.Image:
    """The review backdrop: a neutral checker that makes transparency legible to a judge."""

    image = Image.new("RGBA", size, (220, 220, 220, 255))
    draw = ImageDraw.Draw(image)
    block = 20
    for y in range(0, size[1], block):
        for x in range(0, size[0], block):
            if (x // block + y // block) % 2:
                draw.rectangle((x, y, x + block - 1, y + block - 1), fill=(174, 174, 174, 255))
    return image


def inventory_panel_evidence(data: bytes) -> bytes:
    with Image.open(io.BytesIO(data)) as opened:
        panel = opened.convert("RGBA")
    canvas = checkerboard(panel.size)
    canvas.alpha_composite(panel)
    stream = io.BytesIO()
    canvas.convert("RGB").save(stream, format="PNG", optimize=False)
    return stream.getvalue()


__all__ = [
    "INVENTORY_PANEL_VALIDATION_VERSION",
    "INVENTORY_REVIEW_CHECKS",
    "canonicalize_inventory_panel_image",
    "checkerboard",
    "inventory_panel_evidence",
    "validate_inventory_panel_image",
]
