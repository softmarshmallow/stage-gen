// Items / pickup sheet generator (Wave 2).
// Single 4×2 grid of 8 distinct items on chroma-key magenta, 2400×800.
// Reuses obstacle_template.png as the layout prior.

import { join } from "node:path";
import type { WorldSpec } from "../schema/world.ts";
import { generateImageAsset } from "./image-helper.ts";

const CANVAS_W = 2400;
const CANVAS_H = 800;

function buildItemsPrompt(items: WorldSpec["items"]): string {
  const lines = items
    .map((it, i) => `  • Cell ${i}: "${it.name}" (${it.kind}) — ${it.brief}`)
    .join("\n");

  return (
    `Item / pickup sprite sheet for a 2D side-scroll platformer.\n` +
    `TWO reference images:\n` +
    `  IMAGE 1 — LAYOUT TEMPLATE: a 4×2 grid of 8 equal cells on magenta. Ignore the green band at the bottom of each cell — paint magenta over it. Treat each cell as a centered slot for ONE item.\n` +
    `  IMAGE 2 — STYLE REFERENCE: the world's concept art. Match its painterly rendering, palette, lighting, and overall mood EXACTLY.\n\n` +
    `PAINT EXACTLY THESE 8 NAMED ITEMS, ONE PER CELL (read order: top-left → top-right across row 0, then bottom-left → bottom-right across row 1). Each item is centred inside its cell. The "kind" in parentheses is the world-design agent's category label for the pickup (its own design, not a fixed enum) — paint each item so it visually reads as that kind:\n` +
    `${lines}\n\n` +
    `CONTRACT for every cell:\n` +
    `  - Each item is CENTERED inside its cell — neither at the top nor sitting on the bottom band.\n` +
    `  - Each item is sized to roughly 40-60% of its cell's height (not filling the cell, leaving comfortable margin).\n` +
    `  - Each item is opaque and HARD-edged against magenta — no soft halos, no glow halos painted as soft alpha (any "glow" appearance must be painted as crisp shapes; the runtime applies any glow/bloom procedurally).\n` +
    `  - EVERY pixel that is NOT part of the item stays solid magenta (#FF00FF — the EXACT chroma-key colour). Magenta is the chroma key.\n` +
    `  - Items vary in size relative to each other: a coin is small, a relic is large.\n` +
    `  - The 8 items together form a varied loot palette — no two items should read the same.\n\n` +
    `Do NOT render the cell grid lines, the green grass band, or any text in the output. No labels, no borders, no frame numbers.\n` +
    `Output canvas: 2400×800 (3:1).`
  );
}

export interface ItemsArgs {
  prompt: string;
  tag: string;
  runDir: string;
  model: string;
  conceptImagePath: string;
  obstacleTemplatePath: string;
  items: WorldSpec["items"];
}

export async function generateItems(args: ItemsArgs) {
  const { prompt, tag, runDir, model, conceptImagePath, obstacleTemplatePath, items } = args;
  const outPath = join(runDir, `items_${tag}.png`);
  return generateImageAsset({
    stage: "items",
    userPrompt: prompt,
    promptText: buildItemsPrompt(items),
    refs: [obstacleTemplatePath, conceptImagePath],
    outPath,
    width: CANVAS_W,
    height: CANVAS_H,
    model,
    extra: {
      item_count: items.length,
      kinds: items.map((it) => it.kind),
    },
  });
}
