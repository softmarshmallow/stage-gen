"""The content gates Bellweather holds its actors and catalog to, and the motion contract."""

from __future__ import annotations

import io
from typing import cast

import pytest
from PIL import Image, ImageDraw

from bellweather_pipeline.assets import validate_atlas, validate_transparent_image
from bellweather_pipeline.motion_contract import (
    motion_semantic_direction,
    motion_source_facing,
)
from demo_game_tools.kits.sideview_actor.motion_geometry import (
    dialogue_atlas_grid,
    runtime_mirrors_source,
)


def _atlas(*, missing_cell: int | None = None) -> bytes:
    image = Image.new("RGBA", (1536, 1024), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    cell_width = image.width // 4
    cell_height = image.height
    for index in range(4):
        if index == missing_cell:
            continue
        row, column = divmod(index, 4)
        left = column * cell_width + 40
        top = row * cell_height + 40
        draw.ellipse(
            (left, top, left + cell_width - 80, top + cell_height - 80),
            fill=(120, 180, 240, 255),
        )
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def test_motion_atlas_requires_native_alpha_and_all_cells() -> None:
    facts = validate_atlas(_atlas(), columns=4, rows=1, required_cells=4)
    assert facts["all_required_cells_visible"] is True
    assert len(cast(list[float], facts["cell_visible_fractions"])) == 4

    with pytest.raises(ValueError, match="missing a required visible cell"):
        validate_atlas(_atlas(missing_cell=3), columns=4, rows=1, required_cells=4)


def test_motion_source_facing_is_runtime_owned_and_climb_is_rear_facing() -> None:
    assert motion_source_facing("player", "walk") == "right"
    assert motion_source_facing("mob", "move") == "right"
    assert motion_source_facing("npc", "idle", npc_world_orientation="front") == "front"
    with pytest.raises(ValueError, match="requires world_orientation"):
        motion_source_facing("npc", "idle")
    assert motion_source_facing("player", "climb_ladder") == "back"
    assert motion_source_facing("player", "climb_rope") == "back"
    assert runtime_mirrors_source("right") is True
    assert runtime_mirrors_source("back") is False
    assert runtime_mirrors_source("front") is False


def test_crouch_visual_semantics_are_stationary_and_distinct_from_crawl() -> None:
    direction = motion_semantic_direction("player", "crouch")

    assert "low stationary crouch loop" in direction
    assert "does not crawl" in direction
    assert motion_semantic_direction("player", "walk") == (
        "four clear game-animation key poses that communicate walk"
    )


def test_transparent_image_rejects_opaque_and_dialogue_grid_is_stable() -> None:
    opaque = Image.new("RGBA", (1024, 1024), (1, 2, 3, 255))
    stream = io.BytesIO()
    opaque.save(stream, format="PNG")
    with pytest.raises(ValueError, match="transparent and visible"):
        validate_transparent_image(stream.getvalue(), width=1024, height=1024)

    contaminated = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    ImageDraw.Draw(contaminated).rectangle((0, 0, 1023, 100), fill=(40, 40, 40, 180))
    stream = io.BytesIO()
    contaminated.save(stream, format="PNG")
    with pytest.raises(ValueError, match="alpha contamination at the canvas border"):
        validate_transparent_image(stream.getvalue(), width=1024, height=1024)

    assert dialogue_atlas_grid(4) == (2, 2)
    assert dialogue_atlas_grid(5) == (3, 2)
