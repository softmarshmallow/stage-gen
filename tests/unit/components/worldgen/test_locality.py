"""Editing one object's block moves that object, and nothing beyond one footprint of it.

L1: every untouched object's candidate list is bit-identical.
L2: every untouched object's tier-1 + quota set is bit-identical.
L3: every point of an untouched object farther than R from every changed point
    of the edited object is identical, and the number of changed points equals
    the number within R: no cascade.
Attachment is the exception by design (a fern follows its pine), and a seed
change moves everything, so nobody reads L1 as more than it is.
"""

from __future__ import annotations

import math
from dataclasses import replace

from stage_gen.components.worldgen import (
    AttachedProcess,
    Placed,
    WorldPlan,
    WorldSpec,
    accept_own,
    apply_quota,
    candidates_for,
    plan_world,
)

from ._world import SEED, fresh_fields, spec


def _plans(edited: WorldSpec) -> tuple[WorldSpec, WorldPlan, WorldPlan]:
    base = spec()
    return base, plan_world(base, fresh_fields()), plan_world(edited, fresh_fields())


def _closure(world: WorldSpec, object_id: str) -> set[str]:
    out = {object_id}
    grown = True
    while grown:
        grown = False
        for obj in world.objects:
            if (
                isinstance(obj.process, AttachedProcess)
                and obj.process.host_object_id in out
                and obj.object_id not in out
            ):
                out.add(obj.object_id)
                grown = True
    return out


def _reach(world: WorldSpec, edited: str, other: str) -> float:
    rho = max(
        [o.footprint_radius_meters for o in world.objects] + [r for _, r in world.member_footprints]
    )
    alpha = 0.0
    for obj in world.objects:
        for rule in obj.avoid:
            if {obj.object_id, rule.object_id} == {edited, other}:
                alpha = max(alpha, rule.radius_meters)
    return world.object(other).footprint_radius_meters + max(rho, alpha)


def _delta(before: tuple[Placed, ...], after: tuple[Placed, ...]) -> list[Placed]:
    return [p for p in set(before) ^ set(after)]


def _assert_local(edited_id: str, edited: WorldSpec) -> None:
    base, first, second = _plans(edited)
    closure = _closure(base, edited_id)
    delta = _delta(first.points[edited_id], second.points[edited_id])
    assert delta, "the edit must change the edited object, or the test proves nothing"
    for obj in base.objects:
        if obj.object_id in closure:
            continue
        # L1 and L2 on the same fresh fields the plans saw, minus the edited
        # object's clearings (none of these objects declare any).
        fields_a, fields_b = fresh_fields(), fresh_fields()
        for f, w in ((fields_a, base), (fields_b, edited)):
            sites = plan_world(w, f).sites  # re-sites the set pieces into the fields
            assert sites
        assert candidates_for(obj, fields_a, SEED) == candidates_for(obj, fields_b, SEED)
        passed = sorted(
            (c for c in candidates_for(obj, fields_a, SEED) if c.passed),
            key=lambda c: (c.priority, c.key),
        )
        reserve = [c for c in candidates_for(obj, fields_a, SEED) if not c.passed]
        kept_a, _ = accept_own(passed, obj.spacing_meters)
        kept_a, _, _ = apply_quota(
            kept_a,
            reserve,
            min_per_world=obj.quota.min_per_world,
            max_per_world=obj.quota.max_per_world,
            spacing_meters=obj.spacing_meters,
        )
        passed_b = sorted(
            (c for c in candidates_for(obj, fields_b, SEED) if c.passed),
            key=lambda c: (c.priority, c.key),
        )
        kept_b, _ = accept_own(passed_b, obj.spacing_meters)
        kept_b, _, _ = apply_quota(
            kept_b,
            reserve,
            min_per_world=obj.quota.min_per_world,
            max_per_world=obj.quota.max_per_world,
            spacing_meters=obj.spacing_meters,
        )
        assert kept_a == kept_b
        # L3.
        reach = _reach(base, edited_id, obj.object_id)
        before = {p.key: p for p in first.points[obj.object_id]}
        after = {p.key: p for p in second.points[obj.object_id]}
        changed = [k for k in set(before) | set(after) if before.get(k) != after.get(k)]
        for key in changed:
            point = before.get(key) or after[key]
            assert min(math.hypot(point.x - d.x, point.z - d.z) for d in delta) <= reach, (
                f"{obj.object_id} point {key} moved farther than {reach:.2f} m from the edit"
            )


def test_a_density_edit_is_local() -> None:
    _assert_local("tree", spec(tree_density=0.8))


def test_a_rarity_edit_is_local() -> None:
    _assert_local("tree", spec(tree_chance=0.5))


def test_a_quota_edit_is_local() -> None:
    base = spec()
    stone = replace(
        base.object("stone"), quota=replace(base.object("stone").quota, max_per_world=40)
    )
    edited = replace(
        base, objects=tuple(stone if o.object_id == "stone" else o for o in base.objects)
    )
    _assert_local("stone", edited)


def test_the_attach_closure_follows_its_host() -> None:
    base, first, second = _plans(spec(tree_density=0.8))
    assert first.points["fern"] != second.points["fern"]
    fern = base.object("fern")
    assert isinstance(fern.process, AttachedProcess) and fern.process.host_object_id == "tree"


def test_changing_the_seed_changes_everything() -> None:
    first = plan_world(spec(), fresh_fields())
    second = plan_world(spec(SEED + 1), fresh_fields(SEED + 1))
    for object_id, points in first.points.items():
        assert points != second.points[object_id]
