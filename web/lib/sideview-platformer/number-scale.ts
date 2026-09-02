// How big the numbers are.
//
// The generator publishes a *scale name* per package and no numbers, in the shape the critical
// profile and the weapon class already use: whether a common creature has two hit points or two
// hundred is how the game feels, which the consumer owns. Every package published before the field
// existed is `unit_v1`, the identity, so nothing already shipped plays differently.
//
// `arcade_v1` is the action-RPG read: the same fight in hundreds, with a little per-blow variance
// so a column of numbers is a column of different numbers. It scales the player's blows and the
// creatures' pools by one factor, so balance is exactly what it was at unit scale and only the
// digits changed. It deliberately does not touch the creatures' blows or the player's pool: those
// are the aggression table's and progression's, and a package that wanted the whole fight in
// hundreds would name a second scale that says so rather than have this one silently widen.

import { criticalUnitRoll } from "./combat";

export const NUMBER_SCALES = Object.freeze(["unit_v1", "arcade_v1"] as const);

export type NumberScale = (typeof NUMBER_SCALES)[number];

/** The default when a package publishes no scale - every run predating the field. */
export const DEFAULT_NUMBER_SCALE: NumberScale = "unit_v1";

export type NumberScaleProfile = Readonly<{
  numberScale: NumberScale;
  /** Multiplier on outgoing damage and on creature health alike. */
  factor: number;
  /** Symmetric per-blow variation on outgoing damage, as a ratio around one. Zero is exact. */
  varianceRatio: number;
}>;

const PROFILES: Readonly<Record<NumberScale, NumberScaleProfile>> = Object.freeze({
  unit_v1: Object.freeze({ numberScale: "unit_v1", factor: 1, varianceRatio: 0 }),
  arcade_v1: Object.freeze({ numberScale: "arcade_v1", factor: 100, varianceRatio: 0.12 }),
});

export function numberScaleProfile(numberScale: NumberScale | null | undefined): NumberScaleProfile {
  return PROFILES[numberScale ?? DEFAULT_NUMBER_SCALE] ?? PROFILES[DEFAULT_NUMBER_SCALE];
}

export function parseNumberScale(value: unknown): NumberScale | null {
  return typeof value === "string" && (NUMBER_SCALES as readonly string[]).includes(value)
    ? (value as NumberScale)
    : null;
}

const VARIANCE_CHANNEL = 0x5bd1e995;

/**
 * One blow's base damage at this scale, before the critical roll.
 *
 * Seeded from the same blow seed the critical uses, on a different channel, so a replayed run
 * rolls the same variance and the same critical for the same blow. Rounded and floored at one, as
 * the critical multiplier is, so scaling can never round a landed blow away to nothing. The unit
 * scale returns its input untouched, which is what keeps every older package's arithmetic exact.
 */
export function scaleOutgoingDamage(
  baseAmount: number,
  profile: NumberScaleProfile,
  seed: number,
): number {
  if (!Number.isFinite(baseAmount) || baseAmount <= 0) return baseAmount;
  if (profile.factor === 1 && profile.varianceRatio === 0) return baseAmount;
  const roll = criticalUnitRoll((Math.trunc(seed) ^ VARIANCE_CHANNEL) >>> 0);
  const variation = 1 + (roll * 2 - 1) * profile.varianceRatio;
  return Math.max(1, Math.round(baseAmount * profile.factor * variation));
}

/** A creature's health pool at this scale. Exact, so the ladder between ranks is preserved. */
export function scaleMobHealth(baseHealth: number, profile: NumberScaleProfile): number {
  if (!Number.isSafeInteger(baseHealth) || baseHealth <= 0) {
    throw new RangeError("mob health to scale must be a positive integer");
  }
  return baseHealth * profile.factor;
}
