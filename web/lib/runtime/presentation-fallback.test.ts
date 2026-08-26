import { describe, expect, test } from "bun:test";
import type Phaser from "phaser";
import {
  registerGridPresentationFallback,
  registerPresentationFallback,
  type PresentationFallbackKind,
} from "./presentation-fallback";

type FrameCall = readonly [string | number, number, number, number, number, number];

function withFakeBrowser<T>(run: () => T): T {
  const original = Object.getOwnPropertyDescriptor(globalThis, "document");
  const context = {
    fillStyle: "",
    strokeStyle: "",
    lineWidth: 0,
    fillRect() {},
    strokeRect() {},
    beginPath() {},
    moveTo() {},
    lineTo() {},
    stroke() {},
  };
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: {
      createElement(tag: string) {
        if (tag !== "canvas") throw new Error(`unexpected element: ${tag}`);
        return {
          width: 0,
          height: 0,
          getContext(kind: string) {
            return kind === "2d" ? context : null;
          },
        };
      },
    },
  });
  try {
    return run();
  } finally {
    if (original) Object.defineProperty(globalThis, "document", original);
    else Reflect.deleteProperty(globalThis, "document");
  }
}

function fakeTextures(existing = false): {
  manager: Phaser.Textures.TextureManager;
  frames: FrameCall[];
  removed: string[];
} {
  const frames: FrameCall[] = [];
  const removed: string[] = [];
  const texture = {
    add(...args: FrameCall) {
      frames.push(args);
    },
  };
  const manager = {
    exists() {
      return existing;
    },
    remove(key: string) {
      removed.push(key);
    },
    addCanvas() {},
    get() {
      return texture;
    },
  } as unknown as Phaser.Textures.TextureManager;
  return { manager, frames, removed };
}

function register(kind: PresentationFallbackKind) {
  return withFakeBrowser(() => {
    const fake = fakeTextures();
    const canvas = registerPresentationFallback(fake.manager, "missing-art", kind);
    return { canvas, ...fake };
  });
}

describe("presentation fallback", () => {
  test("registers a four-frame strip with the integer frames actors consume", () => {
    const result = register("four_frame_strip");
    expect([result.canvas.width, result.canvas.height]).toEqual([256, 64]);
    expect(result.frames).toEqual([
      [0, 0, 0, 0, 64, 64],
      [1, 0, 64, 0, 64, 64],
      [2, 0, 128, 0, 64, 64],
      [3, 0, 192, 0, 64, 64],
    ]);
  });

  test("registers the two named portal cells expected by PortalSystem", () => {
    const result = register("portal_sheet");
    expect([result.canvas.width, result.canvas.height]).toEqual([128, 96]);
    expect(result.frames).toEqual([
      ["portal_entry", 0, 0, 0, 64, 96],
      ["portal_exit", 0, 64, 0, 64, 96],
    ]);
  });

  test("registers the row-major named frames dialogue consumes", () => {
    const result = withFakeBrowser(() => {
      const fake = fakeTextures();
      const canvas = registerGridPresentationFallback(
        fake.manager,
        "missing-dialogue",
        3,
        2,
        "expression",
      );
      return { canvas, ...fake };
    });
    expect([result.canvas.width, result.canvas.height]).toEqual([192, 128]);
    expect(result.frames).toHaveLength(6);
    expect(result.frames[0]).toEqual(["expression_0", 0, 0, 0, 64, 64]);
    expect(result.frames[5]).toEqual(["expression_5", 0, 128, 64, 64, 64]);
  });

  test("creates a panel, replaces partial data, and reports non-fatally", () => {
    withFakeBrowser(() => {
      const fake = fakeTextures(true);
      const diagnostics: string[] = [];
      const canvas = registerPresentationFallback(
        fake.manager,
        `inventory-${"x".repeat(400)}\nsecret-looking-tail`,
        "inventory_panel",
        (message) => diagnostics.push(message),
      );
      expect([canvas.width, canvas.height]).toEqual([384, 256]);
      expect(fake.removed).toHaveLength(1);
      expect(diagnostics).toHaveLength(1);
      expect(diagnostics[0].length).toBeLessThanOrEqual(256);
      expect(diagnostics[0]).not.toContain("secret-looking-tail");

      expect(() =>
        registerPresentationFallback(
          fake.manager,
          "broken-reporter",
          "sprite",
          () => {
            throw new Error("reporter unavailable");
          },
        ),
      ).not.toThrow();
    });
  });
});
