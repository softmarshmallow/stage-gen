import { describe, expect, test } from "bun:test";
import {
  DEFAULT_AGGRESSION,
  MOB_AGGRESSIONS,
  aggressionProfile,
  attackFootLevelsOverlap,
  CRITICAL_PROFILE_NAMES,
  criticalRule,
  resolveCriticalDamage,
  mobIntent,
  parseAggression,
  resolveDamage,
} from "./combat";
import {
  PLAYER_INVULNERABLE_BLINK_ALPHA,
  PLAYER_INVULNERABLE_BLINK_INTERVAL_MS,
  PLAYER_INVULNERABLE_MS,
  PLAYER_MAX_HP,
  applyPlayerDamage,
  applyPlayerHealing,
  grownPlayerHealth,
  healingRestoreAmount,
  initialPlayerHealth,
  isPlayerInvulnerable,
  playerInvulnerabilityBlinkAlpha,
} from "./vitals";

describe("attack level reach", () => {
  test("accepts the same or one adjacent level and rejects a jump above it", () => {
    expect(attackFootLevelsOverlap(600, 600, 64)).toBeTrue();
    expect(attackFootLevelsOverlap(600, 536, 64)).toBeTrue();
    expect(attackFootLevelsOverlap(536, 600, 64)).toBeTrue();
    expect(attackFootLevelsOverlap(600, 535.99, 64)).toBeFalse();
    expect(() => attackFootLevelsOverlap(0, 0, 0)).toThrow("positive tile size");
  });

  test("a caller may widen or narrow the band, and a nonsense band is refused", () => {
    // The default is the one every package has been played at; the parameter exists so a weapon
    // class can declare its own rather than a second module owning the number.
    expect(attackFootLevelsOverlap(600, 472, 64, 2)).toBeTrue();
    expect(attackFootLevelsOverlap(600, 471.99, 64, 2)).toBeFalse();
    expect(attackFootLevelsOverlap(600, 600, 64, 0)).toBeTrue();
    expect(attackFootLevelsOverlap(600, 599, 64, 0)).toBeFalse();
    expect(() => attackFootLevelsOverlap(600, 600, 64, -1)).toThrow("positive tile size");
    expect(() => attackFootLevelsOverlap(600, 600, 64, Number.NaN)).toThrow("positive tile size");
  });
});

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

  test("passive is the prey archetype: it never reacts, and it is the only one that does not", () => {
    const p = aggressionProfile("passive");
    expect(p.hostile).toBe(false);
    expect(p.damage).toBe(0);
    expect(p.flees).toBe(false);
    expect(MOB_AGGRESSIONS.filter((a) => !aggressionProfile(a).hostile)).toEqual(["passive"]);
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
  test("accepts authored starting health and rejects invalid maxima", () => {
    expect(initialPlayerHealth(10)).toEqual({
      hp: 10,
      maxHp: 10,
      invulnerableUntilMs: 0,
      defeated: false,
    });
    expect(() => initialPlayerHealth(0)).toThrow(RangeError);
    expect(() => initialPlayerHealth(1.5)).toThrow(RangeError);
  });

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
      critical: false,
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
      critical: false,
    });
    expect(resolveDamage(0, 1, true)).toEqual({
      connected: false,
      attemptedAmount: 1,
      appliedAmount: 0,
      hpBefore: 0,
      hpAfter: 0,
      defeated: true,
      critical: false,
    });
    expect(resolveDamage(0, 1).defeated).toBe(true);
    expect(resolveDamage(6, Number.NaN)).toEqual({
      connected: false,
      attemptedAmount: 0,
      appliedAmount: 0,
      hpBefore: 6,
      hpAfter: 6,
      defeated: false,
      critical: false,
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

  test("blinks the player throughout invulnerability and restores full opacity", () => {
    const hit = applyPlayerDamage(initialPlayerHealth(), 1, 1000).health;
    expect(playerInvulnerabilityBlinkAlpha(hit, 1000)).toBe(
      PLAYER_INVULNERABLE_BLINK_ALPHA,
    );
    expect(
      playerInvulnerabilityBlinkAlpha(
        hit,
        1000 + PLAYER_INVULNERABLE_BLINK_INTERVAL_MS,
      ),
    ).toBe(1);
    expect(
      playerInvulnerabilityBlinkAlpha(hit, 1000 + PLAYER_INVULNERABLE_MS),
    ).toBe(1);
  });

  test("keeps a defeated player's terminal pose fully visible", () => {
    const defeated = applyPlayerDamage(initialPlayerHealth(1), 1, 1000).health;
    expect(defeated.defeated).toBe(true);
    expect(playerInvulnerabilityBlinkAlpha(defeated, 1000)).toBe(1);
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

  test("cooldown enters explicit attack recovery instead of idle patrol", () => {
    const profile = aggressionProfile("hunting");
    const cooling = mobIntent({
      ...base, profile, distancePx: 0, attackReadyAtMs: base.nowMs + 1,
    });
    expect(cooling).toBe("attack_recovery");
  });

  test("passive holds at every distance, however close and however ready", () => {
    const profile = aggressionProfile("passive");
    expect(mobIntent({ ...base, profile, distancePx: 0 })).toBe("hold");
    expect(mobIntent({ ...base, profile, distancePx: profile.aggroRadiusPx - 1 })).toBe("hold");
    expect(mobIntent({ ...base, profile, distancePx: profile.aggroRadiusPx + 1 })).toBe("hold");
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

describe("player healing", () => {
  test("restores a share of the authored pool, never less than one point", () => {
    // Scale-free: the same drink is meaningful in a six-point game and a sixty-point one.
    expect(healingRestoreAmount(10)).toBe(4);
    expect(healingRestoreAmount(60)).toBe(24);
    expect(healingRestoreAmount(1)).toBe(1);
    expect(() => healingRestoreAmount(0)).toThrow(RangeError);
  });

  test("a drink restores hit points without touching immunity", () => {
    const hurt = applyPlayerDamage(initialPlayerHealth(10), 6, 1000).health;
    const healed = applyPlayerHealing(hurt, 4);
    expect(healed).toMatchObject({
      connected: true,
      attemptedAmount: 4,
      appliedAmount: 4,
      hpBefore: 4,
      hpAfter: 8,
    });
    // Drinking is not being hit; granting immunity here would make chugging the best defence.
    expect(healed.health.invulnerableUntilMs).toBe(hurt.invulnerableUntilMs);
  });

  test("clamps to the pool instead of overfilling it", () => {
    const hurt = applyPlayerDamage(initialPlayerHealth(10), 1, 1000).health;
    const healed = applyPlayerHealing(hurt, 999);
    expect(healed.connected).toBe(true);
    expect(healed.appliedAmount).toBe(1);
    expect(healed.health.hp).toBe(10);
  });

  test("refuses to spend on a full pool, an invalid amount, or a defeated player", () => {
    // `connected: false` is what stops a held key from emptying the bag into an unhurt character.
    const full = initialPlayerHealth(10);
    expect(applyPlayerHealing(full, 4).connected).toBe(false);
    expect(applyPlayerHealing(full, 4).health).toBe(full);

    const hurt = applyPlayerDamage(full, 5, 1000).health;
    for (const amount of [0, -3, Number.NaN, Number.POSITIVE_INFINITY]) {
      const rejected = applyPlayerHealing(hurt, amount);
      expect(rejected.connected).toBe(false);
      expect(rejected.health).toBe(hurt);
    }

    const defeated = applyPlayerDamage(initialPlayerHealth(1), 1, 1000).health;
    expect(defeated.defeated).toBe(true);
    const attempt = applyPlayerHealing(defeated, 4);
    expect(attempt.connected).toBe(false);
    expect(attempt.health.defeated).toBe(true);
  });
});

describe("critical hits", () => {
  test("every named profile has a rate, and none is accidentally identical", () => {
    const seen = new Set<string>();
    for (const profile of CRITICAL_PROFILE_NAMES) {
      const rule = criticalRule(profile);
      expect(rule.chance).toBeGreaterThanOrEqual(0);
      expect(rule.chance).toBeLessThanOrEqual(1);
      expect(rule.multiplier).toBeGreaterThanOrEqual(1);
      seen.add(JSON.stringify(rule));
    }
    expect(seen.size).toBe(CRITICAL_PROFILE_NAMES.length);
    expect(() => criticalRule("savage_v1" as "rare_v1")).toThrow(/unknown critical profile/);
  });

  test("`none` never rolls a critical, whatever the seed", () => {
    for (let seed = 0; seed < 200; seed += 1) {
      expect(resolveCriticalDamage(3, "none", seed).critical).toBe(false);
    }
  });

  test("the same seed always rolls the same result", () => {
    // Determinism is not a nicety here: `Math.random` would make every replay of a run diverge at
    // the first swing, and the deterministic transcript is what makes the runtime verifiable.
    for (const seed of [1, 7, 4242, 999_983]) {
      const first = resolveCriticalDamage(2, "standard_v1", seed);
      const second = resolveCriticalDamage(2, "standard_v1", seed);
      expect(first).toEqual(second);
    }
  });

  test("observed rate tracks the profile across a wide seed sweep", () => {
    const sample = 20_000;
    for (const profile of ["rare_v1", "standard_v1", "frequent_v1"] as const) {
      let hits = 0;
      for (let seed = 1; seed <= sample; seed += 1) {
        if (resolveCriticalDamage(1, profile, seed).critical) hits += 1;
      }
      const observed = hits / sample;
      expect(Math.abs(observed - criticalRule(profile).chance)).toBeLessThan(0.02);
    }
  });

  test("a critical multiplies the blow and never rounds it away", () => {
    const crit = Array.from({ length: 400 }, (_, seed) =>
      resolveCriticalDamage(2, "standard_v1", seed),
    ).find((outcome) => outcome.critical);
    expect(crit).toBeDefined();
    expect(crit?.amount).toBe(4);
    // A multiplier below one point of damage still lands for one, never zero.
    const tiny = Array.from({ length: 400 }, (_, seed) =>
      resolveCriticalDamage(0.5, "frequent_v1", seed),
    ).find((outcome) => outcome.critical);
    expect(tiny?.amount).toBeGreaterThanOrEqual(1);
  });

  test("the flag rides the resolution both sides of a fight read", () => {
    const outgoing = resolveDamage(9, 4, false, true);
    expect(outgoing.critical).toBe(true);
    const incoming = applyPlayerDamage(initialPlayerHealth(10), 4, 1000, true);
    expect(incoming.critical).toBe(true);
    // A blow that never landed is not a critical, whatever the roll said.
    expect(resolveDamage(0, 4, true, true).critical).toBe(false);
    expect(applyPlayerDamage(initialPlayerHealth(10), 0, 1000, true).critical).toBe(false);
  });
});

describe("level growth", () => {
  test("raises the ceiling and fills it", () => {
    // A level that only widened the bar arrives as an empty promise mid-fight.
    const hurt = applyPlayerDamage(initialPlayerHealth(10), 7, 1000).health;
    expect(hurt.hp).toBe(3);
    const grown = grownPlayerHealth(hurt, 12);
    expect(grown.hp).toBe(12);
    expect(grown.maxHp).toBe(12);
    expect(grown.invulnerableUntilMs).toBe(hurt.invulnerableUntilMs);
  });

  test("never lowers a ceiling and rejects nonsense maxima", () => {
    const health = initialPlayerHealth(10);
    expect(grownPlayerHealth(health, 10)).toBe(health);
    expect(grownPlayerHealth(health, 4)).toBe(health);
    expect(() => grownPlayerHealth(health, 0)).toThrow(RangeError);
    expect(() => grownPlayerHealth(health, 2.5)).toThrow(RangeError);
  });
});
