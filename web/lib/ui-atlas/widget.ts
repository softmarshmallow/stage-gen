// The agnostic nine-slice widget: a generated atlas cell drawn at any size, with a state switch.
//
// Phaser has its own nine-slice game object, and the manifest's resolved geometry maps onto it
// one-to-one: a cell rect is a texture frame, the insets are its corner widths, and the admitted
// band fill is its tile flag. So the widget owns no drawing of its own; it registers one frame per
// published state on the sheet, hands the engine the geometry, and switches frames on a state
// change. Where the widget sits and what its press means stay with the genre HUD that owns it.

import type Phaser from "phaser";
import type { Insets, UiAtlasRoleLayout } from "../manifest/ui-atlas-layout";
import { uiAtlasCellFor } from "../manifest/ui-atlas-layout";
import type { Rect, Size } from "../shell/hud-geometry";

/** The smallest on-screen size a sheet can be drawn at without its corners overlapping. */
export function minimumSliceSize(insets: Insets, drawScale = 1): Size {
  return {
    width: (insets.left + insets.right) / drawScale,
    height: (insets.top + insets.bottom) / drawScale,
  };
}

/** The frame registered on `sheetKey` for one published state. */
export function atlasFrameName(sheetKey: string, state: string): string {
  return `${sheetKey}:${state}`;
}

/**
 * Register one texture frame per published cell, once per sheet.
 *
 * Frames are keyed by state so any number of widgets drawn from the same sheet share them, and a
 * sheet that was replaced by a runtime stand-in still resolves: the stand-in is the whole declared
 * canvas, so every published cell falls inside it.
 */
export function registerAtlasFrames(
  textures: Phaser.Textures.TextureManager,
  sheetKey: string,
  layout: UiAtlasRoleLayout,
): void {
  const texture = textures.get(sheetKey);
  for (const entry of layout.cells) {
    const name = atlasFrameName(sheetKey, entry.state);
    if (texture.has(name)) continue;
    texture.add(name, 0, entry.cell.x, entry.cell.y, entry.cell.width, entry.cell.height);
  }
}

export type NineSliceWidgetOptions = Readonly<{
  scene: Phaser.Scene;
  /** Texture key of the loaded atlas sheet. */
  sheetKey: string;
  layout: UiAtlasRoleLayout;
  width: number;
  height: number;
  x: number;
  y: number;
  depth: number;
  state?: string;
}>;

/**
 * One drawn atlas cell as a screen-fixed engine nine-slice.
 *
 * `setState` switches to the sheet's frame for that state, so a button's hover and pressed looks
 * are the producer's pixels rather than a tint. `setSize` re-lays the slices at a new size; a size
 * smaller than the sheet's corners is the HUD's layout not fitting the art, which is why
 * `minimumSize` is exposed for the HUD to clamp against.
 */
export class NineSliceWidget {
  readonly image: Phaser.GameObjects.NineSlice;
  private readonly sheetKey: string;
  private readonly layout: UiAtlasRoleLayout;
  private state: string;

  constructor(options: NineSliceWidgetOptions) {
    this.sheetKey = options.sheetKey;
    this.layout = options.layout;
    this.state = options.state ?? options.layout.cells[0].state;
    registerAtlasFrames(options.scene.textures, options.sheetKey, options.layout);
    const { left, top, right, bottom } = options.layout.insets;
    const tile = options.layout.band_fill === "tile";
    // The sheet is authored at `draw_scale` times screen density: lay the slices out at that
    // multiple of the target size and scale the object down, so corners keep their drawn
    // proportion to the body instead of their sheet pixel size.
    const scale = options.layout.draw_scale;
    this.image = options.scene.add
      .nineslice(
        options.x,
        options.y,
        options.sheetKey,
        this.frame(),
        options.width * scale,
        options.height * scale,
        left,
        right,
        top,
        bottom,
        tile,
        tile,
      )
      .setScale(1 / scale)
      .setScrollFactor(0)
      .setDepth(options.depth);
  }

  get minimumSize(): Size {
    return minimumSliceSize(this.layout.insets, this.layout.draw_scale);
  }

  /** The on-screen size the widget is drawn at. */
  get size(): Size {
    const scale = this.layout.draw_scale;
    return { width: this.image.width / scale, height: this.image.height / scale };
  }

  /** The screen rectangle of the geometric interior for the current size and position. */
  contentRect(): Rect {
    return this.interior(0, 0, 0, 0);
  }

  /**
   * The screen rectangle text is safe in: the interior less the measured ornament curl of the
   * current state's cell. This is what a HUD lays out from; `contentRect` is for decoration
   * that may run under the ornament.
   */
  safeRect(): Rect {
    const cell = uiAtlasCellFor(this.layout, this.state);
    const content = cell.content_rect;
    const safe = cell.safe_rect;
    return this.interior(
      safe.x - content.x,
      safe.y - content.y,
      content.x + content.width - (safe.x + safe.width),
      content.y + content.height - (safe.y + safe.height),
    );
  }

  private interior(curlLeft: number, curlTop: number, curlRight: number, curlBottom: number): Rect {
    const scale = this.layout.draw_scale;
    const { width, height } = this.size;
    const left = (this.layout.insets.left + curlLeft) / scale;
    const top = (this.layout.insets.top + curlTop) / scale;
    const right = (this.layout.insets.right + curlRight) / scale;
    const bottom = (this.layout.insets.bottom + curlBottom) / scale;
    return {
      x: this.image.x - width / 2 + left,
      y: this.image.y - height / 2 + top,
      width: width - left - right,
      height: height - top - bottom,
    };
  }

  get currentState(): string {
    return this.state;
  }

  setState(state: string): void {
    if (state === this.state) return;
    this.state = state;
    this.image.setFrame(this.frame());
  }

  /** Re-lay the slices at a new on-screen size. */
  setSize(width: number, height: number): void {
    const scale = this.layout.draw_scale;
    this.image.setSize(width * scale, height * scale);
  }

  destroy(): void {
    this.image.destroy();
  }

  private frame(): string {
    return atlasFrameName(this.sheetKey, uiAtlasCellFor(this.layout, this.state).state);
  }
}
