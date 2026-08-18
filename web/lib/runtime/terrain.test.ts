import { describe, expect, test } from "bun:test";
import { buildHeightmapFromSeed } from "./heightmap";
import {
  assertTerrainBoundaryStrips,
  assertTerrainIntegrationPatches,
  assertSupportedTerrainScale,
  buildTerrainPlan,
  buildTerrainRenderPlan,
  createTerrainContract,
  selectTerrainRole,
  terrainBoundaryStrips,
  terrainFillRuns,
  terrainMaterialOrigin,
  terrainScreenRect,
  terrainSurfaceYAtColumn,
  terrainSurfaceRuns,
  terrainVariant,
  visibleTerrainColumnRange,
  type TerrainPlan,
} from "./terrain";

const makeContract = (columns: number) =>
  createTerrainContract({
    columns,
    tilePixels: 16,
    baselineY: 128,
    viewportWidth: 256,
    viewportHeight: 128,
  });

describe("terrain topology", () => {
  test("selects surfaces, slopes, corners, sides, and fill from adjacency", () => {
    const heights = [2, 2, 3, 2, 1, 1];
    expect(
      heights.map((_, column) => selectTerrainRole(heights, column, 0)),
    ).toEqual([
      "top_left",
      "inner_tr",
      "top_single",
      "slope_down",
      "inner_tl",
      "top_right",
    ]);
    expect(selectTerrainRole([1, 2, 2], 0, 0)).toBe("slope_up");
    expect(selectTerrainRole(heights, 0, 1)).toBe("side_left");
    expect(selectTerrainRole(heights, 2, 1)).toBe("fill");
  });

  test("builds deterministic integer placements aligned to the collision surface", () => {
    const heights = buildHeightmapFromSeed(0x5eed, {
      cols: 512,
      minH: 1,
      maxH: 4,
      flatRun: 5,
    });
    const contract = makeContract(heights.length);
    const first = buildTerrainPlan(heights, contract);
    const second = buildTerrainPlan(heights, contract);
    expect(second).toEqual(first);
    expect(first.cells).toHaveLength(
      heights.reduce((sum, height) => sum + height, 0),
    );
    for (const cell of first.cells) {
      expect(Number.isInteger(cell.nominalRect.x)).toBe(true);
      expect(Number.isInteger(cell.nominalRect.y)).toBe(true);
      expect(Number.isInteger(cell.paintRect.x)).toBe(true);
      expect(Number.isInteger(cell.paintRect.y)).toBe(true);
      expect(cell.fillMaterial).toBe("approved-fill-derived-continuous");
      expect(cell.paintRect.y).toBe(cell.nominalRect.y);
      expect(cell.paintRect.x).toBeLessThanOrEqual(cell.nominalRect.x);
      expect(cell.paintRect.x + cell.paintRect.width).toBeGreaterThanOrEqual(
        cell.nominalRect.x + cell.nominalRect.width,
      );
      if (cell.surface) {
        expect(cell.nominalRect.y).toBe(
          terrainSurfaceYAtColumn(heights, cell.column, contract),
        );
      }
    }
    expect(terrainVariant("top_mid", 10, 0)).toBe(
      terrainVariant("top_mid", 10, 0),
    );

    const fillRuns = terrainFillRuns(first);
    expect(fillRuns.length).toBeLessThan(first.cells.length);
    for (const run of fillRuns) {
      expect(run.paintRect.x).toBe(run.startColumn * contract.tilePixels);
      expect(run.paintRect.width).toBe(
        (run.endColumn - run.startColumn + 1) * contract.tilePixels,
      );
    }

    const cellsByLevel = new Map<number, typeof first.cells>();
    for (const cell of first.cells) {
      const peers = cellsByLevel.get(cell.level) ?? [];
      cellsByLevel.set(cell.level, [...peers, cell]);
    }
    for (const peers of cellsByLevel.values()) {
      const ordered = [...peers].sort(
        (left, right) => left.column - right.column,
      );
      for (let index = 1; index < ordered.length; index += 1) {
        const left = ordered[index - 1];
        const right = ordered[index];
        if (right.column !== left.column + 1) continue;
        const overlapStart = Math.max(left.paintRect.x, right.paintRect.x);
        const overlapEnd = Math.min(
          left.paintRect.x + left.paintRect.width,
          right.paintRect.x + right.paintRect.width,
        );
        expect(overlapEnd - overlapStart).toBeGreaterThanOrEqual(
          contract.overlapPixels,
        );
        const worldX = overlapStart;
        const leftOrigin = terrainMaterialOrigin(left);
        const rightOrigin = terrainMaterialOrigin(right);
        expect(worldX - left.paintRect.x + leftOrigin.x).toBe(worldX);
        expect(worldX - right.paintRect.x + rightOrigin.x).toBe(worldX);
      }
    }
  });

  test("rejects invalid heightfields instead of rendering ambiguous geometry", () => {
    expect(() => buildTerrainPlan([1, 3], makeContract(2))).toThrow(
      "at most one tile",
    );
    expect(() => buildTerrainPlan([1, 1], makeContract(3))).toThrow("length");
    expect(() => buildTerrainPlan([0], makeContract(1))).toThrow("positive");
    expect(() =>
      createTerrainContract({
        columns: 1,
        tilePixels: 16,
        baselineY: 120,
        viewportWidth: 256,
        viewportHeight: 128,
      }),
    ).toThrow("viewport bottom");
    expect(() => terrainVariant("fill", -1, 0)).toThrow("coordinates");
  });

  test("culls by visible columns with deterministic overscan", () => {
    const contract = makeContract(100);
    expect(visibleTerrainColumnRange(160, 416, contract)).toEqual({
      start: 8,
      end: 27,
    });
    expect(visibleTerrainColumnRange(-40, 40, contract)).toEqual({
      start: 0,
      end: 4,
    });
    expect(visibleTerrainColumnRange(1_700, 1_800, contract)).toBeNull();
  });

  test("keeps every visual boundary inside a narrow contour strip at failed checkpoints", () => {
    const heights = buildHeightmapFromSeed(1_235_206_006, {
      cols: 200,
      minH: 1,
      maxH: 4,
    });
    const contract = createTerrainContract({
      columns: 200,
      tilePixels: 64,
      baselineY: 720,
      viewportWidth: 1280,
      viewportHeight: 720,
    });
    const plan = buildTerrainPlan(heights, contract);
    const frame450 = visibleTerrainColumnRange(5_496, 5_496 + 1_280, contract);
    expect(frame450).not.toBeNull();
    const strips = terrainBoundaryStrips(plan, 12).filter(
      (strip) =>
        frame450 &&
        strip.endColumn >= frame450.start &&
        strip.startColumn <= frame450.end,
    );
    expect(strips.length).toBeGreaterThan(0);
    for (const strip of strips) {
      expect(
        strip.paintRect.width === contract.tilePixels &&
          strip.paintRect.height === contract.tilePixels,
      ).toBe(false);
      expect(
        strip.paintRect.width === strip.thickness ||
          strip.paintRect.height === strip.thickness,
      ).toBe(true);
    }
    for (const cell of plan.cells) {
      expect("detailFrame" in cell).toBe(false);
    }
  });

  test("integrates opening and raised checkpoint contours only inside connected soil", () => {
    const heights = buildHeightmapFromSeed(1_235_206_006, {
      cols: 200,
      minH: 1,
      maxH: 4,
    });
    const contract = createTerrainContract({
      columns: heights.length,
      tilePixels: 64,
      baselineY: 720,
      viewportWidth: 1280,
      viewportHeight: 720,
    });
    const first = buildTerrainRenderPlan(
      buildTerrainPlan(heights, contract),
      12,
    );
    const second = buildTerrainRenderPlan(
      buildTerrainPlan(heights, contract),
      12,
    );
    expect(second.integrationPatches).toEqual(first.integrationPatches);
    for (const [left, right] of [
      [0, 1_280],
      [5_496, 6_776],
    ]) {
      const visible = first.integrationPatches.filter(
        (patch) =>
          patch.paintRect.x < right &&
          patch.paintRect.x + patch.paintRect.width > left,
      );
      expect(visible.length).toBeGreaterThan(0);
      expect(visible.some((patch) => patch.kind === "surface")).toBe(true);
      for (const patch of visible) {
        expect(patch.depth).toBeLessThanOrEqual(36);
        expect(
          patch.paintRect.width === contract.tilePixels &&
            patch.paintRect.height === contract.tilePixels,
        ).toBe(false);
        for (const x of [
          patch.paintRect.x,
          patch.paintRect.x + patch.paintRect.width - 1,
        ]) {
          const column = Math.floor(x / contract.tilePixels);
          expect(patch.paintRect.y).toBeGreaterThanOrEqual(
            terrainSurfaceYAtColumn(heights, column, contract),
          );
        }
      }
    }
  });

  test("renders flat terrain as connected body and surface runs without cap stamps", () => {
    const heights = [2, 2, 2, 2, 2, 1, 1, 1];
    const plan = buildTerrainPlan(heights, makeContract(heights.length));
    expect(terrainFillRuns(plan)).toEqual([
      expect.objectContaining({ startColumn: 0, endColumn: 7, level: 1 }),
      expect.objectContaining({ startColumn: 0, endColumn: 4, level: 2 }),
    ]);
    expect(terrainSurfaceRuns(plan, 6)).toEqual([
      expect.objectContaining({ startColumn: 0, endColumn: 4, height: 2 }),
      expect.objectContaining({ startColumn: 5, endColumn: 7, height: 1 }),
    ]);
    const flatInterior = plan.cells.filter(
      (cell) => cell.surface && cell.role === "top_mid",
    );
    expect(flatInterior.length).toBeGreaterThan(0);
    expect(flatInterior.every((cell) => !("detailFrame" in cell))).toBe(true);
  });

  test("renders flat, raised, and stepped slopes only as contour strips", () => {
    for (const heights of [
      [2, 2, 2, 2, 2],
      [1, 2, 2, 1],
      [1, 2, 3, 2, 1],
    ]) {
      const plan = buildTerrainPlan(heights, makeContract(heights.length));
      const render = buildTerrainRenderPlan(plan, 6);
      expect(render.mode).toBe(
        "continuous-material-with-boundary-integration-v2",
      );
      expect(Object.keys(render).sort()).toEqual([
        "boundaryStrips",
        "fillRuns",
        "integrationPatches",
        "mode",
      ]);
      assertTerrainBoundaryStrips(plan, render.boundaryStrips, 6);
      assertTerrainIntegrationPatches(
        plan,
        render.boundaryStrips,
        render.integrationPatches,
        6,
      );
      expect(render.boundaryStrips.length).toBeGreaterThan(0);
      for (const strip of render.boundaryStrips) {
        expect("frame" in strip).toBe(false);
        expect("texture" in strip).toBe(false);
        expect(
          strip.paintRect.width === plan.contract.tilePixels &&
            strip.paintRect.height === plan.contract.tilePixels,
        ).toBe(false);
      }
      expectBoundaryPixelsStayOnContour(plan, render.boundaryStrips);
      const firstStrip = render.boundaryStrips[0];
      const poisoned = [
        Object.freeze({
          ...firstStrip,
          paintRect: Object.freeze({
            ...firstStrip.paintRect,
            width: plan.contract.tilePixels,
            height: plan.contract.tilePixels,
          }),
        }),
        ...render.boundaryStrips.slice(1),
      ];
      expect(() => assertTerrainBoundaryStrips(plan, poisoned, 6)).toThrow(
        "full-cell frame",
      );
    }
  });
});

function expectBoundaryPixelsStayOnContour(
  plan: TerrainPlan,
  strips: ReturnType<typeof terrainBoundaryStrips>,
): void {
  const { contract } = plan;
  const solidAt = (x: number, y: number): boolean => {
    if (x < 0 || x >= contract.columns * contract.tilePixels) return false;
    const column = Math.floor(x / contract.tilePixels);
    return y >= terrainSurfaceYAtColumn(plan.heights, column, contract);
  };
  for (const strip of strips) {
    const { x, y, width, height } = strip.paintRect;
    for (let worldY = y; worldY < y + height; worldY += 1) {
      for (let worldX = x; worldX < x + width; worldX += 1) {
        expect(solidAt(worldX, worldY)).toBe(true);
        if (strip.kind === "surface") {
          expect(worldY - y).toBeLessThan(strip.thickness);
          expect(solidAt(worldX, y - 1)).toBe(false);
        } else if (strip.kind === "side-left") {
          expect(worldX - x).toBeLessThan(strip.thickness);
          expect(solidAt(x - 1, worldY)).toBe(false);
        } else {
          expect(x + width - 1 - worldX).toBeLessThan(strip.thickness);
          expect(solidAt(x + width, worldY)).toBe(false);
        }
      }
    }
  }
}

function rasterizeCoverage(
  plan: TerrainPlan,
  cameraLeft: number,
  zoom: number,
  devicePixelRatio: number,
): Uint8Array {
  const { contract } = plan;
  const deviceWidth = Math.ceil(contract.viewportWidth * devicePixelRatio);
  const deviceHeight = Math.ceil(contract.viewportHeight * devicePixelRatio);
  const raster = new Uint8Array(deviceWidth * deviceHeight);
  const worldRight = cameraLeft + contract.viewportWidth / zoom;
  const range = visibleTerrainColumnRange(cameraLeft, worldRight, contract);
  if (!range) return raster;
  for (const cell of plan.cells) {
    if (cell.column < range.start || cell.column > range.end) continue;
    const projected = terrainScreenRect(
      cell.paintRect,
      cameraLeft,
      0,
      zoom,
      devicePixelRatio,
    );
    const x0 = Math.max(0, Math.floor(projected.x));
    const y0 = Math.max(0, Math.floor(projected.y));
    const x1 = Math.min(deviceWidth, Math.ceil(projected.x + projected.width));
    const y1 = Math.min(
      deviceHeight,
      Math.ceil(projected.y + projected.height),
    );
    for (let y = y0; y < y1; y += 1) {
      raster.fill(1, y * deviceWidth + x0, y * deviceWidth + x1);
    }
  }
  return raster;
}

function expectIdealSolidPixelsCovered(
  plan: TerrainPlan,
  cameraLeft: number,
  zoom: number,
  devicePixelRatio: number,
): void {
  const { contract, heights } = plan;
  const raster = rasterizeCoverage(plan, cameraLeft, zoom, devicePixelRatio);
  const deviceWidth = Math.ceil(contract.viewportWidth * devicePixelRatio);
  const deviceHeight = Math.ceil(contract.viewportHeight * devicePixelRatio);
  const scale = zoom * devicePixelRatio;
  for (let y = 0; y < deviceHeight; y += 1) {
    const worldY = (y + 0.5) / scale;
    if (worldY >= contract.baselineY) continue;
    for (let x = 0; x < deviceWidth; x += 1) {
      const worldX = cameraLeft + (x + 0.5) / scale;
      const column = Math.floor(worldX / contract.tilePixels);
      if (column < 0 || column >= heights.length) continue;
      const surfaceY = terrainSurfaceYAtColumn(heights, column, contract);
      if (worldY >= surfaceY) {
        expect(raster[y * deviceWidth + x]).toBe(1);
      }
    }
  }
}

describe("terrain raster coverage", () => {
  test("has no uncovered pixels across long slopes, camera positions, zooms, and DPRs", () => {
    const heights = buildHeightmapFromSeed(0xc0ffee, {
      cols: 320,
      minH: 1,
      maxH: 4,
      flatRun: 4,
    });
    const plan = buildTerrainPlan(heights, makeContract(heights.length));
    for (const zoom of [1, 1.2, 1.5, 2]) {
      const visibleWorldWidth = plan.contract.viewportWidth / zoom;
      const lastCamera =
        plan.contract.columns * plan.contract.tilePixels - visibleWorldWidth;
      for (const dpr of [1, 1.25, 2, 3, 4]) {
        for (const cameraLeft of [0, 173.375, lastCamera]) {
          expectIdealSolidPixelsCovered(plan, cameraLeft, zoom, dpr);
        }
      }
    }
  });

  test("bounds the supported affine projection contract", () => {
    expect(() => assertSupportedTerrainScale(1, 1)).not.toThrow();
    expect(() => assertSupportedTerrainScale(2, 4)).not.toThrow();
    expect(() => assertSupportedTerrainScale(0.99, 1)).toThrow("zoom");
    expect(() => assertSupportedTerrainScale(1, 4.01)).toThrow(
      "device pixel ratio",
    );
  });
});
