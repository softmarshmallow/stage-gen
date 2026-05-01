// Character attack strip generator (Wave 3 / Wave B).
// 1 row × 4 columns of attack frames on chroma magenta, 2400×800.
//
// Inputs:
//   - layout prior: fixtures/image_gen_templates/character_template.png
//   - identity ref: out/<tag>/character_concept_<tag>.png
//
// Frames (left → right): wind-up, swing, impact, recovery.

import { join } from "node:path";
import { generateImageAsset } from "./image-helper.ts";

const CANVAS_W = 2400;
const CANVAS_H = 800;

function buildPrompt(): string {
  return (
    `Sprite ATTACK animation strip for a 2D platformer character.\n` +
    `TWO reference images:\n` +
    `  IMAGE 1 — LAYOUT TEMPLATE: a 4x1 grid on magenta with bright YELLOW grid lines. Each cell has a CYAN horizontal rail (head-top marker) and a single GREEN horizontal rail across the FULL ROW (feet baseline / ground line). The grey humanoid silhouette marks the body's height, width, and centre.\n` +
    `  IMAGE 2 — DESIGN REFERENCE: the character's turnaround. Match its design, proportions, colours, outfit, and rendering style EXACTLY across every frame.\n\n` +
    `Render a 4-frame ATTACK animation as a strict 4x1 grid of equal cells, aligned 1:1 with the template's cells. Read order: left-to-right.\n\n` +
    `The character performs ONE attack motion, choose whatever weapon / style fits the design reference (a sword swing, a punch combo, a magic cast, a claw swipe, a staff strike, a kick — anything consistent with the character):\n` +
    `  Frame 1 — ANTICIPATION / WIND-UP: weight shifted back, weapon or limb drawn back / charging up, body coiled.\n` +
    `  Frame 2 — FORWARD SWING / RELEASE: body driving forward, weapon or limb mid-arc / mid-throw, peak motion line, debris or motion suggestion welcome.\n` +
    `  Frame 3 — IMPACT / FULL EXTENSION: arm and weapon at full extension forward, weight committed forward, peak reach. This is the hit frame.\n` +
    `  Frame 4 — RECOVERY: weapon / limb pulling back, body settling back to neutral, ready to chain into idle.\n` +
    `The four frames should read as ONE fluid motion when played at ~12 fps.\n\n` +
    `Side view facing right.\n\n` +
    `CRITICAL anchoring rules — the rails are HARD limits FOR THE BODY:\n` +
    `  - The CYAN top rail = the TOP of the character's head/hair. Do NOT paint the head above it.\n` +
    `  - The GREEN feet rail = the SOLES of the character's feet/boots. Do NOT paint any character pixels below the green line.\n` +
    `  - The character's BODY (torso, head, legs) must fit between the rails at the SAME scale as the silhouette — same proportions as the idle/walk/run reference frames.\n` +
    `  - WEAPON / EFFECT EXCEPTION: an outstretched sword, fist, claw, or magic effect MAY extend OUTSIDE the silhouette horizontally during the swing/impact frames — that is expected. But the BODY itself stays within the rails.\n` +
    `  - Pixels that are not the character or their weapon/effect stay solid magenta.\n\n` +
    `Background is solid magenta (#FF00FF) — chroma key, will be removed. EXACT colour, not a pinkish hue.\n` +
    `Do NOT render the silhouettes, the cyan/green rails, or the yellow grid in the output. No labels, no borders, no shadows.\n` +
    `Output canvas: 2400×800 (3:1).`
  );
}

export interface CharacterAttackArgs {
  prompt: string;
  tag: string;
  runDir: string;
  model: string;
  /** Path to fixtures/image_gen_templates/character_template.png */
  layoutTemplatePath: string;
  /** Path to character_concept_<tag>.png (identity ref). */
  characterConceptPath: string;
}

export async function generateCharacterAttack(args: CharacterAttackArgs) {
  const { prompt, tag, runDir, model, layoutTemplatePath, characterConceptPath } = args;
  const outPath = join(runDir, `character_${tag}_attack.png`);
  return generateImageAsset({
    stage: "character-attack",
    userPrompt: prompt,
    promptText: buildPrompt(),
    refs: [layoutTemplatePath, characterConceptPath],
    outPath,
    width: CANVAS_W,
    height: CANVAS_H,
    model,
    extra: {
      rows: 1,
      cols: 4,
      phases: ["wind-up", "swing", "impact", "recovery"],
    },
  });
}
