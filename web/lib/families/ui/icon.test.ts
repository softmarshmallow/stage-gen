import { describe, expect, test } from "bun:test";
import type Phaser from "phaser";
import { UI_ATLAS_FIXTURE_ROLES } from "@/lib/shell/prepared-runtime.fixture";
import { atlasButtonContentLayout } from "./button";
import { AtlasIcon, iconFrameName } from "./icon";

type FrameCall = readonly [string, number, number, number, number, number];

function fakeScene() {
  const frames = new Map<string, FrameCall>();
  const image = {
    x: 0,
    y: 0,
    frame: "",
    displayWidth: 0,
    displayHeight: 0,
    setOrigin() {
      return image;
    },
    setScrollFactor() {
      return image;
    },
    setDepth() {
      return image;
    },
    setFrame(name: string) {
      image.frame = name;
      return image;
    },
    setDisplaySize(width: number, height: number) {
      image.displayWidth = width;
      image.displayHeight = height;
      return image;
    },
    setPosition(x: number, y: number) {
      image.x = x;
      image.y = y;
      return image;
    },
    setVisible() {
      return image;
    },
    setAlpha() {
      return image;
    },
    destroy() {},
  };
  const scene = {
    add: {
      image: (x: number, y: number, _sheet: string, frame: string) => {
        image.x = x;
        image.y = y;
        image.frame = frame;
        return image;
      },
    },
    textures: {
      get: () => ({
        has: (name: string) => frames.has(name),
        add: (...call: FrameCall) => frames.set(call[0], call),
      }),
    },
  };
  return { scene: scene as unknown as Phaser.Scene, frames, image };
}

const LAYOUT = UI_ATLAS_FIXTURE_ROLES.preview_icons;

describe("atlas icon", () => {
  test("registers one frame per published cell, keyed by glyph, and draws at the set's size", () => {
    const { scene, frames, image } = fakeScene();
    const icon = new AtlasIcon({ scene, sheetKey: "ui_preview_icons", layout: LAYOUT, glyph: "home", x: 10, y: 20, depth: 3 });
    expect(frames.size).toBe(16);
    expect(frames.get(iconFrameName("ui_preview_icons", "home"))).toEqual([
      "ui_preview_icons:home",
      0,
      272,
      272,
      232,
      232,
    ]);
    expect(image.frame).toBe("ui_preview_icons:home");
    // 232 sheet pixels at draw scale 2 is the size the set was drawn for.
    expect(icon.currentSize).toBe(116);
    expect(image.displayWidth).toBe(116);
  });

  test("switches glyph by frame and keeps its size, and refuses a glyph the grid lacks", () => {
    const { scene, image } = fakeScene();
    const icon = new AtlasIcon({ scene, sheetKey: "ui_preview_icons", layout: LAYOUT, glyph: "play", x: 0, y: 0, size: 32, depth: 1 });
    icon.setGlyph("pause");
    expect(image.frame).toBe("ui_preview_icons:pause");
    expect(image.displayWidth).toBe(32);
    expect(() => icon.setGlyph("trophy" as never)).toThrow(/no trophy cell/);
  });
});

describe("button content layout", () => {
  const safe = { x: 100, y: 50, width: 200, height: 40 };

  test("words alone sit at the centre", () => {
    const layout = atlasButtonContentLayout(safe, { hasIcon: false, labelWidth: 80 });
    expect(layout.icon).toBeNull();
    expect(layout.text).toEqual({ x: 200, y: 70, originX: 0.5 });
  });

  test("a glyph alone sits at the centre, sized by the safe height", () => {
    const layout = atlasButtonContentLayout(safe, { hasIcon: true, labelWidth: 0 });
    expect(layout.icon).toEqual({ x: 200, y: 70, size: 40 });
  });

  test("a glyph beside words is one centred group, words drawn from their left edge", () => {
    const layout = atlasButtonContentLayout(safe, { hasIcon: true, labelWidth: 80 }, { gap: 10, iconScale: 1 });
    // group = 40 + 10 + 80 = 130, starting at 200 - 65 = 135
    expect(layout.icon).toEqual({ x: 155, y: 70, size: 40 });
    expect(layout.text).toEqual({ x: 185, y: 70, originX: 0 });
  });
});
