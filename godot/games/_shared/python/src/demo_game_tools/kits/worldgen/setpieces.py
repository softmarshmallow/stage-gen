"""Set pieces: authored compositions sited whole, before any object is placed.

A set piece is a list of members at offsets from an anchor, a clearing the
population keeps out of, a count, and where it may stand: at the origin (the
one the player spawns on) or in an annulus of distances from the origin, on a
required region. Sites are drawn by hashed candidates and refused by name
when the world offers none, because a set piece that is silently missing is
worse than a run that says so.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from .fields import Clearing, WorldFields
from .hashing import Stream
from .spec import SetPieceSpec, WorldSpec

#: Hashed candidates tried for one set-piece instance before refusal.
MAX_SITE_TRIES: Final = 256


@dataclass(frozen=True, slots=True)
class MemberPoint:
    object_id: str
    x: float
    z: float
    mark: int


@dataclass(frozen=True, slots=True)
class SetPieceSite:
    set_piece_id: str
    ordinal: int
    x: float
    z: float
    clearing_radius_meters: float
    members: tuple[MemberPoint, ...]

    @property
    def instance_id(self) -> str:
        return f"{self.set_piece_id}/{self.ordinal}"

    @property
    def clearing(self) -> Clearing:
        return Clearing(self.x, self.z, self.clearing_radius_meters)


def _site_ok(
    x: float, z: float, spec: SetPieceSpec, fields: WorldFields, placed: list[SetPieceSite]
) -> bool:
    if spec.required_regions and fields.region_at(x, z) not in spec.required_regions:
        return False
    if not fields.clearing_on_land(x, z, spec.clearing_radius_meters):
        return False
    for member in spec.members:
        if not fields.on_land(x + member.dx, z + member.dz, fields.shore_margin_meters):
            return False
    for site in placed:
        if (
            math.hypot(x - site.x, z - site.z)
            < site.clearing_radius_meters + spec.clearing_radius_meters
        ):
            return False
    return True


def _build(x: float, z: float, spec: SetPieceSpec, ordinal: int) -> SetPieceSite:
    return SetPieceSite(
        set_piece_id=spec.set_piece_id,
        ordinal=ordinal,
        x=round(x, 3),
        z=round(z, 3),
        clearing_radius_meters=spec.clearing_radius_meters,
        members=tuple(
            MemberPoint(
                object_id=member.object_id,
                x=round(x + member.dx, 3),
                z=round(z + member.dz, 3),
                mark=member.mark,
            )
            for member in spec.members
        ),
    )


def place_set_pieces(
    spec: WorldSpec, fields: WorldFields
) -> tuple[tuple[SetPieceSite, ...], list[str]]:
    """Every set piece's sites, in declaration order, and the refusals."""

    sites: list[SetPieceSite] = []
    refusals: list[str] = []
    for piece in spec.set_pieces:
        site_s = Stream.of(spec.seed, piece.set_piece_id, "setpiece", "site")
        for ordinal in range(piece.count_per_world):
            if piece.at == "origin":
                if _site_ok(0.0, 0.0, piece, fields, sites):
                    sites.append(_build(0.0, 0.0, piece, ordinal))
                else:
                    refusals.append(f"{piece.set_piece_id}: the origin is not a usable site")
                continue
            r0, r1 = piece.band_meters
            found: tuple[float, float] | None = None
            for attempt in range(MAX_SITE_TRIES):
                u = site_s.unit(ordinal, attempt, 0)
                v = site_s.unit(ordinal, attempt, 1)
                # Area-uniform in the annulus, so the far band is not starved.
                r = math.sqrt(r0 * r0 + u * (r1 * r1 - r0 * r0))
                a = v * math.tau
                x, z = math.cos(a) * r, math.sin(a) * r
                if _site_ok(x, z, piece, fields, sites):
                    found = (x, z)
                    break
            if found is None:
                refusals.append(
                    f"{piece.set_piece_id} #{ordinal}: no site in {MAX_SITE_TRIES} tries "
                    f"(band {r0:g}..{r1:g} m, regions {sorted(piece.required_regions)})"
                )
                continue
            sites.append(_build(found[0], found[1], piece, ordinal))
    return tuple(sites), refusals
