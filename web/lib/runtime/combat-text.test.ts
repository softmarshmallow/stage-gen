import { describe, expect, test } from "bun:test";
import type Phaser from "phaser";
import { resolveDamage } from "./combat";
import { COMBAT_TEXT_FONT_FAMILY } from "./combat-font";
import {
  COMBAT_TEXT_DEPTH,
  COMBAT_TEXT_FADE_START_MS,
  COMBAT_TEXT_FONT_STACK,
  COMBAT_TEXT_INCOMING_COLOR,
  COMBAT_TEXT_LIFETIME_MS,
  COMBAT_TEXT_OUTGOING_COLOR,
  COMBAT_TEXT_PUNCH_PEAK_MS,
  COMBAT_TEXT_PUNCH_SETTLE_MS,
  COMBAT_TEXT_RISE_MS,
  COMBAT_TEXT_RISE_PX,
  COMBAT_TEXT_SHAKE_PX,
  CombatTextSystem,
  combatTextVisualStyle,
  formatCombatTextAmount,
  sampleCombatText,
  type CombatTextMotion,
} from "./combat-text";
import { SCENE_CONTENT_DEPTH } from "./layers";

const MOTION: CombatTextMotion = Object.freeze({
  // Multiple of the shake pattern length, so frame zero starts at the authored anchor.
  eventId: 6,
  startedAtMs: 1_000,
  anchorX: 320,
  anchorY: 180,
  reducedMotion: false,
});

describe("floating combat text presentation contract", () => {
  test("uses the fixed outgoing/incoming hierarchy and actor-HUD depth", () => {
    const outgoing = combatTextVisualStyle("outgoing");
    const incoming = combatTextVisualStyle("incoming");

    expect(outgoing.color).toBe(COMBAT_TEXT_OUTGOING_COLOR);
    expect(outgoing.color).toBe("#FFF0A6");
    expect(incoming.color).toBe(COMBAT_TEXT_INCOMING_COLOR);
    expect(incoming.color).toBe("#FF6B6B");
    expect(incoming.fontSizePx).toBeGreaterThan(outgoing.fontSizePx);
    expect(outgoing.outlineThicknessPx).toBeGreaterThanOrEqual(4);
    expect(outgoing.fontFamily).toBe(COMBAT_TEXT_FONT_STACK);
    expect(COMBAT_TEXT_FONT_STACK).toContain(COMBAT_TEXT_FONT_FAMILY);
    expect(COMBAT_TEXT_FONT_STACK).toContain("Arial Rounded MT Bold");
    expect(COMBAT_TEXT_DEPTH).toBeGreaterThan(SCENE_CONTENT_DEPTH.actorHud);
    expect(COMBAT_TEXT_DEPTH).toBeLessThan(SCENE_CONTENT_DEPTH.hud);
  });

  test("formats the applied HP delta without locale or wall-clock state", () => {
    expect(formatCombatTextAmount(2)).toBe("2");
    expect(formatCombatTextAmount(1.25)).toBe("1.25");
    expect(formatCombatTextAmount(1.234)).toBe("1.23");
    expect(formatCombatTextAmount(0)).toBe("");
    expect(formatCombatTextAmount(Number.NaN)).toBe("");
  });
});

describe("fixed-clock floating combat text motion", () => {
  test("punches, settles, rises, fades, and completes at exact boundaries", () => {
    const start = sampleCombatText(MOTION, MOTION.startedAtMs);
    expect(start).toEqual({
      x: MOTION.anchorX,
      y: MOTION.anchorY,
      alpha: 1,
      scale: 0.78,
      complete: false,
    });

    const peak = sampleCombatText(
      MOTION,
      MOTION.startedAtMs + COMBAT_TEXT_PUNCH_PEAK_MS,
    );
    expect(peak.scale).toBeCloseTo(1.14, 12);

    const settled = sampleCombatText(
      MOTION,
      MOTION.startedAtMs + COMBAT_TEXT_PUNCH_SETTLE_MS,
    );
    expect(settled.scale).toBe(1);

    const risen = sampleCombatText(
      MOTION,
      MOTION.startedAtMs + COMBAT_TEXT_RISE_MS,
    );
    expect(risen.y).toBe(MOTION.anchorY - COMBAT_TEXT_RISE_PX);

    const fadeStart = sampleCombatText(
      MOTION,
      MOTION.startedAtMs + COMBAT_TEXT_FADE_START_MS,
    );
    expect(fadeStart.alpha).toBe(1);
    const halfwayThroughFade = sampleCombatText(MOTION, MOTION.startedAtMs + 500);
    expect(halfwayThroughFade.alpha).toBeCloseTo(0.5, 12);

    const complete = sampleCombatText(
      MOTION,
      MOTION.startedAtMs + COMBAT_TEXT_LIFETIME_MS,
    );
    expect(complete.alpha).toBe(0);
    expect(complete.scale).toBe(1);
    expect(complete.complete).toBe(true);
  });

  test("is deterministic and keeps micro-shake inside the glyph-only bound", () => {
    for (let elapsedMs = 0; elapsedMs <= COMBAT_TEXT_LIFETIME_MS; elapsedMs += 6) {
      const nowMs = MOTION.startedAtMs + elapsedMs;
      const first = sampleCombatText({ ...MOTION, eventId: 11 }, nowMs);
      const second = sampleCombatText({ ...MOTION, eventId: 11 }, nowMs);
      expect(second).toEqual(first);
      expect(Math.abs(first.x - MOTION.anchorX)).toBeLessThanOrEqual(
        COMBAT_TEXT_SHAKE_PX,
      );
    }
  });

  test("reduced motion is opacity-only for the full readable lifetime", () => {
    const reduced = Object.freeze({ ...MOTION, reducedMotion: true });
    for (const elapsedMs of [0, 72, 96, 160, 360, 500, 639]) {
      const sample = sampleCombatText(reduced, reduced.startedAtMs + elapsedMs);
      expect(sample.x).toBe(reduced.anchorX);
      expect(sample.y).toBe(reduced.anchorY);
      expect(sample.scale).toBe(1);
      expect(sample.complete).toBe(false);
    }
    expect(
      sampleCombatText(reduced, reduced.startedAtMs + COMBAT_TEXT_LIFETIME_MS),
    ).toEqual({
      x: reduced.anchorX,
      y: reduced.anchorY,
      alpha: 0,
      scale: 1,
      complete: true,
    });
  });

  test("timestamps before the event clamp to its initial sample", () => {
    expect(sampleCombatText(MOTION, 0)).toEqual(
      sampleCombatText(MOTION, MOTION.startedAtMs),
    );
  });
});

class FakeText {
  text = "";
  x = 0;
  y = 0;
  alpha = 1;
  scale = 1;
  visible = true;
  active = true;
  destroyed = false;
  style: unknown;

  constructor(text: string, style: unknown) {
    this.text = text;
    this.style = style;
  }

  setText(text: string): this {
    this.text = text;
    return this;
  }

  setStyle(style: unknown): this {
    this.style = style;
    return this;
  }

  setOrigin(_x: number, _y: number): this {
    return this;
  }

  setScrollFactor(_value: number): this {
    return this;
  }

  setDepth(_value: number): this {
    return this;
  }

  setActive(active: boolean): this {
    this.active = active;
    return this;
  }

  setVisible(visible: boolean): this {
    this.visible = visible;
    return this;
  }

  setPosition(x: number, y: number): this {
    this.x = x;
    this.y = y;
    return this;
  }

  setAlpha(alpha: number): this {
    this.alpha = alpha;
    return this;
  }

  setScale(scale: number): this {
    this.scale = scale;
    return this;
  }

  destroy(): void {
    this.destroyed = true;
    this.active = false;
    this.visible = false;
  }
}

function fakeScene(): Readonly<{
  scene: Phaser.Scene;
  glyphs: FakeText[];
}> {
  const glyphs: FakeText[] = [];
  const scene = {
    add: {
      text(_x: number, _y: number, text: string, style: unknown): FakeText {
        const glyph = new FakeText(text, style);
        glyphs.push(glyph);
        return glyph;
      },
    },
  } as unknown as Phaser.Scene;
  return Object.freeze({ scene, glyphs });
}

describe("bounded CombatTextSystem lifecycle", () => {
  const hit = resolveDamage(10, 1);

  test("shows only connected applied damage and snapshots the effective amount", () => {
    const fake = fakeScene();
    const system = new CombatTextSystem({ scene: fake.scene });

    expect(
      system.showDamage({
        resolution: resolveDamage(6, 0),
        direction: "outgoing",
        x: 100,
        y: 200,
        nowMs: 0,
      }),
    ).toBeNull();
    expect(fake.glyphs).toHaveLength(0);

    const overkill = resolveDamage(2, 99);
    expect(
      system.showDamage({
        resolution: overkill,
        direction: "outgoing",
        x: 100,
        y: 200,
        nowMs: 1_000,
      }),
    ).toBe(1);
    expect(system.snapshot()).toMatchObject({
      enabled: true,
      reducedMotion: false,
      disposed: false,
      activeCount: 1,
      pooledCount: 0,
      entries: [{ eventId: 1, amount: 2, text: "2", direction: "outgoing" }],
    });
  });

  test("recycles the oldest glyph at the active cap and expires from simulation time", () => {
    const fake = fakeScene();
    const system = new CombatTextSystem({ scene: fake.scene, maxActive: 2 });
    for (let index = 0; index < 3; index += 1) {
      system.showDamage({
        resolution: hit,
        direction: index % 2 === 0 ? "outgoing" : "incoming",
        x: 20 + index,
        y: 40,
        nowMs: index,
      });
    }

    expect(fake.glyphs).toHaveLength(2);
    expect(system.snapshot().entries.map((entry) => entry.eventId)).toEqual([2, 3]);

    system.update(COMBAT_TEXT_LIFETIME_MS + 2);
    expect(system.snapshot()).toMatchObject({ activeCount: 0, pooledCount: 2 });

    system.showDamage({
      resolution: hit,
      direction: "outgoing",
      x: 20,
      y: 40,
      nowMs: 1_000,
    });
    expect(fake.glyphs).toHaveLength(2);
    expect(system.snapshot()).toMatchObject({ activeCount: 1, pooledCount: 1 });
  });

  test("can switch active glyphs to reduced motion and clear when disabled", () => {
    const fake = fakeScene();
    const system = new CombatTextSystem({ scene: fake.scene });
    system.showDamage({
      resolution: hit,
      direction: "incoming",
      x: 70,
      y: 90,
      nowMs: 0,
    });

    system.setReducedMotion(true);
    system.update(100);
    expect(system.snapshot()).toMatchObject({
      reducedMotion: true,
      entries: [{ x: 70, y: 90, scale: 1 }],
    });

    system.setEnabled(false);
    expect(system.snapshot()).toMatchObject({
      enabled: false,
      activeCount: 0,
      pooledCount: 1,
    });
    expect(
      system.showDamage({
        resolution: hit,
        direction: "incoming",
        x: 70,
        y: 90,
        nowMs: 101,
      }),
    ).toBeNull();
  });

  test("disposes pooled and active Phaser glyphs exactly once", () => {
    const fake = fakeScene();
    const system = new CombatTextSystem({ scene: fake.scene, maxActive: 2 });
    system.showDamage({
      resolution: hit,
      direction: "outgoing",
      x: 0,
      y: 0,
      nowMs: 0,
    });
    system.dispose();
    system.dispose();

    expect(fake.glyphs).toHaveLength(1);
    expect(fake.glyphs[0].destroyed).toBe(true);
    expect(system.snapshot()).toEqual({
      enabled: false,
      reducedMotion: false,
      disposed: true,
      activeCount: 0,
      pooledCount: 0,
      entries: [],
    });
  });

  test("rejects an invalid active cap", () => {
    const fake = fakeScene();
    expect(() => new CombatTextSystem({ scene: fake.scene, maxActive: 0 })).toThrow(
      "combat text maxActive",
    );
    expect(
      () => new CombatTextSystem({ scene: fake.scene, maxActive: 129 }),
    ).toThrow("combat text maxActive");
  });
});
