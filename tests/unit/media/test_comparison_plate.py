from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from stage_gen.media.comparison_plate import (
    TALLEST_TARGET_PX,
    ComparisonPlateError,
    PlateGroup,
    band_groups,
    compose_comparison_plate,
)


def _frame(width: int, height: int, *, alpha: int = 255, pad: int = 6) -> bytes:
    image = Image.new("RGBA", (width + pad * 2, height + pad * 2), (0, 0, 0, 0))
    for y in range(pad, pad + height):
        for x in range(pad, pad + width):
            image.putpixel((x, y), (200, 60, 40, alpha))
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def _group(
    key: str, width: int, height: int, *, baseline: bool = False, count: int = 4
) -> PlateGroup:
    return PlateGroup(
        key=key, frames=tuple(_frame(width, height) for _ in range(count)), baseline=baseline
    )


def test_one_uniform_scale_keeps_a_small_group_looking_small() -> None:
    plate = compose_comparison_plate(
        [_group("idle", 40, 100, baseline=True), _group("death", 40, 50)]
    )

    idle = [frame for frame in plate.frames if frame.group_key == "idle"]
    death = [frame for frame in plate.frames if frame.group_key == "death"]
    assert idle[0].drawn_height == TALLEST_TARGET_PX
    # Half the source height must stay half the drawn height. Normalising it away would erase
    # the only signal the judge can read.
    assert death[0].drawn_height == pytest.approx(TALLEST_TARGET_PX / 2, abs=1)
    assert death[0].baseline_percent == pytest.approx(50.0, abs=1.0)


def test_plate_binds_every_frame_it_composited_by_digest() -> None:
    groups = [_group("idle", 40, 100, baseline=True), _group("run", 40, 80)]
    plate = compose_comparison_plate(groups)

    assert len(plate.frames) == 8
    assert plate.group_keys == ("idle", "run")
    for group in groups:
        composited = [f.sha256 for f in plate.frames if f.group_key == group.key]
        assert composited == [__import__("hashlib").sha256(f).hexdigest() for f in group.frames]


def test_composition_is_deterministic() -> None:
    def build() -> str:
        return compose_comparison_plate(
            [_group("idle", 40, 100, baseline=True), _group("hurt", 40, 60)]
        ).sha256

    assert build() == build()


def test_a_collapsed_group_still_gets_a_band_tall_enough_for_the_crown() -> None:
    tall = compose_comparison_plate(
        [_group("idle", 40, 100, baseline=True), _group("death", 40, 100)]
    )
    collapsed = compose_comparison_plate(
        [_group("idle", 40, 100, baseline=True), _group("death", 40, 12)]
    )
    # The crown rule is drawn at the baseline height inside every panel, so a collapsed group
    # must not shrink its band below that or the reference leaves the panel.
    assert collapsed.height == tall.height


def test_plate_requires_exactly_one_baseline() -> None:
    with pytest.raises(ComparisonPlateError, match="exactly one baseline"):
        compose_comparison_plate([_group("idle", 40, 100), _group("run", 40, 80)])
    with pytest.raises(ComparisonPlateError, match="exactly one baseline"):
        compose_comparison_plate(
            [_group("idle", 40, 100, baseline=True), _group("run", 40, 80, baseline=True)]
        )


def test_plate_rejects_unusable_input() -> None:
    with pytest.raises(ComparisonPlateError, match="at least one group"):
        compose_comparison_plate([])
    with pytest.raises(ComparisonPlateError, match="carries no frames"):
        compose_comparison_plate([PlateGroup(key="idle", frames=(), baseline=True)])
    with pytest.raises(ComparisonPlateError, match="unique"):
        compose_comparison_plate([_group("idle", 40, 100, baseline=True), _group("idle", 40, 80)])
    with pytest.raises(ComparisonPlateError, match="no painted pixels"):
        compose_comparison_plate(
            [PlateGroup(key="idle", frames=(_frame(40, 100, alpha=10),), baseline=True)]
        )


def test_prescale_draws_a_group_at_its_corrected_size() -> None:
    # A verification plate applies a judged multiplier before the uniform scale: a group drawn
    # at half size with a prescale of 2.0 must read exactly like the baseline beside it.
    plate = compose_comparison_plate(
        [
            _group("idle", 40, 100, baseline=True),
            PlateGroup(
                key="death",
                frames=tuple(_frame(40, 50) for _ in range(4)),
                prescale=2.0,
            ),
        ]
    )

    idle = [frame for frame in plate.frames if frame.group_key == "idle"]
    death = [frame for frame in plate.frames if frame.group_key == "death"]
    assert idle[0].drawn_height == TALLEST_TARGET_PX
    assert death[0].drawn_height == pytest.approx(TALLEST_TARGET_PX, abs=1)
    assert death[0].baseline_percent == pytest.approx(100.0, abs=1.0)


def test_prescale_must_be_positive_and_finite() -> None:
    with pytest.raises(ComparisonPlateError, match="prescale"):
        compose_comparison_plate(
            [
                _group("idle", 40, 100, baseline=True),
                PlateGroup(key="run", frames=(_frame(40, 80),), prescale=0.0),
            ]
        )


def test_banding_reads_the_corrected_height_not_the_canvas() -> None:
    # A 300px canvas beside a 100px baseline demands its own band raw, but corrected down to a
    # third it belongs beside the baseline: bands protect the legibility of what will actually
    # be drawn.
    raw = [
        _group("idle", 40, 100, baseline=True),
        _group("walk", 40, 95),
        _group("climb", 40, 300, count=2),
    ]
    corrected = [
        _group("idle", 40, 100, baseline=True),
        _group("walk", 40, 95),
        PlateGroup(key="climb", frames=tuple(_frame(40, 300) for _ in range(2)), prescale=0.33),
    ]

    assert len(band_groups(raw)) == 2
    assert len(band_groups(corrected)) == 1
