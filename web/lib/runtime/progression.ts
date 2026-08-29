// Experience and levels — the numbers behind the names the package publishes.
//
// The gameplay contract says `experience_curve = "gentle_rpg_v1"` and stops there, exactly as it
// says `aggression = "relentless"` for a mob and leaves the damage to `combat.ts`. What a level
// costs, what a kill is worth, and what a level buys are gameplay, so they live here: pacing can
// be retuned without regenerating a single asset, and two games that name the same curve level at
// the same rate.
//
// The curve is geometric in cost, which makes level logarithmic in total experience — the ordinary
// RPG shape where the first levels arrive quickly and the tenth is a campaign. A linear cost would
// make the twentieth level as cheap as the second and the whole ladder meaningless by the end.

export type ExperienceCurve = "gentle_rpg_v1" | "steady_rpg_v1" | "brisk_rpg_v1";
export type StatGrowth = "balanced_novice_v1";

export type ExperienceCurveRule = Readonly<{
  /** Experience the first level-up costs. */
  baseCost: number;
  /** Multiplier applied to each successive level's cost. */
  growth: number;
}>;

const EXPERIENCE_CURVES: Readonly<Record<ExperienceCurve, ExperienceCurveRule>> =
  Object.freeze({
    // Roughly nine common kills to level two, and the climb doubles every three levels.
    gentle_rpg_v1: Object.freeze({ baseCost: 24, growth: 1.28 }),
    steady_rpg_v1: Object.freeze({ baseCost: 32, growth: 1.4 }),
    brisk_rpg_v1: Object.freeze({ baseCost: 16, growth: 1.18 }),
  });

export function experienceCurveRule(curve: ExperienceCurve): ExperienceCurveRule {
  const rule = EXPERIENCE_CURVES[curve];
  if (!rule) throw new Error(`unknown experience curve ${curve}`);
  return rule;
}

/** Experience the step from `level` to `level + 1` costs. */
export function experienceForNextLevel(
  level: number,
  curve: ExperienceCurve,
): number {
  if (!Number.isSafeInteger(level) || level < 1) {
    throw new RangeError("experience cost requires a level of at least one");
  }
  const rule = experienceCurveRule(curve);
  return Math.round(rule.baseCost * rule.growth ** (level - 1));
}

/**
 * What one kill is worth.
 *
 * Derived from the rank the package already publishes for the mob, so a game earns experience in
 * proportion to what it actually fought without authoring a second set of numbers. Unknown ranks
 * are worth the common award rather than nothing, because an unrecognised rank is a catalog the
 * runtime has not caught up with, not a creature worth zero.
 */
export function experienceForRank(rank: string): number {
  if (rank === "boss") return 90;
  if (rank === "elite") return 30;
  if (rank === "uncommon") return 12;
  return 6;
}

/**
 * The health pool a level buys.
 *
 * A fifth of the authored pool per level, so growth is proportional to whatever scale the package
 * chose and a level always reads as at least one more point of survivability.
 */
export function maximumHealthForLevel(
  baseHealth: number,
  level: number,
  growth: StatGrowth = "balanced_novice_v1",
): number {
  if (!Number.isSafeInteger(baseHealth) || baseHealth < 1) {
    throw new RangeError("stat growth requires a positive authored health pool");
  }
  if (!Number.isSafeInteger(level) || level < 1) {
    throw new RangeError("stat growth requires a level of at least one");
  }
  if (growth !== "balanced_novice_v1") {
    throw new Error(`unknown stat growth ${growth}`);
  }
  const perLevel = Math.max(1, Math.round(baseHealth * 0.2));
  return baseHealth + (level - 1) * perLevel;
}

export type ProgressionPolicy = Readonly<{
  enabled: boolean;
  maximumLevel: number;
  curve: ExperienceCurve;
  growth: StatGrowth;
  baseHealth: number;
}>;

export type ProgressionState = Readonly<{
  level: number;
  /** Experience banked toward the next level, always below `experienceForNext` while levelling. */
  experienceIntoLevel: number;
  /** Cost of the next level, or null once the authored maximum is reached. */
  experienceForNext: number | null;
  /** Every point ever earned, for display and for the transcript. */
  totalExperience: number;
  maximumHealth: number;
}>;

export function initialProgression(policy: ProgressionPolicy): ProgressionState {
  if (!Number.isSafeInteger(policy.maximumLevel) || policy.maximumLevel < 1) {
    throw new RangeError("progression requires a maximum level of at least one");
  }
  return Object.freeze({
    level: 1,
    experienceIntoLevel: 0,
    experienceForNext:
      policy.maximumLevel > 1 ? experienceForNextLevel(1, policy.curve) : null,
    totalExperience: 0,
    maximumHealth: maximumHealthForLevel(policy.baseHealth, 1, policy.growth),
  });
}

export type ExperienceAward = Readonly<{
  /** Points actually banked. Zero when progression is off or the award was invalid. */
  awarded: number;
  levelsGained: number;
  state: ProgressionState;
}>;

/**
 * Bank experience and settle any levels it buys.
 *
 * Pure and total, and it resolves a multi-level award in one call rather than leaving a caller to
 * loop: a boss worth several levels should read as several levels, not as one plus a remainder
 * that the next kill quietly collects. At the authored maximum the level stops but the total keeps
 * climbing, so the display never lies about what was earned.
 */
export function grantExperience(
  state: ProgressionState,
  amount: number,
  policy: ProgressionPolicy,
): ExperienceAward {
  if (!policy.enabled || !Number.isFinite(amount) || amount <= 0) {
    return Object.freeze({ awarded: 0, levelsGained: 0, state });
  }
  const awarded = Math.floor(amount);
  if (awarded <= 0) return Object.freeze({ awarded: 0, levelsGained: 0, state });

  let level = state.level;
  let intoLevel = state.experienceIntoLevel + awarded;
  let forNext = state.experienceForNext;
  let levelsGained = 0;
  while (forNext !== null && intoLevel >= forNext && level < policy.maximumLevel) {
    intoLevel -= forNext;
    level += 1;
    levelsGained += 1;
    forNext =
      level < policy.maximumLevel ? experienceForNextLevel(level, policy.curve) : null;
  }
  if (forNext === null) intoLevel = 0;
  return Object.freeze({
    awarded,
    levelsGained,
    state: Object.freeze({
      level,
      experienceIntoLevel: intoLevel,
      experienceForNext: forNext,
      totalExperience: state.totalExperience + awarded,
      maximumHealth: maximumHealthForLevel(policy.baseHealth, level, policy.growth),
    }),
  });
}
