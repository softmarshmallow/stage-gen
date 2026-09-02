// One generated button, drawn from a state sheet and driven by the pointer.
//
// A button is the same object in every genre: a nine-slice at four states, a label and/or a
// glyph centred on the safe interior, and a press that the owning HUD reads once. What differs
// between genres is where it sits and what the press means, so neither is here. The four looks
// are the producer's pixels rather than a tint, which is the whole reason the sheet publishes
// four cells; an icon button is this same button with a glyph from the icon grid composed onto
// it, exactly as the taxonomy says, because the icon sheet publishes no button of its own.

import type Phaser from "phaser";
import type { UiAtlasRoleLayout } from "../manifest/ui-atlas-layout";
import type { UiIconGlyph, UiIconSetLayout } from "../manifest/ui-icon-layout";
import type { Rect } from "../shell/hud-geometry";
import { AtlasIcon } from "./icon";
import { NineSliceWidget } from "./widget";

/** The four looks a `button_rect` sheet publishes, in the order it publishes them. */
export type AtlasButtonState = "normal" | "hover" | "pressed" | "disabled";

/** Whatever text style the owning HUD already uses; the button does not impose one. */
export type AtlasButtonStyle = Phaser.Types.GameObjects.Text.TextStyle;

export const DEFAULT_ATLAS_BUTTON_STYLE: AtlasButtonStyle = Object.freeze({
  fontFamily: "system-ui, sans-serif",
  fontSize: "23px",
  color: "#ffffff",
  fontStyle: "bold",
});

/** A glyph composed onto the button, from the loaded icon sheet. */
export type AtlasButtonIcon = Readonly<{
  sheetKey: string;
  layout: UiIconSetLayout;
  glyph: UiIconGlyph;
}>;

export type AtlasButtonOptions = Readonly<{
  scene: Phaser.Scene;
  /** Texture key of the loaded button sheet. */
  sheetKey: string;
  layout: UiAtlasRoleLayout;
  /** Where the button sits, in screen pixels, centred on the rect. */
  rect: Rect;
  depth: number;
  /** The words; empty for an icon-only button. */
  label: string;
  style?: AtlasButtonStyle;
  icon?: AtlasButtonIcon;
  /** Called on release inside the button, when it is enabled and live. */
  onPress?: () => void;
}>;

export type AtlasButtonContentKnobs = Readonly<{
  /** Between the glyph and the words, when both are present. */
  gap: number;
  /** The glyph's cell side as a fraction of the safe rect's height. */
  iconScale: number;
}>;

export const DEFAULT_ATLAS_BUTTON_CONTENT_KNOBS: AtlasButtonContentKnobs = Object.freeze({
  gap: 10,
  iconScale: 1,
});

export type AtlasButtonContentLayout = Readonly<{
  /** Centre and cell side of the glyph, absent when the button carries none. */
  icon: Readonly<{ x: number; y: number; size: number }> | null;
  /** Anchor of the words and the origin they are drawn at. */
  text: Readonly<{ x: number; y: number; originX: number }>;
}>;

/**
 * Where the glyph and the words go inside the safe rect.
 *
 * A glyph beside words is one centred group: the glyph, a gap, then the words drawn from their
 * left edge. A glyph alone or words alone sit at the centre. Pure, so a HUD can test its knobs
 * without a scene.
 */
export function atlasButtonContentLayout(
  safe: Rect,
  content: Readonly<{ hasIcon: boolean; labelWidth: number }>,
  knobs: AtlasButtonContentKnobs = DEFAULT_ATLAS_BUTTON_CONTENT_KNOBS,
): AtlasButtonContentLayout {
  const centreX = safe.x + safe.width / 2;
  const centreY = safe.y + safe.height / 2;
  if (!content.hasIcon) {
    return Object.freeze({ icon: null, text: Object.freeze({ x: centreX, y: centreY, originX: 0.5 }) });
  }
  const size = Math.min(safe.height * knobs.iconScale, safe.width);
  if (content.labelWidth <= 0) {
    return Object.freeze({
      icon: Object.freeze({ x: centreX, y: centreY, size }),
      text: Object.freeze({ x: centreX, y: centreY, originX: 0.5 }),
    });
  }
  const group = size + knobs.gap + content.labelWidth;
  const start = centreX - group / 2;
  return Object.freeze({
    icon: Object.freeze({ x: start + size / 2, y: centreY, size }),
    text: Object.freeze({ x: start + size + knobs.gap, y: centreY, originX: 0 }),
  });
}

/**
 * A pointer-driven atlas button whose state art follows the pointer.
 *
 * `live` is the owner's gate: a Phaser interactive object keeps its hit area while hidden, so a
 * button belonging to a panel that is not up must not answer a click that happens to land on it.
 * The owner sets `live` when it shows the surface the button belongs to.
 */
export class AtlasButton {
  readonly widget: NineSliceWidget;
  readonly text: Phaser.GameObjects.Text;
  readonly icon: AtlasIcon | null;
  private hovered = false;
  private enabled = true;
  private alive = true;
  private pressed = false;
  private selected = false;
  private readonly onPress?: () => void;

  constructor(options: AtlasButtonOptions) {
    this.onPress = options.onPress;
    this.widget = new NineSliceWidget({
      scene: options.scene,
      sheetKey: options.sheetKey,
      layout: options.layout,
      width: options.rect.width,
      height: options.rect.height,
      x: options.rect.x + options.rect.width / 2,
      y: options.rect.y + options.rect.height / 2,
      depth: options.depth,
      state: "normal",
    });
    const style = options.style ?? DEFAULT_ATLAS_BUTTON_STYLE;
    this.text = options.scene.add
      .text(this.widget.image.x, this.widget.image.y, options.label, { ...style })
      .setOrigin(0.5)
      .setScrollFactor(0)
      .setDepth(options.depth + 1);
    this.icon = options.icon
      ? new AtlasIcon({
          scene: options.scene,
          sheetKey: options.icon.sheetKey,
          layout: options.icon.layout,
          glyph: options.icon.glyph,
          x: this.widget.image.x,
          y: this.widget.image.y,
          depth: options.depth + 1,
        })
      : null;
    this.place();
    // The hit area is the drawn body, stated explicitly.
    //
    // Phaser's default sizes it from the texture *frame*, which for an atlas cell is the sheet
    // rectangle — several times the size the widget is drawn at. Three buttons in a row then
    // overlap each other's hit areas, and the first one drawn silently swallows every press
    // aimed at its neighbours. The shape below is the object's own local size, so a press
    // lands on the button under the pointer and nowhere else.
    this.widget.image.setInteractive(
      { width: this.widget.image.width, height: this.widget.image.height },
      (shape: { width: number; height: number }, x: number, y: number) =>
        x >= 0 && y >= 0 && x <= shape.width && y <= shape.height,
    );
    if (this.widget.image.input) this.widget.image.input.cursor = "pointer";
    this.widget.image.on("pointerover", () => {
      this.hovered = true;
      this.paint();
    });
    this.widget.image.on("pointerout", () => {
      this.hovered = false;
      this.pressed = false;
      this.paint();
    });
    this.widget.image.on("pointerdown", () => {
      if (!this.alive || !this.enabled) return;
      this.pressed = true;
      this.paint();
    });
    this.widget.image.on("pointerup", () => {
      const fired = this.pressed && this.alive && this.enabled;
      this.pressed = false;
      this.paint();
      if (fired) this.onPress?.();
    });
  }

  /** Every game object this button owns, for a caller that shows or fades a whole surface. */
  get parts(): readonly Phaser.GameObjects.GameObject[] {
    return this.icon ? [this.widget.image, this.text, this.icon.image] : [this.widget.image, this.text];
  }

  get state(): AtlasButtonState {
    if (!this.enabled) return "disabled";
    if (this.pressed || this.selected) return "pressed";
    return this.hovered ? "hover" : "normal";
  }

  setLabel(label: string): void {
    this.text.setText(label);
    this.place();
  }

  /** Swap the glyph on an icon button; a button built without one has nowhere to put it. */
  setGlyph(glyph: UiIconGlyph): void {
    if (!this.icon) throw new Error("this button carries no icon");
    this.icon.setGlyph(glyph);
  }

  /** Enable or disable the button; a disabled button shows its disabled cell and ignores presses. */
  setEnabled(enabled: boolean): void {
    this.enabled = enabled;
    if (!enabled) this.pressed = false;
    this.paint();
  }

  /**
   * Show this button as the chosen one in a group.
   *
   * A four-state sheet publishes no selected cell, so a toggle borrows the pressed art: it is
   * the one look that reads as "this is the one that is on" without inventing a tint the
   * producer never drew. A fifth cell is its own role promotion, not a field added here.
   */
  setSelected(selected: boolean): void {
    this.selected = selected;
    this.paint();
  }

  /** Whether the surface this button belongs to is currently up. */
  setLive(live: boolean): void {
    this.alive = live;
    if (!live) {
      this.pressed = false;
      this.hovered = false;
      this.paint();
    }
  }

  setVisible(visible: boolean): void {
    this.widget.image.setVisible(visible);
    this.text.setVisible(visible);
    this.icon?.setVisible(visible);
  }

  setAlpha(alpha: number): void {
    this.widget.image.setAlpha(alpha);
    this.text.setAlpha(alpha);
    this.icon?.setAlpha(alpha);
  }

  /** Move and resize the button, keeping its content placed and the hit area on the body. */
  setRect(rect: Rect): void {
    this.widget.setSize(rect.width, rect.height);
    this.widget.image.setPosition(rect.x + rect.width / 2, rect.y + rect.height / 2);
    this.place();
    const shape = this.widget.image.input?.hitArea as { width: number; height: number } | undefined;
    if (shape) {
      shape.width = this.widget.image.width;
      shape.height = this.widget.image.height;
    }
  }

  destroy(): void {
    this.text.destroy();
    this.icon?.destroy();
    this.widget.destroy();
  }

  private paint(): void {
    this.widget.setState(this.state);
  }

  /** Lay the glyph and the words out inside the current safe rect. */
  private place(): void {
    const layout = atlasButtonContentLayout(this.widget.safeRect(), {
      hasIcon: this.icon !== null,
      labelWidth: this.text.text ? this.text.width : 0,
    });
    this.text.setOrigin(layout.text.originX, 0.5);
    this.text.setPosition(layout.text.x, layout.text.y);
    if (this.icon && layout.icon) {
      this.icon.setSize(layout.icon.size);
      this.icon.setPosition(layout.icon.x, layout.icon.y);
    }
  }
}
