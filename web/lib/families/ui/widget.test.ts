import { describe, expect, test } from "bun:test";
import type Phaser from "phaser";
import { UI_ATLAS_FIXTURE_ROLES } from "@/lib/shell/prepared-runtime.fixture";
import { NineSliceWidget, atlasFrameName, minimumSliceSize } from "./widget";

type FrameCall = readonly [string, number, number, number, number, number];

function fakeScene() {
  const frames = new Map<string, FrameCall>();
  const nineslices: unknown[][] = [];
  const image = {
    x: 0,
    y: 0,
    width: 0,
    height: 0,
    frame: "",
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
    setSize(width: number, height: number) {
      image.width = width;
      image.height = height;
      return image;
    },
    scale: 1,
    setScale(value: number) {
      image.scale = value;
      return image;
    },
    destroy() {},
  };
  const scene = {
    add: {
      nineslice: (...args: unknown[]) => {
        nineslices.push(args);
        image.x = args[0] as number;
        image.y = args[1] as number;
        image.frame = args[3] as string;
        image.width = args[4] as number;
        image.height = args[5] as number;
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
  return { scene: scene as unknown as Phaser.Scene, frames, nineslices, image };
}

describe("the nine-slice widget hands the engine the manifest's geometry", () => {
  test("every published cell becomes a frame, once per sheet", () => {
    const { scene, frames } = fakeScene();
    const layout = UI_ATLAS_FIXTURE_ROLES.button_rect;
    new NineSliceWidget({ scene, sheetKey: "ui_button_rect", layout, width: 400, height: 80, x: 1, y: 2, depth: 3 });
    new NineSliceWidget({ scene, sheetKey: "ui_button_rect", layout, width: 200, height: 80, x: 1, y: 2, depth: 3 });
    expect([...frames.keys()]).toEqual(
      layout.cells.map((entry) => atlasFrameName("ui_button_rect", entry.state)),
    );
    const pressed = layout.cells[2];
    expect(frames.get(atlasFrameName("ui_button_rect", "pressed"))).toEqual([
      "ui_button_rect:pressed",
      0,
      pressed.cell.x,
      pressed.cell.y,
      pressed.cell.width,
      pressed.cell.height,
    ]);
  });

  test("insets become corner widths, the fill becomes the tile flags, and the draw scale lays the slices out at sheet density", () => {
    const { scene, nineslices, image } = fakeScene();
    const layout = UI_ATLAS_FIXTURE_ROLES.button_rect;
    new NineSliceWidget({ scene, sheetKey: "ui_button_rect", layout, width: 400, height: 80, x: 10, y: 20, depth: 3 });
    const { left, top, right, bottom } = layout.insets;
    expect(image.scale).toBe(0.5);
    expect(nineslices[0]).toEqual([
      10,
      20,
      "ui_button_rect",
      "ui_button_rect:normal",
      800,
      160,
      left,
      right,
      top,
      bottom,
      true,
      true,
    ]);
    const stretched = { ...layout, band_fill: "stretch" as const };
    new NineSliceWidget({ scene, sheetKey: "ui_button_rect", layout: stretched, width: 400, height: 80, x: 0, y: 0, depth: 3 });
    expect(nineslices[1]?.slice(10)).toEqual([false, false]);
  });

  test("a state switch is a frame switch, and an unknown state falls back to the first cell", () => {
    const { scene, image } = fakeScene();
    const widget = new NineSliceWidget({
      scene,
      sheetKey: "ui_button_rect",
      layout: UI_ATLAS_FIXTURE_ROLES.button_rect,
      width: 400,
      height: 80,
      x: 0,
      y: 0,
      depth: 3,
    });
    widget.setState("hover");
    expect(image.frame).toBe("ui_button_rect:hover");
    expect(widget.currentState).toBe("hover");
    widget.setState("selected");
    expect(image.frame).toBe("ui_button_rect:normal");
  });

  test("the content rect follows the size and the corners bound the smallest size", () => {
    const { scene, image } = fakeScene();
    const layout = UI_ATLAS_FIXTURE_ROLES.panel_frame;
    const widget = new NineSliceWidget({ scene, sheetKey: "ui_panel_frame", layout, width: 560, height: 232, x: 640, y: 360, depth: 1 });
    // Insets are sheet pixels; on screen they are halved by the draw scale.
    expect(widget.size).toEqual({ width: 560, height: 232 });
    expect(widget.contentRect()).toEqual({ x: 640 - 280 + 48, y: 360 - 116 + 48, width: 560 - 96, height: 232 - 96 });
    // The fixture's panel curls 12 sheet px past every corner: 6 px on screen, each side.
    expect(widget.safeRect()).toEqual({ x: 640 - 280 + 54, y: 360 - 116 + 54, width: 560 - 108, height: 232 - 108 });
    widget.setSize(800, 400);
    expect([image.width, image.height]).toEqual([1600, 800]);
    expect(widget.size).toEqual({ width: 800, height: 400 });
    expect(widget.minimumSize).toEqual(minimumSliceSize(layout.insets, 2));
    expect(minimumSliceSize(layout.insets, 2)).toEqual({ width: 96, height: 96 });
  });
});
