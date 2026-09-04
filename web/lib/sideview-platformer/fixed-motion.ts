export const MOB_KNOCKBACK_MS = 220;
/** How long a freshly placed creature takes to fade in, so a spawn in view reads as arriving. */
export const MOB_SPAWN_FADE_MS = 240;

/**
 * The alpha of a creature `nowMs` after it was placed, and whether the fade is over.
 *
 * Sampled from simulation time like everything else here, because a creature can now be placed
 * on screen: the population policy prefers off-screen columns, but a crowded zone falls back to
 * whatever is free, and a body that simply appears at full opacity reads as a glitch.
 */
export function sampleMobSpawnFade(
  spawnedAtMs: number,
  nowMs: number,
): Readonly<{ alpha: number; complete: boolean }> {
  const elapsedMs = Math.max(0, nowMs - spawnedAtMs);
  const alpha = Math.min(1, elapsedMs / MOB_SPAWN_FADE_MS);
  return Object.freeze({ alpha, complete: alpha >= 1 });
}
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

/** How long the map-name banner takes to arrive, how long it stays, and the same again to leave. */
export const MAP_NAME_BANNER_FADE_MS = 250;
export const MAP_NAME_BANNER_HOLD_MS = 1000;

export type MapNameBannerSample = Readonly<{ alpha: number; done: boolean }>;

/**
 * The banner's opacity `nowMs` after it was raised, and whether it is finished.
 *
 * Pure fixed-clock equivalent of the yoyo-with-hold tween the scene used to hand the engine: in
 * two hundred and fifty milliseconds, held for a second, out in another two hundred and fifty. A
 * tween is stepped by the browser's frame delta, so under a fixed-step capture the same run
 * announced the same map for a different number of frames every time it was recorded.
 */
export function sampleMapNameBanner(
  raisedAtMs: number,
  nowMs: number,
): MapNameBannerSample {
  const elapsedMs = Math.max(0, nowMs - raisedAtMs);
  const outFromMs = MAP_NAME_BANNER_FADE_MS + MAP_NAME_BANNER_HOLD_MS;
  const totalMs = outFromMs + MAP_NAME_BANNER_FADE_MS;
  if (elapsedMs >= totalMs) return Object.freeze({ alpha: 0, done: true });
  if (elapsedMs <= MAP_NAME_BANNER_FADE_MS) {
    return Object.freeze({
      alpha: unitProgress(elapsedMs, MAP_NAME_BANNER_FADE_MS),
      done: false,
    });
  }
  if (elapsedMs <= outFromMs) return Object.freeze({ alpha: 1, done: false });
  return Object.freeze({
    alpha: 1 - unitProgress(elapsedMs - outFromMs, MAP_NAME_BANNER_FADE_MS),
    done: false,
  });
}
