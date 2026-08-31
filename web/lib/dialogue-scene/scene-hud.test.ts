import { describe, expect, test } from "bun:test";
import {
  bodyTextPoint,
  bodyTextWrapWidth,
  completeCardRect,
  DIALOGUE_STAGE,
  dialoguePanelRect,
  speakerChipRect,
  spriteFrame,
  SPRITE_MAX_WIDTH_RATIO,
} from "./scene-hud";

const PLATE = { width: 1024, height: 1536 };
const CENTRED = { scale: 1, xPercent: 50, yPercent: 0 };

describe("spriteFrame", () => {
  test("fills the frame height and centres on the authored anchor", () => {
    const frame = spriteFrame(DIALOGUE_STAGE, PLATE, CENTRED);
    expect(frame.height).toBeCloseTo(DIALOGUE_STAGE.height * 0.98, 5);
    expect(frame.x + frame.width / 2).toBeCloseTo(DIALOGUE_STAGE.width / 2, 5);
    expect(frame.y).toBe(0);
    // The plate's aspect survives: a portrait stays portrait.
    expect(frame.width / frame.height).toBeCloseTo(PLATE.width / PLATE.height, 5);
  });

  test("a wide plate is limited by width rather than stretched", () => {
    const wide = spriteFrame(DIALOGUE_STAGE, { width: 3000, height: 1000 }, CENTRED);
    expect(wide.width).toBeCloseTo(DIALOGUE_STAGE.width * SPRITE_MAX_WIDTH_RATIO, 5);
    expect(wide.width / wide.height).toBeCloseTo(3, 5);
  });

  test("scale grows about the top edge, so a zoomed character does not drift up", () => {
    const base = spriteFrame(DIALOGUE_STAGE, PLATE, { ...CENTRED, yPercent: 6 });
    const zoomed = spriteFrame(DIALOGUE_STAGE, PLATE, {
      ...CENTRED,
      yPercent: 6,
      scale: 1.4,
    });
    expect(zoomed.y).toBe(base.y);
    expect(zoomed.x + zoomed.width / 2).toBeCloseTo(base.x + base.width / 2, 5);
    expect(zoomed.height).toBeCloseTo(base.height * 1.4, 5);
  });

  test("a source with no area is refused rather than dividing by zero", () => {
    expect(() => spriteFrame(DIALOGUE_STAGE, { width: 0, height: 10 }, CENTRED)).toThrow(
      "positive size",
    );
  });
});

describe("panel geometry", () => {
  test("the panel sits inside the frame with the body copy inside the panel", () => {
    const panel = dialoguePanelRect(DIALOGUE_STAGE);
    expect(panel.x).toBeGreaterThan(0);
    expect(panel.y + panel.height).toBeLessThan(DIALOGUE_STAGE.height);
    expect(panel.x + panel.width).toBeLessThan(DIALOGUE_STAGE.width);

    const body = bodyTextPoint(panel);
    expect(body.x).toBeGreaterThan(panel.x);
    expect(body.y).toBeGreaterThan(panel.y);
    expect(bodyTextWrapWidth(panel)).toBeLessThan(panel.width);
  });

  test("the speaker plate straddles the panel edge and grows with its label", () => {
    const panel = dialoguePanelRect(DIALOGUE_STAGE);
    const short = speakerChipRect(panel, 10);
    const long = speakerChipRect(panel, 600);
    expect(short.y).toBeLessThan(panel.y);
    expect(short.y + short.height).toBeGreaterThan(panel.y);
    expect(long.width).toBeGreaterThan(short.width);
    // A short name still gets a plate wide enough to read as one.
    expect(short.width).toBe(150);
  });

  test("the end card is centred and never wider than the frame", () => {
    const card = completeCardRect(DIALOGUE_STAGE);
    expect(card.x + card.width / 2).toBeCloseTo(DIALOGUE_STAGE.width / 2, 5);
    expect(card.y + card.height / 2).toBeCloseTo(DIALOGUE_STAGE.height / 2, 5);
    expect(card.width).toBeLessThan(DIALOGUE_STAGE.width);
  });
});
