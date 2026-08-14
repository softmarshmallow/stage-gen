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

// --- Tileset: consume canonical alpha + register cells by role. ---

import { cellRectFor, TILESET_COLS, TILESET_ROWS, type TileRole } from "./tiles";

export async function loadTileset(
  url: string,
  key: string,
  textures: Phaser.Textures.TextureManager,
  policy: PreviewTransparencyPolicy,
): Promise<{
  canvas: HTMLCanvasElement;
  tileW: number;
  tileH: number;
  bestFillCell: { row: number; col: number; opacity: number };
}> {
  const img = await fetchImage(url);
  const canvas = transparencyCanvas(img, policy);
  registerCanvas(textures, key, canvas);
  const tex = textures.get(key);
  const tileW = Math.floor(canvas.width / TILESET_COLS);
  const tileH = Math.floor(canvas.height / TILESET_ROWS);
  const ROLES: TileRole[] = [
    "top_left", "top_mid", "top_right", "top_single",
    "slope_up", "slope_down", "inner_tl", "inner_tr",
    "side_left", "side_right", "bot_left", "bot_right",
    "fill", "plat_left", "plat_mid", "plat_right",
  ];
  for (const role of ROLES) {
    for (let v = 0; v < 3; v++) {
      const r = cellRectFor(role, canvas.width, canvas.height, v);
      tex.add(`${role}_v${v}`, 0, r.x, r.y, r.w, r.h);
    }
  }

  // The 12×4 role contract is unreliable in places, but the tileset prompt
  // explicitly guarantees row 4 (0-indexed row 3), cols 1..4 are 100% solid
  // interior fill — the only cells contracted as fully opaque underground
  // blocks. The scrolling recipe owns that tile contract. Use cell
  // (row=3, col=0) as the canonical universal fill. Static, no scan.
  const FILL_ROW = 3;
  const FILL_COL = 0;
  tex.add(
    "ground_fill",
    0,
    FILL_COL * tileW,
    FILL_ROW * tileH,
    tileW,
    tileH,
  );

  return {
    canvas,
    tileW,
    tileH,
    bestFillCell: { row: FILL_ROW, col: FILL_COL, opacity: 1 },
  };
}

function transparencyCanvas(
  image: HTMLImageElement,
  policy: PreviewTransparencyPolicy,
): HTMLCanvasElement {
  return policy === "legacy-chroma" ? chromaKeyToAlpha(image) : copyImageToCanvas(image);
}
