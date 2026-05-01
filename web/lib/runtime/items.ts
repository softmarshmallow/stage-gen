// Items system (Phase 7).
//
// Drops one item-sheet cell at a position when a mob dies (TC-086) and
// supports gravity-fall to the ground baseline. The scene polls for
// player overlap and calls collect() on contact (TC-087).

import Phaser from "phaser";

export type ItemKindIndex = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | number;

export interface DroppedItem {
  /** Index 0..7 into the world's items palette (and items_<tag>.png cell). */
  kindIndex: number;
  /** Phaser image displayed in the world. */
  sprite: Phaser.GameObjects.Image;
  /** True once the item has settled to ground. */
  settled: boolean;
  /** Vertical velocity (px/s) while falling. */
  vy: number;
}

export interface ItemSystemOpts {
  scene: Phaser.Scene;
  tilePx: number;
  baselineY: number;
  heightFn: (col: number) => number;
  /** Frame keys on the items texture (e.g. "item_0".."item_7"). */
  itemFrameKey: (kindIndex: number) => string;
  itemTextureKey: string;
  itemHeightPx?: number;
}

const GRAVITY_PX = 1500;

export class ItemSystem {
  readonly items: DroppedItem[] = [];
  private opts: ItemSystemOpts;

  constructor(opts: ItemSystemOpts) {
    this.opts = opts;
  }

  /**
   * Drop a single item at world coords (x, y). The item falls under gravity
   * until it lands on the heightmap surface for that column.
   */
  drop(x: number, y: number, kindIndex: number): DroppedItem | null {
    const tex = this.opts.itemTextureKey;
    const frameKey = this.opts.itemFrameKey(kindIndex);
    if (!this.opts.scene.textures.exists(tex)) return null;
    const sprite = this.opts.scene.add.image(x, y, tex, frameKey);
    sprite.setOrigin(0.5, 1.0);
    const targetH = this.opts.itemHeightPx ?? Math.floor(this.opts.tilePx * 0.7);
    const phaserFrame = this.opts.scene.textures.get(tex).get(frameKey);
    const aspect = (phaserFrame?.width ?? 1) / Math.max(1, phaserFrame?.height ?? 1);
    sprite.setDisplaySize(targetH * aspect, targetH);
    sprite.setDepth(850);
    const item: DroppedItem = { kindIndex, sprite, settled: false, vy: 0 };
    this.items.push(item);
    return item;
  }

  update(dtMs: number) {
    const dt = dtMs / 1000;
    for (const it of this.items) {
      if (it.settled) {
        // Gentle bob.
        const bob = Math.sin(performance.now() / 200 + it.kindIndex) * 2;
        it.sprite.y = it.sprite.getData("groundY") + bob;
        continue;
      }
      it.vy += GRAVITY_PX * dt;
      it.sprite.y += it.vy * dt;
      const col = Math.floor(it.sprite.x / this.opts.tilePx);
      const colH = this.opts.heightFn(col);
      const surfaceY = this.opts.baselineY - colH * this.opts.tilePx;
      if (it.sprite.y >= surfaceY) {
        it.sprite.y = surfaceY;
        it.settled = true;
        it.vy = 0;
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

  snapshot() {
    return this.items.map((it) => ({
      kindIndex: it.kindIndex,
      x: it.sprite.x,
      y: it.sprite.y,
      settled: it.settled,
    }));
  }
}
