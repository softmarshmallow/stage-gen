from __future__ import annotations

import io

import pytest
from PIL import Image

from stage_gen.components.game_ui import (
    ATLAS_ALPHA_POLICY,
    ATLAS_ROLES,
    BUTTON_RECT,
    PANEL_FRAME,
    AtlasAdmissionError,
    atlas_evidence,
    atlas_role_contract,
    canonicalize_atlas_image,
    render_atlas_template,
    validate_atlas_image,
)
from tests.unit._ui_atlas_fixture import atlas_sheet


def test_template_renders_from_geometry_with_a_magenta_body_per_cell() -> None:
    for role in ATLAS_ROLES.values():
        with Image.open(io.BytesIO(render_atlas_template(role))) as image:
            assert image.mode == "RGBA"
            assert image.size == role.canvas
            for rect in role.cells:
                centre = image.getpixel((rect.x + rect.width // 2, rect.y + rect.height // 2))
                assert centre == (255, 0, 255, 255)
            assert image.getpixel((0, 0)) == (0, 0, 0, 0)


def test_perfect_sheets_admit_stretch_with_identical_state_silhouettes() -> None:
    for role in (PANEL_FRAME, BUTTON_RECT):
        facts = validate_atlas_image(atlas_sheet(role), role)
        assert facts["band_fill"] == "stretch"
        assert facts["alpha_policy"] == ATLAS_ALPHA_POLICY
        cells = facts["cells"]
        assert isinstance(cells, list)
        assert [entry["state"] for entry in cells] == list(role.states)
        state_checks = facts["state_checks"]
        assert isinstance(state_checks, dict)
        for entry in state_checks.values():
            assert entry["silhouette_iou"] == 1.0
            assert entry["size_delta_px"] == 0
            assert entry["distinct_from_normal_mae"] >= 3.0


def test_a_mid_band_medallion_is_admitted_only_under_tile() -> None:
    # A tiled band repeats whole, so a motif away from both ends is a repeating pattern rather
    # than a failure; it is `stretch` that cannot rebuild it from one strip.
    facts = validate_atlas_image(atlas_sheet(PANEL_FRAME, medallion=True), PANEL_FRAME)
    assert facts["band_fill"] == "tile"


def test_a_band_that_drifts_along_its_length_fails_every_fill() -> None:
    for role in (PANEL_FRAME, BUTTON_RECT):
        with pytest.raises(AtlasAdmissionError, match=r"no band fill|stretch|tile|seam"):
            validate_atlas_image(atlas_sheet(role, band_gradient=True), role)


def test_a_state_drawn_wider_breaks_the_shared_silhouette() -> None:
    with pytest.raises(AtlasAdmissionError, match=r"size delta|silhouette"):
        validate_atlas_image(atlas_sheet(BUTTON_RECT, drift_px=24), BUTTON_RECT)


def test_a_missing_body_fails_the_count() -> None:
    with pytest.raises(AtlasAdmissionError, match="detected 3 opaque bodies, declared 4"):
        validate_atlas_image(atlas_sheet(BUTTON_RECT, drop_last=True), BUTTON_RECT)


def test_a_translucent_band_and_an_exterior_glow_fail_the_alpha_policy() -> None:
    with pytest.raises(AtlasAdmissionError, match="band strip alpha"):
        validate_atlas_image(atlas_sheet(PANEL_FRAME, band_alpha=200), PANEL_FRAME)
    with pytest.raises(AtlasAdmissionError, match="border alpha"):
        validate_atlas_image(atlas_sheet(PANEL_FRAME, exterior_glow=True), PANEL_FRAME)


def test_canonicalization_touches_only_the_admitted_alpha_boundary() -> None:
    source = atlas_sheet(BUTTON_RECT)
    with Image.open(io.BytesIO(source)) as opened:
        image = opened.convert("RGBA")
    alpha = image.getchannel("A").point(lambda value: 12 if value == 0 else value)
    image.putalpha(alpha)
    dusty = io.BytesIO()
    image.save(dusty, format="PNG")

    canonical, facts = canonicalize_atlas_image(dusty.getvalue(), BUTTON_RECT)

    assert facts["pixel_rewrite"] == "alpha_boundary_normalization_v1"
    with Image.open(io.BytesIO(canonical)) as opened:
        canonical_alpha = opened.convert("RGBA").getchannel("A")
    assert canonical_alpha.getpixel((0, 0)) == 0
    rect = facts["canonical"]["cells"][0]["content_rect"]  # type: ignore[index]
    assert canonical_alpha.getpixel((rect["x"] + 1, rect["y"] + 1)) == 255


def test_safe_rect_excludes_ornament_that_hangs_into_the_content() -> None:
    plain = validate_atlas_image(atlas_sheet(PANEL_FRAME), PANEL_FRAME)
    cell = plain["cells"][0]  # type: ignore[index]
    assert cell["safe_rect"] == cell["content_rect"]

    # A corner cap that merely curls is absorbed by the widened insets; a tassel hanging from a
    # plain band is not, and the content rect starts on top of it. The safe rect steps below it.
    hung = validate_atlas_image(atlas_sheet(PANEL_FRAME, band_tassel=True), PANEL_FRAME)
    cell = hung["cells"][0]  # type: ignore[index]
    content, safe = cell["content_rect"], cell["safe_rect"]
    assert safe["y"] >= content["y"] + 24
    assert safe["x"] == content["x"]
    assert safe["width"] == content["width"]
    assert safe["y"] + safe["height"] == content["y"] + content["height"]


def test_role_contract_and_evidence_carry_what_a_consumer_needs() -> None:
    facts = validate_atlas_image(atlas_sheet(BUTTON_RECT), BUTTON_RECT)
    contract = atlas_role_contract(facts)

    assert set(contract) == {
        "role",
        "layout",
        "scale_mode",
        "alpha_policy",
        "band_fill",
        "draw_scale",
        "canvas",
        "insets",
        "cells",
    }
    assert contract["scale_mode"] == "nine_slice"
    assert contract["draw_scale"] == 2
    cells = contract["cells"]
    assert isinstance(cells, list)
    assert len(cells) == 4
    insets = contract["insets"]
    assert isinstance(insets, dict)
    first = cells[0]
    assert set(first) == {"state", "cell", "content_rect", "safe_rect"}
    assert first["content_rect"]["x"] == first["cell"]["x"] + insets["left"]
    assert first["content_rect"]["width"] == (
        first["cell"]["width"] - insets["left"] - insets["right"]
    )
    with Image.open(io.BytesIO(atlas_evidence(atlas_sheet(BUTTON_RECT), facts))) as evidence:
        # The sheet at full size on the left, the redraws at consumer density on the right.
        assert 1024 < evidence.width < 1024 + 24 + 1024
