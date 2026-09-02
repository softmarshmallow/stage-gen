// One generated button, drawn from a state sheet and driven by the pointer.
//
// A button is the same object in every genre: a nine-slice at four states, a label centred on the
// safe interior, and a press that the owning HUD reads once. What differs between genres is where
// it sits and what the press means, so neither is here. The four looks are the producer's pixels
// rather than a tint, which is the whole reason the sheet publishes four cells.

import type Phaser from "phaser";
import type { UiAtlasRoleLayout } from "../manifest/ui-atlas-layout";
import type { Rect } from "../shell/hud-geometry";
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

export type AtlasButtonOptions = Readonly<{
  scene: Phaser.Scene;
  /** Texture key of the loaded button sheet. */
  sheetKey: string;
  layout: UiAtlasRoleLayout;
  /** Where the button sits, in screen pixels, centred on the rect. */
  rect: Rect;
  depth: number;
  label: string;
  style?: AtlasButtonStyle;
  /** Called on release inside the button, when it is enabled and live. */
  onPress?: () => void;
}>;

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
    return [this.widget.image, this.text];
  }

  get state(): AtlasButtonState {
    if (!this.enabled) return "disabled";
    if (this.pressed || this.selected) return "pressed";
    return this.hovered ? "hover" : "normal";
  }

  setLabel(label: string): void {
    this.text.setText(label);
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
  }

  setAlpha(alpha: number): void {
    this.widget.image.setAlpha(alpha);
    this.text.setAlpha(alpha);
  }

  /** Move and resize the button, keeping the label centred and the hit area on the body. */
  setRect(rect: Rect): void {
    this.widget.setSize(rect.width, rect.height);
    this.widget.image.setPosition(rect.x + rect.width / 2, rect.y + rect.height / 2);
    this.text.setPosition(this.widget.image.x, this.widget.image.y);
    const shape = this.widget.image.input?.hitArea as { width: number; height: number } | undefined;
    if (shape) {
      shape.width = this.widget.image.width;
      shape.height = this.widget.image.height;
    }
  }

  destroy(): void {
    this.text.destroy();
    this.widget.destroy();
  }

  private paint(): void {
    this.widget.setState(this.state);
  }
}
