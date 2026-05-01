// Ground tileset generator (Wave 2).
// 12×4 grid on 2400×800. Uses fixtures/wireframe.png as the layout prior.
// Concept attached as the style reference.

import { join } from "node:path";
import { generateImageAsset } from "./image-helper.ts";

const CANVAS_W = 2400;
const CANVAS_H = 800;

const PROMPT = `Render the layout in the FIRST image as ground terrain for this world.
The layout is a 12×4 grid of independent ground blocks; each cell is one self-contained block that meets its neighbours at the cell border, sharing material with adjacent cells.

The SECOND image is the style reference — match its rendering technique, brushwork, palette, lighting, atmosphere and overall mood exactly. The FIRST image is only a layout guide; do not copy its flat colours.

The GREEN regions mark the WALKABLE SURFACE LAYER of this world (only the top row has any). Treat green as a placeholder colour, NOT as a material instruction — the actual material must come from the world style reference. For example: lush forest → grass blades; snowy mountain → snow / snowdrifts / pine-needle litter; desert → dry grass tufts / sand drifts; swamp → mossy clumps / reeds; cyberpunk alley → broken pavement edge / weeds in cracks. Pick the material that fits the reference.

The green silhouette has TWO parts you must read literally as SHAPES (independent of what material you paint them with):
  • A thin horizontal BAND of solid green near the middle of the cell — paint this as the continuous flat top of the walkable surface (the strip the player walks on).
  • Tall, irregular GREEN PROTRUSIONS rising upward from that band into the magenta sky — paint these as vertical surface details: blades, drifts, crystals, tufts, weeds, sprigs, icicles — whatever fits the world. Vary heights; some short, some tall, some clumped.
Honour both parts. Do NOT smooth the protrusions into a flat ledge or trim them into a hedge; do NOT thicken the band into a fat slab. The band stays thin and the protrusions stand out against the sky.

The GRAY regions are the UNDERGROUND material directly below the walkable surface — uniform across all three lower rows. Pick the material from the world reference (dirt, packed snow, sand, stone, peat, concrete substrate, etc.). Do NOT add a second surface layer, ledges, terraces, or highlights between rows; the horizontal seams are tile borders, not elevation changes.

Magenta regions stay exactly magenta (#FF00FF), untouched (including the magenta gaps between tall protrusions at the top of the surface layer).
Fill each cell edge-to-edge.

Output canvas: 2400×800 (3:1). The 12×4 cell grid must be visible structure even though no grid lines are drawn — every cell self-contained.`;

export interface TilesetArgs {
  prompt: string;
  tag: string;
  runDir: string;
  model: string;
  conceptImagePath: string;
  wireframePath: string;
}

export async function generateTileset(args: TilesetArgs) {
  const { prompt, tag, runDir, model, conceptImagePath, wireframePath } = args;
  const outPath = join(runDir, `tileset_${tag}.png`);
  return generateImageAsset({
    stage: "tileset",
    userPrompt: prompt,
    promptText: PROMPT,
    refs: [wireframePath, conceptImagePath],
    outPath,
    width: CANVAS_W,
    height: CANVAS_H,
    model,
  });
}
