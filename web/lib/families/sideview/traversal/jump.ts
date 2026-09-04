// Which jump a press buys, and the two ways to know what an arc reaches.
//
// The request and the arcs are one subject because the request is where an arc
// is spent, and a genre that derives its arc from one arithmetic and refuses a
// press with another has two physics wearing one name.
//
// **Both** arc functions live here, and they answer opposite questions. The
// platformer *proves* an authored arc: it has real numbers — a launch speed, a
// gravity, a fixed step — and asks whether a given rise and gap are inside
// them, which is a simulation, step for step, in the same order the controller
// integrates. The runner *derives* an arc from admission: it has no authored
// launch speed at all, only the maximum rise and gap the track was admitted
// against, and closes the kinematics from those, so the arc the player flies is
// by construction the arc the offline proof flew. Neither can be written as the
// other, and the family holds both rather than picking a favourite.

/** Which jump a press bought. */
export type JumpKind = "ground" | "air" | "none";

export type JumpResolution = Readonly<{
  kind: JumpKind;
  /** Signed vertical velocity to assign; negative is upward, 0 when refused. */
  vy: number;
  airJumpsUsed: number;
}>;

/**
 * Decide which jump a press buys.
 *
 * `coyoteExpiresAtMs` is set by the caller only when a support was lost by
 * falling, never by jumping, so the grace window cannot be spent twice or turn
 * one press into a free second grounded launch. A genre with no grace window
 * passes null and the branch is simply never open.
 *
 * The velocities are the caller's, in the caller's own unit, and so is the
 * budget: a runner whose air jump is a full relaunch passes the same speed
 * twice, a platformer whose second impulse is deliberately weaker passes two
 * different ones, and neither arrangement is a special case here.
 */
export function resolveJumpRequest(input: Readonly<{
  support: "terrain" | "platform" | "climbable" | "air";
  airJumpsUsed: number;
  nowMs: number;
  coyoteExpiresAtMs: number | null;
  crouching: boolean;
  maximumAirJumps: number;
  jumpVelocity: number;
  airJumpVelocity: number;
}>): JumpResolution {
  if (!Number.isSafeInteger(input.airJumpsUsed) || input.airJumpsUsed < 0) {
    throw new Error("air jump count must be a nonnegative integer");
  }
  if (!Number.isSafeInteger(input.maximumAirJumps) || input.maximumAirJumps < 0) {
    throw new Error("air jump budget must be a nonnegative integer");
  }
  if (!Number.isFinite(input.nowMs)) throw new Error("jump clock must be finite");
  const refused: JumpResolution = Object.freeze({
    kind: "none" as const,
    vy: 0,
    airJumpsUsed: input.airJumpsUsed,
  });
  if (input.support === "climbable") return refused;
  if (input.support !== "air") {
    if (input.crouching) return refused;
    return Object.freeze({ kind: "ground" as const, vy: -input.jumpVelocity, airJumpsUsed: 0 });
  }
  const coyoteOpen =
    input.coyoteExpiresAtMs !== null && input.nowMs <= input.coyoteExpiresAtMs;
  if (coyoteOpen && input.airJumpsUsed === 0) {
    return Object.freeze({ kind: "ground" as const, vy: -input.jumpVelocity, airJumpsUsed: 0 });
  }
  if (input.airJumpsUsed >= input.maximumAirJumps) return refused;
  return Object.freeze({
    kind: "air" as const,
    vy: -input.airJumpVelocity,
    airJumpsUsed: input.airJumpsUsed + 1,
  });
}

export type JumpReachability = Readonly<{
  reachable: boolean;
  rise: number;
  gap: number;
  apexRise: number;
  landingStep: number | null;
  horizontalRange: number | null;
  /** Step the mid-air impulse was spent on, or null for a single grounded jump. */
  airJumpStep: number | null;
}>;

/**
 * Prove an authored arc: semi-implicit Euler in the controller's own step order.
 *
 * `airJumpVelocity` proves a double jump. The impulse is spent on the first step
 * the arc stops rising, which is both the height-optimal moment and the one a
 * player naturally hits, so a route proved here is a route a player can fly.
 * Landing still requires a descending foot, so the second arc cannot "land" on
 * a deck it is passing on the way up.
 */
export function simulateJumpArc(input: Readonly<{
  rise: number;
  gap: number;
  horizontalSpeed: number;
  jumpVelocity: number;
  airJumpVelocity: number | null;
  gravity: number;
  stepSeconds: number;
  maximumSteps: number;
}>): JumpReachability {
  const { horizontalSpeed, jumpVelocity, airJumpVelocity, gravity, stepSeconds, maximumSteps } =
    input;
  for (const value of [
    input.rise,
    input.gap,
    horizontalSpeed,
    jumpVelocity,
    gravity,
    stepSeconds,
    maximumSteps,
    ...(airJumpVelocity === null ? [] : [airJumpVelocity]),
  ]) {
    if (!Number.isFinite(value)) throw new Error("jump proof values must be finite");
  }
  if (
    input.rise < 0 ||
    input.gap < 0 ||
    horizontalSpeed < 0 ||
    jumpVelocity <= 0 ||
    (airJumpVelocity !== null && airJumpVelocity <= 0) ||
    gravity <= 0 ||
    stepSeconds <= 0 ||
    !Number.isSafeInteger(maximumSteps) ||
    maximumSteps < 1
  ) {
    throw new Error("jump proof values are outside their supported range");
  }
  const targetY = -input.rise;
  let y = 0;
  let vy = -jumpVelocity;
  let apexRise = 0;
  let airJumpStep: number | null = null;
  let airJumpPending = airJumpVelocity !== null;
  for (let step = 1; step <= maximumSteps; step += 1) {
    const previousY = y;
    vy += gravity * stepSeconds;
    if (airJumpPending && vy >= 0) {
      vy = -airJumpVelocity!;
      airJumpPending = false;
      airJumpStep = step;
    }
    y += vy * stepSeconds;
    apexRise = Math.max(apexRise, -y);
    if (vy >= 0 && previousY <= targetY && y >= targetY) {
      const horizontalRange = horizontalSpeed * stepSeconds * step;
      return Object.freeze({
        reachable: input.gap <= horizontalRange,
        rise: input.rise,
        gap: input.gap,
        apexRise,
        landingStep: step,
        horizontalRange,
        airJumpStep,
      });
    }
  }
  return Object.freeze({
    reachable: false,
    rise: input.rise,
    gap: input.gap,
    apexRise,
    landingStep: null,
    horizontalRange: null,
    airJumpStep,
  });
}

/** How many fixed steps a free fall of `fallDistance` takes, or null past the cap. */
export function fallRecoverySteps(input: Readonly<{
  fallDistance: number;
  gravity: number;
  stepSeconds: number;
  maximumSteps: number;
}>): number | null {
  const { gravity, stepSeconds, maximumSteps } = input;
  if (
    !Number.isFinite(input.fallDistance) ||
    input.fallDistance < 0 ||
    !Number.isFinite(gravity) ||
    gravity <= 0 ||
    !Number.isFinite(stepSeconds) ||
    stepSeconds <= 0 ||
    !Number.isSafeInteger(maximumSteps) ||
    maximumSteps < 1
  ) {
    throw new Error("drop proof values are outside their supported range");
  }
  let distance = 0;
  let velocity = 0;
  for (let step = 1; step <= maximumSteps; step += 1) {
    velocity += gravity * stepSeconds;
    distance += velocity * stepSeconds;
    if (distance >= input.fallDistance) return step;
  }
  return null;
}

/** An arc stated as the four numbers an integrator needs. */
export interface JumpArc {
  /** Upward launch speed, units per second. */
  readonly initialSpeedPerSecond: number;
  /** Downward acceleration, units per second squared. */
  readonly gravityPerSecondSquared: number;
  /** Highest point of the arc above the takeoff line, in units. */
  readonly peakUnits: number;
  /** Flat-ground airtime in seconds. */
  readonly airtimeSeconds: number;
}

/**
 * Derive an arc from the admission arithmetic instead of authoring one.
 *
 * A pit of `maxClearGap` columns needs the takeoff column plus the gap crossed
 * before landing, so flat-ground airtime is `(gap + 1) / speed` at the slowest
 * admitted speed — every faster speed then crosses farther. Peak height is the
 * maximal rise plus a margin. From airtime T and peak P the kinematics close:
 * `v0 = 4P/T` and `g = 8P/T²`.
 *
 * Nothing here is in rows: `maxRise` and `maxClearGap` are counts of grid
 * cells, `minSpeed` is cells per second, and the arc comes back in the same
 * cell unit. A genre that admits its track in pixels gets a pixel arc from the
 * identical arithmetic.
 */
export function jumpArcFromAdmission(input: Readonly<{
  maxRise: number;
  maxClearGap: number;
  minSpeed: number;
  peakMargin: number;
  airtimeHeadroom: number;
}>): JumpArc {
  if (input.minSpeed <= 0) {
    throw new Error("jump arc requires a positive minimum speed");
  }
  const peakUnits = input.maxRise + input.peakMargin;
  const airtimeSeconds = ((input.maxClearGap + 1) / input.minSpeed) * input.airtimeHeadroom;
  return Object.freeze({
    initialSpeedPerSecond: (4 * peakUnits) / airtimeSeconds,
    gravityPerSecondSquared: (8 * peakUnits) / (airtimeSeconds * airtimeSeconds),
    peakUnits,
    airtimeSeconds,
  });
}
