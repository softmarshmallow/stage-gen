"""Regions solve to their shares, the coast to its, distances match brute force."""

from __future__ import annotations

import math

from stage_gen.components.worldgen import (
    Clearing,
    GridSpec,
    HabitatSpec,
    HeightBand,
    band,
    chamfer_distance,
    solve_threshold,
    trapezoid,
)

from ._world import BASE_ONLY, EVERYWHERE, REGION_MIX, SHORE, SIZE, coast, fresh_fields, regions


def test_the_region_shares_are_solved_not_assumed() -> None:
    field = regions()
    assert abs(field.shares[0] - 0.25) < 0.03
    assert abs(field.shares[1] - 0.15) < 0.03
    assert abs(field.shares[-1] - 0.60) < 0.04


def test_the_spawn_clearing_stands_on_the_base_region() -> None:
    fields = fresh_fields()
    for radius in (0.0, 2.0, 4.0):
        for k in range(8):
            a = math.tau * k / 8
            assert fields.region_at(math.cos(a) * radius, math.sin(a) * radius) == -1


def test_the_coast_solves_to_its_share_and_the_bump_holds_the_origin() -> None:
    shore = coast()
    assert abs(shore.solved_share - 0.6) < 0.02
    assert shore.at(0.0, 0.0)
    fields = fresh_fields()
    assert abs(fields.land.share(0) - 0.6) < 0.03
    assert fields.on_land(0.0, 0.0, 3.0)
    assert not fields.on_land(SIZE / 2.0 - 0.5, 0.0, 0.0)


def test_the_chamfer_distance_matches_brute_force() -> None:
    spec = GridSpec(64.0, 64)
    seeds = {(5, 7), (40, 41), (12, 50), (60, 3)}
    grid = chamfer_distance(spec, lambda i, j: (i, j) in seeds)
    worst = 0.0
    for j in range(0, 64, 3):
        for i in range(0, 64, 3):
            exact = min(math.hypot(i - si, j - sj) for si, sj in seeds) * spec.cell_meters
            if exact > 0.0:
                worst = max(worst, abs(grid.cell(i, j) - exact) / exact)
    assert worst < 0.09  # the 3-4 chamfer's known worst-case error is about 8 %


def test_band_and_trapezoid_shape() -> None:
    assert band(1.0, peak_meters=4.0, falloff_meters=2.0, outside=0.0) == 1.0
    assert band(7.0, peak_meters=4.0, falloff_meters=2.0, outside=0.0) == 0.0
    assert 0.0 < band(5.0, peak_meters=4.0, falloff_meters=2.0, outside=0.0) < 1.0
    assert band(9.0, peak_meters=4.0, falloff_meters=2.0, outside=0.3) == 0.3
    assert trapezoid(0.5, low=0.2, high=0.8, falloff=0.1) == 1.0
    assert trapezoid(0.05, low=0.2, high=0.8, falloff=0.1) == 0.0
    assert abs(trapezoid(0.85, low=0.2, high=0.8, falloff=0.1) - 0.5) < 1e-9


def test_the_height_is_zero_at_the_coast_and_within_one_inland() -> None:
    fields = fresh_fields()
    cells = fields.analysis.cells
    lows: list[float] = []
    highs: list[float] = []
    for j in range(cells):
        for i in range(cells):
            x, z = fields.analysis.centre(i, j)
            h = fields.height.cell(i, j)
            assert 0.0 <= h <= 1.0
            if fields.on_land(x, z, 0.0):
                (lows if fields.distance("water", x, z) < 3.0 else highs).append(h)
    assert sum(lows) / len(lows) < sum(highs) / len(highs)


def test_the_intensity_reads_every_factor() -> None:
    fields = fresh_fields()
    assert fields.intensity(EVERYWHERE, SIZE / 2.0 - 0.5, 0.0) == 0.0
    assert fields.intensity(EVERYWHERE, 0.0, 0.0) == 1.0
    assert fields.intensity(BASE_ONLY, 0.0, 0.0) == 1.0
    found = {fields.region_at(x, z) for x in range(-60, 60, 4) for z in range(-60, 60, 4)}
    assert found >= {-1, 0, 1}
    for x in range(-60, 60, 4):
        for z in range(-60, 60, 4):
            weight = fields.intensity(REGION_MIX, x, z)
            if fields.on_land(x, z, 1.5):
                assert weight == REGION_MIX.weight(fields.region_at(x, z))
            else:
                assert weight == 0.0
            if fields.distance("water", x, z) > 6.5:
                assert fields.intensity(SHORE, x, z) == 0.0
    lowland = HabitatSpec(((-1, 1.0), (0, 1.0), (1, 1.0)), height=HeightBand(0.0, 0.2, 0.0))
    assert fields.support_area_m2(lowland) < fields.support_area_m2(EVERYWHERE)


def test_a_clearing_zeroes_the_intensity_and_the_scan_cache_follows() -> None:
    fields = fresh_fields()
    before = fields.support_area_m2(EVERYWHERE)
    fields.add_clearings([Clearing(0.0, 0.0, 10.0)])
    assert fields.intensity(EVERYWHERE, 1.0, 1.0) == 0.0
    assert fields.support_area_m2(EVERYWHERE) < before
    assert fields.distance("set_piece", 0.0, 0.0) < fields.analysis.cell_meters


def test_solve_threshold_is_a_quantile() -> None:
    samples = [i / 100.0 for i in range(100)]
    assert solve_threshold(samples, 0.25) == 0.74
    assert solve_threshold(samples, 1.0) == 0.0
