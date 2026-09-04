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
import type { GameSystem } from "@/lib/kernel/systems";
import { RUNNER_BLOCKS } from "./contract";
import type { BlockTable } from "@/lib/manifest/blocks";
import {
  jumpArcFromAdmission,
  resolveJumpRequest,
  resolveTerrainStep,
  resolveVerticalLanding,
  parseTraversalBlock,
  type TraversalBlockView,
} from "@/lib/families/sideview/traversal";

import { type ThrustArithmetic, thrustVelocity } from "./encounter-arithmetic";
import { applyPendingRecovery } from "./vitals";
import type { RunnerWorld } from "./world";

/**
 * The block this genre authors its traversal in.
 *
 * The composition table calls it `[navigation]` and this genre has no such
 * block: the same subject is authored as `gameplay.jump_profile`,
 * `gameplay.duck_profile`, `max_clear_gap_columns` and `max_rise_tiles` — the
 * admission arithmetic the arc is *derived* from rather than an authored arc.
 * Move it and the refusal comes from the traversal core, by name, rather than
 * from a genre parser gating a dozen blocks on a dozen consumers' behalf.
 */
export const RUNNER_TRAVERSAL_BLOCK = Object.freeze({
  block: "gameplay",
  version: RUNNER_BLOCKS.gameplay,
});

/** Gate the runner's traversal block. Refuses by naming `gameplay`. */
export function parseRunnerTraversalBlock(blocks: BlockTable): TraversalBlockView {
  return parseTraversalBlock(blocks, RUNNER_TRAVERSAL_BLOCK);
}

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
 * Derive the jump arc from the admission arithmetic, in rows.
 *
 * The closure is the family's — a pit of `maxClearGapColumns` needs the takeoff
 * column plus the gap crossed before landing, peak height is the maximal rise
 * plus a margin, and from airtime T and peak P the kinematics close as
 * `v0 = 4P/T` and `g = 8P/T²`. What this genre supplies is the *unit*: its
 * admission counts grid cells and its avatar integrates in rows, so the arc
 * comes back in rows and the field names say so. A genre that admitted the same
 * track in pixels would get a pixel arc out of the identical arithmetic, which
 * is the whole of what "generic over the length unit" buys here.
 */
export function jumpArcFor(
  maxRiseTiles: number,
  maxClearGapColumns: number,
  arithmetic: JumpArcArithmetic = {},
): JumpArc {
  const arc = jumpArcFromAdmission({
    maxRise: maxRiseTiles,
    maxClearGap: maxClearGapColumns,
    minSpeed: arithmetic.baseSpeedColumnsPerSecond ?? DEFAULT_BASE_SPEED_COLUMNS_PER_SECOND,
    peakMargin: arithmetic.jumpPeakMarginTiles ?? JUMP_PEAK_MARGIN_TILES,
    airtimeHeadroom: arithmetic.airtimeHeadroom ?? AIRTIME_HEADROOM,
  });
  return Object.freeze({
    initialSpeedRowsPerSecond: arc.initialSpeedPerSecond,
    gravityRowsPerSecondSquared: arc.gravityPerSecondSquared,
    peakRows: arc.peakUnits,
    airtimeSeconds: arc.airtimeSeconds,
  });
}

function launch(world: RunnerWorld, vy: number): void {
  const avatar = world.avatar;
  avatar.vy = vy;
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
  // The intro holds the avatar where the reset put it: no physics, no intent.
  if (world.run.phase === "intro") return;
  // A forgiven fall, decided last frame: applied before anything else moves,
  // so the recovered avatar starts this step standing rather than still in
  // the hole it was pulled out of.
  applyPendingRecovery(world);

  const arc = jumpArcFor(
    world.config.maxRiseTiles,
    world.config.maxClearGapColumns,
    world.config.arithmetic,
  );
  // Which physics to integrate is a feedback read of `locomotion`: the
  // encounter director writes it, and it is not declared as a read here
  // because that edge would seal a cycle (avatar -> encounter -> avatar). The
  // cost is that the switch lands one 60Hz frame late, which is a sixtieth of
  // a second at the moment a two-second cut-in has just finished playing.
  if (world.locomotion === "thrust" && world.config.encounter !== null) {
    stepThrust(world, dt, world.config.encounter.thrust);
    return;
  }

  avatar.distanceColumns += world.difficulty.speedColumnsPerSecond * dt;
  const support = surfaceRowAt(world.segments, Math.floor(avatar.distanceColumns));

  if (world.intent.jump) {
    // The family answers which jump the press buys; this genre supplies the
    // budget and the velocities. Both velocities are the same arc, because the
    // air jump here is a full relaunch from wherever the mistake happened —
    // recovery, never reach, since admission's arithmetic is single-hop and no
    // admitted chunk ever demands the press. There is no coyote window: the
    // track has no ledges to forgive, so the grace branch is simply never open.
    const request = resolveJumpRequest({
      support: avatar.grounded ? "terrain" : "air",
      airJumpsUsed: avatar.airJumpsUsed,
      nowMs: 0,
      coyoteExpiresAtMs: null,
      crouching: false,
      maximumAirJumps: JUMP_FEEL_PROFILES[world.config.jumpProfile].airJumps,
      jumpVelocity: arc.initialSpeedRowsPerSecond,
      airJumpVelocity: arc.initialSpeedRowsPerSecond,
    });
    if (request.kind !== "none") {
      avatar.airJumpsUsed = request.airJumpsUsed;
      launch(world, request.vy);
    }
  }

  if (avatar.grounded) {
    // The slide is held state: low while duck is held, back up when released.
    avatar.sliding = world.config.duckProfile !== null && world.intent.duck;
    avatar.motion = avatar.sliding ? "slide" : "run";
    // The standing foot against the column under it, at zero tolerance: this
    // track steps in whole rows and there is no kerb small enough to absorb.
    const contact =
      support === null
        ? null
        : resolveTerrainStep({ footY: avatar.y, surfaceY: support, tolerance: 0 });
    if (contact === null || contact.support === "air") {
      // Ran off a ledge or over a pit: start falling from the current height.
      avatar.grounded = false;
      avatar.sliding = false;
      avatar.motion = "jump";
    } else if (contact.footY < avatar.y) {
      // The ground face rose into the avatar. The family lifts a buried foot as
      // a recovery; this genre refuses the lift, because an unjumped step is a
      // crush. What that costs is not decided here — the package's consequence
      // table answers it, and the vitals system reads that. This says what
      // happened.
      world.events.emit({ type: "crush" });
      return;
    }
  }

  if (!avatar.grounded) {
    const yBefore = avatar.y;
    avatar.vy += arc.gravityRowsPerSecondSquared * dt;
    avatar.y += avatar.vy * dt;
    // `crossing`, which is the runner's half of the family's one real
    // disagreement: this track is admitted so that no arc ever has to arrive
    // from inside a step's face, so a foot below the surface that did not cross
    // it from above is buried rather than landed. The platformer clamps
    // instead, and neither answer can be derived from the other.
    const landing =
      support === null
        ? null
        : resolveVerticalLanding({
            x: avatar.distanceColumns,
            previousFootY: yBefore,
            nextFootY: avatar.y,
            vy: avatar.vy,
            terrainY: support,
            terrainEntry: "crossing",
          });
    if (landing?.support === "terrain") {
      // Fell across the surface from above: land on it.
      avatar.y = landing.footY;
      avatar.vy = landing.vy;
      avatar.grounded = true;
      avatar.airJumpsUsed = 0;
      avatar.sliding = world.config.duckProfile !== null && world.intent.duck;
      avatar.motion = avatar.sliding ? "slide" : "run";
    } else if (landing?.support === "buried") {
      // Ascending into a step's face, or carried into a pit wall while already
      // below its rim. Either way it is a crush.
      world.events.emit({ type: "crush" });
      return;
    } else if (avatar.y > world.config.rows) {
      world.events.emit({ type: "pit" });
    }
  }
}

/**
 * Advance the avatar one fixed step under thrust.
 *
 * The same forward motion, a different vertical verb: held climbs, released
 * falls, and the floor is the arena's, which is flat by contract. There is no
 * jump edge, no slide, and no air-jump budget - a locomotion is the whole map
 * from intent to vertical motion, not a modifier on the running one, so
 * nothing here reads a jump profile.
 *
 * The head is clamped at row 0 rather than allowed off the top, because the
 * salvo's lane is measured inside the band and an avatar above the band could
 * dodge everything by leaving the fight.
 */
function stepThrust(world: RunnerWorld, dt: number, thrust: ThrustArithmetic): void {
  const avatar = world.avatar;
  avatar.distanceColumns += world.difficulty.speedColumnsPerSecond * dt;
  const support = surfaceRowAt(world.segments, Math.floor(avatar.distanceColumns));
  const held = world.intent.thrust;

  avatar.sliding = false;
  avatar.airJumpsUsed = 0;

  if (avatar.grounded && !held) {
    // Idling on the arena floor: still running, just not climbing.
    avatar.vy = 0;
    avatar.motion = "run";
    return;
  }
  if (avatar.grounded) avatar.grounded = false;

  const yBefore = avatar.y;
  avatar.vy = thrustVelocity(avatar.vy, held, dt, thrust);
  avatar.y += avatar.vy * dt;

  const ceiling = world.config.playerHeightTiles;
  if (avatar.y < ceiling) {
    avatar.y = ceiling;
    avatar.vy = 0;
  }

  // `clamp` under thrust, and the arena is why: it is flat by contract, so a
  // descending body that is at or below the floor arrived there by falling onto
  // it and there is nothing to bury it in. The same family function, the other
  // entry rule, in the same genre — which is the clearest statement available
  // that the rule is a parameter and not a genre.
  const landing =
    support === null
      ? null
      : resolveVerticalLanding({
          x: avatar.distanceColumns,
          previousFootY: yBefore,
          nextFootY: avatar.y,
          vy: avatar.vy,
          terrainY: support,
          terrainEntry: "clamp",
        });
  if (landing?.support === "terrain") {
    avatar.y = landing.footY;
    avatar.vy = landing.vy;
    avatar.grounded = true;
    avatar.motion = "run";
    return;
  }
  if (support === null && avatar.y > world.config.rows) {
    // Unreachable on an admitted arena, which is flat in every column. Kept
    // so a mis-authored floor fails the way a pit does rather than silently.
    world.events.emit({ type: "pit" });
    return;
  }
  avatar.motion = "fly";
}

export function createAvatarSystem(): GameSystem<RunnerWorld> {
  return {
    id: "runner/avatar",
    contractVersion: "avatar-system-v5",
    reads: ["clock", "intent", "difficulty"],
    writes: [],
    // One author for the avatar, death pose included: the run-loop used to
    // write the pose too, a frame earlier, without declaring it.
    owns: ["avatar"],
    emits: ["pit", "crush", "jumped", "landed", "slid"],
    update(world) {
      // The simulation's delta, not the frame's: under a moment the avatar
      // integrates zero, which is the half of "a jump under the cut-in does
      // not fire" that this system owns. The other half is the intent system
      // reporting neutral edges while the clock is held.
      //
      // The three verbs are read off this step's own before and after, not off
      // a copy of last frame's avatar: this system is the slice's sole author,
      // so nothing can have moved it since, and the comparison is local rather
      // than a shadow of somebody else's state. Two consumers used to keep that
      // shadow — the cues and the ground dust — and a restart had to
      // resynchronise both by hand.
      const before = {
        jumpImpulses: world.avatar.jumpImpulses,
        grounded: world.avatar.grounded,
        sliding: world.avatar.sliding,
      };
      stepAvatar(world, world.clock.simulationDt);
      const avatar = world.avatar;
      if (avatar.jumpImpulses > before.jumpImpulses) {
        world.events.emit({ type: "jumped", airJump: avatar.airJumpsUsed > 0 });
      }
      if (avatar.grounded && !before.grounded) world.events.emit({ type: "landed" });
      if (avatar.sliding && !before.sliding) world.events.emit({ type: "slid" });
    },
  };
}
