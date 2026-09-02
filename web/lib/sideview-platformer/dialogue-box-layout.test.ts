import { describe, expect, test } from "bun:test";
import { DEFAULT_DIALOGUE_BOX_KNOBS, dialogueBoxLayout } from "./dialogue-box-layout";

const SAFE = { x: 100, y: 500, width: 1080, height: 150 };

describe("the dialogue box lays itself out from the frame's safe rect", () => {
  test("the portrait sits on the safe bottom and the text column starts past its slot", () => {
    const layout = dialogueBoxLayout(SAFE);
    const k = DEFAULT_DIALOGUE_BOX_KNOBS;
    expect(layout.portrait.bottomY).toBe(500 + 150 - k.padding);
    expect(layout.portrait.centerX).toBe(100 + k.padding + k.portraitSlotWidth / 2);
    expect(layout.name.y).toBe(500 + k.padding);
    expect(layout.text.y).toBe(500 + k.padding + k.nameRowHeight + k.rowGap);
    expect(layout.text.x).toBe(100 + k.padding + k.portraitSlotWidth + k.columnGap);
    expect(layout.text.x + layout.text.wrapWidth).toBe(100 + 1080 - k.padding);
  });

  test("a knob change moves only what it names", () => {
    const wide = dialogueBoxLayout(SAFE, { ...DEFAULT_DIALOGUE_BOX_KNOBS, portraitSlotWidth: 300 });
    const base = dialogueBoxLayout(SAFE);
    expect(wide.text.x - base.text.x).toBe(90);
    expect(wide.text.wrapWidth).toBe(base.text.wrapWidth - 90);
    expect(wide.name.y).toBe(base.name.y);
  });

  test("a safe rect that cannot host the layout is refused rather than overlapped", () => {
    expect(() => dialogueBoxLayout({ x: 0, y: 0, width: 200, height: 150 })).toThrow(/too small/);
  });
});
