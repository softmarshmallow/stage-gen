"""The runner's gameplay contract: named profiles, no authored numbers.

An infinite runner's feel is a handful of closed names - how it runs, how it
jumps, how wide it collides, what each way of coming to grief costs, and
(optionally) how it ducks - plus a ramp. Each name
declares its admission arithmetic as an SDK constant (the `experience_curve`
idiom: the contract names the feel, the consumer owns the numbers), so a track
is provable against the exact arc it will be played with before any art is
paid for. Scoring is runtime-owned: distance plus pickups, with nothing to
author.

v3 splits what v2's `collision_policy` had conflated. That one name carried
the avatar's torso box - which every press-window proof reads - *and* asserted
that a hazard ends the run, and the two are unrelated: the box is geometry
admission depends on, while what a contact costs is a consequence the package
chooses. So `collision_box` keeps the geometry under an honest name, and a
`[run.consequences]` table answers the separate question once per way of
coming to grief. `end_run_v1` survives there, as the consequence it always
was.

Admission is unchanged and stays exactly as strict. A gauge is forgiveness
laid over a fair track, never a licence to author an unfair one: every hazard
must still be provably avoidable at the base speed, whether or not surviving
it is possible.

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

from pydantic import Field, field_validator, model_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import (
    GAME_ID_PATTERN,
    KEBAB_ID_PATTERN,
    SNAKE_ID_PATTERN,
    canonical_contract_json,
    parse_toml_contract,
    sha256_bytes,
)

RUNNER_GAMEPLAY_SCHEMA_VERSION = 4

SpeedProfileName = Literal["steady_runner_v1", "brisk_runner_v1", "swift_runner_v1"]
JumpProfileName = Literal["single_arc_v1", "double_arc_v1"]
CollisionBoxName = Literal["torso_v1"]
DuckProfileName = Literal["slide_v1"]
RampProfile = Literal["gentle_ramp_v1", "brisk_ramp_v1"]

#: How the avatar converts intent into vertical motion while an override is
#: running. Not a mode flag: each name carries its own admission arithmetic,
#: because a track flown under thrust has no gaps to clear - it has corridors
#: to fit through - and a proof written for arcs says nothing about it.
LocomotionProfileName = Literal["thrust_v1"]

#: How one boss fights. One name, one closed set of numbers, every one of them
#: read by a refusal below.
BossProfileName = Literal["barrage_boss_v1"]

#: How much of the run one way of coming to grief costs.
#:
#: `end_run_v1` is terminal. `drain_v1` spends one point of the vitals gauge
#: and opens its refractory window, leaving the avatar where it stands - right
#: for a hazard the avatar runs through. `drain_and_recover_v1` spends the same
#: point and then places the avatar back on the next legal surface, which is
#: what a pit or a crush needs, because there is nowhere to leave it standing.
ConsequenceName = Literal["end_run_v1", "drain_v1", "drain_and_recover_v1"]

#: Every way a run can come to grief. Each one is answered separately, so a
#: package can forgive a clipped hazard while keeping a pit final. `shot` is
#: reachable only during an encounter, which is why the contract refuses it
#: without one and refuses an encounter without it.
DamageSource = Literal["hazard", "pit", "crush", "shot"]

VitalsProfileName = Literal["single_point_v1", "three_point_v1", "five_point_v1"]

#: How a survivable hit is shown.
#:
#: `docs/game-contract.md` requires that visible gameplay have visual coverage:
#: a subsystem may not advertise an actor transition unless a validated asset
#: or an explicitly contracted nonvisual representation exists for it.
#: `blink_v1` is that contracted nonvisual representation, stated rather than
#: assumed - the avatar keeps its running pose and the consumer blinks it for
#: the refractory window. `drawn_v1` obligates a drawn `hurt` motion instead.
HurtRepresentation = Literal["blink_v1", "drawn_v1"]


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
    "brisk_runner_v1": SpeedProfile(base_speed_columns_per_second=7.5, max_speed_multiplier=1.5),
    # Every press window scales as 1 / base speed (the arc is speed-invariant
    # in columns, so time-above-height and crossing time shrink together), so
    # a faster name re-opens admission on every authored track rather than
    # relaxing it: a hazard that cleared at 7.5 by a hair refuses at 9.0.
    "swift_runner_v1": SpeedProfile(base_speed_columns_per_second=9.0, max_speed_multiplier=1.5),
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
    """The collision-box discipline one collision-box name declares.

    The avatar's torso box and the hazard's inset footprint decide how long a
    hazard crossing lasts, which is half of every press-window proof. Purely
    geometry: what a contact then costs is a consequence, and lives in its own
    table so the two can be chosen independently.
    """

    avatar_half_width_columns: float
    hazard_column_inset: float


COLLISION_BOXES: Final[dict[str, CollisionProfile]] = {
    "torso_v1": CollisionProfile(avatar_half_width_columns=0.3, hazard_column_inset=0.15),
}


@dataclass(frozen=True, slots=True)
class VitalsProfile:
    """The gauge one vitals name declares.

    Only the point count lives here, and only because a refusal and the HUD
    both read it: a package with one point is one-hit-kill however its
    consequences are worded, and a bar cannot be drawn without its maximum.
    Everything else about how a hit feels - the refractory window, the blink
    interval, how far recovery looks ahead - is consumer-owned, exactly as the
    difficulty ramp's pacing is.
    """

    max_points: int


VITALS_PROFILES: Final[dict[str, VitalsProfile]] = {
    "single_point_v1": VitalsProfile(max_points=1),
    "three_point_v1": VitalsProfile(max_points=3),
    "five_point_v1": VitalsProfile(max_points=5),
}

#: The consequences that spend a point, and therefore oblige a gauge to spend.
DRAINING_CONSEQUENCES: Final[frozenset[str]] = frozenset({"drain_v1", "drain_and_recover_v1"})


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
class ThrustProfile:
    """The admission arithmetic one locomotion name declares.

    Thrust is held-climb, released-fall: one acceleration drives the avatar
    toward whichever cap the held state selects. One acceleration rather than
    two because the asymmetry that matters is the pair of caps - a rise that
    is slower than the fall is what keeps a dodge honest - and a second
    acceleration would be a number no refusal reads.

    The worst-case traverse of a band is therefore the CLIMB, whose cap is the
    lower of the two; every dodge proof below is written against it.
    """

    max_climb_rows_per_second: float
    max_fall_rows_per_second: float
    climb_acceleration_rows_per_second2: float


THRUST_PROFILES: Final[dict[str, ThrustProfile]] = {
    "thrust_v1": ThrustProfile(
        max_climb_rows_per_second=9.0,
        max_fall_rows_per_second=10.0,
        climb_acceleration_rows_per_second2=24.0,
    ),
}


@dataclass(frozen=True, slots=True)
class BossProfile:
    """The admission arithmetic one boss name declares.

    Every field is read by one of the three refusals below, which is why they
    are all here rather than split with the consumer: how the boss *reads* -
    its approach speed, its hit flash, its bob - is feel and stays in the
    runtime, but how far it stands off, how fast it fires and how much it can
    fire decide whether the fight is survivable and winnable, and those are
    refusals.

    - `firing_distance_columns` with `projectile_speed_columns_per_second`
      fixes the time a shot spends in the air, which is the dodge budget.
      The speed is measured in the AVATAR's frame: the run carries both, so
      what a player experiences is the closing speed, and admission proves the
      number the player actually gets.
    - `projectile_height_rows` and `salvo_shots` decide how much of the band a
      salvo can occupy, and `lane_margin_rows` how much daylight the lane must
      keep beyond the avatar's own silhouette.
    - `salvo_budget` and `salvo_period_seconds` bound the encounter, and with
      `hits_to_defeat`, `player_fire_period_seconds` and
      `player_shot_speed_columns_per_second` decide whether it can be won
      before it ends.
    """

    firing_distance_columns: int
    projectile_speed_columns_per_second: float
    projectile_height_rows: float
    salvo_shots: int
    salvo_period_seconds: float
    salvo_budget: int
    lane_margin_rows: float
    hits_to_defeat: int
    player_fire_period_seconds: float
    player_shot_speed_columns_per_second: float


BOSS_PROFILES: Final[dict[str, BossProfile]] = {
    "barrage_boss_v1": BossProfile(
        firing_distance_columns=10,
        projectile_speed_columns_per_second=7.5,
        projectile_height_rows=1.0,
        salvo_shots=3,
        salvo_period_seconds=1.5,
        salvo_budget=16,
        lane_margin_rows=0.5,
        hits_to_defeat=24,
        player_fire_period_seconds=0.5,
        player_shot_speed_columns_per_second=12.0,
    ),
}

#: The shortest run an encounter may be authored to interrupt, in columns.
#:
#: A refusal reads it, so it is arithmetic rather than taste: twice the widest
#: chunk the track contract admits (64 columns), which is the shortest gap that
#: guarantees at least one WHOLE authored chunk is run between two fights
#: however the chunk boundaries happen to fall. Below it a track could be
#: authored whose player never sees a complete piece of it - the fight would
#: have become the game and the track its interruption, which is the wrong way
#: round. `test_encounter_contract` pins the derivation against the track
#: contract's own maximum so the two cannot drift apart.
MIN_ENCOUNTER_INTERVAL_COLUMNS: Final[int] = 128


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


def thrust_traverse_seconds(thrust: ThrustProfile, rows: float) -> float:
    """Worst-case seconds to cross `rows` of band under one thrust profile.

    The climb, always: its cap is the lower of the two, so an avatar that can
    climb the band in time can certainly fall it in time. Accelerate from rest
    to the cap, then hold it - a triangle followed by a rectangle. If the band
    is short enough that the cap is never reached, the whole crossing is the
    triangle.
    """

    if rows <= 0:
        return 0.0
    cap = thrust.max_climb_rows_per_second
    accel = thrust.climb_acceleration_rows_per_second2
    time_to_cap = cap / accel
    rows_to_cap = cap * time_to_cap / 2
    if rows <= rows_to_cap:
        return math.sqrt(2 * rows / accel)
    return time_to_cap + (rows - rows_to_cap) / cap


def boss_lane_rows(boss: BossProfile, walk_surface_row: int) -> float:
    """Rows a salvo must leave open, at worst, in the playable band.

    A pigeonhole, not a simulation: the band above the walk surface is
    `walk_surface_row` rows tall, a salvo can occupy at most
    `salvo_shots * projectile_height_rows` of it, and what is left over is the
    smallest lane any placement can leave. Whether the lane is contiguous is
    the runtime's obligation, stated by publishing these numbers; whether it
    is large enough is this refusal.
    """

    return walk_surface_row - boss.salvo_shots * boss.projectile_height_rows


def boss_dodge_window_seconds(
    boss: BossProfile,
    thrust: ThrustProfile,
    *,
    walk_surface_row: int,
) -> float:
    """Seconds of slack between seeing a salvo and having to be clear of it.

    The same discipline as `hazard_press_window_seconds`, written for the
    other locomotion: a shot's flight time is what the player is given, the
    worst-case traverse of the whole band is what the dodge costs, and the
    remainder is the reaction slack the placement profile's
    `min_hazard_clear_seconds` is compared against. Negative means the salvo
    arrives before the avatar could have crossed to meet it.
    """

    flight = boss.firing_distance_columns / boss.projectile_speed_columns_per_second
    return flight - thrust_traverse_seconds(thrust, walk_surface_row)


def boss_kill_seconds(boss: BossProfile) -> float:
    """Seconds to defeat one boss with every player shot landing.

    The floor, not the expectation: the cadence spends `hits_to_defeat`
    periods and the last shot still has to fly the stand-off. A real player
    misses, which is what the slack against the salvo budget is for.
    """

    return (
        boss.hits_to_defeat * boss.player_fire_period_seconds
        + boss.firing_distance_columns / boss.player_shot_speed_columns_per_second
    )


def boss_salvo_budget_seconds(boss: BossProfile) -> float:
    """Seconds the boss stays before its salvo budget is spent."""

    return boss.salvo_budget * boss.salvo_period_seconds


class RunnerVitals(PersistedContractModel):
    """The gauge a survivable hit spends, and how spending it is shown."""

    profile: VitalsProfileName
    hurt_representation: HurtRepresentation


class RunnerConsequences(PersistedContractModel):
    """What each way of coming to grief costs.

    Every source is answered explicitly rather than defaulted, because a
    silent default is exactly how a pit quietly stops being final.
    """

    hazard: ConsequenceName
    pit: ConsequenceName
    crush: ConsequenceName
    #: Absent means no encounter can fire at the avatar; present, it obligates
    #: one. A run with no boss has no shot to answer for, and an encounter
    #: whose hits cost nothing is a fight the player cannot lose.
    shot: ConsequenceName | None = None

    def by_source(self) -> dict[str, str]:
        sources: dict[str, str] = {"hazard": self.hazard, "pit": self.pit, "crush": self.crush}
        if self.shot is not None:
            sources["shot"] = self.shot
        return sources

    def drains(self) -> bool:
        return any(name in DRAINING_CONSEQUENCES for name in self.by_source().values())


class RunnerEncounter(PersistedContractModel):
    """One boss fight the run is interrupted by, and how often it arrives.

    An interlude rather than a place: the track authors one flat arena chunk,
    the run streams it when the interval comes due, and the encounter plays
    over it. That is what keeps the seam rule intact - every chunk still
    follows every chunk, and no chunk carries state about what came before.

    The locomotion is named here rather than on `RunnerRun` because it is an
    override with a beginning and an end, not the way this package runs.
    """

    boss_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    profile: BossProfileName
    #: The locomotion the avatar wears for the fight's duration.
    locomotion: LocomotionProfileName
    #: Columns of ordinary running between encounters.
    interval_columns: int = Field(ge=MIN_ENCOUNTER_INTERVAL_COLUMNS, le=100_000)
    #: The `role = "arena"` chunk this encounter is fought over.
    arena_segment_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    boss_projectile_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    player_projectile_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)

    @model_validator(mode="after")
    def validate_projectiles(self) -> RunnerEncounter:
        """The two roles are drawn separately.

        One silhouette flying both ways is a fight in which a player cannot
        tell their own fire from the boss's, which is a readability failure
        the contract can refuse offline instead of a review catching it.
        """
        if self.boss_projectile_id == self.player_projectile_id:
            raise ValueError(
                "runner encounter fires and is fired at with one projectile "
                f"({self.boss_projectile_id}); draw the two roles separately"
            )
        return self

    def boss_profile(self) -> BossProfile:
        return BOSS_PROFILES[self.profile]

    def thrust_profile(self) -> ThrustProfile:
        return THRUST_PROFILES[self.locomotion]


class RunnerRun(PersistedContractModel):
    speed_profile: SpeedProfileName
    jump_profile: JumpProfileName
    collision_box: CollisionBoxName
    #: Absent means the avatar cannot duck and the track may not hang overhead
    #: hazards; present, it obligates a drawn slide motion.
    duck_profile: DuckProfileName | None = None
    consequences: RunnerConsequences
    #: Present exactly when some consequence drains it. A gauge nothing can
    #: spend is dead contract, and a drain with no gauge is unsayable.
    vitals: RunnerVitals | None = None


class RunnerRamp(PersistedContractModel):
    profile: RampProfile


class RunnerGameplayContract(PersistedContractModel):
    schema_version: Literal[4]
    kind: Literal["runner-gameplay-v4"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    #: The single track this gameplay is played on. Exactly one in v2: an
    #: endless run has no map graph, and a second track is a second member.
    track_id: str = Field(pattern=KEBAB_ID_PATTERN, max_length=96)
    run: RunnerRun
    ramp: RunnerRamp
    #: Absent means the run is uninterrupted. Present, it obligates a boss, an
    #: arena chunk, two projectiles, a drawn fly motion and a shot
    #: consequence - every one of them refused offline when it is missing.
    encounter: RunnerEncounter | None = None

    @field_validator("track_id")
    @classmethod
    def validate_track_id(cls, value: str) -> str:
        return value

    @model_validator(mode="after")
    def validate_vitals_obligation(self) -> RunnerGameplayContract:
        """A gauge and a drain each require the other.

        The same shape as the duck triangle: a declared profile that nothing
        can reach, and a reference to something undeclared, are both refused
        rather than quietly tolerated, so an unplayable combination is
        unsayable instead of merely unlucky.
        """
        drains = self.run.consequences.drains()
        if drains and self.run.vitals is None:
            raise ValueError(
                "runner gameplay declares a draining consequence with no [run.vitals] gauge"
            )
        if not drains and self.run.vitals is not None:
            raise ValueError(
                "runner gameplay declares [run.vitals] no consequence can drain; "
                "use a draining consequence or drop the gauge"
            )
        return self

    @model_validator(mode="after")
    def validate_shot_obligation(self) -> RunnerGameplayContract:
        """A shot consequence and an encounter each require the other.

        The third triangle, after duck/slide and drain/gauge, and refused for
        the same reason: an answer to a hit nothing can deliver is dead
        contract, and a boss whose fire costs nothing is a fight with no
        stake. Neither is worth discovering at play time.
        """
        shot = self.run.consequences.shot
        if self.encounter is not None and shot is None:
            raise ValueError(
                "runner gameplay declares an encounter with no [run.consequences] shot answer"
            )
        if self.encounter is None and shot is not None:
            raise ValueError(
                "runner gameplay answers a shot no encounter can fire; "
                "declare an [encounter] or drop the answer"
            )
        return self

    def jump_profile(self) -> JumpProfile:
        return JUMP_PROFILES[self.run.jump_profile]

    def speed_profile(self) -> SpeedProfile:
        return SPEED_PROFILES[self.run.speed_profile]

    def collision_profile(self) -> CollisionProfile:
        return COLLISION_BOXES[self.run.collision_box]

    def vitals_profile(self) -> VitalsProfile | None:
        if self.run.vitals is None:
            return None
        return VITALS_PROFILES[self.run.vitals.profile]

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
    "COLLISION_BOXES",
    "DRAINING_CONSEQUENCES",
    "BOSS_PROFILES",
    "DUCK_PROFILES",
    "JUMP_PROFILES",
    "MIN_ENCOUNTER_INTERVAL_COLUMNS",
    "PLACEMENT_PROFILES",
    "VITALS_PROFILES",
    "RUNNER_GAMEPLAY_SCHEMA_VERSION",
    "RUNNER_PLACEMENT_PROFILE",
    "SPEED_PROFILES",
    "THRUST_PROFILES",
    "BossProfile",
    "BossProfileName",
    "CollisionBoxName",
    "CollisionProfile",
    "ConsequenceName",
    "DamageSource",
    "DuckProfile",
    "DuckProfileName",
    "JumpArc",
    "JumpProfile",
    "JumpProfileName",
    "LocomotionProfileName",
    "PlacementProfile",
    "RampProfile",
    "RunnerGameplayContract",
    "HurtRepresentation",
    "RunnerConsequences",
    "RunnerEncounter",
    "RunnerRamp",
    "RunnerRun",
    "RunnerVitals",
    "SpeedProfile",
    "SpeedProfileName",
    "ThrustProfile",
    "VitalsProfile",
    "VitalsProfileName",
    "apron_columns",
    "arc_height_rows",
    "canonical_runner_gameplay_json",
    "boss_dodge_window_seconds",
    "boss_kill_seconds",
    "boss_lane_rows",
    "boss_salvo_budget_seconds",
    "clearable_span_columns",
    "drop_scatter_columns",
    "hazard_press_window_seconds",
    "jump_arc",
    "landing_time_seconds",
    "load_runner_gameplay_bytes",
    "runner_gameplay_sha256",
    "thrust_traverse_seconds",
]
