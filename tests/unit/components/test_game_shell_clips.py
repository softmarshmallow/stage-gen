"""The shell's clip gate: the layout it fills, and the ending it claims."""

from __future__ import annotations

import pytest
from PIL import Image

from ember_hollow_pipeline.shell.clips import (
    CLIP_MATCH_TITLE_MAX_DISTANCE,
    SHELL_CLIP_VALIDATION_VERSION,
    ShellClipError,
    match_title_verdict,
    shell_clip_record,
)
from stage_gen.components.screen_art.layouts import OPENING_CLIP, OPENING_SHOT
from stage_gen.media.codec import encode_png


def _picture(colour: tuple[int, int, int], *, size: tuple[int, int] = (320, 180)) -> bytes:
    image = Image.new("RGB", size, colour)
    # A little structure, so a signature is comparing pictures rather than flat fields.
    for x in range(0, size[0], 40):
        for y in range(size[1] // 2):
            image.putpixel((x, y), (colour[0] // 2, colour[1] // 2, colour[2] // 2))
    return encode_png(image)


def test_the_clip_canvas_reserves_the_same_band_as_the_still_canvas() -> None:
    """Both are 16:9, and the card band is the same fraction of each.

    That is the whole reason the clip gate checks aspect: a host scales a canvas to its
    window and every rect by the same factor, so a card band published against the still
    canvas lands in the same place over a clip drawn on the smaller one.
    """

    assert OPENING_CLIP.canvas == (1280, 720)
    assert OPENING_SHOT.canvas == (2560, 1440)
    for layout in (OPENING_CLIP, OPENING_SHOT):
        assert layout.canvas[0] / layout.canvas[1] == pytest.approx(16 / 9)

    def fractions(layout: object) -> tuple[float, ...]:
        rect = layout.region("card_band")  # type: ignore[attr-defined]
        width, height = layout.canvas  # type: ignore[attr-defined]
        return (rect.x / width, rect.y / height, rect.width / width, rect.height / height)

    assert fractions(OPENING_CLIP) == pytest.approx(fractions(OPENING_SHOT))


def test_a_clip_that_ends_on_the_title_is_admitted_and_one_that_does_not_is_refused() -> None:
    title = _picture((40, 60, 90))
    verdict = match_title_verdict(_picture((40, 60, 90), size=(1280, 720)), title)
    # Scale is very nearly identity: the same picture drawn at another size differs only
    # by how its detail lands in the downscale - here 0.58 against a ceiling of 12.
    assert float(str(verdict["match_distance"])) < 1.0
    assert match_title_verdict(title, title)["match_distance"] == 0.0
    assert verdict["match_distance_max"] == CLIP_MATCH_TITLE_MAX_DISTANCE

    with pytest.raises(ShellClipError, match="it is a different picture"):
        match_title_verdict(_picture((200, 40, 30)), title)


def test_a_grade_is_still_the_same_picture_and_a_repaint_is_not() -> None:
    """The ceiling has to sit above a re-encode and below a different plate."""

    title = _picture((80, 90, 100))
    graded = _picture((72, 81, 90))  # about 0.9 brightness
    distance = float(str(match_title_verdict(graded, title)["match_distance"]))
    assert distance < CLIP_MATCH_TITLE_MAX_DISTANCE
    with pytest.raises(ShellClipError):
        match_title_verdict(_picture((30, 140, 60)), title)


def test_the_record_says_which_pass_measured_what() -> None:
    """Both passes are recorded; the second is what makes the transcode auditable."""

    source = {"codec": "h264", "motion_mean": 0.44}
    published = {"codec": "theora", "motion_mean": 0.4405}

    without = shell_clip_record(source, layout=OPENING_CLIP, seconds=8.0)
    assert without["validation_version"] == SHELL_CLIP_VALIDATION_VERSION
    assert without["canvas"] == {"width": 1280, "height": 720}
    assert without["source"] == source
    assert "published" not in without and "pixel_rewrite" not in without

    with_published = shell_clip_record(
        source, layout=OPENING_CLIP, seconds=8.0, published_facts=published
    )
    assert with_published["published"] == published
    assert with_published["pixel_rewrite"] == "theora_publication_v1"
