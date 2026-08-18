// Centralised asset-load layer.
//
// Each asset family (parallax, tileset, character, mob, obstacle, items,
// inventory, portal) flows through the same alpha / bbox / edge-fade
// primitives. New runs already provide canonical transparent PNGs. Exact
// magenta keying is retained only for legacy manifests without strategy data.

import {
  chromaKeyToAlpha,
  copyImageToCanvas,
  extractCellsBbox,
  fadeParallaxEdges,
  type CellRect,
} from "./image-ops";
import type { PreviewTransparencyPolicy } from "@/lib/shell/transparency";
import {
  prepareForegroundRaster,
  type PreparedForegroundRaster,
} from "./foreground";

export type AssetUrlFn = (file: string) => string;

export async function fetchImage(url: string): Promise<HTMLImageElement> {
  return await new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = (e) => reject(new Error(`image load failed: ${url} (${e})`));
    img.src = url;
  });
}

export async function fetchJson<T>(url: string): Promise<T> {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`${url} → HTTP ${r.status}`);
  return (await r.json()) as T;
}

// Replace any existing texture under key with a fresh canvas-backed one.
export function registerCanvas(
  textures: Phaser.Textures.TextureManager,
  key: string,
  canvas: HTMLCanvasElement,
) {
  if (textures.exists(key)) textures.remove(key);
  textures.addCanvas(key, canvas);
}

// --- Parallax: preserve canonical alpha + edge-fade for non-opaque. ---
export type LoadedParallaxLayer = {
  key: string;
  canvas: HTMLCanvasElement;
  width: number;
  height: number;
  opaque: boolean;
};

export type LoadedForegroundLayer = LoadedParallaxLayer &
  Readonly<{
    foreground: Pick<
      PreparedForegroundRaster,
      | "sourceWidth"
      | "sourceHeight"
      | "contentBounds"
      | "meaningfulContentBounds"
      | "contactStrip"
      | "contactSourceY"
      | "repeatPeriod"
      | "overlap"
    >;
  }>;

export async function loadParallaxLayer(
  url: string,
  key: string,
  opaque: boolean,
  fadePx: number,
  textures: Phaser.Textures.TextureManager,
  policy: PreviewTransparencyPolicy,
): Promise<LoadedParallaxLayer> {
  const img = await fetchImage(url);
  let canvas: HTMLCanvasElement;
  if (opaque) {
    canvas = copyImageToCanvas(img);
  } else {
    canvas = fadeParallaxEdges(transparencyCanvas(img, policy), fadePx);
  }
  registerCanvas(textures, key, canvas);
  return {
    key,
    canvas,
    width: canvas.width,
    height: canvas.height,
    opaque,
  };
}

/** Prepare one vertically trimmed, premultiplied periodic foreground canvas. */
export async function loadForegroundLayer(
  url: string,
  key: string,
  overlapPx: number,
  textures: Phaser.Textures.TextureManager,
  policy: PreviewTransparencyPolicy,
): Promise<LoadedForegroundLayer> {
  const image = await fetchImage(url);
  const source = transparencyCanvas(image, policy);
  const sourceContext = source.getContext("2d", { willReadFrequently: true });
  if (!sourceContext) {
    throw new Error("foreground preparation requires a 2d source canvas");
  }
  const prepared = prepareForegroundRaster(
    {
      width: source.width,
      height: source.height,
      data: sourceContext.getImageData(0, 0, source.width, source.height).data,
    },
    overlapPx,
  );
  const canvas = document.createElement("canvas");
  canvas.width = prepared.width;
  canvas.height = prepared.height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) {
    throw new Error("foreground preparation requires a 2d target canvas");
  }
  const imageData = context.createImageData(prepared.width, prepared.height);
  imageData.data.set(prepared.data);
  context.putImageData(imageData, 0, 0);
  registerCanvas(textures, key, canvas);
  return {
    key,
    canvas,
    width: canvas.width,
    height: canvas.height,
    opaque: false,
    foreground: {
      sourceWidth: prepared.sourceWidth,
      sourceHeight: prepared.sourceHeight,
      contentBounds: prepared.contentBounds,
      meaningfulContentBounds: prepared.meaningfulContentBounds,
      contactStrip: prepared.contactStrip,
      contactSourceY: prepared.contactSourceY,
      repeatPeriod: prepared.repeatPeriod,
      overlap: prepared.overlap,
    },
  };
}

// --- Generic transparent sprite (character, mob, portal, inventory). ---

export async function loadTransparentSprite(
  url: string,
  key: string,
  textures: Phaser.Textures.TextureManager,
  policy: PreviewTransparencyPolicy,
): Promise<HTMLCanvasElement> {
  const img = await fetchImage(url);
  const canvas = transparencyCanvas(img, policy);
  registerCanvas(textures, key, canvas);
  return canvas;
}

// Opaque concept/backdrop assets never participate in transparency handling,
// including when a legacy run is previewed.
export async function loadOpaqueSprite(
  url: string,
  key: string,
  textures: Phaser.Textures.TextureManager,
): Promise<HTMLCanvasElement> {
  const img = await fetchImage(url);
  const canvas = copyImageToCanvas(img);
  registerCanvas(textures, key, canvas);
  return canvas;
}

// --- Sliced spritesheet (mob idle/hurt/attack: 1 row × 4 frames). ---
// Registers the sheet under `key`, plus per-frame sub-textures `key:0` ..
// `key:N-1` cropped via each cell's alpha bounding box.

export type FrameRect = { x: number; y: number; w: number; h: number };

export async function loadFrameStrip(
  url: string,
  key: string,
  frames: number,
  textures: Phaser.Textures.TextureManager,
  policy: PreviewTransparencyPolicy,
): Promise<{ canvas: HTMLCanvasElement; cells: CellRect[] }> {
  const img = await fetchImage(url);
  const canvas = transparencyCanvas(img, policy);
  registerCanvas(textures, key, canvas);
  const { cells } = extractCellsBbox(canvas, 1, frames);
  // Add each frame as a sub-frame on the texture. Frame names are integers
  // 0..N-1 so Phaser anim configs can reference them directly.
  const tex = textures.get(key);
  cells.forEach((cell, i) => {
    if (cell.w > 1 && cell.h > 1) {
      tex.add(i, 0, cell.x, cell.y, cell.w, cell.h);
    } else {
      // Empty frame fallback — point at the whole cell.
      const cellW = Math.floor(canvas.width / frames);
      tex.add(i, 0, i * cellW, 0, cellW, canvas.height);
    }
  });
  return { canvas, cells };
}

// --- Obstacles + items sheet (2 rows × 4 cols). ---

export async function loadGridSheet(
  url: string,
  key: string,
  rows: number,
  cols: number,
  framePrefix: string,
  textures: Phaser.Textures.TextureManager,
  policy: PreviewTransparencyPolicy,
): Promise<{ canvas: HTMLCanvasElement; cells: CellRect[] }> {
  const img = await fetchImage(url);
  const canvas = transparencyCanvas(img, policy);
  registerCanvas(textures, key, canvas);
  const { cells } = extractCellsBbox(canvas, rows, cols);
  const tex = textures.get(key);
  cells.forEach((cell, idx) => {
    if (cell.w > 1 && cell.h > 1) {
      tex.add(`${framePrefix}_${idx}`, 0, cell.x, cell.y, cell.w, cell.h);
    }
  });
  return { canvas, cells };
}

// --- Tileset: consume canonical alpha into continuous terrain materials. ---

import {
  atlasExtrusionBlits,
  cellRectFor,
  contentRectFor,
  deriveTerrainMaterialProfile,
  deriveTerrainSideBand,
  deriveTerrainSurfaceBand,
  terrainIntegrationPixel,
  terrainMaterialPixelFromSource,
  TERRAIN_INTEGRATION_TEXTURE_DEPTH,
  TERRAIN_MATERIAL_TEXTURE_PIXELS,
  TERRAIN_SIDE_BAND_TEXTURE_WIDTH,
  TERRAIN_SURFACE_BAND_TEXTURE_HEIGHT,
  tilesetGeometry,
  type TerrainMaterialProfile,
  type TerrainIntegrationAxis,
  type TerrainSideEdge,
} from "./tiles";

/**
 * Build a runtime-only atlas whose isolation gutters repeat each cell's own
 * edge pixels. This prevents transparent gutter scaling and cross-cell
 * sampling without changing the approved source image bytes.
 */
export function prepareTilesetCanvas(
  source: HTMLCanvasElement,
): HTMLCanvasElement {
  const geometry = tilesetGeometry(source.width, source.height);
  const fillContent = contentRectFor("fill", source.width, source.height, 0);
  assertOpaqueCanvasRect(source, fillContent, "tileset fill content");

  const prepared = document.createElement("canvas");
  prepared.width = source.width;
  prepared.height = source.height;
  const context = prepared.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error("tileset preparation requires a 2d canvas");
  context.imageSmoothingEnabled = false;
  for (const blit of atlasExtrusionBlits(source.width, source.height)) {
    context.drawImage(
      source,
      blit.source.x,
      blit.source.y,
      blit.source.w,
      blit.source.h,
      blit.target.x,
      blit.target.y,
      blit.target.w,
      blit.target.h,
    );
  }

  // The canonical fill frame is the coverage layer under every terrain role.
  // Its derived cell must remain opaque including the extruded gutter.
  const fillCell = cellRectFor("fill", source.width, source.height, 0);
  assertOpaqueCanvasRect(prepared, fillCell, "prepared tileset fill frame");
  if (fillCell.w !== geometry.cellWidth || fillCell.h !== geometry.cellHeight) {
    throw new Error(
      "prepared tileset cell geometry diverged from its contract",
    );
  }
  return prepared;
}

export function prepareTerrainMaterialCanvas(
  source: HTMLCanvasElement,
): Readonly<{
  canvas: HTMLCanvasElement;
  profile: TerrainMaterialProfile;
}> {
  const fillContent = contentRectFor("fill", source.width, source.height, 0);
  assertOpaqueCanvasRect(source, fillContent, "tileset fill content");
  const sourceContext = source.getContext("2d", { willReadFrequently: true });
  if (!sourceContext) {
    throw new Error("terrain material preparation requires a 2d source canvas");
  }
  const sourcePixels = sourceContext.getImageData(
    fillContent.x,
    fillContent.y,
    fillContent.w,
    fillContent.h,
  ).data;
  const profile = deriveTerrainMaterialProfile(sourcePixels);
  const material = document.createElement("canvas");
  material.width = TERRAIN_MATERIAL_TEXTURE_PIXELS;
  material.height = TERRAIN_MATERIAL_TEXTURE_PIXELS;
  const context = material.getContext("2d", { willReadFrequently: true });
  if (!context) {
    throw new Error("terrain material preparation requires a 2d target canvas");
  }
  const image = context.createImageData(material.width, material.height);
  for (let y = 0; y < material.height; y += 1) {
    for (let x = 0; x < material.width; x += 1) {
      const color = terrainMaterialPixelFromSource(
        profile,
        sourcePixels,
        fillContent.w,
        fillContent.h,
        x,
        y,
        material.width,
      );
      const offset = (y * material.width + x) * 4;
      image.data[offset] = color.red;
      image.data[offset + 1] = color.green;
      image.data[offset + 2] = color.blue;
      image.data[offset + 3] = color.alpha;
    }
  }
  context.putImageData(image, 0, 0);
  return Object.freeze({ canvas: material, profile });
}

export function prepareTerrainSurfaceCanvas(
  source: HTMLCanvasElement,
): HTMLCanvasElement {
  const cap = contentRectFor("top_single", source.width, source.height, 0);
  const sourceContext = source.getContext("2d", { willReadFrequently: true });
  if (!sourceContext) {
    throw new Error("terrain surface preparation requires a 2d source canvas");
  }
  const pixels = sourceContext.getImageData(cap.x, cap.y, cap.w, cap.h).data;
  const surface = document.createElement("canvas");
  surface.width = TERRAIN_MATERIAL_TEXTURE_PIXELS;
  surface.height = TERRAIN_SURFACE_BAND_TEXTURE_HEIGHT;
  const context = surface.getContext("2d", { willReadFrequently: true });
  if (!context) {
    throw new Error("terrain surface preparation requires a 2d target canvas");
  }
  const image = context.createImageData(surface.width, surface.height);
  image.data.set(
    deriveTerrainSurfaceBand(
      pixels,
      cap.w,
      cap.h,
      surface.width,
      surface.height,
    ),
  );
  context.putImageData(image, 0, 0);
  return surface;
}

export function prepareTerrainSideCanvas(
  source: HTMLCanvasElement,
  edge: TerrainSideEdge,
): HTMLCanvasElement {
  const role = edge === "left" ? "side_left" : "side_right";
  const side = contentRectFor(role, source.width, source.height, 0);
  const sourceContext = source.getContext("2d", { willReadFrequently: true });
  if (!sourceContext) {
    throw new Error("terrain side preparation requires a 2d source canvas");
  }
  const pixels = sourceContext.getImageData(
    side.x,
    side.y,
    side.w,
    side.h,
  ).data;
  const strip = document.createElement("canvas");
  strip.width = TERRAIN_SIDE_BAND_TEXTURE_WIDTH;
  strip.height = TERRAIN_MATERIAL_TEXTURE_PIXELS;
  const context = strip.getContext("2d", { willReadFrequently: true });
  if (!context) {
    throw new Error("terrain side preparation requires a 2d target canvas");
  }
  const image = context.createImageData(strip.width, strip.height);
  image.data.set(
    deriveTerrainSideBand(
      pixels,
      side.w,
      side.h,
      edge,
      strip.width,
      strip.height,
    ),
  );
  context.putImageData(image, 0, 0);
  return strip;
}

export function prepareTerrainIntegrationCanvas(
  profile: TerrainMaterialProfile,
  axis: TerrainIntegrationAxis,
): HTMLCanvasElement {
  const vertical = axis !== "surface";
  const canvas = document.createElement("canvas");
  canvas.width = vertical
    ? TERRAIN_INTEGRATION_TEXTURE_DEPTH
    : TERRAIN_MATERIAL_TEXTURE_PIXELS;
  canvas.height = vertical
    ? TERRAIN_MATERIAL_TEXTURE_PIXELS
    : TERRAIN_INTEGRATION_TEXTURE_DEPTH;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) {
    throw new Error("terrain integration preparation requires a 2d canvas");
  }
  const image = context.createImageData(canvas.width, canvas.height);
  for (let y = 0; y < canvas.height; y += 1) {
    for (let x = 0; x < canvas.width; x += 1) {
      const along = vertical ? y : x;
      const depth =
        axis === "side-right" ? canvas.width - 1 - x : vertical ? x : y;
      const color = terrainIntegrationPixel(profile, axis, along, depth);
      const offset = (y * canvas.width + x) * 4;
      image.data[offset] = color.red;
      image.data[offset + 1] = color.green;
      image.data[offset + 2] = color.blue;
      image.data[offset + 3] = color.alpha;
    }
  }
  context.putImageData(image, 0, 0);
  return canvas;
}

export async function loadTileset(
  url: string,
  key: string,
  textures: Phaser.Textures.TextureManager,
  policy: PreviewTransparencyPolicy,
): Promise<{
  canvas: HTMLCanvasElement;
  fillMaterialKey: string;
  surfaceMaterialKey: string;
  leftSideMaterialKey: string;
  rightSideMaterialKey: string;
  surfaceIntegrationKey: string;
  leftSideIntegrationKey: string;
  rightSideIntegrationKey: string;
  fillMaterialProfile: TerrainMaterialProfile;
}> {
  const img = await fetchImage(url);
  const sourceCanvas = transparencyCanvas(img, policy);
  const canvas = prepareTilesetCanvas(sourceCanvas);
  const fillMaterial = prepareTerrainMaterialCanvas(sourceCanvas);
  const surfaceMaterial = prepareTerrainSurfaceCanvas(sourceCanvas);
  const leftSideMaterial = prepareTerrainSideCanvas(sourceCanvas, "left");
  const rightSideMaterial = prepareTerrainSideCanvas(sourceCanvas, "right");
  const surfaceIntegration = prepareTerrainIntegrationCanvas(
    fillMaterial.profile,
    "surface",
  );
  const leftSideIntegration = prepareTerrainIntegrationCanvas(
    fillMaterial.profile,
    "side-left",
  );
  const rightSideIntegration = prepareTerrainIntegrationCanvas(
    fillMaterial.profile,
    "side-right",
  );
  const fillMaterialKey = `${key}_continuous_fill`;
  const surfaceMaterialKey = `${key}_continuous_surface`;
  const leftSideMaterialKey = `${key}_continuous_side_left`;
  const rightSideMaterialKey = `${key}_continuous_side_right`;
  const surfaceIntegrationKey = `${key}_surface_integration`;
  const leftSideIntegrationKey = `${key}_side_left_integration`;
  const rightSideIntegrationKey = `${key}_side_right_integration`;
  registerCanvas(textures, key, canvas);
  registerCanvas(textures, fillMaterialKey, fillMaterial.canvas);
  registerCanvas(textures, surfaceMaterialKey, surfaceMaterial);
  registerCanvas(textures, leftSideMaterialKey, leftSideMaterial);
  registerCanvas(textures, rightSideMaterialKey, rightSideMaterial);
  registerCanvas(textures, surfaceIntegrationKey, surfaceIntegration);
  registerCanvas(textures, leftSideIntegrationKey, leftSideIntegration);
  registerCanvas(textures, rightSideIntegrationKey, rightSideIntegration);

  return {
    canvas,
    fillMaterialKey,
    surfaceMaterialKey,
    leftSideMaterialKey,
    rightSideMaterialKey,
    surfaceIntegrationKey,
    leftSideIntegrationKey,
    rightSideIntegrationKey,
    fillMaterialProfile: fillMaterial.profile,
  };
}

function assertOpaqueCanvasRect(
  canvas: HTMLCanvasElement,
  rect: { x: number; y: number; w: number; h: number },
  label: string,
): void {
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error(`${label} requires a 2d canvas`);
  const pixels = context.getImageData(rect.x, rect.y, rect.w, rect.h).data;
  for (let offset = 3; offset < pixels.length; offset += 4) {
    if (pixels[offset] !== 255) {
      throw new Error(`${label} must be fully opaque`);
    }
  }
}

function transparencyCanvas(
  image: HTMLImageElement,
  policy: PreviewTransparencyPolicy,
): HTMLCanvasElement {
  return policy === "legacy-chroma"
    ? chromaKeyToAlpha(image)
    : copyImageToCanvas(image);
}
