"""The cut-in plate gates over synthetic plates. Each knob breaks exactly one promise."""

from __future__ import annotations

import io
import json

import pytest
from PIL import Image, ImageDraw

from stage_gen.components.game_fx import (
    CUT_IN_CANVAS,
    CUT_IN_FRAME,
    CUT_IN_PORTRAIT,
    MASK_POLYGON_MAX_VERTICES,
    CutInAdmissionError,
    canonicalize_plate,
    cut_in_evidence,
    draw_procedural_frame,
    trace_band_polygon,
    validate_frame_plate,
    validate_portrait_plate,
)


def _png(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def frame_plate(
    *,
    band: float = 0.45,
    ink: int = 14,
    hole: bool = False,
    split: bool = False,
    span: float = 1.0,
    glow: bool = False,
    grey_fill: bool = False,
) -> bytes:
    """A clean torn strip; each knob breaks one promise of the frame contract."""

    width, height = CUT_IN_CANVAS
    top = height * (0.5 - band / 2)
    bottom = height * (0.5 + band / 2)
    x1 = width * span
    fill = Image.new("L", CUT_IN_CANVAS, 0)
    draw = ImageDraw.Draw(fill)
    if split:
        draw.polygon([(0, top), (width * 0.45, top), (width * 0.45, bottom), (0, bottom)], fill=255)
        draw.polygon(
            [(width * 0.55, top), (x1, top), (x1, bottom), (width * 0.55, bottom)], fill=255
        )
    else:
        draw.polygon([(0, top), (x1, top - 40), (x1, bottom - 40), (0, bottom)], fill=255)
    if hole:
        draw.ellipse((width * 0.4, height * 0.45, width * 0.5, height * 0.55), fill=0)
    plate = Image.new("RGBA", CUT_IN_CANVAS, (0, 0, 0, 0))
    grown = fill.filter(
        __import__("PIL.ImageFilter", fromlist=["MaxFilter"]).MaxFilter(ink * 2 + 1)
    )
    plate.paste(Image.new("RGBA", CUT_IN_CANVAS, (10, 10, 10, 255)), mask=grown)
    colour = (140, 140, 140, 255) if grey_fill else (255, 255, 255, 255)
    plate.paste(Image.new("RGBA", CUT_IN_CANVAS, colour), mask=fill)
    if glow:
        halo = Image.new("RGBA", CUT_IN_CANVAS, (255, 255, 255, 60))
        plate.alpha_composite(halo)
    return _png(plate)


def portrait_plate(*, coverage: float = 0.7, wash: bool = False, twin: bool = False) -> bytes:
    width, height = CUT_IN_CANVAS
    plate = Image.new("RGBA", CUT_IN_CANVAS, (0, 0, 0, 0))
    draw = ImageDraw.Draw(plate)
    radius_x = width * coverage / 2
    draw.ellipse(
        (width / 2 - radius_x, -height * 0.1, width / 2 + radius_x, height * 1.1),
        fill=(210, 160, 130, 255),
    )
    # Shoulders run off the bottom edge the way a cropped bust does.
    draw.rectangle(
        (width / 2 - radius_x * 1.1, height * 0.7, width / 2 + radius_x * 1.1, height),
        fill=(90, 70, 160, 255),
    )
    if twin:
        draw.ellipse((0, 0, width * 0.18, height * 0.18), fill=(210, 160, 130, 255))
    if wash:
        plate.alpha_composite(Image.new("RGBA", CUT_IN_CANVAS, (90, 40, 20, 40)))
    return _png(plate)


def test_a_clean_strip_and_the_procedural_frame_pass_the_same_gate() -> None:
    for data in (frame_plate(), draw_procedural_frame()):
        facts = validate_frame_plate(data)
        assert facts["components"] == 1
        assert facts["holes"] == 0
        assert facts["width_span"] >= 0.95
        assert facts["white_share"] > 0.55


@pytest.mark.parametrize(
    ("knob", "message"),
    [
        ({"hole": True}, "holes"),
        ({"split": True}, "shapes, not one"),
        ({"span": 0.7}, "edge to edge"),
        ({"glow": True}, "glow"),
        ({"grey_fill": True}, "flat white"),
        ({"band": 0.9}, "coverage"),
        ({"ink": 0}, "ink share"),
    ],
)
def test_each_broken_frame_promise_is_named(knob: dict[str, object], message: str) -> None:
    with pytest.raises(CutInAdmissionError, match=message):
        validate_frame_plate(frame_plate(**knob))  # type: ignore[arg-type]


def test_the_frame_gate_refuses_the_wrong_canvas() -> None:
    with pytest.raises(CutInAdmissionError, match="exactly 1536x1024"):
        validate_frame_plate(_png(Image.new("RGBA", (1024, 1024), (255, 255, 255, 255))))


def test_a_die_cut_portrait_passes_and_records_its_bleed() -> None:
    facts = validate_portrait_plate(portrait_plate())
    assert facts["components"] == 1
    assert facts["bleeds_top"] is True
    assert facts["bleeds_bottom"] is True
    assert facts["alpha_rect"]["width"] > 0


@pytest.mark.parametrize(
    ("knob", "message"),
    [
        ({"wash": True}, "glow or wash"),
        ({"twin": True}, "not one subject"),
        ({"coverage": 0.2}, "coverage"),
    ],
)
def test_each_broken_portrait_promise_is_named(knob: dict[str, object], message: str) -> None:
    with pytest.raises(CutInAdmissionError, match=message):
        validate_portrait_plate(portrait_plate(**knob))  # type: ignore[arg-type]


def test_the_mask_polygon_is_the_eroded_band_within_the_vertex_budget() -> None:
    with Image.open(io.BytesIO(frame_plate())) as opened:
        alpha = opened.convert("RGBA").getchannel("A")
    polygon = trace_band_polygon(alpha)
    assert 4 <= len(polygon) <= MASK_POLYGON_MAX_VERTICES
    xs = [x for x, _ in polygon]
    ys = [y for _, y in polygon]
    assert all(0.0 <= v <= 1.0 for v in xs + ys)
    # The band sits around the vertical centre (the fixture tilts it 40 px) and the
    # mask sits inside the rim: eroded by MASK_ERODE_PX from both torn edges.
    assert 0.20 < min(ys) < 0.45
    assert 0.55 < max(ys) < 0.80


def test_canonicalization_clears_only_the_exterior_and_publishes_geometry() -> None:
    canonical, facts = canonicalize_plate(frame_plate(), CUT_IN_FRAME)
    with Image.open(io.BytesIO(canonical)) as opened:
        alpha = opened.convert("RGBA").getchannel("A")
    assert alpha.getpixel((5, 5)) == 0
    geometry = facts["geometry"]
    assert geometry["role"] == "frame"
    assert geometry["layout"] == "cut_in_frame_1536x1024_v1"
    assert len(geometry["mask_polygon"]) >= 4
    assert geometry["band_rect"]["width"] == CUT_IN_CANVAS[0]
    assert facts["pixel_rewrite"] == "alpha_exterior_clear_v1"
    json.dumps(facts)  # the record is plain JSON

    _portrait, portrait_facts = canonicalize_plate(portrait_plate(), CUT_IN_PORTRAIT)
    assert portrait_facts["geometry"]["role"] == "portrait"
    assert "alpha_rect" in portrait_facts["geometry"]
    assert "mask_polygon" not in portrait_facts["geometry"]


def test_evidence_composes_the_portrait_through_the_frames_polygon() -> None:
    frame, frame_facts = canonicalize_plate(frame_plate(), CUT_IN_FRAME)
    portrait, portrait_facts = canonicalize_plate(portrait_plate(), CUT_IN_PORTRAIT)
    portrait_facts["frame_geometry"] = frame_facts["geometry"]
    evidence = cut_in_evidence(portrait, portrait_facts, frame_data=frame)
    with Image.open(io.BytesIO(evidence)) as opened:
        assert opened.width == 1280
        # The composed half shows the backdrop through the mask beside the portrait:
        # vermilion (or its stripe) at the band's centre near the left edge.
        band_y = round((0.5 * 1024 - 40 * 0.08) * 640 / 1536)
        pixel = opened.convert("RGB").getpixel((640 + round(120 * 640 / 1536), band_y))
    assert isinstance(pixel, tuple)
    r, _g, b = pixel[:3]
    assert r > 180 and b < 120
    frame_only = cut_in_evidence(frame, frame_facts)
    with Image.open(io.BytesIO(frame_only)) as opened:
        assert opened.width == 1280
