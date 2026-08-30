from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw

from stage_gen.components.game_ui import (
    INVENTORY_CANVAS_HEIGHT,
    INVENTORY_CANVAS_WIDTH,
    INVENTORY_PANEL_HEIGHT,
    INVENTORY_PANEL_LEFT,
    INVENTORY_PANEL_TOP,
    INVENTORY_PANEL_WIDTH,
    INVENTORY_SLOT_LEFT,
    INVENTORY_SLOT_SIZE,
    INVENTORY_SLOT_TOP,
)
from stage_gen.recipes.sideview_platformer.prepared_content import (
    _canonicalize_inventory_panel_image,
    _validate_inventory_panel_image,
)


def _panel(
    *,
    slot_hole: bool = False,
    middle_hole: bool = False,
    panel_alpha: int = 255,
    exterior_glow: bool = False,
) -> bytes:
    image = Image.new(
        "RGBA",
        (INVENTORY_CANVAS_WIDTH, INVENTORY_CANVAS_HEIGHT),
        (0, 0, 0, 0),
    )
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (
            INVENTORY_PANEL_LEFT,
            INVENTORY_PANEL_TOP,
            INVENTORY_PANEL_LEFT + INVENTORY_PANEL_WIDTH - 1,
            INVENTORY_PANEL_TOP + INVENTORY_PANEL_HEIGHT - 1,
        ),
        fill=(68, 91, 74, panel_alpha),
    )
    if exterior_glow:
        draw.rectangle((0, 0, 32, 32), fill=(68, 91, 74, 32))
    if slot_hole:
        draw.rectangle(
            (
                INVENTORY_SLOT_LEFT + 48,
                INVENTORY_SLOT_TOP + 48,
                INVENTORY_SLOT_LEFT + INVENTORY_SLOT_SIZE - 49,
                INVENTORY_SLOT_TOP + INVENTORY_SLOT_SIZE - 49,
            ),
            fill=(0, 0, 0, 0),
        )
    if middle_hole:
        draw.point((INVENTORY_PANEL_LEFT + 64, INVENTORY_PANEL_TOP + 64), fill=(0, 0, 0, 0))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_inventory_panel_validator_requires_opaque_middle_and_slots() -> None:
    facts = _validate_inventory_panel_image(_panel())

    assert facts["panel_core_alpha_min"] == 255
    assert facts["slot_interior_alpha_minima"] == [255] * 8
    assert facts["pixel_rewrite_performed"] is False


def test_inventory_panel_validator_rejects_alpha_inside_a_slot() -> None:
    with pytest.raises(ValueError, match="middle must be fully opaque"):
        _validate_inventory_panel_image(_panel(slot_hole=True))


def test_inventory_panel_validator_rejects_alpha_in_the_panel_middle() -> None:
    with pytest.raises(ValueError, match="middle must be fully opaque"):
        _validate_inventory_panel_image(_panel(middle_hole=True))


def test_inventory_panel_validator_rejects_alpha_at_the_canvas_border() -> None:
    with pytest.raises(ValueError, match="canvas border"):
        _validate_inventory_panel_image(_panel(exterior_glow=True))


def test_inventory_panel_canonicalizer_clamps_admitted_middle_to_alpha_255() -> None:
    canonical, facts = _canonicalize_inventory_panel_image(_panel(panel_alpha=251))
    with Image.open(io.BytesIO(canonical)) as image:
        alpha = image.getchannel("A")

    source_facts = facts["source"]
    canonical_facts = facts["canonical"]
    assert isinstance(source_facts, dict)
    assert isinstance(canonical_facts, dict)
    assert source_facts["panel_core_alpha_min"] == 251
    assert canonical_facts["panel_core_alpha_min"] == 255
    assert facts["pixel_rewrite"] == "alpha_boundary_normalization_v1"
    assert alpha.crop((160, 192, 1376, 832)).getextrema() == (255, 255)
