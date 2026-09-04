import { selectMotion } from "@/lib/families/sideview/motion";

export const DEATH_STRIP_FRAME_COUNT = 4;
export const DEATH_STRIP_FRAME_RATE = 8;
export const DEATH_STRIP_DURATION_MS =
  (DEATH_STRIP_FRAME_COUNT / DEATH_STRIP_FRAME_RATE) * 1000;

export type PlayerDamagePresentationState =
  | "death"
  | "hurt"
  | "jump"
  | "idle"
  | null;

/**
 * Select the visible player state without changing authoritative health or the
 * control lock.
 *
 * Two halves, and keeping them apart is the whole ruling. The **rule** is one
 * line and knows nothing about what artwork shipped: a defeated player wears
 * their death, a flinching one wears their flinch, and anybody else wears
 * whatever the controller chose. The **substitution** is the family's fallback
 * walk: a package with no terminal strip draws its flinch, and one with neither
 * lies in whatever pose it was already in.
 *
 * Availability therefore cannot reach the rule. It never could here — the
 * control lock is `health.defeated` and always was — and this is the shape that
 * keeps it that way as the table grows, instead of a chain of `if (available)`
 * that the next state has to be threaded into.
 */
export function playerDamagePresentationState(
  input: Readonly<{
    defeated: boolean;
    deathAvailable: boolean;
    hurtAvailable: boolean;
    hurtMotionActive: boolean;
    airborne: boolean;
  }>,
): PlayerDamagePresentationState {
  const ruled = input.defeated ? "death" : input.hurtMotionActive ? "hurt" : null;
  if (ruled === null) return null;
  const selection = selectMotion({
    state: ruled,
    available: (candidate) => {
      if (candidate === "death") return input.deathAvailable;
      if (candidate === "hurt") return input.hurtAvailable;
      // The last rung of a defeated body's chain is a pose every package has.
      return true;
    },
    fallbacks: {
      death: ["hurt", input.airborne ? "jump" : "idle"],
      // A flinch has nowhere to fall back to: not drawing one is the answer,
      // because the controller is still playing whatever it was playing.
      hurt: [],
    },
  });
  return selection.drawn as PlayerDamagePresentationState;
}

export type MobDeathPresentationPlan = Readonly<{
  playAnimation: boolean;
  fadeDelayMs: number;
}>;

/** Preserve the deterministic legacy fade while prepared actors play their authored strip first. */
export function mobDeathPresentationPlan(
  input: Readonly<{
    deathAnimationAvailable: boolean;
    fixedStepMotion: boolean;
  }>,
): MobDeathPresentationPlan {
  const playAnimation =
    input.deathAnimationAvailable && !input.fixedStepMotion;
  return Object.freeze({
    playAnimation,
    fadeDelayMs: playAnimation ? DEATH_STRIP_DURATION_MS : 0,
  });
}
