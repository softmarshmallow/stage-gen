// Per-mob hurt strip generator (Wave 3 / Wave B).
// 1 row × 4 columns of hurt frames on chroma magenta, 2400×800.
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
    `Sprite HURT / DAMAGE animation strip for a CREATURE / MOB in a 2D platformer.\n` +
    `TWO reference images:\n` +
    `  IMAGE 1 — DESIGN REFERENCE (CANONICAL SUBJECT): the creature's turnaround sheet. This image is the SINGLE SOURCE OF TRUTH for what the creature is. Reproduce its silhouette, anatomy, species, colour palette, markings, proportions, and rendering style EXACTLY across all 4 frames. DO NOT substitute a different animal. DO NOT invent a new creature. DO NOT reinterpret the body-plan label below as license to draw a different species — the IMAGE wins over the words. If the reference shows a fluffy white puff-bird, every frame must be that exact puff-bird; if it shows an ice eagle, every frame must be that exact ice eagle.\n` +
    `  IMAGE 2 — LAYOUT TEMPLATE (sizing only): a 4x1 grid on magenta with bright YELLOW grid lines. Each cell has a CYAN top rail (head-top marker) and a single GREEN feet rail across the FULL ROW (ground baseline). The grey humanoid silhouette in this template is JUST a sizing rail — IGNORE its shape and species; it is NOT the subject. The creature does NOT need to be humanoid; only the top of the creature touches the cyan rail and the base of the creature rests on the GREEN rail.\n\n` +
    `Subject (textual anchor — secondary to IMAGE 1): "${mob.name}", a ${mob.tier_label} on this world's mob ladder. Body-plan archetype: ${mob.body_plan}. Brief: ${mob.brief}\n` +
    `If the textual description above ever conflicts with IMAGE 1, IMAGE 1 wins. Reproduce the creature shown in IMAGE 1 exactly — just contorted into the recoil poses below.\n\n` +
    `Render a 4-frame HURT animation as a strict 4x1 grid of equal cells. Read order: left-to-right. Side view, the creature is facing RIGHT but is being hit FROM THE RIGHT (so the recoil pushes it LEFT — back of the body / head whips away from the attacker). Use the side view from the IMAGE 1 turnaround as the basis for the body shape.\n\n` +
    `  Frame 1 — IMPACT FLINCH: sharp recoil, body whipping away from the hit point, head/eyes squeezed, mouth open in pain, limbs splayed slightly. Strongest pose of the four.\n` +
    `  Frame 2 — STAGGER PEAK: leaning back / off-balance, body tilted away from where the hit landed, weight shifted to the rear contact point, expression dazed.\n` +
    `  Frame 3 — STAGGER SETTLING: still off-balance but starting to recover, body partially returning to upright, dazed expression continuing.\n` +
    `  Frame 4 — RECOVERY: nearly back to neutral upright pose, almost ready to return to idle, residual flinch.\n\n` +
    `The four frames read as ONE recoil motion at ~10 fps.\n\n` +
    `IDENTITY-PRESERVATION CHECK (apply to every frame before committing the pixel):\n` +
    `  - Same SPECIES as IMAGE 1? (e.g. bird stays bird, not insect/crab; raptor stays raptor, not hedgehog/fox)\n` +
    `  - Same SILHOUETTE outline as IMAGE 1's side view (just contorted by the recoil)?\n` +
    `  - Same PALETTE / markings as IMAGE 1?\n` +
    `  - Same PROPORTIONS (head-to-body ratio, limb length) as IMAGE 1?\n` +
    `  If any answer is "no", the frame is wrong — redraw it.\n\n` +
    `CRITICAL anchoring rules — the rails are HARD limits:\n` +
    `  - CYAN top rail = the topmost point of the creature's body silhouette in its NEUTRAL standing pose. The recoil may visually compress/lower the head; that is fine, but do NOT paint anything ABOVE the cyan rail.\n` +
    `  - GREEN feet rail = ground contact base. The creature stays on the ground (one foot may lift, but the body's contact point with the ground stays on the green line). Do NOT paint any pixels BELOW the green line.\n` +
    `  - Scale is IDENTICAL across all 4 frames AND identical to the idle reference scale — same body size, just contorted.\n` +
    `  - The creature stays the same colours and design; do NOT add red flash overlays, blood, or extra effects (the runtime tints / flashes the sprite procedurally).\n\n` +
    `Background is solid magenta (#FF00FF) — chroma key. EXACT colour, not a pinkish hue.\n` +
    `Do NOT render the silhouettes, the cyan/green rails, or the yellow grid in the output. No labels, no borders, no shadows.\n` +
    `Output canvas: 2400×800 (3:1).`
  );
}

export interface MobHurtArgs {
  prompt: string;
  tag: string;
  runDir: string;
  model: string;
  /** Path to fixtures/image_gen_templates/character_template.png */
  layoutTemplatePath: string;
  mobs: WorldSpec["mobs"];
}

export async function generateAllMobHurts(args: MobHurtArgs) {
  const { prompt, tag, runDir, model, layoutTemplatePath, mobs } = args;
  return Promise.all(
    mobs.map((mob, i) => {
      const outPath = join(runDir, `mob_${tag}_${i}_hurt.png`);
      const mobConceptPath = join(runDir, `mob_concept_${tag}_${i}.png`);
      return generateImageAsset({
        stage: `mob-hurt-${i}`,
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
          state: "hurt",
          rows: 1,
          cols: 4,
          ref_order: ["mob_concept", "layout_template"],
        },
      });
    }),
  );
}
