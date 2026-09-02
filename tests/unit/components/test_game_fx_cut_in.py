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
    admit_cut_in_placement,
    canonicalize_plate,
    compose_hold_frame,
    cut_in_evidence,
    draw_procedural_frame,
    mask_reveal_facts,
    trace_mask_polygon,
    validate_frame_plate,
    validate_portrait_plate,
)

_SHA = "a" * 64
_PLACEMENT = {"scale": 0.45, "x": 0.5, "y": 0.52, "rationale": "Eyes in the upper band."}


def _admitted(**overrides: object) -> dict[str, object]:
    return admit_cut_in_placement(
        {**_PLACEMENT, **overrides}, portrait_sha256=_SHA, frame_sha256=_SHA
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
    specks: int = 0,
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
    for index in range(specks):
        left = width * (0.1 + index * 0.05)
        draw.ellipse((left, height * 0.1, left + 12, height * 0.1 + 12), fill=255)
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
        ({"span": 0.4}, "under 0.6"),
        ({"specks": 6}, "specks"),
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
    polygon = trace_mask_polygon(alpha)
    assert polygon is not None
    assert 4 <= len(polygon) <= MASK_POLYGON_MAX_VERTICES
    xs = [x for x, _ in polygon]
    ys = [y for _, y in polygon]
    assert all(0.0 <= v <= 1.0 for v in xs + ys)
    # The band sits around the vertical centre (the fixture tilts it 40 px) and the
    # mask sits inside the rim: eroded by MASK_ERODE_PX from both torn edges.
    assert 0.20 < min(ys) < 0.45
    assert 0.55 < max(ys) < 0.80


def test_an_authored_shape_the_gate_now_allows_publishes_no_lying_outline() -> None:
    # Two shards and a punched hole are shapes, not defects: the gate admits them and
    # the runtime clips with the plate's alpha either way.
    shards = validate_frame_plate(frame_plate(split=True))
    assert shards["components"] == 2
    assert validate_frame_plate(frame_plate(hole=True))["holes"] == 1
    with Image.open(io.BytesIO(frame_plate(split=True))) as opened:
        alpha = opened.convert("RGBA").getchannel("A")
    # No single outline describes two shards, so none is published.
    assert trace_mask_polygon(alpha) is None
    _canonical, facts = canonicalize_plate(frame_plate(split=True), CUT_IN_FRAME)
    assert facts["geometry"]["mask_polygon"] is None


def test_canonicalization_clears_only_the_exterior_and_publishes_geometry() -> None:
    canonical, facts = canonicalize_plate(frame_plate(), CUT_IN_FRAME)
    with Image.open(io.BytesIO(canonical)) as opened:
        alpha = opened.convert("RGBA").getchannel("A")
    assert alpha.getpixel((5, 5)) == 0
    geometry = facts["geometry"]
    assert geometry["role"] == "frame"
    assert geometry["layout"] == "cut_in_frame_1536x1024_v1"
    assert geometry["mask_polygon"] is not None and len(geometry["mask_polygon"]) >= 4
    assert geometry["band_rect"]["width"] == CUT_IN_CANVAS[0]
    assert facts["pixel_rewrite"] == "alpha_exterior_clear_v1"
    json.dumps(facts)  # the record is plain JSON

    _portrait, portrait_facts = canonicalize_plate(
        portrait_plate(), CUT_IN_PORTRAIT, placement=_admitted()
    )
    assert portrait_facts["geometry"]["role"] == "portrait"
    assert "alpha_rect" in portrait_facts["geometry"]
    assert "mask_polygon" not in portrait_facts["geometry"]
    # The placement a consumer reads is the three numbers, not the admission envelope.
    assert portrait_facts["geometry"]["placement"] == {"scale": 0.45, "x": 0.5, "y": 0.52}
    _bare, bare_facts = canonicalize_plate(portrait_plate(), CUT_IN_PORTRAIT)
    assert "placement" not in bare_facts["geometry"]


def test_evidence_composes_the_portrait_at_its_placement_through_the_frames_polygon() -> None:
    frame, frame_facts = canonicalize_plate(frame_plate(), CUT_IN_FRAME)
    # A small portrait parked at the right of the band: the left of the band shows
    # the backdrop, the placed centre shows the portrait's skin colour.
    placement = _admitted(scale=0.3, x=0.75, y=0.5)
    portrait, portrait_facts = canonicalize_plate(
        portrait_plate(), CUT_IN_PORTRAIT, placement=placement
    )
    portrait_facts["frame_geometry"] = frame_facts["geometry"]
    evidence = cut_in_evidence(portrait, portrait_facts, frame_data=frame)
    with Image.open(io.BytesIO(evidence)) as opened:
        assert opened.width == 1280
        rgb = opened.convert("RGB")
        half = 640 / 1536
        band_y = round((0.5 * 1024 - 40 * 0.08) * half)
        left = rgb.getpixel((640 + round(120 * half), band_y))
        centre = rgb.getpixel((640 + round(0.75 * 1536 * half), band_y))
    assert isinstance(left, tuple) and isinstance(centre, tuple)
    assert left[0] > 180 and left[2] < 120  # vermilion backdrop, or its stripe
    assert abs(centre[0] - 210) < 25 and abs(centre[1] - 160) < 25  # the portrait's skin
    frame_only = cut_in_evidence(frame, frame_facts)
    with Image.open(io.BytesIO(frame_only)) as opened:
        assert opened.width == 1280


def test_hold_frame_puts_the_portrait_centre_where_the_placement_says() -> None:
    frame, _frame_facts = canonicalize_plate(frame_plate(), CUT_IN_FRAME)
    small = compose_hold_frame(frame, portrait_plate(), placement=_admitted(scale=0.2))
    large = compose_hold_frame(frame, portrait_plate(), placement=_admitted(scale=0.6))
    # Same centre, the larger scale reaches further along the band's centre line.
    probe_y = round(0.5 * 1024)
    far_x = round((0.5 + 0.18) * 1536)
    small_pixel = small.getpixel((far_x, probe_y))
    large_pixel = large.getpixel((far_x, probe_y))
    assert isinstance(small_pixel, tuple) and isinstance(large_pixel, tuple)
    assert small_pixel[0] > 180 and small_pixel[2] < 120  # backdrop beyond a small portrait
    assert abs(large_pixel[0] - 210) < 25 and abs(large_pixel[1] - 160) < 25
    with pytest.raises(ValueError, match="needs a placement"):
        compose_hold_frame(frame, portrait_plate())


def test_the_agents_facts_are_read_from_the_mask_not_from_the_outline() -> None:
    with Image.open(io.BytesIO(frame_plate())) as opened:
        facts = mask_reveal_facts(opened.convert("RGBA").getchannel("A"))
    centre_x, centre_y = facts["centroid"]
    assert 0.45 < centre_x < 0.55
    assert 0.45 < centre_y < 0.55
    middle = facts["columns"][2]
    assert middle["x"] == 0.5
    assert 0.25 < middle["top"] < 0.45 and 0.55 < middle["bottom"] < 0.75

    # A hole the traced outline smooths over still shows up as a column less open,
    # and a column the shape does not reach reports no span at all.
    with Image.open(io.BytesIO(frame_plate(hole=True))) as opened:
        punched = mask_reveal_facts(opened.convert("RGBA").getchannel("A"))
    assert punched["columns"][2]["filled"] < middle["filled"]
    with Image.open(io.BytesIO(frame_plate(split=True))) as opened:
        shards = mask_reveal_facts(opened.convert("RGBA").getchannel("A"))
    assert "top" not in shards["columns"][2]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"scale": 0.0}, "scale must be between"),
        ({"scale": 3.0}, "scale must be between"),
        ({"x": float("nan")}, "x must be a finite number"),
        ({"y": 5}, "y must be between"),
        ({"scale": "0.5"}, "scale must be a finite number"),
        ({"rationale": "  "}, "must carry a rationale"),
    ],
)
def test_each_broken_placement_promise_is_named(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _admitted(**overrides)


def test_placement_admission_binds_the_plates_and_rounds_the_numbers() -> None:
    record = admit_cut_in_placement(
        {"scale": 0.44444444, "x": 0.5, "y": 0.52, "rationale": "  fits  the band "},
        portrait_sha256="p" * 64,
        frame_sha256="f" * 64,
    )
    assert record == {
        "schema_version": 1,
        "kind": "fx-cut-in-placement-v1",
        "scale": 0.4444,
        "x": 0.5,
        "y": 0.52,
        "rationale": "fits the band",
        "portrait_sha256": "p" * 64,
        "frame_sha256": "f" * 64,
    }
    with pytest.raises(ValueError, match="must be an object"):
        admit_cut_in_placement([0.5], portrait_sha256=_SHA, frame_sha256=_SHA)
