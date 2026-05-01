// Centralised asset-load layer.
//
// Each asset family (parallax, tileset, character, mob, obstacle, items,
// inventory, portal) flows through the same chroma-key / bbox / edge-fade
// primitives. The scene calls into this module instead of doing its own
// fetch+process per asset, so the runtime image-ops contract stays in one
// place.

import {
  chromaKeyToAlpha,
  extractCellsBbox,
  fadeParallaxEdges,
  type CellRect,
} from "./image-ops";

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

// --- Parallax: chroma-key + edge-fade for non-opaque, raw for opaque. ---
//
// Parallax layers are the ONLY asset family that uses the tolerant
// chroma-key path (see image-ops.ts § ChromaKeyOptions and TC-078).
// gpt-image-2 drifts the magenta background substantially on dense
// foreground layers — the pipeline-side snap (Manhattan threshold 30)
// leaves a residual pink cluster around (220,50,200) that overwhelms
// the runtime blur. A wider runtime threshold cleans that up without
// mutating the on-disk PNG and without affecting sprite chroma keying
// (sprites still use exact-match → TC-062 preserved).
const LAYER_CHROMA_THRESHOLD = 180;

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
): Promise<LoadedParallaxLayer> {
  const img = await fetchImage(url);
  let canvas: HTMLCanvasElement;
  if (opaque) {
    const c = document.createElement("canvas");
    c.width = img.naturalWidth;
    c.height = img.naturalHeight;
    c.getContext("2d")!.drawImage(img, 0, 0);
    canvas = c;
  } else {
    const keyed = chromaKeyToAlpha(img, { threshold: LAYER_CHROMA_THRESHOLD });
    canvas = fadeParallaxEdges(keyed, fadePx);
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

// --- Generic chroma-keyed sprite (character, mob, portal, inventory). ---

export async function loadChromaKeyedSprite(
  url: string,
  key: string,
  textures: Phaser.Textures.TextureManager,
): Promise<HTMLCanvasElement> {
  const img = await fetchImage(url);
  const keyed = chromaKeyToAlpha(img);
  registerCanvas(textures, key, keyed);
  return keyed;
}

// --- Sliced spritesheet (mob idle/hurt/attack: 1 row × 4 frames). ---
// Registers the sheet under `key`, plus per-frame sub-textures `key:0` ..
// `key:N-1` cropped via per-cell alpha bbox (so frames lose magenta padding).

export type FrameRect = { x: number; y: number; w: number; h: number };

export async function loadFrameStrip(
  url: string,
  key: string,
  frames: number,
  textures: Phaser.Textures.TextureManager,
): Promise<{ canvas: HTMLCanvasElement; cells: CellRect[] }> {
  const img = await fetchImage(url);
  const keyed = chromaKeyToAlpha(img);
  registerCanvas(textures, key, keyed);
  const { cells } = extractCellsBbox(keyed, 1, frames);
  // Add each frame as a sub-frame on the texture. Frame names are integers
  // 0..N-1 so Phaser anim configs can reference them directly.
  const tex = textures.get(key);
  cells.forEach((cell, i) => {
    if (cell.w > 1 && cell.h > 1) {
      tex.add(i, 0, cell.x, cell.y, cell.w, cell.h);
    } else {
      // Empty frame fallback — point at the whole cell.
      const cellW = Math.floor(keyed.width / frames);
      tex.add(i, 0, i * cellW, 0, cellW, keyed.height);
    }
  });
  return { canvas: keyed, cells };
}

// --- Obstacles + items sheet (2 rows × 4 cols). ---

export async function loadGridSheet(
  url: string,
  key: string,
  rows: number,
  cols: number,
  framePrefix: string,
  textures: Phaser.Textures.TextureManager,
): Promise<{ canvas: HTMLCanvasElement; cells: CellRect[] }> {
  const img = await fetchImage(url);
  const keyed = chromaKeyToAlpha(img);
  registerCanvas(textures, key, keyed);
  const { cells } = extractCellsBbox(keyed, rows, cols);
  const tex = textures.get(key);
  cells.forEach((cell, idx) => {
    if (cell.w > 1 && cell.h > 1) {
      tex.add(`${framePrefix}_${idx}`, 0, cell.x, cell.y, cell.w, cell.h);
    }
  });
  return { canvas: keyed, cells };
}

// --- Tileset: chroma-key + register cells by role. ---

import { cellRectFor, TILESET_COLS, TILESET_ROWS, type TileRole } from "./tiles";

export async function loadTileset(
  url: string,
  key: string,
  textures: Phaser.Textures.TextureManager,
): Promise<{ canvas: HTMLCanvasElement; tileW: number; tileH: number }> {
  const img = await fetchImage(url);
  const keyed = chromaKeyToAlpha(img);
  registerCanvas(textures, key, keyed);
  const tex = textures.get(key);
  const tileW = Math.floor(keyed.width / TILESET_COLS);
  const tileH = Math.floor(keyed.height / TILESET_ROWS);
  const ROLES: TileRole[] = [
    "top_left", "top_mid", "top_right", "top_single",
    "slope_up", "slope_down", "inner_tl", "inner_tr",
    "side_left", "side_right", "bot_left", "bot_right",
    "fill", "plat_left", "plat_mid", "plat_right",
  ];
  for (const role of ROLES) {
    for (let v = 0; v < 3; v++) {
      const r = cellRectFor(role, keyed.width, keyed.height, v);
      tex.add(`${role}_v${v}`, 0, r.x, r.y, r.w, r.h);
    }
  }
  return { canvas: keyed, tileW, tileH };
}
