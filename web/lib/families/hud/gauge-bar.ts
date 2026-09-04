// The capsule gauge bar: one widget for every bounded resource on screen.
//
// Lifted out of the platformer's floating health bar, which had the drawing
// right and the placement welded in. Three things were assumptions rather than
// decisions there: that a bar scrolls with the world, that it hangs below a
// body's feet, and that it sits on the actor-HUD depth rung. A runner's bar is
// screen furniture pinned to the top of the canvas and none of the three hold,
// yet the drawing — the capsule, the baked textures, the crop — is exactly the
// same widget. So placement, scroll factor and depth become constructor
// arguments and the caller says where its bar lives.
//
// What did not change, because it is the whole reason this reads at a glance:
// the fill is one continuous rounded bar over a spectrum, not a row of pips,
// and the colour under the fill's leading edge *is* the reading. Reveal is a
// crop of a gradient baked once per size, so the colour at a given fraction is
// a property of the texture rather than something recomputed — a bar at half
// is the same amber whether it got there in one hit or four.

import Phaser from "phaser";

export type GaugeBarStyle = Readonly<{
  /** Drawn size of the whole capsule, in pixels of the bar's own space. */
  width: number;
  height: number;
}>;

/**
 * Low to high, left to right.
 *
 * Read at the fill's leading edge, so these are not decoration: the hand-off
 * from red through amber is where a player decides to back out.
 */
const GRADIENT_STOPS: readonly (readonly [number, string])[] = Object.freeze([
  Object.freeze([0, "#d43d2f"] as const),
  Object.freeze([0.35, "#e8743b"] as const),
  Object.freeze([0.6, "#f2c14e"] as const),
  Object.freeze([0.82, "#9ecb47"] as const),
  Object.freeze([1, "#3fbf6f"] as const),
]);

const TRACK_FILL = "rgba(14, 10, 9, 0.78)";
const TRACK_RIM = "rgba(0, 0, 0, 0.7)";
const RIM_WIDTH = 1;

/** Alpha applied to the whole bar while its gauge is refusing input. */
export const GAUGE_BAR_DIMMED_ALPHA = 0.55;

/**
 * How much of the capsule the fill covers.
 *
 * A gauge with anything left never draws an empty bar: below one cap's worth
 * the rounded end has nothing left to round and the bar reads as spent, which
 * on something one hit from empty is the difference between pressing on and
 * backing off. Reaching zero is the only state that empties it, and it empties
 * it completely.
 */
export function gaugeBarFillWidth(
  input: Readonly<{ value: number; max: number; style: GaugeBarStyle }>,
): number {
  const max = Math.max(0, input.max);
  const value = Math.min(Math.max(0, input.value), max);
  if (value <= 0 || max <= 0) return 0;
  const exact = (value / max) * input.style.width;
  return Math.min(input.style.width, Math.max(input.style.height, exact));
}

/**
 * Whether a bar has anything to say yet.
 *
 * A full gauge's bar reports that nothing has happened, and a stage carrying a
 * dozen of them is a dozen readouts competing with the bodies they belong to.
 * The first change is what makes the readout worth having. Callers that always
 * want their bar — a player's own, which is a promise about the run rather
 * than news about one body — simply do not ask.
 */
export function gaugeBarRevealedByChange(
  input: Readonly<{ value: number; max: number }>,
): boolean {
  if (!Number.isFinite(input.value) || !Number.isFinite(input.max)) return false;
  if (input.max <= 0) return false;
  return input.value < input.max;
}

/** One texture pair per distinct bar size, shared by every bar drawn at that size. */
function textureKeys(style: GaugeBarStyle): Readonly<{ track: string; fill: string }> {
  const size = `${style.width}x${style.height}`;
  return Object.freeze({
    track: `stage-gen-gauge-track-${size}`,
    fill: `stage-gen-gauge-fill-${size}`,
  });
}

/** A capsule path: the radius is half the height, so the ends are true semicircles. */
function capsulePath(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
): void {
  const radius = Math.min(height / 2, width / 2);
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + width, y, x + width, y + height, radius);
  ctx.arcTo(x + width, y + height, x, y + height, radius);
  ctx.arcTo(x, y + height, x, y, radius);
  ctx.arcTo(x, y, x + width, y, radius);
  ctx.closePath();
}

/**
 * Draw the two capsules this size needs, once.
 *
 * Baked into textures rather than redrawn as `Graphics` per frame because
 * every bar at a size shares them: a stage with eight mobs pays for one 46px
 * pair, not eight, and the fill's colour ramp is then a fixed property of the
 * image instead of arithmetic repeated per actor per frame.
 */
function ensureTextures(scene: Phaser.Scene, style: GaugeBarStyle): void {
  const keys = textureKeys(style);
  const { width, height } = style;

  if (!scene.textures.exists(keys.track)) {
    const canvas = scene.textures.createCanvas(keys.track, width, height);
    const ctx = canvas?.getContext();
    if (canvas && ctx) {
      capsulePath(ctx, RIM_WIDTH / 2, RIM_WIDTH / 2, width - RIM_WIDTH, height - RIM_WIDTH);
      ctx.fillStyle = TRACK_FILL;
      ctx.fill();
      ctx.lineWidth = RIM_WIDTH;
      ctx.strokeStyle = TRACK_RIM;
      ctx.stroke();
      canvas.refresh();
    }
  }

  if (!scene.textures.exists(keys.fill)) {
    // Inset by the rim so the colour sits inside the track rather than over
    // its edge, which at five pixels tall is the difference between a bar and
    // a smear.
    const inset = RIM_WIDTH;
    const canvas = scene.textures.createCanvas(keys.fill, width, height);
    const ctx = canvas?.getContext();
    if (canvas && ctx) {
      const gradient = ctx.createLinearGradient(0, 0, width, 0);
      for (const [stop, colour] of GRADIENT_STOPS) gradient.addColorStop(stop, colour);
      capsulePath(ctx, inset, inset, width - inset * 2, height - inset * 2);
      ctx.fillStyle = gradient;
      ctx.fill();
      canvas.refresh();
    }
  }
}

export type GaugeBarOptions = Readonly<{
  style: GaugeBarStyle;
  max: number;
  /**
   * 1 pins the bar to the world and it scrolls with the camera; 0 pins it to
   * the canvas and it does not. That single number is the whole difference
   * between a bar belonging to a body and a bar belonging to the run.
   */
  scrollFactor: number;
  depth: number;
}>;

export type GaugeBarTick = Readonly<{
  value: number;
  max: number;
  /** Centre of the capsule, in whatever space `scrollFactor` selected. */
  x: number;
  y: number;
  /** Flashes the whole bar, so a change that connected shows on the readout itself. */
  dimmed: boolean;
}>;

export class GaugeBar {
  private readonly container: Phaser.GameObjects.Container;
  private readonly fill: Phaser.GameObjects.Image;
  private readonly style: GaugeBarStyle;
  private lastValue = -1;
  private lastMax: number;

  constructor(scene: Phaser.Scene, options: GaugeBarOptions) {
    this.style = options.style;
    this.lastMax = Math.max(1, options.max);
    ensureTextures(scene, options.style);
    const keys = textureKeys(options.style);

    this.container = scene.add.container(0, 0);
    this.container.setScrollFactor(options.scrollFactor);
    this.container.setDepth(options.depth);

    const track = scene.add.image(0, 0, keys.track);
    track.setOrigin(0.5, 0.5);
    this.container.add(track);

    this.fill = scene.add.image(0, 0, keys.fill);
    this.fill.setOrigin(0.5, 0.5);
    this.container.add(this.fill);
    this.applyFill(this.lastMax);
  }

  /**
   * Reveal the leading `width` pixels of the gradient.
   *
   * A crop, not a scale: scaling would drag the whole spectrum along with the
   * fill and paint a half-empty bar in the same green as a full one, which is
   * the one thing the gradient exists to prevent. Cropping leaves each colour
   * at the fraction it belongs to and squares off the leading edge, which is
   * what a bar draining should look like anyway.
   */
  private applyFill(value: number): void {
    const width = gaugeBarFillWidth({ value, max: this.lastMax, style: this.style });
    if (width <= 0) {
      this.fill.setVisible(false);
      return;
    }
    this.fill.setVisible(true);
    this.fill.setCrop(0, 0, width, this.style.height);
  }

  /**
   * Re-place the bar and redraw from its gauge.
   *
   * The position is written every frame and the fill only on a change, because
   * this runs at frame rate: following has to be unconditional or a
   * world-anchored bar visibly lags the body it is attached to, while the
   * value changes a handful of times a run.
   */
  update(tick: GaugeBarTick): void {
    this.container.setPosition(tick.x, tick.y);
    if (tick.max > 0 && tick.max !== this.lastMax) {
      this.lastMax = tick.max;
      this.lastValue = -1;
    }
    if (tick.value !== this.lastValue) {
      this.applyFill(tick.value);
      this.lastValue = tick.value;
    }
    this.container.setAlpha(tick.dimmed ? GAUGE_BAR_DIMMED_ALPHA : 1);
  }

  /** Follow an owner that is fading out, so the bar goes with it rather than after it. */
  setAlpha(alpha: number): void {
    this.container.setAlpha(alpha);
  }

  setVisible(visible: boolean): void {
    this.container.setVisible(visible);
  }

  /** Back to full, for the frame-zero restore a deterministic capture runs before it starts. */
  reset(value: number, max: number): void {
    this.lastMax = Math.max(1, max);
    this.lastValue = value;
    this.applyFill(value);
    this.container.setAlpha(1);
    this.container.setVisible(true);
  }

  snapshot(): Readonly<{
    value: number;
    max: number;
    visible: boolean;
    x: number;
    y: number;
    fillWidth: number;
  }> {
    return Object.freeze({
      value: this.lastValue,
      max: this.lastMax,
      visible: this.container.visible,
      x: this.container.x,
      y: this.container.y,
      fillWidth: gaugeBarFillWidth({
        value: this.lastValue,
        max: this.lastMax,
        style: this.style,
      }),
    });
  }

  destroy(): void {
    this.container.destroy(true);
  }
}
