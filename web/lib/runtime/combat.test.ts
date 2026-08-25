import { describe, expect, test } from "bun:test";
import {
  DEFAULT_AGGRESSION,
  MOB_AGGRESSIONS,
  PLAYER_INVULNERABLE_MS,
  PLAYER_MAX_HP,
  aggressionProfile,
  applyPlayerDamage,
  initialPlayerHealth,
  isPlayerInvulnerable,
  mobIntent,
  parseAggression,
  resolveDamage,
} from "./combat";

describe("aggression archetypes", () => {
  test("every archetype has a profile and none is accidentally identical", () => {
    const seen = new Set<string>();
    for (const a of MOB_AGGRESSIONS) {
      const p = aggressionProfile(a);
      expect(p.aggroRadiusPx).toBeGreaterThan(0);
      seen.add(JSON.stringify(p));
    }
    // Four archetypes that behave identically are one archetype with four names.
    expect(seen.size).toBe(MOB_AGGRESSIONS.length);
  });

  test("aggression rises monotonically with reach, speed and pressure", () => {
    // The ordering is the whole meaning of the vocabulary: a player must be able to learn what a
    // word implies and have that hold for every creature carrying it.
    const order = ["territorial", "hunting", "relentless"] as const;
    for (let i = 1; i < order.length; i += 1) {
      const prev = aggressionProfile(order[i - 1]);
      const cur = aggressionProfile(order[i]);
      expect(cur.aggroRadiusPx).toBeGreaterThan(prev.aggroRadiusPx);
      expect(cur.chaseSpeedPx).toBeGreaterThan(prev.chaseSpeedPx);
      expect(cur.cooldownMs).toBeLessThan(prev.cooldownMs);
    }
  });

  test("every pursuer outruns the wander speed", () => {
    // Wander is 36 px/s. A chase that moves at patrol speed does not read as a chase.
    for (const a of MOB_AGGRESSIONS) {
      expect(aggressionProfile(a).chaseSpeedPx).toBeGreaterThan(36);
    }
  });

  test("skittish is the harmless one and it retreats rather than standing inert", () => {
    const p = aggressionProfile("skittish");
    expect(p.damage).toBe(0);
    expect(p.flees).toBe(true);
    expect(MOB_AGGRESSIONS.filter((a) => aggressionProfile(a).flees)).toEqual(["skittish"]);
  });

  test("an absent or unknown archetype falls back rather than throwing", () => {
    // Every run generated before the combat system publishes no archetype at all.
    expect(aggressionProfile(null)).toEqual(aggressionProfile(DEFAULT_AGGRESSION));
    expect(aggressionProfile(undefined)).toEqual(aggressionProfile(DEFAULT_AGGRESSION));
    expect(parseAggression("ferocious")).toBeNull();
    expect(parseAggression(7)).toBeNull();
    expect(parseAggression("hunting")).toBe("hunting");
  });
});

describe("player health", () => {
  test("starts full and survives more than two blows from the worst archetype", () => {
    const h = initialPlayerHealth();
    expect(h.hp).toBe(PLAYER_MAX_HP);
    expect(h.defeated).toBe(false);
    // Three mistakes against `relentless` (2 damage), six against the common one.
    expect(PLAYER_MAX_HP / aggressionProfile("relentless").damage).toBeGreaterThan(2);
  });

  test("a blow lands, then invulnerability absorbs the next", () => {
    const first = applyPlayerDamage(initialPlayerHealth(), 1, 1000);
    expect(first.connected).toBe(true);
    expect(first).toMatchObject({
      attemptedAmount: 1,
      appliedAmount: 1,
      hpBefore: PLAYER_MAX_HP,
      hpAfter: PLAYER_MAX_HP - 1,
      defeated: false,
    });
    expect(first.health.hp).toBe(PLAYER_MAX_HP - 1);

    const during = applyPlayerDamage(first.health, 1, 1000 + PLAYER_INVULNERABLE_MS - 1);
    expect(during.connected).toBe(false);
    expect(during).toMatchObject({
      attemptedAmount: 1,
      appliedAmount: 0,
      hpBefore: PLAYER_MAX_HP - 1,
      hpAfter: PLAYER_MAX_HP - 1,
      defeated: false,
    });
    expect(during.health.hp).toBe(PLAYER_MAX_HP - 1);
    expect(during.health).toBe(first.health);

    const after = applyPlayerDamage(first.health, 1, 1000 + PLAYER_INVULNERABLE_MS);
    expect(after.connected).toBe(true);
    expect(after.health.hp).toBe(PLAYER_MAX_HP - 2);
  });

  test("invulnerability outlasts the fastest cooldown", () => {
    // Otherwise a relentless mob standing inside the player drains the bar in one cycle,
    // because contact is continuous and nothing separates one blow from the next.
    const fastest = Math.min(...MOB_AGGRESSIONS.map((a) => aggressionProfile(a).cooldownMs || Infinity));
    expect(PLAYER_INVULNERABLE_MS).toBeGreaterThanOrEqual(fastest);
  });

  test("hp floors at zero and defeat is terminal", () => {
    let h = initialPlayerHealth();
    for (let t = 0; t < 20; t += 1) {
      h = applyPlayerDamage(h, 2, t * PLAYER_INVULNERABLE_MS).health;
    }
    expect(h.hp).toBe(0);
    expect(h.defeated).toBe(true);
    // A defeated player cannot be damaged again — no negative hp in the transcript.
    const again = applyPlayerDamage(h, 2, 999_999);
    expect(again.connected).toBe(false);
    expect(again.appliedAmount).toBe(0);
    expect(again.defeated).toBe(true);
    expect(again.health.hp).toBe(0);
  });

  test("reports effective damage instead of presenting overkill as lost hp", () => {
    const lethal = resolveDamage(2, 99);
    expect(lethal).toEqual({
      connected: true,
      attemptedAmount: 99,
      appliedAmount: 2,
      hpBefore: 2,
      hpAfter: 0,
      defeated: true,
    });
    expect(Object.isFrozen(lethal)).toBe(true);
  });

  test("resolves rejected attempts as complete immutable outcomes", () => {
    expect(resolveDamage(6, 0)).toEqual({
      connected: false,
      attemptedAmount: 0,
      appliedAmount: 0,
      hpBefore: 6,
      hpAfter: 6,
      defeated: false,
    });
    expect(resolveDamage(0, 1, true)).toEqual({
      connected: false,
      attemptedAmount: 1,
      appliedAmount: 0,
      hpBefore: 0,
      hpAfter: 0,
      defeated: true,
    });
    expect(resolveDamage(0, 1).defeated).toBe(true);
    expect(resolveDamage(6, Number.NaN)).toEqual({
      connected: false,
      attemptedAmount: 0,
      appliedAmount: 0,
      hpBefore: 6,
      hpAfter: 6,
      defeated: false,
    });
  });

  test("zero and negative damage never connect", () => {
    const h = initialPlayerHealth();
    expect(applyPlayerDamage(h, 0, 500).connected).toBe(false);
    expect(applyPlayerDamage(h, -3, 500).connected).toBe(false);
    expect(applyPlayerDamage(h, -3, 500).health.hp).toBe(PLAYER_MAX_HP);
  });

  test("invulnerability is reported for the flash the HUD draws", () => {
    const hit = applyPlayerDamage(initialPlayerHealth(), 1, 0).health;
    expect(isPlayerInvulnerable(hit, PLAYER_INVULNERABLE_MS - 1)).toBe(true);
    expect(isPlayerInvulnerable(hit, PLAYER_INVULNERABLE_MS)).toBe(false);
  });
});

describe("mob intent", () => {
  const base = { nowMs: 10_000, attackReadyAtMs: 0, playerDefeated: false };

  test("holds outside its aggro radius", () => {
    const profile = aggressionProfile("territorial");
    expect(mobIntent({ ...base, profile, distancePx: profile.aggroRadiusPx + 1 })).toBe("hold");
    expect(mobIntent({ ...base, profile, distancePx: profile.aggroRadiusPx })).toBe("chase");
  });

  test("closes, then strikes inside its reach", () => {
    const profile = aggressionProfile("hunting");
    expect(mobIntent({ ...base, profile, distancePx: profile.strikeRangePx + 1 })).toBe("chase");
    expect(mobIntent({ ...base, profile, distancePx: profile.strikeRangePx })).toBe("strike");
  });

  test("cooldown outranks range, so it does not swing into its own cooldown", () => {
    const profile = aggressionProfile("hunting");
    const cooling = mobIntent({
      ...base, profile, distancePx: 0, attackReadyAtMs: base.nowMs + 1,
    });
    expect(cooling).toBe("hold");
  });

  test("skittish flees at every distance inside its radius", () => {
    const profile = aggressionProfile("skittish");
    expect(mobIntent({ ...base, profile, distancePx: 0 })).toBe("flee");
    expect(mobIntent({ ...base, profile, distancePx: profile.aggroRadiusPx - 1 })).toBe("flee");
    expect(mobIntent({ ...base, profile, distancePx: profile.aggroRadiusPx + 1 })).toBe("hold");
  });

  test("nothing pursues a defeated player", () => {
    // Otherwise the corpse keeps being mobbed, which reads as a bug rather than as a defeat.
    for (const a of MOB_AGGRESSIONS) {
      expect(mobIntent({ ...base, profile: aggressionProfile(a), distancePx: 0, playerDefeated: true })).toBe("hold");
    }
  });
});
