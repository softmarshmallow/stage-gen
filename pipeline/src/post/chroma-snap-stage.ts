// post-chroma stage runner — walks the per-tag runDir, picks chroma-keyed
// PNGs per the asset contract, and snaps each to exact #FF00FF.
//
// What's chroma-keyed (per docs/spec/asset-contracts.md):
//   - Parallax layers EXCEPT the opaque backdrop (sidecar extra.opaque===true)
//   - Tileset (magenta = sky region in the wireframe)
//   - Character concept turnaround (poses on magenta)
//   - Character motion master sheet (cells on magenta + cyan/green rails)
//   - Character attack strip
//   - Per-mob concept turnarounds
//   - Per-mob idle + hurt strips
//   - Obstacle sheets
//   - Items sheet
//   - Inventory panel (magenta surrounds outer panel)
//   - Portal pair
//
// What's NOT chroma-keyed (skipped):
//   - concept_<tag>.png — painterly opaque, no chroma key
//   - The opaque parallax layer — full-bleed skybox
//
// Ordering: this stage runs AFTER Wave B (so Wave B outputs exist) and
// BEFORE the master-sheet slicer, so the slicer downstream operates on
// already-snapped pixels.

import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import { snapChromaKey, type SnapChromaResult } from "./chroma-snap.ts";

export interface PostChromaArgs {
  /** Per-tag run directory. */
  runDir: string;
  /** Tag (used to recognize <tag>-prefixed files). */
  tag: string;
  /** Distance threshold (default 30). */
  threshold?: number;
}

export interface PostChromaSummary {
  processed: SnapChromaResult[];
  skipped: string[];
  /** Files explicitly skipped because they are NOT chroma-keyed. */
  notChromaKeyed: string[];
}

/** Decide whether a file in the run dir is a chroma-keyed sprite asset.
 *  Returns {process: true} or {process: false, reason}.
 *
 *  Filename-based first pass; layer files cross-checked against their
 *  sidecar's extra.opaque flag.
 */
async function classify(
  fileName: string,
  runDir: string,
  tag: string,
): Promise<{ process: boolean; reason?: string }> {
  // Only consider PNGs.
  if (!fileName.endsWith(".png")) {
    return { process: false, reason: "not png" };
  }

  // World concept — painterly, no chroma key.
  if (fileName === `concept_${tag}.png`) {
    return { process: false, reason: "concept (painterly opaque)" };
  }

  // Parallax layers — opaque backdrop is full-bleed sky, skip; all other
  // layers carry magenta chroma key.
  if (fileName.startsWith(`layer_${tag}_`)) {
    const sidecarPath = join(runDir, `${fileName}.meta.json`);
    try {
      const raw = await readFile(sidecarPath, "utf8");
      const sidecar = JSON.parse(raw);
      if (sidecar?.extra?.opaque === true) {
        return { process: false, reason: "opaque parallax backdrop" };
      }
    } catch {
      // No sidecar — fall through and process to be safe (better to snap
      // than leave drift in a chroma-keyed sprite).
    }
    return { process: true };
  }

  // Every other recognized chroma-keyed family.
  const chromaPrefixes = [
    `tileset_${tag}`,
    `character_concept_${tag}`,
    `character_${tag}_combined`,
    `character_${tag}_attack`,
    `mob_concept_${tag}_`,
    `mob_${tag}_`, // catches both _idle and _hurt
    `obstacles_${tag}_`,
    `items_${tag}`,
    `inventory_${tag}`,
    `portal_${tag}`,
  ];
  for (const p of chromaPrefixes) {
    if (fileName.startsWith(p)) return { process: true };
  }

  return { process: false, reason: "unrecognized" };
}

export async function runPostChroma(args: PostChromaArgs): Promise<PostChromaSummary> {
  const { runDir, tag, threshold } = args;
  const entries = await readdir(runDir);

  const processed: SnapChromaResult[] = [];
  const skipped: string[] = [];
  const notChromaKeyed: string[] = [];

  for (const entry of entries) {
    const decision = await classify(entry, runDir, tag);
    if (!decision.process) {
      if (entry.endsWith(".png")) notChromaKeyed.push(entry);
      continue;
    }
    const fullPath = join(runDir, entry);
    const result = await snapChromaKey(fullPath, { threshold });
    if (result.skipped) {
      skipped.push(entry);
    } else {
      processed.push(result);
    }
  }

  return { processed, skipped, notChromaKeyed };
}
