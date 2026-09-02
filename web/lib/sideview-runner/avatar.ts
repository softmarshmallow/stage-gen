// Auto-run physics: constant ramped forward speed, the jump family, the
// slide, and hard falls.
//
// The arc is not authored — it is derived from the manifest's published
// admission arithmetic. Track admission proved every chunk against the
// declared jump name's `max_clear_gap_columns` and `max_rise_tiles` using
// exactly these closed forms, so the arc the player flies IS the arc the
// proof flew, not a convention. The hop count is deliberately NOT part of
// that arithmetic: `double_arc_v1`'s second hop is recovery, never reach —
// no refusal depends on it, so it lives here, in the consumer's feel table.
//
// Coordinates follow the occupancy grid: y grows downward in row units, the
// avatar's feet sit at y, and gravity is positive.

import { surfaceRowAt } from "./segments";
import type { GameSystem } from "@/lib/game-systems/systems";
import { applyPendingRecovery } from "./vitals";
import type { RunnerWorld } from "./world";

/** The consumer's own defaults, equal to the SDK's published values; runtime
 * code passes the manifest's arithmetic instead of relying on these. */
export const JUMP_PEAK_MARGIN_TILES = 0.75;
export const AIRTIME_HEADROOM = 1.15;
export const DEFAULT_BASE_SPEED_COLUMNS_PER_SECOND = 6;

/** Air jumps per jump name: pure feel, no refusal reads it. */
export const JUMP_FEEL_PROFILES: Readonly<
  Record<"single_arc_v1" | "double_arc_v1", { readonly airJumps: number }>
> = Object.freeze({
  single_arc_v1: Object.freeze({ airJumps: 0 }),
  double_arc_v1: Object.freeze({ airJumps: 1 }),
});

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

export interface JumpArcArithmetic {
  readonly baseSpeedColumnsPerSecond?: number;
  readonly jumpPeakMarginTiles?: number;
  readonly airtimeHeadroom?: number;
}

/**
 * Derive the jump arc from the admission arithmetic.
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
  arithmetic: JumpArcArithmetic = {},
): JumpArc {
  const minSpeed =
    arithmetic.baseSpeedColumnsPerSecond ?? DEFAULT_BASE_SPEED_COLUMNS_PER_SECOND;
  if (minSpeed <= 0) {
    throw new Error("jump arc requires a positive minimum speed");
  }
  const peakRows = maxRiseTiles + (arithmetic.jumpPeakMarginTiles ?? JUMP_PEAK_MARGIN_TILES);
  const airtimeSeconds =
    ((maxClearGapColumns + 1) / minSpeed) * (arithmetic.airtimeHeadroom ?? AIRTIME_HEADROOM);
  return Object.freeze({
    initialSpeedRowsPerSecond: (4 * peakRows) / airtimeSeconds,
    gravityRowsPerSecondSquared: (8 * peakRows) / (airtimeSeconds * airtimeSeconds),
    peakRows,
    airtimeSeconds,
  });
}

function launch(world: RunnerWorld, arc: JumpArc): void {
  const avatar = world.avatar;
  avatar.vy = -arc.initialSpeedRowsPerSecond;
  avatar.grounded = false;
  avatar.sliding = false;
  avatar.motion = "jump";
  avatar.jumpImpulses += 1;
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
  // A forgiven fall, decided last frame: applied before anything else moves,
  // so the recovered avatar starts this step standing rather than still in
  // the hole it was pulled out of.
  applyPendingRecovery(world);

  const arc = jumpArcFor(
    world.config.maxRiseTiles,
    world.config.maxClearGapColumns,
    world.config.arithmetic,
  );
  avatar.distanceColumns += world.difficulty.speedColumnsPerSecond * dt;
  const support = surfaceRowAt(world.segments, Math.floor(avatar.distanceColumns));

  if (world.intent.jump) {
    if (avatar.grounded) {
      launch(world, arc);
    } else if (avatar.airJumpsUsed < JUMP_FEEL_PROFILES[world.config.jumpProfile].airJumps) {
      // The air jump: a full relaunch from wherever the mistake happened.
      // Recovery, never reach — admission's arithmetic is single-hop, so no
      // admitted chunk ever demands this press.
      avatar.airJumpsUsed += 1;
      launch(world, arc);
    }
  }

  if (avatar.grounded) {
    // The slide is held state: low while duck is held, back up when released.
    avatar.sliding = world.config.duckProfile !== null && world.intent.duck;
    avatar.motion = avatar.sliding ? "slide" : "run";
    if (support === null || support > avatar.y) {
      // Ran off a ledge or over a pit: start falling from the current height.
      avatar.grounded = false;
      avatar.sliding = false;
      avatar.motion = "jump";
    } else if (support < avatar.y) {
      // The ground face rose into the avatar: an unjumped step is a crush.
      // What that costs is not decided here — the package's consequence table
      // answers it, and the vitals system reads that. This says what happened.
      world.events.emit({ type: "crush" });
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
        avatar.airJumpsUsed = 0;
        avatar.sliding = world.config.duckProfile !== null && world.intent.duck;
        avatar.motion = avatar.sliding ? "slide" : "run";
      } else {
        // Buried without crossing from above — ascending into a step's face,
        // or carried into a pit wall while already below its rim. Either way
        // it is a crush.
        world.events.emit({ type: "crush" });
        return;
      }
    } else if (avatar.y > world.config.rows) {
      world.events.emit({ type: "pit" });
    }
  }
}

export function createAvatarSystem(): GameSystem<RunnerWorld> {
  return {
    id: "runner/avatar",
    contractVersion: "avatar-system-v3",
    reads: ["intent", "difficulty"],
    writes: ["avatar"],
    emits: ["pit", "crush"],
    update(world, step) {
      stepAvatar(world, step.dt);
    },
  };
}
