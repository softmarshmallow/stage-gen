import { describe, expect, test } from "bun:test";
import type Phaser from "phaser";
import {
  DEFEAT_PANEL_DEPTH,
  DEFEAT_PANEL_TITLE,
  DefeatPanel,
  defeatReturnLabel,
} from "./defeat-panel";
import { SCENE_CONTENT_DEPTH } from "./depths";
import { DEFEAT_PROMPT_DELAY_MS, DEFEAT_PROMPT_FADE_MS } from "./respawn";
import { UI_ATLAS_FIXTURE_ROLES } from "@/lib/shell/prepared-runtime.fixture";

/**
 * The smallest scene the panel can be built against.
 *
 * Enough to exercise what the panel actually decides — when it is up, whose press counts, and
 * which state the button shows — without a renderer. The handlers are kept so a test can press
 * the button the way a person does; the texture manager records which sheets were sliced.
 */
function fakeScene() {
  const handlers = new Map<string, () => void>();
  const frames: string[] = [];
  const object = (extra: Record<string, unknown> = {}) => {
    const self: Record<string, unknown> = {
      alpha: 1,
      visible: true,
      ...extra,
      setScrollFactor: () => self,
      setDepth: () => self,
      setOrigin: () => self,
      setStrokeStyle: () => self,
      setScale: () => self,
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
      setFrame: (value: string) => {
        self.frame = value;
        return self;
      },
      destroy: () => undefined,
    };
    return self;
  };
  const scene = {
    add: {
      rectangle: () => object(),
      nineslice: (_x: number, _y: number, _sheet: string, frame: string) =>
        object({ frame, setFrame: undefined }),
      text: (_x: number, _y: number, text: string) => object({ text }),
    },
    textures: {
      get: () => ({
        has: (name: string) => frames.includes(name),
        add: (name: string) => frames.push(name),
      }),
    },
  };
  return { scene: scene as unknown as Phaser.Scene, handlers, frames };
}

function buildPanel() {
  const fake = fakeScene();
  const panel = new DefeatPanel({ scene: fake.scene, ui: UI_ATLAS_FIXTURE_ROLES });
  return { ...fake, panel };
}

const AT_DEFEAT = 10_000;
const SHOWN_AT = AT_DEFEAT + DEFEAT_PROMPT_DELAY_MS + DEFEAT_PROMPT_FADE_MS;

function shownPanel() {
  const { panel, handlers } = buildPanel();
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
    const { panel } = buildPanel();
    panel.update({ defeatedAtMs: null, nowMs: 900_000, destinationName: "Anywhere" });
    expect(panel.visible).toBe(false);
    expect(panel.snapshot().visible).toBe(false);
  });

  test("it waits out the death strip before appearing", () => {
    const { panel } = buildPanel();
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

  test("the button shows the producer's hover and pressed cells, and rests on normal", () => {
    const { panel, handlers } = shownPanel();
    expect(panel.snapshot().buttonState).toBe("normal");
    handlers.get("pointerover")?.();
    expect(panel.snapshot().buttonState).toBe("hover");
    handlers.get("pointerdown")?.();
    expect(panel.snapshot().buttonState).toBe("pressed");
    handlers.get("pointerup")?.();
    expect(panel.snapshot().buttonState).toBe("hover");
    panel.hide();
    expect(panel.snapshot().buttonState).toBe("normal");
  });

  test("the frame and the button are cut from the package's own sheets", () => {
    const { frames } = buildPanel();
    expect(frames).toEqual([
      "ui_panel_frame:default",
      "ui_button_rect:normal",
      "ui_button_rect:hover",
      "ui_button_rect:pressed",
      "ui_button_rect:disabled",
    ]);
  });

  test("a confirm key reaches the same request", () => {
    const { panel } = shownPanel();
    panel.requestConfirm();
    expect(panel.consumeConfirm()).toBe(true);
  });

  test("a click on the hidden panel is not an answer", () => {
    const { panel, handlers } = buildPanel();
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
