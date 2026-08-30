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
