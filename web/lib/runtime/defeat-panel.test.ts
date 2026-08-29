import { describe, expect, test } from "bun:test";
import type Phaser from "phaser";
import {
  DEFEAT_PANEL_DEPTH,
  DEFEAT_PANEL_TITLE,
  DefeatPanel,
  defeatReturnLabel,
} from "./defeat-panel";
import { SCENE_CONTENT_DEPTH } from "./layers";
import { DEFEAT_PROMPT_DELAY_MS, DEFEAT_PROMPT_FADE_MS } from "./respawn";

/**
 * The smallest scene the panel can be built against.
 *
 * Enough to exercise what the panel actually decides — when it is up, and whose press counts —
 * without a canvas. The handlers are kept so a test can press the button the way a person does.
 */
function fakeScene() {
  const handlers = new Map<string, () => void>();
  const object = (extra: Record<string, unknown> = {}) => {
    const self: Record<string, unknown> = {
      alpha: 1,
      visible: true,
      ...extra,
      setScrollFactor: () => self,
      setDepth: () => self,
      setOrigin: () => self,
      setStrokeStyle: () => self,
      setFillStyle: () => self,
      setInteractive: () => self,
      setVisible: (value: boolean) => {
        self.visible = value;
        return self;
      },
      setAlpha: (value: number) => {
        self.alpha = value;
        return self;
      },
      setText: (value: string) => {
        self.text = value;
        return self;
      },
      on: (event: string, handler: () => void) => {
        handlers.set(event, handler);
        return self;
      },
      destroy: () => undefined,
    };
    return self;
  };
  const scene = {
    add: {
      rectangle: () => object(),
      text: (_x: number, _y: number, text: string) => object({ text }),
    },
  };
  return { scene: scene as unknown as Phaser.Scene, handlers };
}

const AT_DEFEAT = 10_000;
const SHOWN_AT = AT_DEFEAT + DEFEAT_PROMPT_DELAY_MS + DEFEAT_PROMPT_FADE_MS;

function shownPanel() {
  const { scene, handlers } = fakeScene();
  const panel = new DefeatPanel({ scene });
  panel.update({
    defeatedAtMs: AT_DEFEAT,
    nowMs: SHOWN_AT,
    destinationName: "Sunpetal Crossing",
  });
  return { panel, handlers };
}

describe("the button's words", () => {
  test("name where the run resumes rather than promising 'continue'", () => {
    expect(defeatReturnLabel("Sunpetal Crossing")).toBe("Return to Sunpetal Crossing");
    expect(defeatReturnLabel("  Bellweather  ")).toBe("Return to Bellweather");
  });

  test("a package with no name for home still offers a way back", () => {
    expect(defeatReturnLabel("")).toBe("Return to safety");
    expect(defeatReturnLabel("   ")).toBe("Return to safety");
  });
});

describe("when the panel stands", () => {
  test("it is drawn over the conversation box, which is otherwise the topmost furniture", () => {
    expect(DEFEAT_PANEL_DEPTH).toBeGreaterThan(SCENE_CONTENT_DEPTH.dialogue);
  });

  test("a living player has no panel, whatever the clock says", () => {
    const { scene } = fakeScene();
    const panel = new DefeatPanel({ scene });
    panel.update({ defeatedAtMs: null, nowMs: 900_000, destinationName: "Anywhere" });
    expect(panel.visible).toBe(false);
    expect(panel.snapshot().visible).toBe(false);
  });

  test("it waits out the death strip before appearing", () => {
    const { scene } = fakeScene();
    const panel = new DefeatPanel({ scene });
    panel.update({
      defeatedAtMs: AT_DEFEAT,
      nowMs: AT_DEFEAT,
      destinationName: "Sunpetal Crossing",
    });
    expect(panel.visible).toBe(false);
  });

  test("it names the destination and says what happened", () => {
    const { panel } = shownPanel();
    expect(panel.snapshot()).toMatchObject({
      visible: true,
      alpha: 1,
      title: DEFEAT_PANEL_TITLE,
      buttonLabel: "Return to Sunpetal Crossing",
    });
  });
});

describe("answering it", () => {
  test("a press is reported rather than acted on, and reading it clears it", () => {
    const { panel, handlers } = shownPanel();
    expect(panel.snapshot().confirmRequested).toBe(false);
    handlers.get("pointerdown")?.();
    expect(panel.snapshot().confirmRequested).toBe(true);
    expect(panel.consumeConfirm()).toBe(true);
    expect(panel.consumeConfirm()).toBe(false);
  });

  test("a confirm key reaches the same request", () => {
    const { panel } = shownPanel();
    panel.requestConfirm();
    expect(panel.consumeConfirm()).toBe(true);
  });

  test("a click on the hidden panel is not an answer", () => {
    const { scene, handlers } = fakeScene();
    const panel = new DefeatPanel({ scene });
    // The button keeps its hit area while hidden, so a live run would otherwise respawn on a
    // click near the middle of the screen.
    handlers.get("pointerdown")?.();
    expect(panel.consumeConfirm()).toBe(false);
    panel.requestConfirm();
    expect(panel.consumeConfirm()).toBe(false);
  });

  test("dismissing it drops a press nobody collected", () => {
    const { panel, handlers } = shownPanel();
    handlers.get("pointerdown")?.();
    panel.hide();
    expect(panel.visible).toBe(false);
    expect(panel.consumeConfirm()).toBe(false);
  });
});
