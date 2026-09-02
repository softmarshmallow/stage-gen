// When an action commits, and when it can produce a blow.
//
// Fifteen lines that used to sit in the middle of `Player.update`, between the walk and the
// gravity, and therefore could not be exercised without a browser. They are the whole of combat
// cadence: how long a character is committed after pressing the key, and which slice of that
// commitment is allowed to hit. Getting either wrong is the difference between a swing that
// connects and one that whiffs, and neither is visible in a screenshot.
//
// Pure, like `strike.ts` and `projectile-flight.ts` next to it, so the weapon class's numbers can
// be checked directly rather than inferred from what a sprite did.

import type { WeaponClassProfile } from "./weapon-class";

/** Everything the controller carries between frames about the action it is running. */
export type AttackWindowState = Readonly<{
  /** When the current commitment ends. Zero when nothing is running. */
  attackUntil: number;
  /** When it began, which the hit window is measured from. */
  attackStarted: number;
  /** Whether the blow may land right now. */
  attackActive: boolean;
}>;

export const IDLE_ATTACK_WINDOW: AttackWindowState = Object.freeze({
  attackUntil: 0,
  attackStarted: 0,
  attackActive: false,
});

export type AttackWindowStep = AttackWindowState &
  Readonly<{
    /** True on the frame a fresh action commits, so the caller can clear its per-action latches. */
    committed: boolean;
    /** Whether the character is mid-action, which is what selects the attack pose. */
    attacking: boolean;
  }>;

/**
 * Advance one frame of the action clock.
 *
 * A fresh action starts only when the previous commitment has fully elapsed — not merely when its
 * hit window closed. Allowing a new swing during the recovery frames would let a held key produce
 * an attack rate the animation cannot draw, which is the same reason the request is edge-triggered
 * in the first place.
 *
 * `blocked` folds together every reason the character may not start one: defeat, and hanging off a
 * climbable. It is passed in rather than derived because those are the controller's business and
 * this function has no opinion about ladders.
 */
export function stepAttackWindow(input: {
  profile: WeaponClassProfile;
  state: AttackWindowState;
  nowMs: number;
  requested: boolean;
  blocked: boolean;
}): AttackWindowStep {
  const { profile, state, nowMs, requested, blocked } = input;
  const committed =
    requested && !blocked && !state.attackActive && nowMs >= state.attackUntil;

  const attackUntil = committed ? nowMs + profile.actionDurationMs : state.attackUntil;
  const attackStarted = committed ? nowMs : state.attackStarted;
  const attacking = nowMs < attackUntil;
  const elapsed = nowMs - attackStarted;

  return Object.freeze({
    attackUntil,
    attackStarted,
    attacking,
    committed,
    attackActive:
      attacking && elapsed >= profile.hitWindowFromMs && elapsed <= profile.hitWindowToMs,
  });
}

/**
 * The index of the blow due now, or null when none is.
 *
 * A single-blow class is the degenerate case: tick zero is due the moment the window opens and
 * nothing follows it, which is exactly the once-per-action latch the controller kept before
 * multi-hit existed. A multi-hit class spaces its later ticks `hitIntervalMs` apart from the window
 * opening; a tick that would fall after the window closes is never due, so a class authored with
 * more blows than its window holds simply lands fewer rather than landing during recovery.
 *
 * At most one tick per call. A long frame - or a held hitstop, during which the clock still runs -
 * therefore spreads a combo over frames rather than collapsing it into one, which is what keeps
 * the numbers readable as separate blows.
 */
export function nextAttackHitTick(input: {
  profile: WeaponClassProfile;
  state: AttackWindowState;
  nowMs: number;
  ticksFired: number;
}): number | null {
  const { profile, state, nowMs, ticksFired } = input;
  if (!state.attackActive) return null;
  if (!Number.isSafeInteger(ticksFired) || ticksFired < 0) {
    throw new Error("attack hit ticks fired must be a nonnegative integer");
  }
  if (ticksFired >= profile.hitsPerAction) return null;
  const elapsed = nowMs - state.attackStarted;
  const dueAt = profile.hitWindowFromMs + ticksFired * profile.hitIntervalMs;
  if (elapsed < dueAt || elapsed > profile.hitWindowToMs) return null;
  return ticksFired;
}
