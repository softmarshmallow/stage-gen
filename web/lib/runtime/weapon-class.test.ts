import { describe, expect, test } from "bun:test";
import { aggressionProfile, MOB_AGGRESSIONS } from "./combat";
import {
  DEFAULT_WEAPON_CLASS,
  WEAPON_CLASSES,
  parseWeaponClass,
  resolveWeaponClassProfile,
  targetingToleranceUnits,
  weaponClassProfile,
} from "./weapon-class";

const TILE = 64;

describe("the melee record is a transcription, not a redesign", () => {
  test("every number the swing shipped with survives the move into the table", () => {
    // These are the values that were `PLAYER_ATTACK_DAMAGE`, the inline `TILE_PX * 1.4`, the
    // controller's three cadence constants, and the scene's single-target `break`. If any of them
    // moves, every package already published starts playing differently, so they are pinned here
    // rather than merely inspected.
    const melee = weaponClassProfile("melee_dps_v1");
    expect(melee.motionState).toBe("basic_attack");
    expect(melee.damage).toBe(1);
    expect(melee.actionDurationMs).toBe(333);
    expect(melee.hitWindowFromMs).toBe(80);
    expect(melee.hitWindowToMs).toBe(250);
    expect(melee.maxTargetsPerAction).toBe(1);
    expect(melee.delivery).toEqual({ kind: "instant", reachTiles: 1.4 });
    expect(melee.verticalReach).toEqual({
      kind: "foot_band",
      tiles: 1,
      targetingToleranceTiles: 1,
    });
    expect(melee.ammoKind).toBeNull();
  });

  test("the automated policy's own three distances survive too", () => {
    // The hunter carried these as `engageRangeUnits: 84` and `footLevelToleranceUnits: 64`, with a
    // `* 0.5` closing rule. Expressed in tiles they are the same pixels, which is what makes the
    // deletion of those fields a refactor rather than a retune.
    const melee = weaponClassProfile("melee_dps_v1");
    expect(melee.standOffTiles.minimum * TILE).toBe(0);
    expect(melee.standOffTiles.approach * TILE).toBe(42);
    expect(melee.standOffTiles.maximum * TILE).toBe(84);
    expect(targetingToleranceUnits(melee, TILE)).toBe(64);
  });
});

describe("the ranged record", () => {
  test("it plays the cast strip every combat package already ships", () => {
    expect(weaponClassProfile("ranged_dps_v1").motionState).toBe("skill_cast");
  });

  test("distance is what it buys, so the damage is deliberately identical", () => {
    expect(weaponClassProfile("ranged_dps_v1").damage).toBe(
      weaponClassProfile("melee_dps_v1").damage,
    );
  });

  test("it commits for longer than the swing, which is what the reach costs", () => {
    const melee = weaponClassProfile("melee_dps_v1");
    const ranged = weaponClassProfile("ranged_dps_v1");
    expect(ranged.actionDurationMs).toBeGreaterThan(melee.actionDurationMs);
    // The object leaves on the release frame, not during the wind-up.
    expect(ranged.hitWindowFromMs).toBeGreaterThan(melee.hitWindowFromMs);
  });

  test("its stand-off floor clears every archetype's swing", () => {
    // Derived, not typed. The scene rechecks an incoming blow against `strikeRangePx * 1.35`
    // before applying it, so a policy that holds station beyond that number is standing outside
    // the reach of every creature in the roster — and stays outside it if an archetype is retuned.
    const worstStrikeReach = Math.max(
      ...MOB_AGGRESSIONS.map((aggression) => aggressionProfile(aggression).strikeRangePx * 1.35),
    );
    const ranged = weaponClassProfile("ranged_dps_v1");
    expect(ranged.standOffTiles.minimum * TILE).toBeGreaterThan(worstStrikeReach);
  });

  test("it gains nothing by walking closer, so it never approaches inside its band", () => {
    const ranged = weaponClassProfile("ranged_dps_v1");
    expect(ranged.standOffTiles.approach).toBe(ranged.standOffTiles.maximum);
    expect(ranged.standOffTiles.minimum).toBeLessThan(ranged.standOffTiles.maximum);
  });

  test("a flat throw reaches one terrain deck either way and says so", () => {
    // The targeting tolerance is what an automated policy asks before anything is in the air, so
    // it must at least cover the decks the shot can actually reach — otherwise the bot declines
    // targets it would have killed.
    expect(targetingToleranceUnits(weaponClassProfile("ranged_dps_v1"), TILE)).toBeGreaterThanOrEqual(
      TILE,
    );
  });
});

describe("the table as a whole", () => {
  test("no two classes are the same record under different names", () => {
    const seen = new Set(
      WEAPON_CLASSES.map((weaponClass) => JSON.stringify(weaponClassProfile(weaponClass))),
    );
    expect(seen.size).toBe(WEAPON_CLASSES.length);
  });

  test("a run that names no class swings, which is what every older package did", () => {
    expect(weaponClassProfile(null)).toBe(weaponClassProfile(DEFAULT_WEAPON_CLASS));
    expect(weaponClassProfile(undefined)).toBe(weaponClassProfile("melee_dps_v1"));
  });

  test("parsing accepts exactly the published vocabulary", () => {
    for (const weaponClass of WEAPON_CLASSES) {
      expect(parseWeaponClass(weaponClass)).toBe(weaponClass);
    }
    expect(parseWeaponClass("hitscan_dps_v1")).toBeNull();
    expect(parseWeaponClass(7)).toBeNull();
    expect(parseWeaponClass(null)).toBeNull();
  });

  test("every profile is frozen, so no caller can retune the game at runtime", () => {
    for (const weaponClass of WEAPON_CLASSES) {
      expect(Object.isFrozen(weaponClassProfile(weaponClass))).toBe(true);
      expect(Object.isFrozen(weaponClassProfile(weaponClass).delivery)).toBe(true);
    }
  });
});

describe("choosing the class a package can actually play", () => {
  const BOTH_POSES = { basic_attack: {}, skill_cast: {} };
  const collect = () => {
    const messages: string[] = [];
    return { messages, record: (message: string) => messages.push(message) };
  };

  test("a package with the pose and a round gets the class it asked for", () => {
    const sink = collect();
    const profile = resolveWeaponClassProfile({
      weaponClass: "ranged_dps_v1",
      combatEnabled: true,
      publishedMotionStates: BOTH_POSES,
      projectileNamed: true,
      recordDiagnostic: sink.record,
    });
    expect(profile).toBe(weaponClassProfile("ranged_dps_v1"));
    expect(sink.messages).toEqual([]);
  });

  test("a missing pose degrades to the default and says so", () => {
    const sink = collect();
    const profile = resolveWeaponClassProfile({
      weaponClass: "ranged_dps_v1",
      combatEnabled: true,
      publishedMotionStates: { basic_attack: {} },
      projectileNamed: true,
      recordDiagnostic: sink.record,
    });
    expect(profile).toBe(weaponClassProfile("melee_dps_v1"));
    expect(sink.messages[0]).toContain("skill_cast");
    expect(sink.messages[0]).toContain("falling back to melee_dps_v1");
  });

  test("a throwing class with nothing to throw degrades rather than declining every attack", () => {
    // The silent failure this exists to prevent: no pool is installed, the hit latch is still
    // consumed, and the character plays the whole cast animation while nothing ever happens.
    const sink = collect();
    const profile = resolveWeaponClassProfile({
      weaponClass: "ranged_dps_v1",
      combatEnabled: true,
      publishedMotionStates: BOTH_POSES,
      projectileNamed: false,
      recordDiagnostic: sink.record,
    });
    expect(profile).toBe(weaponClassProfile("melee_dps_v1"));
    expect(sink.messages[0]).toContain("names nothing to throw");
  });

  test("a package that does not fight is not reported for artwork it does not owe", () => {
    const sink = collect();
    const profile = resolveWeaponClassProfile({
      weaponClass: "ranged_dps_v1",
      combatEnabled: false,
      publishedMotionStates: {},
      projectileNamed: false,
      recordDiagnostic: sink.record,
    });
    expect(profile).toBe(weaponClassProfile("ranged_dps_v1"));
    expect(sink.messages).toEqual([]);
  });

  test("the default class failing on its own pose does not claim to fall back to itself", () => {
    const sink = collect();
    const profile = resolveWeaponClassProfile({
      weaponClass: "melee_dps_v1",
      combatEnabled: true,
      publishedMotionStates: { skill_cast: {} },
      projectileNamed: false,
      recordDiagnostic: sink.record,
    });
    expect(profile).toBe(weaponClassProfile("melee_dps_v1"));
    expect(sink.messages[0]).toContain("no other class is playable");
    expect(sink.messages[0]).not.toContain("falling back");
  });
});
