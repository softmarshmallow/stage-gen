"""The runner's gameplay contract: named profiles, no authored numbers.

An infinite runner's feel is four closed names - how it runs, how it jumps,
what a hit means, and (optionally) how it ducks - plus a ramp. Each name
declares its admission arithmetic as an SDK constant (the `experience_curve`
idiom: the contract names the feel, the consumer owns the numbers), so a track
is provable against the exact arc it will be played with before any art is
paid for. Scoring is runtime-owned: distance plus pickups, with nothing to
author in v2.

The rule that decides where a number lives: it belongs in the SDK constant
table iff a REFUSAL depends on it; it stays consumer-owned iff only the FEEL
depends on it. The arc constants below shape offline refusals (gap spans,
hazard press windows, overhead fit), so they are declared here and published
into the runtime manifest; the difficulty ramp's pacing shapes only feel and
stays in the consumer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Literal

from pydantic import Field, field_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import (
    GAME_ID_PATTERN,
    KEBAB_ID_PATTERN,
    canonical_contract_json,
    parse_toml_contract,
    sha256_bytes,
)

RUNNER_GAMEPLAY_SCHEMA_VERSION = 2

SpeedProfileName = Literal["steady_runner_v1"]
JumpProfileName = Literal["single_arc_v1", "double_arc_v1"]
CollisionPolicy = Literal["end_run_v1"]
DuckProfileName = Literal["slide_v1"]
RampProfile = Literal["gentle_ramp_v1"]


@dataclass(frozen=True, slots=True)
class SpeedProfile:
    """The admission arithmetic one speed name declares.

    Base speed is the slowest admitted speed - the worst case for press
    windows and gap spans, since airtime is fixed by construction and ramping
    only lengthens jumps and shortens hazard crossings. The multiplier CAP is
    the worst case for the opposite family of proofs: a faster run stretches
    every flown arc, so spacing rules (the apron, demand separation, the
    drop-scatter zone) must hold at `max_speed_multiplier`, and the consumer's
    ramp may never exceed it.
    """

    base_speed_columns_per_second: float
    max_speed_multiplier: float


SPEED_PROFILES: Final[dict[str, SpeedProfile]] = {
    "steady_runner_v1": SpeedProfile(base_speed_columns_per_second=6.0, max_speed_multiplier=1.5),
}


@dataclass(frozen=True, slots=True)
class JumpProfile:
    """The admission arithmetic one jump name declares.

    `max_clear_gap_columns` is the widest bottom-row pit run the avatar can
    clear at any admitted speed; `max_rise_tiles` is the tallest step the arc
    lands on. `peak_margin_tiles` and `airtime_headroom` complete the arc the
    runtime actually flies - peak `max_rise_tiles + peak_margin_tiles` rows,
    flat airtime `((gap + 1) / base_speed) * airtime_headroom` seconds - so the
    offline proofs and the played arc are the same closed forms, not a
    convention. `double_arc_v1` declares the identical single-hop arithmetic
    on purpose: its second hop is recovery, never reach, so admission stays a
    one-dimensional existential over launch columns and every chunk admitted
    under one name is clearable under the other.
    """

    max_clear_gap_columns: int
    max_rise_tiles: int
    peak_margin_tiles: float
    airtime_headroom: float


JUMP_PROFILES: Final[dict[str, JumpProfile]] = {
    "single_arc_v1": JumpProfile(
        max_clear_gap_columns=3, max_rise_tiles=2, peak_margin_tiles=0.75, airtime_headroom=1.15
    ),
    "double_arc_v1": JumpProfile(
        max_clear_gap_columns=3, max_rise_tiles=2, peak_margin_tiles=0.75, airtime_headroom=1.15
    ),
}


@dataclass(frozen=True, slots=True)
class CollisionProfile:
    """The collision-box discipline one collision name declares.

    The avatar's torso box and the hazard's inset footprint decide how long a
    hazard crossing lasts, which is half of every press-window proof.
    """

    avatar_half_width_columns: float
    hazard_column_inset: float


COLLISION_PROFILES: Final[dict[str, CollisionProfile]] = {
    "end_run_v1": CollisionProfile(avatar_half_width_columns=0.3, hazard_column_inset=0.15),
}


@dataclass(frozen=True, slots=True)
class DuckProfile:
    """The admission arithmetic one duck name declares.

    A ducked avatar stands `ducked_height_fraction` of its full height; an
    overhead hazard admits a slide only when its declared clearance holds that
    plus `min_overhead_clearance_rows` of daylight, and refuses a standing run
    only when its clearance sits below the full height by the same margin.
    """

    ducked_height_fraction: float
    min_overhead_clearance_rows: float


DUCK_PROFILES: Final[dict[str, DuckProfile]] = {
    "slide_v1": DuckProfile(ducked_height_fraction=0.5, min_overhead_clearance_rows=0.25),
}


@dataclass(frozen=True, slots=True)
class PlacementProfile:
    """The placement discipline every admitted chunk is proved against.

    Deliberately not a `JumpProfile` concern: traversal capability and
    placement fairness are different disciplines, and only this one refuses
    layouts. One member exists, selected by `RUNNER_PLACEMENT_PROFILE`; the
    name becomes a persisted field in one bump the moment a second discipline
    (a deliberately unsignposted `telegraph = "none_v1"`, say) exists.

    - `apron_headroom` scales one jump's flat span - flown at the speed CAP,
      the spacing worst case - into the calm zone required at both ends of
      every chunk, which is what makes any chunk safe to follow any chunk
      without a cross-chunk check.
    - `min_hazard_separation_columns` exceeds one jump's flown span at the
      speed cap (4.6 x 1.5 = 6.9 columns), so two demands - hazard clusters
      and terrain features alike - never share an arc unless authored as one
      adjacent cluster.
    - `min_landing_clear_columns` guarantees calm ground after every pit and
      rise landing; the end apron extends the same guarantee across the seam.
    - `min_hazard_clear_seconds` is the smallest admissible press window over
      any hazard cluster, proved from the arc at base speed.
    - `telegraph` names the teaching channel authored chunks must carry.
    """

    apron_headroom: float
    min_hazard_separation_columns: int
    min_landing_clear_columns: int
    min_hazard_clear_seconds: float
    telegraph: Literal["pickup_arc_v1"]


PLACEMENT_PROFILES: Final[dict[str, PlacementProfile]] = {
    "reaction_fair_v1": PlacementProfile(
        apron_headroom=1.15,
        min_hazard_separation_columns=8,
        min_landing_clear_columns=3,
        min_hazard_clear_seconds=0.15,
        telegraph="pickup_arc_v1",
    ),
}

#: The one placement discipline current admission proves. A constant, not a
#: persisted field: a one-member vocabulary nobody can choose between.
RUNNER_PLACEMENT_PROFILE: Final[str] = "reaction_fair_v1"

# The end apron is what lets a landing-clearance window run off a chunk's edge:
# every placement discipline must keep the apron at least as calm as the
# clearance it promises.
for _placement in PLACEMENT_PROFILES.values():
    _apron = math.ceil(
        (JUMP_PROFILES["single_arc_v1"].max_clear_gap_columns + 1)
        * _placement.apron_headroom
        * SPEED_PROFILES["steady_runner_v1"].max_speed_multiplier
    )
    if _apron < _placement.min_landing_clear_columns:
        raise AssertionError("placement apron must cover its own landing clearance")


@dataclass(frozen=True, slots=True)
class JumpArc:
    """The closed-form arc a jump name flies, shared by admission and runtime."""

    initial_speed_rows_per_second: float
    gravity_rows_per_second_squared: float
    peak_rows: float
    airtime_seconds: float


def jump_arc(jump: JumpProfile, speed: SpeedProfile) -> JumpArc:
    """Derive the arc from the declared arithmetic: v0 = 4P/T, g = 8P/T^2."""

    peak_rows = jump.max_rise_tiles + jump.peak_margin_tiles
    airtime_seconds = (
        (jump.max_clear_gap_columns + 1) / speed.base_speed_columns_per_second
    ) * jump.airtime_headroom
    return JumpArc(
        initial_speed_rows_per_second=4 * peak_rows / airtime_seconds,
        gravity_rows_per_second_squared=8 * peak_rows / (airtime_seconds * airtime_seconds),
        peak_rows=peak_rows,
        airtime_seconds=airtime_seconds,
    )


def apron_columns(jump: JumpProfile, placement: PlacementProfile, speed: SpeedProfile) -> int:
    """Calm columns at each chunk end: one flat jump span flown at the speed cap."""

    return math.ceil(
        (jump.max_clear_gap_columns + 1) * placement.apron_headroom * speed.max_speed_multiplier
    )


def drop_scatter_columns(arc: JumpArc, speed: SpeedProfile, depth_rows: float) -> int:
    """Columns a run-off fall can drift before landing, at the speed cap.

    A drop-off is a landing with no launch: the avatar leaves the ledge at
    full forward speed and touches down sqrt(2d/g) seconds later. Everything
    inside that scatter must be level and calm, because no verb is available
    mid-fall under the single-hop arithmetic.
    """

    fall_seconds = math.sqrt(2 * max(0.0, depth_rows) / arc.gravity_rows_per_second_squared)
    return math.ceil(
        fall_seconds * speed.base_speed_columns_per_second * speed.max_speed_multiplier
    )


def landing_time_seconds(arc: JumpArc, rise_rows: float) -> float | None:
    """Seconds until the descending branch reaches `rise_rows` above takeoff.

    Positive rise is upward. None means the arc never reaches that height, so
    no landing exists.
    """

    v0 = arc.initial_speed_rows_per_second
    g = arc.gravity_rows_per_second_squared
    discriminant = v0 * v0 - 2 * g * rise_rows
    if discriminant < 0:
        return None
    return (v0 + math.sqrt(discriminant)) / g


def clearable_span_columns(arc: JumpArc, speed: SpeedProfile, rise_rows: float) -> float | None:
    """Horizontal columns one jump covers before landing `rise_rows` up (or down).

    Proved at base speed - the worst case, since airtime is fixed and ramping
    only stretches the span. A rise steals airtime, so a max-width pit and a
    max-height rise are not simultaneously clearable and admission must see
    them together, not as two independent bounds.
    """

    landing = landing_time_seconds(arc, rise_rows)
    if landing is None:
        return None
    return landing * speed.base_speed_columns_per_second


def arc_height_rows(arc: JumpArc, speed: SpeedProfile, columns_from_launch: float) -> float:
    """Rows above the takeoff surface at a horizontal offset, at base speed."""

    t = columns_from_launch / speed.base_speed_columns_per_second
    return arc.initial_speed_rows_per_second * t - arc.gravity_rows_per_second_squared * t * t / 2


def hazard_press_window_seconds(
    arc: JumpArc,
    speed: SpeedProfile,
    collision: CollisionProfile,
    *,
    hazard_height_rows: float,
    span_columns: float = 1.0,
) -> float:
    """Seconds of launch timing that clear a hazard cluster, at base speed.

    The arc stays above the hazard's height for a fixed window; crossing the
    cluster's x-overlap (its inset span plus the avatar's torso) spends part of
    it. What remains is the press window - the launch-timing slack a player
    actually has. Negative means the silhouette is unjumpable at any timing.
    """

    v0 = arc.initial_speed_rows_per_second
    g = arc.gravity_rows_per_second_squared
    discriminant = v0 * v0 - 2 * g * hazard_height_rows
    if discriminant <= 0:
        return float("-inf")
    above_seconds = 2 * math.sqrt(discriminant) / g
    crossing_columns = (
        span_columns - 2 * collision.hazard_column_inset + 2 * collision.avatar_half_width_columns
    )
    return above_seconds - crossing_columns / speed.base_speed_columns_per_second


class RunnerRun(PersistedContractModel):
    speed_profile: SpeedProfileName
    jump_profile: JumpProfileName
    collision_policy: CollisionPolicy
    #: Absent means the avatar cannot duck and the track may not hang overhead
    #: hazards; present, it obligates a drawn slide motion.
    duck_profile: DuckProfileName | None = None


class RunnerRamp(PersistedContractModel):
    profile: RampProfile


class RunnerGameplayContract(PersistedContractModel):
    schema_version: Literal[2]
    kind: Literal["runner-gameplay-v2"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    #: The single track this gameplay is played on. Exactly one in v2: an
    #: endless run has no map graph, and a second track is a second member.
    track_id: str = Field(pattern=KEBAB_ID_PATTERN, max_length=96)
    run: RunnerRun
    ramp: RunnerRamp

    @field_validator("track_id")
    @classmethod
    def validate_track_id(cls, value: str) -> str:
        return value

    def jump_profile(self) -> JumpProfile:
        return JUMP_PROFILES[self.run.jump_profile]

    def speed_profile(self) -> SpeedProfile:
        return SPEED_PROFILES[self.run.speed_profile]

    def collision_profile(self) -> CollisionProfile:
        return COLLISION_PROFILES[self.run.collision_policy]

    def duck_profile(self) -> DuckProfile | None:
        if self.run.duck_profile is None:
            return None
        return DUCK_PROFILES[self.run.duck_profile]


def load_runner_gameplay_bytes(data: bytes) -> RunnerGameplayContract:
    return parse_toml_contract(data, model=RunnerGameplayContract, label="runner gameplay contract")


def canonical_runner_gameplay_json(contract: RunnerGameplayContract) -> bytes:
    return canonical_contract_json(contract)


def runner_gameplay_sha256(contract: RunnerGameplayContract) -> str:
    return sha256_bytes(canonical_runner_gameplay_json(contract))


__all__ = [
    "COLLISION_PROFILES",
    "DUCK_PROFILES",
    "JUMP_PROFILES",
    "PLACEMENT_PROFILES",
    "RUNNER_GAMEPLAY_SCHEMA_VERSION",
    "RUNNER_PLACEMENT_PROFILE",
    "SPEED_PROFILES",
    "CollisionPolicy",
    "CollisionProfile",
    "DuckProfile",
    "DuckProfileName",
    "JumpArc",
    "JumpProfile",
    "JumpProfileName",
    "PlacementProfile",
    "RampProfile",
    "RunnerGameplayContract",
    "RunnerRamp",
    "RunnerRun",
    "SpeedProfile",
    "SpeedProfileName",
    "apron_columns",
    "arc_height_rows",
    "canonical_runner_gameplay_json",
    "clearable_span_columns",
    "drop_scatter_columns",
    "hazard_press_window_seconds",
    "jump_arc",
    "landing_time_seconds",
    "load_runner_gameplay_bytes",
    "runner_gameplay_sha256",
]
