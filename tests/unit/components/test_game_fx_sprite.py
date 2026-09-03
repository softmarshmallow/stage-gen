"""The dust atlas gate: four separated clouds, and what each refusal protects."""

from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw

from stage_gen.components.game_fx.sprite import (
    DUST_CELL_FILL_MIN,
    DUST_CELL_KINDS,
    DUST_CELL_MIN_SIDE,
    DUST_SPECK_COUNT_MAX,
    SPRITE_CANVAS,
    SpriteAdmissionError,
    canonicalize_dust_atlas,
    dust_atlas_contract,
    validate_dust_atlas,
)

#: Where each cell's cloud is drawn, in reading order, as canvas fractions.
_QUARTERS = ((0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75))
#: The four silhouettes the layout names: low-wide, tall-rounded, small-compact, swept.
_SHAPES = ((0.20, 0.10), (0.09, 0.14), (0.07, 0.07), (0.15, 0.09))


def dust_atlas(
    *,
    clouds: int = 4,
    specks: int = 0,
    body_alpha: int = 254,
    thin: bool = False,
    wispy: bool = False,
    merged: bool = False,
    size: tuple[int, int] = SPRITE_CANVAS,
) -> bytes:
    """A clean four-cloud sheet; each knob breaks one promise of the atlas contract."""

    width, height = size
    plate = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(plate)
    for index in range(clouds):
        centre_x, centre_y = _QUARTERS[index % 4]
        if merged and index == 1:
            # Drag the second cloud left until it touches the first.
            centre_x = 0.42
        radius_x, radius_y = _SHAPES[index % 4]
        if thin and index == 2:
            radius_y = DUST_CELL_MIN_SIDE / 4 / height
        cx, cy = centre_x * width, centre_y * height
        if wispy and index == 3:
            # One connected ring: the bounding box of a cloud, with almost none of it filled.
            # This is what a sheet of trailing wisps measures like, and what dies at 40 px.
            draw.ellipse(
                (
                    cx - radius_x * width,
                    cy - radius_y * height,
                    cx + radius_x * width,
                    cy + radius_y * height,
                ),
                outline=(240, 234, 218, body_alpha),
                width=18,
            )
            continue
        draw.ellipse(
            (
                cx - radius_x * width,
                cy - radius_y * height,
                cx + radius_x * width,
                cy + radius_y * height,
            ),
            fill=(240, 234, 218, body_alpha),
        )
    for speck in range(specks):
        # Big enough to survive the mask downsample, far under the share that makes a cloud.
        x = width * (0.02 + 0.022 * speck)
        draw.ellipse((x, height * 0.5, x + 14, height * 0.5 + 14), fill=(240, 234, 218, body_alpha))
    stream = io.BytesIO()
    plate.save(stream, format="PNG")
    return stream.getvalue()


def test_a_clean_sheet_is_four_clouds_one_to_a_quarter_named_in_reading_order() -> None:
    facts = validate_dust_atlas(dust_atlas())
    assert facts["clouds"] == 4
    assert facts["specks"] == 0
    assert [cell["kind"] for cell in facts["cells"]] == list(DUST_CELL_KINDS)
    # Reading order is the layout's promise: each cell sits in the quarter its kind names.
    width, height = SPRITE_CANVAS
    for index, cell in enumerate(facts["cells"]):
        expect_x, expect_y = _QUARTERS[index]
        assert abs((cell["x"] + cell["width"] / 2) / width - expect_x) < 0.05
        assert abs((cell["y"] + cell["height"] / 2) / height - expect_y) < 0.05


def test_the_published_cells_are_the_shapes_the_brief_asked_for() -> None:
    cells = {cell["kind"]: cell for cell in validate_dust_atlas(dust_atlas())["cells"]}
    assert cells["land"]["width"] > cells["land"]["height"]
    assert cells["takeoff"]["height"] > cells["takeoff"]["width"]
    assert cells["stride"]["width"] < cells["land"]["width"]


def test_canonicalization_lifts_the_providers_254_body_to_fully_opaque() -> None:
    # The measured provider behaviour: a flat fill comes back one step below opaque, and a
    # consumer compositing that over a lit background shows a hairline of it through the paint.
    raw = dust_atlas(body_alpha=254)
    assert validate_dust_atlas(raw)["max_alpha"] == 254
    canonical, facts = canonicalize_dust_atlas(raw)
    assert facts["source"]["max_alpha"] == 254
    assert facts["canonical"]["max_alpha"] == 255
    assert validate_dust_atlas(canonical)["max_alpha"] == 255
    assert facts["pixel_rewrite"] == "alpha_exterior_clear_body_lift_and_speck_clear_v1"


def test_a_few_specks_are_measured_around_and_erased_rather_than_refused() -> None:
    raw = dust_atlas(specks=4)
    facts = validate_dust_atlas(raw)
    assert facts["clouds"] == 4
    assert facts["specks"] == 4
    _, record = canonicalize_dust_atlas(raw)
    assert record["canonical"]["specks"] == 0
    assert record["canonical"]["clouds"] == 4


def test_the_contract_projection_carries_the_cells_a_consumer_reads() -> None:
    _, facts = canonicalize_dust_atlas(dust_atlas())
    contract = dust_atlas_contract(facts)
    assert contract["layout"] == "fx_dust_atlas_1024x1024_v1"
    assert contract["canvas"] == {"width": 1024, "height": 1024}
    cells = contract["cells"]
    assert isinstance(cells, list)
    assert [cell["kind"] for cell in cells] == list(DUST_CELL_KINDS)
    for cell in cells:
        assert cell["width"] > 0 and cell["height"] > 0
        assert cell["x"] >= 0 and cell["x"] + cell["width"] <= 1024


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"clouds": 3}, "not 4"),
        ({"clouds": 1}, "not 4"),
        ({"specks": DUST_SPECK_COUNT_MAX + 4}, "sprayed"),
        ({"thin": True}, "thinner than"),
        ({"wispy": True}, "wisps rather than a cloud"),
        # Two clouds nearer than a mask block are one piece, and the count says so.
        ({"merged": True}, "not 4"),
        ({"size": (512, 512)}, "exactly 1024x1024"),
    ],
)
def test_the_gate_refuses_what_a_consumer_could_not_use(
    kwargs: dict[str, object], expected: str
) -> None:
    with pytest.raises(SpriteAdmissionError) as error:
        validate_dust_atlas(dust_atlas(**kwargs))  # type: ignore[arg-type]
    assert any(expected in reason for reason in error.value.reasons)


def test_an_empty_canvas_and_a_non_png_are_both_refused_before_anything_is_measured() -> None:
    with pytest.raises(SpriteAdmissionError):
        validate_dust_atlas(dust_atlas(clouds=0))
    with pytest.raises(SpriteAdmissionError) as error:
        validate_dust_atlas(b"not a png at all")
    assert any("decodable PNG" in reason for reason in error.value.reasons)


def test_every_refusal_is_reported_together_so_one_run_learns_them_all() -> None:
    with pytest.raises(SpriteAdmissionError) as error:
        validate_dust_atlas(dust_atlas(thin=True, wispy=True))
    assert len(error.value.reasons) >= 2
    assert any("thinner than" in reason for reason in error.value.reasons)
    assert any("wisps" in reason for reason in error.value.reasons)


def test_a_wispy_cloud_is_refused_for_what_it_measures_not_for_how_it_looks() -> None:
    # The spike's finding, as a threshold: a shape can have the bounding box of a cloud and
    # still be trailing wisps, and it is the fill that tells them apart.
    with pytest.raises(SpriteAdmissionError) as error:
        validate_dust_atlas(dust_atlas(wispy=True))
    reason = next(r for r in error.value.reasons if "wisps" in r)
    measured = float(reason.split("fills ")[1].split(" ")[0])
    assert measured < DUST_CELL_FILL_MIN
