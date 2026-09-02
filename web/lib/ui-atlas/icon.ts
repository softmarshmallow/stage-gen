// One glyph from the generated icon grid, drawn at a size the HUD chooses.
//
// An icon is content, never a surface: it is composed onto a button or beside a readout, and
// switches glyph rather than state. The manifest's published cells map onto texture frames
// one-to-one, keyed by glyph, so every icon drawn from the same sheet shares them and a sheet
// replaced by the runtime stand-in still resolves, because the stand-in is the whole canvas.
//
// Sizing scales the whole cell rather than the detected glyph bounds: the set was drawn as one
// family at one density, and fitting each glyph's own bounds to the target would make a pause
// bar as wide as a house. `size` is the cell's on-screen side; the glyph inside it keeps the
// proportion the artist gave it.

import type Phaser from "phaser";
import type { UiIconGlyph, UiIconSetLayout } from "../manifest/ui-icon-layout";
import { uiIconCellFor, uiIconNativeSize } from "../manifest/ui-icon-layout";

/** The frame registered on `sheetKey` for one glyph. */
export function iconFrameName(sheetKey: string, glyph: UiIconGlyph): string {
  return `${sheetKey}:${glyph}`;
}

/** Register one texture frame per published cell, once per sheet. */
export function registerIconFrames(
  textures: Phaser.Textures.TextureManager,
  sheetKey: string,
  layout: UiIconSetLayout,
): void {
  const texture = textures.get(sheetKey);
  for (const entry of layout.cells) {
    const name = iconFrameName(sheetKey, entry.glyph);
    if (texture.has(name)) continue;
    texture.add(name, 0, entry.cell.x, entry.cell.y, entry.cell.width, entry.cell.height);
  }
}

export type AtlasIconOptions = Readonly<{
  scene: Phaser.Scene;
  /** Texture key of the loaded icon sheet. */
  sheetKey: string;
  layout: UiIconSetLayout;
  glyph: UiIconGlyph;
  /** Centre, in screen pixels. */
  x: number;
  y: number;
  /** The cell's on-screen side. Defaults to the size the set was drawn for. */
  size?: number;
  depth: number;
}>;

/** One drawn glyph as a screen-fixed engine image, sized by its cell. */
export class AtlasIcon {
  readonly image: Phaser.GameObjects.Image;
  private readonly sheetKey: string;
  private readonly layout: UiIconSetLayout;
  private glyph: UiIconGlyph;
  private size: number;

  constructor(options: AtlasIconOptions) {
    this.sheetKey = options.sheetKey;
    this.layout = options.layout;
    this.glyph = options.glyph;
    this.size = options.size ?? uiIconNativeSize(options.layout);
    registerIconFrames(options.scene.textures, options.sheetKey, options.layout);
    // Looking the cell up proves the glyph is one the grid holds before a frame is named.
    uiIconCellFor(options.layout, options.glyph);
    this.image = options.scene.add
      .image(options.x, options.y, options.sheetKey, iconFrameName(options.sheetKey, options.glyph))
      .setOrigin(0.5)
      .setScrollFactor(0)
      .setDepth(options.depth)
      .setDisplaySize(this.size, this.size);
  }

  get currentGlyph(): UiIconGlyph {
    return this.glyph;
  }

  get currentSize(): number {
    return this.size;
  }

  setGlyph(glyph: UiIconGlyph): void {
    if (glyph === this.glyph) return;
    uiIconCellFor(this.layout, glyph);
    this.glyph = glyph;
    this.image.setFrame(iconFrameName(this.sheetKey, glyph));
    // Every cell is one square, so the display size survives the frame change; restating it
    // keeps that true if a future grid publishes cells of more than one size.
    this.image.setDisplaySize(this.size, this.size);
  }

  setSize(size: number): void {
    this.size = size;
    this.image.setDisplaySize(size, size);
  }

  setPosition(x: number, y: number): void {
    this.image.setPosition(x, y);
  }

  setVisible(visible: boolean): void {
    this.image.setVisible(visible);
  }

  setAlpha(alpha: number): void {
    this.image.setAlpha(alpha);
  }

  destroy(): void {
    this.image.destroy();
  }
}
