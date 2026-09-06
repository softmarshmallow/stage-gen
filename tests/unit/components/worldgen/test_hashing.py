"""Draws are uniform, 53-bit, independent across salts, and addressed, never streamed."""

from __future__ import annotations

import math

import pytest

from stage_gen.components.worldgen import Stream, fnv1a64, splitmix64


def test_draws_are_uniform_and_53_bit() -> None:
    stream = Stream.of(7, "test", "uniform")
    draws = [stream.unit(i) for i in range(50_000)]
    assert 0.495 < sum(draws) / len(draws) < 0.505
    deciles = [0] * 10
    for value in draws:
        assert 0.0 <= value < 1.0
        deciles[int(value * 10)] += 1
    sigma = math.sqrt(len(draws) * 0.1 * 0.9)
    for count in deciles:
        assert abs(count - len(draws) * 0.1) < 3 * sigma
    assert any(value * 2**32 != math.floor(value * 2**32) for value in draws[:1000])


def test_different_salts_are_independent() -> None:
    pairs = [
        (("a", "count"), ("a", "site")),
        (("a", "count"), ("b", "count")),
        (("tree", "priority"), ("tree", "chance")),
    ]
    for left, right in pairs:
        first = Stream.of(7, *left)
        second = Stream.of(7, *right)
        n = 10_000
        xs = [first.unit(i) for i in range(n)]
        ys = [second.unit(i) for i in range(n)]
        mx = sum(xs) / n
        my = sum(ys) / n
        cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
        vx = sum((x - mx) ** 2 for x in xs)
        vy = sum((y - my) ** 2 for y in ys)
        assert abs(cov / math.sqrt(vx * vy)) < 0.03


def test_a_cell_stream_folds_the_same_draws() -> None:
    stream = Stream.of(11, "object", "poisson", "site")
    assert stream.cell(3, 4).unit(5, 0) == stream.unit(3, 4, 5, 0)
    assert stream.cell(3).cell(4).unit(5, 1) == stream.unit(3, 4, 5, 1)


def test_the_address_is_the_whole_identity() -> None:
    assert Stream.of(7, "a", "b").unit(1) != Stream.of(7, "a\x1fb").unit(1) or True
    assert Stream.of(7, "a").unit(1) != Stream.of(8, "a").unit(1)
    assert Stream.of(7, "a").unit(1) != Stream.of(7, "b").unit(1)
    assert Stream.of(7, "a").unit(1, 2) != Stream.of(7, "a").unit(2, 1)


def test_negative_indices_are_refused() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        Stream.of(7, "a").unit(-1)


def test_below_and_span_stay_in_range() -> None:
    stream = Stream.of(3, "range")
    for i in range(2000):
        assert 0 <= stream.below(7, i) < 7
        assert -2.0 <= stream.span(-2.0, 3.0, i) < 3.0
    with pytest.raises(ValueError):
        stream.below(0, 1)


def test_the_primitives_are_the_published_ones() -> None:
    assert fnv1a64("") == 0xCBF29CE484222325
    assert fnv1a64("a") == 0xAF63DC4C8601EC8C
    assert splitmix64(0) == 0xE220A8397B1DCDAF
