"""The processes draw what they say, and refuse what they cannot draw."""

from __future__ import annotations

import math
import random

import pytest

from stage_gen.components.worldgen import (
    LAMBDA_CELL_MAX,
    AttachedProcess,
    ClusterProcess,
    HabitatSpec,
    HostPoint,
    ObjectSpec,
    PoissonProcess,
    Quota,
    SpacedProcess,
    SpecError,
    Stream,
    WorldSpec,
    accept_own,
    attached_candidates,
    candidates_for,
    cell_meters_for,
    check_spec,
    cluster_candidates,
    poisson_count,
)

from ._world import EVERYWHERE, REGION_MIX, SEED, SIZE, flat_fields, fresh_fields, objects, spec


@pytest.mark.parametrize("lam", [0.5, 4.0, 20.0, 64.0])
def test_poisson_count_matches_its_parameter(lam: float) -> None:
    stream = Stream.of(1, "poisson", "test")
    n = 40_000
    draws = [poisson_count(stream.unit(i), lam) for i in range(n)]
    mean = sum(draws) / n
    var = sum((d - mean) ** 2 for d in draws) / n
    assert abs(mean - lam) / lam < 0.02
    assert abs(var - lam) / lam < 0.04


def test_a_cell_expectation_over_the_line_refuses() -> None:
    with pytest.raises(SpecError, match="exceeds"):
        poisson_count(0.5, LAMBDA_CELL_MAX + 1.0)


def test_no_draw_sits_on_a_cdf_boundary() -> None:
    """libm's exp is not bit-identical across platforms; a draw within an ulp of a
    step could flip a count elsewhere. None of these does."""

    stream = Stream.of(SEED, "poisson", "boundary")
    lam = 8.0
    steps: list[float] = []
    p = math.exp(-lam)
    cdf = p
    for k in range(1, 60):
        steps.append(cdf)
        p *= lam / k
        cdf += p
    for i in range(20_000):
        u = stream.unit(i)
        assert min(abs(u - step) for step in steps) > 1e-12


def test_cell_size_targets_eight_expected_points() -> None:
    assert abs(cell_meters_for(0.02, size_meters=512.0) - 20.0) < 1e-9
    assert cell_meters_for(0.0, size_meters=512.0) == 512.0
    assert cell_meters_for(1e6, size_meters=512.0) == 0.5


def test_the_realised_share_per_region_follows_the_habitat() -> None:
    fields = fresh_fields()
    obj = ObjectSpec("dot", PoissonProcess(6.0), REGION_MIX)
    cands = [c for c in candidates_for(obj, fields, SEED) if c.passed]
    assert len(cands) > 300
    by_region: dict[int, int] = {}
    for c in cands:
        by_region[fields.region_at(c.x, c.z)] = by_region.get(fields.region_at(c.x, c.z), 0) + 1
    area: dict[int, float] = {}
    cells = fields.analysis.cells
    for j in range(cells):
        for i in range(cells):
            x, z = fields.analysis.centre(i, j)
            if fields.on_land(x, z, 1.5):
                r = fields.region_at(x, z)
                area[r] = area.get(r, 0.0) + 1.0
    expected = {r: REGION_MIX.weight(r) * area.get(r, 0.0) for r in (-1, 0, 1)}
    total_expected = sum(expected.values())
    total = sum(by_region.values())
    for r in (-1, 0, 1):
        assert abs(by_region.get(r, 0) / total - expected[r] / total_expected) < 0.05


def test_cluster_children_cross_cell_borders_and_the_parent_scan_finds_them() -> None:
    fields = flat_fields()
    obj = ObjectSpec("grove", ClusterProcess(2.0, 6.0, 9.0), EVERYWHERE)
    cands = list(cluster_candidates(obj, fields, SEED))
    assert cands
    cell = cell_meters_for(2.0 / 100.0 * fields.peak_intensity(EVERYWHERE), size_meters=SIZE)
    half = SIZE / 2.0
    crossed = 0
    for c in cands:
        assert c.parent is not None
        own_cell = (int((c.x + half) // cell), int((c.z + half) // cell))
        if own_cell != c.parent[:2]:
            crossed += 1
        reach = math.ceil(9.0 / cell) + 1
        assert abs(own_cell[0] - c.parent[0]) <= reach
        assert abs(own_cell[1] - c.parent[1]) <= reach
    assert crossed > 0


def test_acceptance_does_not_depend_on_generation_order() -> None:
    fields = flat_fields()
    obj = ObjectSpec("dot", PoissonProcess(4.0), EVERYWHERE, spacing_meters=1.5)
    cands = [c for c in candidates_for(obj, fields, SEED) if c.passed]
    ordered = sorted(cands, key=lambda c: (c.priority, c.key))
    kept, _ = accept_own(ordered, 1.5)
    shuffled = list(cands)
    random.Random(3).shuffle(shuffled)
    kept_again, _ = accept_own(sorted(shuffled, key=lambda c: (c.priority, c.key)), 1.5)
    assert [c.key for c in kept] == [c.key for c in kept_again]


def test_attached_children_are_keyed_by_the_host_address() -> None:
    fields = flat_fields()
    obj = ObjectSpec("moss", AttachedProcess("host", 2.0, 2.0, 0.8), EVERYWHERE)
    hosts = [
        HostPoint(x * 1.0, z * 1.0, (i, j))
        for i, (x, z) in enumerate([(-20, -20), (0, 5), (15, -3), (30, 30)])
        for j in (0,)
    ]
    full = attached_candidates(obj, fields, SEED, hosts)
    fewer = attached_candidates(obj, fields, SEED, [h for h in hosts if h.key != (1, 0)])
    by_host_full = {c.key: c for c in full if c.host != (1, 0)}
    by_host_fewer = {c.key: c for c in fewer}
    assert by_host_full == by_host_fewer


def test_a_spaced_object_covers_evenly() -> None:
    fields = flat_fields()
    obj = ObjectSpec("blade", SpacedProcess(3.0, jitter=0.5), EVERYWHERE)
    cands = [c for c in candidates_for(obj, fields, SEED) if c.passed]
    keys = {c.key for c in cands}
    assert len(keys) == len(cands)
    assert all(abs(c.x) < SIZE / 2 and abs(c.z) < SIZE / 2 for c in cands)


def test_check_spec_refuses_what_cannot_be_drawn() -> None:
    fields = fresh_fields()
    assert check_spec(spec(), fields) == []
    packed = ObjectSpec("packed", ClusterProcess(0.05, 40.0, 2.0), EVERYWHERE, spacing_meters=1.6)
    wide = ObjectSpec("wide", ClusterProcess(0.05, 4.0, 60.0), EVERYWHERE)
    nowhere = ObjectSpec("nowhere", PoissonProcess(1.0), HabitatSpec(((5, 1.0),)))
    upside = ObjectSpec("upside", PoissonProcess(1.0), EVERYWHERE, quota=Quota(5, 2))
    odds = ObjectSpec("odds", PoissonProcess(1.0), EVERYWHERE, chance=0.0)
    world = WorldSpec(SEED, SIZE, (), (packed, wide, nowhere, upside, odds))
    problems = check_spec(world, fields)
    assert any("packed" in p and "hard core" in p for p in problems)
    assert any("wide" in p and "patches" in p for p in problems)
    assert any("nowhere" in p and "no suitable ground" in p for p in problems)
    assert any("upside" in p and "below min" in p for p in problems)
    assert any("odds" in p and "chance" in p for p in problems)
    assert objects()
