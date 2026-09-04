// The `loot` family, second half: a drop on the ground.
//
// The platformer stored a drop's position *on its sprite* — `sprite.x`,
// `sprite.y` and a `groundY` in Phaser's `setData` bag — so "where is the
// loot" was a question only a renderer could answer, and the arithmetic that
// moved it lived in the same class that drew it. The body below is that state
// as a value, and `stepDrop` is the arc: a pop away from the blow, one bounce,
// and a settle into a bob.
//
// The surface is a port. "How high is the ground under this x" is a question
// about the world, answered by the space family in the platformer and by the
// track's own occupancy in anything else — the same shape `vitals` uses for
// its recovery.

/** A drop in flight or at rest. Mutable, because it is stepped in place every frame. */
export interface DropBody {
  x: number;
  y: number;
  /** Horizontal pop velocity, halved by the landing bounce and gone once settled. */
  vx: number;
  /** Vertical velocity while falling. */
  vy: number;
  settled: boolean;
  /** Bounces taken so far; the arc allows exactly one. */
  bounces: number;
  /** The surface the drop settled on, and the datum its bob is measured from. */
  groundY: number;
  /**
   * The drop's own phase in the settled bob.
   *
   * Per drop rather than global, so two items resting side by side do not rise
   * and fall as one object.
   */
  bobPhase: number;
}

/** Acceleration on a drop in flight, in units per second squared. */
export const DROP_GRAVITY = 1500;

// A drop *pops*: it leaves the corpse with an upward and sideways velocity,
// bounces once, and only then settles into its bob. Before this it fell
// straight down from a tile above the kill, which read as an item appearing
// rather than as something being knocked loose. The velocities are seeded from
// the drop's own sequence number, so the same kill in the same run pops the
// same way twice, which is what a fixed-frame capture needs and what a tween
// never provides.
export const DROP_POP_VX_MIN = 60;
export const DROP_POP_VX_SPAN = 80;
export const DROP_POP_VY_MIN = 260;
export const DROP_POP_VY_SPAN = 120;
export const DROP_BOUNCE_RESTITUTION = 0.35;
/** A landing slower than this settles outright; bouncing a crawl reads as jitter. */
export const DROP_BOUNCE_MIN_VY = 120;
export const DROP_BOUNCE_VX_RETAINED = 0.5;
/** How far a settled drop rises and falls. */
export const DROP_BOB_AMPLITUDE = 2;
/** The bob's period divisor: one cycle every ~1.26 seconds. */
export const DROP_BOB_MS = 200;

/** Which way a drop was knocked: away from the striker, or alternating for a caller with no blow. */
export type DropDirection = 1 | -1 | 0;

function dropUnitNoise(sequence: number, channel: number): number {
  let hash = (Math.imul(sequence ^ channel, 0x9e3779b1) ^ (sequence >>> 15)) >>> 0;
  hash = Math.imul(hash ^ (hash >>> 13), 0x85ebca6b) >>> 0;
  hash = Math.imul(hash ^ (hash >>> 16), 0xc2b2ae35) >>> 0;
  return hash / 4294967296;
}

/**
 * The launch velocity for one drop.
 *
 * `dirSign` is the direction the blow travelled, so loot flies away from the
 * striker as the body does; zero alternates by sequence, for callers that have
 * no blow to report.
 */
export function dropPopVelocity(
  sequence: number,
  dirSign: DropDirection,
): Readonly<{ vx: number; vy: number }> {
  if (!Number.isSafeInteger(sequence) || sequence < 0) {
    throw new Error("drop pop velocity requires a nonnegative sequence");
  }
  const direction = dirSign === 0 ? (sequence % 2 === 0 ? 1 : -1) : dirSign;
  return Object.freeze({
    vx: direction * (DROP_POP_VX_MIN + dropUnitNoise(sequence, 0x11) * DROP_POP_VX_SPAN),
    vy: -(DROP_POP_VY_MIN + dropUnitNoise(sequence, 0x22) * DROP_POP_VY_SPAN),
  });
}

/** A fresh body, popped away from the blow that knocked it loose. */
export function launchDrop(
  x: number,
  y: number,
  sequence: number,
  dirSign: DropDirection,
  bobPhase: number,
): DropBody {
  const launch = dropPopVelocity(sequence, dirSign);
  return { x, y, vx: launch.vx, vy: launch.vy, settled: false, bounces: 0, groundY: y, bobPhase };
}

export interface DropSurface {
  /** The ground under this x, in the caller's own units. */
  surfaceAt(x: number): number;
  /** Keep a pop inside the world; identity for a place with no edges. */
  clampX?(x: number): number;
}

/** What a step did, for a caller that wants to say so. */
export type DropStep = "flying" | "bounced" | "settled" | "resting";

/**
 * Advance one drop by `dtMs`, or bob it if it has already come to rest.
 *
 * In place, because a drop is stepped every frame and a value rebuilt sixty
 * times a second per item is a lot of garbage for no argument gained.
 */
export function stepDrop(
  body: DropBody,
  dtMs: number,
  nowMs: number,
  surface: DropSurface,
): DropStep {
  if (body.settled) {
    body.y = body.groundY + Math.sin(nowMs / DROP_BOB_MS + body.bobPhase) * DROP_BOB_AMPLITUDE;
    return "resting";
  }
  const dt = dtMs / 1000;
  body.vy += DROP_GRAVITY * dt;
  body.y += body.vy * dt;
  body.x += body.vx * dt;
  if (surface.clampX) body.x = surface.clampX(body.x);
  const surfaceY = surface.surfaceAt(body.x);
  if (body.y < surfaceY) return "flying";
  body.y = surfaceY;
  if (body.bounces < 1 && body.vy > DROP_BOUNCE_MIN_VY) {
    body.vy = -body.vy * DROP_BOUNCE_RESTITUTION;
    body.vx *= DROP_BOUNCE_VX_RETAINED;
    body.bounces += 1;
    return "bounced";
  }
  body.settled = true;
  body.vy = 0;
  body.vx = 0;
  body.groundY = surfaceY;
  return "settled";
}
