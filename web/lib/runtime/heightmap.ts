// Deterministic heightmap generator.
//
// Given a string tag, produce a 1D array of integer column heights for the
// stage. Used by scene.ts to lay tiles, place obstacles on flat ground, and
// fix mob/player Y positions.
//
// Determinism: SAME tag → SAME heightmap, byte-for-byte. We seed a small
// xorshift32 PRNG from a 32-bit FNV-1a hash of the tag, then sample.

function fnv1a32(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

function makeRng(seed: number): () => number {
  let x = (seed | 0) || 1;
  return () => {
    x ^= x << 13;
    x ^= x >>> 17;
    x ^= x << 5;
    return ((x >>> 0) % 0x100000000) / 0x100000000;
  };
}

export type HeightmapOpts = {
  /** Number of tile columns to generate. */
  cols: number;
  /** Minimum height (inclusive) in tiles above the bottom row. */
  minH: number;
  /** Maximum height (inclusive) in tiles above the bottom row. */
  maxH: number;
  /** Average run length (in columns) of a single flat ledge. */
  flatRun?: number;
};

/**
 * Build a heightmap of integer column heights. Adjacent columns differ by
 * at most ±1 (ensured by smoothing) so the tile picker only needs single-
 * step slope variants.
 */
export function buildHeightmap(tag: string, opts: HeightmapOpts): number[] {
  const { cols, minH, maxH, flatRun = 6 } = opts;
  const range = Math.max(1, maxH - minH);
  const rng = makeRng(fnv1a32(tag));

  // Generate raw heights: pick a target every ~flatRun columns, hold it for
  // that many columns, then drift to a new target.
  const heights: number[] = [];
  let cur = minH + Math.floor(rng() * (range + 1));
  let nextChangeAt = Math.max(2, Math.floor(rng() * flatRun) + Math.floor(flatRun / 2));
  for (let x = 0; x < cols; x++) {
    if (x === nextChangeAt) {
      // Drift target by ±1 or ±2 with probabilities.
      const r = rng();
      let delta = 0;
      if (r < 0.35) delta = +1;
      else if (r < 0.7) delta = -1;
      else if (r < 0.85) delta = +2;
      else delta = -2;
      cur = Math.min(maxH, Math.max(minH, cur + delta));
      nextChangeAt = x + Math.max(2, Math.floor(rng() * flatRun) + Math.floor(flatRun / 2));
    }
    heights.push(cur);
  }

  // Smooth: enforce ±1 max step between neighbours.
  for (let pass = 0; pass < 4; pass++) {
    let changed = false;
    for (let x = 1; x < cols; x++) {
      const d = heights[x] - heights[x - 1];
      if (d > 1) {
        heights[x] = heights[x - 1] + 1;
        changed = true;
      } else if (d < -1) {
        heights[x] = heights[x - 1] - 1;
        changed = true;
      }
    }
    if (!changed) break;
  }

  return heights;
}

/**
 * For a given column x, classify its slope context:
 * - "flat":      neighbours equal in height
 * - "rise_r":    column rises into the next column (h[x+1] > h[x])
 * - "rise_l":    column rises from the previous column (h[x-1] < h[x])
 * - "fall_r":    column drops into the next column (h[x+1] < h[x])
 * - "fall_l":    column drops from the previous column (h[x-1] > h[x])
 */
export type SlopeKind = "flat" | "rise_r" | "rise_l" | "fall_r" | "fall_l";

export function slopeAt(heights: number[], x: number): SlopeKind {
  const h = heights[x];
  const hL = x > 0 ? heights[x - 1] : h;
  const hR = x < heights.length - 1 ? heights[x + 1] : h;
  if (hR > h) return "rise_r";
  if (hL > h) return "fall_l";
  if (hR < h) return "fall_r";
  if (hL < h) return "rise_l";
  return "flat";
}

/**
 * Find runs of contiguous flat columns (where this column AND its k forward
 * neighbours all share the same height and none are slope columns). Used by
 * obstacle placement.
 */
export function flatRuns(
  heights: number[],
  minWidth: number,
): { start: number; len: number }[] {
  const out: { start: number; len: number }[] = [];
  let i = 0;
  while (i < heights.length) {
    if (slopeAt(heights, i) !== "flat") {
      i++;
      continue;
    }
    let j = i;
    const h = heights[i];
    while (
      j < heights.length &&
      heights[j] === h &&
      slopeAt(heights, j) === "flat"
    ) {
      j++;
    }
    const len = j - i;
    if (len >= minWidth) out.push({ start: i, len });
    i = Math.max(j, i + 1);
  }
  return out;
}
