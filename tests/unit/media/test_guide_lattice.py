from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from stage_gen.media.guide_lattice import detect_guide_lattice, extract_guided_cells


def _lattice(*, x_lines: tuple[int, ...], y_lines: tuple[int, ...]) -> Image.Image:
    image = Image.new("RGB", (420, 220), (255, 0, 255))
    draw = ImageDraw.Draw(image)
    for x in x_lines:
        draw.rectangle((x, 10, x + 2, 209), fill=(0, 255, 255))
    for y in y_lines:
        draw.rectangle((10, y, 409, y + 2), fill=(0, 255, 255))
    return image


def test_detects_provider_resized_but_regular_lattice() -> None:
    image = _lattice(x_lines=(20, 80, 140, 200), y_lines=(30, 100, 170))
    resized = image.resize((630, 330), Image.Resampling.NEAREST)

    lattice = detect_guide_lattice(resized, expected_columns=3, expected_rows=2)

    assert len(lattice.x_lines) == 4
    assert len(lattice.y_lines) == 3
    assert lattice.x_maximum_residual_px <= 0.25
    assert lattice.y_maximum_residual_px <= 0.25
    cells, _ = extract_guided_cells(
        resized,
        columns=3,
        rows=2,
        canonical_cell_px=120,
    )
    assert len(cells) == 6
    assert all(cell.size == (120, 120) and cell.mode == "RGBA" for cell in cells.values())


@pytest.mark.parametrize(
    ("x_lines", "y_lines"),
    (
        ((20, 80, 140), (30, 100, 170)),
        ((20, 60, 100, 140, 180), (30, 100, 170)),
        ((20, 80, 140, 200), (30, 170)),
        ((20, 80, 140, 200), (30, 75, 120, 165)),
    ),
)
def test_missing_and_extra_guides_fail_closed(
    x_lines: tuple[int, ...], y_lines: tuple[int, ...]
) -> None:
    with pytest.raises(ValueError, match="guide lattice count mismatch"):
        detect_guide_lattice(
            _lattice(x_lines=x_lines, y_lines=y_lines),
            expected_columns=3,
            expected_rows=2,
        )


def test_irregular_lattice_is_measured_for_recipe_rejection() -> None:
    lattice = detect_guide_lattice(
        _lattice(x_lines=(20, 80, 151, 200), y_lines=(30, 100, 170)),
        expected_columns=3,
        expected_rows=2,
    )
    assert lattice.x_maximum_residual_px > 1.5
