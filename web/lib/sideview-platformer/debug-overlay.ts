import Phaser from "phaser";
import { SCENE_CONTENT_DEPTH } from "./layers";
import {
  debugOverlayText,
  debugOverlayToggleRequested,
  type DebugOverlayState,
} from "./debug-overlay-policy";

/** Screen-fixed diagnostics, intentionally absent from ordinary gameplay presentation. */
export class DebugOverlay {
  private readonly text: Phaser.GameObjects.Text;

  constructor(scene: Phaser.Scene) {
    this.text = scene.add
      .text(18, 18, "", {
        fontFamily: "monospace",
        fontSize: "15px",
        color: "#ffffff",
        backgroundColor: "#122536dd",
        padding: { x: 12, y: 9 },
      })
      .setScrollFactor(0)
      .setDepth(SCENE_CONTENT_DEPTH.hud + 50)
      .setVisible(false);
  }

  toggleForKey(key: Phaser.Input.Keyboard.Key): void {
    if (
      !debugOverlayToggleRequested({
        justPressed: Phaser.Input.Keyboard.JustDown(key),
        metaKey: key.metaKey,
      })
    ) {
      return;
    }
    this.text.setVisible(!this.text.visible);
  }

  update(state: DebugOverlayState): void {
    this.text.setText(debugOverlayText(state));
  }
}
