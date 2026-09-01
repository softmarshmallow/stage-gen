// Auto-run physics: constant ramped forward speed, one jump arc, hard falls.
//
// The arc is not authored — it is derived from the manifest's admission
// arithmetic. Track admission proved every chunk against `single_arc_v1`'s
// `max_clear_gap_columns` and `max_rise_tiles` before art was paid for, so
// the runtime's obligation is exact: produce an arc that clears that gap at
// the slowest admitted speed and lands that rise. The closed forms below do
// so by construction, and the tests hold them to it.
//
// Coordinates follow the occupancy grid: y grows downward in row units, the
// avatar's feet sit at y, and gravity is positive.

import { BASE_SPEED_COLUMNS_PER_SECOND } from "./difficulty";
import { surfaceRowAt } from "./segments";
import type { GameSystem } from "./systems";
import type { RunnerWorld } from "./world";

/** How far above `max_rise_tiles` the arc peaks, so a maximal step still lands. */
export const JUMP_PEAK_MARGIN_TILES = 0.75;

/** Airtime headroom over the bare gap crossing, so clearing is not frame-exact. */
export const AIRTIME_HEADROOM = 1.15;

export interface JumpArc {
  /** Upward launch speed, rows per second. */
  readonly initialSpeedRowsPerSecond: number;
  /** Downward acceleration, rows per second squared. */
  readonly gravityRowsPerSecondSquared: number;
  /** Highest point of the arc above the takeoff row, in rows. */
  readonly peakRows: number;
  /** Flat-ground airtime in seconds. */
  readonly airtimeSeconds: number;
}

/**
 * Derive the single jump arc from the admission arithmetic.
 *
 * A pit of `maxClearGapColumns` needs the takeoff column plus the gap crossed
 * before landing, so flat-ground airtime is `(gap + 1) / speed` at the
 * slowest admitted speed — every ramped speed then crosses farther. Peak
 * height is the maximal rise plus a margin. From airtime T and peak P, the
 * kinematics close: v0 = 4P/T and g = 8P/T².
 */
export function jumpArcFor(
  maxRiseTiles: number,
  maxClearGapColumns: number,
  minSpeedColumnsPerSecond: number = BASE_SPEED_COLUMNS_PER_SECOND,
): JumpArc {
  if (minSpeedColumnsPerSecond <= 0) {
    throw new Error("jump arc requires a positive minimum speed");
  }
  const peakRows = maxRiseTiles + JUMP_PEAK_MARGIN_TILES;
  const airtimeSeconds =
    ((maxClearGapColumns + 1) / minSpeedColumnsPerSecond) * AIRTIME_HEADROOM;
  return Object.freeze({
    initialSpeedRowsPerSecond: (4 * peakRows) / airtimeSeconds,
    gravityRowsPerSecondSquared: (8 * peakRows) / (airtimeSeconds * airtimeSeconds),
    peakRows,
    airtimeSeconds,
  });
}

/**
 * Advance the avatar one fixed step.
 *
 * Reads this frame's intent and difficulty, and — deliberately as feedback —
 * last frame's segment window and run phase: the window streams far ahead of
 * anything one step can reach, and a hazard death decided by the run-loop is
 * worn as the death pose one frame later, which at 60Hz is invisible.
 */
export function stepAvatar(world: RunnerWorld, dt: number): void {
  const avatar = world.avatar;
  if (world.run.phase === "dead") {
    avatar.motion = "death";
    return;
  }

  const arc = jumpArcFor(world.config.maxRiseTiles, world.config.maxClearGapColumns);
  avatar.distanceColumns += world.difficulty.speedColumnsPerSecond * dt;
  const support = surfaceRowAt(world.segments, Math.floor(avatar.distanceColumns));

  if (avatar.grounded && world.intent.jump) {
    avatar.vy = -arc.initialSpeedRowsPerSecond;
    avatar.grounded = false;
    avatar.motion = "jump";
  }

  if (avatar.grounded) {
    if (support === null || support > avatar.y) {
      // Ran off a ledge or over a pit: start falling from the current height.
      avatar.grounded = false;
      avatar.motion = "jump";
    } else if (support < avatar.y) {
      // The ground face rose into the avatar: an unjumped step is a collision,
      // and the manifest's collision policy makes a collision end the run.
      avatar.deathCause = "step";
      avatar.motion = "death";
      return;
    }
  }

  if (!avatar.grounded) {
    const yBefore = avatar.y;
    avatar.vy += arc.gravityRowsPerSecondSquared * dt;
    avatar.y += avatar.vy * dt;
    if (support !== null && avatar.y >= support) {
      if (avatar.vy >= 0 && yBefore <= support) {
        // Fell across the surface from above: land on it.
        avatar.y = support;
        avatar.vy = 0;
        avatar.grounded = true;
        avatar.motion = "run";
      } else {
        // Buried without crossing from above — ascending into a step's face,
        // or carried into a pit wall while already below its rim. Either way
        // it is a collision, and a collision ends the run.
        avatar.deathCause = "step";
        avatar.motion = "death";
        return;
      }
    } else if (avatar.y > world.config.rows) {
      avatar.deathCause = "pit";
      avatar.motion = "death";
    }
  }
}

export function createAvatarSystem(): GameSystem<RunnerWorld> {
  return {
    id: "runner/avatar",
    contractVersion: "avatar-system-v1",
    reads: ["intent", "difficulty"],
    writes: ["avatar"],
    update(world, step) {
      stepAvatar(world, step.dt);
    },
  };
}
