// The platformer's vitals: the player's body, on the shared gauge.
//
// This was the second half of `combat.ts` — a vitals module living in a combat
// file. What it held was the kernel's `Gauge` written a second time under four
// other names: `hp` for `value`, `maxHp` for `max`, `invulnerableUntilMs` for
// `refractoryUntilMs`, `defeated` for `depleted`, with the same absorb-while-
// immune rule, the same nine-hundred-millisecond window and the same
// seventy-five-millisecond blink the runner arrived at independently.
//
// The names stay, because they are what a platformer calls them and because a
// rename would move a golden for nothing; the arithmetic is the kernel's, and
// the four numbers are the `vitals` family's one profile. What is left in
// `combat.ts` is combat: strike resolution, reach, criticals, aggression, and
// `resolveDamage` against a bare pool, which mobs use as well as players.

import {
  createGauge,
  drain,
  grow,
  isRefractory,
  refractoryBlinkAlpha,
  restore,
  type Gauge,
} from "@/lib/kernel/gauge";
import {
  CONTACT_HURT_PROFILE,
  parseVitalsBlock,
  type Consequence,
  type VitalsBlockView,
} from "@/lib/families/vitals";
import { PREPARED_RUNTIME_BLOCKS } from "@/lib/manifest/prepared-manifest";
import type { BlockTable } from "@/lib/manifest/blocks";
import type { DamageResolution } from "./combat";

/** Default pool for a package that authors none. */
export const PLAYER_MAX_HP = 6;

/** Immunity after a contact, in ms. The family's profile, not a second copy. */
export const PLAYER_INVULNERABLE_MS = CONTACT_HURT_PROFILE.refractoryMs;

/** One bright/dim phase of the sprite while the window is open. */
export const PLAYER_INVULNERABLE_BLINK_INTERVAL_MS = CONTACT_HURT_PROFILE.blinkIntervalMs;

/** Dim phase opacity: visible enough to track while making immunity unmistakable. */
export const PLAYER_INVULNERABLE_BLINK_ALPHA = CONTACT_HURT_PROFILE.blinkAlpha;

export type PlayerHealthState = Readonly<{
  hp: number;
  maxHp: number;
  invulnerableUntilMs: number;
  defeated: boolean;
}>;

/** Player damage also carries the immutable state that must replace the caller's current state. */
export type PlayerDamageResolution = DamageResolution & Readonly<{ health: PlayerHealthState }>;

/** The authoritative outcome of one healing attempt, shaped like its damage counterpart. */
export type PlayerHealResolution = Readonly<{
  connected: boolean;
  attemptedAmount: number;
  appliedAmount: number;
  hpBefore: number;
  hpAfter: number;
  health: PlayerHealthState;
}>;

/**
 * The player's pool as the kernel sees it, and back again.
 *
 * Two total functions and no state: the genre's field names are a view over
 * the primitive, so there is exactly one implementation of "drain, honouring a
 * window" in the tree and this file is not it.
 */
function asGauge(health: PlayerHealthState): Gauge {
  return Object.freeze({
    value: health.hp,
    max: health.maxHp,
    refractoryUntilMs: health.invulnerableUntilMs,
    depleted: health.defeated,
  });
}

function asHealth(gauge: Gauge): PlayerHealthState {
  return Object.freeze({
    hp: gauge.value,
    maxHp: gauge.max,
    invulnerableUntilMs: gauge.refractoryUntilMs,
    defeated: gauge.depleted,
  });
}

export function initialPlayerHealth(maxHp = PLAYER_MAX_HP): PlayerHealthState {
  if (!Number.isSafeInteger(maxHp) || maxHp <= 0) {
    throw new RangeError("player max HP must be a positive integer");
  }
  return asHealth(createGauge(maxHp));
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
  critical = false,
): PlayerDamageResolution {
  const change = drain(asGauge(health), amount, nowMs, PLAYER_INVULNERABLE_MS);
  return Object.freeze({
    connected: change.connected,
    attemptedAmount: change.attempted,
    appliedAmount: change.applied,
    hpBefore: change.before,
    hpAfter: change.after,
    defeated: change.depleted,
    // A blow that never landed is not a critical, whatever the roll said.
    critical: change.connected && critical,
    health: change.connected ? asHealth(change.gauge) : health,
  });
}

/**
 * What one healing consumable restores, as a fraction of the pool it is poured into.
 *
 * A fraction rather than a flat number because the pool is authored per package: `starting_health`
 * is 6 in one game and 60 in the next, and a flat "+4" is a lifesaver in the first and litter in
 * the second. Two fifths means a full bar is three drinks away at worst, so carrying a stack is
 * worth doing and carrying one is not a full reset.
 */
export const PLAYER_HEALING_RESTORE_FRACTION = 0.4;

/** Hit points one consumable restores against `maxHp`, always at least one. */
export function healingRestoreAmount(maxHp: number): number {
  if (!Number.isFinite(maxHp) || maxHp <= 0) {
    throw new RangeError("healing restore requires a positive maximum HP");
  }
  return Math.max(1, Math.ceil(maxHp * PLAYER_HEALING_RESTORE_FRACTION));
}

/**
 * Restore hit points, honouring the pool ceiling.
 *
 * Rejecting rather than clamping in the three cases where a drink would be wasted: a defeated
 * player (recovery is respawn's job, not a potion's), an invalid or non-positive amount, and a
 * pool already at full. That last rejection is the one that matters in play — it is what stops a
 * held key, or an automated policy, from emptying a bag into a character who was never hurt.
 *
 * Invulnerability is deliberately untouched: drinking is not being hit, and granting immunity here
 * would make chugging the strongest defensive move in the game.
 */
export function applyPlayerHealing(
  health: PlayerHealthState,
  amount: number,
): PlayerHealResolution {
  const change = restore(asGauge(health), amount);
  return Object.freeze({
    connected: change.connected,
    attemptedAmount: change.attempted,
    appliedAmount: change.applied,
    hpBefore: change.before,
    hpAfter: change.after,
    health: change.connected ? asHealth(change.gauge) : health,
  });
}

/**
 * Raise the pool ceiling and fill it, which is what a level-up is.
 *
 * The full heal is the point, not a side effect: a level that only widened the bar would arrive
 * as an empty promise in the middle of the fight that earned it.
 */
export function grownPlayerHealth(
  health: PlayerHealthState,
  maxHp: number,
): PlayerHealthState {
  if (!Number.isSafeInteger(maxHp) || maxHp <= 0) {
    throw new RangeError("grown player health requires a positive integer maximum");
  }
  const grown = grow(asGauge(health), maxHp);
  return maxHp <= health.maxHp ? health : asHealth(grown);
}

export function isPlayerInvulnerable(health: PlayerHealthState, nowMs: number): boolean {
  return isRefractory(asGauge(health), nowMs);
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
  return refractoryBlinkAlpha(
    asGauge(health),
    nowMs,
    PLAYER_INVULNERABLE_BLINK_INTERVAL_MS,
    PLAYER_INVULNERABLE_BLINK_ALPHA,
  );
}

/**
 * The one way a body is hurt here: a creature's blow landing on the player.
 *
 * Opaque to the family, which never learns what a contact is — the string is
 * this genre's, the way `pit` and `crush` are the runner's.
 */
export type PlatformerVitalsSource = "contact";

/**
 * The platformer's authored form, mapped onto the family's table.
 *
 * This is the mapping the plan says lives in the consumer until the authored
 * unification: the runner names a consequence per source, and the platformer
 * publishes a bare `starting_health` integer (which is the gauge's ceiling) and
 * a `contact_damage` boolean. The boolean is not a consequence — it decides
 * whether the *source is raised at all*, which is exactly what the scene's own
 * `if (combat.enabled && combat.contact_damage)` already does — so the table
 * itself is unconditional and says the one thing the package can mean: a blow
 * that connects spends a point and the run goes on.
 */
export const PLATFORMER_CONSEQUENCES: Readonly<Record<PlatformerVitalsSource, Consequence>> =
  Object.freeze({ contact: "drain_v1" });

/** Whether this package raises a contact at all; the boolean, read where it belongs. */
export function contactCanHurt(combat: {
  readonly enabled: boolean;
  readonly contact_damage: boolean;
}): boolean {
  return combat.enabled && combat.contact_damage;
}

/**
 * The block this genre's vitals are authored in.
 *
 * `[gameplay] player.starting_health` is the pool and `[gameplay]
 * combat.contact_damage` is whether a contact costs anything at all — the bare
 * integer and the boolean the plan intends to unify with the runner's named
 * table, which is a contract bump and a separate decision. Gating the block is
 * not: the family takes its own dependency on `gameplay` by name.
 */
export const PLATFORMER_VITALS_BLOCK = Object.freeze({
  block: "gameplay",
  version: PREPARED_RUNTIME_BLOCKS.gameplay,
});

/** Gate the platformer's vitals block. Refuses by naming `gameplay`. */
export function parsePlatformerVitalsBlock(blocks: BlockTable): VitalsBlockView {
  return parseVitalsBlock(blocks, PLATFORMER_VITALS_BLOCK);
}
