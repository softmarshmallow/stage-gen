from __future__ import annotations

import io
from itertools import pairwise
from typing import cast

import pytest
from PIL import Image

from stage_gen.components.game_ui import (
    ICON_ALPHA_POLICY,
    PREVIEW_ICON_GLYPHS,
    PREVIEW_ICONS,
    IconAdmissionError,
    IconGridRole,
    canonicalize_icon_sheet,
    icon_evidence,
    icon_role_contract,
    render_icon_template,
    validate_icon_sheet,
)
from stage_gen.components.game_ui.nodes import (
    ICON_GRID_FAMILY,
    NINE_SLICE_FAMILY,
    icon_content_task,
    icon_review_prompt,
    sheet_family,
    validate_ui_sheet,
)
from tests.unit._ui_atlas_fixture import icon_sheet, ui_sheet


def test_the_grid_tiles_its_canvas_and_publishes_cells_that_never_touch() -> None:
    cells = PREVIEW_ICONS.cells
    assert len(cells) == 16 == len(PREVIEW_ICONS.glyphs)
    assert all(cell.width == cell.height == PREVIEW_ICONS.cell_size for cell in cells)
    # Reading order: left to right, then top to bottom.
    assert [cell.x for cell in cells[:4]] == sorted(cell.x for cell in cells[:4])
    assert cells[4].y > cells[3].y and cells[4].x == cells[0].x
    for left, right in pairwise(cells):
        if left.y == right.y:
            assert left.x + left.width < right.x
    last = cells[-1]
    assert last.x + last.width <= 1024 and last.y + last.height <= 1024
    with pytest.raises(ValueError, match="tile its canvas"):
        IconGridRole(
            role="x",
            layout="x",
            glyphs=PREVIEW_ICONS.glyphs,
            columns=4,
            rows=4,
            cell=200,
            gutter=48,
            margin=41,
            slack=16,
        )


def test_template_draws_guides_only_and_no_body() -> None:
    with Image.open(io.BytesIO(render_icon_template(PREVIEW_ICONS))) as image:
        assert image.mode == "RGBA" and image.size == PREVIEW_ICONS.canvas
        guide = PREVIEW_ICONS.guide_cells[0]
        assert image.getpixel((guide.x, guide.y + guide.height // 2)) == (0, 255, 255, 255)
        # The middle of a cell is empty: nothing tells the model a cell is a body.
        assert image.getpixel((guide.x + guide.width // 2, guide.y + guide.height // 2)) == (
            0,
            0,
            0,
            0,
        )
        assert image.getpixel((0, 0)) == (0, 0, 0, 0)


def test_a_perfect_sheet_registers_every_glyph_to_its_named_cell() -> None:
    facts = validate_icon_sheet(icon_sheet(PREVIEW_ICONS), PREVIEW_ICONS)
    assert facts["alpha_policy"] == ICON_ALPHA_POLICY
    assert facts["scale_mode"] == "fixed"
    cells = facts["cells"]
    assert isinstance(cells, list)
    assert [entry["glyph"] for entry in cells] == [name for name, _ in PREVIEW_ICON_GLYPHS]
    for entry, cell in zip(cells, PREVIEW_ICONS.cells, strict=True):
        assert entry["cell"] == cell.as_dict()
        glyph = entry["glyph_rect"]
        assert cell.x <= glyph["x"] and glyph["x"] + glyph["width"] <= cell.x + cell.width
        assert entry["alpha_max"] == 255
    set_facts = facts["set"]
    assert isinstance(set_facts, dict)
    assert set_facts["extent_ratio"] < 1.2


def test_each_broken_promise_is_named() -> None:
    role = PREVIEW_ICONS
    with pytest.raises(IconAdmissionError, match=r"cell 3 \(close\): no glyph drawn"):
        validate_icon_sheet(icon_sheet(role, empty_cell=2), role)
    with pytest.raises(IconAdmissionError, match="plate rather than a glyph"):
        validate_icon_sheet(icon_sheet(role, plate_cell=0), role)
    with pytest.raises(IconAdmissionError, match="drawn between or around the cells"):
        validate_icon_sheet(icon_sheet(role, spill_cell=5), role)
    with pytest.raises(IconAdmissionError, match=r"cell 1 \(play\): glyph extent"):
        validate_icon_sheet(icon_sheet(role, tiny_cell=0), role)
    with pytest.raises(IconAdmissionError, match="canvas border alpha"):
        validate_icon_sheet(icon_sheet(role, halo=True), role)


def test_canonicalization_clears_the_exterior_and_leaves_glyph_edges_alone() -> None:
    source = icon_sheet(PREVIEW_ICONS)
    with Image.open(io.BytesIO(source)) as image:
        faint = image.convert("RGBA")
        # Provider noise: a faint wash on the exterior that the gate admits and the
        # canonical sheet must not carry.
        faint.putpixel((5, 5), (255, 255, 255, 12))
        stream = io.BytesIO()
        faint.save(stream, format="PNG")
    canonical, facts = canonicalize_icon_sheet(stream.getvalue(), PREVIEW_ICONS)
    assert facts["pixel_rewrite"] == "alpha_exterior_normalization_v1"
    with Image.open(io.BytesIO(canonical)) as image:
        pixel = image.getpixel((5, 5))
        assert isinstance(pixel, tuple) and pixel[3] == 0
    source_facts = facts["source"]
    canonical_facts = facts["canonical"]
    assert isinstance(source_facts, dict) and isinstance(canonical_facts, dict)
    source_cells = cast(list[dict[str, object]], source_facts["cells"])
    canonical_cells = cast(list[dict[str, object]], canonical_facts["cells"])
    assert [c["glyph_rect"] for c in source_cells] == [c["glyph_rect"] for c in canonical_cells]


def test_contract_and_evidence_carry_what_a_consumer_and_a_judge_need() -> None:
    facts = validate_icon_sheet(icon_sheet(PREVIEW_ICONS), PREVIEW_ICONS)
    contract = icon_role_contract(facts)
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
    assert contract["draw_scale"] == 2 and contract["cell_size"] == 232
    cells = contract["cells"]
    assert isinstance(cells, list) and len(cells) == 16
    assert set(cells[0]) == {"glyph", "cell", "glyph_rect"}
    with Image.open(io.BytesIO(icon_evidence(icon_sheet(PREVIEW_ICONS), facts))) as evidence:
        # The sheet on the left, sixteen annotated rows on the right.
        assert evidence.width > 1024 + 24 and evidence.height >= 16 * 60


def test_the_family_lookup_and_the_shared_gate_agree_on_the_icon_role() -> None:
    assert sheet_family(PREVIEW_ICONS) is ICON_GRID_FAMILY
    assert sheet_family(PREVIEW_ICONS) is not NINE_SLICE_FAMILY
    facts = validate_ui_sheet(ui_sheet("preview_icons"), "preview_icons")
    assert facts["role"] == "preview_icons"
    assert "glyph_identity" in ICON_GRID_FAMILY.review_checks


def test_the_prompt_states_the_fixed_vocabulary_and_the_review_asks_for_identity() -> None:
    prompt = icon_content_task(PREVIEW_ICONS, "flat warm glyphs")
    assert "16 icons in a 4 by 4 grid" in prompt
    assert "1 play (a right-pointing triangle)" in prompt
    assert "16 sound off (a speaker with a cross beside it)" in prompt
    assert "Style direction: flat warm glyphs" in prompt
    assert "these are glyphs and not buttons" in prompt
    review = icon_review_prompt(PREVIEW_ICONS, "flat warm glyphs")
    assert "cell <n> <name>: <what it shows instead>" in review
    assert "annotation added by the validator" in review
