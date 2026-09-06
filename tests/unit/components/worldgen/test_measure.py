"""The estimator reads synthetic patterns, and refuses a block that did nothing."""

from __future__ import annotations

from stage_gen.components.worldgen import (
    ClusterProcess,
    ObjectSpec,
    PoissonProcess,
    SpacedProcess,
    WorldSpec,
    mean_nearest_neighbour,
    measure_object,
    neighbours_within,
    plan_world,
    refuse_patterns,
)

from ._world import EVERYWHERE, SEED, SIZE, flat_fields


def _measure(obj: ObjectSpec) -> tuple[str, float, float]:
    world = WorldSpec(SEED, SIZE, (), (obj,))
    fields = flat_fields()
    plan = plan_world(world, fields)
    report = measure_object(world, fields, obj, plan.points[obj.object_id])
    return report.verdict, report.r_mc, report.k_ratio


def test_the_estimator_reads_a_poisson_pattern_as_random() -> None:
    verdict, r_mc, _ = _measure(ObjectSpec("dot", PoissonProcess(3.0), EVERYWHERE))
    assert verdict == "random"
    assert 0.9 < r_mc < 1.1


def test_the_estimator_reads_a_cluster_as_clustered() -> None:
    verdict, r_mc, k_ratio = _measure(
        ObjectSpec("grove", ClusterProcess(0.5, 10.0, 4.0), EVERYWHERE, spacing_meters=0.5)
    )
    assert verdict == "clustered"
    assert r_mc < 0.7
    assert k_ratio > 2.0


def test_the_estimator_reads_a_jittered_grid_as_spaced() -> None:
    verdict, r_mc, _ = _measure(ObjectSpec("blade", SpacedProcess(3.0), EVERYWHERE))
    assert verdict == "spaced"
    assert r_mc > 1.2


def test_the_report_is_deterministic() -> None:
    obj = ObjectSpec("grove", ClusterProcess(0.12, 6.0, 4.0), EVERYWHERE)
    assert _measure(obj) == _measure(obj)


def test_a_cluster_that_clusters_nothing_is_refused() -> None:
    wide = ObjectSpec("wide", ClusterProcess(0.02, 30.0, 45.0), EVERYWHERE, spacing_meters=1.0)
    world = WorldSpec(SEED, SIZE, (), (wide,))
    fields = flat_fields()
    plan = plan_world(world, fields)
    report = measure_object(world, fields, wide, plan.points["wide"])
    problems = refuse_patterns(world, [report])
    assert problems and problems[0].startswith("wide: authored as a cluster but came out random")


def test_small_counts_are_reported_never_refused() -> None:
    few = ObjectSpec("few", ClusterProcess(0.001, 2.0, 3.0), EVERYWHERE)
    world = WorldSpec(SEED, SIZE, (), (few,))
    fields = flat_fields()
    plan = plan_world(world, fields)
    report = measure_object(world, fields, few, plan.points["few"])
    assert report.verdict == "unmeasurable"
    assert refuse_patterns(world, [report]) == []


def test_the_bucketed_statistics_match_brute_force() -> None:
    from stage_gen.components.worldgen import Stream

    stream = Stream.of(5, "points")
    points = [(stream.span(-30.0, 30.0, i, 0), stream.span(-30.0, 30.0, i, 1)) for i in range(300)]
    brute_nn = sum(
        min(((x - px) ** 2 + (z - pz) ** 2) ** 0.5 for px, pz in points if (px, pz) != (x, z))
        for x, z in points
    ) / len(points)
    assert abs(mean_nearest_neighbour(points) - brute_nn) < 1e-9
    radius = 4.0
    brute_k = sum(
        sum(1 for px, pz in points if 0.0 < (x - px) ** 2 + (z - pz) ** 2 < radius * radius)
        for x, z in points
    ) / len(points)
    assert abs(neighbours_within(points, radius) - brute_k) < 1e-9
