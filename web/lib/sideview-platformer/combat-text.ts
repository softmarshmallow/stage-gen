// Floating combat text (FCT) for resolved damage.
//
// Combat decides whether a hit connected and how much HP it actually removed. This module only
// presents that immutable resolution. Motion is sampled from caller-supplied simulation time, so
// normal play and fixed-frame automation use the same path; there are no Phaser tweens, timers, or
// random offsets whose state could drift between captures.

import type Phaser from "phaser";
import type { DamageResolution } from "./combat";
import { COMBAT_TEXT_FONT_FAMILY } from "./combat-font";
import { SCENE_CONTENT_DEPTH } from "./depths";

export type CombatTextDirection = "outgoing" | "incoming";

/** Committed Fredoka face first, explicit rounded-display fallbacks after it. */
export const COMBAT_TEXT_FONT_STACK =
  `"${COMBAT_TEXT_FONT_FAMILY}", "Arial Rounded MT Bold", "Trebuchet MS", sans-serif`;

export const COMBAT_TEXT_OUTGOING_COLOR = "#FFF0A6";
export const COMBAT_TEXT_INCOMING_COLOR = "#FF6B6B";
export const COMBAT_TEXT_OUTLINE_COLOR = "#24110D";
/** Criticals read as heat: the same hue family pushed to white-hot, not a different palette. */
export const COMBAT_TEXT_CRITICAL_OUTGOING_COLOR = "#FFFFFF";
export const COMBAT_TEXT_CRITICAL_INCOMING_COLOR = "#FFD2D2";
export const COMBAT_TEXT_CRITICAL_OUTLINE_COLOR = "#7A1B10";
/** Size and punch multipliers that make a critical unmistakable at a glance. */
export const COMBAT_TEXT_CRITICAL_SCALE = 1.4;
export const COMBAT_TEXT_DEPTH = SCENE_CONTENT_DEPTH.actorHud + 10;

export const COMBAT_TEXT_LIFETIME_MS = 640;
export const COMBAT_TEXT_PUNCH_PEAK_MS = 96;
export const COMBAT_TEXT_PUNCH_SETTLE_MS = 160;
export const COMBAT_TEXT_RISE_MS = 480;
export const COMBAT_TEXT_FADE_START_MS = 360;
export const COMBAT_TEXT_SHAKE_MS = 72;
export const COMBAT_TEXT_RISE_PX = 32;
export const COMBAT_TEXT_SHAKE_PX = 2;
export const COMBAT_TEXT_DEFAULT_ACTIVE_CAP = 24;

const PUNCH_START_SCALE = 0.78;
const PUNCH_PEAK_SCALE = 1.14;
const MAX_ACTIVE_CAP = 128;
const SHAKE_STEP_MS = 12;
const SHAKE_PATTERN = Object.freeze([0, 1, -0.75, 0.5, -0.35, 0] as const);

export type CombatTextVisualStyle = Readonly<{
  color: string;
  outlineColor: string;
  outlineThicknessPx: number;
  fontFamily: string;
  fontSizePx: number;
}>;

const COMBAT_TEXT_CRITICAL_STYLES: Readonly<
  Record<CombatTextDirection, CombatTextVisualStyle>
> = Object.freeze({
  outgoing: Object.freeze({
    color: COMBAT_TEXT_CRITICAL_OUTGOING_COLOR,
    outlineColor: COMBAT_TEXT_CRITICAL_OUTLINE_COLOR,
    outlineThicknessPx: 7,
    fontFamily: COMBAT_TEXT_FONT_STACK,
    fontSizePx: Math.round(32 * COMBAT_TEXT_CRITICAL_SCALE),
  }),
  incoming: Object.freeze({
    color: COMBAT_TEXT_CRITICAL_INCOMING_COLOR,
    outlineColor: COMBAT_TEXT_CRITICAL_OUTLINE_COLOR,
    outlineThicknessPx: 7,
    fontFamily: COMBAT_TEXT_FONT_STACK,
    fontSizePx: Math.round(36 * COMBAT_TEXT_CRITICAL_SCALE),
  }),
});

const COMBAT_TEXT_STYLES: Readonly<
  Record<CombatTextDirection, CombatTextVisualStyle>
> = Object.freeze({
  outgoing: Object.freeze({
    color: COMBAT_TEXT_OUTGOING_COLOR,
    outlineColor: COMBAT_TEXT_OUTLINE_COLOR,
    outlineThicknessPx: 5,
    fontFamily: COMBAT_TEXT_FONT_STACK,
    fontSizePx: 32,
  }),
  incoming: Object.freeze({
    color: COMBAT_TEXT_INCOMING_COLOR,
    outlineColor: COMBAT_TEXT_OUTLINE_COLOR,
    outlineThicknessPx: 5,
    fontFamily: COMBAT_TEXT_FONT_STACK,
    fontSizePx: 36,
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

/** Stable decimal formatting; current combat is integer-valued but the contract need not be. */
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

type ActiveCombatText = {
  eventId: number;
  direction: CombatTextDirection;
  critical: boolean;
  amount: number;
  text: string;
  motion: CombatTextMotion;
  sample: CombatTextSample;
  glyph: Phaser.GameObjects.Text;
};

function phaserTextStyle(
  style: CombatTextVisualStyle,
): Phaser.Types.GameObjects.Text.TextStyle {
  return {
    align: "center",
    color: style.color,
    fontFamily: style.fontFamily,
    fontSize: `${style.fontSizePx}px`,
    fontStyle: "bold",
    stroke: style.outlineColor,
    strokeThickness: style.outlineThicknessPx,
  };
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
  private readonly pool: Phaser.GameObjects.Text[] = [];
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
    const motion: CombatTextMotion = Object.freeze({
      eventId,
      startedAtMs: input.nowMs,
      anchorX: input.x,
      anchorY: input.y,
      reducedMotion: this.reducedMotion,
      critical,
    });
    const sample = sampleCombatText(motion, input.nowMs);
    const glyph = this.acquireGlyph(input.direction, text, critical);
    const entry: ActiveCombatText = {
      eventId,
      direction: input.direction,
      critical,
      amount,
      text,
      motion,
      sample,
      glyph,
    };
    this.applySample(entry, sample);
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
        this.applySample(entry, sample);
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
        }),
      ),
    );
    return Object.freeze({
      enabled: this.enabled,
      reducedMotion: this.reducedMotion,
      disposed: this.disposed,
      activeCount: entries.length,
      pooledCount: this.pool.length,
      entries,
    });
  }

  /** Destroy every Phaser object exactly once. Safe to call more than once. */
  dispose(): void {
    if (this.disposed) return;
    this.clear();
    for (const glyph of this.pool) glyph.destroy();
    this.pool.length = 0;
    this.enabled = false;
    this.disposed = true;
  }

  private acquireGlyph(
    direction: CombatTextDirection,
    text: string,
    critical = false,
  ): Phaser.GameObjects.Text {
    const style = combatTextVisualStyle(direction, critical);
    const glyph =
      this.pool.pop() ?? this.scene.add.text(0, 0, text, phaserTextStyle(style));
    glyph.setText(text);
    glyph.setStyle(phaserTextStyle(style));
    glyph.setOrigin(0.5, 0.5);
    glyph.setScrollFactor(1);
    glyph.setDepth(COMBAT_TEXT_DEPTH);
    glyph.setActive(true);
    glyph.setVisible(true);
    return glyph;
  }

  private applySample(entry: ActiveCombatText, sample: CombatTextSample): void {
    entry.glyph.setPosition(sample.x, sample.y);
    entry.glyph.setAlpha(sample.alpha);
    entry.glyph.setScale(sample.scale);
  }

  private releaseAt(index: number): void {
    const [entry] = this.active.splice(index, 1);
    if (!entry) return;
    entry.glyph.setVisible(false);
    entry.glyph.setActive(false);
    entry.glyph.setAlpha(0);
    if (this.pool.length < this.maxActive) {
      this.pool.push(entry.glyph);
    } else {
      entry.glyph.destroy();
    }
  }
}
