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
// The post-chroma stage runs BEFORE this stage, so the master-sheet input
// already has exact #FF00FF and the strips inherit it without any extra
// pass. No model calls. No vision payloads in the main agent.
//
// Idempotent: if all 5 strips and their sidecars already exist non-empty,
// this is a no-op.

import { stat } from "node:fs/promises";
import { join } from "node:path";
import sharp from "sharp";
import { writeMeta } from "../meta.ts";

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

async function existsNonEmpty(p: string): Promise<boolean> {
  try {
    const st = await stat(p);
    return st.isFile() && st.size > 0;
  } catch {
    return false;
  }
}

/**
 * Slice the 2400×3440 master sheet into 5 per-state 2400×688 strips.
 *
 * Returns the absolute paths of the 5 written strips, in canonical state
 * order: idle, walk, run, jump, crawl.
 *
 * Skips processing entirely if all 5 strips + sidecars already exist
 * non-empty (idempotent like chroma-snap).
 */
export async function sliceMasterSheet(
  masterSheetPath: string,
  tag: string,
  runDir: string,
): Promise<string[]> {
  const outPaths = STATES.map((s) => stripPath(runDir, tag, s));
  const sidecarPaths = outPaths.map((p) => `${p}.meta.json`);

  // Skip-if-all-exist: same contract as chroma-snap / image-helper.
  const force = process.env.STAGE_GEN_FORCE === "1";
  if (!force) {
    const allExist = (
      await Promise.all([...outPaths, ...sidecarPaths].map(existsNonEmpty))
    ).every(Boolean);
    if (allExist) {
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
  const ts = new Date().toISOString();
  await Promise.all(
    STATES.map(async (state, rowIndex) => {
      const top = rowIndex * ROW_H;
      const outPath = outPaths[rowIndex];
      await sharp(masterSheetPath)
        .extract({ left: 0, top, width: CANVAS_W, height: ROW_H })
        .png()
        .toFile(outPath);

      await writeMeta(outPath, {
        stage: "post-split",
        prompt: "",
        ts,
        extra: {
          source_master_sheet: masterSheetPath,
          source_row_index: rowIndex,
          state,
          dims: { width: CANVAS_W, height: ROW_H },
        },
      });
    }),
  );

  return outPaths;
}
