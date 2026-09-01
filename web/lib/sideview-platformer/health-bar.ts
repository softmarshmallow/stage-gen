// Floating health bars, drawn under the body they belong to.
//
// World space, not screen space: a bar is re-anchored to its actor every frame
// (`setScrollFactor(1)`, position read back off the sprite) so it scrolls, zooms, and travels
// with them. That is the RPG read - health belongs to the body carrying it, and checking it
// never costs the player a glance away from the fight they are checking it during. The same
// widget serves the player and every mob, at two sizes, so a fight is read the same way from
// both sides rather than through two unrelated dialects.
//
// It keeps the HUD depth rung all the same, because painting order and coordinate space are
// separate questions and only the second one changed. Dropped into the actor band the bars went
// behind the near-foreground foliage the characters walk through - right for a body, wrong for
// the readout saying how close that body is to dying - and behind any mob that happened to
// stand in front of one. They sit above every world layer and below the true screen furniture.
//
// The fill is one continuous rounded bar over a spectrum, not a row of pips. The colour under
// the fill's leading edge is the reading: a bar running out green is healthy, one guttering at
// red is a body about to drop, and that is legible on a 46px mob bar at a glance where counting
// cells is not. Reveal is a crop of a gradient baked once per size, so the colour at a given
// fraction is a property of the texture rather than something recomputed - a bar at half is the
// same amber whether it got there by one blow or four.

import Phaser from "phaser";
import { SCENE_CONTENT_DEPTH } from "./depths";

export type HealthBarStyle = Readonly<{
  /** Drawn size of the whole capsule, in world pixels. */
  width: number;
  height: number;
  /**
   * Drop from the actor's feet to the middle of the bar, in world pixels.
   *
   * Actor sprites use a (0.5, 1) origin, so their `y` is the contact point with the ground: this
   * clears the bar of the *body*, not of the terrain, and the capsule is drawn over whatever
   * surface they stand on. That is what puts it visibly under them from any camera, rather than
   * floating at a height that only looks right on flat ground.
   */
  footGap: number;
}>;

/**
 * The player's bar, sized against the character rather than against the screen.
 *
 * The sprite is 140.8px tall but draws only about 57px of alpha across, and a bar wider than
 * that reads as a piece of the level rather than as his.
 */
export const PLAYER_HEALTH_BAR_STYLE: HealthBarStyle = Object.freeze({
  width: 72,
  height: 8,
  footGap: 11,
});

/**
 * A mob's bar: the same capsule, smaller.
 *
 * Deliberately not the player's size. Several are on screen at once and one of them is the
 * player's own, so the size difference is what keeps "how am I doing" separable from "how is
 * that one doing" without colour-coding the two apart and losing the spectrum.
 */
export const MOB_HEALTH_BAR_STYLE: HealthBarStyle = Object.freeze({
  width: 46,
  height: 5,
  footGap: 8,
});

/**
 * Low to high, left to right.
 *
 * Read at the fill's leading edge, so these are not decoration: the hand-off from red through
 * amber is where a player decides to back out of a fight.
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

export type HealthBarPlacement = Readonly<{
  /** Centre of the capsule, in world pixels. */
  x: number;
  y: number;
  width: number;
  height: number;
}>;

/**
 * Where the bar sits for an actor standing at a point.
 *
 * Pure and exported because this is the whole of the "under the body" claim, and it is the part
 * of the widget worth asserting without a browser.
 */
export function healthBarPlacement(
  input: Readonly<{ actorX: number; actorFootY: number; style: HealthBarStyle }>,
): HealthBarPlacement {
  return Object.freeze({
    x: input.actorX,
    y: input.actorFootY + input.style.footGap,
    width: input.style.width,
    height: input.style.height,
  });
}

/**
 * How much of the capsule the fill covers.
 *
 * A living actor never draws an empty bar: below one cap's worth the rounded end has nothing
 * left to round and the bar reads as a corpse's, which on a mob one hit from death is the
 * difference between pressing the attack and walking away from it. Death is the only state that
 * empties it, and it empties it completely.
 */
export function healthBarFillWidth(
  input: Readonly<{ hp: number; maxHp: number; style: HealthBarStyle }>,
): number {
  const max = Math.max(0, input.maxHp);
  const hp = Math.min(Math.max(0, input.hp), max);
  if (hp <= 0 || max <= 0) return 0;
  const exact = (hp / max) * input.style.width;
  return Math.min(input.style.width, Math.max(input.style.height, exact));
}

/**
 * Whether a bar has anything to say yet.
 *
 * An undamaged actor's bar is a full capsule reporting that nothing has happened, and a stage
 * carrying a dozen of them is a dozen readouts competing with the bodies they belong to for the
 * player's attention. The first blow is what makes the readout worth having, so the bar arrives
 * with the damage and stays for as long as the damage does.
 *
 * Strictly "is it damaged": defeat is a separate question and its own gate, so a caller that
 * hides a corpse's bar keeps doing that rather than having this predicate decide it twice.
 */
export function healthBarRevealedByDamage(
  input: Readonly<{ hp: number; maxHp: number }>,
): boolean {
  if (!Number.isFinite(input.hp) || !Number.isFinite(input.maxHp)) return false;
  if (input.maxHp <= 0) return false;
  return input.hp < input.maxHp;
}

/** One texture pair per distinct bar size, shared by every bar drawn at that size. */
function textureKeys(style: HealthBarStyle): Readonly<{
  track: string;
  fill: string;
}> {
  const size = `${style.width}x${style.height}`;
  return Object.freeze({
    track: `stage-gen-health-track-${size}`,
    fill: `stage-gen-health-fill-${size}`,
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
 * Baked into textures rather than redrawn as `Graphics` per frame because every bar at a size
 * shares them: a stage with eight mobs pays for one 46px pair, not eight, and the fill's colour
 * ramp is then a fixed property of the image instead of arithmetic repeated per actor per frame.
 */
function ensureTextures(scene: Phaser.Scene, style: HealthBarStyle): void {
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
    // Inset by the rim so the colour sits inside the track rather than over its edge, which at
    // five pixels tall is the difference between a bar and a smear.
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

export type HealthBarTick = Readonly<{
  hp: number;
  maxHp: number;
  /** Flashes the whole bar, so a blow that connected is visible on the readout itself. */
  invulnerable: boolean;
  actorX: number;
  actorFootY: number;
}>;

export class FloatingHealthBar {
  private readonly container: Phaser.GameObjects.Container;
  private readonly fill: Phaser.GameObjects.Image;
  private readonly style: HealthBarStyle;
  private lastHp = -1;
  private lastMax: number;

  constructor(scene: Phaser.Scene, maxHp: number, style: HealthBarStyle) {
    this.style = style;
    this.lastMax = Math.max(1, maxHp);
    ensureTextures(scene, style);
    const keys = textureKeys(style);

    this.container = scene.add.container(0, 0);
    this.container.setScrollFactor(1);
    this.container.setDepth(SCENE_CONTENT_DEPTH.actorHud);

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
   * A crop, not a scale: scaling would drag the whole spectrum along with the fill and paint a
   * half-empty bar in the same green as a full one, which is the one thing the gradient exists
   * to prevent. Cropping leaves each colour at the fraction it belongs to and squares off the
   * leading edge, which is what a bar draining should look like anyway.
   */
  private applyFill(hp: number): void {
    const width = healthBarFillWidth({ hp, maxHp: this.lastMax, style: this.style });
    if (width <= 0) {
      this.fill.setVisible(false);
      return;
    }
    this.fill.setVisible(true);
    this.fill.setCrop(0, 0, width, this.style.height);
  }

  /**
   * Re-anchor to the actor and redraw from their health.
   *
   * The position is written every frame and the fill only on a change, because this runs at
   * frame rate: following has to be unconditional or the bar visibly lags the body it is
   * attached to, while health changes a handful of times a stage.
   */
  update(tick: HealthBarTick): void {
    const placement = healthBarPlacement({
      actorX: tick.actorX,
      actorFootY: tick.actorFootY,
      style: this.style,
    });
    this.container.setPosition(placement.x, placement.y);
    if (tick.maxHp > 0 && tick.maxHp !== this.lastMax) {
      this.lastMax = tick.maxHp;
      this.lastHp = -1;
    }
    if (tick.hp !== this.lastHp) {
      this.applyFill(tick.hp);
      this.lastHp = tick.hp;
    }
    this.container.setAlpha(tick.invulnerable ? 0.55 : 1);
  }

  /** Follow an actor that is fading out, so the bar dies with the body rather than after it. */
  setAlpha(alpha: number): void {
    this.container.setAlpha(alpha);
  }

  setVisible(visible: boolean): void {
    this.container.setVisible(visible);
  }

  /** Back to full, for the frame-zero restore the deterministic capture runs before it starts. */
  reset(hp: number, maxHp: number): void {
    this.lastMax = Math.max(1, maxHp);
    this.lastHp = hp;
    this.applyFill(hp);
    this.container.setAlpha(1);
    this.container.setVisible(true);
  }

  snapshot(): Readonly<{
    hp: number;
    maxHp: number;
    visible: boolean;
    x: number;
    y: number;
    fillWidth: number;
  }> {
    return Object.freeze({
      hp: this.lastHp,
      maxHp: this.lastMax,
      visible: this.container.visible,
      x: this.container.x,
      y: this.container.y,
      fillWidth: healthBarFillWidth({
        hp: this.lastHp,
        maxHp: this.lastMax,
        style: this.style,
      }),
    });
  }

  destroy(): void {
    this.container.destroy(true);
  }
}
