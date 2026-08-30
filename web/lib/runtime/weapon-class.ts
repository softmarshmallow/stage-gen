// What a weapon class costs in pixels, milliseconds and hit points.
//
// The generator publishes a *class name* per package — `melee_dps_v1`, `ranged_dps_v1` — and the
// artwork drawn for it. It publishes no numbers. That is the same split the aggression table and
// the critical table already use, and the same architecture rule in AGENTS.md: recipes own
// generation assumptions, consumer adapters own gameplay ones. Reach, damage, cadence, flight
// speed and the distance a bot holds are gameplay, so they live here and nowhere in Python.
//
// Before this module those numbers were five module constants in three files — the swing damage
// and reach inline in the scene, the swing cadence on the controller, and the bot's engage range
// restated a fourth time with a comment explaining that it had to match. A number with four owners
// is a number that will disagree with itself. There is one owner now, and the melee record below
// reproduces every previously shipped value exactly, which is what makes this table a refactor for
// every package that already exists and a feature only for the ones that name the new class.

/**
 * The closed vocabulary the gameplay contract draws from. Mirrors `CombatPolicy.weapon_class`.
 *
 * Declared as one narrow tuple with the union derived from it, rather than a union plus a widened
 * array, so the manifest reader can validate against this list directly instead of restating it.
 * A second copy of a closed vocabulary is a copy that will eventually disagree.
 */
export const WEAPON_CLASSES = Object.freeze(["melee_dps_v1", "ranged_dps_v1"] as const);

export type WeaponClass = (typeof WEAPON_CLASSES)[number];

/** The default when a package publishes no class — every run predating the taxonomy. */
export const DEFAULT_WEAPON_CLASS: WeaponClass = "melee_dps_v1";

/**
 * How a blow gets from the character to the target.
 *
 * A discriminated union rather than a nullable projectile block, because the two arms share no
 * field: a swing has a reach and no travel, a throw has travel and no reach. Modelling the swing
 * as a projectile with zero flight time would put a lifecycle, a pool and a collision pass behind
 * every melee hit for nothing.
 */
export type DeliveryRule =
  | Readonly<{
      kind: "instant";
      /**
       * Width of the swing band, in tiles. The band is centred half a reach ahead of the
       * character, so it covers a little behind and considerably in front.
       */
      reachTiles: number;
    }>
  | Readonly<{
      /**
       * The character throws, and the object decides the rest.
       *
       * Deliberately carries no numbers. Speed, gravity, range, release point and collision box
       * are properties of the thing in the air, not of the arm that threw it, and they live on the
       * projectile's own flight profile — which is what lets one game throw a slow orb and another
       * a flat dart without either inventing a second weapon class.
       */
      kind: "projectile";
    }>;

/**
 * Which vertical rule decides whether a target is in range.
 *
 * Two arms rather than one tolerance, because a swing and a throw disagree about what height even
 * means. A swing reaches from where the character stands, so it compares feet to feet and tolerates
 * one terrain level either way. A thrown object is simply *where it is* — comparing its origin's
 * foot level to the target's would describe a reach the character already let go of.
 *
 * `targetingToleranceTiles` exists on both arms because an automated policy has to decide whether
 * a target is worth engaging *before* anything is in the air, and cannot ask a projectile that
 * does not exist yet.
 */
export type VerticalReachRule =
  | Readonly<{ kind: "foot_band"; tiles: number; targetingToleranceTiles: number }>
  | Readonly<{ kind: "body_overlap"; targetingToleranceTiles: number }>;

/**
 * The distance band an automated policy tries to hold, in tiles.
 *
 * Three numbers rather than two because "far enough to engage" and "close enough to stop walking"
 * are different questions and the hunter has always answered them separately. `maximum` is the
 * furthest a target is worth attacking from; `approach` is the distance the policy walks in to;
 * `minimum` is the distance below which it backs away.
 */
export type StandOffBand = Readonly<{
  minimum: number;
  approach: number;
  maximum: number;
}>;

export type WeaponClassProfile = Readonly<{
  /**
   * The name this profile answers to, carried on the record as the projectile profile carries its
   * own id. Without it the only way back from a resolved profile to its name is a reverse lookup
   * through the table, which every caller would have to write for itself.
   */
  weaponClass: WeaponClass;
  /** Which drawn motion state the action plays. Both are already generated for every package. */
  motionState: "basic_attack" | "skill_cast";
  /** Hit points removed per connected blow, before the critical multiplier. */
  damage: number;
  /** How long the character is committed to the action, in ms. */
  actionDurationMs: number;
  /** When the action can first produce a hit or a launch, in ms from its start. */
  hitWindowFromMs: number;
  /** When that window closes. */
  hitWindowToMs: number;
  delivery: DeliveryRule;
  verticalReach: VerticalReachRule;
  /**
   * How many targets one action may resolve against.
   *
   * A property of the swing, so it applies to the instant arm only; a thrown object's arrival is
   * the projectile's business and comes from its impact profile.
   */
  maxTargetsPerAction: number;
  /** The catalog role one action spends, or null when the class costs nothing to use. */
  ammoKind: string | null;
  standOffTiles: StandOffBand;
}>;

/**
 * What each class costs.
 *
 * `melee_dps_v1` is a transcription, not a design: 1 damage, a 1.4-tile band, a one-tile foot
 * band, one target per swing and a 333/80/250 ms cadence are the values every package shipped so
 * far has been played at, and the table is pinned to them by test.
 *
 * `ranged_dps_v1` deliberately deals the *same* damage. Distance is what it buys — a character
 * that can hit from five tiles never walks into contact and never pays the contact-damage tax, and
 * a class that also hit harder would make the melee record a strictly worse choice rather than a
 * different one.
 */
const PROFILES: Readonly<Record<WeaponClass, WeaponClassProfile>> = Object.freeze({
  melee_dps_v1: Object.freeze({
    weaponClass: "melee_dps_v1",
    // The `basic_action` strip. Four frames at 12 fps is what the contract authors it at.
    motionState: "basic_attack",
    damage: 1,
    actionDurationMs: 333,
    // The window opens around frame 1 and closes after frame 3, so the very first and very last
    // frames of the swing are wind-up and recovery rather than reach.
    hitWindowFromMs: 80,
    hitWindowToMs: 250,
    delivery: Object.freeze({ kind: "instant", reachTiles: 1.4 } as const),
    verticalReach: Object.freeze({
      kind: "foot_band",
      tiles: 1,
      targetingToleranceTiles: 1,
    } as const),
    maxTargetsPerAction: 1,
    ammoKind: null,
    // The shipped hunter numbers, in the table's own unit: 1.3125 tiles is 84 units and 0.65625 is
    // 42, which is what the behaviour has always engaged and closed at. Deliberately shorter than
    // the swing's own 1.4-tile band - the policy walks to a comfortable distance rather than
    // standing at the very edge of its reach and missing whenever the target drifts. A minimum of
    // zero is what keeps it walking all the way in: no distance is too close for a swing, so the
    // back-off branch can never fire.
    standOffTiles: Object.freeze({ minimum: 0, approach: 0.65625, maximum: 1.3125 }),
  }),
  ranged_dps_v1: Object.freeze({
    weaponClass: "ranged_dps_v1",
    // The `secondary_action` strip. Already drawn, already validated, already published for every
    // combat-enabled package, and until now bound to nothing the runtime could play.
    motionState: "skill_cast",
    damage: 1,
    // Four frames at the 10 fps the cast is authored at: the throw is genuinely slower to commit
    // to than the swing, which is the cost that pays for the reach.
    actionDurationMs: 400,
    // Later than the swing's, because the object leaves the hand on the release frame rather than
    // during the wind-up.
    hitWindowFromMs: 160,
    hitWindowToMs: 260,
    delivery: Object.freeze({ kind: "projectile" } as const),
    verticalReach: Object.freeze({
      kind: "body_overlap",
      // What a flat throw can actually reach is asymmetric - the shot leaves at chest height, so
      // it clears more above the character than below - and a targeting rule that has to answer
      // before anything is in the air cannot be. 1.2 tiles is the symmetric band inscribed in the
      // asymmetric one: it covers one terrain deck either way, which is what melee covers, and
      // declines the cases where only a taller-than-average target would have been struck.
      targetingToleranceTiles: 1.2,
    } as const),
    maxTargetsPerAction: 1,
    // Null in this revision. The selector, the spend and the automated decline are all built and
    // tested, but arming them needs a package whose loot rules actually sustain a throw; see the
    // ammunition note in the runtime README.
    ammoKind: null,
    // 2.5 tiles is 160px, outside the longest strike range any aggression archetype has once the
    // scene's own tolerance is applied - so a policy holding this band stands beyond every
    // creature's swing. The test derives that floor from the archetype table rather than typing it.
    // `approach` equals `maximum` on purpose: a throw does not improve by walking closer, so a
    // target anywhere in the band is attacked from where the character already stands.
    standOffTiles: Object.freeze({ minimum: 2.5, approach: 5.5, maximum: 5.5 }),
  }),
});

export function weaponClassProfile(
  weaponClass: WeaponClass | null | undefined,
): WeaponClassProfile {
  return PROFILES[weaponClass ?? DEFAULT_WEAPON_CLASS] ?? PROFILES[DEFAULT_WEAPON_CLASS];
}

export function parseWeaponClass(value: unknown): WeaponClass | null {
  return typeof value === "string" && (WEAPON_CLASSES as readonly string[]).includes(value)
    ? (value as WeaponClass)
    : null;
}

/**
 * The vertical tolerance a targeting decision should use, in pixels.
 *
 * Both arms answer, which is the point: an automated policy asks this before anything is thrown,
 * and a policy that had to know which arm it was holding would be deciding the same question twice.
 */
export function targetingToleranceUnits(
  profile: WeaponClassProfile,
  tilePixels: number,
): number {
  return profile.verticalReach.targetingToleranceTiles * tilePixels;
}

/**
 * Choose the class a package can actually play, reporting anything it asked for and cannot have.
 *
 * Two ways a run can name a class it has no artwork or no ammunition for, and both degrade to the
 * default rather than throwing. The pose may be missing: Python forbids a combat-enabled package
 * from omitting either attack strip, but the gameplay object is parsed independently of the
 * published motion states, so a hand-edited manifest can still ask for a pose that never loaded and
 * take the controller into a state with nothing to draw. The round may be missing: the contract
 * requires a throwing class to name one, and the same independence applies.
 *
 * Degrading rather than failing is the choice the healing-consumable check already makes — a
 * package that ships less than it claimed is still playable, and a blank screen is not a better
 * report of that than a line in the diagnostics.
 *
 * Two things it deliberately does not do. It says nothing about a package that does not fight,
 * because such a package owes no attack strip at all and a report there would be noise. And it
 * claims a fallback only when the fallback is genuinely different and genuinely playable: telling
 * someone their melee package is falling back to melee explains nothing.
 */
export function resolveWeaponClassProfile(input: {
  weaponClass: WeaponClass | null | undefined;
  combatEnabled: boolean;
  publishedMotionStates: Readonly<Record<string, unknown>>;
  projectileNamed: boolean;
  recordDiagnostic: (message: string) => void;
}): WeaponClassProfile {
  const requested = weaponClassProfile(input.weaponClass);
  if (!input.combatEnabled) return requested;

  const fallback = weaponClassProfile(DEFAULT_WEAPON_CLASS);
  const posePublished = input.publishedMotionStates[requested.motionState] !== undefined;
  const roundNamed = requested.delivery.kind !== "projectile" || input.projectileNamed;
  if (posePublished && roundNamed) return requested;

  const reason = !posePublished
    ? `needs the ${requested.motionState} pose, which this package does not publish`
    : "throws, but this package names nothing to throw";
  const recoverable =
    requested !== fallback &&
    input.publishedMotionStates[fallback.motionState] !== undefined;
  input.recordDiagnostic(
    recoverable
      ? `weapon class ${String(input.weaponClass)} ${reason}; falling back to ${DEFAULT_WEAPON_CLASS}`
      : `weapon class ${String(input.weaponClass)} ${reason}, and no other class is playable`,
  );
  return recoverable ? fallback : requested;
}
