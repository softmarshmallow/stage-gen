import { describe, expect, test } from "bun:test";
import { CONTACT_HURT_PROFILE } from "@/lib/families/vitals";
import { PREPARED_RUNTIME_BLOCKS } from "@/lib/manifest/prepared-manifest";
import {
  contactCanHurt,
  initialPlayerHealth,
  applyPlayerDamage,
  parsePlatformerVitalsBlock,
  PLATFORMER_CONSEQUENCES,
  PLAYER_INVULNERABLE_BLINK_ALPHA,
  PLAYER_INVULNERABLE_MS,
} from "./vitals";

describe("the vitals family in the platformer", () => {
  test("the body is the kernel's gauge under this genre's four names", () => {
    const health = initialPlayerHealth(6);
    expect(health).toEqual({ hp: 6, maxHp: 6, invulnerableUntilMs: 0, defeated: false });
    const hit = applyPlayerDamage(health, 2, 1000);
    expect(hit.connected).toBe(true);
    expect(hit.health).toEqual({
      hp: 4,
      maxHp: 6,
      invulnerableUntilMs: 1000 + PLAYER_INVULNERABLE_MS,
      defeated: false,
    });
    // The same window, the same absorb rule, one implementation.
    expect(applyPlayerDamage(hit.health, 2, 1100).connected).toBe(false);
  });

  test("the window and the blink are the family's profile, not a second copy", () => {
    expect(PLAYER_INVULNERABLE_MS).toBe(CONTACT_HURT_PROFILE.refractoryMs);
    expect(PLAYER_INVULNERABLE_BLINK_ALPHA).toBe(CONTACT_HURT_PROFILE.blinkAlpha);
  });

  test("the int-and-boolean map onto the table in the consumer", () => {
    // The boolean is not a consequence: it decides whether the source is
    // raised at all, which is what the scene's own guard already does.
    expect(PLATFORMER_CONSEQUENCES).toEqual({ contact: "drain_v1" });
    expect(contactCanHurt({ enabled: true, contact_damage: true })).toBe(true);
    expect(contactCanHurt({ enabled: true, contact_damage: false })).toBe(false);
    expect(contactCanHurt({ enabled: false, contact_damage: true })).toBe(false);
  });

  test("the family gates its own block, and the refusal names it", () => {
    expect(parsePlatformerVitalsBlock(PREPARED_RUNTIME_BLOCKS).published).toBe(true);
    expect(() =>
      parsePlatformerVitalsBlock({
        ...PREPARED_RUNTIME_BLOCKS,
        gameplay: "platformer-gameplay-block-v2",
      }),
    ).toThrow('manifest block "gameplay" is published as platformer-gameplay-block-v2');
  });
});
