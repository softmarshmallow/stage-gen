// The death screen — what happened, and the way back.
//
// Recovery used to be a timer the player had no part in: the strip played, a beat passed, and the
// village reassembled around them. That reads as the game deciding something rather than as the
// player being told something, and it gives the one moment a run actually ends no acknowledgement
// at all. This panel is the acknowledgement, and the button is the player's answer.
//
// The panel names its destination rather than saying "continue", because where the run resumes is
// the fact worth reporting: home is derived from the package's own safe-hub roles, so a game that
// opens on a hostile route recovers somewhere the player has never been told about otherwise.
//
// The frame, the button and the glyph on it are the package's own generated art: the frame and
// the button are engine nine-slices cut by the geometry the producer detected, and the `home`
// glyph is one cell of the preview icon set. Hover and pressed are the producer's pixels for
// those states rather than a tint, so the button reads the way the artist drew it.
//
// Motion is sampled from caller-supplied simulation time rather than tweened, exactly like the
// stat log and floating combat text, so normal play and fixed-frame automation follow one path.
// Input is reported rather than acted on: a press sets a request the scene drains on its next
// frame, because rebuilding the world out of a pointer callback would tear down the very objects
// the callback is still standing in.

import type Phaser from "phaser";
import type { UiAtlasRoleLayout } from "@/lib/manifest/ui-atlas-layout";
import type { UiIconSetLayout } from "@/lib/manifest/ui-icon-layout";
import { AtlasButton } from "@/lib/families/ui/button";
import { uiAtlasSheetKey } from "@/lib/families/ui/sheets";
import { NineSliceWidget, minimumSliceSize } from "@/lib/families/ui/widget";
import { DEFAULT_DEFEAT_PANEL_KNOBS, defeatPanelLayout } from "./defeat-panel-layout";
import { SCENE_CONTENT_DEPTH } from "./depths";
import { defeatPromptState } from "./respawn";

const VIEW_W = 1280;
const VIEW_H = 720;
const PANEL_W = 560;
const PANEL_H = 232;

export const DEFEAT_PANEL_DEPTH = SCENE_CONTENT_DEPTH.dialogue + 50;
export const DEFEAT_PANEL_TITLE = "You were defeated";

/** The button's words, which name where the run resumes rather than promising "continue". */
export function defeatReturnLabel(destinationName: string): string {
  const trimmed = destinationName.trim();
  return trimmed ? `Return to ${trimmed}` : "Return to safety";
}

export type DefeatPanelSnapshot = Readonly<{
  visible: boolean;
  alpha: number;
  title: string;
  buttonLabel: string;
  buttonState: string;
  confirmRequested: boolean;
}>;

export type DefeatPanelOptions = Readonly<{
  scene: Phaser.Scene;
  ui: Readonly<{
    panel_frame: UiAtlasRoleLayout;
    button_rect: UiAtlasRoleLayout;
    preview_icons: UiIconSetLayout;
  }>;
}>;

/**
 * Scene-owned death screen.
 *
 * Built once and reused, because it belongs to the interface rather than to the world: a respawn
 * tears down every map object, and a panel rebuilt alongside them would be rebuilt precisely when
 * it is being dismissed.
 */
export class DefeatPanel {
  private readonly scrim: Phaser.GameObjects.Rectangle;
  private readonly panel: NineSliceWidget;
  private readonly title: Phaser.GameObjects.Text;
  private readonly button: AtlasButton;
  private readonly parts: readonly Phaser.GameObjects.GameObject[];
  private confirmRequested = false;
  private shown = false;

  constructor(options: DefeatPanelOptions) {
    const scene = options.scene;
    this.scrim = scene.add
      .rectangle(VIEW_W / 2, VIEW_H / 2, VIEW_W, VIEW_H, 0x05080d, 0.62)
      .setScrollFactor(0)
      .setDepth(DEFEAT_PANEL_DEPTH);
    this.panel = new NineSliceWidget({
      scene,
      sheetKey: uiAtlasSheetKey("panel_frame"),
      layout: options.ui.panel_frame,
      width: PANEL_W,
      height: PANEL_H,
      x: VIEW_W / 2,
      y: VIEW_H / 2,
      depth: DEFEAT_PANEL_DEPTH + 1,
    });
    // Everything inside the frame is placed from its measured safe rect, never from the frame's
    // outer edge: a corner cap that curls inward moves the title and the button, not over them.
    const layout = defeatPanelLayout(
      this.panel.safeRect(),
      minimumSliceSize(options.ui.button_rect.insets, options.ui.button_rect.draw_scale),
      DEFAULT_DEFEAT_PANEL_KNOBS,
    );
    this.title = scene.add
      .text(layout.title.x, layout.title.y, DEFEAT_PANEL_TITLE, {
        fontFamily: "Georgia, serif",
        fontSize: "34px",
        color: "#ffe6a9",
        fontStyle: "bold",
      })
      .setOrigin(0.5)
      .setScrollFactor(0)
      .setDepth(DEFEAT_PANEL_DEPTH + 2);
    // The press is reported on release, the way every atlas button reports it, and only while
    // the panel is up: the button's own `live` gate is what keeps a click in the middle of a
    // live run from respawning the player.
    this.button = new AtlasButton({
      scene,
      sheetKey: uiAtlasSheetKey("button_rect"),
      layout: options.ui.button_rect,
      rect: {
        x: layout.button.x - layout.button.width / 2,
        y: layout.button.y - layout.button.height / 2,
        width: layout.button.width,
        height: layout.button.height,
      },
      depth: DEFEAT_PANEL_DEPTH + 2,
      label: defeatReturnLabel(""),
      icon: {
        sheetKey: uiAtlasSheetKey("preview_icons"),
        layout: options.ui.preview_icons,
        glyph: "home",
      },
      onPress: () => {
        this.confirmRequested = true;
      },
    });
    this.parts = [this.scrim, this.panel.image, this.title, ...this.button.parts];
    this.hide();
  }

  /**
   * Show, hide, and fade the panel for this frame's defeat state.
   *
   * `defeatedAtMs` being null is the ordinary case — the player is alive — and is what dismisses
   * the panel, so the caller never has to remember to hide it.
   */
  update(
    input: Readonly<{
      defeatedAtMs: number | null;
      nowMs: number;
      destinationName: string;
    }>,
  ): void {
    if (input.defeatedAtMs === null) {
      this.hide();
      return;
    }
    const state = defeatPromptState({
      defeatedAtMs: input.defeatedAtMs,
      nowMs: input.nowMs,
    });
    if (!state.visible) {
      this.hide();
      return;
    }
    this.button.setLabel(defeatReturnLabel(input.destinationName));
    this.shown = true;
    this.button.setLive(true);
    for (const part of this.parts) {
      const drawable = part as Phaser.GameObjects.Rectangle;
      drawable.setVisible(true);
      drawable.setAlpha(part === this.scrim ? state.alpha * 0.62 : state.alpha);
    }
  }

  /** Take the pending press, if there is one. Reading it clears it. */
  consumeConfirm(): boolean {
    if (!this.confirmRequested) return false;
    this.confirmRequested = false;
    return true;
  }

  /** Raise the request from somewhere other than the button, such as a confirm key. */
  requestConfirm(): void {
    if (this.shown) this.confirmRequested = true;
  }

  get visible(): boolean {
    return this.shown;
  }

  hide(): void {
    this.shown = false;
    this.confirmRequested = false;
    this.button.setLive(false);
    for (const part of this.parts) {
      (part as Phaser.GameObjects.Rectangle).setVisible(false);
    }
  }

  snapshot(): DefeatPanelSnapshot {
    return Object.freeze({
      visible: this.shown,
      alpha: this.panel.image.alpha,
      title: this.title.text,
      buttonLabel: this.button.text.text,
      buttonState: this.button.state,
      confirmRequested: this.confirmRequested,
    });
  }

  destroy(): void {
    this.scrim.destroy();
    this.title.destroy();
    this.panel.destroy();
    this.button.destroy();
  }
}
