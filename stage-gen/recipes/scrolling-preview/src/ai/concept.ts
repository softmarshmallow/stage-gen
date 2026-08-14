import { join } from "node:path";
import { generateImageAsset } from "./image-helper.ts";

const CANVAS_W = 1536;
const CANVAS_H = 1024;

export interface ConceptArgs {
  prompt: string;
  tag: string;
  runDir: string;
  model: string;
}

export interface ConceptResult {
  imagePath: string;
  metaPath: string;
}

function buildConceptPrompt(theme: string): string {
  return (
    `2D scrolling-game scene concept art, wide cinematic landscape view.\n` +
    `Theme: ${theme}.\n` +
    `Compose clear depth: distant background, middle distance, and foreground.\n` +
    `Hand-painted look. Single fully opaque style reference with no cutout regions, text, or labels.`
  );
}

export function generateConcept(args: ConceptArgs): Promise<ConceptResult> {
  const outPath = join(args.runDir, `concept_${args.tag}.png`);
  return generateImageAsset({
    stage: "concept",
    userPrompt: args.prompt,
    promptText: buildConceptPrompt(args.prompt),
    outPath,
    width: CANVAS_W,
    height: CANVAS_H,
    model: args.model,
  });
}
