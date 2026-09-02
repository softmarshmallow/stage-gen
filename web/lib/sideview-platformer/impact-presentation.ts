// Procedural impact presentation: what a connected blow looks like beyond the number.
//
// Combat decides whether a blow connected, how much it removed and whether it killed. This module
// only presents that resolution, exactly as `combat-text.ts` presents the number: every motion is a
// pure sample over caller-supplied simulation time, so ordinary play and fixed-frame automation
// draw the same frame from the same event, and nothing here owns a tween, a timer or an emitter.
//
// Five presentations, one event. A *flash* fills the target white for a few frames. A *spark* fans
// short rays out from the point of contact in the direction of the blow. A *burst* scatters shards
// under gravity when the blow killed. A *hitstop* holds the simulation for a few frames so the blow
// has weight, and a *shake* nudges the camera on a kill. The scene applies the last two - it owns
// the clock it feeds the actors and the camera it scrolls - and this module only says when and by
// how much.
//
// No asset is drawn for any of this. The sprites the generator publishes are the actor's own
// strips, and an effect family does not exist in the taxonomy yet; everything here is geometry
// from a seed, which is what lets it ship without a provider call and stay identical between two
// captures of the same run.

import type Phaser from "phaser";
import { SCENE_CONTENT_DEPTH } from "./depths";

export const IMPACT_FLASH_MS = 64;
export const IMPACT_SPARK_MS = 150;
export const IMPACT_BURST_MS = 420;
export const IMPACT_SHAKE_MS = 130;
/** Frames the simulation holds on an ordinary connect: short enough to read as weight, not lag. */
export const IMPACT_HITSTOP_MS = 40;
/** A kill holds longer, which is what makes the last blow feel different from the others. */
export const IMPACT_KILL_HITSTOP_MS = 70;
export const IMPACT_SHAKE_PX = 4;
export const IMPACT_SPARK_RAYS = 5;
export const IMPACT_SPARK_LENGTH_PX = 30;
export const IMPACT_SPARK_SPREAD_RADIANS = Math.PI * 0.55;
export const IMPACT_BURST_SHARDS = 8;
export const IMPACT_BURST_SPEED_PX = 190;
export const IMPACT_BURST_GRAVITY_PX = 620;
export const IMPACT_BURST_RADIUS_PX = 5;
/** Criticals read as the same shapes pushed larger, the way the combat text pushes its face. */
export const IMPACT_CRITICAL_SCALE = 1.35;
export const IMPACT_DEFAULT_ACTIVE_CAP = 48;
export const IMPACT_SPARK_COLOR = 0xfff0a6;
export const IMPACT_CRITICAL_SPARK_COLOR = 0xffffff;
export const IMPACT_BURST_COLOR = 0xfff6d0;
export const IMPACT_DEPTH = SCENE_CONTENT_DEPTH.effect;
/** The swing arc: the band a strike covers, drawn as the blow that covers it. */
export const IMPACT_SWING_MS = 140;
export const IMPACT_SWING_SPAN_RADIANS = Math.PI * 0.7;
export const IMPACT_SWING_TRAIL_FRACTION = 0.45;
export const IMPACT_SWING_COLOR = 0xfff0a6;

const MAX_ACTIVE_CAP = 256;
const SHAKE_STEP_MS = 16;
const SHAKE_PATTERN = Object.freeze([1, -0.8, 0.55, -0.35, 0.2, 0] as const);
const SPARK_GROWTH_FRACTION = 0.45;
const BURST_UPWARD_BIAS_PX = 80;

/** One connected blow, as the presentation reads it. */
export type ImpactEvent = Readonly<{
  eventId: number;
  /** The blow's own seed, so shard and ray directions replay with the critical roll. */
  seed: number;
  startedAtMs: number;
  x: number;
  y: number;
  dirSign: 1 | -1;
  critical: boolean;
  died: boolean;
  reducedMotion: boolean;
}>;

export type ImpactRay = Readonly<{
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  alpha: number;
  width: number;
}>;

export type ImpactShard = Readonly<{
  x: number;
  y: number;
  radius: number;
  alpha: number;
}>;

export type ImpactSample = Readonly<{
  flash: boolean;
  rays: readonly ImpactRay[];
  shards: readonly ImpactShard[];
  shake: Readonly<{ x: number; y: number }>;
  complete: boolean;
}>;

/** Deterministic unit noise in [0, 1) for one seed and channel; no state, no wall clock. */
export function impactUnitNoise(seed: number, channel: number): number {
  let hash = (Math.imul(seed ^ channel, 0x9e3779b1) ^ (seed >>> 15)) >>> 0;
  hash = Math.imul(hash ^ (hash >>> 13), 0x85ebca6b) >>> 0;
  hash = Math.imul(hash ^ (hash >>> 16), 0xc2b2ae35) >>> 0;
  return hash / 4294967296;
}

function unitProgress(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function easeOutCubic(progress: number): number {
  return 1 - (1 - progress) ** 3;
}

function elapsedSince(event: ImpactEvent, nowMs: number): number {
  const safeNowMs = Number.isFinite(nowMs) ? nowMs : event.startedAtMs;
  return Math.max(0, safeNowMs - event.startedAtMs);
}

/** How long the whole presentation of one event lasts, in ms. */
export function impactLifetimeMs(event: Pick<ImpactEvent, "died" | "reducedMotion">): number {
  if (event.reducedMotion) return IMPACT_FLASH_MS;
  return Math.max(IMPACT_FLASH_MS, IMPACT_SPARK_MS, event.died ? Math.max(IMPACT_BURST_MS, IMPACT_SHAKE_MS) : 0);
}

/** How long the simulation holds for one blow, in ms. */
export function impactHitstopMs(input: Readonly<{ died: boolean; critical: boolean }>): number {
  const base = input.died ? IMPACT_KILL_HITSTOP_MS : IMPACT_HITSTOP_MS;
  return Math.round(base * (input.critical ? 1.25 : 1));
}

export function sampleImpactFlash(event: ImpactEvent, nowMs: number): boolean {
  return elapsedSince(event, nowMs) < IMPACT_FLASH_MS;
}

export function sampleImpactRays(event: ImpactEvent, nowMs: number): readonly ImpactRay[] {
  if (event.reducedMotion) return Object.freeze([]);
  const progress = elapsedSince(event, nowMs) / IMPACT_SPARK_MS;
  if (progress >= 1) return Object.freeze([]);
  const growth = easeOutCubic(unitProgress(progress / SPARK_GROWTH_FRACTION));
  const alpha =
    progress < SPARK_GROWTH_FRACTION
      ? 1
      : 1 - (progress - SPARK_GROWTH_FRACTION) / (1 - SPARK_GROWTH_FRACTION);
  const emphasis = event.critical ? IMPACT_CRITICAL_SCALE : 1;
  const baseAngle = event.dirSign === 1 ? 0 : Math.PI;
  const rays: ImpactRay[] = [];
  for (let index = 0; index < IMPACT_SPARK_RAYS; index += 1) {
    const fan = (index / (IMPACT_SPARK_RAYS - 1) - 0.5) * IMPACT_SPARK_SPREAD_RADIANS;
    const jitter = (impactUnitNoise(event.seed, 0x1000 + index) - 0.5) * 0.25;
    const angle = baseAngle + fan + jitter;
    const length =
      IMPACT_SPARK_LENGTH_PX *
      (0.7 + 0.6 * impactUnitNoise(event.seed, 0x2000 + index)) *
      emphasis *
      growth;
    const cos = Math.cos(angle);
    const sin = Math.sin(angle);
    rays.push(
      Object.freeze({
        x1: event.x + cos * length * 0.35,
        y1: event.y + sin * length * 0.35,
        x2: event.x + cos * length,
        y2: event.y + sin * length,
        alpha,
        width: (event.critical ? 3.5 : 2.5) * (1 - progress * 0.5),
      }),
    );
  }
  return Object.freeze(rays);
}

export function sampleImpactShards(event: ImpactEvent, nowMs: number): readonly ImpactShard[] {
  if (!event.died || event.reducedMotion) return Object.freeze([]);
  const elapsedMs = elapsedSince(event, nowMs);
  const progress = elapsedMs / IMPACT_BURST_MS;
  if (progress >= 1) return Object.freeze([]);
  const seconds = elapsedMs / 1000;
  const emphasis = event.critical ? IMPACT_CRITICAL_SCALE : 1;
  const shards: ImpactShard[] = [];
  for (let index = 0; index < IMPACT_BURST_SHARDS; index += 1) {
    const angle =
      (index / IMPACT_BURST_SHARDS) * Math.PI * 2 +
      (impactUnitNoise(event.seed, 0x3000 + index) - 0.5) * 0.5;
    const speed =
      IMPACT_BURST_SPEED_PX * (0.6 + 0.7 * impactUnitNoise(event.seed, 0x4000 + index)) * emphasis;
    const vx = Math.cos(angle) * speed;
    const vy = Math.sin(angle) * speed - BURST_UPWARD_BIAS_PX;
    shards.push(
      Object.freeze({
        x: event.x + vx * seconds,
        y: event.y + vy * seconds + 0.5 * IMPACT_BURST_GRAVITY_PX * seconds * seconds,
        radius:
          IMPACT_BURST_RADIUS_PX *
          (0.6 + 0.6 * impactUnitNoise(event.seed, 0x5000 + index)) *
          emphasis *
          (1 - progress * 0.6),
        alpha: 1 - progress * progress,
      }),
    );
  }
  return Object.freeze(shards);
}

/** Camera nudge for one event, in world pixels; zero unless the blow killed. */
export function sampleImpactShake(
  event: ImpactEvent,
  nowMs: number,
): Readonly<{ x: number; y: number }> {
  if (!event.died || event.reducedMotion) return Object.freeze({ x: 0, y: 0 });
  const elapsedMs = elapsedSince(event, nowMs);
  if (elapsedMs >= IMPACT_SHAKE_MS) return Object.freeze({ x: 0, y: 0 });
  const step = Math.floor(elapsedMs / SHAKE_STEP_MS);
  const phase = Math.abs(Math.trunc(event.seed)) % SHAKE_PATTERN.length;
  const decay = 1 - elapsedMs / IMPACT_SHAKE_MS;
  const amplitude = IMPACT_SHAKE_PX * (event.critical ? IMPACT_CRITICAL_SCALE : 1) * decay;
  return Object.freeze({
    x: SHAKE_PATTERN[(phase + step) % SHAKE_PATTERN.length] * amplitude * event.dirSign,
    y: SHAKE_PATTERN[(phase + step + 2) % SHAKE_PATTERN.length] * amplitude * 0.6,
  });
}

export function sampleImpact(event: ImpactEvent, nowMs: number): ImpactSample {
  return Object.freeze({
    flash: sampleImpactFlash(event, nowMs),
    rays: sampleImpactRays(event, nowMs),
    shards: sampleImpactShards(event, nowMs),
    shake: sampleImpactShake(event, nowMs),
    complete: elapsedSince(event, nowMs) >= impactLifetimeMs(event),
  });
}

/** One swing, as the presentation reads it: where the character stood and how far it reached. */
export type SwingEvent = Readonly<{
  eventId: number;
  startedAtMs: number;
  x: number;
  y: number;
  dirSign: 1 | -1;
  radiusPx: number;
  reducedMotion: boolean;
}>;

export type ImpactArc = Readonly<{
  x: number;
  y: number;
  radius: number;
  startAngle: number;
  endAngle: number;
  anticlockwise: boolean;
  alpha: number;
  width: number;
}>;

/**
 * The arc a swing has drawn so far, or null once it is spent.
 *
 * The head of the arc travels from up-front to down-front over the swing's life and a trailing
 * fraction follows it, so the shape reads as a blade passing rather than a ring appearing. Angles
 * are Phaser's: zero is right and positive is down. Facing left mirrors about the vertical, which
 * is why the arc is walked anticlockwise there rather than by negating the span.
 */
export function sampleSwingArc(event: SwingEvent, nowMs: number): ImpactArc | null {
  if (event.reducedMotion) return null;
  const safeNowMs = Number.isFinite(nowMs) ? nowMs : event.startedAtMs;
  const elapsedMs = Math.max(0, safeNowMs - event.startedAtMs);
  const progress = elapsedMs / IMPACT_SWING_MS;
  if (progress >= 1) return null;
  const span = IMPACT_SWING_SPAN_RADIANS;
  const head = -span / 2 + span * easeOutCubic(progress);
  const tail = Math.max(-span / 2, head - span * IMPACT_SWING_TRAIL_FRACTION);
  const forward = event.dirSign === 1;
  return Object.freeze({
    x: event.x,
    y: event.y,
    radius: event.radiusPx,
    startAngle: forward ? tail : Math.PI - tail,
    endAngle: forward ? head : Math.PI - head,
    anticlockwise: !forward,
    alpha: 1 - progress * progress,
    width: 4 - 2 * progress,
  });
}

/** What a target must offer for the flash: the system never reaches into a sprite itself. */
export type ImpactFlashTarget = Readonly<{
  setFlash(on: boolean): void;
}>;

export type ShowImpactInput = Readonly<{
  x: number;
  y: number;
  dirSign: 1 | -1;
  critical: boolean;
  died: boolean;
  seed: number;
  nowMs: number;
  target?: ImpactFlashTarget;
}>;

export type ImpactEntrySnapshot = Readonly<{
  eventId: number;
  startedAtMs: number;
  x: number;
  y: number;
  critical: boolean;
  died: boolean;
  flashing: boolean;
}>;

export type ImpactSystemSnapshot = Readonly<{
  enabled: boolean;
  reducedMotion: boolean;
  disposed: boolean;
  activeCount: number;
  swingCount: number;
  hitstopUntilMs: number;
  entries: readonly ImpactEntrySnapshot[];
}>;

export type ShowSwingInput = Readonly<{
  x: number;
  y: number;
  dirSign: 1 | -1;
  radiusPx: number;
  nowMs: number;
}>;

export type ImpactSystemOptions = Readonly<{
  scene: Phaser.Scene;
  enabled?: boolean;
  reducedMotion?: boolean;
  maxActive?: number;
}>;

type ActiveImpact = {
  event: ImpactEvent;
  target: ImpactFlashTarget | undefined;
  flashing: boolean;
};

/**
 * The scene-facing half: one pooled Graphics object redrawn from samples every frame.
 *
 * One drawable for every effect rather than one per event, because a Graphics object is cleared
 * and refilled in a single pass and the sample already knows every shape's position; a pool of
 * per-event objects would only add lifecycle for nothing to own.
 */
export class ImpactSystem {
  private readonly scene: Phaser.Scene;
  private readonly maxActive: number;
  private readonly active: ActiveImpact[] = [];
  private readonly swings: SwingEvent[] = [];
  private graphics: Phaser.GameObjects.Graphics | null = null;
  private nextEventId = 1;
  private enabled: boolean;
  private reducedMotion: boolean;
  private disposed = false;
  private hitstopUntil = 0;

  constructor(options: ImpactSystemOptions) {
    const maxActive = options.maxActive ?? IMPACT_DEFAULT_ACTIVE_CAP;
    if (!Number.isSafeInteger(maxActive) || maxActive < 1 || maxActive > MAX_ACTIVE_CAP) {
      throw new Error(`impact maxActive must be an integer from 1 to ${MAX_ACTIVE_CAP}`);
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

  /** Register one connected blow. Returns its event id, or null when nothing will be shown. */
  showHit(input: ShowImpactInput): number | null {
    if (
      this.disposed ||
      !this.enabled ||
      !Number.isFinite(input.x) ||
      !Number.isFinite(input.y) ||
      !Number.isFinite(input.nowMs) ||
      !Number.isSafeInteger(input.seed)
    ) {
      return null;
    }
    if (this.active.length >= this.maxActive) this.releaseAt(0);

    const eventId = this.nextEventId;
    this.nextEventId = this.nextEventId >= Number.MAX_SAFE_INTEGER ? 1 : this.nextEventId + 1;
    const event: ImpactEvent = Object.freeze({
      eventId,
      seed: input.seed >>> 0,
      startedAtMs: input.nowMs,
      x: input.x,
      y: input.y,
      dirSign: input.dirSign,
      critical: input.critical,
      died: input.died,
      reducedMotion: this.reducedMotion,
    });
    const entry: ActiveImpact = { event, target: input.target, flashing: false };
    this.setFlash(entry, sampleImpactFlash(event, input.nowMs));
    this.active.push(entry);
    // Hitstop extends rather than restarts: three blows in one frame hold once, and the longest
    // of them wins, so a combo's kill is never shortened by the blows before it.
    this.hitstopUntil = Math.max(
      this.hitstopUntil,
      input.nowMs + impactHitstopMs({ died: input.died, critical: input.critical }),
    );
    return eventId;
  }

  /** Register one swing, whether or not it connected with anything. */
  showSwing(input: ShowSwingInput): number | null {
    if (
      this.disposed ||
      !this.enabled ||
      !Number.isFinite(input.x) ||
      !Number.isFinite(input.y) ||
      !Number.isFinite(input.nowMs) ||
      !Number.isFinite(input.radiusPx) ||
      input.radiusPx <= 0
    ) {
      return null;
    }
    if (this.swings.length >= this.maxActive) this.swings.shift();
    const eventId = this.nextEventId;
    this.nextEventId = this.nextEventId >= Number.MAX_SAFE_INTEGER ? 1 : this.nextEventId + 1;
    this.swings.push(
      Object.freeze({
        eventId,
        startedAtMs: input.nowMs,
        x: input.x,
        y: input.y,
        dirSign: input.dirSign,
        radiusPx: input.radiusPx,
        reducedMotion: this.reducedMotion,
      }),
    );
    return eventId;
  }

  /** Whether the simulation should hold this frame. */
  hitstopActive(nowMs: number): boolean {
    return !this.disposed && this.enabled && Number.isFinite(nowMs) && nowMs < this.hitstopUntil;
  }

  /** The camera nudge for this frame: every live kill's shake summed and clamped. */
  shakeOffset(nowMs: number): Readonly<{ x: number; y: number }> {
    if (this.disposed || !this.enabled) return Object.freeze({ x: 0, y: 0 });
    let x = 0;
    let y = 0;
    for (const entry of this.active) {
      const shake = sampleImpactShake(entry.event, nowMs);
      x += shake.x;
      y += shake.y;
    }
    const bound = IMPACT_SHAKE_PX * IMPACT_CRITICAL_SCALE;
    return Object.freeze({
      x: Math.max(-bound, Math.min(bound, x)),
      y: Math.max(-bound, Math.min(bound, y)),
    });
  }

  update(nowMs: number): void {
    if (this.disposed) return;
    const graphics = this.ensureGraphics();
    graphics.clear();
    for (let index = this.swings.length - 1; index >= 0; index -= 1) {
      const arc = sampleSwingArc(this.swings[index]!, nowMs);
      if (arc === null) {
        this.swings.splice(index, 1);
        continue;
      }
      graphics.lineStyle(arc.width, IMPACT_SWING_COLOR, arc.alpha);
      graphics.beginPath();
      graphics.arc(arc.x, arc.y, arc.radius, arc.startAngle, arc.endAngle, arc.anticlockwise);
      graphics.strokePath();
    }
    for (let index = this.active.length - 1; index >= 0; index -= 1) {
      const entry = this.active[index]!;
      const sample = sampleImpact(entry.event, nowMs);
      this.setFlash(entry, sample.flash);
      if (sample.complete) {
        this.releaseAt(index);
        continue;
      }
      const sparkColor = entry.event.critical ? IMPACT_CRITICAL_SPARK_COLOR : IMPACT_SPARK_COLOR;
      for (const ray of sample.rays) {
        graphics.lineStyle(ray.width, sparkColor, ray.alpha);
        graphics.lineBetween(ray.x1, ray.y1, ray.x2, ray.y2);
      }
      for (const shard of sample.shards) {
        graphics.fillStyle(IMPACT_BURST_COLOR, shard.alpha);
        graphics.fillCircle(shard.x, shard.y, shard.radius);
      }
    }
  }

  clear(): void {
    if (this.disposed) return;
    while (this.active.length > 0) this.releaseAt(this.active.length - 1);
    this.swings.length = 0;
    this.graphics?.clear();
    this.hitstopUntil = 0;
  }

  dispose(): void {
    if (this.disposed) return;
    this.clear();
    this.graphics?.destroy();
    this.graphics = null;
    this.disposed = true;
  }

  snapshot(): ImpactSystemSnapshot {
    return Object.freeze({
      enabled: this.enabled,
      reducedMotion: this.reducedMotion,
      disposed: this.disposed,
      activeCount: this.active.length,
      swingCount: this.swings.length,
      hitstopUntilMs: this.hitstopUntil,
      entries: Object.freeze(
        this.active.map((entry) =>
          Object.freeze({
            eventId: entry.event.eventId,
            startedAtMs: entry.event.startedAtMs,
            x: entry.event.x,
            y: entry.event.y,
            critical: entry.event.critical,
            died: entry.event.died,
            flashing: entry.flashing,
          }),
        ),
      ),
    });
  }

  private ensureGraphics(): Phaser.GameObjects.Graphics {
    if (this.graphics) return this.graphics;
    this.graphics = this.scene.add.graphics().setDepth(IMPACT_DEPTH);
    return this.graphics;
  }

  private setFlash(entry: ActiveImpact, on: boolean): void {
    if (entry.flashing === on) return;
    entry.flashing = on;
    entry.target?.setFlash(on);
  }

  private releaseAt(index: number): void {
    const entry = this.active[index];
    if (!entry) return;
    this.setFlash(entry, false);
    this.active.splice(index, 1);
  }
}
