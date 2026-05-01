// Deterministic chroma-snap post-processor (Phase 5 / TC-042b).
//
// gpt-image-2 outputs drift the supposed-magenta chroma-key background
// from exact #FF00FF (255, 0, 255) to clusters like (243, 3-12, 230-242).
// The asset contract (see docs/spec/asset-contracts.md "chroma-key") is
// EXACT magenta — runtime keying without tolerance fails on the drifted
// pixels.
//
// snapChromaKey() does a single CPU pass over a PNG: any pixel whose RGB
// sits within `threshold` (Manhattan distance, default 30) of (255, 0, 255)
// is rewritten to exact (255, 0, 255). Idempotent — a second call is a
// no-op because the snapped pixels are already at distance 0.
//
// The function:
//   - reads the file via sharp (raw RGBA),
//   - rewrites in place,
//   - touches the sidecar with extra.chroma_snapped: true and the
//     threshold used so a re-run can skip cheaply.
//
// No model calls. No vision payloads in the main agent.

import { readFile, writeFile, stat } from "node:fs/promises";
import sharp from "sharp";

export interface SnapChromaOptions {
  /** Manhattan-distance threshold (default 30). Pixels within this distance
   *  of (255, 0, 255) snap to exact magenta. ~30 catches the observed
   *  (243, 0-15, 220-255) drift cluster but leaves stylistic pinks/reds
   *  inside sprites untouched. */
  threshold?: number;
}

export interface SnapChromaResult {
  /** Absolute path of the processed PNG. */
  imagePath: string;
  /** Number of pixels that were snapped to exact (255,0,255) during this call. */
  snappedPixels: number;
  /** Number of pixels already at exact (255,0,255) before the call. */
  exactBefore: number;
  /** Number of pixels at exact (255,0,255) after the call. */
  exactAfter: number;
  /** Threshold used. */
  threshold: number;
  /** True if the file was already marked snapped in its sidecar and processing
   *  was skipped. */
  skipped: boolean;
}

const TARGET_R = 255;
const TARGET_G = 0;
const TARGET_B = 255;
const DEFAULT_THRESHOLD = 30;

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
  patch: { chroma_snapped: true; chroma_snap_threshold: number; chroma_snap_count?: number },
): Promise<void> {
  const sidecarPath = `${imagePath}.meta.json`;
  let payload: any;
  try {
    const raw = await readFile(sidecarPath, "utf8");
    payload = JSON.parse(raw);
  } catch {
    // No sidecar — write a minimal one. Pipeline always writes one for image
    // assets, so this is the cold-start / orphaned case.
    payload = { stage: "post-chroma", ts: new Date().toISOString() };
  }
  payload.extra = { ...(payload.extra ?? {}), ...patch };
  await writeFile(sidecarPath, JSON.stringify(payload, null, 2) + "\n", "utf8");
}

/**
 * Snap near-magenta pixels in a PNG to exact #FF00FF.
 *
 * Idempotent. In-place. Updates the sidecar with chroma_snapped marker.
 * If the sidecar already says extra.chroma_snapped === true, this is a
 * no-op (returns skipped: true) so re-runs stay cheap.
 */
export async function snapChromaKey(
  imagePath: string,
  options: SnapChromaOptions = {},
): Promise<SnapChromaResult> {
  const threshold = options.threshold ?? DEFAULT_THRESHOLD;

  // Skip-if-already-snapped — aligns with the skip-if-exists philosophy in
  // image-helper.ts. A re-run shouldn't pay the I/O cost.
  const existingSidecar = await readSidecar(imagePath);
  if (existingSidecar?.extra?.chroma_snapped === true) {
    return {
      imagePath,
      snappedPixels: 0,
      exactBefore: 0,
      exactAfter: 0,
      threshold,
      skipped: true,
    };
  }

  // Confirm the file exists and is non-empty.
  const st = await stat(imagePath);
  if (!st.isFile() || st.size === 0) {
    throw new Error(`chroma-snap: ${imagePath} missing or empty`);
  }

  // Decode to raw RGBA. sharp() ensures alpha channel exists (4 channels).
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

  // Single linear pass. Manhattan distance is fine for this — magenta is at
  // a corner of the RGB cube and the drift cluster is tight.
  let snapped = 0;
  let exactBefore = 0;
  let exactAfter = 0;
  for (let i = 0; i < data.length; i += 4) {
    const r = data[i];
    const g = data[i + 1];
    const b = data[i + 2];
    const wasExact = r === TARGET_R && g === TARGET_G && b === TARGET_B;
    if (wasExact) {
      exactBefore++;
      exactAfter++;
      continue;
    }
    const dist = Math.abs(r - TARGET_R) + Math.abs(g - TARGET_G) + Math.abs(b - TARGET_B);
    if (dist <= threshold) {
      data[i] = TARGET_R;
      data[i + 1] = TARGET_G;
      data[i + 2] = TARGET_B;
      // alpha preserved
      snapped++;
      exactAfter++;
    }
  }

  // Re-encode to PNG and overwrite in place. Setting alphaQuality maxes
  // alpha fidelity; compressionLevel default (6) is fine.
  const outBuf = await sharp(data, {
    raw: { width: info.width, height: info.height, channels: 4 },
  })
    .png()
    .toBuffer();
  await writeFile(imagePath, outBuf);

  await patchSidecar(imagePath, {
    chroma_snapped: true,
    chroma_snap_threshold: threshold,
    chroma_snap_count: snapped,
  });

  return {
    imagePath,
    snappedPixels: snapped,
    exactBefore,
    exactAfter,
    threshold,
    skipped: false,
  };
}
