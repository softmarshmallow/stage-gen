// Inventory overlay (Phase 7).
//
// Renders the canonical-alpha inventory_<tag>.png panel as a HUD overlay
// (toggled with I, default visible) and composites picked-up items into
// the panel's contracted slot positions (TC-088).
//
// Slot geometry — from docs/spec/asset-contracts.md § Inventory:
//   Outer panel:  1280×704   placed at (128, 160) in the 1536×1024 canvas
//   Slot block:   top-left (208, 240) inside the canvas
//   Slot size:    256 × 256
//   Slot gutter:  32
//   Grid:         4 cols × 2 rows
//
// Slot CENTRES (in panel/inventory-canvas pixels):
//   col c → x = 208 + 256/2 + c*(256+32) = 336 + c*288
//   row r → y = 240 + 256/2 + r*(256+32) = 368 + r*288
// →  cols  336, 624, 912, 1200
// →  rows  368, 656

import Phaser from "phaser";
import { SCENE_CONTENT_DEPTH } from "./layers";
import {
  INVENTORY_GRID_4X2_V1,
  type InventoryPanelLayout,
} from "@/lib/manifest/inventory-layout";

export const INVENTORY_PANEL_W = INVENTORY_GRID_4X2_V1.canvas.width;
export const INVENTORY_PANEL_H = INVENTORY_GRID_4X2_V1.canvas.height;
export const SLOT_CENTRES: {
  col: number;
  row: number;
  x: number;
  y: number;
}[] = INVENTORY_GRID_4X2_V1.slots.map((slot, index) => ({
  col: index % 4,
  row: Math.floor(index / 4),
  x: slot.x + slot.width / 2,
  y: slot.y + slot.height / 2,
}));

export interface InventoryHudOpts {
  scene: Phaser.Scene;
  /** Phaser texture key holding the canonical inventory panel. */
  panelKey: string;
  /** Phaser texture key holding the items grid. */
  itemsKey?: string;
  /** Optional stable-ID texture resolver for prepared packages with one image per item. */
  itemTextureKey?: (kindIndex: number) => string;
  /** items_x → frame name on the items texture. */
  itemFrameKey?: (kindIndex: number) => string | number | undefined;
  viewW: number;
  viewH: number;
  /** Resolved manifest geometry; mature callers use the exact V1 default. */
  layout?: InventoryPanelLayout;
  /** Display scale of the panel inside the viewport. */
  scale?: number;
}

type SlotEntry = {
  kindIndex: number;
  count: number;
  icon: Phaser.GameObjects.Image;
};

export class InventoryHud {
  private opts: InventoryHudOpts;
  private container: Phaser.GameObjects.Container;
  private panelImg: Phaser.GameObjects.Image | null = null;
  private slots: Map<number, SlotEntry> = new Map();
  private countTexts: Map<number, Phaser.GameObjects.Text> = new Map();
  visible = true;
  private scaleFactor: number;
  private readonly slotCentres: readonly { x: number; y: number }[];
  private panelBounds: Readonly<{
    left: number;
    right: number;
    top: number;
    bottom: number;
  }>;

  constructor(opts: InventoryHudOpts) {
    this.opts = opts;
    const layout = opts.layout ?? INVENTORY_GRID_4X2_V1;
    this.slotCentres = layout.slots.map((slot) => ({
      x: slot.x + slot.width / 2,
      y: slot.y + slot.height / 2,
    }));

    // Display the panel scaled down — scale factor chosen so it fits ~30% of viewport width.
    const desiredW = Math.floor(opts.viewW * 0.34);
    this.scaleFactor = opts.scale ?? desiredW / layout.canvas.width;

    // Place at top-right inside the capture-safe margin.
    const panelDisplayW = layout.canvas.width * this.scaleFactor;
    const panelDisplayH = layout.canvas.height * this.scaleFactor;
    const safeMargin = 24;
    const px = opts.viewW - panelDisplayW - safeMargin;
    const py = safeMargin;
    this.panelBounds = Object.freeze({
      left: px,
      right: px + panelDisplayW,
      top: py,
      bottom: py + panelDisplayH,
    });

    this.container = opts.scene.add.container(px, py);
    this.container.setScrollFactor(0);
    this.container.setDepth(SCENE_CONTENT_DEPTH.hud);

    if (opts.scene.textures.exists(opts.panelKey)) {
      const img = opts.scene.add.image(0, 0, opts.panelKey);
      img.setOrigin(0, 0);
      img.setDisplaySize(panelDisplayW, panelDisplayH);
      this.container.add(img);
      this.panelImg = img;
    }
  }

  addItem(kindIndex: number) {
    const existing = this.slots.get(kindIndex);
    if (existing) {
      existing.count += 1;
      const t = this.countTexts.get(kindIndex);
      if (t) t.setText(`x${existing.count}`);
      return;
    }
    const slotIdx = kindIndex % this.slotCentres.length;
    const slot = this.slotCentres[slotIdx];
    const sx = slot.x * this.scaleFactor;
    const sy = slot.y * this.scaleFactor;
    const iconSizeWorld = 192 * this.scaleFactor; // ~75% of 256-px slot

    const textureKey =
      this.opts.itemTextureKey?.(kindIndex) ?? this.opts.itemsKey ?? "";
    if (!textureKey || !this.opts.scene.textures.exists(textureKey)) {
      // No texture — still create a placeholder rectangle so the slot is filled.
      const g = this.opts.scene.add.rectangle(
        sx,
        sy,
        iconSizeWorld,
        iconSizeWorld,
        0x00ff88,
        0.6,
      );
      this.container.add(g);
      // Track via fake icon ref.
      this.slots.set(kindIndex, {
        kindIndex,
        count: 1,
        icon: g as unknown as Phaser.GameObjects.Image,
      });
      return;
    }
    const frameKey = this.opts.itemFrameKey?.(kindIndex);
    const tex = this.opts.scene.textures.get(textureKey);
    const phaserFrame = tex.get(frameKey);
    const aspect =
      (phaserFrame?.width ?? 1) / Math.max(1, phaserFrame?.height ?? 1);
    const icon = this.opts.scene.add.image(
      sx,
      sy,
      textureKey,
      frameKey,
    );
    icon.setOrigin(0.5, 0.5);
    icon.setDisplaySize(iconSizeWorld * aspect, iconSizeWorld);
    this.container.add(icon);

    const txt = this.opts.scene.add.text(
      sx + iconSizeWorld * 0.3,
      sy + iconSizeWorld * 0.3,
      "x1",
      {
        fontFamily: "ui-monospace, Menlo, monospace",
        fontSize: `${Math.max(10, Math.floor(iconSizeWorld * 0.18))}px`,
        color: "#e6e6e6",
      },
    );
    txt.setOrigin(0, 0);
    this.container.add(txt);
    this.countTexts.set(kindIndex, txt);

    this.slots.set(kindIndex, { kindIndex, count: 1, icon });
  }

  /**
   * Spend one of a stack, emptying the slot when the last one goes.
   *
   * The panel is a picture of what the player carries, so a consumed item has to leave it. An
   * emptied slot is torn down rather than left showing "x0", which also frees the slot for the
   * next kind that lands on the same index.
   */
  removeItem(kindIndex: number): void {
    const existing = this.slots.get(kindIndex);
    if (!existing) return;
    existing.count -= 1;
    if (existing.count > 0) {
      this.countTexts.get(kindIndex)?.setText(`x${existing.count}`);
      return;
    }
    existing.icon.destroy();
    this.countTexts.get(kindIndex)?.destroy();
    this.countTexts.delete(kindIndex);
    this.slots.delete(kindIndex);
  }

  toggle() {
    this.visible = !this.visible;
    this.container.setVisible(this.visible);
  }

  setVisible(v: boolean) {
    this.visible = v;
    this.container.setVisible(v);
  }

  snapshot() {
    return Array.from(this.slots.values()).map((s) => ({
      kindIndex: s.kindIndex,
      slotIndex: s.kindIndex % this.slotCentres.length,
      count: s.count,
      // World-space coordinates (relative to the screen, since scrollFactor=0).
      x: s.icon.x + this.container.x,
      y: s.icon.y + this.container.y,
      // Expected (target) slot centre on the panel canvas.
      expectedPanelX: this.slotCentres[s.kindIndex % this.slotCentres.length].x,
      expectedPanelY: this.slotCentres[s.kindIndex % this.slotCentres.length].y,
    }));
  }

  bounds() {
    return this.panelBounds;
  }
}
