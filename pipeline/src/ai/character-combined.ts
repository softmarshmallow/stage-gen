// Character motion master sheet generator (Wave 3 / Wave B).
// 5 rows × 4 columns of motion frames on chroma magenta, 2400×3440.
// Largest call in the pipeline (≈8.26 Mpx, just under the model cap).
//
// Inputs:
//   - layout prior: fixtures/image_gen_templates/character_template_combined.png
//   - identity ref: out/<tag>/character_concept_<tag>.png
//
// Rows (top → bottom): idle, walk, run, jump, crawl. 4 frames each.
//
// Reference order: layout template FIRST, identity ref SECOND. Per
// docs/tech/gpt-image-2.md the model honours `images: [...]` in order
// and the first image tends to dominate compositional / spatial framing.
// We need the rails (cell geometry, head-top, feet-baseline) to dominate
// here — TC-051 fails when scale drifts row-to-row, so layout primacy is
// load-bearing. Identity is preserved by the explicit "match design
// EXACTLY" prompt + the second ref carrying the colours/silhouette.

import { join } from "node:path";
import { generateImageAsset } from "./image-helper.ts";

const CANVAS_W = 2400;
const CANVAS_H = 3440;

// Grid math — every prompt callout below is derived from these constants
// so the prompt and the runtime slicer share a single source of truth.
const COLS = 4;
const ROWS = 5;
const CELL_W = CANVAS_W / COLS; // 600
const CELL_H = CANVAS_H / ROWS; // 688

// Per-cell rails (pixels from the cell's TOP edge):
//   - HEAD_TOP_Y: top of head/hair must sit at this line in EVERY cell.
//   - FEET_BOT_Y: soles of feet must sit at this line in EVERY cell.
// Body height between rails = FEET_BOT_Y - HEAD_TOP_Y = 540 px.
// Margin above head = 80 px; magenta floor band below feet = 68 px.
// These numbers are repeated in the prompt so the model sees the rails
// as hard constraints, not just a soft template hint.
const HEAD_TOP_Y = 80;
const FEET_BOT_Y = 620;
const BODY_PX = FEET_BOT_Y - HEAD_TOP_Y; // 540
const FLOOR_BAND_PX = CELL_H - FEET_BOT_Y; // 68

function buildPrompt(): string {
  return (
    `Sprite animation MASTER SHEET for a single 2D platformer character.\n` +
    `TWO reference images are provided, in this exact order:\n` +
    `  IMAGE 1 — LAYOUT TEMPLATE (PRIMARY / GEOMETRY): a 4×5 grid of equal cells on magenta with bright YELLOW grid lines. Each cell contains a gray HUMANOID silhouette with a CYAN top rail (head height) and a GREEN feet rail spanning the full row width (feet baseline). This image dictates EXACT cell geometry, character scale, and per-cell rail positions. Honour it 1:1.\n` +
    `  IMAGE 2 — DESIGN REFERENCE (IDENTITY): the character's turnaround. Match its design, proportions, colours, outfit, and rendering style EXACTLY across every frame. Use it ONLY for identity/styling — do NOT borrow its scale or framing.\n\n` +
    `Output canvas: ${CANVAS_W}×${CANVAS_H}. Strict ${COLS}-column × ${ROWS}-row grid, cells ${CELL_W}×${CELL_H} px each, aligned 1:1 with the template's cells. Each ROW is a different motion state. Each COLUMN within a row is the next frame in that motion's cycle, read left-to-right.\n\n` +
    `=== HARD PIXEL RAILS — APPLY TO ALL 20 CELLS, NO EXCEPTIONS ===\n` +
    `Within EVERY single cell (measuring from the cell's own top edge):\n` +
    `  • HEAD TOP rail: y ≈ ${HEAD_TOP_Y} px from cell top. Top of hair / hat / ears sits ON this line.\n` +
    `  • FEET BOTTOM rail: y ≈ ${FEET_BOT_Y} px from cell top. Soles of feet / boots sit ON this line.\n` +
    `  • Standing body height between rails = ${BODY_PX} px. This number is IDENTICAL across all 20 cells.\n` +
    `  • The bottom ${FLOOR_BAND_PX} px of every cell is a magenta floor band — NOTHING is painted there (no shadow, no toes, no dust).\n` +
    `These rails are the SAME in row 1 (idle), row 2 (walk), row 3 (run), row 4 (jump), row 5 (crawl). The cyan/green rails in IMAGE 1 mark exactly these positions — do not deviate.\n\n` +
    `=== SCALE LOCK — NO ROW-TO-ROW SCALING ===\n` +
    `The character's standing body height is ${BODY_PX} px in every row. Do NOT scale the character up or down between rows. Idle stance and jump apex use the SAME character height. Run row is NOT taller. Crawl row is NOT shorter — the crawl pose is the SAME body, just deeply folded; head size, limb thickness, and overall body mass are identical to row 1. If a motion would push pixels outside the rails, CROP/CLIP the motion or fold the body smaller — never rescale the character.\n\n` +
    `=== PER-ROW FEET-BASELINE LOCK ===\n` +
    `Within every row, all 4 frames share the SAME feet baseline at y=${FEET_BOT_Y} from each cell's top. The character does not drift up or down between adjacent frames in the same row. The only row where feet may temporarily LIFT off the rail is row 4 (jump) — see jump rules below.\n\n` +
    `=== ROW-BY-ROW MOTION SPEC ===\n` +
    `Row 1 — IDLE: subtle breathing + weight shift. Feet PLANTED on the green rail in ALL 4 frames; feet do NOT lift. Motion is breath rise/fall in chest+shoulders, slight head bob (≤10 px), arms swaying gently at sides. Visible delta between adjacent frames in shoulder/chest height. Loops cleanly.\n` +
    `Row 2 — WALK: alternating legs forward, gentle opposite arm swing, slight head bob. Both feet stay near the green rail — at most one foot lifts a few px during step. Loops cleanly.\n` +
    `Row 3 — RUN: full sprint, knees driven high, bent arms swinging hard front-to-back, body leaning slightly forward. Feet may lift off the rail mid-stride but body height between head and trailing foot stays the SAME ${BODY_PX} px scale. Loops cleanly.\n` +
    `Row 4 — JUMP: four DISTINCT phases, must read clearly:\n` +
    `  Frame 1 ANTICIPATION CROUCH: knees bent, hips lowered, feet on green rail.\n` +
    `  Frame 2 PUSH-OFF: legs extending, body rising, feet just leaving the rail.\n` +
    `  Frame 3 AIRBORNE APEX: character clearly OFF THE GROUND, legs tucked or extended; FEET MAY GO ABOVE the green rail (this is the only allowed rail crossing) but the HEAD TOP must STILL be at y=${HEAD_TOP_Y} (do not let head rise above the cyan rail).\n` +
    `  Frame 4 LANDING IMPACT: feet returning to the green rail, knees absorbing, body slightly compressed.\n` +
    `Row 5 — CRAWL: ALL 4 frames are LOW HORIZONTAL crouch — knees deeply bent, body lowered to roughly half standing height, head ducked. Hands near knees or held low. NO upright frames anywhere in this row. Same orientation across all 4 cells; alternating crouched-step limb cycle. The character's HEAD TOP in this row is BELOW the cyan rail (because the body is folded low) but the magenta band above the head fills to the rail — do not enlarge the character to fill the gap. Feet on the green rail. Loops cleanly.\n\n` +
    `=== ANCHORING + RENDER RULES ===\n` +
    `In every cell, replace the gray silhouette with the character in the correct pose. Rails are HARD limits:\n` +
    `  - CYAN top rail = TOP of head/hair. Do NOT paint any character pixels above the cyan line (jump apex included — head stays inside the cell).\n` +
    `  - GREEN feet rail = SOLES of feet. Do NOT paint character pixels below the green line in ANY row. Jump airborne frames may have feet ABOVE the rail; that is the only allowed deviation.\n` +
    `  - Horizontal centre of the silhouette = character's body centre.\n` +
    `  - The narrow magenta band below the green feet rail in every cell MUST remain solid magenta — no boots, no feet, no shadow, no toes poking through.\n` +
    `Side view, facing right, throughout the whole sheet.\n` +
    `Background is solid magenta (#FF00FF) everywhere outside the character — chroma key, will be removed. EXACT colour, not a pinkish hue.\n` +
    `Do NOT render the silhouettes, the cyan/green rails, or the yellow grid in the output. No labels, no row dividers, no borders, no frame numbers, no ground shadow.`
  );
}

export interface CharacterCombinedArgs {
  prompt: string;
  tag: string;
  runDir: string;
  model: string;
  /** Path to fixtures/image_gen_templates/character_template_combined.png */
  layoutTemplatePath: string;
  /** Path to character_concept_<tag>.png (identity ref). */
  characterConceptPath: string;
}

export async function generateCharacterCombined(args: CharacterCombinedArgs) {
  const { prompt, tag, runDir, model, layoutTemplatePath, characterConceptPath } = args;
  const outPath = join(runDir, `character_${tag}_combined.png`);
  return generateImageAsset({
    stage: "character-master",
    userPrompt: prompt,
    promptText: buildPrompt(),
    // Order matters — see header comment. Layout FIRST (geometry dominance),
    // identity SECOND (style match).
    refs: [layoutTemplatePath, characterConceptPath],
    outPath,
    width: CANVAS_W,
    height: CANVAS_H,
    model,
    extra: {
      rows: ROWS,
      cols: COLS,
      cellW: CELL_W,
      cellH: CELL_H,
      headTopY: HEAD_TOP_Y,
      feetBotY: FEET_BOT_Y,
      states: ["idle", "walk", "run", "jump", "crawl"],
    },
  });
}
