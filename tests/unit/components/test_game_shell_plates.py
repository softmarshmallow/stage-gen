"""The shell plate gate, and the fan-out that decides which plates get drawn.

The gate's whole reason to exist is the legibility check: a full-screen picture is almost
entirely a matter of judgement, except for whether the areas the layout reserved are calm
enough to set a title or a button over. These prove that the measurable part is measured
and that the unmeasurable part is left alone.
"""

from __future__ import annotations

from io import BytesIO
from typing import cast

import pytest
from PIL import Image, ImageDraw

from stage_gen.components.game_shell import (
    LOADING_SCREEN,
    OPENING_SHOT,
    SHELL_CANVAS,
    TITLE_SCREEN,
    load_game_shell_bytes,
)
from stage_gen.components.game_shell.nodes import (
    document_plate_roles,
    plate_content_task,
)
from stage_gen.components.game_shell.plates import (
    ShellPlateError,
    canonicalize_shell_plate,
    shell_plate_evidence,
    validate_shell_plate,
)

OPAQUE = "fully_opaque_v1"
CUTOUT = "transparent_exterior_v1"


def _png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def _flat(colour: tuple[int, int, int, int] = (30, 44, 60, 255)) -> Image.Image:
    return Image.new("RGBA", SHELL_CANVAS, colour)


# --- the backdrop gate --------------------------------------------------------


def test_a_calm_backdrop_is_admitted_and_reports_which_text_colour_reads() -> None:
    record = validate_shell_plate(
        _png(_flat()),
        layout=TITLE_SCREEN,
        alpha_policy=OPAQUE,
        measured_regions=("mark_band", "control_stack"),
    )

    regions = record["regions"]
    assert isinstance(regions, list) and len(regions) == 2
    measured = [cast(dict[str, object], entry) for entry in regions]
    assert all(entry["passed"] for entry in measured)
    assert measured[0]["best_text"] == "white"


def test_a_busy_reserved_region_is_refused_however_good_the_painting_is() -> None:
    busy = _flat()
    draw = ImageDraw.Draw(busy)
    for x in range(0, SHELL_CANVAS[0], 12):
        draw.line((x, 0, x, SHELL_CANVAS[1]), fill=(240, 230, 210, 255), width=6)

    with pytest.raises(ShellPlateError, match="not quiet enough to set text on"):
        validate_shell_plate(
            _png(busy), layout=TITLE_SCREEN, alpha_policy=OPAQUE, measured_regions=("mark_band",)
        )


def test_a_region_is_measured_over_the_drift_the_host_may_apply() -> None:
    """Quiet in the still frame is not quiet: the title parallaxes its layers."""

    plate = _flat()
    band = TITLE_SCREEN.region("mark_band")
    draw = ImageDraw.Draw(plate)
    # A hard bright edge just outside the still band, inside the drift union.
    draw.rectangle(
        (band.x - 80, band.y - 80, band.x + band.width + 80, band.y - 20),
        fill=(255, 250, 240, 255),
    )

    with pytest.raises(ShellPlateError, match="mark_band"):
        validate_shell_plate(
            _png(plate), layout=TITLE_SCREEN, alpha_policy=OPAQUE, measured_regions=("mark_band",)
        )


def test_a_backdrop_with_a_hole_is_refused() -> None:
    holed = _flat()
    holed.putpixel((100, 100), (0, 0, 0, 0))

    with pytest.raises(ShellPlateError, match="hole in it"):
        validate_shell_plate(_png(holed), layout=TITLE_SCREEN, alpha_policy=OPAQUE)


def test_a_plate_on_the_wrong_canvas_is_refused_by_name() -> None:
    small = Image.new("RGBA", (1024, 1024), (30, 44, 60, 255))

    with pytest.raises(ShellPlateError, match="1024x1024"):
        validate_shell_plate(_png(small), layout=TITLE_SCREEN, alpha_policy=OPAQUE)


def test_a_region_the_layout_does_not_reserve_is_refused() -> None:
    with pytest.raises(ShellPlateError, match="reserves no region"):
        validate_shell_plate(
            _png(_flat()),
            layout=LOADING_SCREEN,
            alpha_policy=OPAQUE,
            measured_regions=("mark_band",),
        )


# --- the cut-out gate ---------------------------------------------------------


def _emblem() -> Image.Image:
    plate = Image.new("RGBA", SHELL_CANVAS, (0, 0, 0, 0))
    ImageDraw.Draw(plate).ellipse((1000, 500, 1560, 940), fill=(200, 120, 60, 255))
    return plate


def test_one_shape_on_air_is_admitted() -> None:
    record = validate_shell_plate(_png(_emblem()), layout=TITLE_SCREEN, alpha_policy=CUTOUT)

    alpha = record["alpha"]
    assert isinstance(alpha, dict)
    assert alpha["piece_count"] == 1


def test_a_badge_of_several_pieces_is_admitted_because_an_emblem_is_not_one_shape() -> None:
    """A broken ring around a charge is two pieces, and it is what a badge looks like.

    The first cut of this gate demanded one connected shape, borrowed from the cut-in
    portrait rule. It refused six straight draws of exactly what the brief described.
    """

    badge = Image.new("RGBA", SHELL_CANVAS, (0, 0, 0, 0))
    draw = ImageDraw.Draw(badge)
    draw.arc((1000, 420, 1560, 980), start=200, end=520, fill=(40, 36, 34, 255), width=60)
    draw.polygon(
        [(1230, 560), (1290, 760), (1350, 560), (1330, 860), (1250, 860)],
        fill=(220, 140, 60, 255),
    )

    record = validate_shell_plate(_png(badge), layout=TITLE_SCREEN, alpha_policy=CUTOUT)

    alpha = record["alpha"]
    assert isinstance(alpha, dict)
    assert alpha["piece_count"] == 2


def test_a_scatter_is_refused_because_an_emblem_is_a_compact_mark() -> None:
    """Measured by extent, not area: a row of blobs has a small bounding-box area."""

    scatter = Image.new("RGBA", SHELL_CANVAS, (0, 0, 0, 0))
    draw = ImageDraw.Draw(scatter)
    for x in range(400, 2200, 400):
        draw.ellipse((x, 600, x + 300, 900), fill=(200, 120, 60, 255))

    with pytest.raises(ShellPlateError, match="spread across the canvas"):
        validate_shell_plate(_png(scatter), layout=TITLE_SCREEN, alpha_policy=CUTOUT)


def test_a_cut_out_that_fills_the_canvas_is_a_backdrop_not_an_emblem() -> None:
    with pytest.raises(ShellPlateError, match="covers"):
        validate_shell_plate(
            _png(_flat((200, 120, 60, 255))), layout=TITLE_SCREEN, alpha_policy=CUTOUT
        )


# --- canonicalization and evidence -------------------------------------------


def test_an_opaque_plate_is_flattened_so_no_hairline_shows_through() -> None:
    nearly = _flat((30, 44, 60, 252))

    data, rewrite = canonicalize_shell_plate(_png(nearly), alpha_policy=OPAQUE)

    assert rewrite["pixel_rewrite"] == "alpha_flatten_v1"
    assert Image.open(BytesIO(data)).getchannel("A").getextrema() == (255, 255)


def test_a_cut_outs_own_drawn_edge_survives_canonicalization() -> None:
    """An emblem's antialiasing is its drawing; only the exterior and the core move."""

    plate = Image.new("RGBA", SHELL_CANVAS, (0, 0, 0, 0))
    ImageDraw.Draw(plate).ellipse((1000, 500, 1560, 940), fill=(200, 120, 60, 255))
    plate.putpixel((1200, 700), (200, 120, 60, 128))

    data, rewrite = canonicalize_shell_plate(_png(plate), alpha_policy=CUTOUT)

    assert rewrite["pixel_rewrite"] == "alpha_exterior_clear_and_core_lift_v1"
    pixel = Image.open(BytesIO(data)).getpixel((1200, 700))
    assert isinstance(pixel, tuple) and pixel[3] == 128


def test_the_evidence_outlines_every_measured_region_without_covering_it() -> None:
    record = validate_shell_plate(
        _png(_flat()),
        layout=TITLE_SCREEN,
        alpha_policy=OPAQUE,
        measured_regions=("mark_band",),
    )

    evidence = Image.open(BytesIO(shell_plate_evidence(_png(_flat()), record))).convert("RGBA")
    band = TITLE_SCREEN.drift_union("mark_band")
    # The outline sits outside the measured rect; the pixels judged are untouched.
    assert evidence.getpixel((band.x + 10, band.y + 10)) == (30, 44, 60, 255)
    assert evidence.getpixel((band.x - 2, band.y + 10)) == (0, 255, 255, 255)


# --- the fan-out --------------------------------------------------------------

DIGEST = "a" * 64
FONT = "b" * 64
DOCUMENT = f"""
schema_version = 3
kind = "game-shell-v3"
game_id = "ember-hollow"
revision = 1

[[references]]
reference_id = "style_plate"
source = "references/style-plate.png"
source_sha256 = "{DIGEST}"
rights_status = "redistribution-approved"
rights_basis = ["Digest-bound reviewed package evidence."]

[typeface]
family = "Fredoka"
source = "fonts/fredoka-variable.ttf"
source_sha256 = "{FONT}"
license = "OFL-1.1"
license_source = "fonts/OFL.txt"
copyright = "Copyright 2016 The Fredoka Project Authors"
upstream_source = "google/fonts"
retrieved = "2026-08-24"

[opening]
layout = "opening_16x9_v1"

[[opening.shots]]
shot_id = "carded"
seconds = 4.0
card = "Winter comes early to the hollow."

[opening.shots.plate]
mode = "still"
alpha_policy = "fully_opaque_v1"
reference_ids = ["style_plate"]
prompt = "A wide cold valley under low cloud."

[[opening.shots]]
shot_id = "silent"
seconds = 3.0

[opening.shots.plate]
mode = "still"
alpha_policy = "fully_opaque_v1"
reference_ids = ["style_plate"]
prompt = "The edge of a conifer wood at dusk."

[title]
layout = "title_screen_16x9_v1"

[[title.backdrop]]
depth = "far"

[title.backdrop.plate]
mode = "still"
alpha_policy = "fully_opaque_v1"
reference_ids = ["style_plate"]
prompt = "The hollow at blue dusk from a low rise."

[loading]
layout = "loading_screen_16x9_v1"

[loading.backdrop]
source = "run_artifact"
artifact_role = "season_look_winter"
"""


def test_only_a_shot_that_carries_a_card_is_gated_on_the_card_band() -> None:
    """Refusing a full-bleed shot for a band nothing is drawn in throws away good art."""

    roles = {
        role.role: role for role in document_plate_roles(load_game_shell_bytes(DOCUMENT.encode()))
    }

    assert roles["opening_carded"].measured_regions == ("card_band",)
    # The backdrop answers for the mark band only: the controls sit on opaque
    # button bodies from ui.toml, so the picture under them need not be quiet.
    assert roles["title_backdrop_far"].measured_regions == ("mark_band",)
    assert roles["opening_silent"].measured_regions == ()
    assert roles["opening_carded"].layout is OPENING_SHOT


def test_a_backdrop_bound_to_existing_run_art_is_never_billed() -> None:
    roles = document_plate_roles(load_game_shell_bytes(DOCUMENT.encode()))

    assert "loading_backdrop" not in {role.role for role in roles}
    assert len(roles) == 3


def test_the_composed_prompt_carries_the_quiet_clause_and_the_text_ban() -> None:
    """Without the quiet clause the gate refuses good paintings inside the retry budget."""

    roles = {
        role.role: role for role in document_plate_roles(load_game_shell_bytes(DOCUMENT.encode()))
    }
    task = plate_content_task(roles["title_backdrop_far"])

    assert "stays quiet" in task
    assert "upper middle of the frame" in task
    assert "no letters" in task
    assert "edge to edge" in task
