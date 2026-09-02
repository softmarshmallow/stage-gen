"""Medium contracts and the digest split that keeps review calibration cheap."""

from __future__ import annotations

import dataclasses

import pytest

from stage_gen.recipes.universe.medium import (
    ANIME_2D,
    LIVE_ACTION,
    forbidden_terms_present,
    medium_contract,
)


def test_media_do_not_leak_each_others_vocabulary() -> None:
    """A compiler that speaks one medium overrules any renderer that speaks another."""

    # Each render block names its own medium, and the other only to refuse it.
    assert "anime" in ANIME_2D.render_block.lower()
    assert "photographed" in LIVE_ACTION.render_block.lower()
    assert "photograph" not in ANIME_2D.render_block.lower().replace("not photographic", "")
    assert "anime" not in LIVE_ACTION.render_block.lower().replace("not render as anime", "")
    assert forbidden_terms_present(ANIME_2D, "shot on 35mm film stock") == ["film stock"]
    assert forbidden_terms_present(LIVE_ACTION, "a painted background") == ["painted background"]


def test_an_unknown_medium_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="unknown medium"):
        medium_contract("claymation")


def test_review_calibration_moves_only_the_review_digest() -> None:
    """The whole reason the digest is split three ways.

    The spike hashed compile, render, negative and review prose into one digest
    bound to every direction, image and review node, so rewording how an image
    was judged re-billed every image in the gallery — about eleven dollars to
    change a sentence about judgement.
    """

    recalibrated = dataclasses.replace(
        ANIME_2D, review_criteria=ANIME_2D.review_criteria + " Also fail visible seams."
    )
    assert recalibrated.review_digest() != ANIME_2D.review_digest()
    assert recalibrated.render_digest() == ANIME_2D.render_digest()
    assert recalibrated.compile_digest() == ANIME_2D.compile_digest()


def test_render_wording_moves_only_the_render_digest() -> None:
    repainted = dataclasses.replace(
        ANIME_2D, render_block=ANIME_2D.render_block + " Keep edges crisp."
    )
    assert repainted.render_digest() != ANIME_2D.render_digest()
    assert repainted.review_digest() == ANIME_2D.review_digest()
    assert repainted.compile_digest() == ANIME_2D.compile_digest()


def test_the_three_digests_are_distinct_per_medium() -> None:
    digests = {
        ANIME_2D.compile_digest(),
        ANIME_2D.render_digest(),
        ANIME_2D.review_digest(),
        LIVE_ACTION.compile_digest(),
        LIVE_ACTION.render_digest(),
        LIVE_ACTION.review_digest(),
    }
    assert len(digests) == 6
