// The named capabilities a body may have on top of the core, and the named
// locomotions a genre may bind.
//
// The core — surface, step, walk, landing, jump request, arcs — is what every
// body on an occupancy grid does. Everything in this file is something only
// *some* bodies do, and each one is a name rather than a flag on the core: a
// genre that does not list `climb` has no ladder code in its frame, not a
// ladder system answering false all run.
//
// The geometry of a climbable or a deck stays the genre's own. These functions
// take a projector onto the two or three numbers the rule needs, the same way
// the `camera` family takes `track` and `anchor`, so a genre keeps its authored
// vocabulary — `platformId`, `upperDeckY`, `lowerSurfaceY` — and the family
// keeps one rule.

/** Everything a body can be given beyond walking and falling. */
export const TRAVERSAL_CAPABILITIES = Object.freeze([
  "climb",
  "one-way-decks",
  "crouch",
  "drop-through",
  "wrap",
] as const);

export type TraversalCapability = (typeof TRAVERSAL_CAPABILITIES)[number];

/**
 * How a body's intent becomes vertical motion.
 *
 * A locomotion is the whole map from intent to motion, not a modifier on the
 * running one: `ground_v1` jumps, `momentum_v1` carries speed between steps,
 * `thrust_v1` climbs while a button is held and falls when it is released, and
 * a body under one of them does not answer to another's verbs.
 */
export const TRAVERSAL_LOCOMOTIONS = Object.freeze([
  "ground_v1",
  "momentum_v1",
  "thrust_v1",
] as const);

export type TraversalLocomotion = (typeof TRAVERSAL_LOCOMOTIONS)[number];

/**
 * `wrap`, and why nothing implements it.
 *
 * `[navigation].logical_world_wrap` is authored, parsed, and pinned to `false`
 * by the platformer's own contract, so a package that asks for a wrapping world
 * is already refused at parse. The capability is named here because the name is
 * the contract — a genre that wants wrap declares it and the refusal moves from
 * the parser to a missing implementation, which is a better place for it — and
 * inventing the behaviour without a package that asks for it is content work,
 * not extraction.
 */
export const UNIMPLEMENTED_CAPABILITIES: readonly TraversalCapability[] =
  Object.freeze(["wrap"] as const);

/** Keep crouch locomotion directional but never faster than the cap. */
export function resolveCrouchHorizontalVelocity(velocity: number, cap: number): number {
  if (!Number.isFinite(velocity)) {
    throw new Error("crouch horizontal velocity must be finite");
  }
  if (!Number.isFinite(cap) || cap < 0) {
    throw new Error("crouch speed cap must be a nonnegative finite number");
  }
  return Math.sign(velocity) * Math.min(Math.abs(velocity), cap);
}

/** The deck a given x stands over, or undefined between decks. */
export function deckAtX<D extends { readonly left: number; readonly right: number }>(
  decks: readonly D[],
  x: number,
): D | undefined {
  return decks.find((deck) => x >= deck.left && x <= deck.right);
}

/**
 * Whether a body is still falling through the deck it asked to drop through.
 *
 * Two ways to still be inside the drop, and either is enough: the timer has not
 * expired, or the feet have not yet cleared the deck by `clearance`. The second
 * is what stops a slow fall from being re-caught by the deck it just left.
 */
export function dropThroughActive(input: Readonly<{
  nowMs: number;
  expiresAtMs: number;
  footY: number;
  deckY: number;
  clearance: number;
}>): boolean {
  for (const value of [input.nowMs, input.expiresAtMs, input.footY, input.deckY, input.clearance]) {
    if (!Number.isFinite(value)) throw new Error("drop-through values must be finite");
  }
  return input.nowMs <= input.expiresAtMs || input.footY <= input.deckY + input.clearance;
}

/** The two or three numbers the climb rule needs out of a genre's own zone. */
export interface ClimbGeometry {
  /** The axis the zone is locked to. */
  readonly centerX: number;
  /** How far off that axis a body may be and still take the zone. */
  readonly activationHalfWidth: number;
  /** Top endpoint, in the caller's unit; the deck end. */
  readonly upperY: number;
  /** Bottom endpoint, in the caller's unit; the ground end. */
  readonly lowerY: number;
  /** Which deck the upper endpoint belongs to, for the descend-from-a-deck case. */
  readonly deckId: string;
}

/** How fast a body climbs, and what letting go of the zone costs. */
export interface ClimbProfile {
  /** Climb speed along the axis, units per second. */
  readonly speed: number;
  /** How close an endpoint has to be to be taken from the ground. */
  readonly endpointTolerance: number;
  /** Signed vertical velocity of a jump off the zone; negative is upward. */
  readonly jumpVelocity: number;
  /** Horizontal speed carried out of that jump. */
  readonly jumpHorizontalSpeed: number;
}

export type ClimbEntry<Z> = Readonly<{ zone: Z; direction: "up" | "down" }>;

/**
 * Which climbable a body may take this frame, and in which direction.
 *
 * Three ways in, and they are not symmetric because the endpoints are not: from
 * the ground you take the bottom end by pressing up while standing near it,
 * from the air you take the middle of the zone by pressing up while inside it,
 * and from a deck you take the top end by pressing down while standing exactly
 * on the deck the zone hangs from. Pressing both directions takes nothing,
 * which is what makes the rule edge-free and re-askable every frame.
 */
export function climbEntryAt<Z>(input: Readonly<{
  zones: readonly Z[];
  geometry: (zone: Z) => ClimbGeometry;
  profile: ClimbProfile;
  support: "terrain" | "platform" | "climbable" | "air";
  supportId: string | null;
  x: number;
  footY: number;
  up: boolean;
  down: boolean;
}>): ClimbEntry<Z> | null {
  for (const zone of input.zones) {
    const geometry = input.geometry(zone);
    if (Math.abs(input.x - geometry.centerX) > geometry.activationHalfWidth) continue;
    if (
      input.support === "terrain" &&
      input.up &&
      !input.down &&
      Math.abs(input.footY - geometry.lowerY) <= input.profile.endpointTolerance
    ) {
      return Object.freeze({ zone, direction: "up" as const });
    }
    if (
      input.support === "air" &&
      input.up &&
      !input.down &&
      input.footY >= geometry.upperY &&
      input.footY <= geometry.lowerY
    ) {
      return Object.freeze({ zone, direction: "up" as const });
    }
    if (
      input.support === "platform" &&
      input.supportId === geometry.deckId &&
      input.down &&
      !input.up &&
      input.footY === geometry.upperY
    ) {
      return Object.freeze({ zone, direction: "down" as const });
    }
  }
  return null;
}

export type ClimbMotion = Readonly<{
  footY: number;
  vy: number;
  exit: "platform" | "terrain" | null;
}>;

/** Advance an attached body with axis-locked endpoint clamps. */
export function advanceClimbMotion(input: Readonly<{
  geometry: ClimbGeometry;
  profile: ClimbProfile;
  footY: number;
  deltaSeconds: number;
  up: boolean;
  down: boolean;
}>): ClimbMotion {
  if (!Number.isFinite(input.footY) || !Number.isFinite(input.deltaSeconds)) {
    throw new Error("ladder motion values must be finite");
  }
  if (input.deltaSeconds < 0) throw new Error("ladder delta must be nonnegative");
  const direction = input.up === input.down ? 0 : input.up ? -1 : 1;
  const vy = direction * input.profile.speed;
  const next = input.footY + vy * input.deltaSeconds;
  if (next <= input.geometry.upperY) {
    return Object.freeze({ footY: input.geometry.upperY, vy: 0, exit: "platform" as const });
  }
  if (next >= input.geometry.lowerY) {
    return Object.freeze({ footY: input.geometry.lowerY, vy: 0, exit: "terrain" as const });
  }
  return Object.freeze({ footY: next, vy, exit: null });
}

/**
 * Velocity of a jump off a climbable.
 *
 * Direction comes from held intent when there is any, and from facing when
 * there is not, so a body that lets go without steering falls off the side it
 * was looking at rather than dropping straight down the axis it is locked to.
 */
export function climbJumpOffVelocity(input: Readonly<{
  profile: ClimbProfile;
  left: boolean;
  right: boolean;
  facing: "left" | "right";
}>): Readonly<{ vx: number; vy: number }> {
  const direction =
    input.left !== input.right
      ? input.left
        ? -1
        : 1
      : input.facing === "left"
        ? -1
        : 1;
  return Object.freeze({
    vx: direction * input.profile.jumpHorizontalSpeed,
    vy: input.profile.jumpVelocity,
  });
}
