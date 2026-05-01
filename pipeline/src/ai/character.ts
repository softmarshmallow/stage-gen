// Character concept (turnaround) generator (Wave 2).
// 3-pose turnaround on chroma-key magenta, 2400×800.

import { join } from "node:path";
import { generateImageAsset } from "./image-helper.ts";

const CANVAS_W = 2400;
const CANVAS_H = 800;

function buildPrompt(description: string): string {
  return (
    `Character turnaround sheet for a 2D platformer.\n` +
    `The provided image is the world's concept art — match its painterly rendering, palette, lighting, and overall mood EXACTLY.\n` +
    `Render the SAME character three times in a single horizontal row, evenly spaced:\n` +
    `  1) FRONT view (facing camera)\n` +
    `  2) SIDE view (facing right, profile)\n` +
    `  3) BACK view (facing away from camera)\n\n` +
    `Character: ${description}.\n` +
    `Each pose is full body in a relaxed neutral standing pose — head to feet visible, arms at sides.\n` +
    `Equal spacing between poses, identical scale, same vertical baseline (feet on the same horizontal line).\n` +
    `The entire background is solid magenta (#FF00FF) — chroma key, will be removed later. Do NOT use a near-magenta or pinkish hue; the EXACT colour #FF00FF (255,0,255) is the contract.\n` +
    `No ground shadow, no border, no labels, no captions.\n` +
    `Output canvas: 2400×800 (3:1).`
  );
}

export interface CharacterConceptArgs {
  prompt: string;
  tag: string;
  runDir: string;
  model: string;
  conceptImagePath: string;
  /** Optional character description; defaults to a world-appropriate hero. */
  description?: string;
}

export async function generateCharacterConcept(args: CharacterConceptArgs) {
  const { prompt, tag, runDir, model, conceptImagePath } = args;
  const description =
    args.description ??
    "the world's lone protagonist — an explorer / adventurer figure scaled like a small humanoid hero, designed to fit this world's flavour and palette";
  const outPath = join(runDir, `character_concept_${tag}.png`);
  return generateImageAsset({
    stage: "character-concept",
    userPrompt: prompt,
    promptText: buildPrompt(description),
    refs: [conceptImagePath],
    outPath,
    width: CANVAS_W,
    height: CANVAS_H,
    model,
    extra: { description },
  });
}
