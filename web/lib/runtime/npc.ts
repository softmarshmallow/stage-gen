// Village NPC actor.
//
// A villager is deliberately not a Mob with the fighting switched off. `Mob` owns HP, a wander
// state machine, a hurt window, knockback and a death fade, and every one of those is state that
// would have to be permanently pinned to a neutral value here. An NPC has none of them: it is
// placed once, anchored to the terrain surface under it, and drawn as one still frame. The only
// things that change are which way it is facing and whether the talk prompt is showing. Keeping
// the two classes separate is what lets `snapshot()` be a true statement about a villager rather
// than a mob snapshot with five dead fields in it.
//
// Villagers are deliberately NOT animated yet. The recipe does publish a four-frame idle strip
// per resident - the same shape a mob's idle takes - and this draws only its first cell. That
// frame is not an arbitrary pick: it is the rest pose, and it is the exact frame the facing
// review and the head-matched scale reference were both measured on, so the still a player sees
// is the still every gate judged. Switching the loop on later is `sprite.play` over artwork that
// is already on disk, not a regeneration.
//
// Everything below the class is world-space. The name label and the talk prompt scroll with the
// camera because they belong to a position in the town, not to the screen; the dialogue box that
// opens when the player talks is the screen-fixed half of this feature and lives in
// `dialogue-box.ts`.

import Phaser from "phaser";
import { SCENE_CONTENT_DEPTH } from "./layers";
import {
  headMatchedScale,
  masterSheetScale,
  type ScaleReference,
} from "./sprite-scale";
import { terrainSurfaceY } from "./terrain";

/**
 * Marker shown above the villager the player can currently talk to.
 *
 * Exported so a probe or a harness can assert the prompt's text without duplicating the literal,
 * which is exactly how a rename silently breaks a capture check.
 */
export const NPC_TALK_PROMPT_TEXT = "▲ Talk";

/** Clearance between the tallest drawn idle frame and the bottom of the name label. */
const NAME_LABEL_GAP_PX = 10;

/** Clearance between the top of the name label and the bottom of the talk prompt. */
const TALK_PROMPT_GAP_PX = 6;

const NAME_LABEL_STYLE: Phaser.Types.GameObjects.Text.TextStyle = {
  fontFamily: "monospace",
  fontSize: "14px",
  color: "#f4f4f4",
  backgroundColor: "#000000a0",
  padding: { x: 6, y: 3 },
};

const TALK_PROMPT_STYLE: Phaser.Types.GameObjects.Text.TextStyle = {
  fontFamily: "monospace",
  fontSize: "13px",
  color: "#ffdf8a",
  backgroundColor: "#000000a0",
  padding: { x: 6, y: 3 },
};

/** What a probe needs to assert a villager without taking a screenshot. */
export type NpcSnapshot = Readonly<{
  slot: number;
  name: string;
  x: number;
  y: number;
  /**
   * True while this villager is the player's current interaction target - the nearest one inside
   * talking range, as resolved by `npcInteractionTarget`. It is the same condition that shows the
   * talk prompt, so a probe asserting `inRange` is asserting what the player can actually see.
   */
  inRange: boolean;
}>;

export interface NpcOpts {
  scene: Phaser.Scene;
  /** Manifest slot, 0..3. Identifies which published strip and which dialogue lines are this NPC's. */
  slot: number;
  /** Display name, shown on the world-space label and spoken as the dialogue speaker. */
  name: string;
  /**
   * World x of the villager's feet, from `planNpcPlacements`.
   *
   * The terrain column is derived from this rather than taken separately, so the foot can never
   * be anchored to a column the sprite is not standing on - the same rule `Mob.update` re-applies
   * every frame as a mob wanders across a slope.
   */
  spawnX: number;
  tilePx: number;
  worldWidthPx: number;
  baselineY: number;
  /** Terrain height in tiles for a column, clamped by the caller's heightmap accessor. */
  heightFn: (col: number) => number;
  /** Texture key of this NPC's drawn sheet, e.g. `npc_0_still` or `npc_0_idle`. */
  idleTextureKey: string;
  /**
   * Whether this resident must be mirrored to face the player.
   *
   * True for side-view artwork, which is drawn facing one edge and has to be flipped to look at
   * a player on the other side. False for a forward-facing still: it is already looking at the
   * player from every position, and flipping it only reverses what is asymmetric about the
   * figure - the hand a tool is held in, the side an apron ties on.
   *
   */
  facesPlayer: boolean;
  /** This NPC's required published idle-or-still reference. */
  scaleReference: ScaleReference;
  /** The player's published idle-sheet reference, the size every other actor is matched against. */
  playerScaleReference: ScaleReference;
  /** The player's drawn height in world pixels, i.e. `PlayerOpts.targetSpriteHeight`. */
  playerTargetSpriteHeight: number;
  /** Frame-zero height of the player's idle sheet, in that sheet's own source pixels. */
  playerStandingFrameHeight: number;
  /** Dialogue lines for this villager, in order. Empty when the run publishes none. */
  lines?: readonly string[];
}

export class Npc {
  readonly sprite: Phaser.GameObjects.Sprite;
  readonly slot: number;
  readonly name: string;
  readonly lines: readonly string[];
  private readonly opts: NpcOpts;
  private readonly nameLabel: Phaser.GameObjects.Text;
  private readonly talkPrompt: Phaser.GameObjects.Text;
  private interactionTarget = false;

  constructor(opts: NpcOpts) {
    this.opts = opts;
    this.slot = opts.slot;
    this.name = opts.name;
    this.lines = opts.lines ?? [];

    const scene = opts.scene;
    const sprite = scene.add.sprite(opts.spawnX, opts.baselineY, opts.idleTextureKey, 0);
    // Feet at the sprite's y, exactly like the player and mobs, so one terrain surface value
    // positions every actor in the scene the same way.
    sprite.setOrigin(0.5, 1.0);
    sprite.setDepth(SCENE_CONTENT_DEPTH.mob);
    this.sprite = sprite;
    this.resolveSpriteScale();

    // Clamping happens after the scale is known, not before. A mob can precompute its lane
    // because `mobRenderEnvelope` measures its alpha crop up front; here the drawn width is only
    // decided once the head match resolves, so the villager is nudged inside the world edge at
    // the end of construction instead.
    const halfWidth = sprite.displayWidth / 2;
    const x = Phaser.Math.Clamp(
      opts.spawnX,
      Math.min(halfWidth, opts.worldWidthPx / 2),
      Math.max(opts.worldWidthPx - halfWidth, opts.worldWidthPx / 2),
    );
    const column = Math.max(0, Math.floor(x / opts.tilePx));
    const footY = terrainSurfaceY(
      opts.heightFn(column),
      opts.tilePx,
      opts.baselineY,
    );
    sprite.setPosition(x, footY);
    // No `play`. The sprite was constructed on frame 0 and stays there.

    const drawnHeight = this.drawnHeight();
    const label = scene.add.text(
      x,
      footY - drawnHeight - NAME_LABEL_GAP_PX,
      opts.name,
      NAME_LABEL_STYLE,
    );
    label.setOrigin(0.5, 1);
    // World space on purpose: the label belongs to a spot in the town and has to scroll with it.
    //
    // Drawn above the whole actor band. It was briefly at `prop` depth on the reasoning that the
    // label clears the villager's own tallest frame - which is true, and irrelevant: the sprite
    // it actually collides with is the *player*, who stands at `player` depth directly in front
    // of a resident they are close enough to talk to. Rendered at the town's own depth the name
    // and prompt disappeared behind the player's head at exactly the moment they became useful.
    label.setScrollFactor(1);
    label.setDepth(SCENE_CONTENT_DEPTH.effect);
    this.nameLabel = label;

    const prompt = scene.add.text(
      x,
      label.y - label.displayHeight - TALK_PROMPT_GAP_PX,
      NPC_TALK_PROMPT_TEXT,
      TALK_PROMPT_STYLE,
    );
    prompt.setOrigin(0.5, 1);
    prompt.setScrollFactor(1);
    prompt.setDepth(SCENE_CONTENT_DEPTH.effect);
    // Stacked above the name rather than replacing it, so nothing on screen moves when the player
    // walks into range - only the prompt appears.
    prompt.setVisible(false);
    this.talkPrompt = prompt;
  }

  /**
   * Draw this villager at the same apparent size as the player.
   *
   * The whole point of the village is that a townsfolk sprite reads as a person standing next to
   * the player, and the naive route - normalise every strip to a fixed pixel height, which is
   * what `Mob` does - cannot deliver that. It normalises the *cell*, not the subject: a villager
   * drawn small inside a tall cell renders small, and one drawn edge to edge renders large, from
   * the same target height. Separately generated sheets really do disagree by that much;
   * `sprite-scale.ts` records one run where the same character's head spanned 223px on the idle
   * sheet and 47px on the climb sheet.
   *
   * So the recipe measures a head extent per sheet and publishes it, and the runtime equates
   * `extent * scale` between this NPC's strip and the player's idle sheet - the identical
   * mechanism `Player.resolveSheetScales` uses to reconcile the player's own sheets against each
   * other. Both measurements belong to the current runtime contract; constructing an NPC without
   * either one is invalid rather than a request to guess from the cell canvas.
   */
  private resolveSpriteScale(): void {
    const playerReference = this.opts.playerScaleReference;
    this.sprite.setScale(
      headMatchedScale(
        {
          extentPixels: playerReference.extentPixels,
          scale: masterSheetScale(
            this.opts.playerTargetSpriteHeight,
            this.opts.playerStandingFrameHeight,
          ),
        },
        this.opts.scaleReference,
      ),
    );
  }

  /** Drawn height of the tallest cell in the idle loop, in world pixels. */
  /**
   * Height of the frame actually on screen, for placing the name above it.
   *
   * Frame zero, not the tallest cell in the sheet. While the villager was animated this had to
   * clear the whole loop, because Phaser holds the construction-time scale as frames swap and a
   * gesture phase drawn taller than the rest pose would have slid up behind the label. A still
   * villager has no other frame to clear, so measuring the loop now would push every name a gap
   * further up than the art it belongs to.
   */
  private drawnHeight(): number {
    return this.sprite.displayHeight;
  }

  /**
   * Turn to the player and offer, or withdraw, the talk prompt.
   *
   * `isInteractionTarget` is resolved by the scene through `npcInteractionTarget`, which already
   * applies the range test and picks the nearest villager, so two townsfolk standing close
   * together never both offer a prompt.
   *
   * Side-view art faces right - the recipe's `REQUIRED_SIDE_VIEW_FACING`, enforced by the same
   * `reviews_facing` gate the mob strips go through - so a player to the left is faced by
   * flipping. Deriving facing from the player's position each frame rather than storing it means
   * a villager cannot end up staring at a wall after the player walks around them.
   *
   * A forward-facing still is left alone. It is drawn looking out of the screen, held to
   * `front` by the same review, and there is no position the player can stand in that it is not
   * already facing.
   */
  update(playerX: number, isInteractionTarget: boolean): void {
    if (this.opts.facesPlayer) {
      this.sprite.setFlipX(playerX < this.sprite.x);
    }
    if (isInteractionTarget !== this.interactionTarget) {
      this.interactionTarget = isInteractionTarget;
      this.talkPrompt.setVisible(isInteractionTarget);
    }
  }

  /** World x of the villager's feet, for the scene's interaction-target query. */
  get x(): number {
    return this.sprite.x;
  }

  /** Release every object this villager owns. Called by the stage teardown. */
  destroy(): void {
    this.talkPrompt.destroy();
    this.nameLabel.destroy();
    this.sprite.destroy();
  }

  snapshot(): NpcSnapshot {
    return {
      slot: this.slot,
      name: this.name,
      x: this.sprite.x,
      y: this.sprite.y,
      inRange: this.interactionTarget,
    };
  }
}
