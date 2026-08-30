from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw

from stage_gen.media import (
    AlphaComponentRepackContract,
    measure_alpha_ground_contact,
    repack_alpha_components,
)
from stage_gen.media.sprite_sheets import measure_alpha_subjects


def _png(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def test_alpha_ground_contact_ignores_tiny_and_low_alpha_bottom_contamination() -> None:
    source = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    draw = ImageDraw.Draw(source)
    draw.rectangle((20, 15, 80, 74), fill=(120, 180, 240, 255))
    draw.rectangle((5, 96, 7, 98), fill=(255, 80, 80, 255))
    draw.rectangle((90, 99, 99, 99), fill=(255, 255, 255, 8))

    contact = measure_alpha_ground_contact(_png(source))

    assert contact["kind"] == "alpha-ground-contact-v1"
    assert contact["principal_component_count"] == 1
    assert contact["ground_contact_y_pixels"] == 75
    assert contact["ground_contact_y_normalized"] == 0.75
    assert contact["bottom_padding_pixels"] == 25


def test_alpha_ground_contact_retains_meaningful_detached_parts() -> None:
    source = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    draw = ImageDraw.Draw(source)
    draw.rectangle((10, 10, 70, 69), fill=(120, 180, 240, 255))
    draw.rectangle((75, 75, 94, 94), fill=(120, 180, 240, 255))

    contact = measure_alpha_ground_contact(_png(source))

    assert contact["principal_component_count"] == 2
    assert contact["ground_contact_y_pixels"] == 95
    assert contact["ground_contact_y_normalized"] == 0.95


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


def _uneven_pair() -> bytes:
    """Two components of different heights sharing one baseline, as a climb cycle produces."""

    source = Image.new("RGBA", (240, 200), (0, 0, 0, 0))
    draw = ImageDraw.Draw(source)
    draw.rectangle((10, 20, 100, 180), fill=(220, 30, 30, 255))
    draw.rectangle((140, 90, 230, 180), fill=(30, 220, 30, 255))
    return _png(source)


def test_top_anchor_registers_uneven_poses_on_their_grip_instead_of_their_feet() -> None:
    _, bottom_report = repack_alpha_components(
        _uneven_pair(),
        AlphaComponentRepackContract(rows=1, columns=2, required_cells=2, gutter=6),
    )
    _, top_report = repack_alpha_components(
        _uneven_pair(),
        AlphaComponentRepackContract(rows=1, columns=2, required_cells=2, gutter=6, anchor="top"),
    )

    def edges(report: object) -> tuple[list[int], list[int]]:
        placements = report["placements"]  # type: ignore[index]
        assert isinstance(placements, list)
        return (
            [entry["target_bbox"][1] for entry in placements],
            [entry["target_bbox"][3] for entry in placements],
        )

    bottom_tops, bottom_bottoms = edges(bottom_report)
    top_tops, top_bottoms = edges(top_report)

    # Bottom anchoring agrees on the feet and disagrees on the head; top anchoring is the reverse.
    # That difference is the whole reason a hanging pose needs its own registration.
    assert len(set(bottom_bottoms)) == 1
    assert len(set(bottom_tops)) == 2
    assert len(set(top_tops)) == 1
    assert len(set(top_bottoms)) == 2


def test_top_anchor_keeps_the_tallest_pose_on_the_runtime_foot_origin() -> None:
    """Why the runtime origin does not branch on the anchor.

    The web runtime places every motion sprite at `repackedMotionFootOriginY`, which is
    ``1 - gutter / frameHeight``. Cell height is the tallest crop plus two gutters, so a
    top-anchored strip lands the tallest pose's painted bottom exactly on that line and only shorter
    poses lift off it. If this ever fails the runtime has to start branching, and admitting the
    repacker's `center` anchor to an authored contract would break it immediately.
    """

    gutter = 6
    for anchor in ("bottom", "top"):
        output_data, _ = repack_alpha_components(
            _uneven_pair(),
            AlphaComponentRepackContract(
                rows=1, columns=2, required_cells=2, gutter=gutter, anchor=anchor
            ),
        )
        with Image.open(io.BytesIO(output_data)) as opened:
            output = opened.convert("RGBA")
        cell_width = output.width // 2
        bottoms: list[int] = []
        for index in range(2):
            cell = output.crop((index * cell_width, 0, (index + 1) * cell_width, output.height))
            box = cell.getchannel("A").getbbox()
            assert box is not None
            bottoms.append(box[3])
        assert max(bottoms) == output.height - gutter, anchor


def _blob_png(blobs: list[tuple[int, int, int, int]], size: tuple[int, int] = (256, 256)) -> bytes:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    for left, top, right, bottom in blobs:
        for x in range(left, right):
            for y in range(top, bottom):
                image.putpixel((x, y), (200, 120, 60, 255))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def test_one_object_measures_as_one_subject_and_reports_its_box() -> None:
    report = measure_alpha_subjects(_blob_png([(40, 100, 200, 130)]))

    assert report["subject_count"] == 1
    assert report["largest_bbox"] == [40, 100, 200, 130]
    assert report["largest_width"] == 160
    assert report["largest_height"] == 30
    assert report["largest_share"] == 1.0


def test_a_detached_streak_is_a_second_subject() -> None:
    """The defect no other isolation check catches.

    A painted trail or spark beside the object passes every alpha, border, and size gate the
    pipeline already runs, and then moves the measured bounding box - so the object draws at the
    wrong size and rotates around a point outside itself.
    """

    report = measure_alpha_subjects(_blob_png([(40, 100, 200, 130), (210, 110, 250, 120)]))

    assert report["subject_count"] == 2


def test_a_speck_is_not_a_second_subject() -> None:
    # Both filters have to agree: an antialiasing crumb is neither large in absolute terms nor a
    # real share of the paint, and calling it a subject would reject good artwork.
    report = measure_alpha_subjects(_blob_png([(40, 100, 200, 130), (240, 240, 243, 243)]))

    assert report["subject_count"] == 1


def test_an_empty_canvas_is_refused_rather_than_measured_as_zero() -> None:
    with pytest.raises(ValueError, match="no painted pixels"):
        measure_alpha_subjects(_blob_png([]))


def test_the_thresholds_are_validated() -> None:
    data = _blob_png([(40, 100, 200, 130)])
    with pytest.raises(ValueError, match="alpha threshold"):
        measure_alpha_subjects(data, alpha_threshold=255)
    with pytest.raises(ValueError, match="component fraction"):
        measure_alpha_subjects(data, minimum_component_fraction=0)
    with pytest.raises(ValueError, match="minimum component area"):
        measure_alpha_subjects(data, minimum_component_area=0)


def test_an_image_of_only_specks_names_what_was_wrong() -> None:
    # Every other guard in this function reports its own failure; without this one the caller gets
    # a bare "max() arg is an empty sequence" and no way to act on it.
    speckled = _blob_png([(x, x, x + 2, x + 2) for x in range(0, 40, 6)])

    with pytest.raises(ValueError, match="no component large enough to be a subject"):
        measure_alpha_subjects(speckled)
