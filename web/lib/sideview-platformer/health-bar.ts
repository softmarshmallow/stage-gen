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
// The drawing itself lives in `lib/families/hud/gauge-bar.ts` and is shared with every other
// bounded resource on screen - the capsule, the spectrum, the crop, the baked textures. What
// stays here is what is actually the platformer's: the two sizes, the drop below the feet, the
// actor-HUD rung, and the rule that a mob's bar arrives with its first wound.

import Phaser from "phaser";
import {
  GaugeBar,
  gaugeBarFillWidth,
  gaugeBarRevealedByChange,
  type GaugeBarStyle,
} from "@/lib/families/hud";
import { SCENE_CONTENT_DEPTH } from "./depths";

export type HealthBarStyle = GaugeBarStyle &
  Readonly<{
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
 * of the widget worth asserting without a browser. It is also the part the shared capsule
 * deliberately does not know: a bar pinned to the top of a canvas has no feet to hang under.
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
  return gaugeBarFillWidth({ value: input.hp, max: input.maxHp, style: input.style });
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
  return gaugeBarRevealedByChange({ value: input.hp, max: input.maxHp });
}

export type HealthBarTick = Readonly<{
  hp: number;
  maxHp: number;
  /** Flashes the whole bar, so a blow that connected is visible on the readout itself. */
  invulnerable: boolean;
  actorX: number;
  actorFootY: number;
}>;

/**
 * An actor's bar: the shared capsule, anchored under a body in world space.
 *
 * A thin preset rather than its own widget. Everything that made this floating
 * — scroll factor one, the drop below the feet, the actor-HUD rung — is stated
 * here in three lines, and everything that made it *a bar* is shared.
 */
export class FloatingHealthBar {
  private readonly bar: GaugeBar;
  private readonly style: HealthBarStyle;
  private lastHp = -1;
  private lastMax: number;

  constructor(scene: Phaser.Scene, maxHp: number, style: HealthBarStyle) {
    this.style = style;
    this.lastMax = Math.max(1, maxHp);
    this.bar = new GaugeBar(scene, {
      style,
      max: this.lastMax,
      // World space: a bar is re-anchored to its actor every frame, so it
      // scrolls, zooms and travels with them.
      scrollFactor: 1,
      depth: SCENE_CONTENT_DEPTH.actorHud,
    });
  }

  /** Re-anchor to the actor and redraw from their health. */
  update(tick: HealthBarTick): void {
    const placement = healthBarPlacement({
      actorX: tick.actorX,
      actorFootY: tick.actorFootY,
      style: this.style,
    });
    if (tick.maxHp > 0) this.lastMax = tick.maxHp;
    this.lastHp = tick.hp;
    this.bar.update({
      value: tick.hp,
      max: tick.maxHp,
      x: placement.x,
      y: placement.y,
      dimmed: tick.invulnerable,
    });
  }

  /** Follow an actor that is fading out, so the bar dies with the body rather than after it. */
  setAlpha(alpha: number): void {
    this.bar.setAlpha(alpha);
  }

  setVisible(visible: boolean): void {
    this.bar.setVisible(visible);
  }

  /** Back to full, for the frame-zero restore the deterministic capture runs before it starts. */
  reset(hp: number, maxHp: number): void {
    this.lastMax = Math.max(1, maxHp);
    this.lastHp = hp;
    this.bar.reset(hp, maxHp);
  }

  snapshot(): Readonly<{
    hp: number;
    maxHp: number;
    visible: boolean;
    x: number;
    y: number;
    fillWidth: number;
  }> {
    const inner = this.bar.snapshot();
    return Object.freeze({
      hp: this.lastHp,
      maxHp: this.lastMax,
      visible: inner.visible,
      x: inner.x,
      y: inner.y,
      fillWidth: healthBarFillWidth({
        hp: this.lastHp,
        maxHp: this.lastMax,
        style: this.style,
      }),
    });
  }

  destroy(): void {
    this.bar.destroy();
  }
}
