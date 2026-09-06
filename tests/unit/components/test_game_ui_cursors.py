from __future__ import annotations

import io
from typing import cast

import pytest
from PIL import Image

from stage_gen.components.game_ui import (
    CURSOR_ALPHA_POLICY,
    CURSOR_GLYPHS,
    CURSOR_SET,
    HOTSPOT_RULES,
    CursorGridRole,
    canonicalize_cursor_sheet,
    cursor_evidence,
    cursor_role_contract,
    render_icon_template,
    validate_cursor_sheet,
)
from stage_gen.components.game_ui.nodes import (
    CURSOR_GRID_FAMILY,
    ICON_GRID_FAMILY,
    CursorSetLayout,
    cursor_content_task,
    cursor_review_prompt,
    sheet_family,
    validate_ui_sheet,
)
from tests.unit._ui_atlas_fixture import cursor_sheet, ui_sheet


def test_nine_pointers_fill_the_icon_grid_s_canvas() -> None:
    """The model honours a template whose grid fills the canvas and ignores one that sits as
    an island inside a wide margin (the first cut, eight cells on a 3:2 canvas, was laid out
    afresh across the whole canvas on every draw), so the cursor grid fills a 1024 square with
    the icon grid's own margins."""

    assert CURSOR_SET.canvas == (1024, 1024)
    cells = CURSOR_SET.cells
    assert len(cells) == 9 == len(CURSOR_SET.glyphs) == len(CURSOR_SET.hotspots)
    assert CURSOR_SET.cell_size == 320
    assert cells[0].x == CURSOR_SET.margin - CURSOR_SET.slack == 16
    last = cells[-1]
    assert last.x + last.width == 1024 - 16 and last.y + last.height == 1024 - 16
    assert [cell.y for cell in cells[:3]] == [cells[0].y] * 3 and cells[3].y > cells[0].y
    assert cells[0].x == cells[3].x
    assert CURSOR_SET.geometry_record()["hotspots"] == list(CURSOR_SET.hotspots)
    with pytest.raises(ValueError, match="one hotspot rule per glyph"):
        CursorGridRole(
            role="x",
            layout="x",
            glyphs=CURSOR_SET.glyphs,
            columns=3,
            rows=3,
            cell=288,
            gutter=48,
            margin=32,
            slack=16,
            canvas=(1024, 1024),
            hotspots=("centre",),
        )
    with pytest.raises(ValueError, match="hotspot rules must be one of"):
        CursorGridRole(
            role="x",
            layout="x",
            glyphs=CURSOR_SET.glyphs,
            columns=3,
            rows=3,
            cell=288,
            gutter=48,
            margin=32,
            slack=16,
            canvas=(1024, 1024),
            hotspots=cast(tuple[str, ...], ("nowhere",) * 9),  # type: ignore[arg-type]
        )


def test_the_template_is_the_icon_grid_s() -> None:
    with Image.open(io.BytesIO(render_icon_template(CURSOR_SET))) as image:
        assert image.size == (1024, 1024)
        guide = CURSOR_SET.guide_cells[0]
        assert image.getpixel((guide.x, guide.y + guide.height // 2)) == (0, 255, 255, 255)
        assert image.getpixel((guide.x + guide.width // 2, guide.y + guide.height // 2)) == (
            0,
            0,
            0,
            0,
        )


def test_each_hotspot_is_read_by_its_rule_from_the_drawn_alpha() -> None:
    facts = validate_cursor_sheet(cursor_sheet(CURSOR_SET), CURSOR_SET)
    assert facts["alpha_policy"] == CURSOR_ALPHA_POLICY
    assert facts["hotspot_rules"] == list(CURSOR_SET.hotspots)
    cells = cast(list[dict[str, object]], facts["cells"])
    assert [entry["glyph"] for entry in cells] == [name for name, _, _ in CURSOR_GLYPHS]
    for entry, cell, rule in zip(cells, CURSOR_SET.cells, CURSOR_SET.hotspots, strict=True):
        glyph = cast(dict[str, int], entry["glyph_rect"])
        hotspot = cast(dict[str, int], entry["hotspot"])
        assert entry["hotspot_rule"] == rule
        # Relative to the cell, and inside it.
        assert 0 <= hotspot["x"] < cell.width and 0 <= hotspot["y"] < cell.height
        absolute = (hotspot["x"] + cell.x, hotspot["y"] + cell.y)
        if rule == "tip_top_left":
            # The right triangle's right angle: the bounds' own corner.
            assert absolute == (glyph["x"], glyph["y"])
        elif rule == "tip_top":
            # The middle of the bar's top edge.
            assert absolute[1] == glyph["y"]
            assert abs(absolute[0] - (glyph["x"] + glyph["width"] // 2)) <= 1
        else:
            # The ring's centre, which no drawn pixel occupies.
            assert absolute == (
                glyph["x"] + glyph["width"] // 2,
                glyph["y"] + glyph["height"] // 2,
            )


def test_the_gate_is_the_icon_gate_and_the_projection_carries_the_hotspot() -> None:
    assert sheet_family(CURSOR_SET) is CURSOR_GRID_FAMILY
    assert sheet_family(CURSOR_SET) is not ICON_GRID_FAMILY
    assert validate_ui_sheet(ui_sheet("cursor_set"), "cursor_set")["role"] == "cursor_set"
    canonical, facts = canonicalize_cursor_sheet(cursor_sheet(CURSOR_SET), CURSOR_SET)
    assert facts["pixel_rewrite"] == "alpha_exterior_normalization_v1"
    canonical_facts = cast(dict[str, object], facts["canonical"])
    contract = cursor_role_contract(canonical_facts)
    assert set(contract) == {
        "role",
        "layout",
        "scale_mode",
        "alpha_policy",
        "draw_scale",
        "canvas",
        "cell_size",
        "cells",
    }
    cells = cast(list[dict[str, object]], contract["cells"])
    assert len(cells) == 9
    assert set(cells[0]) == {"glyph", "cell", "glyph_rect", "hotspot_rule", "hotspot"}
    # The typed block every host can validate the projection against.
    layout = CursorSetLayout.model_validate({**contract, "cells": cells})
    assert layout.scale_mode == "fixed" and layout.cells[0].hotspot_rule == "tip_top_left"
    assert {rule for rule in HOTSPOT_RULES} >= {entry.hotspot_rule for entry in layout.cells}
    with Image.open(io.BytesIO(cursor_evidence(canonical, canonical_facts))) as evidence:
        # The sheet on the left, eight annotated rows on the right.
        assert evidence.width > 1024 + 24 and evidence.height >= 9 * 80


def test_the_prompt_places_every_pointing_part_and_the_review_asks_where_the_mark_sits() -> None:
    prompt = cursor_content_task(CURSOR_SET, "flat bone pointers")
    assert "9 cursors in a 3 by 3 grid on one 1024 by 1024 canvas" in prompt
    assert "1 arrow (a classic pointer arrow, its tip at the upper left" in prompt
    assert "2 hand (a pointing hand with the index finger straight up" in prompt
    assert "8 move (four arrows pointing outward from one centre)" in prompt
    assert "9 text (a text I-beam" in prompt
    assert "Style direction: flat bone pointers" in prompt
    assert "these are glyphs and not buttons" in prompt
    review = cursor_review_prompt(CURSOR_SET, "flat bone pointers")
    assert "small red cross" in review
    assert "on the arrow's tip, on the pointing finger's tip" in review
    assert "hotspot_placement" in CURSOR_GRID_FAMILY.review_checks
