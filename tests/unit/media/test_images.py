from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from stage_gen.media import (
    apply_chroma_transparency,
    compose_source_with_alpha,
    inspect_image,
    normalize_png,
)


def _png(mode: str, size: tuple[int, int], values: list[object]) -> bytes:
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
