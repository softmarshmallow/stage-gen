import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { PNG } from "pngjs";
import {
  atlasExtrusionBlits,
  cellRectFor,
  contentRectFor,
  deriveTerrainMaterialProfile,
  deriveTerrainSideBand,
  deriveTerrainSurfaceBand,
  terrainIntegrationPixel,
  terrainMaterialPixel,
  terrainMaterialPixelFromSource,
  TILE_ROLE_CONTRACTS,
  TILE_ROLES,
  TILESET_COLS,
  TILESET_ROWS,
  tilesetGeometry,
} from "./tiles";

describe("terrain atlas contract", () => {
  test("maps every role and variant to an exact isolated grid cell", () => {
    const geometry = tilesetGeometry(384, 128);
    expect(geometry).toEqual({
      sheetWidth: 384,
      sheetHeight: 128,
      cellWidth: 32,
      cellHeight: 32,
      gutterPixels: 2,
      contentWidth: 28,
      contentHeight: 28,
    });
    expect(TILE_ROLES).toHaveLength(16);
    for (const role of TILE_ROLES) {
      const seen = new Set<number>();
      for (let variant = 0; variant < 3; variant += 1) {
        const cell = cellRectFor(role, 384, 128, variant);
        const content = contentRectFor(role, 384, 128, variant);
        expect(cell.x % 32).toBe(0);
        expect(cell.y % 32).toBe(0);
        expect(content).toEqual({
          x: cell.x + 2,
          y: cell.y + 2,
          w: 28,
          h: 28,
        });
        seen.add(cell.x / 32);
      }
      expect(seen.size).toBe(3);
      expect(TILE_ROLE_CONTRACTS[role].role).toBe(role);
    }
  });

  test("edge extrusion covers each destination cell from only its own content", () => {
    const geometry = tilesetGeometry(384, 128);
    const blits = atlasExtrusionBlits(384, 128);
    expect(blits).toHaveLength(TILESET_ROWS * TILESET_COLS * 9);
    for (let row = 0; row < TILESET_ROWS; row += 1) {
      for (let column = 0; column < TILESET_COLS; column += 1) {
        const coverage = new Uint8Array(
          geometry.cellWidth * geometry.cellHeight,
        );
        const cellBlits = blits.filter(
          (blit) => blit.row === row && blit.column === column,
        );
        expect(cellBlits).toHaveLength(9);
        const cellX = column * geometry.cellWidth;
        const cellY = row * geometry.cellHeight;
        for (const blit of cellBlits) {
          expect(blit.source.x).toBeGreaterThanOrEqual(
            cellX + geometry.gutterPixels,
          );
          expect(blit.source.y).toBeGreaterThanOrEqual(
            cellY + geometry.gutterPixels,
          );
          expect(blit.source.x + blit.source.w).toBeLessThanOrEqual(
            cellX + geometry.cellWidth - geometry.gutterPixels,
          );
          expect(blit.source.y + blit.source.h).toBeLessThanOrEqual(
            cellY + geometry.cellHeight - geometry.gutterPixels,
          );
          expect(blit.target.x).toBeGreaterThanOrEqual(cellX);
          expect(blit.target.y).toBeGreaterThanOrEqual(cellY);
          expect(blit.target.x + blit.target.w).toBeLessThanOrEqual(
            cellX + geometry.cellWidth,
          );
          expect(blit.target.y + blit.target.h).toBeLessThanOrEqual(
            cellY + geometry.cellHeight,
          );
          for (
            let y = blit.target.y;
            y < blit.target.y + blit.target.h;
            y += 1
          ) {
            for (
              let x = blit.target.x;
              x < blit.target.x + blit.target.w;
              x += 1
            ) {
              const local = (y - cellY) * geometry.cellWidth + (x - cellX);
              coverage[local] += 1;
            }
          }
        }
        expect([...coverage].every((count) => count === 1)).toBe(true);
      }
    }
  });

  test("rejects ambiguous sheet and variant geometry", () => {
    expect(() => tilesetGeometry(383, 128)).toThrow("exactly divisible");
    expect(() => tilesetGeometry(48, 8, 4)).toThrow("no cell content");
    expect(() => cellRectFor("fill", 384, 128, -1)).toThrow("variant");
    expect(() => cellRectFor("fill", 384, 128, 3)).toThrow("variant");
  });

  test("derives a periodic non-flat material without preserving cell motifs", () => {
    const profile = deriveTerrainMaterialProfile(
      Uint8ClampedArray.from([10, 20, 30, 255, 30, 40, 50, 255]),
    );
    expect(profile).toMatchObject({
      meanRed: 20,
      meanGreen: 30,
      meanBlue: 40,
      spreadRed: 10,
      spreadGreen: 10,
      spreadBlue: 10,
      derivation: "approved-fill-palette-periodic-strata-v2",
    });
    const colors = new Set<string>();
    const redSamples: number[] = [];
    for (let y = 0; y < 256; y += 16) {
      for (let x = 0; x < 256; x += 16) {
        const pixel = terrainMaterialPixel(profile, x, y, 256);
        colors.add(`${pixel.red}:${pixel.green}:${pixel.blue}`);
        redSamples.push(pixel.red);
        expect(terrainMaterialPixel(profile, x + 256, y, 256)).toEqual(pixel);
        expect(terrainMaterialPixel(profile, x, y + 256, 256)).toEqual(pixel);
        expect(pixel.alpha).toBe(255);
      }
    }
    expect(colors.size).toBeGreaterThan(1);
    const meanRed =
      redSamples.reduce((sum, value) => sum + value, 0) / redSamples.length;
    const spreadRed = Math.sqrt(
      redSamples.reduce((sum, value) => sum + (value - meanRed) ** 2, 0) /
        redSamples.length,
    );
    expect(spreadRed).toBeGreaterThan(6);
    expect(spreadRed).toBeLessThan(12);
    const left = terrainMaterialPixel(profile, 0, 80, 256);
    const wrappedLeft = terrainMaterialPixel(profile, 255, 80, 256);
    expect(Math.abs(left.red - wrappedLeft.red)).toBeLessThanOrEqual(1);
    expect(Math.abs(left.green - wrappedLeft.green)).toBeLessThanOrEqual(1);
    expect(Math.abs(left.blue - wrappedLeft.blue)).toBeLessThanOrEqual(1);
    expect(() =>
      deriveTerrainMaterialProfile(Uint8ClampedArray.from([1, 2, 3, 0])),
    ).toThrow("opaque 8-bit RGBA");

    const source = Uint8ClampedArray.from([10, 20, 30, 255, 30, 40, 50, 255]);
    const sampled = terrainMaterialPixelFromSource(
      profile,
      source,
      2,
      1,
      73,
      99,
      512,
    );
    expect(
      terrainMaterialPixelFromSource(profile, source, 2, 1, 73 + 512, 99, 512),
    ).toEqual(sampled);
    expect(sampled.alpha).toBe(255);
    const seamDeltas: number[] = [];
    for (let sampleY = 0; sampleY < 512; sampleY += 16) {
      const left = terrainMaterialPixelFromSource(
        profile,
        source,
        2,
        1,
        0,
        sampleY,
        512,
      );
      const right = terrainMaterialPixelFromSource(
        profile,
        source,
        2,
        1,
        511,
        sampleY,
        512,
      );
      seamDeltas.push(
        Math.max(
          Math.abs(left.red - right.red),
          Math.abs(left.green - right.green),
          Math.abs(left.blue - right.blue),
        ),
      );
    }
    expect(Math.max(...seamDeltas)).toBeLessThanOrEqual(2);
    expect(() =>
      terrainMaterialPixelFromSource(profile, source, 3, 1, 0, 0, 512),
    ).toThrow("dimensions");
  });

  test("varies boundary integration depth without a cell-periodic edge", () => {
    const source = Uint8ClampedArray.from(
      Array.from({ length: 32 }, (_, index) => [
        25 + index * 2,
        55 + index * 2,
        45 + index,
        255,
      ]).flat(),
    );
    const profile = deriveTerrainMaterialProfile(source);
    const transitionDepths: number[] = [];
    for (let along = 0; along < 512; along += 1) {
      let transition = -1;
      for (let depth = 0; depth < 36; depth += 1) {
        const pixel = terrainIntegrationPixel(profile, "surface", along, depth);
        if (pixel.alpha > 0) transition = depth;
        expect(pixel).toEqual(
          terrainIntegrationPixel(profile, "surface", along + 512, depth),
        );
      }
      transitionDepths.push(transition);
    }
    expect(standardDeviation(transitionDepths)).toBeGreaterThanOrEqual(3);
    const bins = new Map<number, number>();
    for (const depth of transitionDepths) {
      bins.set(depth, (bins.get(depth) ?? 0) + 1);
    }
    expect(Math.max(...bins.values())).toBeLessThan(512 * 0.25);
    expect(terrainIntegrationPixel(profile, "side-left", 80, 10)).not.toEqual(
      terrainIntegrationPixel(profile, "side-right", 80, 10),
    );
    expect(() => terrainIntegrationPixel(profile, "surface", 0, 36)).toThrow(
      "coordinates",
    );
  });

  test("extracts one continuous cap band without full-cell stems", () => {
    const source = new Uint8ClampedArray(8 * 8 * 4);
    for (let y = 2; y < 7; y += 1) {
      for (let x = 1; x < 7; x += 1) {
        const offset = (y * 8 + x) * 4;
        source[offset] = 20 + x * 3;
        source[offset + 1] = 50 + y * 4;
        source[offset + 2] = 40 + x + y;
        source[offset + 3] = 255;
      }
    }
    // A stem exists below the five-row cap and must never enter the output.
    source[(7 * 8 + 4) * 4 + 3] = 255;
    const before = Uint8ClampedArray.from(source);
    const band = deriveTerrainSurfaceBand(source, 8, 8, 64, 12);
    expect(band).toHaveLength(64 * 12 * 4);
    expect(source).toEqual(before);
    expect(
      [...Array(64).keys()].every((x) =>
        [...Array(12).keys()].some((y) => band[(y * 64 + x) * 4 + 3] > 0),
      ),
    ).toBe(true);
    expect(deriveTerrainSurfaceBand(source, 8, 8, 64, 12)).toEqual(band);
    expect(() =>
      deriveTerrainSurfaceBand(new Uint8ClampedArray(8 * 8 * 4), 8, 8),
    ).toThrow("painted pixels");
  });

  test("extracts narrow side bands without interior cell fragments", () => {
    const source = new Uint8ClampedArray(16 * 16 * 4);
    for (let y = 1; y < 15; y += 1) {
      for (let x = 1; x < 15; x += 1) {
        const offset = (y * 16 + x) * 4;
        source[offset] = 20 + x;
        source[offset + 1] = 40 + y;
        source[offset + 2] = 60;
        source[offset + 3] = 255;
      }
    }
    // A conspicuous interior slab must be outside both five-column corridors.
    for (let y = 4; y < 12; y += 1) {
      for (let x = 7; x < 9; x += 1) {
        const offset = (y * 16 + x) * 4;
        source[offset] = 250;
        source[offset + 1] = 0;
        source[offset + 2] = 0;
      }
    }
    const before = Uint8ClampedArray.from(source);
    const left = deriveTerrainSideBand(source, 16, 16, "left", 6, 64);
    const right = deriveTerrainSideBand(source, 16, 16, "right", 6, 64);
    expect(source).toEqual(before);
    expect(left).toHaveLength(6 * 64 * 4);
    expect(right).toHaveLength(6 * 64 * 4);
    expect(
      [...left, ...right]
        .filter((_, index) => index % 4 === 0)
        .every((red) => red < 100),
    ).toBe(true);
    expect(
      [...left, ...right]
        .filter((_, index) => index % 4 === 3)
        .every((alpha) => alpha === 255),
    ).toBe(true);
    expect(deriveTerrainSideBand(source, 16, 16, "left", 6, 64)).toEqual(left);
    expect(() =>
      deriveTerrainSideBand(new Uint8ClampedArray(16 * 16 * 4), 16, 16, "left"),
    ).toThrow("painted pixels");
  });

  test("keeps approved-palette strata rich without 32/64/128px cadence", () => {
    const atlasPath = path.resolve(
      import.meta.dir,
      "../../../fixtures/gameplay-demo/tileset.png",
    );
    const atlas = PNG.sync.read(readFileSync(atlasPath), {
      checkCRC: true,
      skipRescale: false,
    });
    const fill = contentRectFor("fill", atlas.width, atlas.height, 0);
    const source = new Uint8ClampedArray(fill.w * fill.h * 4);
    for (let y = 0; y < fill.h; y += 1) {
      const start = ((fill.y + y) * atlas.width + fill.x) * 4;
      source.set(
        atlas.data.subarray(start, start + fill.w * 4),
        y * fill.w * 4,
      );
    }
    const profile = deriveTerrainMaterialProfile(source);
    const size = 512;
    const luminance = new Float64Array(size * size);
    for (let y = 0; y < size; y += 1) {
      for (let x = 0; x < size; x += 1) {
        const pixel = terrainMaterialPixelFromSource(
          profile,
          source,
          fill.w,
          fill.h,
          x,
          y,
          size,
        );
        luminance[y * size + x] = pixelLuminance(pixel);
      }
    }
    const sourceLuminance = new Float64Array(fill.w * fill.h);
    for (let index = 0; index < sourceLuminance.length; index += 1) {
      const offset = index * 4;
      sourceLuminance[index] =
        source[offset] * 0.2126 +
        source[offset + 1] * 0.7152 +
        source[offset + 2] * 0.0722;
    }
    const metrics = {
      sourceStdDev: standardDeviation(sourceLuminance),
      outputStdDev: standardDeviation(luminance),
      detail4: differenceOfBlockMeansRms(luminance, size, 1, 4),
      detail16: differenceOfBlockMeansRms(luminance, size, 4, 16),
      detail64: differenceOfBlockMeansRms(luminance, size, 16, 64),
      x32: normalizedAutocorrelation(luminance, size, 32, 0),
      x64: normalizedAutocorrelation(luminance, size, 64, 0),
      x128: normalizedAutocorrelation(luminance, size, 128, 0),
      y32: normalizedAutocorrelation(luminance, size, 0, 32),
      y64: normalizedAutocorrelation(luminance, size, 0, 64),
      y128: normalizedAutocorrelation(luminance, size, 0, 128),
      boundaryCadence: cellBoundaryGradientRatio(luminance, size, 64),
    };
    expect(metrics.outputStdDev).toBeGreaterThanOrEqual(
      Math.max(8, metrics.sourceStdDev * 0.65),
    );
    expect(metrics.detail4).toBeGreaterThanOrEqual(2);
    expect(metrics.detail16).toBeGreaterThanOrEqual(3);
    expect(metrics.detail64).toBeGreaterThanOrEqual(4);
    for (const correlation of [
      metrics.x32,
      metrics.x64,
      metrics.x128,
      metrics.y32,
      metrics.y64,
      metrics.y128,
    ]) {
      expect(Math.abs(correlation)).toBeLessThan(0.15);
    }
    expect(metrics.boundaryCadence).toBeGreaterThan(0.7);
    expect(metrics.boundaryCadence).toBeLessThan(1.3);
  });
});

function pixelLuminance(pixel: {
  red: number;
  green: number;
  blue: number;
}): number {
  return pixel.red * 0.2126 + pixel.green * 0.7152 + pixel.blue * 0.0722;
}

function standardDeviation(values: ArrayLike<number>): number {
  let sum = 0;
  for (let index = 0; index < values.length; index += 1) {
    sum += values[index] ?? 0;
  }
  const mean = sum / values.length;
  let squared = 0;
  for (let index = 0; index < values.length; index += 1) {
    squared += ((values[index] ?? 0) - mean) ** 2;
  }
  return Math.sqrt(squared / values.length);
}

function blockMeans(
  values: Float64Array,
  width: number,
  block: number,
): Float64Array {
  const blocks = width / block;
  const output = new Float64Array(blocks * blocks);
  for (let blockY = 0; blockY < blocks; blockY += 1) {
    for (let blockX = 0; blockX < blocks; blockX += 1) {
      let total = 0;
      for (let y = 0; y < block; y += 1) {
        for (let x = 0; x < block; x += 1) {
          total += values[(blockY * block + y) * width + blockX * block + x];
        }
      }
      output[blockY * blocks + blockX] = total / (block * block);
    }
  }
  return output;
}

function differenceOfBlockMeansRms(
  values: Float64Array,
  width: number,
  smaller: number,
  larger: number,
): number {
  const small = blockMeans(values, width, smaller);
  const large = blockMeans(values, width, larger);
  const smallWidth = width / smaller;
  const ratio = larger / smaller;
  let squared = 0;
  for (let y = 0; y < smallWidth; y += 1) {
    for (let x = 0; x < smallWidth; x += 1) {
      const delta =
        small[y * smallWidth + x] -
        large[Math.floor(y / ratio) * (width / larger) + Math.floor(x / ratio)];
      squared += delta * delta;
    }
  }
  return Math.sqrt(squared / small.length);
}

function normalizedAutocorrelation(
  values: Float64Array,
  width: number,
  lagX: number,
  lagY: number,
): number {
  const mean =
    [...values].reduce((sum, value) => sum + value, 0) / values.length;
  let numerator = 0;
  let denominator = 0;
  for (let y = 0; y < width; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const value = values[y * width + x] - mean;
      const peer =
        values[((y + lagY) % width) * width + ((x + lagX) % width)] - mean;
      numerator += value * peer;
      denominator += value * value;
    }
  }
  return numerator / denominator;
}

function cellBoundaryGradientRatio(
  values: Float64Array,
  width: number,
  cellPixels: number,
): number {
  let boundaryTotal = 0;
  let boundaryCount = 0;
  let allTotal = 0;
  let allCount = 0;
  for (let y = 0; y < width; y += 1) {
    for (let x = 1; x < width; x += 1) {
      const delta = Math.abs(values[y * width + x] - values[y * width + x - 1]);
      allTotal += delta;
      allCount += 1;
      if (x % cellPixels === 0) {
        boundaryTotal += delta;
        boundaryCount += 1;
      }
    }
  }
  return boundaryTotal / boundaryCount / (allTotal / allCount);
}
