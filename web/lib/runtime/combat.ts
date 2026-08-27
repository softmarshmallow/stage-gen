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
  | "skittish"
  | "territorial"
  | "hunting"
  | "relentless";

export const MOB_AGGRESSIONS: readonly MobAggression[] = Object.freeze([
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
): boolean {
  if (
    !Number.isFinite(attackerFootY) ||
    !Number.isFinite(targetFootY) ||
    !Number.isFinite(tilePixels) ||
    tilePixels <= 0
  ) {
    throw new Error("attack level comparison requires finite feet and a positive tile size");
  }
  return (
    Math.abs(attackerFootY - targetFootY) <=
    tilePixels * COMBAT_VERTICAL_REACH_TILES
  );
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
    skittish: Object.freeze({
      aggroRadiusPx: 192,
      chaseSpeedPx: 96,
      strikeRangePx: 0,
      windupMs: 0,
      cooldownMs: 0,
      damage: 0,
      flees: true,
    }),
    territorial: Object.freeze({
      aggroRadiusPx: 256,
      chaseSpeedPx: 72,
      strikeRangePx: 72,
      windupMs: 320,
      cooldownMs: 1400,
      damage: 1,
      flees: false,
    }),
    hunting: Object.freeze({
      aggroRadiusPx: 448,
      chaseSpeedPx: 108,
      strikeRangePx: 80,
      windupMs: 260,
      cooldownMs: 1100,
      damage: 1,
      flees: false,
    }),
    relentless: Object.freeze({
      aggroRadiusPx: 768,
      chaseSpeedPx: 132,
      strikeRangePx: 88,
      windupMs: 200,
      cooldownMs: 900,
      damage: 2,
      flees: false,
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

/**
 * Starting and maximum player hit points.
 *
 * Six, not three: a `relentless` mob deals two, so three would mean two blows from a standing
 * start and the stage would read as unfair rather than dangerous. Six gives a player three
 * mistakes against the worst creature in the roster and six against the common one.
 */
export const PLAYER_MAX_HP = 6;

/**
 * Invulnerability after taking a blow, in ms.
 *
 * Without it, a mob standing inside the player drains the whole bar in one cooldown cycle,
 * because contact is continuous and nothing separates one blow from the next. 900ms is longer
 * than the fastest archetype's 900ms cooldown by design — it guarantees that even `relentless`
 * cannot land twice without the player having had a full window to move.
 */
export const PLAYER_INVULNERABLE_MS = 900;

/** One bright/dim phase of the player sprite while a post-hit immunity window is active. */
export const PLAYER_INVULNERABLE_BLINK_INTERVAL_MS = 75;
/** Dim phase opacity: visible enough to track while making immunity unmistakable. */
export const PLAYER_INVULNERABLE_BLINK_ALPHA = 0.35;

/** Horizontal shove applied to the player on a hit, in pixels per second. */
export const PLAYER_KNOCKBACK_VX = 260;
/** Upward component, so a blow lifts the player slightly rather than sliding them along. */
export const PLAYER_KNOCKBACK_VY = -180;

export type PlayerHealthState = Readonly<{
  hp: number;
  maxHp: number;
  invulnerableUntilMs: number;
  defeated: boolean;
}>;

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
}>;

/** Player damage also carries the immutable state that must replace the caller's current state. */
export type PlayerDamageResolution = DamageResolution &
  Readonly<{ health: PlayerHealthState }>;

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
  });
}

export function initialPlayerHealth(maxHp = PLAYER_MAX_HP): PlayerHealthState {
  if (!Number.isSafeInteger(maxHp) || maxHp <= 0) {
    throw new RangeError("player max HP must be a positive integer");
  }
  return Object.freeze({
    hp: maxHp,
    maxHp,
    invulnerableUntilMs: 0,
    defeated: false,
  });
}

/**
 * Apply one blow, honouring invulnerability.
 *
 * Pure and total: it returns the next state and whether the blow connected, so the caller can
 * decide about knockback, flashes and transcript events without this function knowing about any
 * of them. A blow that lands during invulnerability is not an error and is not a hit — it is
 * simply absorbed, which is what makes standing next to a mob survivable.
 */
export function applyPlayerDamage(
  health: PlayerHealthState,
  amount: number,
  nowMs: number,
): PlayerDamageResolution {
  if (
    health.defeated ||
    !Number.isFinite(amount) ||
    amount <= 0 ||
    nowMs < health.invulnerableUntilMs
  ) {
    return Object.freeze({
      ...rejectedDamage(health.hp, amount, health.defeated),
      health,
    });
  }

  const resolution = resolveDamage(health.hp, amount, health.defeated);
  if (!resolution.connected) {
    return Object.freeze({ ...resolution, health });
  }
  const nextHealth = Object.freeze({
    hp: resolution.hpAfter,
    maxHp: health.maxHp,
    invulnerableUntilMs: nowMs + PLAYER_INVULNERABLE_MS,
    defeated: resolution.defeated,
  });
  return Object.freeze({
    ...resolution,
    health: nextHealth,
  });
}

export function isPlayerInvulnerable(
  health: PlayerHealthState,
  nowMs: number,
): boolean {
  return nowMs < health.invulnerableUntilMs;
}

/**
 * Deterministic sprite opacity for post-hit invulnerability.
 *
 * The phase is derived from the remaining immunity time, so the connecting hit starts dim even
 * though the scene resolves combat after the player's update for that frame. Defeat never
 * blinks: its authored terminal presentation remains fully visible.
 */
export function playerInvulnerabilityBlinkAlpha(
  health: PlayerHealthState,
  nowMs: number,
): number {
  if (health.defeated || !isPlayerInvulnerable(health, nowMs)) return 1;
  const remainingMs = health.invulnerableUntilMs - nowMs;
  const phase = Math.floor(remainingMs / PLAYER_INVULNERABLE_BLINK_INTERVAL_MS);
  return phase % 2 === 0 ? PLAYER_INVULNERABLE_BLINK_ALPHA : 1;
}

// --- Mob decision --------------------------------------------------------------------------

export type MobIntent = "hold" | "chase" | "flee" | "strike";

/**
 * What a mob should do this frame, given where the player is.
 *
 * Separated from `Mob.update` so the decision can be tested against distances directly. The
 * ordering matters and is asserted in the tests: cooldown outranks range, so a mob that has just
 * swung closes again rather than standing inside the player swinging into its own cooldown.
 */
export function mobIntent(input: {
  profile: AggressionProfile;
  distancePx: number;
  nowMs: number;
  attackReadyAtMs: number;
  playerDefeated: boolean;
}): MobIntent {
  const { profile, distancePx, nowMs, attackReadyAtMs, playerDefeated } = input;
  if (playerDefeated || distancePx > profile.aggroRadiusPx) return "hold";
  if (profile.flees) return "flee";
  if (distancePx <= profile.strikeRangePx) {
    return nowMs >= attackReadyAtMs ? "strike" : "hold";
  }
  return "chase";
}
