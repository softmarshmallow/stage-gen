// Inventory overlay (Phase 7).
//
// Renders the chroma-keyed inventory_<tag>.png panel as a HUD overlay
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

export const INVENTORY_PANEL_W = 1536;
export const INVENTORY_PANEL_H = 1024;
export const SLOT_CENTRES: { col: number; row: number; x: number; y: number }[] = [
  // Row 0
  { col: 0, row: 0, x: 336, y: 368 },
  { col: 1, row: 0, x: 624, y: 368 },
  { col: 2, row: 0, x: 912, y: 368 },
  { col: 3, row: 0, x: 1200, y: 368 },
  // Row 1
  { col: 0, row: 1, x: 336, y: 656 },
  { col: 1, row: 1, x: 624, y: 656 },
  { col: 2, row: 1, x: 912, y: 656 },
  { col: 3, row: 1, x: 1200, y: 656 },
];

export interface InventoryHudOpts {
  scene: Phaser.Scene;
  /** Phaser texture key holding the chroma-keyed inventory panel. */
  panelKey: string;
  /** Phaser texture key holding the items grid. */
  itemsKey: string;
  /** items_x → frame name on the items texture. */
  itemFrameKey: (kindIndex: number) => string;
  viewW: number;
  viewH: number;
  /** Display scale of the panel inside the viewport. */
  scale?: number;
}

type SlotEntry = { kindIndex: number; count: number; icon: Phaser.GameObjects.Image };

export class InventoryHud {
  private opts: InventoryHudOpts;
  private container: Phaser.GameObjects.Container;
  private panelImg: Phaser.GameObjects.Image | null = null;
  private slots: Map<number, SlotEntry> = new Map();
  private countTexts: Map<number, Phaser.GameObjects.Text> = new Map();
  visible = true;
  private scaleFactor: number;

  constructor(opts: InventoryHudOpts) {
    this.opts = opts;

    // Display the panel scaled down — scale factor chosen so it fits ~30% of viewport width.
    const desiredW = Math.floor(opts.viewW * 0.34);
    this.scaleFactor = opts.scale ?? desiredW / INVENTORY_PANEL_W;

    // Place at top-right with padding.
    const panelDisplayW = INVENTORY_PANEL_W * this.scaleFactor;
    const panelDisplayH = INVENTORY_PANEL_H * this.scaleFactor;
    const px = opts.viewW - panelDisplayW - 8;
    const py = 8;

    this.container = opts.scene.add.container(px, py);
    this.container.setScrollFactor(0);
    this.container.setDepth(2000);

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
    const slotIdx = kindIndex % SLOT_CENTRES.length;
    const slot = SLOT_CENTRES[slotIdx];
    const sx = slot.x * this.scaleFactor;
    const sy = slot.y * this.scaleFactor;
    const iconSizeWorld = 192 * this.scaleFactor; // ~75% of 256-px slot

    if (!this.opts.scene.textures.exists(this.opts.itemsKey)) {
      // No texture — still create a placeholder rectangle so the slot is filled.
      const g = this.opts.scene.add.rectangle(sx, sy, iconSizeWorld, iconSizeWorld, 0x00ff88, 0.6);
      this.container.add(g);
      // Track via fake icon ref.
      this.slots.set(kindIndex, {
        kindIndex,
        count: 1,
        icon: g as unknown as Phaser.GameObjects.Image,
      });
      return;
    }
    const frameKey = this.opts.itemFrameKey(kindIndex);
    const tex = this.opts.scene.textures.get(this.opts.itemsKey);
    const phaserFrame = tex.get(frameKey);
    const aspect = (phaserFrame?.width ?? 1) / Math.max(1, phaserFrame?.height ?? 1);
    const icon = this.opts.scene.add.image(sx, sy, this.opts.itemsKey, frameKey);
    icon.setOrigin(0.5, 0.5);
    icon.setDisplaySize(iconSizeWorld * aspect, iconSizeWorld);
    this.container.add(icon);

    const txt = this.opts.scene.add.text(sx + iconSizeWorld * 0.3, sy + iconSizeWorld * 0.3, "x1", {
      fontFamily: "ui-monospace, Menlo, monospace",
      fontSize: `${Math.max(10, Math.floor(iconSizeWorld * 0.18))}px`,
      color: "#e6e6e6",
    });
    txt.setOrigin(0, 0);
    this.container.add(txt);
    this.countTexts.set(kindIndex, txt);

    this.slots.set(kindIndex, { kindIndex, count: 1, icon });
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
      slotIndex: s.kindIndex % SLOT_CENTRES.length,
      count: s.count,
      // World-space coordinates (relative to the screen, since scrollFactor=0).
      x: s.icon.x + this.container.x,
      y: s.icon.y + this.container.y,
      // Expected (target) slot centre on the panel canvas.
      expectedPanelX: SLOT_CENTRES[s.kindIndex % SLOT_CENTRES.length].x,
      expectedPanelY: SLOT_CENTRES[s.kindIndex % SLOT_CENTRES.length].y,
    }));
  }
}
