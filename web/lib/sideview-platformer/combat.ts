// Mob aggression archetypes and player health — the gameplay half of the combat system.
//
// The generator publishes an *archetype name* per mob (`skittish`, `territorial`, `hunting`,
// `relentless`) and the artwork drawn for it. It publishes no numbers. That split is the
// architecture rule in AGENTS.md: recipes own generation-specific genre, composition, layout and
// validation assumptions, and consumer adapters own runtime camera, scene, engine and *gameplay*
// assumptions. Aggro radius, chase speed, attack cadence, damage and invulnerability are gameplay,
// so they live here and nowhere in Python.
//
// The practical payoff is that combat feel is tunable without regenerating a single image. The
// archetype decides how a creature behaves and how it was drawn; these tables decide what those
// behaviours cost in pixels and milliseconds.
//
// Everything in this module is pure. The Mob and Player classes hold Phaser objects and cannot be
// unit-tested without a browser; these rules can, and they are the part that decides whether the
// fight is fair.

/** Aggression archetypes, mirroring the closed vocabulary the generator draws from. */
export type MobAggression =
  | "passive"
  | "skittish"
  | "territorial"
  | "hunting"
  | "relentless";

export const MOB_AGGRESSIONS: readonly MobAggression[] = Object.freeze([
  "passive",
  "skittish",
  "territorial",
  "hunting",
  "relentless",
]);

/** The default when a run publishes no combat block — every mob predating the attack system. */
export const DEFAULT_AGGRESSION: MobAggression = "territorial";

/** Combat reaches the current terrain/platform level and one adjacent tile level. */
export const COMBAT_VERTICAL_REACH_TILES = 1 as const;

export function attackFootLevelsOverlap(
  attackerFootY: number,
  targetFootY: number,
  tilePixels: number,
  reachTiles: number = COMBAT_VERTICAL_REACH_TILES,
): boolean {
  if (
    !Number.isFinite(attackerFootY) ||
    !Number.isFinite(targetFootY) ||
    !Number.isFinite(tilePixels) ||
    tilePixels <= 0 ||
    !Number.isFinite(reachTiles) ||
    reachTiles < 0
  ) {
    throw new Error("attack level comparison requires finite feet and a positive tile size");
  }
  return Math.abs(attackerFootY - targetFootY) <= tilePixels * reachTiles;
}

export type AggressionProfile = Readonly<{
  /**
   * How near the player must come, in pixels, before the mob reacts at all.
   *
   * Measured in tiles at the runtime's 64px tile: skittish reacts at 3 tiles and flees,
   * territorial at 4, hunting at 7, relentless at 12 — far enough that it reads as having
   * noticed you across the screen rather than switching on when you touch it.
   */
  aggroRadiusPx: number;
  /**
   * Pixels per second while closing. The wander speed is 36, so even the slowest pursuer is
   * visibly faster once roused — a chase that moves at patrol speed does not read as a chase.
   */
  chaseSpeedPx: number;
  /** Distance at which it stops closing and swings. Slightly inside the player's own reach. */
  strikeRangePx: number;
  /** Wind-up before the blow lands, in ms. The player's window to back out. */
  windupMs: number;
  /** Minimum gap between the start of one swing and the next. */
  cooldownMs: number;
  /** Hit points removed from the player per connected blow. */
  damage: number;
  /** True when the archetype retreats instead of closing. */
  flees: boolean;
  /**
   * False for a creature that never reacts to the player at all: it wanders, it can be struck,
   * and it hurts only on contact. The hunting-ground read, where most of what stands on the route
   * is prey rather than a threat. A hostile flag rather than a zero aggro radius, because the
   * radius still says how far away the creature *notices* you for presentation, and a radius of
   * zero would say it never does.
   */
  hostile: boolean;
  /** Horizontal half-width patrolled around a player the mob cannot reach vertically. */
  inaccessibleSweepHalfWidthPx: number;
  /** Endpoint tolerance for that patrol, preventing sub-pixel turn jitter. */
  pursuitArrivalRadiusPx: number;
  /** Per-instance symmetric movement-speed variation, expressed as a ratio around 1. */
  movementSpeedVarianceRatio: number;
  /** Per-instance symmetric pursuit-corridor variation, expressed as a ratio around 1. */
  pursuitSweepVarianceRatio: number;
  /** Per-action symmetric wind-up/cooldown variation, expressed as a ratio around 1. */
  actionTimingVarianceRatio: number;
}>;

/**
 * Behaviour numbers per archetype.
 *
 * `skittish` is the one that does not attack. It exists so a roster can contain something
 * harmless without the runtime needing a separate "is this thing hostile" flag, and so a
 * peaceful creature reads as peaceful by moving away rather than by standing inert.
 */
const PROFILES: Readonly<Record<MobAggression, AggressionProfile>> =
  Object.freeze({
    passive: Object.freeze({
      aggroRadiusPx: 64,
      chaseSpeedPx: 48,
      strikeRangePx: 0,
      windupMs: 0,
      cooldownMs: 0,
      damage: 0,
      flees: false,
      hostile: false,
      inaccessibleSweepHalfWidthPx: 96,
      pursuitArrivalRadiusPx: 12,
      movementSpeedVarianceRatio: 0.1,
      pursuitSweepVarianceRatio: 0.2,
      actionTimingVarianceRatio: 0,
    }),
    skittish: Object.freeze({
      aggroRadiusPx: 192,
      chaseSpeedPx: 96,
      strikeRangePx: 0,
      windupMs: 0,
      cooldownMs: 0,
      damage: 0,
      flees: true,
      hostile: true,
      inaccessibleSweepHalfWidthPx: 96,
      pursuitArrivalRadiusPx: 12,
      movementSpeedVarianceRatio: 0.1,
      pursuitSweepVarianceRatio: 0.2,
      actionTimingVarianceRatio: 0,
    }),
    territorial: Object.freeze({
      aggroRadiusPx: 256,
      chaseSpeedPx: 72,
      strikeRangePx: 72,
      windupMs: 320,
      cooldownMs: 1400,
      damage: 1,
      flees: false,
      hostile: true,
      inaccessibleSweepHalfWidthPx: 96,
      pursuitArrivalRadiusPx: 12,
      movementSpeedVarianceRatio: 0.1,
      pursuitSweepVarianceRatio: 0.2,
      actionTimingVarianceRatio: 0.2,
    }),
    hunting: Object.freeze({
      aggroRadiusPx: 448,
      chaseSpeedPx: 108,
      strikeRangePx: 80,
      windupMs: 260,
      cooldownMs: 1100,
      damage: 1,
      flees: false,
      hostile: true,
      inaccessibleSweepHalfWidthPx: 112,
      pursuitArrivalRadiusPx: 12,
      movementSpeedVarianceRatio: 0.12,
      pursuitSweepVarianceRatio: 0.24,
      actionTimingVarianceRatio: 0.16,
    }),
    relentless: Object.freeze({
      aggroRadiusPx: 768,
      chaseSpeedPx: 132,
      strikeRangePx: 88,
      windupMs: 200,
      cooldownMs: 900,
      damage: 2,
      flees: false,
      hostile: true,
      inaccessibleSweepHalfWidthPx: 128,
      pursuitArrivalRadiusPx: 12,
      movementSpeedVarianceRatio: 0.14,
      pursuitSweepVarianceRatio: 0.28,
      actionTimingVarianceRatio: 0.12,
    }),
  });

export function aggressionProfile(
  aggression: MobAggression | null | undefined,
): AggressionProfile {
  return PROFILES[aggression ?? DEFAULT_AGGRESSION] ?? PROFILES[DEFAULT_AGGRESSION];
}

export function parseAggression(value: unknown): MobAggression | null {
  return typeof value === "string" &&
    (MOB_AGGRESSIONS as readonly string[]).includes(value)
    ? (value as MobAggression)
    : null;
}

// --- Player health -------------------------------------------------------------------------

/** Horizontal shove applied to the player on a hit, in pixels per second. */
export const PLAYER_KNOCKBACK_VX = 260;
/** Upward component, so a blow lifts the player slightly rather than sliding them along. */
export const PLAYER_KNOCKBACK_VY = -180;

/**
 * The authoritative outcome of applying one damage attempt to one health pool.
 *
 * `attemptedAmount` is the combat rule's request. `appliedAmount` is the HP delta after the
 * zero-floor, so downstream presentation and telemetry never have to reconstruct overkill from
 * mutable actor state. A rejected attempt is still a complete resolution: it reports the same
 * HP before and after, zero applied damage, and `connected = false`.
 */
export type DamageResolution = Readonly<{
  connected: boolean;
  attemptedAmount: number;
  appliedAmount: number;
  hpBefore: number;
  hpAfter: number;
  defeated: boolean;
  /** Whether the blow that produced this resolution rolled critical. Presentation reads it here. */
  critical: boolean;
}>;

function rejectedDamage(
  hp: number,
  attemptedAmount: number,
  defeated: boolean,
): DamageResolution {
  const safeHp = Number.isFinite(hp) ? Math.max(0, hp) : 0;
  return Object.freeze({
    connected: false,
    attemptedAmount: Number.isFinite(attemptedAmount) ? attemptedAmount : 0,
    appliedAmount: 0,
    hpBefore: safeHp,
    hpAfter: safeHp,
    defeated: defeated || safeHp <= 0,
    // A blow that never landed is not a critical, whatever the roll said.
    critical: false,
  });
}

/**
 * Resolve damage against a bare health pool.
 *
 * Pure, side-effect free, and deliberately independent of invulnerability: invulnerability is a
 * player-state gate, while this function is also used by mobs. Finite positive damage preserves
 * the existing arithmetic exactly. Invalid, non-positive, already-defeated, and empty-pool
 * attempts are rejected rather than allowing NaN or negative health into the runtime.
 */
export function resolveDamage(
  hp: number,
  attemptedAmount: number,
  alreadyDefeated = false,
  critical = false,
): DamageResolution {
  if (
    alreadyDefeated ||
    !Number.isFinite(hp) ||
    hp <= 0 ||
    !Number.isFinite(attemptedAmount) ||
    attemptedAmount <= 0
  ) {
    return rejectedDamage(hp, attemptedAmount, alreadyDefeated);
  }

  const hpAfter = Math.max(0, hp - attemptedAmount);
  return Object.freeze({
    connected: true,
    attemptedAmount,
    appliedAmount: hp - hpAfter,
    hpBefore: hp,
    hpAfter,
    defeated: hpAfter <= 0,
    critical,
  });
}

// --- Critical hits -------------------------------------------------------------------------

export type CriticalProfile = "none" | "rare_v1" | "standard_v1" | "frequent_v1";

export type CriticalRule = Readonly<{
  /** Probability in [0, 1] that one blow lands critical. */
  chance: number;
  /** Damage multiplier applied to a critical blow. */
  multiplier: number;
}>;

/**
 * What each named profile costs in probability and damage.
 *
 * The package names the profile and the runtime owns these numbers, the same split the aggression
 * table uses. `frequent_v1` deliberately hits more often for less: a profile that both fires
 * constantly and doubles would turn every fight into a coin flip on the first swing.
 */
const CRITICAL_PROFILES: Readonly<Record<CriticalProfile, CriticalRule>> =
  Object.freeze({
    none: Object.freeze({ chance: 0, multiplier: 1 }),
    rare_v1: Object.freeze({ chance: 0.08, multiplier: 2 }),
    standard_v1: Object.freeze({ chance: 0.18, multiplier: 2 }),
    frequent_v1: Object.freeze({ chance: 0.32, multiplier: 1.75 }),
  });

export const CRITICAL_PROFILE_NAMES: readonly CriticalProfile[] = Object.freeze([
  "none",
  "rare_v1",
  "standard_v1",
  "frequent_v1",
]);

export function criticalRule(profile: CriticalProfile): CriticalRule {
  const rule = CRITICAL_PROFILES[profile];
  if (!rule) throw new Error(`unknown critical profile ${profile}`);
  return rule;
}

/**
 * A stable value in [0, 1) for an integer seed.
 *
 * Deterministic on purpose. `Math.random` would make every replay of the same run diverge at the
 * first swing, and the deterministic transcript is the only reason the runtime can be verified
 * frame by frame at all. Callers supply a seed built from facts that already replay identically —
 * positions, indices, and the scene's own blow counter.
 */
export function criticalUnitRoll(seed: number): number {
  let mixed = Math.trunc(seed) >>> 0;
  mixed ^= mixed >>> 16;
  mixed = Math.imul(mixed, 0x7feb352d) >>> 0;
  mixed ^= mixed >>> 15;
  mixed = Math.imul(mixed, 0x846ca68b) >>> 0;
  mixed ^= mixed >>> 16;
  return (mixed >>> 0) / 0x1_0000_0000;
}

export type CriticalOutcome = Readonly<{
  amount: number;
  critical: boolean;
}>;

/**
 * Roll one blow's damage against a profile.
 *
 * Both sides of a fight go through this: a package arms criticals for the world, not for the
 * player, so a mob that lands one hurts exactly as much more as the player's would. The result
 * is rounded and floored at one, so a multiplier can never round a landed blow away to nothing.
 */
export function resolveCriticalDamage(
  baseAmount: number,
  profile: CriticalProfile,
  seed: number,
): CriticalOutcome {
  const rule = criticalRule(profile);
  if (!Number.isFinite(baseAmount) || baseAmount <= 0) {
    return Object.freeze({ amount: baseAmount, critical: false });
  }
  if (rule.chance <= 0 || criticalUnitRoll(seed) >= rule.chance) {
    return Object.freeze({ amount: baseAmount, critical: false });
  }
  return Object.freeze({
    amount: Math.max(1, Math.round(baseAmount * rule.multiplier)),
    critical: true,
  });
}

// The player's own pool, its window and its blink moved to `vitals.ts`: they were the kernel's
// `Gauge` written a second time under four other names, and the `vitals` family owns them now.
// What is left here is combat — reach, criticals, aggression, and `resolveDamage` against a bare
// pool, which mobs use as well as players.

// --- Mob decision --------------------------------------------------------------------------

export type MobIntent =
  | "hold"
  | "chase"
  | "flee"
  | "strike"
  | "attack_recovery";

/**
 * What a mob should do this frame, given where the player is.
 *
 * Separated from `Mob.update` so the decision can be tested against distances directly. The
 * ordering matters and is asserted in the tests: cooldown outranks range, so a mob that has just
 * swung preserves its committed combat pose instead of falling through to idle patrol.
 */
export function mobIntent(input: {
  profile: AggressionProfile;
  distancePx: number;
  nowMs: number;
  attackReadyAtMs: number;
  playerDefeated: boolean;
}): MobIntent {
  const { profile, distancePx, nowMs, attackReadyAtMs, playerDefeated } = input;
  if (!profile.hostile) return "hold";
  if (playerDefeated || distancePx > profile.aggroRadiusPx) return "hold";
  if (profile.flees) return "flee";
  if (distancePx <= profile.strikeRangePx) {
    return nowMs >= attackReadyAtMs ? "strike" : "attack_recovery";
  }
  return "chase";
}
