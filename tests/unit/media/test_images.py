from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO
from typing import Any, cast

import pytest
from PIL import Image

from stage_gen.media import (
    apply_chroma_transparency,
    compose_source_with_alpha,
    decontaminate_magenta_edges,
    inspect_image,
    normalize_image_to_png,
    normalize_png,
)


def _png(mode: str, size: tuple[int, int], values: Sequence[Any]) -> bytes:
    image = Image.new(mode, size)
    image.putdata(values)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_normalize_png_is_deterministic_and_records_transform() -> None:
    source = _png(
        "RGBA",
        (2, 2),
        [(1, 2, 3, 255), (20, 30, 40, 255), (50, 60, 70, 128), (80, 90, 100, 0)],
    )

    first, first_record = normalize_png(source, width=4, height=3)
    second, second_record = normalize_png(source, width=4, height=3)

    assert first == second
    assert first_record == second_record
    assert (inspect_image(first).width, inspect_image(first).height) == (4, 3)
    assert first_record.operation == "resize"
    assert first_record.transform == {
        "fit": "fill",
        "kernel": "lanczos3",
        "format": "png",
        "compression_level": 9,
    }
    with pytest.raises(ValueError, match="positive integer"):
        normalize_png(source, width=0, height=3)


@pytest.mark.parametrize("source_format", ["JPEG", "PNG", "WEBP"])
def test_normalize_image_to_png_accepts_provider_formats_without_resampling(
    source_format: str,
) -> None:
    image = Image.new("RGB", (5, 3), (23, 45, 67))
    source_io = BytesIO()
    image.save(source_io, format=source_format)

    first, first_record = normalize_image_to_png(source_io.getvalue())
    second, second_record = normalize_image_to_png(source_io.getvalue())

    assert first == second
    assert first_record == second_record
    assert inspect_image(first, expected_media_type="image/png") == inspect_image(first)
    assert (inspect_image(first).width, inspect_image(first).height) == (5, 3)
    assert first_record.operation == "image-to-png"
    assert (
        first_record.source["media_type"]
        == {
            "JPEG": "image/jpeg",
            "PNG": "image/png",
            "WEBP": "image/webp",
        }[source_format]
    )
    assert first_record.transform == {
        "format": "png",
        "color_mode": "RGB",
        "compression_level": 9,
        "metadata": "stripped",
        "pixels_resampled": False,
    }


def test_normalize_image_to_png_preserves_rgba_pixels() -> None:
    source = _png("RGBA", (2, 1), [(1, 2, 3, 0), (4, 5, 6, 127)])

    output, record = normalize_image_to_png(source)

    assert _rgba(output) == [(1, 2, 3, 0), (4, 5, 6, 127)]
    assert inspect_image(output).has_alpha
    assert record.transform["color_mode"] == "RGBA"


@pytest.mark.parametrize("source_format", ["GIF", "WEBP"])
def test_normalize_image_to_png_rejects_animated_inputs(source_format: str) -> None:
    first = Image.new("RGB", (8, 8), (255, 0, 0))
    second = Image.new("RGB", (8, 8), (0, 255, 0))
    source_io = BytesIO()
    format_options = {"lossless": True, "minimize_size": False} if source_format == "WEBP" else {}
    first.save(
        source_io,
        format=source_format,
        save_all=True,
        append_images=[second],
        duration=100,
        loop=0,
        **format_options,
    )

    with pytest.raises(ValueError, match="animated images are not supported"):
        normalize_image_to_png(source_io.getvalue())


def test_chroma_transparency_handles_every_matching_pixel() -> None:
    source = _png(
        "RGBA",
        (4, 1),
        [(255, 0, 255, 255), (250, 4, 250, 255), (0, 0, 0, 0), (20, 40, 60, 3)],
    )

    output, facts = apply_chroma_transparency(source)

    assert facts.transparent_pixels == 2
    assert facts.nontransparent_pixels == 2
    assert inspect_image(output, expected_media_type="image/png").has_alpha


def test_alpha_composition_prefers_mask_and_rejects_degenerate_alpha() -> None:
    source = _png("RGB", (2, 1), [(10, 20, 30), (40, 50, 60)])
    removed = _png("RGBA", (2, 1), [(1, 1, 1, 255), (2, 2, 2, 255)])
    mask = _png("L", (2, 1), [0, 255])

    output, facts = compose_source_with_alpha(
        source,
        removed_data=removed,
        mask_data=mask,
    )

    assert facts.transparent_pixels == 1
    assert facts.nontransparent_pixels == 1
    assert inspect_image(output).has_alpha
    with pytest.raises(ValueError, match="both transparent and nontransparent"):
        compose_source_with_alpha(source, mask_data=_png("L", (2, 1), [255, 255]))


def _rgba(data: bytes) -> list[tuple[int, int, int, int]]:
    with Image.open(BytesIO(data)) as opened:
        flattened = opened.convert("RGBA").get_flattened_data()
    return [cast(tuple[int, int, int, int], pixel) for pixel in flattened]


def test_chroma_matte_ramps_coverage_instead_of_forcing_opacity() -> None:
    # Distances: 0 (pure key), 118 (inside the ramp), 510 (wholly foreground).
    source = _png(
        "RGBA",
        (3, 1),
        [(255, 0, 255, 255), (255, 59, 196, 255), (0, 0, 0, 255)],
    )

    output, facts = apply_chroma_transparency(source)

    keyed, ramped, solid = _rgba(output)
    assert keyed[3] == 0
    assert solid[3] == 255
    # The ramped pixel keeps partial coverage rather than snapping to either extreme.
    assert 0 < ramped[3] < 255
    # The counts are "carries some transparency" and "carries some opacity", so a partially
    # covered pixel is reported by both. They stop partitioning once the matte is soft.
    assert facts.transparent_pixels == 2
    assert facts.nontransparent_pixels == 2


def test_chroma_matte_uses_unsaturated_distance_for_large_thresholds() -> None:
    # Distance from magenta is 510. Saturating channel addition at 255 would incorrectly key this
    # pixel out when the configured threshold is 300 instead of placing it inside the matte ramp.
    source = _png("RGBA", (1, 1), [(0, 0, 0, 255)])

    output, _facts = apply_chroma_transparency(
        source,
        threshold=300,
        solid_threshold=600,
        minimum_coverage=0,
        despill_radius=0,
    )

    assert 0 < _rgba(output)[0][3] < 255


def test_chroma_matte_removes_key_spill_near_the_silhouette_only() -> None:
    # One keyed pixel, then eight foreground pixels each carrying an equal red/blue cast.
    source = _png(
        "RGBA",
        (9, 1),
        [(255, 0, 255, 255)] + [(200, 100, 200, 255)] * 8,
    )

    output, _facts = apply_chroma_transparency(source, despill_radius=1)

    pixels = _rgba(output)
    assert pixels[0][3] == 0
    # Adjacent to the silhouette: the cast of min(R, B) - G is subtracted from red and blue.
    assert pixels[1][:3] == (100, 100, 100)
    # Far from any transparency the same colour is left alone, so interior art survives.
    assert pixels[5][:3] == (200, 100, 200)


def test_chroma_matte_despills_everywhere_when_the_band_is_disabled() -> None:
    source = _png("RGBA", (9, 1), [(255, 0, 255, 255)] + [(200, 100, 200, 255)] * 8)

    output, _facts = apply_chroma_transparency(source, despill_radius=0)

    pixels = _rgba(output)
    assert pixels[1][:3] == (100, 100, 100)
    assert pixels[5][:3] == (100, 100, 100)


def test_chroma_matte_rejects_incoherent_thresholds() -> None:
    source = _png("RGBA", (1, 1), [(255, 0, 255, 255)])

    with pytest.raises(ValueError, match="chroma threshold"):
        apply_chroma_transparency(source, threshold=-1)
    with pytest.raises(ValueError, match="solid threshold"):
        apply_chroma_transparency(source, threshold=200, solid_threshold=200)
    with pytest.raises(ValueError, match="despill radius"):
        apply_chroma_transparency(source, despill_radius=-1)


def test_magenta_edge_decontamination_removes_only_boundary_fringe() -> None:
    source_pixels = [
        (0, 0, 0, 0),
        (90, 60, 40, 128),
        (255, 0, 255, 240),
        (250, 20, 245, 255),
        (245, 100, 180, 255),
        (180, 65, 220, 255),
        (80, 50, 30, 255),
        (255, 0, 255, 255),
    ]
    source = _png("RGBA", (8, 1), source_pixels)

    output, facts = decontaminate_magenta_edges(source, boundary_radius=3)

    output_pixels = _rgba(output)
    assert output_pixels[:2] == source_pixels[:2]
    assert output_pixels[2:4] == [(0, 0, 0, 0), (0, 0, 0, 0)]
    # A blush-like pink and purple flower colour are outside the conservative hot-magenta class.
    assert output_pixels[4:7] == source_pixels[4:7]
    # This hot-magenta interior pixel is outside the transparency-connected boundary band.
    assert output_pixels[7] == source_pixels[7]
    assert facts.as_dict() == {
        "width": 8,
        "height": 1,
        "source_hot_magenta_pixels": 3,
        "output_hot_magenta_pixels": 1,
        "removed_pixels": 2,
        "high_alpha_removed_pixels": 2,
        "opaque_removed_pixels": 1,
    }


def test_magenta_edge_decontamination_is_deterministic_and_preserves_dimensions() -> None:
    image = Image.new("RGBA", (1024, 1536), (20, 30, 40, 255))
    image.putpixel((0, 0), (0, 0, 0, 0))
    image.putpixel((31, 31), (255, 0, 255, 255))
    output_io = BytesIO()
    image.save(output_io, format="PNG")

    first, first_facts = decontaminate_magenta_edges(output_io.getvalue())
    second, second_facts = decontaminate_magenta_edges(output_io.getvalue())

    assert first == second
    assert first_facts == second_facts
    assert (inspect_image(first).width, inspect_image(first).height) == (1024, 1536)
    assert _rgba(first)[31 * 1024 + 31] == (0, 0, 0, 0)


@pytest.mark.parametrize(
    ("parameter", "value", "message"),
    [
        ("boundary_radius", -1, "boundary radius"),
        ("minimum_red", 256, "minimum red"),
        ("maximum_green", True, "maximum green"),
        ("minimum_blue", -1, "minimum blue"),
        ("minimum_red_green_delta", 256, "red-green delta"),
        ("minimum_blue_green_delta", True, "blue-green delta"),
        ("maximum_red_blue_delta", 256, "red-blue delta"),
        ("transparent_alpha_max", 255, "alpha maximum"),
    ],
)
def test_magenta_edge_decontamination_validates_parameters(
    parameter: str, value: int, message: str
) -> None:
    source = _png("RGBA", (1, 1), [(0, 0, 0, 0)])

    with pytest.raises(ValueError, match=message):
        decontaminate_magenta_edges(source, **{parameter: value})


def test_magenta_edge_decontamination_requires_alpha() -> None:
    source = _png("RGB", (1, 1), [(255, 0, 255)])

    with pytest.raises(ValueError, match="alpha-bearing"):
        decontaminate_magenta_edges(source)
