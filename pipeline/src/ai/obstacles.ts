// Obstacle / prop sheet generators (Wave 2).
// One per declared obstacle sheet theme (M = world.obstacles.length).
// 4×2 grid on chroma-key magenta, 2400×800. Uses obstacle_template.png as
// the layout prior + concept as the style ref.

import { join } from "node:path";
import type { WorldSpec } from "../schema/world.ts";
import { generateImageAsset } from "./image-helper.ts";

const CANVAS_W = 2400;
const CANVAS_H = 800;

function buildObstaclePrompt(args: {
  variantIdx: number;
  sheet: WorldSpec["obstacles"][number];
}): string {
  const { variantIdx, sheet } = args;
  const propLines = sheet.props
    .map((p, i) => `  • Cell ${i}: "${p.name}" — ${p.brief}`)
    .join("\n");

  return (
    `Obstacle / prop sprite sheet #${variantIdx + 1} for a 2D side-scroll platformer.\n` +
    `TWO reference images:\n` +
    `  IMAGE 1 — LAYOUT TEMPLATE: a 4×2 grid of 8 equal cells on magenta. Each cell has a thin GREEN GRASS BAND at the bottom — that band is the ground-contact line where the obstacle rests on the world's ground.\n` +
    `  IMAGE 2 — STYLE REFERENCE: the world's concept art. Match its painterly rendering, palette, lighting, and overall mood EXACTLY.\n\n` +
    `Theme for THIS sheet: ${sheet.sheet_theme}. Other sheets in this world cover other themes, so emphasize this one — the 8 props on this sheet should all clearly fit the theme above.\n\n` +
    `PAINT EXACTLY THESE 8 NAMED PROPS, ONE PER CELL (read order: top-left → top-right across row 0, then bottom-left → bottom-right across row 1):\n` +
    `${propLines}\n\n` +
    `Keep the proportions realistic and varied — some props small, some tall, some wide. Each must clearly read as the named entry.\n\n` +
    `CONTRACT for every cell:\n` +
    `  - The obstacle's BASE rests directly on the grass band, with grass tufts wrapping the foot of the obstacle so it BLENDS into the world's grass — no floating, no shadow gap.\n` +
    `  - Keep the bottom of each painted obstacle FLAT and TEXTURED (not a sharp single-line edge) so it integrates with grass at any width when placed in-world.\n` +
    `  - The grass band stays GREEN at the bottom of the cell — paint over it in the same painterly grass style as the world reference.\n` +
    `  - Above the grass band, EVERY pixel that is NOT part of the obstacle stays solid magenta (#FF00FF — the EXACT chroma-key colour). Magenta is the chroma key.\n` +
    `  - Each obstacle is opaque and HARD-edged against the magenta — no soft halos, no glow, no feathered alpha.\n` +
    `  - Obstacles vary in size: some fill 30% of the cell, others fill 90%. Mix small / medium / tall / wide so the demo has visual variety.\n\n` +
    `Do NOT render the cell grid lines or any text in the output. No labels, no borders, no frame numbers.\n` +
    `Output canvas: 2400×800 (3:1).`
  );
}

export interface ObstaclesArgs {
  prompt: string;
  tag: string;
  runDir: string;
  model: string;
  conceptImagePath: string;
  obstacleTemplatePath: string;
  obstacles: WorldSpec["obstacles"];
}

export async function generateAllObstacles(args: ObstaclesArgs) {
  const { prompt, tag, runDir, model, conceptImagePath, obstacleTemplatePath, obstacles } = args;
  return Promise.all(
    obstacles.map((sheet, i) => {
      const outPath = join(runDir, `obstacles_${tag}_${i}.png`);
      const promptText = buildObstaclePrompt({ variantIdx: i, sheet });
      return generateImageAsset({
        stage: `obstacles-${i}`,
        userPrompt: prompt,
        promptText,
        refs: [obstacleTemplatePath, conceptImagePath],
        outPath,
        width: CANVAS_W,
        height: CANVAS_H,
        model,
        extra: {
          variant: i,
          sheet_theme: sheet.sheet_theme,
          prop_count: sheet.props.length,
        },
      });
    }),
  );
}
