import { describe, expect, test } from "bun:test";
import {
  FOREGROUND_PAINTED_ALPHA_THRESHOLD,
  measureForegroundRaster,
  prepareForegroundRaster,
  type ForegroundRaster,
} from "./foreground";

function raster(width: number, height: number): ForegroundRaster {
  return { width, height, data: new Uint8ClampedArray(width * height * 4) };
}

function paint(
  target: ForegroundRaster,
  x: number,
  y: number,
  rgba: readonly [number, number, number, number],
): void {
  const offset = (y * target.width + x) * 4;
  target.data.set(rgba, offset);
}

function pixel(
  target: ForegroundRaster,
  x: number,
  y: number,
): readonly number[] {
  const offset = (y * target.width + x) * 4;
  return [...target.data.slice(offset, offset + 4)];
}

function measuredFixture(): ForegroundRaster {
  const target = raster(16, 12);
  paint(target, 0, 1, [20, 40, 60, 90]);
  for (let y = 5; y <= 7; y += 1) {
    for (let x = 2; x <= 9; x += 1) {
      paint(target, x, y, [x * 8, y * 10, 130, 180]);
    }
  }
  for (let y = 8; y <= 10; y += 1) {
    for (let x = 1; x <= 14; x += 1) {
      paint(target, x, y, [x * 9, y * 11, 180, 255]);
    }
  }
  paint(target, 15, 11, [200, 210, 220, 80]);
  return target;
}

describe("foreground runtime preparation", () => {
  test("measures sparse alpha separately from meaningful content and contact", () => {
    const measured = measureForegroundRaster(measuredFixture());
    expect(measured.contentBounds).toEqual({
      left: 0,
      top: 1,
      right: 16,
      bottom: 12,
    });
    expect(measured.meaningfulContentBounds).toEqual({
      left: 1,
      top: 5,
      right: 15,
      bottom: 11,
    });
    expect(measured.contactStrip).toEqual({
      top: 8,
      bottom: 11,
      minimumCoveragePixels: 13,
      maximumCoveragePixels: 14,
    });
  });

  test("vertically trims full width and emits one W-minus-F repeat period", () => {
    const source = measuredFixture();
    const prepared = prepareForegroundRaster(source, 4);
    expect({ width: prepared.width, height: prepared.height }).toEqual({
      width: 12,
      height: 11,
    });
    expect(prepared.repeatPeriod).toBe(12);
    expect(prepared.overlap).toBe(4);
    expect(prepared.contactStrip).toMatchObject({ top: 7, bottom: 10 });
    expect(prepared.contactSourceY).toBe(9);
    expect(prepared.sourceContentBounds).toEqual({
      left: 0,
      top: 1,
      right: 16,
      bottom: 12,
    });
    for (let y = 0; y < prepared.height; y += 1) {
      for (let x = 4; x < prepared.width; x += 1) {
        expect(pixel(prepared, x, y)).toEqual(pixel(source, x, y + 1));
      }
    }
  });

  test("uses exact complementary premultiplied endpoints without alpha holes", () => {
    const source = raster(16, 2);
    for (let y = 0; y < source.height; y += 1) {
      for (let x = 0; x < source.width; x += 1) {
        paint(source, x, y, [x * 12, 240 - x * 8, 40 + x, 80 + x * 10]);
      }
    }
    const prepared = prepareForegroundRaster(source, 4);
    const denominator = 3;
    const headAlpha = pixel(source, 1, 0)[3]!;
    const tailAlpha = pixel(source, 13, 0)[3]!;
    expect(pixel(prepared, 1, 0)[3]).toBe(
      Math.round((headAlpha + tailAlpha * 2) / denominator),
    );
    for (let y = 0; y < prepared.height; y += 1) {
      expect(pixel(prepared, 0, y)).toEqual(pixel(source, 12, y));
      expect(pixel(prepared, 3, y)).toEqual(pixel(source, 3, y));
      for (let x = 0; x < prepared.width; x += 1) {
        expect(pixel(prepared, x, y)[3]).toBeGreaterThan(0);
      }
    }
  });

  test("preserves source-local gradients at both periodic boundaries", () => {
    const source = raster(16, 3);
    for (let y = 0; y < source.height; y += 1) {
      for (let x = 0; x < source.width; x += 1) {
        paint(source, x, y, [x * 10, 50 + x * 5, 180 - x * 3, 255]);
      }
    }
    const prepared = prepareForegroundRaster(source, 4);
    for (let y = 0; y < prepared.height; y += 1) {
      expect(pixel(prepared, 0, y)).toEqual(pixel(source, 12, y));
      expect(pixel(prepared, 11, y)).toEqual(pixel(source, 11, y));
      expect(pixel(prepared, 3, y)).toEqual(pixel(source, 3, y));
      expect(pixel(prepared, 4, y)).toEqual(pixel(source, 4, y));
      for (let channel = 0; channel < 4; channel += 1) {
        expect(
          Math.abs(
            pixel(prepared, 0, y)[channel]! - pixel(prepared, 11, y)[channel]!,
          ),
        ).toBe(
          Math.abs(
            pixel(source, 12, y)[channel]! - pixel(source, 11, y)[channel]!,
          ),
        );
        expect(
          Math.abs(
            pixel(prepared, 4, y)[channel]! - pixel(prepared, 3, y)[channel]!,
          ),
        ).toBe(
          Math.abs(
            pixel(source, 4, y)[channel]! - pixel(source, 3, y)[channel]!,
          ),
        );
      }
      const threePeriods = Buffer.concat([
        Buffer.from(prepared.data),
        Buffer.from(prepared.data),
        Buffer.from(prepared.data),
      ]);
      expect(threePeriods.subarray(0, prepared.data.length)).toEqual(
        threePeriods.subarray(prepared.data.length, prepared.data.length * 2),
      );
    }
  });

  test("rejects empty alpha, invalid byte lengths, and ambiguous overlaps", () => {
    expect(() => measureForegroundRaster(raster(16, 12))).toThrow(
      "painted alpha",
    );
    const subthreshold = raster(16, 12);
    paint(subthreshold, 0, 0, [
      255,
      255,
      255,
      FOREGROUND_PAINTED_ALPHA_THRESHOLD,
    ]);
    expect(() => measureForegroundRaster(subthreshold)).toThrow(
      "painted alpha",
    );
    expect(() =>
      measureForegroundRaster({
        width: 16,
        height: 12,
        data: new Uint8ClampedArray(4),
      }),
    ).toThrow("byte length");
    const source = measuredFixture();
    for (const overlap of [0, 1, 8, 16]) {
      expect(() => prepareForegroundRaster(source, overlap)).toThrow(
        "nonempty byte-preserved middle band",
      );
    }
  });
});
