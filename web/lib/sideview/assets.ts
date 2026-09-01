// Centralised asset-load layer for side-view scenes.
//
// Each asset family (parallax, terrain atlas, character, mob, obstacle, items,
// inventory, portal) flows through the same alpha / bbox / edge-fade
// primitives. The current prepared manifests guarantee canonical-alpha PNGs
// for both AI and chroma generation modes. Everything here is genre-neutral:
// a loader that knows about a specific runtime's raster contract (the
// platformer's verified foreground repeats) lives with that runtime and reuses
// these primitives.

import Phaser from "phaser";

import {
  copyImageToCanvas,
  extractCellsBbox,
  fadeParallaxEdges,
  type CellRect,
} from "./image-ops";
import type { PreviewTransparencyPolicy } from "@/lib/shell/transparency";
import {
  TERRAIN_ATLAS_CELL_PX,
  TERRAIN_ATLAS_HEIGHT,
  TERRAIN_ATLAS_WIDTH,
  terrainAtlasFrameName,
  terrainAtlasLookupEntries,
} from "./terrain-atlas";

export type AssetUrlFn = (file: string) => string;

export async function fetchImage(url: string): Promise<HTMLImageElement> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${url} → HTTP ${response.status}`);
  const objectUrl = URL.createObjectURL(await response.blob());
  return await new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(objectUrl);
      resolve(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      reject(new Error(`image decode failed: ${url}`));
    };
    img.src = objectUrl;
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

/**
 * Load a single-subject sprite trimmed to the pixels it actually paints.
 *
 * A whole-canvas texture makes every display size a statement about the canvas rather than
 * about the artwork. The ladder is drawn across 89 of its 256 source columns, so asking for an
 * 80px-wide ladder produced 28px of rails and spent the remaining 52px on transparent margin -
 * next to a 56px-wide character. Trimming first is what lets a width constant mean the width
 * that appears on screen.
 */
export async function loadTrimmedSprite(
  url: string,
  key: string,
  textures: Phaser.Textures.TextureManager,
  policy: PreviewTransparencyPolicy,
): Promise<{ canvas: HTMLCanvasElement; trimmed: CellRect }> {
  const img = await fetchImage(url);
  const source = transparencyCanvas(img, policy);
  const { cells } = extractCellsBbox(source, 1, 1);
  const cell = cells[0];
  // A blank or unreadable subject keeps the untrimmed canvas rather than collapsing to nothing.
  if (!cell || cell.w <= 1 || cell.h <= 1) {
    registerCanvas(textures, key, source);
    return {
      canvas: source,
      trimmed: { row: 0, col: 0, x: 0, y: 0, w: source.width, h: source.height },
    };
  }
  const canvas = document.createElement("canvas");
  canvas.width = cell.w;
  canvas.height = cell.h;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("2d context unavailable");
  context.drawImage(source, cell.x, cell.y, cell.w, cell.h, 0, 0, cell.w, cell.h);
  registerCanvas(textures, key, canvas);
  return { canvas, trimmed: cell };
}

// Opaque concept/backdrop assets never participate in transparency handling.
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

/** Register the canonical 47-mask atlas as exact 120px frames for dynamic tilemaps. */
export async function loadTerrainAtlas(
  url: string,
  key: string,
  textures: Phaser.Textures.TextureManager,
  policy: PreviewTransparencyPolicy,
): Promise<HTMLCanvasElement> {
  const image = await fetchImage(url);
  const canvas = transparencyCanvas(image, policy);
  if (canvas.width !== TERRAIN_ATLAS_WIDTH || canvas.height !== TERRAIN_ATLAS_HEIGHT) {
    throw new Error(
      `terrain atlas must be exactly ${TERRAIN_ATLAS_WIDTH}x${TERRAIN_ATLAS_HEIGHT}`,
    );
  }
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error("terrain atlas import requires a 2d canvas");
  const entries = terrainAtlasLookupEntries();
  for (const { coordinate } of entries) {
    const alpha = context.getImageData(
      coordinate.column * TERRAIN_ATLAS_CELL_PX,
      coordinate.row * TERRAIN_ATLAS_CELL_PX,
      TERRAIN_ATLAS_CELL_PX,
      TERRAIN_ATLAS_CELL_PX,
    ).data;
    if (!Array.from({ length: alpha.length / 4 }, (_, index) => alpha[index * 4 + 3]).some(Boolean)) {
      throw new Error("terrain atlas contains an empty lookup cell");
    }
  }
  const placeholderAlpha = context.getImageData(
    10 * TERRAIN_ATLAS_CELL_PX,
    TERRAIN_ATLAS_CELL_PX,
    TERRAIN_ATLAS_CELL_PX,
    TERRAIN_ATLAS_CELL_PX,
  ).data;
  if (
    Array.from(
      { length: placeholderAlpha.length / 4 },
      (_, index) => placeholderAlpha[index * 4 + 3],
    ).some(Boolean)
  ) {
    throw new Error("terrain atlas placeholder cell must be transparent");
  }
  registerCanvas(textures, key, canvas);
  const texture = textures.get(key);
  texture.setFilter(Phaser.Textures.FilterMode.NEAREST);
  for (const { coordinate } of entries) {
    texture.add(
      terrainAtlasFrameName(coordinate),
      0,
      coordinate.column * TERRAIN_ATLAS_CELL_PX,
      coordinate.row * TERRAIN_ATLAS_CELL_PX,
      TERRAIN_ATLAS_CELL_PX,
      TERRAIN_ATLAS_CELL_PX,
    );
  }
  return canvas;
}

export function transparencyCanvas(
  image: HTMLImageElement,
  policy: PreviewTransparencyPolicy,
): HTMLCanvasElement {
  if (policy !== "canonical-alpha") {
    throw new Error("current scrolling assets require canonical-alpha policy");
  }
  return copyImageToCanvas(image);
}
