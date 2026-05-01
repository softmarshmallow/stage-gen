// Character motion master sheet generator (Wave 3 / Wave B).
// 5 rows × 4 columns of motion frames on chroma magenta, 2400×3440.
// Largest call in the pipeline (≈8.26 Mpx, just under the model cap).
//
// Inputs:
//   - layout prior: fixtures/image_gen_templates/character_template_combined.png
//   - identity ref: out/<tag>/character_concept_<tag>.png
//
// Rows (top → bottom): idle, walk, run, jump, crawl. 4 frames each.

import { join } from "node:path";
import { generateImageAsset } from "./image-helper.ts";

const CANVAS_W = 2400;
const CANVAS_H = 3440;

function buildPrompt(): string {
  return (
    `Sprite animation MASTER SHEET for a single 2D platformer character.\n` +
    `TWO reference images are provided:\n` +
    `  IMAGE 1 — LAYOUT TEMPLATE: a 4×5 grid of equal cells on magenta with bright YELLOW grid lines. Each cell contains a gray HUMANOID silhouette (head circle + torso + legs) marking the EXACT position, scale, and feet baseline the character must occupy:\n` +
    `    • The CYAN horizontal rail across the top of each silhouette = the TOP OF THE CHARACTER'S HEAD/HAIR.\n` +
    `    • The GREEN horizontal rail running across the FULL ROW WIDTH = the SOLES OF THE FEET. Every frame in a row shares this single green ground line.\n` +
    `    • The grey humanoid figure between cyan and green rails marks the body's height, width, and centre.\n` +
    `  Match those rails and silhouette dimensions PRECISELY in every cell; do NOT draw the character taller, shorter, wider, or narrower than the silhouette.\n` +
    `  IMAGE 2 — DESIGN REFERENCE: the character's turnaround. Match its design, proportions, colours, outfit, and rendering style EXACTLY across every frame.\n\n` +
    `Render a master sheet as a strict 4×5 grid (4 columns × 5 rows), aligned 1:1 with the template's cells. Each ROW is a different motion state. Each COLUMN within a row is the next frame in that motion's cycle, read left-to-right.\n\n` +
    `Rows (top to bottom):\n` +
    `  Row 1 (top): IDLE — subtle breathing, weight shift, arms relaxed at sides. Loops cleanly.\n` +
    `  Row 2: WALK — alternating left/right legs forward, gentle opposite arm swing, slight head bob. Loops cleanly.\n` +
    `  Row 3: RUN — full sprint, knees driven high, bent arms swinging hard front-to-back, body leaning slightly forward, cloak/hair trailing. Faster, more exaggerated than the walk row. Loops cleanly.\n` +
    `  Row 4: JUMP — frame 1 anticipation crouch, frame 2 push-off rising, frame 3 apex with legs tucked, frame 4 descending/landing absorption.\n` +
    `  Row 5 (bottom): CRAWL / SQUAT-WALK — character is crouched LOW, knees deeply bent, body lowered to ~half its standing height, head ducked. Alternating crouched steps with hands near knees or held low. Sustained low squat the entire row. Loops cleanly.\n\n` +
    `In every cell, replace the gray silhouette with the character in the correct pose for that row's motion and that column's phase. CRITICAL anchoring rules — the rails are HARD limits:\n` +
    `  - The CYAN top rail = the TOP of the character's head/hair. Do NOT paint hair, ears, or head pixels above the cyan line.\n` +
    `  - The GREEN feet rail = the SOLES of the character's feet/boots. Do NOT paint any character pixels below the green line.\n` +
    `  - The horizontal centre of the silhouette = the character's body centre.\n` +
    `  - The character must fit ENTIRELY between the cyan top rail and the green feet rail; pixels outside the silhouette stay magenta.\n` +
    `  - The narrow magenta band below the green feet rail in every cell MUST remain solid magenta — no boots, no feet, no shadow, no toes poking through.\n` +
    `SCALE LOCK: because every row shares the same green feet rail height and the same cyan head-top rail height, the character's overall body scale must be IDENTICAL across ALL 20 frames in the sheet. The crawl row character is the SAME body as the idle row, just deeply crouched — same head size, same proportions, same scale; only the pose changes. Do NOT enlarge the run-row character or shrink the crawl-row character.\n\n` +
    `Side view, facing right, throughout the whole sheet.\n` +
    `Background is solid magenta (#FF00FF) everywhere outside the character — chroma key, will be removed. EXACT colour, not a pinkish hue.\n` +
    `Do NOT render the silhouettes, the cyan/green rails, or the yellow grid in the output. No labels, no row dividers, no borders, no frame numbers, no ground shadow.\n` +
    `Output canvas: 2400×3440.`
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
    refs: [layoutTemplatePath, characterConceptPath],
    outPath,
    width: CANVAS_W,
    height: CANVAS_H,
    model,
    extra: {
      rows: 5,
      cols: 4,
      states: ["idle", "walk", "run", "jump", "crawl"],
    },
  });
}
