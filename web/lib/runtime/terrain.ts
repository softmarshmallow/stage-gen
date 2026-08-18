import {
  TERRAIN_WORLD_OVERLAP_PIXELS,
  TILESET_VARIANTS,
  TILE_ROLES,
  type TileRole,
} from "./tiles";

export type TerrainRect = Readonly<{
  x: number;
  y: number;
  width: number;
  height: number;
}>;

export type TerrainContract = Readonly<{
  columns: number;
  tilePixels: number;
  baselineY: number;
  viewportWidth: number;
  viewportHeight: number;
  overlapPixels: number;
  cullOverscanColumns: number;
}>;

export type TerrainAdjacency = Readonly<{
  leftSolid: boolean;
  rightSolid: boolean;
  aboveSolid: boolean;
  belowSolid: boolean;
}>;

export type TerrainCellPlan = Readonly<{
  column: number;
  depth: number;
  level: number;
  surface: boolean;
  role: TileRole;
  variant: number;
  fillMaterial: "approved-fill-derived-continuous";
  adjacency: TerrainAdjacency;
  nominalRect: TerrainRect;
  paintRect: TerrainRect;
}>;

export type TerrainPlan = Readonly<{
  contract: TerrainContract;
  heights: readonly number[];
  cells: readonly TerrainCellPlan[];
}>;

export type TerrainFillRun = Readonly<{
  startColumn: number;
  endColumn: number;
  level: number;
  paintRect: TerrainRect;
}>;

export type TerrainSurfaceRun = Readonly<{
  startColumn: number;
  endColumn: number;
  height: number;
  paintRect: TerrainRect;
}>;

export type TerrainBoundaryKind = "surface" | "side-left" | "side-right";

export type TerrainBoundaryStrip = Readonly<{
  kind: TerrainBoundaryKind;
  startColumn: number;
  endColumn: number;
  ownerHeight: number;
  thickness: number;
  material:
    | "approved-cap-derived-boundary-strip"
    | "approved-left-side-derived-boundary-strip"
    | "approved-right-side-derived-boundary-strip";
  paintRect: TerrainRect;
}>;

export type TerrainIntegrationPatch = Readonly<{
  kind: TerrainBoundaryKind;
  startColumn: number;
  endColumn: number;
  ownerHeight: number;
  depth: number;
  material: "approved-fill-derived-irregular-boundary-integration";
  paintRect: TerrainRect;
}>;

export type TerrainRenderPlan = Readonly<{
  mode: "continuous-material-with-boundary-integration-v2";
  fillRuns: readonly TerrainFillRun[];
  integrationPatches: readonly TerrainIntegrationPatch[];
  boundaryStrips: readonly TerrainBoundaryStrip[];
}>;

export type TerrainColumnRange = Readonly<{
  start: number;
  end: number;
}>;

export type TerrainMaterialOrigin = Readonly<{
  x: number;
  y: number;
}>;

export const TERRAIN_SUPPORTED_SCALE = Object.freeze({
  minZoom: 1,
  maxZoom: 2,
  minDevicePixelRatio: 1,
  maxDevicePixelRatio: 4,
});

function positiveSafeInteger(value: number, label: string): void {
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new Error(`${label} must be a positive safe integer`);
  }
}

export function createTerrainContract(
  input: Omit<TerrainContract, "overlapPixels" | "cullOverscanColumns"> &
    Partial<Pick<TerrainContract, "overlapPixels" | "cullOverscanColumns">>,
): TerrainContract {
  positiveSafeInteger(input.columns, "terrain columns");
  positiveSafeInteger(input.tilePixels, "terrain tile pixels");
  positiveSafeInteger(input.viewportWidth, "terrain viewport width");
  positiveSafeInteger(input.viewportHeight, "terrain viewport height");
  if (!Number.isSafeInteger(input.baselineY) || input.baselineY <= 0) {
    throw new Error("terrain baseline must be a positive safe integer");
  }
  if (input.baselineY !== input.viewportHeight) {
    throw new Error("terrain baseline must equal the viewport bottom");
  }
  const overlapPixels = input.overlapPixels ?? TERRAIN_WORLD_OVERLAP_PIXELS;
  const cullOverscanColumns = input.cullOverscanColumns ?? 2;
  if (
    !Number.isSafeInteger(overlapPixels) ||
    overlapPixels < 1 ||
    overlapPixels * 2 >= input.tilePixels
  ) {
    throw new Error(
      "terrain overlap must be a positive integer smaller than half a tile",
    );
  }
  if (!Number.isSafeInteger(cullOverscanColumns) || cullOverscanColumns < 1) {
    throw new Error("terrain cull overscan must be a positive safe integer");
  }
  return Object.freeze({
    columns: input.columns,
    tilePixels: input.tilePixels,
    baselineY: input.baselineY,
    viewportWidth: input.viewportWidth,
    viewportHeight: input.viewportHeight,
    overlapPixels,
    cullOverscanColumns,
  });
}

export function terrainWorldWidth(contract: TerrainContract): number {
  return contract.columns * contract.tilePixels;
}

export function terrainSurfaceY(
  height: number,
  tilePixels: number,
  baselineY: number,
): number {
  if (!Number.isSafeInteger(height) || height < 0) {
    throw new Error("terrain height must be a nonnegative safe integer");
  }
  positiveSafeInteger(tilePixels, "terrain tile pixels");
  if (!Number.isSafeInteger(baselineY)) {
    throw new Error("terrain baseline must be a safe integer");
  }
  return baselineY - height * tilePixels;
}

export function terrainColumnAt(worldX: number, tilePixels: number): number {
  if (!Number.isFinite(worldX))
    throw new Error("terrain world x must be finite");
  positiveSafeInteger(tilePixels, "terrain tile pixels");
  return Math.floor(worldX / tilePixels);
}

export function terrainHeightAtColumn(
  heights: readonly number[],
  column: number,
): number {
  if (heights.length === 0)
    throw new Error("terrain heightmap must not be empty");
  if (!Number.isSafeInteger(column)) {
    throw new Error("terrain column must be a safe integer");
  }
  const clamped = Math.max(0, Math.min(heights.length - 1, column));
  const height = heights[clamped];
  if (!Number.isSafeInteger(height) || height < 1) {
    throw new Error("terrain heightmap values must be positive safe integers");
  }
  return height;
}

export function terrainSurfaceYAtColumn(
  heights: readonly number[],
  column: number,
  contract: Pick<TerrainContract, "tilePixels" | "baselineY">,
): number {
  return terrainSurfaceY(
    terrainHeightAtColumn(heights, column),
    contract.tilePixels,
    contract.baselineY,
  );
}

function assertHeightmap(
  heights: readonly number[],
  contract: TerrainContract,
): void {
  if (heights.length !== contract.columns) {
    throw new Error("terrain heightmap length must match the terrain contract");
  }
  for (let column = 0; column < heights.length; column += 1) {
    const height = heights[column];
    if (!Number.isSafeInteger(height) || height < 1) {
      throw new Error(
        "terrain heightmap values must be positive safe integers",
      );
    }
    if (column > 0 && Math.abs(height - heights[column - 1]) > 1) {
      throw new Error(
        "terrain heightmap adjacency may change by at most one tile",
      );
    }
    if (terrainSurfaceY(height, contract.tilePixels, contract.baselineY) < 0) {
      throw new Error(
        "terrain heightmap rises above the supported world bounds",
      );
    }
  }
}

function neighboringHeight(heights: readonly number[], column: number): number {
  return column < 0 || column >= heights.length ? 0 : heights[column];
}

/** Select one non-overlapping atlas role from local heightfield adjacency. */
export function selectTerrainRole(
  heights: readonly number[],
  column: number,
  depth: number,
): TileRole {
  const height = terrainHeightAtColumn(heights, column);
  if (!Number.isSafeInteger(depth) || depth < 0 || depth >= height) {
    throw new Error("terrain depth must address a solid cell");
  }
  const level = height - depth;
  const left = neighboringHeight(heights, column - 1);
  const right = neighboringHeight(heights, column + 1);
  const leftSolid = left >= level;
  const rightSolid = right >= level;
  if (depth > 0) {
    if (!leftSolid) return "side_left";
    if (!rightSolid) return "side_right";
    return "fill";
  }

  const leftDelta = Math.sign(left - height);
  const rightDelta = Math.sign(right - height);
  if (leftDelta < 0 && rightDelta > 0) return "slope_up";
  if (leftDelta > 0 && rightDelta < 0) return "slope_down";
  if (leftDelta > 0 && rightDelta === 0) return "inner_tl";
  if (leftDelta === 0 && rightDelta > 0) return "inner_tr";
  if (leftDelta < 0 && rightDelta < 0) return "top_single";
  if (leftDelta < 0) return "top_left";
  if (rightDelta < 0) return "top_right";
  return "top_mid";
}

export function terrainVariant(
  role: TileRole,
  column: number,
  depth: number,
): number {
  if (
    !Number.isSafeInteger(column) ||
    column < 0 ||
    !Number.isSafeInteger(depth) ||
    depth < 0
  ) {
    throw new Error(
      "terrain variant coordinates must be nonnegative safe integers",
    );
  }
  const roleIndex = TILE_ROLES.indexOf(role);
  if (roleIndex < 0) throw new Error("unknown terrain role");
  const mixed =
    Math.imul(column + 1, 1_103_515_245) ^
    Math.imul(depth + 1, 12_345) ^
    Math.imul(roleIndex + 1, 2_654_435_761);
  return (mixed >>> 0) % TILESET_VARIANTS;
}

function rect(
  x: number,
  y: number,
  width: number,
  height: number,
): TerrainRect {
  return Object.freeze({ x, y, width, height });
}

export function buildTerrainPlan(
  heights: readonly number[],
  contract: TerrainContract,
): TerrainPlan {
  assertHeightmap(heights, contract);
  const cells: TerrainCellPlan[] = [];
  for (let column = 0; column < heights.length; column += 1) {
    const height = heights[column];
    const leftHeight = neighboringHeight(heights, column - 1);
    const rightHeight = neighboringHeight(heights, column + 1);
    for (let depth = 0; depth < height; depth += 1) {
      const level = height - depth;
      const leftSolid = leftHeight >= level;
      const rightSolid = rightHeight >= level;
      const aboveSolid = depth > 0;
      const belowSolid = depth + 1 < height;
      const role = selectTerrainRole(heights, column, depth);
      const variant = terrainVariant(role, column, depth);
      const x = column * contract.tilePixels;
      const y = terrainSurfaceY(level, contract.tilePixels, contract.baselineY);
      const nominalRect = rect(x, y, contract.tilePixels, contract.tilePixels);
      const paintRect = rect(
        x - (leftSolid ? contract.overlapPixels : 0),
        y,
        contract.tilePixels +
          (leftSolid ? contract.overlapPixels : 0) +
          (rightSolid ? contract.overlapPixels : 0),
        contract.tilePixels + (belowSolid ? contract.overlapPixels : 0),
      );
      cells.push(
        Object.freeze({
          column,
          depth,
          level,
          surface: depth === 0,
          role,
          variant,
          fillMaterial: "approved-fill-derived-continuous" as const,
          adjacency: Object.freeze({
            leftSolid,
            rightSolid,
            aboveSolid,
            belowSolid,
          }),
          nominalRect,
          paintRect,
        }),
      );
    }
  }
  const plan = Object.freeze({
    contract,
    heights: Object.freeze([...heights]),
    cells: Object.freeze(cells),
  });
  assertTerrainPlanCoverage(plan);
  return plan;
}

/** Merge every horizontally connected solid level into one material body. */
export function terrainFillRuns(plan: TerrainPlan): readonly TerrainFillRun[] {
  const runs: TerrainFillRun[] = [];
  const maxHeight = Math.max(...plan.heights);
  for (let level = 1; level <= maxHeight; level += 1) {
    let start = -1;
    for (let column = 0; column <= plan.heights.length; column += 1) {
      const solid =
        column < plan.heights.length && plan.heights[column] >= level;
      if (solid && start < 0) start = column;
      if (solid || start < 0) continue;
      const end = column - 1;
      runs.push(
        Object.freeze({
          startColumn: start,
          endColumn: end,
          level,
          paintRect: rect(
            start * plan.contract.tilePixels,
            terrainSurfaceY(
              level,
              plan.contract.tilePixels,
              plan.contract.baselineY,
            ),
            (end - start + 1) * plan.contract.tilePixels,
            plan.contract.tilePixels +
              (level > 1 ? plan.contract.overlapPixels : 0),
          ),
        }),
      );
      start = -1;
    }
  }
  return Object.freeze(runs);
}

/** Merge equal-height columns so flat surface paint has no tile cadence. */
export function terrainSurfaceRuns(
  plan: TerrainPlan,
  bandHeight: number,
): readonly TerrainSurfaceRun[] {
  positiveSafeInteger(bandHeight, "terrain surface band height");
  if (bandHeight >= plan.contract.tilePixels) {
    throw new Error("terrain surface band must be shorter than one tile");
  }
  const runs: TerrainSurfaceRun[] = [];
  let start = 0;
  for (let column = 1; column <= plan.heights.length; column += 1) {
    if (
      column < plan.heights.length &&
      plan.heights[column] === plan.heights[start]
    ) {
      continue;
    }
    const end = column - 1;
    const height = plan.heights[start];
    runs.push(
      Object.freeze({
        startColumn: start,
        endColumn: end,
        height,
        paintRect: rect(
          start * plan.contract.tilePixels,
          terrainSurfaceY(
            height,
            plan.contract.tilePixels,
            plan.contract.baselineY,
          ),
          (end - start + 1) * plan.contract.tilePixels,
          bandHeight,
        ),
      }),
    );
    start = column;
  }
  return Object.freeze(runs);
}

function assertNarrowBoundaryThickness(
  thickness: number,
  tilePixels: number,
): void {
  positiveSafeInteger(thickness, "terrain boundary thickness");
  if (thickness * 2 >= tilePixels) {
    throw new Error("terrain boundary strip must be narrower than half a tile");
  }
}

/**
 * Trace the collision contour as narrow top and vertical strips. Corners and
 * stepped slopes are intersections of these strips; no full atlas cell is a
 * render primitive and no decoration can extend beyond `thickness` into soil.
 */
export function terrainBoundaryStrips(
  plan: TerrainPlan,
  thickness: number,
): readonly TerrainBoundaryStrip[] {
  assertNarrowBoundaryThickness(thickness, plan.contract.tilePixels);
  const strips: TerrainBoundaryStrip[] = terrainSurfaceRuns(
    plan,
    thickness,
  ).map((run) =>
    Object.freeze({
      kind: "surface" as const,
      startColumn: run.startColumn,
      endColumn: run.endColumn,
      ownerHeight: run.height,
      thickness,
      material: "approved-cap-derived-boundary-strip" as const,
      paintRect: run.paintRect,
    }),
  );

  for (let boundary = 0; boundary <= plan.heights.length; boundary += 1) {
    const leftHeight = boundary === 0 ? 0 : plan.heights[boundary - 1];
    const rightHeight =
      boundary === plan.heights.length ? 0 : plan.heights[boundary];
    if (leftHeight === rightHeight) continue;
    const ownerHeight = Math.max(leftHeight, rightHeight);
    const exposedHeight = ownerHeight - Math.min(leftHeight, rightHeight);
    const kind = leftHeight < rightHeight ? "side-left" : "side-right";
    const ownerColumn = kind === "side-left" ? boundary : boundary - 1;
    const boundaryX = boundary * plan.contract.tilePixels;
    strips.push(
      Object.freeze({
        kind,
        startColumn: ownerColumn,
        endColumn: ownerColumn,
        ownerHeight,
        thickness,
        material:
          kind === "side-left"
            ? "approved-left-side-derived-boundary-strip"
            : "approved-right-side-derived-boundary-strip",
        paintRect: rect(
          kind === "side-left" ? boundaryX : boundaryX - thickness,
          terrainSurfaceY(
            ownerHeight,
            plan.contract.tilePixels,
            plan.contract.baselineY,
          ),
          thickness,
          exposedHeight * plan.contract.tilePixels,
        ),
      }),
    );
  }

  const frozen = Object.freeze(strips);
  assertTerrainBoundaryStrips(plan, frozen, thickness);
  return frozen;
}

export function buildTerrainRenderPlan(
  plan: TerrainPlan,
  boundaryThickness: number,
): TerrainRenderPlan {
  const boundaryStrips = terrainBoundaryStrips(plan, boundaryThickness);
  const integrationPatches = terrainIntegrationPatches(
    plan,
    boundaryStrips,
    boundaryThickness,
  );
  return Object.freeze({
    mode: "continuous-material-with-boundary-integration-v2" as const,
    fillRuns: terrainFillRuns(plan),
    integrationPatches,
    boundaryStrips,
  });
}

/**
 * Extend each narrow approved contour inward with a source-palette transition.
 * These rectangles are never coverage primitives: their generated texture
 * becomes fully transparent at an irregular world-space depth over the
 * continuous opaque fill.
 */
export function terrainIntegrationPatches(
  plan: TerrainPlan,
  strips: readonly TerrainBoundaryStrip[],
  boundaryThickness: number,
): readonly TerrainIntegrationPatch[] {
  assertTerrainBoundaryStrips(plan, strips, boundaryThickness);
  const depth = Math.min(
    plan.contract.tilePixels - boundaryThickness,
    boundaryThickness * 3,
  );
  positiveSafeInteger(depth, "terrain integration depth");
  const patches = strips.flatMap((strip): TerrainIntegrationPatch[] => {
    const { paintRect } = strip;
    if (strip.kind === "surface") {
      const available =
        plan.contract.baselineY - (paintRect.y + boundaryThickness);
      const patchDepth = Math.min(depth, available);
      if (patchDepth <= 0) return [];
      return [
        Object.freeze({
          kind: strip.kind,
          startColumn: strip.startColumn,
          endColumn: strip.endColumn,
          ownerHeight: strip.ownerHeight,
          depth: patchDepth,
          material:
            "approved-fill-derived-irregular-boundary-integration" as const,
          paintRect: rect(
            paintRect.x,
            paintRect.y + boundaryThickness,
            paintRect.width,
            patchDepth,
          ),
        }),
      ];
    }
    const availableHeight = paintRect.height - boundaryThickness;
    if (availableHeight <= 0) return [];
    return [
      Object.freeze({
        kind: strip.kind,
        startColumn: strip.startColumn,
        endColumn: strip.endColumn,
        ownerHeight: strip.ownerHeight,
        depth,
        material:
          "approved-fill-derived-irregular-boundary-integration" as const,
        paintRect: rect(
          strip.kind === "side-left"
            ? paintRect.x + boundaryThickness
            : paintRect.x - depth,
          paintRect.y + boundaryThickness,
          depth,
          availableHeight,
        ),
      }),
    ];
  });
  const frozen = Object.freeze(patches);
  assertTerrainIntegrationPatches(plan, strips, frozen, boundaryThickness);
  return frozen;
}

function right(rectangle: TerrainRect): number {
  return rectangle.x + rectangle.width;
}

function bottom(rectangle: TerrainRect): number {
  return rectangle.y + rectangle.height;
}

/**
 * Validate the world-space coverage theorem used by every supported positive
 * zoom/DPR transform: every ideal solid cell is contained by an opaque fill
 * rectangle, internal seams overlap, and paint never crosses above collision.
 */
export function assertTerrainPlanCoverage(plan: TerrainPlan): void {
  const byCell = new Map<string, TerrainCellPlan>();
  for (const cell of plan.cells) {
    const key = `${cell.column}:${cell.level}`;
    if (byCell.has(key))
      throw new Error("terrain plan contains a duplicate solid cell");
    byCell.set(key, cell);
    if (
      cell.paintRect.x > cell.nominalRect.x ||
      cell.paintRect.y !== cell.nominalRect.y ||
      right(cell.paintRect) < right(cell.nominalRect) ||
      bottom(cell.paintRect) < bottom(cell.nominalRect)
    ) {
      throw new Error(
        "terrain paint must contain its collision-aligned solid cell",
      );
    }
    if (cell.surface) {
      const expected = terrainSurfaceYAtColumn(
        plan.heights,
        cell.column,
        plan.contract,
      );
      if (cell.nominalRect.y !== expected) {
        throw new Error("terrain surface paint and collision height diverged");
      }
    }
    const rightNeighbor = byCell.get(`${cell.column - 1}:${cell.level}`);
    if (
      rightNeighbor &&
      right(rightNeighbor.paintRect) - cell.paintRect.x <
        plan.contract.overlapPixels
    ) {
      throw new Error("terrain horizontal paint seam does not overlap");
    }
    const aboveNeighbor = byCell.get(`${cell.column}:${cell.level + 1}`);
    if (
      aboveNeighbor &&
      bottom(aboveNeighbor.paintRect) - cell.paintRect.y <
        plan.contract.overlapPixels
    ) {
      throw new Error("terrain vertical paint seam does not overlap");
    }
  }
  const expectedCells = plan.heights.reduce((sum, height) => sum + height, 0);
  if (plan.cells.length !== expectedCells || byCell.size !== expectedCells) {
    throw new Error(
      "terrain plan does not cover every heightmap cell exactly once",
    );
  }
}

export function assertTerrainBoundaryStrips(
  plan: TerrainPlan,
  strips: readonly TerrainBoundaryStrip[],
  thickness: number,
): void {
  assertNarrowBoundaryThickness(thickness, plan.contract.tilePixels);
  const expectedSurfaceRuns = terrainSurfaceRuns(plan, thickness);
  const surfaceStrips = strips.filter((strip) => strip.kind === "surface");
  if (surfaceStrips.length !== expectedSurfaceRuns.length) {
    throw new Error("terrain surface strips must match equal-height runs");
  }
  let expectedSides = 0;
  for (let boundary = 0; boundary <= plan.heights.length; boundary += 1) {
    const leftHeight = boundary === 0 ? 0 : plan.heights[boundary - 1];
    const rightHeight =
      boundary === plan.heights.length ? 0 : plan.heights[boundary];
    if (leftHeight !== rightHeight) expectedSides += 1;
  }
  if (strips.length !== surfaceStrips.length + expectedSides) {
    throw new Error(
      "terrain side strips must match every exposed vertical edge",
    );
  }

  const seen = new Set<string>();
  for (const strip of strips) {
    const identity = `${strip.kind}:${strip.startColumn}:${strip.endColumn}`;
    if (seen.has(identity)) {
      throw new Error("terrain boundary strips must be unique");
    }
    seen.add(identity);
    if (
      strip.thickness !== thickness ||
      strip.startColumn < 0 ||
      strip.endColumn < strip.startColumn ||
      strip.endColumn >= plan.contract.columns ||
      !Number.isSafeInteger(strip.paintRect.x) ||
      !Number.isSafeInteger(strip.paintRect.y) ||
      !Number.isSafeInteger(strip.paintRect.width) ||
      !Number.isSafeInteger(strip.paintRect.height) ||
      strip.paintRect.width <= 0 ||
      strip.paintRect.height <= 0
    ) {
      throw new Error("terrain boundary strip geometry is invalid");
    }
    if (
      strip.paintRect.width === plan.contract.tilePixels &&
      strip.paintRect.height === plan.contract.tilePixels
    ) {
      throw new Error(
        "terrain boundary decoration must not be a full-cell frame",
      );
    }
    if (strip.kind === "surface") {
      const expectedRun = expectedSurfaceRuns.find(
        (run) =>
          run.startColumn === strip.startColumn &&
          run.endColumn === strip.endColumn,
      );
      if (
        expectedRun === undefined ||
        expectedRun.height !== strip.ownerHeight ||
        strip.material !== "approved-cap-derived-boundary-strip" ||
        strip.paintRect.height !== thickness ||
        strip.paintRect.x !== strip.startColumn * plan.contract.tilePixels ||
        strip.paintRect.width !==
          (strip.endColumn - strip.startColumn + 1) *
            plan.contract.tilePixels ||
        strip.paintRect.y !==
          terrainSurfaceY(
            strip.ownerHeight,
            plan.contract.tilePixels,
            plan.contract.baselineY,
          )
      ) {
        throw new Error("terrain surface decoration escaped its contour band");
      }
    } else {
      const ownerColumn = strip.startColumn;
      const neighborColumn =
        strip.kind === "side-left" ? ownerColumn - 1 : ownerColumn + 1;
      const neighborHeight =
        neighborColumn < 0 || neighborColumn >= plan.heights.length
          ? 0
          : plan.heights[neighborColumn];
      const expectedX =
        strip.kind === "side-left"
          ? ownerColumn * plan.contract.tilePixels
          : (ownerColumn + 1) * plan.contract.tilePixels - thickness;
      const expectedMaterial =
        strip.kind === "side-left"
          ? "approved-left-side-derived-boundary-strip"
          : "approved-right-side-derived-boundary-strip";
      if (
        strip.startColumn !== strip.endColumn ||
        strip.ownerHeight !== plan.heights[ownerColumn] ||
        strip.ownerHeight <= neighborHeight ||
        strip.material !== expectedMaterial ||
        strip.paintRect.x !== expectedX ||
        strip.paintRect.y !==
          terrainSurfaceY(
            strip.ownerHeight,
            plan.contract.tilePixels,
            plan.contract.baselineY,
          ) ||
        strip.paintRect.width !== thickness ||
        strip.paintRect.height !==
          (strip.ownerHeight - neighborHeight) * plan.contract.tilePixels
      ) {
        throw new Error(
          "terrain side decoration escaped its air-facing contour",
        );
      }
    }
  }
}

export function assertTerrainIntegrationPatches(
  plan: TerrainPlan,
  strips: readonly TerrainBoundaryStrip[],
  patches: readonly TerrainIntegrationPatch[],
  boundaryThickness: number,
): void {
  const expectedCount = strips.filter(
    (strip) =>
      strip.kind === "surface" || strip.paintRect.height > boundaryThickness,
  ).length;
  if (patches.length !== expectedCount) {
    throw new Error("terrain integration must match every eligible contour");
  }
  const solidAt = (x: number, y: number): boolean => {
    if (x < 0 || x >= plan.contract.columns * plan.contract.tilePixels) {
      return false;
    }
    const column = Math.floor(x / plan.contract.tilePixels);
    return y >= terrainSurfaceYAtColumn(plan.heights, column, plan.contract);
  };
  for (const patch of patches) {
    const owner = strips.find(
      (strip) =>
        strip.kind === patch.kind &&
        strip.startColumn === patch.startColumn &&
        strip.endColumn === patch.endColumn,
    );
    if (
      owner === undefined ||
      patch.material !==
        "approved-fill-derived-irregular-boundary-integration" ||
      patch.depth <= 0 ||
      patch.depth > boundaryThickness * 3 ||
      patch.paintRect.width <= 0 ||
      patch.paintRect.height <= 0 ||
      (patch.paintRect.width === plan.contract.tilePixels &&
        patch.paintRect.height === plan.contract.tilePixels)
    ) {
      throw new Error("terrain boundary integration geometry is invalid");
    }
    const sampleXs = [
      patch.paintRect.x,
      patch.paintRect.x + patch.paintRect.width - 1,
    ];
    const sampleYs = [
      patch.paintRect.y,
      patch.paintRect.y + patch.paintRect.height - 1,
    ];
    for (const x of sampleXs) {
      for (const y of sampleYs) {
        if (!solidAt(x, y)) {
          throw new Error("terrain boundary integration escaped solid terrain");
        }
      }
    }
    if (patch.kind === "surface") {
      if (
        patch.paintRect.x !== owner.paintRect.x ||
        patch.paintRect.width !== owner.paintRect.width ||
        patch.paintRect.y !== owner.paintRect.y + boundaryThickness ||
        patch.paintRect.height !== patch.depth
      ) {
        throw new Error("terrain surface integration is not contour-adjacent");
      }
    } else if (
      patch.paintRect.y !== owner.paintRect.y + boundaryThickness ||
      patch.paintRect.height !== owner.paintRect.height - boundaryThickness ||
      patch.paintRect.width !== patch.depth ||
      (patch.kind === "side-left" &&
        patch.paintRect.x !== owner.paintRect.x + boundaryThickness) ||
      (patch.kind === "side-right" &&
        patch.paintRect.x + patch.paintRect.width !== owner.paintRect.x)
    ) {
      throw new Error("terrain side integration is not contour-adjacent");
    }
  }
}

/**
 * Phaser TileSprite samples local pixels after adding tilePosition. Anchoring
 * that offset to the paint rectangle makes every overlapping cell sample the
 * same approved-fill-derived texel at a given world coordinate.
 */
export function terrainMaterialOrigin(
  cell: Pick<TerrainCellPlan, "paintRect">,
): TerrainMaterialOrigin {
  return Object.freeze({ x: cell.paintRect.x, y: cell.paintRect.y });
}

export function visibleTerrainColumnRange(
  worldLeft: number,
  worldRight: number,
  contract: TerrainContract,
): TerrainColumnRange | null {
  if (!Number.isFinite(worldLeft) || !Number.isFinite(worldRight)) {
    throw new Error("terrain camera bounds must be finite");
  }
  if (worldRight <= worldLeft) {
    throw new Error("terrain camera right bound must exceed its left bound");
  }
  const worldWidth = terrainWorldWidth(contract);
  if (worldRight <= 0 || worldLeft >= worldWidth) return null;
  const start = Math.max(
    0,
    Math.floor(worldLeft / contract.tilePixels) - contract.cullOverscanColumns,
  );
  const end = Math.min(
    contract.columns - 1,
    Math.ceil(worldRight / contract.tilePixels) -
      1 +
      contract.cullOverscanColumns,
  );
  return Object.freeze({ start, end });
}

export function assertSupportedTerrainScale(
  zoom: number,
  devicePixelRatio: number,
): void {
  if (
    !Number.isFinite(zoom) ||
    zoom < TERRAIN_SUPPORTED_SCALE.minZoom ||
    zoom > TERRAIN_SUPPORTED_SCALE.maxZoom
  ) {
    throw new Error("terrain camera zoom is outside the supported range");
  }
  if (
    !Number.isFinite(devicePixelRatio) ||
    devicePixelRatio < TERRAIN_SUPPORTED_SCALE.minDevicePixelRatio ||
    devicePixelRatio > TERRAIN_SUPPORTED_SCALE.maxDevicePixelRatio
  ) {
    throw new Error(
      "terrain device pixel ratio is outside the supported range",
    );
  }
}

export function terrainScreenRect(
  worldRect: TerrainRect,
  cameraLeft: number,
  cameraTop: number,
  zoom: number,
  devicePixelRatio: number,
): TerrainRect {
  assertSupportedTerrainScale(zoom, devicePixelRatio);
  if (!Number.isFinite(cameraLeft) || !Number.isFinite(cameraTop)) {
    throw new Error("terrain camera origin must be finite");
  }
  const scale = zoom * devicePixelRatio;
  return rect(
    (worldRect.x - cameraLeft) * scale,
    (worldRect.y - cameraTop) * scale,
    worldRect.width * scale,
    worldRect.height * scale,
  );
}
