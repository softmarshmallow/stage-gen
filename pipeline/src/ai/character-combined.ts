// Character motion master sheet generator (Wave 3 / Wave B).
//
// PER-ROW STRATEGY (retry 2 of TC-051 / TC-050b / TC-050c):
// The single 2400×3440 5-row generation produced two persistent failures:
//   - jump row (row 4) contained zero airborne frames — model rendered
//     crouches in grid context.
//   - idle row (row 1) collapsed to 4 near-identical poses.
//   - rows 4-5 kneeling stances shrank the figure (cross-row scale drift).
//
// Root cause: a single prompt that has to describe 5 different motion
// states simultaneously dilutes per-state guidance and lets the model
// skip per-row specificity. The character-attack strip (TC-052) uses a
// single focused prompt and consistently produces 4 distinct phases.
//
// New approach: generate 5 independent 1×4 strips at 2400×688 each — same
// shape as character-attack — with one focused prompt per state, then
// composite them deterministically with sharp into the 2400×3440 master
// sheet. Each strip carries the same identity ref (character_concept) so
// scale-lock is an emergent property of identity preservation across
// strips, not a prompt rule the model has to enforce within one canvas.
//
// Inputs:
//   - layout prior: fixtures/image_gen_templates/character_template.png  (4×1 strip)
//   - identity ref: out/<tag>/character_concept_<tag>.png
//
// Output filename unchanged: character_<tag>_combined.png
// Sidecar records all 5 source strip paths and the composite step in extra.
//
// Reference order: layout template FIRST, identity ref SECOND. Same as
// character-attack.ts (the working pattern).

import { join } from "node:path";
import { readFile, writeFile, mkdir, stat } from "node:fs/promises";
import { dirname } from "node:path";
import sharp from "sharp";
import { generateImageAsset } from "./image-helper.ts";
import { snapChromaKey } from "../post/chroma-snap.ts";
import { writeMeta } from "../meta.ts";

const CANVAS_W = 2400;
const ROW_H = 688; // master-sheet row height (composite output: 5 × 688 = 3440)
const CANVAS_H = ROW_H * 5; // 3440

// Per-strip generation height — gpt-image-2 caps aspect ratio at 3:1, so
// the smallest legal height for a 2400-wide canvas is 800. We generate each
// strip at 2400×800, then crop the bottom (extra magenta floor band) down to
// 2400×688 before compositing. Character occupies y=80..620 — cropping the
// bottom 112 px is safely below the feet rail.
const GEN_H = 800;
const CROP_BOTTOM_PX = GEN_H - ROW_H; // 112 — sliced off after generation

// Per-cell rails — applied within the 2400×800 generation canvas. The
// composite uses the same head-top and feet-baseline rail offsets, so the
// crop-bottom step preserves the full character.
const HEAD_TOP_Y = 80;
const FEET_BOT_Y = 620;
const BODY_PX = FEET_BOT_Y - HEAD_TOP_Y; // 540
const FLOOR_BAND_PX = GEN_H - FEET_BOT_Y; // 180 — bottom band in the gen canvas

type State = "idle" | "walk" | "run" | "jump" | "crawl";
const STATES: State[] = ["idle", "walk", "run", "jump", "crawl"];

// Shared rail / canvas preamble reused across every per-row prompt.
function railPreamble(): string {
  return (
    `TWO reference images are provided:\n` +
    `  IMAGE 1 — LAYOUT TEMPLATE: a 4×1 grid on magenta with bright YELLOW grid lines. Each cell has a CYAN horizontal rail (head-top marker) and a single GREEN horizontal rail across the FULL ROW (feet baseline / ground line). The grey humanoid silhouette marks the body's height, width, and centre.\n` +
    `  IMAGE 2 — DESIGN REFERENCE: the character's turnaround. Match its design, proportions, colours, outfit, and rendering style EXACTLY across every frame. Use it for identity / colours / silhouette — do NOT borrow its scale or framing.\n\n` +
    `Render a strict 4×1 grid of equal cells (each 600×${GEN_H}), aligned 1:1 with the template's cells. Read order: left-to-right.\n\n` +
    `=== HARD PIXEL RAILS — APPLY TO ALL 4 CELLS ===\n` +
    `Within EVERY single cell (measuring from the cell's top edge):\n` +
    `  • HEAD TOP rail: y ≈ ${HEAD_TOP_Y} px from cell top. Top of hair / hat / ears sits ON this line.\n` +
    `  • FEET BOTTOM rail: y ≈ ${FEET_BOT_Y} px from cell top. Soles of feet / boots sit ON this line.\n` +
    `  • Standing body height between rails = ${BODY_PX} px. IDENTICAL across all 4 cells.\n` +
    `  • The bottom ${FLOOR_BAND_PX} px of every cell is a magenta floor band — NOTHING is painted there.\n` +
    `Side view, facing right, throughout the strip.\n` +
    `Background is solid magenta (#FF00FF) outside the character — chroma key, will be removed. EXACT colour, not a pinkish hue.\n` +
    `Do NOT render the silhouettes, the cyan/green rails, or the yellow grid in the output. No labels, no row dividers, no borders, no frame numbers, no ground shadow.\n\n`
  );
}

// Per-state focused motion spec. Each is intentionally narrow — one
// motion only, no grid context, no cross-row scale negotiation.
const STATE_SPEC: Record<State, { title: string; spec: string; railNote?: string }> = {
  idle: {
    title: "IDLE breath cycle",
    spec:
      `Subtle breath cycle in 4 frames — the ONLY motion is breathing.\n` +
      `  Frame 1: chest neutral (resting), shoulders at neutral height.\n` +
      `  Frame 2: shoulders rise slightly (~6-10 px), chest beginning to expand.\n` +
      `  Frame 3: chest expanded peak, shoulders at highest point, head may bob up ~4 px.\n` +
      `  Frame 4: shoulders descending back toward neutral, chest deflating.\n` +
      `Feet PLANTED on the green rail in ALL 4 frames — feet do NOT lift, do NOT step, do NOT shuffle. Arms hang at sides, may sway gently with the breath. Visible delta between adjacent frames in shoulder/chest height — the strip must NOT collapse to 4 identical poses.`,
  },
  walk: {
    title: "WALK cycle",
    spec:
      `One full walk cycle in 4 frames — standard alternating-leg gait.\n` +
      `  Frame 1: LEFT foot forward contact (heel just landed), right foot pushing off behind.\n` +
      `  Frame 2: LEFT foot passing under body (planted, weight transfer), right leg swinging forward.\n` +
      `  Frame 3: RIGHT foot forward contact (heel just landed), left foot pushing off behind.\n` +
      `  Frame 4: RIGHT foot passing under body (planted, weight transfer), left leg swinging forward.\n` +
      `Opposite arm swing (right arm forward when left leg forward, etc.). Slight head bob. Feet stay near the green rail; at most one foot lifts a few px during step. Loops cleanly (frame 4 → frame 1).`,
  },
  run: {
    title: "RUN cycle",
    spec:
      `One full run cycle in 4 frames — full sprint, exaggerated stride.\n` +
      `  Frame 1: LEFT foot driving forward at peak knee-lift, right leg extended back.\n` +
      `  Frame 2: BOTH FEET BRIEFLY OFF GROUND — airborne mid-stride, body extended.\n` +
      `  Frame 3: RIGHT foot driving forward at peak knee-lift, left leg extended back.\n` +
      `  Frame 4: BOTH FEET BRIEFLY OFF GROUND — airborne mid-stride, body extended.\n` +
      `Forward lean throughout. Bent arms swinging hard front-to-back, opposite to legs. Cloak / hair trailing behind. Feet may lift off the green rail mid-stride but the body height between head and trailing foot stays at the SAME ${BODY_PX}-px scale. Loops cleanly.`,
    railNote:
      `Run row exception: feet may lift OFF the green rail in airborne frames; HEAD TOP must still be at y=${HEAD_TOP_Y} (do not let head rise above the cyan rail).`,
  },
  jump: {
    title: "JUMP — 4 distinct phases",
    spec:
      `Four DISTINCT jump phases — must read clearly and unambiguously as one jump arc:\n` +
      `  Frame 1 — ANTICIPATION CROUCH: knees bent deep, hips lowered, arms swung BACK behind body, weight loaded. Feet ON the green rail.\n` +
      `  Frame 2 — PUSH-OFF: legs EXTENDING upward, arms SWINGING UP, body rising, feet JUST LEAVING the green rail.\n` +
      `  Frame 3 — APEX AIRBORNE: character clearly OFF THE GROUND. Feet visibly ABOVE the green rail (feet rail-cross is REQUIRED in this frame). Body extended or legs tucked, arms RAISED overhead. This is the airborne peak — without this frame the strip is wrong.\n` +
      `  Frame 4 — LANDING IMPACT: feet returning to the green rail, knees BENT to absorb impact, arms forward / out for balance, body slightly compressed.\n` +
      `Critical: frame 3 MUST show the feet clear of the green rail — if you draw a crouch in frame 3, the strip is wrong. Each of the 4 frames must be visually distinct from the other 3.`,
    railNote:
      `Jump apex (frame 3) is the ONLY allowed feet-above-rail moment in this whole sheet. HEAD TOP must STILL be at y=${HEAD_TOP_Y} (do not let head rise above the cyan rail in any frame, apex included).`,
  },
  crawl: {
    title: "CRAWL — low horizontal stance",
    spec:
      `LOW HORIZONTAL CRAWL throughout — all 4 frames are a hands-and-knees crawl, NOT a crouch-walk, NOT an upright pose.\n` +
      `  Body orientation: torso roughly HORIZONTAL, parallel to the ground. Hands and knees on the ground. Head looking forward (slightly up).\n` +
      `  Frame 1: RIGHT hand + LEFT knee forward (diagonal pair planted), left hand + right knee trailing.\n` +
      `  Frame 2: passing — limbs swapping; right hand and left knee pushing back, left hand and right knee swinging forward.\n` +
      `  Frame 3: LEFT hand + RIGHT knee forward (opposite diagonal pair planted), right hand + left knee trailing.\n` +
      `  Frame 4: passing — limbs swapping back toward the frame-1 configuration. Loops cleanly.\n` +
      `The character's HEAD TOP in this strip is BELOW the cyan rail (because the body is folded low) — that is correct, do NOT enlarge the character to fill the gap. Hands and knees rest ON the green rail. NO upright frames anywhere.`,
  },
};

function buildStripPrompt(state: State): string {
  const spec = STATE_SPEC[state];
  return (
    `Sprite ${spec.title} animation strip for a 2D platformer character.\n` +
    railPreamble() +
    `=== MOTION SPEC (${state.toUpperCase()}) ===\n` +
    spec.spec +
    `\n\n` +
    (spec.railNote
      ? `=== RAIL EXCEPTION ===\n${spec.railNote}\n\n`
      : ``) +
    `=== ANCHORING + RENDER RULES ===\n` +
    `In every cell, replace the gray silhouette with the character in the correct pose. Rails are HARD limits:\n` +
    `  - CYAN top rail = TOP of head/hair. Do NOT paint character pixels above the cyan line.\n` +
    `  - GREEN feet rail = SOLES of feet. Do NOT paint character pixels below the green line in any frame.\n` +
    `  - Horizontal centre of the silhouette = character's body centre.\n` +
    `  - The narrow magenta band below the green feet rail in every cell MUST remain solid magenta — no boots, no feet, no shadow, no toes poking through.\n` +
    `Output canvas: ${CANVAS_W}×${GEN_H} (3:1, sliced as 4 cells of 600×${GEN_H}).`
  );
}

export interface CharacterCombinedArgs {
  prompt: string;
  tag: string;
  runDir: string;
  model: string;
  /** Path to fixtures/image_gen_templates/character_template.png (the 4×1 strip prior). */
  layoutTemplatePath: string;
  /** Path to character_concept_<tag>.png (identity ref). */
  characterConceptPath: string;
}

export interface CharacterCombinedResult {
  imagePath: string;
  metaPath: string;
  stripPaths: Record<State, string>;
  /** Per-strip wall-clock generation duration in ms (best-effort). */
  stripTimingsMs: Record<State, number>;
}

/**
 * Generate the 5 per-state strips in parallel, then composite into the
 * 2400×3440 master sheet via sharp. Apply chroma-snap to the composite.
 */
export async function generateCharacterCombined(
  args: CharacterCombinedArgs,
): Promise<CharacterCombinedResult> {
  const {
    prompt,
    tag,
    runDir,
    model,
    layoutTemplatePath,
    characterConceptPath,
  } = args;

  const outPath = join(runDir, `character_${tag}_combined.png`);
  const metaPath = `${outPath}.meta.json`;

  // Skip-if-exists: same contract as image-helper. If the composite + sidecar
  // already exist non-empty, return without re-running.
  const force = process.env.STAGE_GEN_FORCE === "1";
  if (!force) {
    try {
      const [imgStat, metaStat] = await Promise.all([stat(outPath), stat(metaPath)]);
      if (imgStat.isFile() && imgStat.size > 0 && metaStat.isFile() && metaStat.size > 0) {
        // Best-effort reconstruction of strip paths for the return value.
        const stripPaths = Object.fromEntries(
          STATES.map((s) => [s, join(runDir, `character_${tag}_combined_strip_${s}.png`)]),
        ) as Record<State, string>;
        const stripTimingsMs = Object.fromEntries(
          STATES.map((s) => [s, 0]),
        ) as Record<State, number>;
        return { imagePath: outPath, metaPath, stripPaths, stripTimingsMs };
      }
    } catch {
      // fall through to generate
    }
  }

  await mkdir(dirname(outPath), { recursive: true });

  // Per-strip generation. Each is its own retry-wrapped image-gen call via
  // generateImageAsset (which already handles retries, sidecar, dim check).
  const stripTimings: Record<string, number> = {};
  const stripResults = await Promise.all(
    STATES.map(async (state) => {
      const stripOut = join(runDir, `character_${tag}_combined_strip_${state}.png`);
      const t0 = Date.now();
      const result = await generateImageAsset({
        stage: `character-master-strip-${state}`,
        userPrompt: prompt,
        promptText: buildStripPrompt(state),
        // Order matters — layout FIRST, identity SECOND (matches character-attack).
        refs: [layoutTemplatePath, characterConceptPath],
        outPath: stripOut,
        width: CANVAS_W,
        height: GEN_H,
        model,
        extra: {
          state,
          rows: 1,
          cols: 4,
          cellW: CANVAS_W / 4,
          cellH: GEN_H,
          headTopY: HEAD_TOP_Y,
          feetBotY: FEET_BOT_Y,
          gen_height: GEN_H,
          composite_row_height: ROW_H,
          part_of: `character_${tag}_combined.png`,
        },
      });
      stripTimings[state] = Date.now() - t0;
      // Snap each strip individually so the composite inputs have exact magenta;
      // chroma-snap is idempotent and the post-stage will skip-mark via sidecar.
      await snapChromaKey(stripOut);
      return { state, stripPath: result.imagePath };
    }),
  );

  // Deterministic vertical composite via sharp. Each strip is generated at
  // 2400×800 (gpt-image-2 3:1 aspect cap), then cropped to 2400×688 (the
  // master-sheet row height) by trimming CROP_BOTTOM_PX from the bottom.
  // Character bodies live at y=80..620 so the trimmed band is pure magenta.
  // Cropped strips stack at y=0,688,1376,2064,2752.
  const stripBuffers = await Promise.all(
    stripResults.map(async (r) => ({
      state: r.state,
      buf: await sharp(await readFile(r.stripPath))
        .extract({ left: 0, top: 0, width: CANVAS_W, height: ROW_H })
        .png()
        .toBuffer(),
    })),
  );
  // Order by STATES (Promise.all preserves order, but be explicit).
  const ordered = STATES.map((s) => {
    const found = stripBuffers.find((sb) => sb.state === s);
    if (!found) throw new Error(`character-combined: missing strip for state ${s}`);
    return found;
  });

  const composite = await sharp({
    create: {
      width: CANVAS_W,
      height: CANVAS_H,
      channels: 4,
      background: { r: 255, g: 0, b: 255, alpha: 1 },
    },
  })
    .composite(
      ordered.map((sb, idx) => ({
        input: sb.buf,
        top: idx * ROW_H,
        left: 0,
      })),
    )
    .png()
    .toBuffer();

  await writeFile(outPath, composite);

  const stripPaths = Object.fromEntries(
    stripResults.map((r) => [r.state, r.stripPath]),
  ) as Record<State, string>;
  const stripTimingsMs = Object.fromEntries(
    STATES.map((s) => [s, stripTimings[s] ?? 0]),
  ) as Record<State, number>;

  await writeMeta(outPath, {
    stage: "character-master",
    prompt,
    ts: new Date().toISOString(),
    model,
    refs: [layoutTemplatePath, characterConceptPath],
    params: {
      size: `${CANVAS_W}x${CANVAS_H}` as const,
      moderation: "low",
    },
    extra: {
      composite_strategy: "per-row",
      states: STATES,
      rows: 5,
      cols: 4,
      cellW: CANVAS_W / 4,
      cellH: ROW_H,
      headTopY: HEAD_TOP_Y,
      feetBotY: FEET_BOT_Y,
      width: CANVAS_W,
      height: CANVAS_H,
      bytes: composite.length,
      strip_gen_height: GEN_H,
      strip_crop_bottom_px: CROP_BOTTOM_PX,
      strip_paths: stripPaths,
      strip_timings_ms: stripTimingsMs,
      composite_offsets_y: STATES.map((_, i) => i * ROW_H),
    },
  });

  // Snap the composite as well — defensive; the chroma-snap post-stage will
  // see the sidecar marker after this and skip a redundant pass.
  await snapChromaKey(outPath);

  return { imagePath: outPath, metaPath, stripPaths, stripTimingsMs };
}
