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
// Motion is sampled from caller-supplied simulation time rather than tweened, exactly like the
// stat log and floating combat text, so normal play and fixed-frame automation follow one path.
// Input is reported rather than acted on: a press sets a request the scene drains on its next
// frame, because rebuilding the world out of a pointer callback would tear down the very objects
// the callback is still standing in.

import type Phaser from "phaser";
import { SCENE_CONTENT_DEPTH } from "./depths";
import { defeatPromptState } from "./respawn";

const VIEW_W = 1280;
const VIEW_H = 720;
const PANEL_W = 560;
const PANEL_H = 232;
const BUTTON_W = 380;
const BUTTON_H = 62;
const BUTTON_CENTER_Y = VIEW_H / 2 + 44;

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
  confirmRequested: boolean;
}>;

export type DefeatPanelOptions = Readonly<{
  scene: Phaser.Scene;
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
  private readonly panel: Phaser.GameObjects.Rectangle;
  private readonly title: Phaser.GameObjects.Text;
  private readonly button: Phaser.GameObjects.Rectangle;
  private readonly buttonLabel: Phaser.GameObjects.Text;
  private readonly parts: Phaser.GameObjects.GameObject[];
  private confirmRequested = false;
  private shown = false;

  constructor(options: DefeatPanelOptions) {
    const scene = options.scene;
    this.scrim = scene.add
      .rectangle(VIEW_W / 2, VIEW_H / 2, VIEW_W, VIEW_H, 0x05080d, 0.62)
      .setScrollFactor(0)
      .setDepth(DEFEAT_PANEL_DEPTH);
    this.panel = scene.add
      .rectangle(VIEW_W / 2, VIEW_H / 2, PANEL_W, PANEL_H, 0x182a3a, 0.97)
      .setScrollFactor(0)
      .setDepth(DEFEAT_PANEL_DEPTH + 1);
    this.panel.setStrokeStyle(4, 0xf1d69a, 1);
    this.title = scene.add
      .text(VIEW_W / 2, VIEW_H / 2 - 54, DEFEAT_PANEL_TITLE, {
        fontFamily: "Georgia, serif",
        fontSize: "34px",
        color: "#ffe6a9",
        fontStyle: "bold",
      })
      .setOrigin(0.5)
      .setScrollFactor(0)
      .setDepth(DEFEAT_PANEL_DEPTH + 2);
    this.button = scene.add
      .rectangle(VIEW_W / 2, BUTTON_CENTER_Y, BUTTON_W, BUTTON_H, 0x2c5064, 1)
      .setScrollFactor(0)
      .setDepth(DEFEAT_PANEL_DEPTH + 2);
    this.button.setStrokeStyle(3, 0xf1d69a, 1);
    this.buttonLabel = scene.add
      .text(VIEW_W / 2, BUTTON_CENTER_Y, defeatReturnLabel(""), {
        fontFamily: "system-ui, sans-serif",
        fontSize: "23px",
        color: "#ffffff",
        fontStyle: "bold",
      })
      .setOrigin(0.5)
      .setScrollFactor(0)
      .setDepth(DEFEAT_PANEL_DEPTH + 3);
    this.parts = [this.scrim, this.panel, this.title, this.button, this.buttonLabel];

    this.button.setInteractive({ useHandCursor: true });
    this.button.on("pointerover", () => {
      if (this.shown) this.button.setFillStyle(0x3c6c88, 1);
    });
    this.button.on("pointerout", () => this.button.setFillStyle(0x2c5064, 1));
    this.button.on("pointerdown", () => {
      // Only while the panel is actually up: an interactive rectangle keeps its hit area when it
      // is hidden, so without this a click anywhere near the middle of a live run would respawn.
      if (this.shown) this.confirmRequested = true;
    });
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
    this.buttonLabel.setText(defeatReturnLabel(input.destinationName));
    this.shown = true;
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
    this.button.setFillStyle(0x2c5064, 1);
    for (const part of this.parts) {
      (part as Phaser.GameObjects.Rectangle).setVisible(false);
    }
  }

  snapshot(): DefeatPanelSnapshot {
    return Object.freeze({
      visible: this.shown,
      alpha: this.panel.alpha,
      title: this.title.text,
      buttonLabel: this.buttonLabel.text,
      confirmRequested: this.confirmRequested,
    });
  }

  destroy(): void {
    for (const part of this.parts) part.destroy();
  }
}
