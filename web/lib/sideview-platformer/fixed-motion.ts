export const MOB_KNOCKBACK_MS = 220;
export const MOB_DEATH_FADE_MS = 280;

export type FixedMobHitMotion = Readonly<{
  startedMs: number;
  startX: number;
  targetX: number;
  died: boolean;
}>;

export type FixedMobHitSample = Readonly<{
  x: number;
  alpha: number;
  hidden: boolean;
  complete: boolean;
}>;

function unitProgress(elapsedMs: number, durationMs: number): number {
  return Math.max(0, Math.min(1, elapsedMs / durationMs));
}
/**
 * Pure fixed-clock equivalent of the normal preview's Cubic.easeOut
 * knockback and linear death fade.
 */
export function sampleFixedMobHit(
  motion: FixedMobHitMotion,
  nowMs: number,
): FixedMobHitSample {
  const elapsedMs = Math.max(0, nowMs - motion.startedMs);
  const knockbackProgress = unitProgress(elapsedMs, MOB_KNOCKBACK_MS);
  const easedKnockback = 1 - (1 - knockbackProgress) ** 3;
  const x = motion.startX + (motion.targetX - motion.startX) * easedKnockback;
  const fadeProgress = motion.died
    ? unitProgress(elapsedMs, MOB_DEATH_FADE_MS)
    : 0;
  const complete = motion.died
    ? fadeProgress === 1
    : knockbackProgress === 1;
  return Object.freeze({
    x,
    alpha: 1 - fadeProgress,
    hidden: motion.died && fadeProgress === 1,
    complete,
  });
}
