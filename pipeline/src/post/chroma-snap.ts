// Deterministic chroma-snap post-processor — flood-from-edges variant
// (Phase 5 / TC-042b / TC-078 retry 2).
//
// PROBLEM: gpt-image-2 outputs drift the supposed-magenta chroma-key
// background from exact #FF00FF (255, 0, 255) to clusters that range
// from a tight (243, 3-12, 230-242) all the way out to (180, 80, 200)
// and beyond on heavy foreground layers. The previous threshold-based
// snap (Manhattan ≤ 30) only caught the tight cluster; the loose end
// leaked tens of thousands of pink pixels per frame on parallax layers
// AND left pink rectangles around mob sprite turnarounds.
//
// Bumping the threshold high enough to catch the full drift cluster
// (≥ 200) starts eating stylistic interior pinks (skin tones, painted
// blossoms, the flame on a fire-mob's tail). False positives.
//
// THE FIX (definitional): a sprite/layer BACKGROUND is the magenta-ish
// region CONNECTED TO THE EDGE of the PNG. Interior magenta blobs
// (rare — e.g. a stylistic pink prop floating inside a sprite's body)
// are NOT edge-connected and must stay opaque.
//
// snapChromaKey() now does:
//   1. Read raw RGBA via sharp.
//   2. Build a "background" mask via 4-connected BFS flood-fill from
//      every edge pixel that is within EDGE_SEED_THRESHOLD of (255,0,255).
//      The flood spreads to neighbours within FLOOD_THRESHOLD.
//   3. For every masked pixel, snap RGB to exact (255,0,255). Alpha
//      preserved. Non-masked pixels untouched (interior pinks survive).
//   4. Update sidecar with extra.chroma_method = "flood-from-edges"
//      so a re-run skips cheaply.
//
// Idempotent: re-running on flood-snapped output produces the same mask
// (already-exact magenta is within both thresholds), so output is
// byte-identical. Sidecar gates the redundant work.

import { readFile, writeFile, stat } from "node:fs/promises";
import sharp from "sharp";

export interface SnapChromaOptions {
  /** Manhattan-distance threshold for edge SEED pixels (default 280).
   *  Generous — anything pinkish on the border is treated as a candidate
   *  background seed. Outliers that aren't actually background still get
   *  filtered by the flood-fill connectivity constraint. */
  seedThreshold?: number;
  /** Manhattan-distance threshold for FLOOD propagation (default 220).
   *  A neighbour is added to the background mask only if its colour is
   *  within this distance of (255,0,255). Wider than the original 30 to
   *  bridge the full drift cluster, but the connectivity requirement
   *  still gates interior pinks. */
  floodThreshold?: number;
}

export interface SnapChromaResult {
  /** Absolute path of the processed PNG. */
  imagePath: string;
  /** Number of pixels rewritten to exact (255,0,255) during this call. */
  snappedPixels: number;
  /** Number of pixels already at exact (255,0,255) before the call. */
  exactBefore: number;
  /** Number of pixels at exact (255,0,255) after the call. */
  exactAfter: number;
  /** Seed threshold used. */
  seedThreshold: number;
  /** Flood threshold used. */
  floodThreshold: number;
  /** True if the file was already marked snapped with the current method
   *  in its sidecar and processing was skipped. */
  skipped: boolean;
}

const TARGET_R = 255;
const TARGET_G = 0;
const TARGET_B = 255;
const DEFAULT_SEED_THRESHOLD = 280;
const DEFAULT_FLOOD_THRESHOLD = 220;
const METHOD = "flood-from-edges";

/** Read the sidecar JSON if present; return undefined on any failure. */
async function readSidecar(imagePath: string): Promise<any | undefined> {
  const sidecarPath = `${imagePath}.meta.json`;
  try {
    const raw = await readFile(sidecarPath, "utf8");
    return JSON.parse(raw);
  } catch {
    return undefined;
  }
}

/** Update sidecar in place, merging chroma-snap fields into extra. */
async function patchSidecar(
  imagePath: string,
  patch: {
    chroma_snapped: true;
    chroma_method: typeof METHOD;
    chroma_seed_threshold: number;
    chroma_flood_threshold: number;
    chroma_snap_count: number;
  },
): Promise<void> {
  const sidecarPath = `${imagePath}.meta.json`;
  let payload: any;
  try {
    const raw = await readFile(sidecarPath, "utf8");
    payload = JSON.parse(raw);
  } catch {
    payload = { stage: "post-chroma", ts: new Date().toISOString() };
  }
  payload.extra = { ...(payload.extra ?? {}), ...patch };
  await writeFile(sidecarPath, JSON.stringify(payload, null, 2) + "\n", "utf8");
}

function manhattanFromMagenta(r: number, g: number, b: number): number {
  // (255 - r) + g + (255 - b) — equivalent to Manhattan(r,g,b → 255,0,255).
  // Each channel range is [0..255] so abs is unnecessary, but use abs to
  // be defensive against signed surprises.
  return Math.abs(r - TARGET_R) + Math.abs(g - TARGET_G) + Math.abs(b - TARGET_B);
}

/**
 * Snap edge-connected near-magenta pixels in a PNG to exact #FF00FF.
 *
 * Idempotent. In-place. Updates the sidecar with chroma_method marker.
 * If the sidecar already says extra.chroma_method === "flood-from-edges",
 * this is a no-op (returns skipped: true). Older threshold-based snaps
 * (chroma_method missing or != "flood-from-edges") are RE-PROCESSED so
 * the upgrade actually flows through to existing on-disk assets.
 */
export async function snapChromaKey(
  imagePath: string,
  options: SnapChromaOptions = {},
): Promise<SnapChromaResult> {
  const seedThreshold = options.seedThreshold ?? DEFAULT_SEED_THRESHOLD;
  const floodThreshold = options.floodThreshold ?? DEFAULT_FLOOD_THRESHOLD;

  // Skip-if-already-flood-snapped. Older marker (chroma_snapped: true but
  // no chroma_method or a different method) MUST trigger a fresh pass —
  // the previous threshold-30 leaked, so the on-disk pixels are wrong.
  const existingSidecar = await readSidecar(imagePath);
  if (existingSidecar?.extra?.chroma_method === METHOD) {
    return {
      imagePath,
      snappedPixels: 0,
      exactBefore: 0,
      exactAfter: 0,
      seedThreshold,
      floodThreshold,
      skipped: true,
    };
  }

  const st = await stat(imagePath);
  if (!st.isFile() || st.size === 0) {
    throw new Error(`chroma-snap: ${imagePath} missing or empty`);
  }

  const img = sharp(imagePath);
  const meta = await img.metadata();
  const width = meta.width;
  const height = meta.height;
  if (!width || !height) {
    throw new Error(`chroma-snap: ${imagePath} could not read dimensions`);
  }

  const { data, info } = await img
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });

  if (info.channels !== 4) {
    throw new Error(
      `chroma-snap: ${imagePath} expected 4 channels after ensureAlpha, got ${info.channels}`,
    );
  }

  const W = info.width;
  const H = info.height;
  const N = W * H;

  // Bitmap mask: 1 = in background set. Uint8Array initialises to 0.
  const mask = new Uint8Array(N);

  // Pre-count exact magenta before mutation.
  let exactBefore = 0;
  for (let i = 0, p = 0; i < data.length; i += 4, p++) {
    if (
      data[i] === TARGET_R &&
      data[i + 1] === TARGET_G &&
      data[i + 2] === TARGET_B
    ) {
      exactBefore++;
    }
  }

  // BFS queue: store flat pixel indices (0..N-1).
  // Sized for worst case (whole image is background); typed for speed.
  // Two cursors implement a ring-free FIFO since we only ever push and pop
  // from opposite ends of an ever-growing array.
  const queue = new Int32Array(N);
  let qHead = 0;
  let qTail = 0;

  function pixelDist(idx: number): number {
    const off = idx * 4;
    return manhattanFromMagenta(data[off], data[off + 1], data[off + 2]);
  }

  function trySeed(idx: number) {
    if (mask[idx]) return;
    if (pixelDist(idx) <= seedThreshold) {
      mask[idx] = 1;
      queue[qTail++] = idx;
    }
  }

  // Seed from all four edges.
  for (let x = 0; x < W; x++) {
    trySeed(x); // top row
    trySeed((H - 1) * W + x); // bottom row
  }
  for (let y = 0; y < H; y++) {
    trySeed(y * W); // left column
    trySeed(y * W + (W - 1)); // right column
  }

  // Flood-fill via BFS. 4-connectivity.
  while (qHead < qTail) {
    const idx = queue[qHead++];
    const x = idx % W;
    const y = (idx - x) / W;

    // Up
    if (y > 0) {
      const n = idx - W;
      if (!mask[n] && pixelDist(n) <= floodThreshold) {
        mask[n] = 1;
        queue[qTail++] = n;
      }
    }
    // Down
    if (y < H - 1) {
      const n = idx + W;
      if (!mask[n] && pixelDist(n) <= floodThreshold) {
        mask[n] = 1;
        queue[qTail++] = n;
      }
    }
    // Left
    if (x > 0) {
      const n = idx - 1;
      if (!mask[n] && pixelDist(n) <= floodThreshold) {
        mask[n] = 1;
        queue[qTail++] = n;
      }
    }
    // Right
    if (x < W - 1) {
      const n = idx + 1;
      if (!mask[n] && pixelDist(n) <= floodThreshold) {
        mask[n] = 1;
        queue[qTail++] = n;
      }
    }
  }

  // Apply mask: snap RGB to exact (255,0,255), preserve alpha.
  let snapped = 0;
  let exactAfter = 0;
  for (let p = 0; p < N; p++) {
    const off = p * 4;
    if (mask[p]) {
      const wasExact =
        data[off] === TARGET_R &&
        data[off + 1] === TARGET_G &&
        data[off + 2] === TARGET_B;
      if (!wasExact) {
        data[off] = TARGET_R;
        data[off + 1] = TARGET_G;
        data[off + 2] = TARGET_B;
        snapped++;
      }
      exactAfter++;
    } else {
      if (
        data[off] === TARGET_R &&
        data[off + 1] === TARGET_G &&
        data[off + 2] === TARGET_B
      ) {
        exactAfter++;
      }
    }
  }

  const outBuf = await sharp(data, {
    raw: { width: W, height: H, channels: 4 },
  })
    .png()
    .toBuffer();
  await writeFile(imagePath, outBuf);

  await patchSidecar(imagePath, {
    chroma_snapped: true,
    chroma_method: METHOD,
    chroma_seed_threshold: seedThreshold,
    chroma_flood_threshold: floodThreshold,
    chroma_snap_count: snapped,
  });

  return {
    imagePath,
    snappedPixels: snapped,
    exactBefore,
    exactAfter,
    seedThreshold,
    floodThreshold,
    skipped: false,
  };
}
