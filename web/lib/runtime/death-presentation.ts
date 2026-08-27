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

/** Select the visible player state without changing authoritative health or control lock. */
export function playerDamagePresentationState(
  input: Readonly<{
    defeated: boolean;
    deathAvailable: boolean;
    hurtAvailable: boolean;
    hurtMotionActive: boolean;
    airborne: boolean;
  }>,
): PlayerDamagePresentationState {
  if (input.defeated) {
    if (input.deathAvailable) return "death";
    if (input.hurtAvailable) return "hurt";
    return input.airborne ? "jump" : "idle";
  }
  return input.hurtAvailable && input.hurtMotionActive ? "hurt" : null;
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
