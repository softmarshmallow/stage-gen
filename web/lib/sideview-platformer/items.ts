// Items system (Phase 7).
//
// Drops one item-sheet cell at a position when a mob dies (TC-086) and
// supports gravity-fall to the ground baseline. The scene polls for
// player overlap and calls collect() on contact (TC-087).

import Phaser from "phaser";
import { SCENE_CONTENT_DEPTH } from "./depths";
import { terrainSurfaceY } from "./terrain";

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
  /** Phaser image displayed in the world. */
  sprite: Phaser.GameObjects.Image;
  /** True once the item has settled to ground. */
  settled: boolean;
  /** Vertical velocity (px/s) while falling. */
  vy: number;
  /** Horizontal pop velocity (px/s), halved by the landing bounce and gone once settled. */
  vx: number;
  /** Bounces taken so far; the arc allows exactly one before the drop settles. */
  bounces: number;
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

const GRAVITY_PX = 1500;

// A drop *pops*: it leaves the corpse with an upward and sideways velocity, bounces once, and only
// then settles into its bob. Before this it fell straight down from a tile above the kill, which
// read as an item appearing rather than as something being knocked loose. The velocities are seeded
// from the drop's own sequence number, so the same kill in the same run pops the same way twice,
// which is what a fixed-frame capture needs and what a tween never provides.
export const DROP_POP_VX_MIN_PX = 60;
export const DROP_POP_VX_SPAN_PX = 80;
export const DROP_POP_VY_MIN_PX = 260;
export const DROP_POP_VY_SPAN_PX = 120;
export const DROP_BOUNCE_RESTITUTION = 0.35;
/** A landing slower than this settles outright; bouncing a crawl reads as jitter. */
export const DROP_BOUNCE_MIN_VY_PX = 120;
export const DROP_BOUNCE_VX_RETAINED = 0.5;

export type DropDirection = 1 | -1 | 0;

function dropUnitNoise(sequence: number, channel: number): number {
  let hash = (Math.imul(sequence ^ channel, 0x9e3779b1) ^ (sequence >>> 15)) >>> 0;
  hash = Math.imul(hash ^ (hash >>> 13), 0x85ebca6b) >>> 0;
  hash = Math.imul(hash ^ (hash >>> 16), 0xc2b2ae35) >>> 0;
  return hash / 4294967296;
}

/**
 * The launch velocity for one drop, in pixels per second.
 *
 * `dirSign` is the direction the blow travelled, so loot flies away from the striker as the mob
 * does; zero alternates by sequence, for callers that have no blow to report.
 */
export function dropPopVelocity(
  sequence: number,
  dirSign: DropDirection,
): Readonly<{ vx: number; vy: number }> {
  if (!Number.isSafeInteger(sequence) || sequence < 0) {
    throw new Error("drop pop velocity requires a nonnegative sequence");
  }
  const direction = dirSign === 0 ? (sequence % 2 === 0 ? 1 : -1) : dirSign;
  return Object.freeze({
    vx: direction * (DROP_POP_VX_MIN_PX + dropUnitNoise(sequence, 0x11) * DROP_POP_VX_SPAN_PX),
    vy: -(DROP_POP_VY_MIN_PX + dropUnitNoise(sequence, 0x22) * DROP_POP_VY_SPAN_PX),
  });
}

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
    const launch = dropPopVelocity(this.nextDropId, dirSign);
    const item: DroppedItem = {
      id: `drop_${this.nextDropId}`,
      kindIndex,
      sprite,
      settled: false,
      vy: launch.vy,
      vx: launch.vx,
      bounces: 0,
    };
    this.nextDropId += 1;
    this.items.push(item);
    return item;
  }

  update(dtMs: number, nowMs: number) {
    const dt = dtMs / 1000;
    for (const it of this.items) {
      if (it.settled) {
        // Gentle bob.
        const bob = Math.sin(nowMs / 200 + it.kindIndex) * 2;
        it.sprite.y = it.sprite.getData("groundY") + bob;
        continue;
      }
      it.vy += GRAVITY_PX * dt;
      it.sprite.y += it.vy * dt;
      it.sprite.x += it.vx * dt;
      const worldWidth = this.opts.worldWidthPx;
      if (worldWidth !== undefined) {
        const margin = this.opts.tilePx / 2;
        it.sprite.x = Math.max(margin, Math.min(worldWidth - margin, it.sprite.x));
      }
      const col = Math.floor(it.sprite.x / this.opts.tilePx);
      const colH = this.opts.heightFn(col);
      const surfaceY = terrainSurfaceY(
        colH,
        this.opts.tilePx,
        this.opts.baselineY,
      );
      if (it.sprite.y >= surfaceY) {
        it.sprite.y = surfaceY;
        if (it.bounces < 1 && it.vy > DROP_BOUNCE_MIN_VY_PX) {
          it.vy = -it.vy * DROP_BOUNCE_RESTITUTION;
          it.vx *= DROP_BOUNCE_VX_RETAINED;
          it.bounces += 1;
          continue;
        }
        it.settled = true;
        it.vy = 0;
        it.vx = 0;
        it.sprite.setData("groundY", surfaceY);
      }
    }
  }

  /**
   * Test whether the player rectangle overlaps any settled (or even falling)
   * item. On overlap, remove the item from the world and return its info.
   */
  tryPickup(playerX: number, playerY: number, radiusPx: number): DroppedItem[] {
    const picked: DroppedItem[] = [];
    for (let i = this.items.length - 1; i >= 0; i--) {
      const it = this.items[i];
      const dx = it.sprite.x - playerX;
      const dy = it.sprite.y - playerY;
      // Cheap circle test, generous radius — player overlap is forgiving.
      if (Math.abs(dx) < radiusPx && Math.abs(dy) < radiusPx * 1.5) {
        it.sprite.destroy();
        this.items.splice(i, 1);
        picked.push(it);
      }
    }
    return picked;
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
        x: it.sprite.x,
        y: it.sprite.y,
        settled: it.settled,
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
