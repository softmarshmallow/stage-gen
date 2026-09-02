// Floating combat text (FCT) for resolved damage.
//
// Combat decides whether a hit connected and how much HP it actually removed. This module only
// presents that immutable resolution. Motion is sampled from caller-supplied simulation time, so
// normal play and fixed-frame automation use the same path; there are no Phaser tweens, timers, or
// random offsets whose state could drift between captures.

import type Phaser from "phaser";
import type { DamageResolution } from "./combat";
import { DAMAGE_NUMBER_FONT_FAMILY } from "./combat-font";
import { SCENE_CONTENT_DEPTH } from "./depths";

export type CombatTextDirection = "outgoing" | "incoming";

/** Committed display face first, explicit rounded-display fallbacks after it. */
export const COMBAT_TEXT_FONT_STACK =
  `"${DAMAGE_NUMBER_FONT_FAMILY}", "Arial Rounded MT Bold", "Trebuchet MS", sans-serif`;

// An arcade damage number is a sticker: a saturated core, a light ring around it, and a dark
// edge around that. The ring is what separates the number from whatever it is drawn over, and
// the dark edge is what gives the glyph its weight -- it fattens the silhouette by half its own
// thickness on every side, which is most of why these numbers read as heavier than the typeface
// they are set in. The fills are saturated rather than pale for the ring's sake: a near-white
// number with a white ring has no ring at all.
// The hue is a contrast decision, measured against this library's own art rather than picked.
// Bellweather is painted in warm ambers, tans and autumn oranges under a blue sky, and a gold
// number sits at almost exactly the luminance of the stone it is drawn over (0.65 against 0.48)
// as well as of the horizon (0.67). Magenta is the one saturated hue the world does not already
// contain, and at 0.36 it steps hard away from the white ring above it and from every band of
// the art below it. That is the same reason the arcade reference uses it.
export const COMBAT_TEXT_OUTGOING_COLOR = "#FF2E8B";
/** Damage taken stays red, because which side a number belongs to outranks its contrast. */
export const COMBAT_TEXT_INCOMING_COLOR = "#E5241F";
// The core is filled with a vertical gradient rather than one flat colour, which is the other
// half of what makes an arcade number look struck rather than printed: light collects along the
// top of a glyph and the colour deepens into its foot, so a flat digit reads as a decal and a
// graded one reads as an object. The middle stop is the number's identity colour; the top is lit
// and the bottom is where the hue goes deep.
export const COMBAT_TEXT_OUTGOING_HIGHLIGHT_COLOR = "#FF5AA8";
export const COMBAT_TEXT_OUTGOING_SHADOW_COLOR = "#A8064B";
export const COMBAT_TEXT_INCOMING_HIGHLIGHT_COLOR = "#FF5A50";
export const COMBAT_TEXT_INCOMING_SHADOW_COLOR = "#8A0906";
/** A critical is white-hot at the top with the heat pooling into its foot. */
export const COMBAT_TEXT_CRITICAL_HIGHLIGHT_COLOR = "#FFFFFF";
export const COMBAT_TEXT_CRITICAL_OUTGOING_SHADOW_COLOR = "#FF8A1F";
export const COMBAT_TEXT_CRITICAL_INCOMING_SHADOW_COLOR = "#FF5A1F";
// How thick the two rings may be is a property of the *typeface*, not a free choice: a stroke
// eats into a glyph's counters from both sides, so a face with small holes in its 8, 9 and 0
// closes them long before the edge is heavy enough to read as arcade weight. These are the most
// the committed display face carries at these sizes, measured rather than guessed.
/** The light half of the edge, drawn against the fill. */
export const COMBAT_TEXT_INNER_OUTLINE_COLOR = "#FFFFFF";
/** The dark half, drawn behind everything. */
export const COMBAT_TEXT_OUTER_OUTLINE_COLOR = "#24110D";
/**
 * Criticals read as heat: the same hue family pushed to white-hot, not a different palette.
 *
 * With a ring to keep, that becomes an inversion rather than a wash: a normal number is its own
 * colour inside a white ring, and a critical is white inside a ring of that colour. The pair
 * shares a silhouette and a hue, so a critical is unmistakable without being a second palette to
 * learn - and the white core is the brightest thing on the screen, which is what a critical
 * should be.
 */
export const COMBAT_TEXT_CRITICAL_OUTGOING_COLOR = "#FFFFFF";
export const COMBAT_TEXT_CRITICAL_INCOMING_COLOR = "#FFFFFF";
export const COMBAT_TEXT_CRITICAL_OUTGOING_INNER_COLOR = COMBAT_TEXT_OUTGOING_COLOR;
export const COMBAT_TEXT_CRITICAL_INCOMING_INNER_COLOR = COMBAT_TEXT_INCOMING_COLOR;
export const COMBAT_TEXT_CRITICAL_OUTER_OUTLINE_COLOR = "#280414";
/** Size and punch multipliers that make a critical unmistakable at a glance. */
export const COMBAT_TEXT_CRITICAL_SCALE = 1.4;
/**
 * How big a damage number is, measured against the character it is drawn beside.
 *
 * The arcade reference sets a digit at roughly four fifths of the player's height, and a hit for
 * a big number is the largest thing on the screen - that scale *is* the feedback, and a modest
 * number beside a 154px character reads as a footnote no matter how well it is drawn. These sizes
 * put a digit's cap at just under a third of the player: short of the reference on purpose, because
 * the reference is one boss taking one combo and this is a hunting map where a dozen creatures
 * die at once, and at the reference's own scale four simultaneous deaths cover the fight. Every
 * other measurement in this module is a share of this, so moving it moves the whole number.
 */
const OUTGOING_FONT_SIZE_PX = 64;
const INCOMING_FONT_SIZE_PX = 70;
/** The ring, as a share of the font size. Proportional, so a bigger number is not a fatter one. */
const RING_SHARE = 0.055;
/** The dark edge, likewise. It stays about twice the ring, which is what keeps it visible. */
const EDGE_SHARE = 0.115;
export const COMBAT_TEXT_DEPTH = SCENE_CONTENT_DEPTH.actorHud + 10;
/**
 * The fill layer sits one step above every dark edge, not just its own.
 *
 * Numbers overlap - that is what a stack of blows on one creature is - and the friendlier read is
 * the one where a neighbour's edge never covers a digit's face. Two flat depths give that for
 * free, and cost nothing over sorting each number as its own unit.
 */
export const COMBAT_TEXT_FILL_DEPTH = COMBAT_TEXT_DEPTH + 1;

export const COMBAT_TEXT_LIFETIME_MS = 640;
export const COMBAT_TEXT_PUNCH_PEAK_MS = 96;
export const COMBAT_TEXT_PUNCH_SETTLE_MS = 160;
export const COMBAT_TEXT_RISE_MS = 480;
export const COMBAT_TEXT_FADE_START_MS = 360;
export const COMBAT_TEXT_SHAKE_MS = 72;
export const COMBAT_TEXT_RISE_PX = 32;
export const COMBAT_TEXT_SHAKE_PX = 2;
/** Six targets times three blows, twice over, before the oldest number is recycled. */
export const COMBAT_TEXT_DEFAULT_ACTIVE_CAP = 64;

// Numbers that land on the same creature within a few frames stack upward instead of drawing on
// top of each other, which is the column read of a multi-hit. The offset is decided once when the
// number is shown and folded into its anchor, so the rise and fade above never have to know.
export const COMBAT_TEXT_STACK_WINDOW_MS = 300;
export const COMBAT_TEXT_STACK_RADIUS_PX = 48;
// Just under a full line. The reference stacks its blows so they nearly touch, which is what
// makes a burst read as one flurry rather than as five separate events - but a step shorter than
// the glyphs is a step that overlaps them, and two overlapping numbers are one unreadable one.
export const COMBAT_TEXT_STACK_STEP_SHARE = 0.95;
export const COMBAT_TEXT_STACK_JITTER_SHARE = 0.15;

// A number is drawn one digit at a time, and each digit is placed, sized, and revealed on its
// own. That is the whole difference between a damage number and a damage *effect*: a single text
// object can only pop as one block, while a row of digits can arrive left to right, each landing
// slightly off the line its neighbours sit on. Every value below is displacement around the run's
// own anchor, so the rise, the shake, the stack, and the fade above are untouched by it.
// The displacement below is expressed as a share of the font size, not in pixels. A number set
// two and a half times larger has to arc, jitter and drop two and a half times as far or it
// reads as a big number sitting perfectly still.
/** The beat between one digit arriving and the next. Time, so it does not scale. */
export const COMBAT_TEXT_GLYPH_STAGGER_MS = 26;
/** How long a digit takes to fall from its arrival size to its resting one. */
export const COMBAT_TEXT_GLYPH_SETTLE_MS = 120;
/** The size a digit arrives at. Bigger than rest, so it reads as thrown rather than typed. */
export const COMBAT_TEXT_GLYPH_ARRIVAL_SCALE = 1.45;
/** Height of the shallow arc the digits of one number come to rest on, at its middle. */
export const COMBAT_TEXT_GLYPH_ARC_SHARE = 0.25;
/** How far a digit may sit either side of that arc, so the row is never a ruled line. */
export const COMBAT_TEXT_GLYPH_JITTER_SHARE = 0.15;
/** How far a digit falls into its place while it settles. */
export const COMBAT_TEXT_GLYPH_DROP_SHARE = 0.3;
/** How much a digit's size may vary either side of the run's own. */
export const COMBAT_TEXT_GLYPH_SIZE_VARIANCE = 0.1;
/**
 * Space added between digit boxes.
 *
 * Positive, not negative. Tight tracking is what an arcade number looks like *without* an
 * outline; with one, each digit is fattened by half the dark edge on every side, so packing them
 * fuses those edges into a single dark mass and the digits stop being separable. The space pays
 * for the edge.
 */
export const COMBAT_TEXT_GLYPH_TRACKING_SHARE = 0.05;
/** A digit's advance as a share of the font size, when the renderer cannot measure the real one. */
export const COMBAT_TEXT_GLYPH_NOMINAL_ADVANCE = 0.62;
/** The same for the narrow marks a number can carry: the critical bang, a decimal point, a sign. */
export const COMBAT_TEXT_NARROW_GLYPH_NOMINAL_ADVANCE = 0.34;
const NARROW_GLYPHS = "!.,+-e";
/** Pooled glyphs per number the cap allows, so a burst of long numbers still recycles. */
const POOLED_GLYPHS_PER_NUMBER = 8;

const PUNCH_START_SCALE = 0.78;
const PUNCH_PEAK_SCALE = 1.14;
const MAX_ACTIVE_CAP = 128;
const SHAKE_STEP_MS = 12;
const SHAKE_PATTERN = Object.freeze([0, 1, -0.75, 0.5, -0.35, 0] as const);

export type CombatTextVisualStyle = Readonly<{
  /** The number's identity colour, the middle of its gradient, and the flat fallback. */
  color: string;
  /** Top of the core gradient, where the light collects. */
  highlightColor: string;
  /** Foot of the core gradient, where the hue goes deep. */
  shadowColor: string;
  innerOutlineColor: string;
  innerOutlineThicknessPx: number;
  outerOutlineColor: string;
  /** Must exceed the inner thickness, or the dark edge never appears from behind the ring. */
  outerOutlineThicknessPx: number;
  fontFamily: string;
  fontSizePx: number;
}>;

/** Build one style from its palette and its size; the two edges are shares of the size. */
function visualStyle(
  input: Readonly<{
    fontSizePx: number;
    color: string;
    highlightColor: string;
    shadowColor: string;
    innerOutlineColor: string;
    outerOutlineColor: string;
  }>,
): CombatTextVisualStyle {
  return Object.freeze({
    ...input,
    innerOutlineThicknessPx: Math.max(1, Math.round(input.fontSizePx * RING_SHARE)),
    outerOutlineThicknessPx: Math.max(2, Math.round(input.fontSizePx * EDGE_SHARE)),
    fontFamily: COMBAT_TEXT_FONT_STACK,
  });
}

const COMBAT_TEXT_CRITICAL_STYLES: Readonly<
  Record<CombatTextDirection, CombatTextVisualStyle>
> = Object.freeze({
  outgoing: visualStyle({
    fontSizePx: Math.round(OUTGOING_FONT_SIZE_PX * COMBAT_TEXT_CRITICAL_SCALE),
    color: COMBAT_TEXT_CRITICAL_OUTGOING_COLOR,
    highlightColor: COMBAT_TEXT_CRITICAL_HIGHLIGHT_COLOR,
    shadowColor: COMBAT_TEXT_CRITICAL_OUTGOING_SHADOW_COLOR,
    innerOutlineColor: COMBAT_TEXT_CRITICAL_OUTGOING_INNER_COLOR,
    outerOutlineColor: COMBAT_TEXT_CRITICAL_OUTER_OUTLINE_COLOR,
  }),
  incoming: visualStyle({
    fontSizePx: Math.round(INCOMING_FONT_SIZE_PX * COMBAT_TEXT_CRITICAL_SCALE),
    color: COMBAT_TEXT_CRITICAL_INCOMING_COLOR,
    highlightColor: COMBAT_TEXT_CRITICAL_HIGHLIGHT_COLOR,
    shadowColor: COMBAT_TEXT_CRITICAL_INCOMING_SHADOW_COLOR,
    innerOutlineColor: COMBAT_TEXT_CRITICAL_INCOMING_INNER_COLOR,
    outerOutlineColor: COMBAT_TEXT_CRITICAL_OUTER_OUTLINE_COLOR,
  }),
});

const COMBAT_TEXT_STYLES: Readonly<
  Record<CombatTextDirection, CombatTextVisualStyle>
> = Object.freeze({
  outgoing: visualStyle({
    fontSizePx: OUTGOING_FONT_SIZE_PX,
    color: COMBAT_TEXT_OUTGOING_COLOR,
    highlightColor: COMBAT_TEXT_OUTGOING_HIGHLIGHT_COLOR,
    shadowColor: COMBAT_TEXT_OUTGOING_SHADOW_COLOR,
    innerOutlineColor: COMBAT_TEXT_INNER_OUTLINE_COLOR,
    outerOutlineColor: COMBAT_TEXT_OUTER_OUTLINE_COLOR,
  }),
  incoming: visualStyle({
    fontSizePx: INCOMING_FONT_SIZE_PX,
    color: COMBAT_TEXT_INCOMING_COLOR,
    highlightColor: COMBAT_TEXT_INCOMING_HIGHLIGHT_COLOR,
    shadowColor: COMBAT_TEXT_INCOMING_SHADOW_COLOR,
    innerOutlineColor: COMBAT_TEXT_INNER_OUTLINE_COLOR,
    outerOutlineColor: COMBAT_TEXT_OUTER_OUTLINE_COLOR,
  }),
});

export function combatTextVisualStyle(
  direction: CombatTextDirection,
  critical = false,
): CombatTextVisualStyle {
  return critical
    ? COMBAT_TEXT_CRITICAL_STYLES[direction]
    : COMBAT_TEXT_STYLES[direction];
}

export type CombatTextMotion = Readonly<{
  eventId: number;
  startedAtMs: number;
  anchorX: number;
  anchorY: number;
  reducedMotion: boolean;
  /** A critical punches harder and rises further; reduced motion still flattens both. */
  critical: boolean;
  /**
   * The size this run is set at.
   *
   * Carried on the motion rather than read from the style, because every displacement below is a
   * share of it: the arc, the jitter, the drop and the stack all have to grow with the glyphs
   * they are moving, and a sampler that had to look a style up could not stay pure.
   */
  glyphSizePx: number;
}>;

export type CombatTextSample = Readonly<{
  x: number;
  y: number;
  alpha: number;
  scale: number;
  complete: boolean;
}>;

function unitProgress(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function easeOutCubic(progress: number): number {
  return 1 - (1 - progress) ** 3;
}

function lerp(from: number, to: number, progress: number): number {
  return from + (to - from) * progress;
}

function punchScale(elapsedMs: number): number {
  if (elapsedMs <= COMBAT_TEXT_PUNCH_PEAK_MS) {
    const progress = easeOutCubic(
      unitProgress(elapsedMs / COMBAT_TEXT_PUNCH_PEAK_MS),
    );
    return lerp(PUNCH_START_SCALE, PUNCH_PEAK_SCALE, progress);
  }
  if (elapsedMs < COMBAT_TEXT_PUNCH_SETTLE_MS) {
    const progress = easeOutCubic(
      unitProgress(
        (elapsedMs - COMBAT_TEXT_PUNCH_PEAK_MS) /
          (COMBAT_TEXT_PUNCH_SETTLE_MS - COMBAT_TEXT_PUNCH_PEAK_MS),
      ),
    );
    return lerp(PUNCH_PEAK_SCALE, 1, progress);
  }
  return 1;
}

/** Deterministic, bounded horizontal glyph shake; it never touches a camera or actor. */
function glyphShakeX(eventId: number, elapsedMs: number): number {
  if (elapsedMs < 0 || elapsedMs >= COMBAT_TEXT_SHAKE_MS) return 0;
  const step = Math.floor(elapsedMs / SHAKE_STEP_MS);
  const idPhase = Math.abs(Math.trunc(eventId)) % SHAKE_PATTERN.length;
  const value = SHAKE_PATTERN[(idPhase + step) % SHAKE_PATTERN.length];
  const decay = 1 - elapsedMs / COMBAT_TEXT_SHAKE_MS;
  return value * COMBAT_TEXT_SHAKE_PX * decay;
}

/**
 * Sample one combat-text instance at an explicit simulation timestamp.
 *
 * Reduced motion is opacity-only: the glyph stays at its authored anchor at scale 1 while keeping
 * the same readable lifetime. Normal motion combines a short punch, a 32px rise, a local 2px
 * maximum micro-shake, and a final opacity fade.
 */
export function sampleCombatText(
  motion: CombatTextMotion,
  nowMs: number,
): CombatTextSample {
  const safeNowMs = Number.isFinite(nowMs) ? nowMs : motion.startedAtMs;
  const elapsedMs = Math.max(0, safeNowMs - motion.startedAtMs);
  const fadeProgress = unitProgress(
    (elapsedMs - COMBAT_TEXT_FADE_START_MS) /
      (COMBAT_TEXT_LIFETIME_MS - COMBAT_TEXT_FADE_START_MS),
  );
  const alpha = 1 - fadeProgress;
  const complete = elapsedMs >= COMBAT_TEXT_LIFETIME_MS;

  if (motion.reducedMotion) {
    return Object.freeze({
      x: motion.anchorX,
      y: motion.anchorY,
      alpha,
      scale: 1,
      complete,
    });
  }

  const riseProgress = easeOutCubic(
    unitProgress(elapsedMs / COMBAT_TEXT_RISE_MS),
  );
  const emphasis = motion.critical ? COMBAT_TEXT_CRITICAL_SCALE : 1;
  return Object.freeze({
    x: motion.anchorX + glyphShakeX(motion.eventId, elapsedMs) * emphasis,
    y: motion.anchorY - COMBAT_TEXT_RISE_PX * riseProgress * emphasis,
    alpha,
    scale: punchScale(elapsedMs),
    complete,
  });
}

export type CombatTextGlyphSample = Readonly<{
  /** Horizontal place in the run, measured from its center. */
  offsetX: number;
  /** Vertical displacement from the run's own line. */
  offsetY: number;
  /** Multiplies the run's scale; this is where the per-digit arrival lives. */
  scale: number;
  /** Multiplies the run's alpha; zero before this digit's turn has come. */
  alpha: number;
}>;

/**
 * Deterministic per-digit noise in [-1, 1).
 *
 * A hash rather than a random draw, for the reason every motion in this module is sampled: the
 * same blow has to displace its digits the same way in normal play and in a fixed-frame capture.
 */
function glyphNoise(eventId: number, index: number, channel: number): number {
  let value =
    (Math.abs(Math.trunc(eventId)) * 0x9e3779b1 + index * 0x85ebca77 + channel * 0xc2b2ae3d) >>> 0;
  value = Math.imul(value ^ (value >>> 15), value | 1);
  value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
  return ((value ^ (value >>> 14)) >>> 0) / 2_147_483_648 - 1;
}

/**
 * Lay a run of glyphs out around its own center.
 *
 * Pure, and separate from the sampler above, because *where* a digit sits along the row is a
 * question about the glyphs the font actually drew, while *how* it arrives is a question about
 * time. The caller supplies real advance widths when it can measure them and nominal ones when it
 * cannot; either way the row is centered, so a number never drifts sideways as it grows a digit.
 */
export function combatTextGlyphLayout(
  advances: readonly number[],
  trackingPx: number,
): readonly number[] {
  if (advances.length === 0) return Object.freeze([]);
  const total =
    advances.reduce((sum, advance) => sum + advance, 0) + trackingPx * (advances.length - 1);
  let cursor = -total / 2;
  const centers = advances.map((advance) => {
    const center = cursor + advance / 2;
    cursor += advance + trackingPx;
    return center;
  });
  return Object.freeze(centers);
}

/** The advance to lay a character out on when the renderer reports no usable width. */
export function combatTextNominalGlyphAdvance(fontSizePx: number, character: string): number {
  const share = NARROW_GLYPHS.includes(character)
    ? COMBAT_TEXT_NARROW_GLYPH_NOMINAL_ADVANCE
    : COMBAT_TEXT_GLYPH_NOMINAL_ADVANCE;
  return fontSizePx * share;
}

/**
 * Sample one digit of a number at an explicit simulation timestamp.
 *
 * Everything here is relative to the run: the caller places the number with `sampleCombatText`
 * and then displaces each digit by this. A digit is invisible until its turn, arrives oversized
 * and high, and falls into a resting place that is a shallow arc plus its own fixed jitter -- so
 * six digits read as six struck things rather than as one word that grew.
 *
 * Reduced motion keeps the row and drops the theatre: digits sit on one flat line at one size,
 * all present from the first frame, and only the run's own fade remains.
 */
export function sampleCombatTextGlyph(
  motion: CombatTextMotion,
  glyph: Readonly<{ index: number; count: number; centerOffsetX: number }>,
  nowMs: number,
): CombatTextGlyphSample {
  if (
    !Number.isSafeInteger(glyph.index) ||
    !Number.isSafeInteger(glyph.count) ||
    glyph.count <= 0 ||
    glyph.index < 0 ||
    glyph.index >= glyph.count
  ) {
    throw new Error("combat text glyph index must lie inside its run");
  }
  if (motion.reducedMotion) {
    return Object.freeze({
      offsetX: glyph.centerOffsetX,
      offsetY: 0,
      scale: 1,
      alpha: 1,
    });
  }
  const safeNowMs = Number.isFinite(nowMs) ? nowMs : motion.startedAtMs;
  const elapsedMs = Math.max(0, safeNowMs - motion.startedAtMs);
  const localMs = elapsedMs - glyph.index * COMBAT_TEXT_GLYPH_STAGGER_MS;
  const size = motion.glyphSizePx;
  const arc =
    -size * COMBAT_TEXT_GLYPH_ARC_SHARE * Math.sin((Math.PI * (glyph.index + 0.5)) / glyph.count);
  const jitter =
    glyphNoise(motion.eventId, glyph.index, 1) * size * COMBAT_TEXT_GLYPH_JITTER_SHARE;
  const variance =
    1 + glyphNoise(motion.eventId, glyph.index, 2) * COMBAT_TEXT_GLYPH_SIZE_VARIANCE;
  const settle = easeOutCubic(unitProgress(localMs / COMBAT_TEXT_GLYPH_SETTLE_MS));
  return Object.freeze({
    offsetX: glyph.centerOffsetX,
    offsetY: arc + jitter - size * COMBAT_TEXT_GLYPH_DROP_SHARE * (1 - settle),
    scale: lerp(COMBAT_TEXT_GLYPH_ARRIVAL_SCALE, 1, settle) * variance,
    alpha: localMs < 0 ? 0 : 1,
  });
}

/** Stable decimal formatting; current combat is integer-valued but the contract need not be. */
export type CombatTextStackPeer = Readonly<{
  baseX: number;
  baseY: number;
  startedAtMs: number;
}>;

/**
 * Where a new number goes relative to where it was asked for, given the numbers already up.
 *
 * Counts the live peers shown within the stack window at nearly the same place - measured at
 * their *unstacked* anchors, so a column does not drift as it grows - and lifts the new one by a
 * step per peer, with a small sideways jitter from its own id so a straight column still reads as
 * separate blows. Pure, so the stack a capture shows is the stack the test computed.
 */
export function combatTextStackOffset(
  peers: readonly CombatTextStackPeer[],
  input: Readonly<{
    eventId: number;
    x: number;
    y: number;
    nowMs: number;
    glyphSizePx: number;
  }>,
): Readonly<{ x: number; y: number }> {
  let count = 0;
  for (const peer of peers) {
    if (input.nowMs - peer.startedAtMs > COMBAT_TEXT_STACK_WINDOW_MS) continue;
    if (Math.abs(peer.baseX - input.x) > COMBAT_TEXT_STACK_RADIUS_PX) continue;
    if (Math.abs(peer.baseY - input.y) > COMBAT_TEXT_STACK_RADIUS_PX) continue;
    count += 1;
  }
  if (count === 0) return Object.freeze({ x: 0, y: 0 });
  const jitter = ((Math.abs(Math.trunc(input.eventId)) * 7) % 3) - 1;
  return Object.freeze({
    x: jitter * input.glyphSizePx * COMBAT_TEXT_STACK_JITTER_SHARE,
    y: -input.glyphSizePx * COMBAT_TEXT_STACK_STEP_SHARE * count,
  });
}

export function formatCombatTextAmount(amount: number): string {
  if (!Number.isFinite(amount) || amount <= 0) return "";
  return String(Number(amount.toFixed(2)));
}

export type ShowCombatTextInput = Readonly<{
  resolution: DamageResolution;
  direction: CombatTextDirection;
  x: number;
  y: number;
  nowMs: number;
}>;

export type CombatTextGlyphSnapshot = Readonly<{
  character: string;
  x: number;
  y: number;
  scale: number;
  alpha: number;
}>;

export type CombatTextEntrySnapshot = Readonly<{
  eventId: number;
  direction: CombatTextDirection;
  critical: boolean;
  amount: number;
  text: string;
  startedAtMs: number;
  anchorX: number;
  anchorY: number;
  x: number;
  y: number;
  alpha: number;
  scale: number;
  /** Where each digit of this number actually ended up, in world space. */
  glyphs: readonly CombatTextGlyphSnapshot[];
}>;

export type CombatTextSystemSnapshot = Readonly<{
  enabled: boolean;
  reducedMotion: boolean;
  disposed: boolean;
  activeCount: number;
  pooledCount: number;
  entries: readonly CombatTextEntrySnapshot[];
}>;

export type CombatTextSystemOptions = Readonly<{
  scene: Phaser.Scene;
  enabled?: boolean;
  reducedMotion?: boolean;
  maxActive?: number;
}>;

type ActiveGlyph = {
  character: string;
  /** Its place along the row, decided once from the run's measured advances. */
  centerOffsetX: number;
  /** The dark silhouette, and the coloured face drawn over it. Moved as one. */
  edge: Phaser.GameObjects.Text;
  fill: Phaser.GameObjects.Text;
  sample: CombatTextGlyphSample;
};

type ActiveCombatText = {
  eventId: number;
  direction: CombatTextDirection;
  critical: boolean;
  amount: number;
  text: string;
  /** The anchor as asked for, before stacking, which is what later numbers stack against. */
  baseX: number;
  baseY: number;
  motion: CombatTextMotion;
  sample: CombatTextSample;
  glyphs: ActiveGlyph[];
};

/**
 * The canvas style for one of a glyph's two layers.
 *
 * Canvas strokes text once, so a second ring has to be a second object. The `edge` layer is the
 * whole glyph painted in the dark colour and stroked with it as well, which is a silhouette
 * fattened by half that thickness on every side; the `fill` layer is the number's own colour
 * stroked with the light ring. Drawn one over the other, that is a double outline.
 */
function phaserTextStyle(
  style: CombatTextVisualStyle,
  layer: "edge" | "fill",
): Phaser.Types.GameObjects.Text.TextStyle {
  const edge = layer === "edge";
  return {
    align: "center",
    color: edge ? style.outerOutlineColor : style.color,
    fontFamily: style.fontFamily,
    fontSize: `${style.fontSizePx}px`,
    // The committed face is single-weight, so this asks for the weight it has. Bold from a face
    // with no bold is synthesized by the browser, and how much it thickens is the browser's
    // decision, not the repository's.
    fontStyle: "normal",
    stroke: edge ? style.outerOutlineColor : style.innerOutlineColor,
    strokeThickness: edge
      ? style.outerOutlineThicknessPx
      : style.innerOutlineThicknessPx,
  };
}

/**
 * Fill one drawn glyph's core with its vertical gradient.
 *
 * Canvas gradients belong to the context that paints them, so this reaches for the text object's
 * own rather than building one centrally. Applied once, when the glyph is first drawn: a pooled
 * glyph keeps the character and the style it was made with, so the gradient it was given still
 * describes it, and reuse stays free. A non-rendering environment has no canvas to build one
 * from and keeps the flat identity colour, which is what it was already going to draw.
 */
function applyCoreGradient(
  glyph: Phaser.GameObjects.Text,
  style: CombatTextVisualStyle,
): void {
  const context = glyph.context as CanvasRenderingContext2D | undefined;
  if (typeof context?.createLinearGradient !== "function") return;
  const height = glyph.height > 0 ? glyph.height : style.fontSizePx;
  const gradient = context.createLinearGradient(0, 0, 0, height);
  // The identity colour sits high in the glyph rather than at its middle, so the lit band is a
  // band and not half the number. A digit that is pale for half its height reads as pale.
  gradient.addColorStop(0, style.highlightColor);
  gradient.addColorStop(0.25, style.color);
  gradient.addColorStop(1, style.shadowColor);
  glyph.setFill(gradient);
}

function glyphPoolKey(
  direction: CombatTextDirection,
  critical: boolean,
  character: string,
  layer: "edge" | "fill",
): string {
  return [direction, critical ? "critical" : "normal", layer, character].join("\u0000");
}

/**
 * Scene-owned FCT renderer with a bounded active set and bounded reusable glyph pool.
 *
 * The oldest glyph is recycled when the cap is reached. This preserves the newest combat signal
 * during pathological bursts while guaranteeing the scene never accumulates unbounded Phaser
 * objects. Call `clear()` on stage teardown and `dispose()` on scene shutdown.
 */
export class CombatTextSystem {
  private readonly scene: Phaser.Scene;
  private readonly maxActive: number;
  private readonly active: ActiveCombatText[] = [];
  // Pooled by the exact glyph, not just by style: a recycled "7" already holds a rendered 7, so
  // reuse costs no text re-render at all. The alphabet a damage number draws from is a dozen
  // characters, which is what makes keying this finely worth doing.
  private readonly pool = new Map<string, Phaser.GameObjects.Text[]>();
  private pooledCount = 0;
  private nextEventId = 1;
  private enabled: boolean;
  private reducedMotion: boolean;
  private disposed = false;

  constructor(options: CombatTextSystemOptions) {
    const maxActive = options.maxActive ?? COMBAT_TEXT_DEFAULT_ACTIVE_CAP;
    if (
      !Number.isSafeInteger(maxActive) ||
      maxActive < 1 ||
      maxActive > MAX_ACTIVE_CAP
    ) {
      throw new Error(`combat text maxActive must be an integer from 1 to ${MAX_ACTIVE_CAP}`);
    }
    this.scene = options.scene;
    this.maxActive = maxActive;
    this.enabled = options.enabled ?? true;
    this.reducedMotion = options.reducedMotion ?? false;
  }

  setEnabled(enabled: boolean): void {
    if (this.disposed) return;
    this.enabled = enabled;
    if (!enabled) this.clear();
  }

  setReducedMotion(reducedMotion: boolean): void {
    if (this.disposed) return;
    this.reducedMotion = reducedMotion;
  }

  /** Present one connected, positive damage resolution. Returns its deterministic event id. */
  showDamage(input: ShowCombatTextInput): number | null {
    if (
      this.disposed ||
      !this.enabled ||
      !input.resolution.connected ||
      !Number.isFinite(input.resolution.appliedAmount) ||
      input.resolution.appliedAmount <= 0 ||
      !Number.isFinite(input.x) ||
      !Number.isFinite(input.y) ||
      !Number.isFinite(input.nowMs)
    ) {
      return null;
    }

    if (this.active.length >= this.maxActive) this.releaseAt(0);

    const eventId = this.nextEventId;
    this.nextEventId =
      this.nextEventId >= Number.MAX_SAFE_INTEGER ? 1 : this.nextEventId + 1;
    const amount = input.resolution.appliedAmount;
    const critical = input.resolution.critical === true;
    // The bang is the half of the critical read that survives a colour-blind viewer and a
    // screenshot scaled down to a thumbnail; the palette and the size carry the rest.
    const text = critical
      ? `${formatCombatTextAmount(amount)}!`
      : formatCombatTextAmount(amount);
    const glyphSizePx = combatTextVisualStyle(input.direction, critical).fontSizePx;
    const stack = combatTextStackOffset(
      this.active.map((peer) => ({
        baseX: peer.baseX,
        baseY: peer.baseY,
        startedAtMs: peer.motion.startedAtMs,
      })),
      {
        eventId,
        x: input.x,
        y: input.y,
        nowMs: input.nowMs,
        glyphSizePx,
      },
    );
    const motion: CombatTextMotion = Object.freeze({
      eventId,
      startedAtMs: input.nowMs,
      anchorX: input.x + stack.x,
      anchorY: input.y + stack.y,
      reducedMotion: this.reducedMotion,
      critical,
      glyphSizePx,
    });
    const sample = sampleCombatText(motion, input.nowMs);
    const entry: ActiveCombatText = {
      eventId,
      direction: input.direction,
      critical,
      amount,
      text,
      baseX: input.x,
      baseY: input.y,
      motion,
      sample,
      glyphs: this.acquireRun(input.direction, text, critical),
    };
    this.applySample(entry, sample, input.nowMs);
    this.active.push(entry);
    return eventId;
  }

  /** Advance all glyphs exclusively from caller-supplied simulation time. */
  update(nowMs: number): void {
    if (this.disposed || !Number.isFinite(nowMs)) return;
    for (let index = this.active.length - 1; index >= 0; index -= 1) {
      const entry = this.active[index];
      const sample = sampleCombatText(
        { ...entry.motion, reducedMotion: this.reducedMotion },
        nowMs,
      );
      if (sample.complete) {
        this.releaseAt(index);
      } else {
        entry.sample = sample;
        this.applySample(entry, sample, nowMs);
      }
    }
  }

  /** Remove stage-owned glyphs while retaining their bounded pool for the next stage. */
  clear(): void {
    if (this.disposed) return;
    while (this.active.length > 0) this.releaseAt(this.active.length - 1);
    this.nextEventId = 1;
  }

  snapshot(): CombatTextSystemSnapshot {
    const entries = Object.freeze(
      this.active.map((entry) =>
        Object.freeze({
          eventId: entry.eventId,
          direction: entry.direction,
          critical: entry.critical,
          amount: entry.amount,
          text: entry.text,
          startedAtMs: entry.motion.startedAtMs,
          anchorX: entry.motion.anchorX,
          anchorY: entry.motion.anchorY,
          x: entry.sample.x,
          y: entry.sample.y,
          alpha: entry.sample.alpha,
          scale: entry.sample.scale,
          glyphs: Object.freeze(
            entry.glyphs.map((glyph) =>
              Object.freeze({
                character: glyph.character,
                x: glyph.fill.x,
                y: glyph.fill.y,
                scale: entry.sample.scale * glyph.sample.scale,
                alpha: entry.sample.alpha * glyph.sample.alpha,
              }),
            ),
          ),
        }),
      ),
    );
    return Object.freeze({
      enabled: this.enabled,
      reducedMotion: this.reducedMotion,
      disposed: this.disposed,
      activeCount: entries.length,
      pooledCount: this.pooledCount,
      entries,
    });
  }

  /** Destroy every Phaser object exactly once. Safe to call more than once. */
  dispose(): void {
    if (this.disposed) return;
    this.clear();
    for (const glyphs of this.pool.values()) {
      for (const glyph of glyphs) glyph.destroy();
    }
    this.pool.clear();
    this.pooledCount = 0;
    this.enabled = false;
    this.disposed = true;
  }

  /** Take one drawn glyph per character, then lay the row out around its own center. */
  private acquireRun(
    direction: CombatTextDirection,
    text: string,
    critical: boolean,
  ): ActiveGlyph[] {
    const style = combatTextVisualStyle(direction, critical);
    const characters = [...text];
    const drawn = characters.map((character) => ({
      edge: this.acquireGlyph(direction, character, critical, "edge"),
      fill: this.acquireGlyph(direction, character, critical, "fill"),
    }));
    // The font's own advance when the renderer reports one, and the nominal share when it does
    // not: a non-rendering environment still has to lay a row out, and a browser should not be
    // laid out by a guess when it knows the answer. Measured on the fill layer, because the edge
    // layer's box is inflated by its own stroke and would space the row by the outline instead of
    // by the letterforms.
    const advances = drawn.map((glyph, index) =>
      Number.isFinite(glyph.fill.width) && glyph.fill.width > 0
        ? glyph.fill.width
        : combatTextNominalGlyphAdvance(style.fontSizePx, characters[index]!),
    );
    const centers = combatTextGlyphLayout(
      advances,
      Math.round(style.fontSizePx * COMBAT_TEXT_GLYPH_TRACKING_SHARE),
    );
    return drawn.map((glyph, index) => ({
      character: characters[index]!,
      centerOffsetX: centers[index]!,
      edge: glyph.edge,
      fill: glyph.fill,
      sample: Object.freeze({ offsetX: centers[index]!, offsetY: 0, scale: 1, alpha: 0 }),
    }));
  }

  private acquireGlyph(
    direction: CombatTextDirection,
    character: string,
    critical: boolean,
    layer: "edge" | "fill",
  ): Phaser.GameObjects.Text {
    const style = combatTextVisualStyle(direction, critical);
    const key = glyphPoolKey(direction, critical, character, layer);
    const pooled = this.pool.get(key);
    const reused = pooled?.pop();
    if (pooled?.length === 0) this.pool.delete(key);
    if (reused) this.pooledCount -= 1;
    // A fresh object is styled once; a recycled one already holds this exact character in this
    // exact style, so it is only re-armed. That is the whole point of keying the pool by glyph.
    let glyph = reused;
    if (!glyph) {
      glyph = this.scene.add
        .text(0, 0, character, phaserTextStyle(style, layer))
        .setOrigin(0.5, 0.5);
      // The dark edge is one flat colour by design - it is a silhouette, and grading it would
      // only muddy the outline the number is separated from its background by.
      if (layer === "fill") applyCoreGradient(glyph, style);
    }
    glyph.setScrollFactor(1);
    glyph.setDepth(layer === "edge" ? COMBAT_TEXT_DEPTH : COMBAT_TEXT_FILL_DEPTH);
    glyph.setActive(true);
    glyph.setVisible(true);
    return glyph;
  }

  private applySample(
    entry: ActiveCombatText,
    sample: CombatTextSample,
    nowMs: number,
  ): void {
    const motion: CombatTextMotion = Object.freeze({
      ...entry.motion,
      reducedMotion: this.reducedMotion,
    });
    const count = entry.glyphs.length;
    for (let index = 0; index < count; index += 1) {
      const glyph = entry.glyphs[index]!;
      const glyphSample = sampleCombatTextGlyph(
        motion,
        { index, count, centerOffsetX: glyph.centerOffsetX },
        nowMs,
      );
      glyph.sample = glyphSample;
      // The run's own scale multiplies the row as well as each digit, so a number that punches
      // stays one number rather than a row of digits drifting apart from each other. Both layers
      // take the identical transform: they are one glyph drawn twice, not two things to keep in
      // step.
      const x = sample.x + glyphSample.offsetX * sample.scale;
      const y = sample.y + glyphSample.offsetY * sample.scale;
      const alpha = sample.alpha * glyphSample.alpha;
      const scale = sample.scale * glyphSample.scale;
      for (const layer of [glyph.edge, glyph.fill]) {
        layer.setPosition(x, y);
        layer.setAlpha(alpha);
        layer.setScale(scale);
      }
    }
  }

  private releaseAt(index: number): void {
    const [entry] = this.active.splice(index, 1);
    if (!entry) return;
    const cap = this.maxActive * POOLED_GLYPHS_PER_NUMBER;
    for (const glyph of entry.glyphs) {
      for (const layer of ["edge", "fill"] as const) {
        const text = layer === "edge" ? glyph.edge : glyph.fill;
        text.setVisible(false);
        text.setActive(false);
        text.setAlpha(0);
        if (this.pooledCount >= cap) {
          text.destroy();
          continue;
        }
        const key = glyphPoolKey(entry.direction, entry.critical, glyph.character, layer);
        const pooled = this.pool.get(key);
        if (pooled) pooled.push(text);
        else this.pool.set(key, [text]);
        this.pooledCount += 1;
      }
    }
  }
}
