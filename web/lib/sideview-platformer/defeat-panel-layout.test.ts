import { describe, expect, test } from "bun:test";
import { DEFAULT_DEFEAT_PANEL_KNOBS, defeatPanelLayout } from "./defeat-panel-layout";

const SAFE = { x: 400, y: 300, width: 480, height: 150 };
const SMALLEST = { width: 80, height: 60 };

describe("the defeat panel lays itself out from the frame's safe rect", () => {
  test("the title takes the top row and the button centres in what is left", () => {
    const layout = defeatPanelLayout(SAFE, SMALLEST);
    const k = DEFAULT_DEFEAT_PANEL_KNOBS;
    expect(layout.title).toEqual({ x: 640, y: 300 + k.padding + k.titleRowHeight / 2 });
    const buttonTop = 300 + k.padding + k.titleRowHeight + k.rowGap;
    const room = 300 + 150 - k.padding - buttonTop;
    expect(layout.button.y).toBe(buttonTop + room / 2);
    expect(layout.button.width).toBe(380);
    expect(layout.button.height).toBe(62);
  });

  test("the button grows to the sheet's smallest size and shrinks to the room it has", () => {
    const grown = defeatPanelLayout(SAFE, { width: 420, height: 70 });
    expect([grown.button.width, grown.button.height]).toEqual([420, 70]);
    const narrow = defeatPanelLayout({ ...SAFE, width: 300 }, SMALLEST);
    expect(narrow.button.width).toBe(300 - 2 * DEFAULT_DEFEAT_PANEL_KNOBS.padding);
    expect(() => defeatPanelLayout({ ...SAFE, height: 90 }, SMALLEST)).toThrow(/smallest size/);
  });

  test("a frame whose ornament curls inward gives up title room before the button", () => {
    // 124px of safe height: the spike's painterly frame at the panel's drawn size. The
    // default title row would leave the button 50px, under its 60px floor, so the row
    // yields down to its own floor and the button keeps its smallest size.
    const layout = defeatPanelLayout({ ...SAFE, height: 124 }, SMALLEST);
    const k = DEFAULT_DEFEAT_PANEL_KNOBS;
    expect(layout.title.y).toBe(300 + k.padding + k.titleRowMinHeight / 2);
    expect(layout.button.height).toBe(60);
  });
});
