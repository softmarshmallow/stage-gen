// Transient stat log — what just happened to the character, in words, briefly.
//
// Floating combat text answers "how much damage", anchored to the body that took it. This answers
// "what did I gain", and it belongs to the screen instead: experience and levels are facts about
// the player, not about a spot in the world, and a number rising off a corpse the player has
// already walked away from is a fact delivered to nobody.
//
// No panel, no frame, no background. The log is meant to be readable while it matters and gone
// afterwards, which a persistent box cannot do. Lines stack upward from a fixed anchor, the newest
// nearest it, and each fades on its own clock — so a burst of three kills reads as three lines
// rather than one line flickering three times.
//
// Motion is sampled from caller-supplied simulation time, exactly like combat text, so normal play
// and fixed-frame automation follow the same path with no tweens or timers to drift between them.

import type Phaser from "phaser";
import { COMBAT_TEXT_FONT_FAMILY } from "./combat-font";
import { SCENE_CONTENT_DEPTH } from "./layers";

export type StatLogKind = "experience" | "level_up" | "notice";

export const STAT_LOG_FONT_STACK =
  `"${COMBAT_TEXT_FONT_FAMILY}", "Arial Rounded MT Bold", "Trebuchet MS", sans-serif`;

export const STAT_LOG_LIFETIME_MS = 2400;
export const STAT_LOG_FADE_START_MS = 1500;
export const STAT_LOG_RISE_PX = 26;
export const STAT_LOG_LINE_HEIGHT_PX = 26;
export const STAT_LOG_DEPTH = SCENE_CONTENT_DEPTH.hud + 5;
export const STAT_LOG_MAX_LINES = 6;

export type StatLogVisualStyle = Readonly<{
  color: string;
  outlineColor: string;
  outlineThicknessPx: number;
  fontSizePx: number;
}>;

const STAT_LOG_STYLES: Readonly<Record<StatLogKind, StatLogVisualStyle>> =
  Object.freeze({
    experience: Object.freeze({
      color: "#CFE9FF",
      outlineColor: "#16202B",
      outlineThicknessPx: 4,
      fontSizePx: 20,
    }),
    // Warmer, larger, and heavier-outlined: a level is the one line worth interrupting for.
    level_up: Object.freeze({
      color: "#FFD777",
      outlineColor: "#3A2408",
      outlineThicknessPx: 5,
      fontSizePx: 26,
    }),
    notice: Object.freeze({
      color: "#E8E8E8",
      outlineColor: "#1A1A1A",
      outlineThicknessPx: 4,
      fontSizePx: 20,
    }),
  });

export function statLogVisualStyle(kind: StatLogKind): StatLogVisualStyle {
  return STAT_LOG_STYLES[kind];
}

export type StatLogMotion = Readonly<{
  entryId: number;
  startedAtMs: number;
  lineIndex: number;
}>;

export type StatLogSample = Readonly<{
  offsetY: number;
  alpha: number;
  complete: boolean;
}>;

/**
 * Where a line sits and how visible it is, given only its start time and its place in the stack.
 *
 * `lineIndex` is the caller's current stacking position rather than the one the line was born at,
 * so when an older line expires the ones above it settle down a row instead of leaving a hole.
 */
export function sampleStatLogEntry(
  motion: StatLogMotion,
  nowMs: number,
): StatLogSample {
  if (!Number.isFinite(nowMs) || !Number.isFinite(motion.startedAtMs)) {
    throw new Error("stat log sampling requires finite milliseconds");
  }
  const elapsed = Math.max(0, nowMs - motion.startedAtMs);
  if (elapsed >= STAT_LOG_LIFETIME_MS) {
    return Object.freeze({ offsetY: 0, alpha: 0, complete: true });
  }
  const rise = (elapsed / STAT_LOG_LIFETIME_MS) * STAT_LOG_RISE_PX;
  const alpha =
    elapsed <= STAT_LOG_FADE_START_MS
      ? 1
      : 1 -
        (elapsed - STAT_LOG_FADE_START_MS) /
          (STAT_LOG_LIFETIME_MS - STAT_LOG_FADE_START_MS);
  // Negated only when there is something to negate, so a line sitting exactly on the anchor
  // reports 0 rather than -0 and compares equal to it in a probe or a test.
  const offset = motion.lineIndex * STAT_LOG_LINE_HEIGHT_PX + rise;
  return Object.freeze({
    offsetY: offset === 0 ? 0 : -offset,
    alpha: Math.max(0, Math.min(1, alpha)),
    complete: false,
  });
}

/** `+12 XP`, and nothing else. The kill it came from is already on screen. */
export function formatExperienceLine(amount: number): string {
  if (!Number.isFinite(amount) || amount <= 0) return "";
  return `+${Math.floor(amount)} XP`;
}

export function formatLevelUpLine(level: number): string {
  if (!Number.isSafeInteger(level) || level < 1) return "";
  return `LEVEL ${level}`;
}

export type StatLogEntrySnapshot = Readonly<{
  entryId: number;
  kind: StatLogKind;
  text: string;
  startedAtMs: number;
  lineIndex: number;
  alpha: number;
}>;

export type StatLogSnapshot = Readonly<{
  enabled: boolean;
  activeCount: number;
  entries: readonly StatLogEntrySnapshot[];
}>;

export type StatLogHudOptions = Readonly<{
  scene: Phaser.Scene;
  /** Screen-space anchor; lines stack upward from here. */
  x: number;
  y: number;
  enabled?: boolean;
  maxLines?: number;
}>;

type ActiveStatLogEntry = {
  entryId: number;
  kind: StatLogKind;
  text: string;
  startedAtMs: number;
  glyph: Phaser.GameObjects.Text;
};

/**
 * Scene-owned renderer for the transient log, with a bounded active set.
 *
 * The oldest line is retired when the cap is reached, which keeps the newest signal during a burst
 * and guarantees the scene never accumulates unbounded text objects.
 */
export class StatLogHud {
  private readonly scene: Phaser.Scene;
  private readonly anchorX: number;
  private readonly anchorY: number;
  private readonly maxLines: number;
  private readonly active: ActiveStatLogEntry[] = [];
  private nextEntryId = 1;
  private enabled: boolean;

  constructor(options: StatLogHudOptions) {
    const maxLines = options.maxLines ?? STAT_LOG_MAX_LINES;
    if (!Number.isSafeInteger(maxLines) || maxLines < 1 || maxLines > 32) {
      throw new Error("stat log maxLines must be an integer from 1 to 32");
    }
    if (!Number.isFinite(options.x) || !Number.isFinite(options.y)) {
      throw new Error("stat log anchor must be finite");
    }
    this.scene = options.scene;
    this.anchorX = options.x;
    this.anchorY = options.y;
    this.maxLines = maxLines;
    this.enabled = options.enabled ?? true;
  }

  /** Add one line. Returns its id, or null when the log is off or the text is empty. */
  push(
    input: Readonly<{ kind: StatLogKind; text: string; nowMs: number }>,
  ): number | null {
    if (!this.enabled || !input.text || !Number.isFinite(input.nowMs)) return null;
    if (this.active.length >= this.maxLines) this.releaseAt(0);
    const style = statLogVisualStyle(input.kind);
    const glyph = this.scene.add.text(this.anchorX, this.anchorY, input.text, {
      align: "left",
      color: style.color,
      fontFamily: STAT_LOG_FONT_STACK,
      fontSize: `${style.fontSizePx}px`,
      fontStyle: "bold",
      stroke: style.outlineColor,
      strokeThickness: style.outlineThicknessPx,
    });
    glyph.setOrigin(0, 1);
    glyph.setScrollFactor(0);
    glyph.setDepth(STAT_LOG_DEPTH);
    const entryId = this.nextEntryId;
    this.nextEntryId =
      this.nextEntryId >= Number.MAX_SAFE_INTEGER ? 1 : this.nextEntryId + 1;
    this.active.push({
      entryId,
      kind: input.kind,
      text: input.text,
      startedAtMs: input.nowMs,
      glyph,
    });
    this.update(input.nowMs);
    return entryId;
  }

  /** Advance every line from caller-supplied simulation time. */
  update(nowMs: number): void {
    if (!Number.isFinite(nowMs)) return;
    for (let index = this.active.length - 1; index >= 0; index -= 1) {
      const entry = this.active[index];
      // Newest nearest the anchor, so a line's row is its distance from the end of the stack.
      const lineIndex = this.active.length - 1 - index;
      const sample = sampleStatLogEntry(
        { entryId: entry.entryId, startedAtMs: entry.startedAtMs, lineIndex },
        nowMs,
      );
      if (sample.complete) {
        this.releaseAt(index);
        continue;
      }
      entry.glyph.setPosition(this.anchorX, this.anchorY + sample.offsetY);
      entry.glyph.setAlpha(sample.alpha);
    }
  }

  setEnabled(enabled: boolean): void {
    this.enabled = enabled;
    if (!enabled) this.clear();
  }

  clear(): void {
    while (this.active.length > 0) this.releaseAt(this.active.length - 1);
  }

  snapshot(): StatLogSnapshot {
    return Object.freeze({
      enabled: this.enabled,
      activeCount: this.active.length,
      entries: Object.freeze(
        this.active.map((entry, index) =>
          Object.freeze({
            entryId: entry.entryId,
            kind: entry.kind,
            text: entry.text,
            startedAtMs: entry.startedAtMs,
            lineIndex: this.active.length - 1 - index,
            alpha: entry.glyph.alpha,
          }),
        ),
      ),
    });
  }

  private releaseAt(index: number): void {
    const [entry] = this.active.splice(index, 1);
    if (entry?.glyph.active) entry.glyph.destroy();
  }
}
