// The ramp: distance into a difficulty band and speed, per named profile.
//
// The manifest names the feel ("gentle_ramp_v1"); this consumer owns the
// numbers, the same division of labor the generation side uses for its
// experience curve. Both curves are pure functions of distance so a replayed
// seed meets exactly the chunks and speeds it met the first time.
//
// The pool is a sliding BAND, not a growing set: the ceiling rises with
// distance and the floor trails it by `minCeilingLag`, so an opening chunk
// eventually leaves the pool instead of staying exactly as likely as the
// hardest one forever. The rest cadence below re-admits the catalog's easiest
// rank on a fixed beat, so a breather is guaranteed rather than probable.

import type { GameSystem } from "./systems";
import type { RunnerWorld } from "./world";

export type RampProfileName = "gentle_ramp_v1";

export interface RampProfile {
  /** Columns of running that raise the difficulty ceiling by one. */
  readonly columnsPerCeilingStep: number;
  /** The ceiling never leaves the authored 1..10 vocabulary. */
  readonly maxCeiling: number;
  /** How far the pool floor trails the ceiling: the band's height. */
  readonly minCeilingLag: number;
  /** Every this-many appended chunks, one catalog-easiest breather is forced. */
  readonly restEveryAppends: number;
  /** Fraction added to the base speed once the ramp is fully spent. */
  readonly maxSpeedBonus: number;
  /** Columns over which the speed bonus is linearly earned. */
  readonly speedRampColumns: number;
}

const RAMP_PROFILES: Readonly<Record<RampProfileName, RampProfile>> = Object.freeze({
  // Gentle: one ceiling step per ~10 seconds of base-speed running, a
  // three-rank band, a guaranteed breather every sixth chunk, and the whole
  // speed bonus takes about five minutes to earn.
  gentle_ramp_v1: Object.freeze({
    columnsPerCeilingStep: 60,
    maxCeiling: 10,
    minCeilingLag: 3,
    restEveryAppends: 6,
    maxSpeedBonus: 0.5,
    speedRampColumns: 1800,
  }),
});

export function rampProfile(name: RampProfileName): RampProfile {
  return RAMP_PROFILES[name];
}

/** The documented default at multiplier 1; the runtime reads the manifest's
 * published base speed instead of this constant. */
export const BASE_SPEED_COLUMNS_PER_SECOND = 6;

export interface DifficultyState {
  /** Chunks with difficulty above this are not yet in the selection pool. */
  ceiling: number;
  /** Chunks with difficulty below this have aged out of the selection pool. */
  floor: number;
  /** Multiplier over the base run speed; starts at 1. */
  speedMultiplier: number;
  /** The run's current forward speed — the one number the avatar advances by. */
  speedColumnsPerSecond: number;
}

export function difficultyCeiling(profile: RampProfile, distanceColumns: number): number {
  const distance = Math.max(0, distanceColumns);
  return Math.min(profile.maxCeiling, 1 + Math.floor(distance / profile.columnsPerCeilingStep));
}

export function difficultyFloor(profile: RampProfile, ceiling: number): number {
  return Math.max(1, ceiling - profile.minCeilingLag);
}

export function speedMultiplier(profile: RampProfile, distanceColumns: number): number {
  const distance = Math.max(0, distanceColumns);
  return 1 + profile.maxSpeedBonus * Math.min(1, distance / profile.speedRampColumns);
}

/**
 * The ramp system. It keys off the distance the avatar wrote *last* frame — a
 * feedback read the declarations cannot carry — and the frame order starts
 * intent → difficulty, so that edge is pinned explicitly.
 */
export function createDifficultySystem(): GameSystem<RunnerWorld> {
  return {
    id: "runner/difficulty",
    contractVersion: "difficulty-system-v3",
    reads: [],
    writes: ["difficulty"],
    after: ["runner/intent"],
    update(world) {
      const profile = rampProfile(world.config.rampProfile);
      const difficulty = world.difficulty;
      difficulty.ceiling = Math.min(
        world.config.maxAuthoredDifficulty,
        difficultyCeiling(profile, world.avatar.distanceColumns),
      );
      difficulty.floor = difficultyFloor(profile, difficulty.ceiling);
      // The ramp is feel, the cap is arithmetic: spacing proofs ran at the
      // published maximum, so the earned multiplier never exceeds it.
      difficulty.speedMultiplier = Math.min(
        world.config.arithmetic.maxSpeedMultiplier,
        speedMultiplier(profile, world.avatar.distanceColumns),
      );
      difficulty.speedColumnsPerSecond =
        world.config.arithmetic.baseSpeedColumnsPerSecond * difficulty.speedMultiplier;
    },
  };
}
