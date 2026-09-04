// The platformer's drops: the `loot` family's bodies, drawn in Phaser.
//
// What left this file is the arithmetic and the state. A drop's position used
// to live on its sprite — `sprite.x`, `sprite.y` and a `groundY` in Phaser's
// `setData` bag — so "where is the loot" was a question only a renderer could
// answer; it is a `DropBody` now, and the sprite is mirrored from it. The pop,
// the single bounce and the settle into a bob are `stepDrop`, over a surface
// port this file answers from the terrain. What is left here is the drop *view*
// (TC-086) and the genre's own reach test for a pickup (TC-087).

import Phaser from "phaser";
import { SCENE_CONTENT_DEPTH } from "./depths";
import { terrainSurfaceY } from "./terrain";
import {
  collectDrops,
  launchDrop,
  stepDrop,
  type DropBody,
  type DropDirection,
} from "@/lib/families/loot";

export type ItemKindIndex = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | number;

export interface DroppedItem {
  /**
   * Identity for one drop, unique within its system and stable for its whole life.
   *
   * Position cannot serve as identity — two drops from the same kill land a few units apart and
   * then bob — and the array index is reused the moment anything is picked up. Anything that
   * follows a particular drop across frames needs this.
   */
  id: string;
  /** Index 0..7 into the world's items palette (and items_<tag>.png cell). */
  kindIndex: number;
  /** Phaser image displayed in the world, mirrored from `body` after every step. */
  sprite: Phaser.GameObjects.Image;
  /** Where the drop is and what it is doing, as the family's value. */
  body: DropBody;
}

export interface ItemSystemOpts {
  scene: Phaser.Scene;
  tilePx: number;
  baselineY: number;
  heightFn: (col: number) => number;
  /** Frame keys on the items texture (e.g. "item_0".."item_7"). */
  itemFrameKey?: (kindIndex: number) => string | number | undefined;
  itemTextureKey: string | ((kindIndex: number) => string);
  itemHeightPx?: number;
  /** World width, so a pop never carries a drop off the edge of the map. */
  worldWidthPx?: number;
}

export type { DropDirection };

/**
 * The launch velocity for one drop, in pixels per second.
 *
 * Re-exported at the genre's own name because the platformer's suite pins these
 * numbers; the arithmetic is the family's.
 */
export {
  dropPopVelocity,
  DROP_BOUNCE_RESTITUTION,
  DROP_BOUNCE_VX_RETAINED,
} from "@/lib/families/loot";

/**
 * The pop numbers at this genre's own names, in pixels.
 *
 * The family carries them unit-free — a drop pops the same way whether the
 * world is measured in pixels or in track columns — and the platformer's suite
 * pins them as pixels, which is what these aliases say.
 */
export {
  DROP_BOUNCE_MIN_VY as DROP_BOUNCE_MIN_VY_PX,
  DROP_POP_VX_MIN as DROP_POP_VX_MIN_PX,
  DROP_POP_VX_SPAN as DROP_POP_VX_SPAN_PX,
  DROP_POP_VY_MIN as DROP_POP_VY_MIN_PX,
  DROP_POP_VY_SPAN as DROP_POP_VY_SPAN_PX,
} from "@/lib/families/loot";

export class ItemSystem {
  readonly items: DroppedItem[] = [];
  private opts: ItemSystemOpts;
  private nextDropId = 1;

  constructor(opts: ItemSystemOpts) {
    this.opts = opts;
  }

  /**
   * Drop a single item at world coords (x, y). The item pops away from the blow, bounces once,
   * and settles on the heightmap surface for whichever column it lands in.
   */
  drop(x: number, y: number, kindIndex: number, dirSign: DropDirection = 0): DroppedItem | null {
    const tex =
      typeof this.opts.itemTextureKey === "function"
        ? this.opts.itemTextureKey(kindIndex)
        : this.opts.itemTextureKey;
    const frameKey = this.opts.itemFrameKey?.(kindIndex);
    if (!this.opts.scene.textures.exists(tex)) return null;
    const sprite = this.opts.scene.add.image(x, y, tex, frameKey);
    sprite.setOrigin(0.5, 1.0);
    const targetH =
      this.opts.itemHeightPx ?? Math.floor(this.opts.tilePx * 0.7);
    const phaserFrame = this.opts.scene.textures.get(tex).get(frameKey);
    const aspect =
      (phaserFrame?.width ?? 1) / Math.max(1, phaserFrame?.height ?? 1);
    sprite.setDisplaySize(targetH * aspect, targetH);
    sprite.setDepth(SCENE_CONTENT_DEPTH.item);
    const item: DroppedItem = {
      id: `drop_${this.nextDropId}`,
      kindIndex,
      sprite,
      // The bob's phase is the catalog kind, which is what it has always been:
      // two tarts resting side by side rise together and a tart beside a dart
      // does not.
      body: launchDrop(x, y, this.nextDropId, dirSign, kindIndex),
    };
    this.nextDropId += 1;
    this.items.push(item);
    return item;
  }

  /**
   * Step every drop, and mirror each body onto the sprite that pictures it.
   *
   * The surface is the family's port, answered here from the terrain heightmap
   * — the same `terrainSurfaceY` the controller stands on, so a drop and the
   * body that walks over it agree about where the ground is.
   */
  update(dtMs: number, nowMs: number) {
    const margin = this.opts.tilePx / 2;
    const worldWidth = this.opts.worldWidthPx;
    for (const it of this.items) {
      stepDrop(it.body, dtMs, nowMs, {
        surfaceAt: (x) =>
          terrainSurfaceY(
            this.opts.heightFn(Math.floor(x / this.opts.tilePx)),
            this.opts.tilePx,
            this.opts.baselineY,
          ),
        clampX:
          worldWidth === undefined
            ? undefined
            : (x) => Math.max(margin, Math.min(worldWidth - margin, x)),
      });
      it.sprite.x = it.body.x;
      it.sprite.y = it.body.y;
    }
  }

  /**
   * Which drops the body is standing over, taken and removed.
   *
   * The reach test is this genre's — a cheap, forgiving circle in pixels, wider
   * than it is tall because a player is — and the resolution is the `loot`
   * family's. The candidates are handed over back to front and the removals are
   * taken in that same order, which is what the array-splicing loop this
   * replaced did: two drops taken on one frame are two events, and which comes
   * first is what a replay hashes.
   */
  tryPickup(playerX: number, playerY: number, radiusPx: number): readonly DroppedItem[] {
    const candidates = [...this.items].reverse();
    const { taken } = collectDrops<DroppedItem>({
      candidates,
      key: (item) => item.id,
      reached: (item) =>
        Math.abs(item.body.x - playerX) < radiusPx &&
        Math.abs(item.body.y - playerY) < radiusPx * 1.5,
    });
    for (const item of taken) {
      item.sprite.destroy();
      this.items.splice(this.items.indexOf(item), 1);
    }
    return taken;
  }

  /** Remove one presentation-only or live drop without disturbing its peers. */
  remove(item: DroppedItem): void {
    const index = this.items.indexOf(item);
    if (index < 0) return;
    if (item.sprite.active) item.sprite.destroy();
    this.items.splice(index, 1);
  }

  /** Drop every live item, used when a stage is torn down for the next one. */
  clearAll(): void {
    for (const item of this.items) {
      if (item.sprite.active) item.sprite.destroy();
    }
    this.items.length = 0;
  }

  snapshot() {
    return this.items.map((it) => {
      const bounds = it.sprite.getBounds();
      return {
        kindIndex: it.kindIndex,
        x: it.body.x,
        y: it.body.y,
        settled: it.body.settled,
        renderBounds: {
          left: bounds.left,
          right: bounds.right,
          top: bounds.top,
          bottom: bounds.bottom,
        },
      };
    });
  }
}
