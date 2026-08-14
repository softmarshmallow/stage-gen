// Deterministic master-sheet slicer (Phase 5 / TC-060 / TC-061).
//
// The Wave-3 character master sheet (`character_<tag>_combined.png`) is a
// 2400×3440 canvas laid out as 5 rows × 4 columns: idle, walk, run, jump,
// crawl (top to bottom). The runtime loads animation strips by state, one
// 2400×688 strip per state — see docs/spec/asset-contracts.md "character
// motion master sheet".
//
// sliceMasterSheet() does a single CPU pass over the master sheet: 5 sharp
// .extract() calls write 5 per-state strips with the contracted filename
// pattern character_<tag>-fromcombined_<state>.png. Each output gets a
// reproducibility sidecar recording the source sheet, row index, state, and
// dims.
//
// The master-sheet input is already a canonical transparent PNG, and the
// strips inherit its alpha without another provider call.
//
// Idempotent: if all 5 strips and their sidecars already exist non-empty,
// this is a no-op.

import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import sharp from "sharp";
import { writeArtifactWithProvenance } from "@stage-gen/core";
import type { TransparencyMode } from "../../../../src/config.ts";

const CANVAS_W = 2400;
const CANVAS_H = 3440;
const ROW_H = 688; // 5 × 688 = 3440

type State = "idle" | "walk" | "run" | "jump" | "crawl";
const STATES: State[] = ["idle", "walk", "run", "jump", "crawl"];

function stripPath(runDir: string, tag: string, state: State): string {
  // Contract: character_<tag>-fromcombined_<state>.png — note the dash and
  // "fromcombined" segment. Exact contract per TC-060.
  return join(runDir, `character_${tag}-fromcombined_${state}.png`);
}

/**
 * Slice the 2400×3440 master sheet into 5 per-state 2400×688 strips.
 *
 * Returns the absolute paths of the 5 written strips, in canonical state
 * order: idle, walk, run, jump, crawl.
 *
 * Skips processing entirely if all 5 strips + sidecars already exist
 * valid for the requested mode and current source hash.
 */
export async function sliceMasterSheet(
  masterSheetPath: string,
  tag: string,
  runDir: string,
  transparencyMode: TransparencyMode,
): Promise<string[]> {
  const outPaths = STATES.map((s) => stripPath(runDir, tag, s));
  const masterBytes = new Uint8Array(await readFile(masterSheetPath));
  const masterSha256 = createHash("sha256").update(masterBytes).digest("hex");

  // Cache identity includes mode, current source hash, and artifact digest.
  const force = process.env.STAGE_GEN_FORCE === "1";
  if (!force) {
    const allValid = (
      await Promise.all(
        outPaths.map((path) =>
          validCachedSlice(path, transparencyMode, masterSha256),
        ),
      )
    ).every(Boolean);
    if (allValid) {
      return outPaths;
    }
  }

  // Confirm input dims match the contract before slicing.
  const meta = await sharp(masterSheetPath).metadata();
  if (meta.width !== CANVAS_W || meta.height !== CANVAS_H) {
    throw new Error(
      `master-sheet-slicer: ${masterSheetPath} expected ${CANVAS_W}×${CANVAS_H}, got ${meta.width}×${meta.height}`,
    );
  }

  // Five extracts, one per row. sharp.extract() is a deterministic crop —
  // no resampling, no recompression beyond the PNG re-encode.
  await Promise.all(
    STATES.map(async (state, rowIndex) => {
      const top = rowIndex * ROW_H;
      const outPath = outPaths[rowIndex];
      const bytes = new Uint8Array(
        await sharp(masterBytes)
        .extract({ left: 0, top, width: CANVAS_W, height: ROW_H })
        .png()
          .toBuffer(),
      );
      const alpha = await alphaFacts(bytes);
      const outputSha256 = createHash("sha256").update(bytes).digest("hex");
      await writeArtifactWithProvenance(
        outPath,
        { bytes, mediaType: "image/png" },
        {
          provider: "local",
          model: "deterministic-master-sheet-slice",
          seed: null,
          prompt: "slice canonical transparent character master sheet",
          refs: [masterSheetPath],
          inputs: [
            {
              ref: masterSheetPath,
              source: "reference",
              sha256: masterSha256,
              bytes: masterBytes.length,
              media_type: "image/png",
            },
          ],
          params: {
            stage: "post-split",
            transparency: {
              mode: transparencyMode,
              processor: "deterministic-png-slice",
              source_path: masterSheetPath,
              source_sha256: masterSha256,
              output_sha256: outputSha256,
            },
            metadata: {
              source_master_sheet: masterSheetPath,
              source_row_index: rowIndex,
              state,
              dims: { width: CANVAS_W, height: ROW_H },
            },
          },
          validation: {
            transparency_mode: transparencyMode,
            dimensions_preserved: true,
            output_width: CANVAS_W,
            output_height: ROW_H,
            alpha_nontrivial: true,
            transparent_pixels: alpha.transparentPixels,
            nontransparent_pixels: alpha.nontransparentPixels,
            output_sha256: outputSha256,
          },
          component: { name: "@stage-gen/stage-gen", version: "0.0.0" },
          tool: { name: "sharp-png-slice", version: sharp.versions.sharp },
          attempts: 1,
        },
      );
    }),
  );

  return outPaths;
}

async function validCachedSlice(
  path: string,
  mode: TransparencyMode,
  sourceSha256: string,
): Promise<boolean> {
  try {
    const [bytes, rawSidecar] = await Promise.all([
      readFile(path),
      readFile(`${path}.meta.json`, "utf8"),
    ]);
    const sidecar: unknown = JSON.parse(rawSidecar);
    if (!isRecord(sidecar) || !isRecord(sidecar.artifact) || !isRecord(sidecar.params)) {
      return false;
    }
    const transparency = sidecar.params.transparency;
    return (
      isRecord(transparency) &&
      transparency.mode === mode &&
      transparency.source_sha256 === sourceSha256 &&
      sidecar.artifact.sha256 === createHash("sha256").update(bytes).digest("hex")
    );
  } catch {
    return false;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

async function alphaFacts(
  bytes: Uint8Array,
): Promise<{ transparentPixels: number; nontransparentPixels: number }> {
  const { data, info } = await sharp(bytes, { failOn: "error" })
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
  if (info.channels !== 4) throw new Error("master-sheet slice must be RGBA");
  let transparentPixels = 0;
  let nontransparentPixels = 0;
  for (let offset = 3; offset < data.length; offset += 4) {
    if (data[offset] < 255) transparentPixels += 1;
    if (data[offset] > 0) nontransparentPixels += 1;
  }
  if (transparentPixels === 0 || nontransparentPixels === 0) {
    throw new Error("master-sheet slice must have nontrivial alpha");
  }
  return { transparentPixels, nontransparentPixels };
}
