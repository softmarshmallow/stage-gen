import { describe, expect, it } from "bun:test";
import { contrastRatio, mostReadable, parseHexColor, relativeLuminance } from "./contrast";

const INK = "#141726";
const PAPER = "#f4f1ee";

describe("parseHexColor", () => {
  it("reads both hex lengths and rejects anything else", () => {
    expect(parseHexColor("#fff")).toEqual({ r: 255, g: 255, b: 255 });
    expect(parseHexColor("141726")).toEqual({ r: 0x14, g: 0x17, b: 0x26 });
    expect(parseHexColor("rebeccapurple")).toBeNull();
    expect(parseHexColor("#12345")).toBeNull();
  });
});

describe("relativeLuminance", () => {
  it("anchors at the ends of the range", () => {
    expect(relativeLuminance({ r: 0, g: 0, b: 0 })).toBe(0);
    expect(relativeLuminance({ r: 255, g: 255, b: 255 })).toBeCloseTo(1, 10);
  });

  it("weights green above red above blue, as an eye does", () => {
    const green = relativeLuminance({ r: 0, g: 255, b: 0 });
    const red = relativeLuminance({ r: 255, g: 0, b: 0 });
    const blue = relativeLuminance({ r: 0, g: 0, b: 255 });
    expect(green).toBeGreaterThan(red);
    expect(red).toBeGreaterThan(blue);
  });
});

describe("contrastRatio", () => {
  it("is 21 for black on white and 1 for a colour on itself", () => {
    expect(contrastRatio({ r: 0, g: 0, b: 0 }, { r: 255, g: 255, b: 255 })).toBeCloseTo(21, 6);
    expect(contrastRatio({ r: 90, g: 20, b: 60 }, { r: 90, g: 20, b: 60 })).toBeCloseTo(1, 10);
  });

  it("does not depend on argument order", () => {
    const a = { r: 12, g: 30, b: 44 };
    const b = { r: 240, g: 236, b: 220 };
    expect(contrastRatio(a, b)).toBeCloseTo(contrastRatio(b, a), 10);
  });
});

describe("mostReadable", () => {
  // The bug this module exists for: a cream generated plate under body text authored for a
  // dark fallback fill. Paper on cream is unreadable, so ink must win.
  it("picks ink on the silkscreen cream plate", () => {
    const cream = { r: 0xf6, g: 0xea, b: 0xc8 };
    expect(mostReadable(cream, [PAPER, INK])).toBe(INK);
  });

  it("keeps the authored paper on a dark plate", () => {
    const nightBlue = { r: 0x11, g: 0x1a, b: 0x33 };
    expect(mostReadable(nightBlue, [PAPER, INK])).toBe(PAPER);
  });

  it("prefers an earlier candidate that already clears the threshold", () => {
    // Both clear 4.5 on this near-black; the first offered is the authored look and wins.
    const nearBlack = { r: 8, g: 8, b: 10 };
    expect(mostReadable(nearBlack, ["#cccccc", "#ffffff"])).toBe("#cccccc");
  });

  it("falls back to the best available when nothing clears the threshold", () => {
    const mid = { r: 128, g: 128, b: 128 };
    expect(mostReadable(mid, ["#7f7f7f", "#000000"])).toBe("#000000");
  });

  it("returns null when no candidate is a colour it can read", () => {
    expect(mostReadable({ r: 0, g: 0, b: 0 }, ["transparent", "currentColor"])).toBeNull();
  });
});
