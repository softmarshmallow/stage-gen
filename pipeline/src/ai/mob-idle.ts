// Per-mob idle strip generator (Wave 3 / Wave B).
// 1 row × 4 columns of idle frames on chroma magenta, 2400×800.
// One file per ladder rung.
//
// Inputs (per rung):
//   - identity ref: out/<tag>/mob_concept_<tag>_<i>.png   (PRIMARY — passed FIRST)
//   - layout prior: fixtures/image_gen_templates/character_template.png (sizing rail, reused — passed SECOND)
//
// Reference order is load-bearing: gpt-image-2 weights the first reference
// most heavily for subject identity. The per-mob concept turnaround MUST be
// the first image so the model reproduces the SAME creature instead of
// inventing a new one styled after the layout template.

import { join } from "node:path";
import type { WorldSpec } from "../schema/world.ts";
import { generateImageAsset } from "./image-helper.ts";

const CANVAS_W = 2400;
const CANVAS_H = 800;

function buildPrompt(mob: WorldSpec["mobs"][number]): string {
  return (
    `Sprite IDLE animation strip for a CREATURE / MOB in a 2D platformer.\n` +
    `TWO reference images:\n` +
    `  IMAGE 1 — DESIGN REFERENCE (CANONICAL SUBJECT): the creature's turnaround sheet. This image is the SINGLE SOURCE OF TRUTH for what the creature is. Reproduce its silhouette, anatomy, species, colour palette, markings, proportions, and rendering style EXACTLY across all 4 frames. DO NOT substitute a different animal. DO NOT invent a new creature. DO NOT reinterpret the body-plan label below as license to draw a different species — the IMAGE wins over the words. If the reference shows a fluffy white puff-bird, every frame must be that exact puff-bird; if it shows an ice eagle, every frame must be that exact ice eagle.\n` +
    `  IMAGE 2 — LAYOUT TEMPLATE (sizing only): a 4×1 grid on magenta with bright YELLOW grid lines. Each cell has a CYAN horizontal rail (head-top marker) and a single GREEN horizontal rail across the FULL ROW (the feet baseline / ground line). The grey humanoid silhouette in this template is JUST a sizing rail — IGNORE its shape and species; it is NOT the subject. The creature does NOT need to be humanoid; only the top of the creature must touch the CYAN rail and the base of the creature must rest on the GREEN rail.\n\n` +
    `Subject (textual anchor — secondary to IMAGE 1): "${mob.name}", a ${mob.tier_label} on this world's mob ladder. Body-plan archetype: ${mob.body_plan}. Brief: ${mob.brief}\n` +
    `If the textual description above ever conflicts with IMAGE 1, IMAGE 1 wins. Reproduce the creature shown in IMAGE 1 exactly.\n\n` +
    `Render a 4-frame IDLE animation as a strict 4×1 grid of equal cells, aligned 1:1 with the template's cells.\n` +
    `Read order: left-to-right — each cell is the next moment in the idle cycle.\n` +
    `Animation: a subtle idle — small breathing rise/fall, gentle sway, antenna twitch, wing flutter, tail flick (whatever fits THIS creature's anatomy as shown in IMAGE 1). The cycle LOOPS cleanly: the last frame leads naturally into the first. Side view facing right (use the side view from the IMAGE 1 turnaround as the basis).\n\n` +
    `IDENTITY-PRESERVATION CHECK (apply to every frame before committing the pixel):\n` +
    `  - Same SPECIES as IMAGE 1? (e.g. bird stays bird, not insect; raptor stays raptor, not fox/hedgehog)\n` +
    `  - Same SILHOUETTE outline as IMAGE 1's side view?\n` +
    `  - Same PALETTE / markings as IMAGE 1?\n` +
    `  - Same PROPORTIONS (head-to-body ratio, limb length) as IMAGE 1?\n` +
    `  If any answer is "no", the frame is wrong — redraw it.\n\n` +
    `CRITICAL anchoring rules — the rails are HARD limits:\n` +
    `  - The CYAN top rail = the topmost point of the creature (head, antenna tip, ear tip — whatever is highest). Do NOT paint above it.\n` +
    `  - The GREEN feet rail = the creature's contact base (feet, slime base, underbelly — whatever rests on the ground). Do NOT paint below it.\n` +
    `  - The body fits ENTIRELY between the cyan and green rails; pixels outside the silhouette stay magenta.\n` +
    `  - Scale is IDENTICAL across all 4 frames — every frame uses the same creature size.\n\n` +
    `Background is solid magenta (#FF00FF) outside the creature — chroma key. EXACT colour, not a pinkish hue.\n` +
    `Do NOT render the silhouettes, the cyan/green rails, or the yellow grid in the output. No labels, no borders, no shadows.\n` +
    `Output canvas: 2400×800 (3:1).`
  );
}

export interface MobIdleArgs {
  prompt: string;
  tag: string;
  runDir: string;
  model: string;
  /** Path to fixtures/image_gen_templates/character_template.png */
  layoutTemplatePath: string;
  mobs: WorldSpec["mobs"];
}

export async function generateAllMobIdles(args: MobIdleArgs) {
  const { prompt, tag, runDir, model, layoutTemplatePath, mobs } = args;
  return Promise.all(
    mobs.map((mob, i) => {
      const outPath = join(runDir, `mob_${tag}_${i}_idle.png`);
      const mobConceptPath = join(runDir, `mob_concept_${tag}_${i}.png`);
      return generateImageAsset({
        stage: `mob-idle-${i}`,
        userPrompt: prompt,
        promptText: buildPrompt(mob),
        // Identity ref FIRST (primary), layout template SECOND (sizing rail only).
        // Order matches the prompt's "IMAGE 1 / IMAGE 2" labels.
        refs: [mobConceptPath, layoutTemplatePath],
        outPath,
        width: CANVAS_W,
        height: CANVAS_H,
        model,
        extra: {
          slot: i,
          rung: i + 1,
          name: mob.name,
          tier_label: mob.tier_label,
          body_plan: mob.body_plan,
          state: "idle",
          rows: 1,
          cols: 4,
          ref_order: ["mob_concept", "layout_template"],
        },
      });
    }),
  );
}
