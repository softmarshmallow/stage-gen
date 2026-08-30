import { describe, expect, test } from "bun:test";
import {
  developerKitLabel,
  developerKitToken,
  nextDeveloperKit,
  sameDeveloperKit,
  selectableDeveloperKits,
  type DeveloperKit,
} from "./developer-kit";

const BOTH_POSES = Object.freeze({ basic_attack: {}, skill_cast: {}, idle: {} });
const DART = Object.freeze({ projectile_id: "paperwing_dart" });
const PULSE = Object.freeze({ projectile_id: "sonar_pulse" });

function kitsFor(
  overrides: Partial<Parameters<typeof selectableDeveloperKits>[0]> = {},
): readonly DeveloperKit[] {
  return selectableDeveloperKits({
    publishedWeaponClass: "melee_dps_v1",
    publishedProjectileId: null,
    projectileCatalog: [DART],
    publishedMotionStates: BOTH_POSES,
    ...overrides,
  });
}

describe("what one run can be played as", () => {
  test("the authored kit is always offered, and always first", () => {
    // The console's default is the package as published; an override is the exception.
    expect(kitsFor()[0]).toEqual({ weaponClass: "melee_dps_v1", projectileId: null });
  });

  test("a throwing kit is offered once per round the run actually drew", () => {
    const kits = kitsFor({ projectileCatalog: [DART, PULSE] });
    expect(kits.map(developerKitToken)).toEqual([
      "melee_dps_v1",
      "ranged_dps_v1:paperwing_dart",
      "ranged_dps_v1:sonar_pulse",
    ]);
  });

  test("a run that drew nothing to throw offers no throwing kit at all", () => {
    // The decisive case: every run generated before the projectile catalog existed is this one.
    // Offering ranged here would have the runtime invent a `projectile_id` the contract never
    // named, which is the runtime authoring a package fact.
    expect(kitsFor({ projectileCatalog: [] }).map(developerKitToken)).toEqual(["melee_dps_v1"]);
  });

  test("a kit whose pose the package never published is not offered", () => {
    // Same rule `resolveWeaponClassProfile` enforces at load, applied before it is ever offered:
    // a class with nothing to draw is not a choice, it is a broken frame.
    const kits = kitsFor({ publishedMotionStates: { basic_attack: {}, idle: {} } });
    expect(kits.map(developerKitToken)).toEqual(["melee_dps_v1"]);
  });

  test("the authored kit is not duplicated when the vocabulary offers it again", () => {
    const kits = kitsFor({
      publishedWeaponClass: "ranged_dps_v1",
      publishedProjectileId: "paperwing_dart",
    });
    expect(kits.map(developerKitToken)).toEqual([
      "ranged_dps_v1:paperwing_dart",
      "melee_dps_v1",
    ]);
  });
});

describe("cycling", () => {
  test("the key advances off the published kit and wraps back to it", () => {
    const kits = kitsFor();
    const second = nextDeveloperKit(null, kits);
    expect(developerKitToken(second!)).toBe("ranged_dps_v1:paperwing_dart");
    expect(developerKitToken(nextDeveloperKit(second, kits)!)).toBe("melee_dps_v1");
  });

  test("a single-kit run cycles to itself rather than to nothing", () => {
    const kits = kitsFor({ projectileCatalog: [] });
    expect(nextDeveloperKit(null, kits)).toEqual(kits[0]);
    expect(nextDeveloperKit(kits[0], kits)).toEqual(kits[0]);
  });

  test("an override no longer offered advances to the first kit rather than sticking", () => {
    const kits = kitsFor({ projectileCatalog: [] });
    const stale: DeveloperKit = { weaponClass: "ranged_dps_v1", projectileId: "gone" };
    expect(nextDeveloperKit(stale, kits)).toEqual(kits[0]);
  });

  test("no kits at all cycles to nothing instead of throwing", () => {
    expect(nextDeveloperKit(null, [])).toBeNull();
  });
});

describe("how a kit reads", () => {
  test("a throwing kit names its round and a swinging kit does not", () => {
    expect(developerKitLabel({ weaponClass: "ranged_dps_v1", projectileId: "paperwing_dart" })).toBe(
      "ranged_dps_v1 (paperwing_dart)",
    );
    expect(developerKitLabel({ weaponClass: "melee_dps_v1", projectileId: null })).toBe(
      "melee_dps_v1",
    );
  });
});

describe("returning to the published kit", () => {
  test("cycling all the way round lands back on the published kit by value", () => {
    // The scene stores null rather than this object, because being played as the published kit is
    // not an override however you arrived there - and cycling is how you arrive there by keyboard.
    // Without that normalisation the probe reports `kitOverridden: true` and the debug overlay
    // marks "(override)" on a run being played exactly as it shipped.
    const kits = kitsFor();
    let current: DeveloperKit | null = null;
    for (let step = 0; step < kits.length; step += 1) {
      current = nextDeveloperKit(current, kits);
    }
    expect(current).not.toBeNull();
    expect(sameDeveloperKit(current!, kits[0])).toBe(true);
  });

  test("kit identity compares both halves, not just the class", () => {
    const dart: DeveloperKit = { weaponClass: "ranged_dps_v1", projectileId: "paperwing_dart" };
    const pulse: DeveloperKit = { weaponClass: "ranged_dps_v1", projectileId: "sonar_pulse" };
    expect(sameDeveloperKit(dart, { ...dart })).toBe(true);
    expect(sameDeveloperKit(dart, pulse)).toBe(false);
  });
});
