// Pure runtime image-processing primitives.
//
// Two operations the runtime applies as it loads pipeline-generated assets:
//
//   1. extractCellsBbox  — per-cell alpha bbox crop on a grid sheet (TC-063)
//   2. fadeParallaxEdges — left/right alpha taper for seamless loop (TC-064)
//
// Everything happens on an in-memory <canvas>; the on-disk PNG is never
// touched. Current v7 scrolling manifests always carry canonical alpha.
//
// Output: a fresh HTMLCanvasElement holding the processed pixels. Callers
// register it with Phaser via `textures.addCanvas(key, canvas)`.

export type ImageSource = HTMLImageElement | HTMLCanvasElement;

/** Copy an image into a fresh canvas while preserving its existing alpha. */
export function copyImageToCanvas(img: ImageSource): HTMLCanvasElement {
  // Take the source dimensions even if it's a plain Image.
  const w = "naturalWidth" in img ? img.naturalWidth || img.width : img.width;
  const h = "naturalHeight" in img ? img.naturalHeight || img.height : img.height;
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  const ctx = c.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("2d context unavailable");
  ctx.drawImage(img as CanvasImageSource, 0, 0);
  return c;
}

// 1) extractCellsBbox — slice a grid sheet (rows × cols) and per-cell
// compute the alpha bounding box of the actual content. Returns the cropped
// region rectangle for each cell (left-to-right, top-to-bottom).
//
// Important: pass an alpha-bearing canvas in. extractCellsBbox does not derive
// transparency itself; it expects alpha=0 to mark the exterior.
//
// Returns the per-cell rectangles and a sourceCanvas the caller can use to
// register sub-textures. An empty cell (no non-zero alpha) yields a 1×1
// rect at the cell's centre.
export type CellRect = {
  /** Cell's row index (0-based, top to bottom). */
  row: number;
  /** Cell's column index (0-based, left to right). */
  col: number;
  /** Source-canvas X of cropped content (left, inclusive). */
  x: number;
  /** Source-canvas Y of cropped content (top, inclusive). */
  y: number;
  /** Cropped content width in source pixels. */
  w: number;
  /** Cropped content height in source pixels. */
  h: number;
};

/**
 * Alpha at or below which a pixel is matte residue rather than subject.
 *
 * A chroma matte leaves a faint tail behind - measured at 33 to 64 across the bottom of about
 * half the animation frames in a run. It is invisible, but a bbox taken on `alpha !== 0` ends at
 * the tail rather than at the artwork, and since sprites are bottom-anchored the tail is what
 * lands on the ground while the creature hangs above it. Trimming on meaningful coverage also
 * makes the frames of one strip agree in height again: measured over a full run it takes
 * per-frame variation from 1.39-2.58x down to 1.00-1.31x, with the remainder being jump, attack
 * and hurt poses that genuinely change height.
 */
export const SPRITE_PAINTED_ALPHA_THRESHOLD = 64;

export function extractCellsBbox(
  spriteSheet: ImageSource,
  rows: number,
  cols: number,
): { sourceCanvas: HTMLCanvasElement; cells: CellRect[] } {
  const sourceCanvas =
    spriteSheet instanceof HTMLCanvasElement
      ? spriteSheet
      : copyImageToCanvas(spriteSheet);
  const ctx = sourceCanvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("2d context unavailable");
  const W = sourceCanvas.width;
  const H = sourceCanvas.height;
  const cellW = Math.floor(W / cols);
  const cellH = Math.floor(H / rows);
  const id = ctx.getImageData(0, 0, W, H);
  const px = id.data;

  const cells: CellRect[] = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const x0 = c * cellW;
      const y0 = r * cellH;
      const x1 = c === cols - 1 ? W : x0 + cellW;
      const y1 = r === rows - 1 ? H : y0 + cellH;

      let minX = x1;
      let minY = y1;
      let maxX = x0 - 1;
      let maxY = y0 - 1;
      let found = false;

      for (let y = y0; y < y1; y++) {
        const rowOffset = y * W * 4;
        for (let x = x0; x < x1; x++) {
          const a = px[rowOffset + x * 4 + 3]!;
          if (a > SPRITE_PAINTED_ALPHA_THRESHOLD) {
            if (x < minX) minX = x;
            if (x > maxX) maxX = x;
            if (y < minY) minY = y;
            if (y > maxY) maxY = y;
            found = true;
          }
        }
      }

      if (!found) {
        const cx = Math.floor((x0 + x1) / 2);
        const cy = Math.floor((y0 + y1) / 2);
        cells.push({ row: r, col: c, x: cx, y: cy, w: 1, h: 1 });
      } else {
        cells.push({
          row: r,
          col: c,
          x: minX,
          y: minY,
          w: maxX - minX + 1,
          h: maxY - minY + 1,
        });
      }
    }
  }
  return { sourceCanvas, cells };
}

// 2) fadeParallaxEdges — apply a smooth alpha taper from the outermost
// L/R columns inward. Outer column ends at alpha 0; ~fadePx inward the
// alpha is fully restored to its original value. The on-disk PNG is
// untouched — we only mutate the in-memory canvas. (TC-064)
//
// The taper multiplies the existing alpha so transparent regions stay
// transparent. This is what enables the two-image looping
// crossfade described in docs/spec/asset-contracts.md § "Looping".
export function fadeParallaxEdges(
  img: ImageSource,
  fadePx = 64,
): HTMLCanvasElement {
  const canvas = copyImageToCanvas(img);
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("2d context unavailable");
  const W = canvas.width;
  const H = canvas.height;
  if (fadePx <= 0 || W < 2) return canvas;
  const fade = Math.min(fadePx, Math.floor(W / 2));
  const id = ctx.getImageData(0, 0, W, H);
  const px = id.data;
  // Pre-compute multipliers for the leftmost `fade` columns.
  // Column 0 → 0; column (fade-1) → near 1.
  const mult = new Float32Array(fade);
  for (let i = 0; i < fade; i++) {
    mult[i] = i / fade;
  }
  for (let y = 0; y < H; y++) {
    const rowOffset = y * W * 4;
    for (let i = 0; i < fade; i++) {
      // Left band: columns [0..fade)
      const li = rowOffset + i * 4 + 3;
      px[li] = Math.round(px[li] * mult[i]);
      // Right band: columns [W-fade..W)  symmetric
      const ri = rowOffset + (W - 1 - i) * 4 + 3;
      px[ri] = Math.round(px[ri] * mult[i]);
    }
  }
  ctx.putImageData(id, 0, 0);
  return canvas;
}

// Utility: read alpha at a single pixel — used by spot-check probes.
export function alphaAt(canvas: HTMLCanvasElement, x: number, y: number): number {
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("2d context unavailable");
  return ctx.getImageData(x, y, 1, 1).data[3];
}
