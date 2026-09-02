import { describe, expect, test } from "bun:test";
import type Phaser from "phaser";
import { resolveDamage } from "./combat";
import { COMBAT_FONT_FACES, DAMAGE_NUMBER_FONT_FAMILY } from "./combat-font";
import {
  COMBAT_TEXT_DEPTH,
  COMBAT_TEXT_FILL_DEPTH,
  COMBAT_TEXT_GLYPH_ARC_SHARE,
  COMBAT_TEXT_GLYPH_ARRIVAL_SCALE,
  COMBAT_TEXT_GLYPH_DROP_SHARE,
  COMBAT_TEXT_GLYPH_JITTER_SHARE,
  COMBAT_TEXT_GLYPH_SETTLE_MS,
  COMBAT_TEXT_GLYPH_SIZE_VARIANCE,
  COMBAT_TEXT_GLYPH_STAGGER_MS,
  COMBAT_TEXT_GLYPH_TRACKING_SHARE,
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
  COMBAT_TEXT_STACK_JITTER_SHARE,
  COMBAT_TEXT_STACK_RADIUS_PX,
  COMBAT_TEXT_STACK_STEP_SHARE,
  COMBAT_TEXT_STACK_WINDOW_MS,
  CombatTextSystem,
  combatTextGlyphLayout,
  combatTextNominalGlyphAdvance,
  combatTextStackOffset,
  combatTextVisualStyle,
  formatCombatTextAmount,
  sampleCombatText,
  sampleCombatTextGlyph,
  type CombatTextMotion,
} from "./combat-text";
import { SCENE_CONTENT_DEPTH } from "./depths";

/** WCAG relative luminance, so a palette claim is a measurement rather than an opinion. */
function relativeLuminance(hex: string): number {
  const channel = (value: number) => {
    const share = value / 255;
    return share <= 0.03928 ? share / 12.92 : ((share + 0.055) / 1.055) ** 2.4;
  };
  const red = channel(Number.parseInt(hex.slice(1, 3), 16));
  const green = channel(Number.parseInt(hex.slice(3, 5), 16));
  const blue = channel(Number.parseInt(hex.slice(5, 7), 16));
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

function contrastRatio(left: string, right: string): number {
  const a = relativeLuminance(left);
  const b = relativeLuminance(right);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

const MOTION: CombatTextMotion = Object.freeze({
  // Multiple of the shake pattern length, so frame zero starts at the authored anchor.
  eventId: 6,
  startedAtMs: 1_000,
  anchorX: 320,
  anchorY: 180,
  reducedMotion: false,
  critical: false,
  glyphSizePx: 100,
});

/** The size the fixture run is set at, so a share reads as the pixels it becomes. */
const GLYPH_SIZE = MOTION.glyphSizePx;

describe("floating combat text presentation contract", () => {
  test("sets a number large enough to be the feedback, measured against the character", () => {
    // The scene draws the player 154px tall (`PLAYER_HEIGHT` in prepared-scene.ts). In the arcade
    // reference a damage digit stands about four fifths of that, and the size *is* the feedback:
    // a tidy number beside the character reads as a footnote however well it is drawn. The floor
    // is well under where the sizes actually sit, because how far below the reference to land is
    // a judgement about screen crowding that will be made again; what it forbids is the return to
    // a fifth of the character, which is not a smaller number but a different kind of thing.
    const playerHeightPx = 154;
    const capShare = 0.72; // cap height of a display face, as a share of its font size
    for (const direction of ["outgoing", "incoming"] as const) {
      const cap = combatTextVisualStyle(direction).fontSizePx * capShare;
      expect(cap / playerHeightPx).toBeGreaterThan(0.25);
      expect(combatTextVisualStyle(direction, true).fontSizePx).toBeGreaterThan(
        combatTextVisualStyle(direction).fontSizePx,
      );
    }
  });

  test("the core is graded from a lit top into a deep foot", () => {
    for (const critical of [false, true]) {
      for (const direction of ["outgoing", "incoming"] as const) {
        const style = combatTextVisualStyle(direction, critical);
        expect(relativeLuminance(style.highlightColor)).toBeGreaterThanOrEqual(
          relativeLuminance(style.color),
        );
        expect(relativeLuminance(style.shadowColor)).toBeLessThan(
          relativeLuminance(style.color),
        );
        // The lit top is the one band that comes near the ring, and it is allowed to: the dark
        // edge is immediately outside the ring, so the three-band sandwich still holds there.
        expect(
          contrastRatio(style.highlightColor, style.innerOutlineColor),
        ).toBeGreaterThanOrEqual(1.5);
      }
    }
  });

  test("both edges are a share of the size, so a bigger number is not a fatter one", () => {
    const normal = combatTextVisualStyle("outgoing");
    const critical = combatTextVisualStyle("outgoing", true);
    const ratio = critical.fontSizePx / normal.fontSizePx;

    // Within a pixel, because a canvas stroke is a whole number of them and two roundings at
    // these magnitudes are worth more than the proportion they are rounding.
    expect(
      Math.abs(critical.innerOutlineThicknessPx - normal.innerOutlineThicknessPx * ratio),
    ).toBeLessThanOrEqual(1);
    expect(
      Math.abs(critical.outerOutlineThicknessPx - normal.outerOutlineThicknessPx * ratio),
    ).toBeLessThanOrEqual(1);
  });

  test("sets its numbers at a weight the committed face actually has", () => {
    // A synthesized bold is the browser's own thickening, which would move glyph metrics under
    // deterministic captures. Every committed face is loaded at the weight it is set at.
    for (const face of COMBAT_FONT_FACES) {
      expect(String(face.loadedWeight)).toMatch(/^\d+$/);
      expect(face.weight).toContain(String(face.loadedWeight));
    }
  });

  test("uses the fixed outgoing/incoming hierarchy and actor-HUD depth", () => {
    const outgoing = combatTextVisualStyle("outgoing");
    const incoming = combatTextVisualStyle("incoming");

    expect(outgoing.color).toBe(COMBAT_TEXT_OUTGOING_COLOR);
    expect(incoming.color).toBe(COMBAT_TEXT_INCOMING_COLOR);
    expect(outgoing.color).not.toBe(incoming.color);
    expect(incoming.fontSizePx).toBeGreaterThan(outgoing.fontSizePx);
    expect(outgoing.fontFamily).toBe(COMBAT_TEXT_FONT_STACK);
    expect(COMBAT_TEXT_FONT_STACK).toContain(DAMAGE_NUMBER_FONT_FAMILY);
    expect(COMBAT_TEXT_FONT_STACK).toContain("Arial Rounded MT Bold");
    // The face the numbers are set in has to be one the demo actually commits to and loads,
    // or the stack is a fallback chain with nothing at the head of it.
    expect(COMBAT_FONT_FACES.map((face) => face.family)).toContain(DAMAGE_NUMBER_FONT_FAMILY);
    expect(COMBAT_TEXT_DEPTH).toBeGreaterThan(SCENE_CONTENT_DEPTH.actorHud);
    expect(COMBAT_TEXT_DEPTH).toBeLessThan(SCENE_CONTENT_DEPTH.hud);
  });

  test("every style steps hard from core to ring to edge", () => {
    // The rule the palette actually has to satisfy. A number is legible over art it has never
    // seen because its own three bands step away from each other, not because any one of them
    // happens to contrast with what is behind it - and a gold core inside a white ring, which is
    // what this was, fails that at 1.7 while looking perfectly fine on a dark test card.
    for (const critical of [false, true]) {
      for (const direction of ["outgoing", "incoming"] as const) {
        const style = combatTextVisualStyle(direction, critical);
        expect(contrastRatio(style.color, style.innerOutlineColor)).toBeGreaterThanOrEqual(3);
        expect(
          contrastRatio(style.innerOutlineColor, style.outerOutlineColor),
        ).toBeGreaterThanOrEqual(4);
      }
    }
  });

  test("a critical is its own colour inverted, not a second palette", () => {
    for (const direction of ["outgoing", "incoming"] as const) {
      const normal = combatTextVisualStyle(direction, false);
      const critical = combatTextVisualStyle(direction, true);

      expect(critical.innerOutlineColor).toBe(normal.color);
      expect(contrastRatio(critical.color, normal.color)).toBeGreaterThanOrEqual(3);
      expect(critical.fontSizePx).toBeGreaterThan(normal.fontSizePx);
    }
  });

  test("every style carries a light ring inside a heavier dark edge", () => {
    for (const critical of [false, true]) {
      for (const direction of ["outgoing", "incoming"] as const) {
        const style = combatTextVisualStyle(direction, critical);
        expect(style.innerOutlineThicknessPx).toBeGreaterThanOrEqual(4);
        // The dark edge has to be the thicker of the two or it never shows behind the ring, and
        // it is what fattens the silhouette, which is most of the perceived weight.
        expect(style.outerOutlineThicknessPx).toBeGreaterThan(style.innerOutlineThicknessPx);
        expect(style.innerOutlineColor).not.toBe(style.color);
        expect(style.outerOutlineColor).not.toBe(style.innerOutlineColor);
      }
    }
  });

  test("the coloured face of every number is drawn over every dark edge", () => {
    expect(COMBAT_TEXT_FILL_DEPTH).toBeGreaterThan(COMBAT_TEXT_DEPTH);
    expect(COMBAT_TEXT_FILL_DEPTH).toBeLessThan(SCENE_CONTENT_DEPTH.hud);
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

describe("stacking numbers that land together", () => {
  const peer = (baseX: number, baseY: number, startedAtMs: number) => ({ baseX, baseY, startedAtMs });

  test("a lone number is not offset at all", () => {
    expect(
      combatTextStackOffset([], {
        eventId: 1,
        x: 100,
        y: 50,
        nowMs: 0,
        glyphSizePx: GLYPH_SIZE,
      }),
    ).toEqual({ x: 0, y: 0 });
  });

  test("each live peer at nearly the same place lifts the next number by one step", () => {
    const peers = [peer(100, 50, 0), peer(104, 52, 45), peer(97, 48, 90)];
    const offset = combatTextStackOffset(peers, { eventId: 9, x: 100, y: 50, nowMs: 135, glyphSizePx: GLYPH_SIZE });
    expect(offset.y).toBe(-GLYPH_SIZE * COMBAT_TEXT_STACK_STEP_SHARE * 3);
    expect(Math.abs(offset.x)).toBeLessThanOrEqual(
      GLYPH_SIZE * COMBAT_TEXT_STACK_JITTER_SHARE,
    );
  });

  test("peers outside the window or the radius do not count", () => {
    const stale = peer(100, 50, 0);
    const far = peer(100 + COMBAT_TEXT_STACK_RADIUS_PX + 1, 50, 100);
    const high = peer(100, 50 - COMBAT_TEXT_STACK_RADIUS_PX - 1, 100);
    const nowMs = COMBAT_TEXT_STACK_WINDOW_MS + 1;
    expect(
      combatTextStackOffset([stale, far, high], {
        eventId: 2,
        x: 100,
        y: 50,
        nowMs,
        glyphSizePx: GLYPH_SIZE,
      }),
    ).toEqual({ x: 0, y: 0 });
  });

  test("the jitter is a function of the event id alone", () => {
    const peers = [peer(0, 0, 0)];
    const at = () =>
      combatTextStackOffset(peers, {
        eventId: 4,
        x: 0,
        y: 0,
        nowMs: 1,
        glyphSizePx: GLYPH_SIZE,
      });
    const a = at();
    const b = at();
    expect(b).toEqual(a);
  });

  test("the system stacks against unstacked anchors, so a column does not drift", () => {
    const fake = fakeScene();
    const system = new CombatTextSystem({ scene: fake.scene });
    const hit = resolveDamage(100, 1);
    for (let index = 0; index < 3; index += 1) {
      system.showDamage({ resolution: hit, direction: "outgoing", x: 300, y: 200, nowMs: index * 45 });
    }
    const step =
      combatTextVisualStyle("outgoing").fontSizePx * COMBAT_TEXT_STACK_STEP_SHARE;
    const entries = system.snapshot().entries;
    expect(entries.map((entry) => entry.anchorY)).toEqual([200, 200 - step, 200 - step * 2]);
    for (const entry of entries) {
      // The bound is a share of the size, so it is the same float arithmetic the offset did,
      // reached by a different route; compare at the bound rather than inside it.
      expect(Math.abs(entry.anchorX - 300)).toBeLessThanOrEqual(
        combatTextVisualStyle("outgoing").fontSizePx * COMBAT_TEXT_STACK_JITTER_SHARE + 1e-9,
      );
    }
  });
});

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

    // Two objects per character - the dark edge and the coloured face - and these are all
    // one-digit numbers, so the cap of two numbers holds four.
    expect(fake.glyphs).toHaveLength(4);
    expect(system.snapshot().entries.map((entry) => entry.eventId)).toEqual([2, 3]);

    system.update(COMBAT_TEXT_LIFETIME_MS + 2);
    expect(system.snapshot()).toMatchObject({ activeCount: 0, pooledCount: 4 });

    system.showDamage({
      resolution: hit,
      direction: "outgoing",
      x: 20,
      y: 40,
      nowMs: 1_000,
    });
    expect(fake.glyphs).toHaveLength(4);
    expect(system.snapshot()).toMatchObject({ activeCount: 1, pooledCount: 2 });
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
      pooledCount: 2,
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

    expect(fake.glyphs).toHaveLength(2);
    expect(fake.glyphs.every((glyph) => glyph.destroyed)).toBe(true);
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

describe("a number drawn one digit at a time", () => {
  const run = (index: number, count: number, centerOffsetX = 0) => ({
    index,
    count,
    centerOffsetX,
  });

  test("the row is centered on the run, whatever it is made of", () => {
    const even = combatTextGlyphLayout([20, 20], 0);
    expect(even).toEqual([-10, 10]);

    const odd = combatTextGlyphLayout([20, 20, 20], 0);
    expect(odd).toEqual([-20, 0, 20]);

    expect(combatTextGlyphLayout([20], 0)).toEqual([0]);
    expect(combatTextGlyphLayout([], 0)).toEqual([]);
  });

  test("tracking packs the row without moving its center", () => {
    const packed = combatTextGlyphLayout([20, 20, 20], GLYPH_SIZE * COMBAT_TEXT_GLYPH_TRACKING_SHARE);

    expect(packed[1]).toBe(0);
    expect(packed[2]! - packed[1]!).toBe(20 + GLYPH_SIZE * COMBAT_TEXT_GLYPH_TRACKING_SHARE);
    expect(packed[0]! + packed[2]!).toBeCloseTo(0, 10);
  });

  test("a mark is laid out narrower than a digit when nothing measured it", () => {
    expect(combatTextNominalGlyphAdvance(32, "!")).toBeLessThan(
      combatTextNominalGlyphAdvance(32, "7"),
    );
  });

  test("digits arrive left to right, each on its own beat", () => {
    const count = 4;
    // The leading digit is there on the frame the blow lands; the rest are still on their way.
    expect(sampleCombatTextGlyph(MOTION, run(0, count), MOTION.startedAtMs).alpha).toBe(1);
    expect(sampleCombatTextGlyph(MOTION, run(1, count), MOTION.startedAtMs).alpha).toBe(0);

    const arrivals = Array.from({ length: count }, (_, index) =>
      sampleCombatTextGlyph(
        MOTION,
        run(index, count),
        MOTION.startedAtMs + COMBAT_TEXT_GLYPH_STAGGER_MS * 2 + 1,
      ).alpha,
    );

    expect(arrivals).toEqual([1, 1, 1, 0]);
  });

  test("a digit arrives oversized and high, then settles onto its resting place", () => {
    const arriving = sampleCombatTextGlyph(
      MOTION,
      run(1, 4),
      MOTION.startedAtMs + COMBAT_TEXT_GLYPH_STAGGER_MS + 1,
    );
    const settled = sampleCombatTextGlyph(
      MOTION,
      run(1, 4),
      MOTION.startedAtMs + COMBAT_TEXT_GLYPH_STAGGER_MS + COMBAT_TEXT_GLYPH_SETTLE_MS,
    );

    expect(arriving.scale).toBeGreaterThan(settled.scale);
    expect(arriving.scale).toBeLessThanOrEqual(
      COMBAT_TEXT_GLYPH_ARRIVAL_SCALE * (1 + COMBAT_TEXT_GLYPH_SIZE_VARIANCE),
    );
    // It comes to rest at the run's own size, give or take its own share of the variance.
    expect(settled.scale).toBeGreaterThanOrEqual(1 - COMBAT_TEXT_GLYPH_SIZE_VARIANCE);
    expect(settled.scale).toBeLessThanOrEqual(1 + COMBAT_TEXT_GLYPH_SIZE_VARIANCE);
    // It falls into place: the arriving sample sits a drop above where it comes to rest.
    expect(settled.offsetY - arriving.offsetY).toBeGreaterThan(0);
    expect(settled.offsetY - arriving.offsetY).toBeLessThanOrEqual(GLYPH_SIZE * COMBAT_TEXT_GLYPH_DROP_SHARE);
  });

  test("the row rests on an arc plus its own jitter, and never on one flat line", () => {
    const count = 6;
    const settleAt = (index: number) =>
      sampleCombatTextGlyph(
        MOTION,
        run(index, count),
        MOTION.startedAtMs + COMBAT_TEXT_GLYPH_STAGGER_MS * count + COMBAT_TEXT_GLYPH_SETTLE_MS,
      );
    const offsets = Array.from({ length: count }, (_, index) => settleAt(index).offsetY);

    expect(new Set(offsets).size).toBe(count);
    for (const offset of offsets) {
      expect(Math.abs(offset)).toBeLessThanOrEqual(
        GLYPH_SIZE * COMBAT_TEXT_GLYPH_ARC_SHARE + GLYPH_SIZE * COMBAT_TEXT_GLYPH_JITTER_SHARE,
      );
    }
    // The arc is a hump: the middle of the row sits above both of its ends.
    expect(Math.min(...offsets)).toBeLessThan(Math.min(offsets[0]!, offsets[count - 1]!));
  });

  test("the same blow displaces its digits the same way twice, and a different one differs", () => {
    const other: CombatTextMotion = { ...MOTION, eventId: MOTION.eventId + 1 };
    const at = (motion: CombatTextMotion, index: number) =>
      sampleCombatTextGlyph(motion, run(index, 5), MOTION.startedAtMs + 400);

    expect(at(MOTION, 2)).toEqual(at(MOTION, 2));
    expect(at(other, 2)).not.toEqual(at(MOTION, 2));
  });

  test("reduced motion keeps the row and drops the theatre", () => {
    const reduced: CombatTextMotion = { ...MOTION, reducedMotion: true };
    const samples = Array.from({ length: 3 }, (_, index) =>
      sampleCombatTextGlyph(reduced, run(index, 3, index * 20 - 20), MOTION.startedAtMs),
    );

    expect(samples.map((sample) => sample.offsetY)).toEqual([0, 0, 0]);
    expect(samples.map((sample) => sample.scale)).toEqual([1, 1, 1]);
    expect(samples.map((sample) => sample.alpha)).toEqual([1, 1, 1]);
    expect(samples.map((sample) => sample.offsetX)).toEqual([-20, 0, 20]);
  });

  test("a glyph outside its own run is refused", () => {
    expect(() => sampleCombatTextGlyph(MOTION, run(3, 3), 0)).toThrow("inside its run");
    expect(() => sampleCombatTextGlyph(MOTION, run(0, 0), 0)).toThrow("inside its run");
  });
});

describe("the glyph pool a multi-digit number draws from", () => {
  test("one number takes one drawn glyph per character", () => {
    const fake = fakeScene();
    const system = new CombatTextSystem({ scene: fake.scene });
    system.showDamage({
      resolution: resolveDamage(1_000, 123),
      direction: "outgoing",
      x: 100,
      y: 100,
      nowMs: 0,
    });

    // Each character is drawn twice: its dark edge, then its coloured face over it.
    expect(fake.glyphs.map((glyph) => glyph.text)).toEqual(["1", "1", "2", "2", "3", "3"]);
    const entry = system.snapshot().entries[0]!;
    expect(entry.glyphs.map((glyph) => glyph.character)).toEqual(["1", "2", "3"]);
    // Laid out around the anchor rather than stacked on it.
    expect(entry.glyphs[0]!.x).toBeLessThan(entry.glyphs[2]!.x);
  });

  test("a recycled glyph already holds the character it is reused for", () => {
    const fake = fakeScene();
    const system = new CombatTextSystem({ scene: fake.scene });
    system.showDamage({
      resolution: resolveDamage(1_000, 12),
      direction: "outgoing",
      x: 100,
      y: 100,
      nowMs: 0,
    });
    system.update(COMBAT_TEXT_LIFETIME_MS + 1);
    expect(system.snapshot()).toMatchObject({ activeCount: 0, pooledCount: 4 });

    // The reversed number needs the same two characters, so nothing new is drawn and no pooled
    // glyph has to be re-rendered into a different digit.
    system.showDamage({
      resolution: resolveDamage(1_000, 21),
      direction: "outgoing",
      x: 100,
      y: 100,
      nowMs: 2_000,
    });

    expect(fake.glyphs).toHaveLength(4);
    expect(system.snapshot()).toMatchObject({ activeCount: 1, pooledCount: 0 });
    expect(system.snapshot().entries[0]!.glyphs.map((glyph) => glyph.character)).toEqual([
      "2",
      "1",
    ]);
  });

  test("a character the pool has never held is drawn once and then kept", () => {
    const fake = fakeScene();
    const system = new CombatTextSystem({ scene: fake.scene });
    const critical = { ...resolveDamage(1_000, 7), critical: true };
    system.showDamage({
      resolution: critical,
      direction: "outgoing",
      x: 100,
      y: 100,
      nowMs: 0,
    });

    expect(fake.glyphs.map((glyph) => glyph.text)).toEqual(["7", "7", "!", "!"]);

    system.update(COMBAT_TEXT_LIFETIME_MS + 1);
    system.showDamage({
      resolution: critical,
      direction: "outgoing",
      x: 100,
      y: 100,
      nowMs: 2_000,
    });

    expect(fake.glyphs).toHaveLength(4);
  });
});

describe("displacement scales with the number it is displacing", () => {
  test("a run set twice as large arcs, jitters and drops twice as far", () => {
    // The whole reason these are shares. A number set two and a half times bigger with pixel
    // displacements reads as a big number sitting perfectly still.
    const at = (glyphSizePx: number) =>
      sampleCombatTextGlyph(
        { ...MOTION, glyphSizePx },
        { index: 1, count: 5, centerOffsetX: 0 },
        MOTION.startedAtMs + 10_000,
      );

    expect(at(200).offsetY).toBeCloseTo(at(100).offsetY * 2, 6);
  });

  test("a stack of numbers opens up with them", () => {
    const peers = [{ baseX: 0, baseY: 0, startedAtMs: 0 }];
    const step = (glyphSizePx: number) =>
      combatTextStackOffset(peers, { eventId: 3, x: 0, y: 0, nowMs: 1, glyphSizePx }).y;

    expect(step(200)).toBeCloseTo(step(100) * 2, 6);
  });
});
