import { describe, expect, mock, test } from "bun:test";
import type Phaser from "phaser";
import {
  TERRAIN_ATLAS_CELL_PX,
  TERRAIN_ATLAS_HEIGHT,
  TERRAIN_ATLAS_WIDTH,
} from "./terrain-atlas";

type FrameCall = readonly [string, number, number, number, number, number];
const NEAREST_FILTER_SENTINEL = 731;

mock.module("phaser", () => ({
  default: {
    Textures: { FilterMode: { NEAREST: NEAREST_FILTER_SENTINEL } },
  },
}));

async function withFakeTerrainBrowser<T>(run: () => Promise<T>): Promise<T> {
  const documentDescriptor = Object.getOwnPropertyDescriptor(globalThis, "document");
  const imageDescriptor = Object.getOwnPropertyDescriptor(globalThis, "Image");
  const fetchDescriptor = Object.getOwnPropertyDescriptor(globalThis, "fetch");
  const createObjectUrlDescriptor = Object.getOwnPropertyDescriptor(URL, "createObjectURL");
  const revokeObjectUrlDescriptor = Object.getOwnPropertyDescriptor(URL, "revokeObjectURL");

  class FakeImage {
    naturalWidth = TERRAIN_ATLAS_WIDTH;
    naturalHeight = TERRAIN_ATLAS_HEIGHT;
    width = TERRAIN_ATLAS_WIDTH;
    height = TERRAIN_ATLAS_HEIGHT;
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;

    set src(_value: string) {
      queueMicrotask(() => this.onload?.());
    }
  }

  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: {
      createElement(tag: string) {
        if (tag !== "canvas") throw new Error(`unexpected element: ${tag}`);
        const context = {
          drawImage() {},
          getImageData(x: number, y: number, width: number, height: number) {
            const data = new Uint8ClampedArray(width * height * 4);
            const placeholder =
              x === 10 * TERRAIN_ATLAS_CELL_PX &&
              y === TERRAIN_ATLAS_CELL_PX &&
              width === TERRAIN_ATLAS_CELL_PX &&
              height === TERRAIN_ATLAS_CELL_PX;
            for (let offset = 3; offset < data.length; offset += 4) {
              data[offset] = placeholder ? 0 : 255;
            }
            return { data };
          },
        };
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
  Object.defineProperty(globalThis, "Image", {
    configurable: true,
    value: FakeImage,
  });
  Object.defineProperty(globalThis, "fetch", {
    configurable: true,
    value: async () => ({ ok: true, blob: async () => new Blob(["terrain"]) }),
  });
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: () => "blob:terrain-atlas-test",
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: () => undefined,
  });

  try {
    return await run();
  } finally {
    if (documentDescriptor) Object.defineProperty(globalThis, "document", documentDescriptor);
    else Reflect.deleteProperty(globalThis, "document");
    if (imageDescriptor) Object.defineProperty(globalThis, "Image", imageDescriptor);
    else Reflect.deleteProperty(globalThis, "Image");
    if (fetchDescriptor) Object.defineProperty(globalThis, "fetch", fetchDescriptor);
    else Reflect.deleteProperty(globalThis, "fetch");
    if (createObjectUrlDescriptor)
      Object.defineProperty(URL, "createObjectURL", createObjectUrlDescriptor);
    else Reflect.deleteProperty(URL, "createObjectURL");
    if (revokeObjectUrlDescriptor)
      Object.defineProperty(URL, "revokeObjectURL", revokeObjectUrlDescriptor);
    else Reflect.deleteProperty(URL, "revokeObjectURL");
  }
}

describe("terrain atlas loading", () => {
  test("registers all 47 frames and applies nearest filtering", async () => {
    const { loadTerrainAtlas } = await import("./assets");
    const frames: FrameCall[] = [];
    const filters: number[] = [];
    const texture = {
      add(...args: FrameCall) {
        frames.push(args);
      },
      setFilter(filter: number) {
        filters.push(filter);
      },
    };
    const textures = {
      exists: () => false,
      remove() {},
      addCanvas() {},
      get: () => texture,
    } as unknown as Phaser.Textures.TextureManager;

    const canvas = await withFakeTerrainBrowser(() =>
      loadTerrainAtlas(
        "/api/prepared/bellweather/maps/road/ground.png",
        "prepared_ground_road",
        textures,
        "canonical-alpha",
      ),
    );

    expect([canvas.width, canvas.height]).toEqual([
      TERRAIN_ATLAS_WIDTH,
      TERRAIN_ATLAS_HEIGHT,
    ]);
    expect(filters).toEqual([NEAREST_FILTER_SENTINEL]);
    expect(frames).toHaveLength(47);
    expect(new Set(frames.map(([name]) => name)).size).toBe(47);
    expect(frames.every(([, source, , , width, height]) =>
      source === 0 &&
      width === TERRAIN_ATLAS_CELL_PX &&
      height === TERRAIN_ATLAS_CELL_PX,
    )).toBeTrue();
  });
});
