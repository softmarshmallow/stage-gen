"""The pipeline: tiers, quotas, set pieces, and a plan that is pure in its inputs."""

from __future__ import annotations

import math

import pytest

from stage_gen.components.worldgen import (
    AvoidRule,
    Candidate,
    ObjectSpec,
    PointIndex,
    PoissonProcess,
    Quota,
    SetPieceMember,
    SetPieceSpec,
    SpecError,
    Stream,
    WorldSpec,
    apply_quota,
    drop_neighbours,
    place_set_pieces,
    placement_order,
    plan_world,
)
from stage_gen.components.worldgen.spec import AttachedProcess

from ._world import EVERYWHERE, SEED, SIZE, fresh_fields, spec


def _cands(n: int, *, seed: int = 1, extent: float = 50.0) -> list[Candidate]:
    stream = Stream.of(seed, "cands")
    return [
        Candidate(
            x=stream.span(-extent, extent, i, 0),
            z=stream.span(-extent, extent, i, 1),
            key=(i,),
            parent=None,
            host=None,
            priority=stream.unit(i, 2),
            intensity=stream.unit(i, 3),
            passed=True,
        )
        for i in range(n)
    ]


def test_max_truncation_is_a_spatially_unbiased_subsample() -> None:
    cands = sorted(_cands(400), key=lambda c: (c.priority, c.key))
    kept, truncated, topped = apply_quota(
        list(cands), [], min_per_world=0, max_per_world=100, spacing_meters=0.0
    )
    assert (len(kept), truncated, topped) == (100, 300, 0)
    mean_x = sum(c.x for c in kept) / len(kept)
    mean_z = sum(c.z for c in kept) / len(kept)
    sigma = 50.0 / math.sqrt(3.0) / math.sqrt(100)
    assert abs(mean_x) < 3 * sigma and abs(mean_z) < 3 * sigma


def test_min_topup_prefers_high_intensity_and_clears_the_core() -> None:
    kept = _cands(3)
    reserve = _cands(50, seed=2)
    out, truncated, topped = apply_quota(
        list(kept), reserve, min_per_world=12, max_per_world=None, spacing_meters=2.0
    )
    assert (len(out), truncated, topped) == (12, 0, 9)
    added = out[3:]
    intensities = [c.intensity for c in added]
    assert intensities == sorted(intensities, reverse=True) or all(
        math.hypot(a.x - b.x, a.z - b.z) >= 2.0 for a in out for b in out if a is not b
    )
    for a in out:
        for b in out:
            if a is not b:
                assert math.hypot(a.x - b.x, a.z - b.z) >= 2.0


def test_the_neighbour_filter_only_removes() -> None:
    kept = _cands(60, extent=20.0)
    index = PointIndex(3.0)
    for i in range(10):
        index.add(kept[i].x, kept[i].z, 0.5, "other")
    obj = ObjectSpec("me", PoissonProcess(1.0), EVERYWHERE, footprint_radius_meters=0.5)
    final, dropped = drop_neighbours(kept, index, obj, footprint_of=lambda _: 0.5)
    assert dropped >= 10
    assert {c.key for c in final} <= {c.key for c in kept}
    avoider = ObjectSpec(
        "me",
        PoissonProcess(1.0),
        EVERYWHERE,
        avoid=(AvoidRule("other", 100.0),),
    )
    gone, dropped_all = drop_neighbours(kept, index, avoider, footprint_of=lambda _: 0.0)
    assert gone == [] and dropped_all == 60


def test_the_plan_is_byte_identical_and_sorted_by_address() -> None:
    first = plan_world(spec(), fresh_fields())
    second = plan_world(spec(), fresh_fields())
    assert first.points == second.points
    assert first.sites == second.sites
    assert first.refusals == ()
    for points in first.points.values():
        keys = [p.key for p in points]
        assert keys == sorted(keys)


def test_every_quota_and_every_hard_core_holds() -> None:
    world = spec()
    plan = plan_world(world, fresh_fields())
    for obj in world.objects:
        count = len(plan.points[obj.object_id])
        assert count >= obj.quota.min_per_world
        if obj.quota.max_per_world is not None:
            assert count <= obj.quota.max_per_world
        pts = plan.points[obj.object_id]
        for i, a in enumerate(pts):
            for b in pts[i + 1 :]:
                assert math.hypot(a.x - b.x, a.z - b.z) >= obj.spacing_meters - 1e-6
    assert len(plan.points["rare"]) == 2
    footprints = {obj.object_id: obj.footprint_radius_meters for obj in world.objects}
    footprints.update(dict(world.member_footprints))
    index = PointIndex(4.0)
    for p in plan.all_points():
        index.add(p.x, p.z, footprints[p.object_id], p.object_id)
    for site in plan.sites:
        for m in site.members:
            index.add(m.x, m.z, footprints[m.object_id], m.object_id)
    overlaps = list(index.pairs_closer_than(lambda a, b: footprints[a] + footprints[b] - 1e-6))
    assert overlaps == []


def test_set_pieces_site_at_the_origin_and_in_their_band() -> None:
    plan = plan_world(spec(), fresh_fields())
    ids = [site.instance_id for site in plan.sites]
    assert ids == ["camp/0", "ring/0", "ring/1"]
    camp = plan.sites[0]
    assert (camp.x, camp.z) == (0.0, 0.0)
    assert [m.object_id for m in camp.members] == ["tent", "fire"]
    for ring in plan.sites[1:]:
        assert 20.0 <= math.hypot(ring.x, ring.z) <= 50.0
    for p in plan.all_points():
        assert math.hypot(p.x, p.z) >= 5.0 - 1e-6


def test_a_set_piece_with_no_site_is_refused_by_name() -> None:
    nowhere = SetPieceSpec(
        "nowhere",
        (SetPieceMember("stone", 0.0, 0.0),),
        3.0,
        1,
        "band",
        (SIZE, SIZE * 2),
        frozenset(),
    )
    sites, refusals = place_set_pieces(WorldSpec(SEED, SIZE, (nowhere,), ()), fresh_fields())
    assert sites == ()
    assert refusals == [
        f"nowhere #0: no site in 256 tries (band {SIZE:g}..{SIZE * 2:g} m, regions [])"
    ]


def test_an_unreachable_minimum_is_refused_by_name() -> None:
    greedy = ObjectSpec(
        "greedy", PoissonProcess(0.01), EVERYWHERE, spacing_meters=40.0, quota=Quota(500, None)
    )
    plan = plan_world(WorldSpec(SEED, SIZE, (), (greedy,)), fresh_fields())
    assert len(plan.refusals) == 1
    assert plan.refusals[0].startswith("greedy: ") and "below min_per_world 500" in plan.refusals[0]


def test_placement_order_puts_hosts_first_and_refuses_a_cycle() -> None:
    a = ObjectSpec("a", AttachedProcess("b", 1.0, 1.0, 1.0), EVERYWHERE)
    b = ObjectSpec("b", PoissonProcess(1.0), EVERYWHERE, avoid=(AvoidRule("c", 2.0),))
    c = ObjectSpec("c", PoissonProcess(1.0), EVERYWHERE)
    assert [o.object_id for o in placement_order([a, b, c])] == ["c", "b", "a"]
    loop = ObjectSpec("c", PoissonProcess(1.0), EVERYWHERE, avoid=(AvoidRule("a", 2.0),))
    with pytest.raises(SpecError, match="cycle"):
        placement_order([a, b, loop])
    with pytest.raises(SpecError, match="unknown object"):
        placement_order([a])
    with pytest.raises(SpecError, match="twice"):
        placement_order([c, c])
