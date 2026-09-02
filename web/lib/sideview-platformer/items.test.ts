import { describe, expect, test } from "bun:test";
import type Phaser from "phaser";
import {
  DROP_BOUNCE_RESTITUTION,
  DROP_POP_VX_MIN_PX,
  DROP_POP_VY_MIN_PX,
  ItemSystem,
  dropPopVelocity,
} from "./items";
import { terrainSurfaceY } from "./terrain";

class FakeImage {
  x: number;
  y: number;
  active = true;
  private data = new Map<string, unknown>();

  constructor(x: number, y: number) {
    this.x = x;
    this.y = y;
  }

  setOrigin(): this {
    return this;
  }

  setDisplaySize(): this {
    return this;
  }

  setDepth(): this {
    return this;
  }

  setData(key: string, value: unknown): this {
    this.data.set(key, value);
    return this;
  }

  getData(key: string): unknown {
    return this.data.get(key);
  }

  getBounds() {
    return { left: this.x - 8, right: this.x + 8, top: this.y - 16, bottom: this.y };
  }

  destroy(): void {
    this.active = false;
  }
}

function fakeScene(): Phaser.Scene {
  return {
    add: {
      image(x: number, y: number): FakeImage {
        return new FakeImage(x, y);
      },
    },
    textures: {
      exists: () => true,
      get: () => ({ get: () => ({ width: 32, height: 32 }) }),
    },
  } as unknown as Phaser.Scene;
}

const TILE = 64;
const BASELINE = 720;
const HEIGHT = 2;
const SURFACE = terrainSurfaceY(HEIGHT, TILE, BASELINE);

function system(worldWidthPx?: number): ItemSystem {
  return new ItemSystem({
    scene: fakeScene(),
    tilePx: TILE,
    baselineY: BASELINE,
    heightFn: () => HEIGHT,
    itemTextureKey: "items",
    worldWidthPx,
  });
}

describe("drop pop arc", () => {
  test("launch velocity is deterministic, upward, and follows the blow direction", () => {
    expect(dropPopVelocity(3, 1)).toEqual(dropPopVelocity(3, 1));
    const right = dropPopVelocity(3, 1);
    const left = dropPopVelocity(3, -1);
    expect(right.vx).toBeGreaterThanOrEqual(DROP_POP_VX_MIN_PX);
    expect(left.vx).toBe(-right.vx);
    expect(right.vy).toBeLessThanOrEqual(-DROP_POP_VY_MIN_PX);
    expect(Math.sign(dropPopVelocity(2, 0).vx)).toBe(1);
    expect(Math.sign(dropPopVelocity(3, 0).vx)).toBe(-1);
    expect(() => dropPopVelocity(-1, 1)).toThrow();
  });

  test("a drop rises, bounces exactly once on the surface, then settles and bobs", () => {
    const items = system();
    const item = items.drop(320, SURFACE - TILE, 0, 1)!;
    const startY = item.sprite.y;
    let minY = startY;
    let bouncedAt: number | null = null;
    let settledAt: number | null = null;
    for (let frame = 1; frame <= 120; frame += 1) {
      items.update(1000 / 60, frame * (1000 / 60));
      minY = Math.min(minY, item.sprite.y);
      if (bouncedAt === null && item.bounces === 1) bouncedAt = frame;
      if (settledAt === null && item.settled) settledAt = frame;
    }
    expect(minY).toBeLessThan(startY);
    expect(bouncedAt).not.toBeNull();
    expect(settledAt).not.toBeNull();
    expect(settledAt!).toBeGreaterThan(bouncedAt!);
    expect(item.bounces).toBe(1);
    expect(item.vx).toBe(0);
    expect(item.sprite.x).toBeGreaterThan(320);
    expect(Math.abs(item.sprite.getData("groundY") as number - SURFACE)).toBe(0);
    expect(Math.abs(item.sprite.y - SURFACE)).toBeLessThanOrEqual(2);
  });

  test("the bounce retains the authored restitution and never leaves the surface twice", () => {
    const items = system();
    const item = items.drop(320, SURFACE, 0, 1)!;
    // Land it hard on the first frame so the bounce is measurable in isolation.
    item.vy = 600;
    items.update(1000 / 60, 16);
    expect(item.bounces).toBe(1);
    expect(item.sprite.y).toBe(SURFACE);
    expect(item.vy).toBeCloseTo(-(600 + 1500 / 60) * DROP_BOUNCE_RESTITUTION, 6);
    expect(item.settled).toBeFalse();
  });

  test("two systems replay the same arc frame for frame", () => {
    const left = system();
    const right = system();
    const first = left.drop(200, SURFACE - TILE, 1, -1)!;
    const second = right.drop(200, SURFACE - TILE, 1, -1)!;
    for (let frame = 1; frame <= 90; frame += 1) {
      left.update(1000 / 60, frame * (1000 / 60));
      right.update(1000 / 60, frame * (1000 / 60));
      expect(second.sprite.x).toBe(first.sprite.x);
      expect(second.sprite.y).toBe(first.sprite.y);
    }
  });

  test("a pop is clamped inside the world when a width is known", () => {
    const items = system(TILE * 4);
    const item = items.drop(TILE * 4 - 4, SURFACE - TILE, 0, 1)!;
    for (let frame = 1; frame <= 60; frame += 1) items.update(1000 / 60, frame * (1000 / 60));
    expect(item.sprite.x).toBeLessThanOrEqual(TILE * 4 - TILE / 2);
  });
});
