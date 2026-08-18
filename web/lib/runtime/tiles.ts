// Typed consumer contract for the scrolling preview's 12x4 terrain atlas.
//
// The source atlas intentionally retains transparent gutters so generated
// cells cannot contaminate one another. Runtime code must therefore prepare a
// derived, edge-extruded texture before scaling cells into world tiles. The
// source bytes remain immutable and continue to satisfy the media contract.

import type { SlopeKind } from "./heightmap";

export type TileRole =
  | "top_left"
  | "top_mid"
  | "top_right"
  | "top_single"
  | "slope_up"
  | "slope_down"
  | "inner_tl"
  | "inner_tr"
  | "side_left"
  | "side_right"
  | "bot_left"
  | "bot_right"
  | "fill"
  | "plat_left"
  | "plat_mid"
  | "plat_right";

export type TileRoleFamily =
  | "surface"
  | "slope"
  | "inner-corner"
  | "side"
  | "bottom"
  | "interior"
  | "platform";

export type TileEdgeCompatibility = "air" | "solid" | "surface" | "any";

export type TileRoleContract = Readonly<{
  role: TileRole;
  family: TileRoleFamily;
  canonicalCell: Readonly<{ row: number; column: number }>;
  adjacency: Readonly<{
    top: TileEdgeCompatibility;
    right: TileEdgeCompatibility;
    bottom: TileEdgeCompatibility;
    left: TileEdgeCompatibility;
  }>;
}>;

export type AtlasRect = Readonly<{
  x: number;
  y: number;
  w: number;
  h: number;
}>;

export type TilesetGeometry = Readonly<{
  sheetWidth: number;
  sheetHeight: number;
  cellWidth: number;
  cellHeight: number;
  gutterPixels: number;
  contentWidth: number;
  contentHeight: number;
}>;

export type AtlasExtrusionBlit = Readonly<{
  row: number;
  column: number;
  source: AtlasRect;
  target: AtlasRect;
}>;

export type TerrainMaterialProfile = Readonly<{
  meanRed: number;
  meanGreen: number;
  meanBlue: number;
  spreadRed: number;
  spreadGreen: number;
  spreadBlue: number;
  palette: readonly TerrainMaterialColor[];
  seed: number;
  derivation: "approved-fill-palette-periodic-strata-v2";
}>;

export type TerrainMaterialColor = Readonly<{
  red: number;
  green: number;
  blue: number;
}>;

export type TerrainMaterialPixel = Readonly<{
  red: number;
  green: number;
  blue: number;
  alpha: number;
}>;

export type TerrainIntegrationAxis = "surface" | "side-left" | "side-right";

export const TILESET_ROWS = 4;
export const TILESET_COLS = 12;
export const TILESET_VARIANTS = 3;
export const TILESET_ROLES_PER_VARIANT = 4;
export const TILESET_CELL_GUTTER_PIXELS = 2;
export const TERRAIN_WORLD_OVERLAP_PIXELS = 1;
export const TERRAIN_MATERIAL_TEXTURE_PIXELS = 512;
export const TERRAIN_SURFACE_BAND_TEXTURE_HEIGHT = 12;
export const TERRAIN_SIDE_BAND_TEXTURE_WIDTH = 12;
export const TERRAIN_INTEGRATION_TEXTURE_DEPTH = 36;

const role = (
  name: TileRole,
  family: TileRoleFamily,
  row: number,
  column: number,
  top: TileEdgeCompatibility,
  right: TileEdgeCompatibility,
  bottom: TileEdgeCompatibility,
  left: TileEdgeCompatibility,
): TileRoleContract =>
  Object.freeze({
    role: name,
    family,
    canonicalCell: Object.freeze({ row, column }),
    adjacency: Object.freeze({ top, right, bottom, left }),
  });

/**
 * Atlas semantics independent from any one generated image.
 *
 * The planner consumes only bottom-contiguous terrain, so bottom/platform
 * roles are catalogued here but reserved for future floating geometry.
 */
export const TILE_ROLE_CONTRACTS = Object.freeze({
  top_left: role("top_left", "surface", 0, 0, "air", "surface", "solid", "air"),
  top_mid: role(
    "top_mid",
    "surface",
    0,
    1,
    "air",
    "surface",
    "solid",
    "surface",
  ),
  top_right: role(
    "top_right",
    "surface",
    0,
    2,
    "air",
    "air",
    "solid",
    "surface",
  ),
  top_single: role("top_single", "surface", 0, 3, "air", "air", "solid", "air"),
  slope_up: role(
    "slope_up",
    "slope",
    1,
    0,
    "air",
    "surface",
    "solid",
    "surface",
  ),
  slope_down: role(
    "slope_down",
    "slope",
    1,
    1,
    "air",
    "surface",
    "solid",
    "surface",
  ),
  inner_tl: role(
    "inner_tl",
    "inner-corner",
    1,
    2,
    "air",
    "surface",
    "solid",
    "solid",
  ),
  inner_tr: role(
    "inner_tr",
    "inner-corner",
    1,
    3,
    "air",
    "solid",
    "solid",
    "surface",
  ),
  side_left: role("side_left", "side", 2, 0, "solid", "solid", "solid", "air"),
  side_right: role(
    "side_right",
    "side",
    2,
    1,
    "solid",
    "air",
    "solid",
    "solid",
  ),
  bot_left: role("bot_left", "bottom", 2, 2, "solid", "solid", "air", "air"),
  bot_right: role("bot_right", "bottom", 2, 3, "solid", "air", "air", "solid"),
  fill: role("fill", "interior", 3, 0, "solid", "solid", "solid", "solid"),
  plat_left: role(
    "plat_left",
    "platform",
    3,
    1,
    "air",
    "surface",
    "air",
    "air",
  ),
  plat_mid: role(
    "plat_mid",
    "platform",
    3,
    2,
    "air",
    "surface",
    "air",
    "surface",
  ),
  plat_right: role(
    "plat_right",
    "platform",
    3,
    3,
    "air",
    "air",
    "air",
    "surface",
  ),
} satisfies Readonly<Record<TileRole, TileRoleContract>>);

export const TILE_ROLES = Object.freeze(
  Object.keys(TILE_ROLE_CONTRACTS) as TileRole[],
);

function positiveSafeInteger(value: number, label: string): void {
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new Error(`${label} must be a positive safe integer`);
  }
}

export function tilesetGeometry(
  sheetWidth: number,
  sheetHeight: number,
  gutterPixels = TILESET_CELL_GUTTER_PIXELS,
): TilesetGeometry {
  positiveSafeInteger(sheetWidth, "tileset width");
  positiveSafeInteger(sheetHeight, "tileset height");
  if (sheetWidth % TILESET_COLS !== 0 || sheetHeight % TILESET_ROWS !== 0) {
    throw new Error(
      "tileset dimensions must be exactly divisible by its 12x4 grid",
    );
  }
  if (!Number.isSafeInteger(gutterPixels) || gutterPixels < 0) {
    throw new Error("tileset gutter must be a nonnegative safe integer");
  }
  const cellWidth = sheetWidth / TILESET_COLS;
  const cellHeight = sheetHeight / TILESET_ROWS;
  const contentWidth = cellWidth - gutterPixels * 2;
  const contentHeight = cellHeight - gutterPixels * 2;
  if (contentWidth < 1 || contentHeight < 1) {
    throw new Error("tileset gutter leaves no cell content");
  }
  return Object.freeze({
    sheetWidth,
    sheetHeight,
    cellWidth,
    cellHeight,
    gutterPixels,
    contentWidth,
    contentHeight,
  });
}

function variantColumn(roleName: TileRole, variant: number): number {
  if (
    !Number.isSafeInteger(variant) ||
    variant < 0 ||
    variant >= TILESET_VARIANTS
  ) {
    throw new Error(
      `tileset variant must be between 0 and ${TILESET_VARIANTS - 1}`,
    );
  }
  const base = TILE_ROLE_CONTRACTS[roleName].canonicalCell.column;
  return base + variant * TILESET_ROLES_PER_VARIANT;
}

export function cellRectFor(
  roleName: TileRole,
  sheetWidth: number,
  sheetHeight: number,
  variant = 0,
): AtlasRect {
  const geometry = tilesetGeometry(sheetWidth, sheetHeight);
  const contract = TILE_ROLE_CONTRACTS[roleName];
  const column = variantColumn(roleName, variant);
  return Object.freeze({
    x: column * geometry.cellWidth,
    y: contract.canonicalCell.row * geometry.cellHeight,
    w: geometry.cellWidth,
    h: geometry.cellHeight,
  });
}

export function contentRectFor(
  roleName: TileRole,
  sheetWidth: number,
  sheetHeight: number,
  variant = 0,
): AtlasRect {
  const geometry = tilesetGeometry(sheetWidth, sheetHeight);
  const cell = cellRectFor(roleName, sheetWidth, sheetHeight, variant);
  return Object.freeze({
    x: cell.x + geometry.gutterPixels,
    y: cell.y + geometry.gutterPixels,
    w: geometry.contentWidth,
    h: geometry.contentHeight,
  });
}

/** Derive palette, contrast, and seed from the approved opaque fill cell. */
export function deriveTerrainMaterialProfile(
  rgba: ArrayLike<number>,
): TerrainMaterialProfile {
  if (rgba.length === 0 || rgba.length % 4 !== 0) {
    throw new Error("terrain fill pixels must be nonempty RGBA data");
  }
  let redTotal = 0;
  let greenTotal = 0;
  let blueTotal = 0;
  let redSquaredTotal = 0;
  let greenSquaredTotal = 0;
  let blueSquaredTotal = 0;
  let seed = 0x811c9dc5;
  const colors: TerrainMaterialColor[] = [];
  const pixels = rgba.length / 4;
  for (let offset = 0; offset < rgba.length; offset += 4) {
    const red = rgba[offset];
    const green = rgba[offset + 1];
    const blue = rgba[offset + 2];
    const alpha = rgba[offset + 3];
    if (
      !Number.isInteger(red) ||
      !Number.isInteger(green) ||
      !Number.isInteger(blue) ||
      !Number.isInteger(alpha) ||
      red < 0 ||
      red > 255 ||
      green < 0 ||
      green > 255 ||
      blue < 0 ||
      blue > 255 ||
      alpha !== 255
    ) {
      throw new Error(
        "terrain fill material requires opaque 8-bit RGBA pixels",
      );
    }
    redTotal += red;
    greenTotal += green;
    blueTotal += blue;
    redSquaredTotal += red * red;
    greenSquaredTotal += green * green;
    blueSquaredTotal += blue * blue;
    colors.push(Object.freeze({ red, green, blue }));
    seed = Math.imul(seed ^ red, 0x01000193);
    seed = Math.imul(seed ^ green, 0x01000193);
    seed = Math.imul(seed ^ blue, 0x01000193);
  }
  const meanRed = redTotal / pixels;
  const meanGreen = greenTotal / pixels;
  const meanBlue = blueTotal / pixels;
  const spread = (squaredTotal: number, mean: number) =>
    Math.sqrt(Math.max(0, squaredTotal / pixels - mean * mean));
  colors.sort(
    (left, right) =>
      left.red * 0.2126 +
      left.green * 0.7152 +
      left.blue * 0.0722 -
      (right.red * 0.2126 + right.green * 0.7152 + right.blue * 0.0722),
  );
  const quantiles = [0, 0.08, 0.2, 0.35, 0.5, 0.65, 0.8, 0.92, 1];
  const palette = quantiles.map((quantile) => {
    const index = Math.round(quantile * (colors.length - 1));
    return colors[index];
  });
  return Object.freeze({
    meanRed,
    meanGreen,
    meanBlue,
    spreadRed: spread(redSquaredTotal, meanRed),
    spreadGreen: spread(greenSquaredTotal, meanGreen),
    spreadBlue: spread(blueSquaredTotal, meanBlue),
    palette: Object.freeze(palette),
    seed: seed >>> 0,
    derivation: "approved-fill-palette-periodic-strata-v2" as const,
  });
}

function materialHash(seed: number, channel: number): number {
  let value = seed ^ Math.imul(channel + 1, 0x9e3779b1);
  value ^= value << 13;
  value ^= value >>> 17;
  value ^= value << 5;
  return value >>> 0;
}

function smoothstep(value: number): number {
  return value * value * (3 - 2 * value);
}

function materialHarmonic(
  seed: number,
  u: number,
  v: number,
  cyclesX: number,
  cyclesY: number,
  channel: number,
): number {
  const phase = (materialHash(seed, channel) / 0xffff_ffff) * Math.PI * 2;
  return Math.sin(cyclesX * u + cyclesY * v + phase);
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, value));
}

function terrainPaletteColor(
  palette: readonly TerrainMaterialColor[],
  position: number,
): TerrainMaterialColor {
  if (palette.length < 2) {
    throw new Error(
      "terrain material palette must contain at least two colors",
    );
  }
  const bounded = clamp(position, 0, palette.length - 1);
  const lowerIndex = Math.floor(bounded);
  const upperIndex = Math.min(palette.length - 1, lowerIndex + 1);
  const fraction = bounded - lowerIndex;
  const lower = palette[lowerIndex];
  const upper = palette[upperIndex];
  return Object.freeze({
    red: Math.round(lower.red + (upper.red - lower.red) * fraction),
    green: Math.round(lower.green + (upper.green - lower.green) * fraction),
    blue: Math.round(lower.blue + (upper.blue - lower.blue) * fraction),
  });
}

/**
 * Sample deterministic toroidal soil/rock strata from the approved fill
 * palette. Integer coordinates repeat only at `size`; deliberately
 * incommensurate strata cycles prevent 32/64px atlas or world-cell cadence.
 */
export function terrainMaterialPixel(
  profile: TerrainMaterialProfile,
  x: number,
  y: number,
  size: number,
): TerrainMaterialPixel {
  if (
    !Number.isSafeInteger(size) ||
    size < 8 ||
    !Number.isSafeInteger(x) ||
    !Number.isSafeInteger(y)
  ) {
    throw new Error(
      "terrain material coordinates and size must be safe integers",
    );
  }
  const wrappedX = ((x % size) + size) % size;
  const wrappedY = ((y % size) + size) % size;
  if (size % 256 !== 0) {
    throw new Error("terrain material size must be exactly divisible by 256");
  }
  const u = (wrappedX / (size - 1)) * Math.PI * 2;
  const v = (wrappedY / (size - 1)) * Math.PI * 2;
  const warpU =
    materialHarmonic(profile.seed, u, v, 3, 2, 31) * 0.2 +
    materialHarmonic(profile.seed, u, v, 7, -3, 32) * 0.07;
  const warpV =
    materialHarmonic(profile.seed, u, v, 2, -3, 33) * 0.18 +
    materialHarmonic(profile.seed, u, v, -5, 7, 34) * 0.06;
  const warpedU = u + warpU;
  const warpedV = v + warpV;
  const macro =
    materialHarmonic(profile.seed, warpedU, warpedV, 3, 2, 35) * 0.62 +
    materialHarmonic(profile.seed, warpedU, warpedV, 2, -3, 36) * 0.38;
  const meso =
    materialHarmonic(profile.seed, warpedU, warpedV, 7, -5, 37) * 0.58 +
    materialHarmonic(profile.seed, warpedU, warpedV, 5, 7, 38) * 0.42;
  const grain =
    materialHarmonic(profile.seed, warpedU, warpedV, 19, 13, 39) * 0.55 +
    materialHarmonic(profile.seed, warpedU, warpedV, -13, 19, 40) * 0.45;
  const micro =
    materialHarmonic(profile.seed, warpedU, warpedV, 43, -29, 41) * 0.52 +
    materialHarmonic(profile.seed, warpedU, warpedV, 31, 43, 42) * 0.48;
  const broadStrata = materialHarmonic(
    profile.seed,
    warpedU,
    warpedV,
    2,
    7,
    43,
  );
  const fineStrata = materialHarmonic(
    profile.seed,
    warpedU,
    warpedV,
    -3,
    19,
    44,
  );
  const rockMass = materialHarmonic(profile.seed, warpedU, warpedV, 7, 3, 45);
  const fractureWave = Math.abs(
    materialHarmonic(profile.seed, warpedU, warpedV, 19, -7, 46),
  );
  const fracture = smoothstep(clamp((fractureWave - 0.82) / 0.18, 0, 1));
  const paletteSignal =
    macro * 0.46 +
    meso * 0.34 +
    grain * 0.22 +
    micro * 0.12 +
    broadStrata * 0.38 +
    fineStrata * 0.2 +
    rockMass * 0.18 -
    fracture * 0.62;
  const contrastedSignal = paletteSignal * 1.8;
  const palettePosition =
    ((clamp(contrastedSignal, -1.35, 1.35) + 1.35) / 2.7) *
    (profile.palette.length - 1);
  const color = terrainPaletteColor(profile.palette, palettePosition);
  return Object.freeze({
    red: color.red,
    green: color.green,
    blue: color.blue,
    alpha: 255,
  });
}

/**
 * Source-palette transition painted just inside an air-facing contour.
 *
 * The reach changes continuously in world space at deliberately non-cell
 * frequencies, so a connected body cannot read as a pasted rectangle. The
 * alpha reaches zero before `maxDepth`; the opaque globally-phased fill below
 * it remains the coverage authority.
 */
export function terrainIntegrationPixel(
  profile: TerrainMaterialProfile,
  axis: TerrainIntegrationAxis,
  alongWorld: number,
  depth: number,
  period = TERRAIN_MATERIAL_TEXTURE_PIXELS,
  maxDepth = TERRAIN_INTEGRATION_TEXTURE_DEPTH,
): TerrainMaterialPixel {
  if (
    !Number.isSafeInteger(alongWorld) ||
    !Number.isSafeInteger(depth) ||
    !Number.isSafeInteger(period) ||
    period < 256 ||
    period % 256 !== 0 ||
    !Number.isSafeInteger(maxDepth) ||
    maxDepth < 4 ||
    depth < 0 ||
    depth >= maxDepth
  ) {
    throw new Error("terrain integration coordinates are invalid");
  }
  const wrapped = ((alongWorld % period) + period) % period;
  const phase = (wrapped / (period - 1)) * Math.PI * 2;
  const axisChannel = axis === "surface" ? 71 : axis === "side-left" ? 79 : 83;
  const reachWave =
    Math.sin(
      phase * 3 +
        (materialHash(profile.seed, axisChannel) / 0xffff_ffff) * Math.PI * 2,
    ) *
      0.46 +
    Math.sin(
      phase * 7 +
        (materialHash(profile.seed, axisChannel + 1) / 0xffff_ffff) *
          Math.PI *
          2,
    ) *
      0.27 +
    Math.sin(
      phase * 19 +
        (materialHash(profile.seed, axisChannel + 2) / 0xffff_ffff) *
          Math.PI *
          2,
    ) *
      0.17 +
    Math.sin(
      phase * 43 +
        (materialHash(profile.seed, axisChannel + 3) / 0xffff_ffff) *
          Math.PI *
          2,
    ) *
      0.1;
  const reach = maxDepth * (0.58 + reachWave * 0.24);
  const fadeWidth = Math.max(4, maxDepth * 0.3);
  const coverage = smoothstep(clamp((reach - depth) / fadeWidth, 0, 1));
  const vein =
    materialHarmonic(
      profile.seed,
      phase,
      depth / maxDepth,
      7,
      3,
      axisChannel + 4,
    ) *
      0.58 +
    materialHarmonic(
      profile.seed,
      phase,
      depth / maxDepth,
      19,
      -7,
      axisChannel + 5,
    ) *
      0.42;
  const palettePosition =
    clamp(0.28 + (vein + 1) * 0.24, 0, 1) * (profile.palette.length - 1);
  const color = terrainPaletteColor(profile.palette, palettePosition);
  return Object.freeze({
    red: color.red,
    green: color.green,
    blue: color.blue,
    alpha: Math.round(coverage * (112 + (vein + 1) * 30)),
  });
}

function mirroredSourceCoordinate(value: number, length: number): number {
  if (length === 1) return 0;
  const period = (length - 1) * 2;
  const wrapped = ((value % period) + period) % period;
  return wrapped < length ? wrapped : period - wrapped;
}

function sourceChannel(
  rgba: ArrayLike<number>,
  width: number,
  height: number,
  x: number,
  y: number,
  channel: 0 | 1 | 2 | 3,
): number {
  const sourceX = mirroredSourceCoordinate(x, width);
  const sourceY = mirroredSourceCoordinate(y, height);
  const x0 = Math.floor(sourceX);
  const y0 = Math.floor(sourceY);
  const x1 = Math.ceil(sourceX);
  const y1 = Math.ceil(sourceY);
  const fractionX = sourceX - x0;
  const fractionY = sourceY - y0;
  const at = (sampleX: number, sampleY: number) =>
    rgba[(sampleY * width + sampleX) * 4 + channel] ?? 0;
  const top = at(x0, y0) + (at(x1, y0) - at(x0, y0)) * fractionX;
  const bottom = at(x0, y1) + (at(x1, y1) - at(x0, y1)) * fractionX;
  return top + (bottom - top) * fractionY;
}

/**
 * Extract only the thin approved top-cap paint, then resample it through a
 * periodic source path. Full-cell stems and square bodies are deliberately
 * outside this material, so a flat run cannot stamp them at tile cadence.
 */
export function deriveTerrainSurfaceBand(
  rgba: ArrayLike<number>,
  sourceWidth: number,
  sourceHeight: number,
  targetWidth = TERRAIN_MATERIAL_TEXTURE_PIXELS,
  targetHeight = TERRAIN_SURFACE_BAND_TEXTURE_HEIGHT,
): Uint8ClampedArray {
  positiveSafeInteger(sourceWidth, "terrain surface source width");
  positiveSafeInteger(sourceHeight, "terrain surface source height");
  positiveSafeInteger(targetWidth, "terrain surface target width");
  positiveSafeInteger(targetHeight, "terrain surface target height");
  if (rgba.length !== sourceWidth * sourceHeight * 4) {
    throw new Error("terrain surface dimensions must match its RGBA data");
  }
  let firstOpaqueRow = -1;
  for (let y = 0; y < sourceHeight && firstOpaqueRow < 0; y += 1) {
    for (let x = 0; x < sourceWidth; x += 1) {
      if ((rgba[(y * sourceWidth + x) * 4 + 3] ?? 0) > 0) {
        firstOpaqueRow = y;
        break;
      }
    }
  }
  if (firstOpaqueRow < 0) {
    throw new Error("terrain surface source must contain painted pixels");
  }
  const sourceBandHeight = Math.min(5, sourceHeight - firstOpaqueRow);
  let minPaintedX = sourceWidth;
  let maxPaintedX = -1;
  for (let y = firstOpaqueRow; y < firstOpaqueRow + sourceBandHeight; y += 1) {
    for (let x = 0; x < sourceWidth; x += 1) {
      if ((rgba[(y * sourceWidth + x) * 4 + 3] ?? 0) > 0) {
        minPaintedX = Math.min(minPaintedX, x);
        maxPaintedX = Math.max(maxPaintedX, x);
      }
    }
  }
  if (maxPaintedX < minPaintedX) {
    throw new Error("terrain surface cap band must contain painted pixels");
  }
  const paintedWidth = maxPaintedX - minPaintedX + 1;
  const output = new Uint8ClampedArray(targetWidth * targetHeight * 4);
  for (let y = 0; y < targetHeight; y += 1) {
    const sourceY =
      firstOpaqueRow +
      (targetHeight === 1
        ? 0
        : (y / (targetHeight - 1)) * (sourceBandHeight - 1));
    for (let x = 0; x < targetWidth; x += 1) {
      const phase = (x / targetWidth) * Math.PI * 2;
      const sourceX =
        minPaintedX +
        (paintedWidth - 1) *
          (0.5 + 0.48 * Math.sin(phase + 0.24 * Math.sin(3 * phase)));
      const offset = (y * targetWidth + x) * 4;
      for (const channel of [0, 1, 2, 3] as const) {
        output[offset + channel] = Math.round(
          sourceChannel(
            rgba,
            sourceWidth,
            sourceHeight,
            sourceX,
            sourceY,
            channel,
          ),
        );
      }
    }
  }
  return output;
}

export type TerrainSideEdge = "left" | "right";

/**
 * Extract only a narrow approved cliff edge and resample it vertically along
 * a periodic path. The cell's interior motif is outside the five-column
 * source corridor, so no 64x64 side/corner block can enter the world body.
 */
export function deriveTerrainSideBand(
  rgba: ArrayLike<number>,
  sourceWidth: number,
  sourceHeight: number,
  edge: TerrainSideEdge,
  targetWidth = TERRAIN_SIDE_BAND_TEXTURE_WIDTH,
  targetHeight = TERRAIN_MATERIAL_TEXTURE_PIXELS,
): Uint8ClampedArray {
  positiveSafeInteger(sourceWidth, "terrain side source width");
  positiveSafeInteger(sourceHeight, "terrain side source height");
  positiveSafeInteger(targetWidth, "terrain side target width");
  positiveSafeInteger(targetHeight, "terrain side target height");
  if (rgba.length !== sourceWidth * sourceHeight * 4) {
    throw new Error("terrain side dimensions must match its RGBA data");
  }
  let minPaintedX = sourceWidth;
  let maxPaintedX = -1;
  for (let y = 0; y < sourceHeight; y += 1) {
    for (let x = 0; x < sourceWidth; x += 1) {
      if ((rgba[(y * sourceWidth + x) * 4 + 3] ?? 0) > 0) {
        minPaintedX = Math.min(minPaintedX, x);
        maxPaintedX = Math.max(maxPaintedX, x);
      }
    }
  }
  if (maxPaintedX < minPaintedX) {
    throw new Error("terrain side source must contain painted pixels");
  }
  const outerX = edge === "left" ? minPaintedX : maxPaintedX;
  const sourceBandWidth = Math.min(5, maxPaintedX - minPaintedX + 1);
  const bandMinX = edge === "left" ? outerX : outerX - sourceBandWidth + 1;
  const bandMaxX = edge === "left" ? outerX + sourceBandWidth - 1 : outerX;
  let minPaintedY = sourceHeight;
  let maxPaintedY = -1;
  for (let y = 0; y < sourceHeight; y += 1) {
    for (let x = bandMinX; x <= bandMaxX; x += 1) {
      if ((rgba[(y * sourceWidth + x) * 4 + 3] ?? 0) > 0) {
        minPaintedY = Math.min(minPaintedY, y);
        maxPaintedY = Math.max(maxPaintedY, y);
      }
    }
  }
  if (maxPaintedY < minPaintedY) {
    throw new Error("terrain side edge corridor must contain painted pixels");
  }

  const paintedHeight = maxPaintedY - minPaintedY + 1;
  const output = new Uint8ClampedArray(targetWidth * targetHeight * 4);
  for (let y = 0; y < targetHeight; y += 1) {
    const phase = (y / targetHeight) * Math.PI * 2;
    const sourceY =
      minPaintedY +
      (paintedHeight - 1) *
        (0.5 + 0.48 * Math.sin(phase + 0.24 * Math.sin(3 * phase)));
    for (let x = 0; x < targetWidth; x += 1) {
      const fraction = targetWidth === 1 ? 0 : x / (targetWidth - 1);
      const sourceX =
        edge === "left"
          ? outerX + fraction * (sourceBandWidth - 1)
          : outerX - (1 - fraction) * (sourceBandWidth - 1);
      const offset = (y * targetWidth + x) * 4;
      for (const channel of [0, 1, 2, 3] as const) {
        output[offset + channel] = Math.round(
          sourceChannel(
            rgba,
            sourceWidth,
            sourceHeight,
            sourceX,
            sourceY,
            channel,
          ),
        );
      }
    }
  }
  return output;
}

/** Sample the palette-bound material after validating the source geometry. */
export function terrainMaterialPixelFromSource(
  profile: TerrainMaterialProfile,
  rgba: ArrayLike<number>,
  sourceWidth: number,
  sourceHeight: number,
  x: number,
  y: number,
  size: number,
): TerrainMaterialPixel {
  positiveSafeInteger(sourceWidth, "terrain source width");
  positiveSafeInteger(sourceHeight, "terrain source height");
  if (rgba.length !== sourceWidth * sourceHeight * 4) {
    throw new Error("terrain source dimensions must match its RGBA data");
  }
  return terrainMaterialPixel(profile, x, y, size);
}

/**
 * Deterministic copy plan that replaces each transparent source gutter in a
 * derived canvas with the nearest content-edge pixel. No neighboring atlas
 * cell is ever sampled, and the source canvas is never mutated.
 */
export function atlasExtrusionBlits(
  sheetWidth: number,
  sheetHeight: number,
): readonly AtlasExtrusionBlit[] {
  const geometry = tilesetGeometry(sheetWidth, sheetHeight);
  const g = geometry.gutterPixels;
  const out: AtlasExtrusionBlit[] = [];
  for (let row = 0; row < TILESET_ROWS; row += 1) {
    for (let column = 0; column < TILESET_COLS; column += 1) {
      const x = column * geometry.cellWidth;
      const y = row * geometry.cellHeight;
      const contentX = x + g;
      const contentY = y + g;
      const rightX = contentX + geometry.contentWidth - 1;
      const bottomY = contentY + geometry.contentHeight - 1;
      const push = (source: AtlasRect, target: AtlasRect) => {
        out.push(Object.freeze({ row, column, source, target }));
      };
      push(
        Object.freeze({
          x: contentX,
          y: contentY,
          w: geometry.contentWidth,
          h: geometry.contentHeight,
        }),
        Object.freeze({
          x: contentX,
          y: contentY,
          w: geometry.contentWidth,
          h: geometry.contentHeight,
        }),
      );
      if (g === 0) continue;
      push(
        Object.freeze({
          x: contentX,
          y: contentY,
          w: geometry.contentWidth,
          h: 1,
        }),
        Object.freeze({ x: contentX, y, w: geometry.contentWidth, h: g }),
      );
      push(
        Object.freeze({
          x: contentX,
          y: bottomY,
          w: geometry.contentWidth,
          h: 1,
        }),
        Object.freeze({
          x: contentX,
          y: bottomY + 1,
          w: geometry.contentWidth,
          h: g,
        }),
      );
      push(
        Object.freeze({
          x: contentX,
          y: contentY,
          w: 1,
          h: geometry.contentHeight,
        }),
        Object.freeze({ x, y: contentY, w: g, h: geometry.contentHeight }),
      );
      push(
        Object.freeze({
          x: rightX,
          y: contentY,
          w: 1,
          h: geometry.contentHeight,
        }),
        Object.freeze({
          x: rightX + 1,
          y: contentY,
          w: g,
          h: geometry.contentHeight,
        }),
      );
      const corners = [
        [contentX, contentY, x, y],
        [rightX, contentY, rightX + 1, y],
        [contentX, bottomY, x, bottomY + 1],
        [rightX, bottomY, rightX + 1, bottomY + 1],
      ] as const;
      for (const [sourceX, sourceY, targetX, targetY] of corners) {
        push(
          Object.freeze({ x: sourceX, y: sourceY, w: 1, h: 1 }),
          Object.freeze({ x: targetX, y: targetY, w: g, h: g }),
        );
      }
    }
  }
  return Object.freeze(out);
}

/** Backwards-compatible role helper for callers with slope classification. */
export function pickRole(
  slope: SlopeKind,
  depth: number,
  isLeftEdge: boolean,
  isRightEdge: boolean,
): TileRole {
  if (!Number.isSafeInteger(depth) || depth < 0) {
    throw new Error("tile depth must be a nonnegative safe integer");
  }
  if (depth === 0) {
    if (slope === "rise_r" || slope === "rise_l") return "slope_up";
    if (slope === "fall_r" || slope === "fall_l") return "slope_down";
    if (isLeftEdge && isRightEdge) return "top_single";
    if (isLeftEdge) return "top_left";
    if (isRightEdge) return "top_right";
    return "top_mid";
  }
  if (isLeftEdge) return "side_left";
  if (isRightEdge) return "side_right";
  return "fill";
}
