from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw

from stage_gen.media import AlphaComponentRepackContract, repack_alpha_components


def _png(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def test_alpha_components_repack_crossing_poses_without_xy_slicing() -> None:
    source = Image.new("RGBA", (400, 120), (0, 0, 0, 0))
    draw = ImageDraw.Draw(source)
    colours = ((220, 30, 30, 255), (30, 220, 30, 255), (30, 30, 220, 255), (220, 180, 30, 255))
    bounds = ((10, 30, 112, 100), (118, 20, 218, 100), (222, 35, 322, 100), (326, 25, 398, 100))
    for colour, bbox in zip(colours, bounds, strict=True):
        draw.rectangle(bbox, fill=colour)

    output_data, report = repack_alpha_components(
        _png(source),
        AlphaComponentRepackContract(rows=1, columns=4, required_cells=4, gutter=6),
    )

    with Image.open(io.BytesIO(output_data)) as opened:
        output = opened.convert("RGBA")
    assert output.width % 4 == 0
    assert report["selected_component_count"] == 4
    assert report["boundaries_isolated"] is True
    assert report["warnings"] == []
    placements = report["placements"]
    assert isinstance(placements, list)
    assert [entry["source_bbox"] for entry in placements] == [
        [left, top, right + 1, bottom + 1] for left, top, right, bottom in bounds
    ]


def test_alpha_components_drop_small_detached_effects_and_report_the_caveat() -> None:
    source = Image.new("RGBA", (400, 120), (0, 0, 0, 0))
    draw = ImageDraw.Draw(source)
    for index in range(4):
        left = 15 + index * 95
        draw.rectangle((left, 25, left + 70, 105), fill=(80, 140, 220, 255))
    draw.rectangle((196, 4, 204, 12), fill=(255, 120, 40, 255))

    _output_data, report = repack_alpha_components(
        _png(source),
        AlphaComponentRepackContract(rows=1, columns=4, required_cells=4),
    )

    assert report["selected_component_count"] == 4
    assert report["rejected_component_count"] == 1
    retained = report["retained_alpha_fraction"]
    assert isinstance(retained, float)
    assert retained < 1
    assert report["warnings"] == [
        "unselected_alpha_components_were_dropped",
        "opaque_unselected_components_were_dropped",
    ]


def test_alpha_components_keep_largest_required_candidates_when_count_is_high() -> None:
    source = Image.new("RGBA", (500, 120), (0, 0, 0, 0))
    draw = ImageDraw.Draw(source)
    for index in range(4):
        left = 10 + index * 115
        draw.rectangle((left, 25, left + 80, 105), fill=(90, 160, 230, 255))
    draw.rectangle((455, 35, 499, 105), fill=(230, 100, 80, 255))

    _output_data, report = repack_alpha_components(
        _png(source),
        AlphaComponentRepackContract(rows=1, columns=4, required_cells=4),
    )

    assert report["principal_candidate_count"] == 5
    assert report["selected_component_count"] == 4
    warnings = report["warnings"]
    assert isinstance(warnings, list)
    assert "principal_component_count_exceeded_required_cells" in warnings


def test_alpha_components_fail_when_principal_frames_are_fused() -> None:
    source = Image.new("RGBA", (400, 120), (0, 0, 0, 0))
    ImageDraw.Draw(source).rectangle((20, 20, 380, 105), fill=(80, 140, 220, 255))

    with pytest.raises(ValueError, match="1 principal components for 4 required cells"):
        repack_alpha_components(
            _png(source),
            AlphaComponentRepackContract(rows=1, columns=4, required_cells=4),
        )


def test_alpha_components_preserve_row_major_dialogue_order() -> None:
    source = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
    draw = ImageDraw.Draw(source)
    bounds = ((30, 20, 100, 80), (185, 15, 260, 80), (20, 120, 105, 190), (180, 115, 270, 190))
    for bbox in bounds:
        draw.rectangle(bbox, fill=(160, 90, 220, 255))

    _output_data, report = repack_alpha_components(
        _png(source),
        AlphaComponentRepackContract(
            rows=2,
            columns=2,
            required_cells=4,
            anchor="center",
        ),
    )

    placements = report["placements"]
    assert isinstance(placements, list)
    assert [entry["source_bbox"] for entry in placements] == [
        [left, top, right + 1, bottom + 1] for left, top, right, bottom in bounds
    ]
