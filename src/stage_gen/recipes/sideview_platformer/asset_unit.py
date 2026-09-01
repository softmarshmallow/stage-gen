"""The platformer's rank ladder over the shared asset-unit contract.

Measurement, calibration, and admission are camera-scoped and live in
`stage_gen.components.sideview_actor.asset_unit`. What stays here is the RPG
vocabulary: a mob's magnitude resolved from its declared rank, and the ladder
admission that keeps silhouette height carrying threat.
"""

from __future__ import annotations

from collections.abc import Mapping
from itertools import pairwise

from stage_gen.components.game_contract.package import PreparedScale
from stage_gen.components.sideview_actor.asset_unit import AssetUnitError, ResolvedMagnitude


def resolve_rank_magnitude(scale: PreparedScale, rank: str) -> ResolvedMagnitude:
    """A mob's magnitude is a gameplay parameter, resolved from its rank so size carries threat."""

    units = scale.rank_units(rank)
    if units is None:
        raise AssetUnitError(
            f"the game declares no [scale.ranks] entry for rank {rank!r}, so a mob of that rank "
            "resolves no magnitude"
        )
    return ResolvedMagnitude(units, "rank")


def admit_rank_ladder(scale: PreparedScale, ranks_by_mob: Mapping[str, str]) -> None:
    """Silhouette height must carry threat, so the ladder is admitted rather than assumed."""

    order = ["common", "uncommon", "elite", "boss"]
    resolved: list[tuple[str, float]] = []
    for rank in order:
        units = scale.rank_units(rank)
        if units is not None:
            resolved.append((rank, units))
    for (lower_rank, lower), (higher_rank, higher) in pairwise(resolved):
        if higher <= lower:
            raise AssetUnitError(
                f"rank {higher_rank!r} resolves {higher} units, not above {lower_rank!r} at "
                f"{lower}; a player reads danger from the size ladder before the artwork"
            )
    for rank, units in resolved:
        if rank != "boss" and units > 1.0:
            raise AssetUnitError(
                f"non-boss rank {rank!r} resolves {units} units, above the player; only a boss "
                "may loom over the character it threatens"
            )
    for mob_id, rank in sorted(ranks_by_mob.items()):
        if scale.rank_units(rank) is None:
            raise AssetUnitError(f"mob {mob_id!r} has rank {rank!r} with no declared magnitude")


__all__ = ["admit_rank_ladder", "resolve_rank_magnitude"]
