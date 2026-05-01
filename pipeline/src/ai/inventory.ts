// Inventory bag panel generator (Wave 2).
// 1536×1024 with locked slot positions visible. Uses inventory_template.png
// (yellow outer frame + cyan slot grid) as the layout prior + concept as
// style ref.

import { join } from "node:path";
import { generateImageAsset } from "./image-helper.ts";

const CANVAS_W = 1536;
const CANVAS_H = 1024;

const PROMPT = `Inventory / bag UI panel for a 2D side-scroll platformer.
TWO reference images:
  IMAGE 1 — LAYOUT TEMPLATE: a 1536×1024 magenta canvas with a YELLOW rectangular outline marking the panel's outer edge, and a 4×2 grid of CYAN-outlined square slots inside. The cyan rectangles mark the EXACT positions and sizes of the 8 inventory slots — these must be honoured 1:1 in the output.
  IMAGE 2 — STYLE REFERENCE: the world's concept art. Match its painterly rendering style, palette, lighting, and overall mood EXACTLY.

Render an ornate themed inventory / bag panel:
  - The PANEL FRAME fills the area between the yellow outline and the cyan slot grid. Style it as something the inhabitants of this world would carry their belongings in: carved wood, etched stone, embroidered cloth, woven leather, hammered metal, woven reeds, polished bone — whatever fits the concept reference. Add decorative trim, corner motifs, and small thematic flourishes appropriate to the world.
  - The 8 SLOTS are EMPTY recessed cells, one inside each cyan outline. Each slot is a SHALLOW INSET pocket — slightly darker / more shadowed than the surrounding panel, with subtle inner-edge shadow at the top-left and a faint highlight at the bottom-right to read as "recessed". The slot interior is a calm, mostly flat tone (so item icons composited on top at runtime read clearly). NO items, NO icons, NO placeholder content inside any slot.
  - Slot positions, sizes, and the gutters between them must EXACTLY match the cyan-outlined grid in the template — do not shift, resize, rotate, or rearrange them. The 8 slot positions must be VISIBLE as discrete recessed cells in the output.

OUTSIDE THE PANEL (everything beyond the yellow outline) stays solid magenta (#FF00FF — the EXACT chroma-key colour). Magenta is the chroma key — it will be removed at runtime.

Do NOT render the cyan slot outlines, the yellow frame line, or any text in the output. No labels, no slot numbers, no badges, no cursor, no item icons.
Output canvas: 1536×1024 (3:2 landscape).`;

export interface InventoryArgs {
  prompt: string;
  tag: string;
  runDir: string;
  model: string;
  conceptImagePath: string;
  inventoryTemplatePath: string;
}

export async function generateInventory(args: InventoryArgs) {
  const { prompt, tag, runDir, model, conceptImagePath, inventoryTemplatePath } = args;
  const outPath = join(runDir, `inventory_${tag}.png`);
  return generateImageAsset({
    stage: "inventory",
    userPrompt: prompt,
    promptText: PROMPT,
    refs: [inventoryTemplatePath, conceptImagePath],
    outPath,
    width: CANVAS_W,
    height: CANVAS_H,
    model,
  });
}
