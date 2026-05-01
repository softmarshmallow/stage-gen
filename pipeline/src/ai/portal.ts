// Portal pair generator (Wave 2).
// 2048×1024 with two portals (entry left half / exit right half) on chroma-key
// magenta. Concept attached as the only ref.

import { join } from "node:path";
import { generateImageAsset } from "./image-helper.ts";

const CANVAS_W = 2048;
const CANVAS_H = 1024;

const PROMPT = `Portal sprite sheet for a 2D side-scroll platformer — two building-sized landmark structures painted on a single 2:1 canvas.

ONE reference image:
  IMAGE 1 — STYLE REFERENCE: the world's concept art. Match its painterly rendering, palette, lighting, and overall mood EXACTLY.

LAYOUT — exactly TWO equal halves on the canvas:
  LEFT HALF (entry portal): the START-of-stage portal. Reads as "you came from here" — calm, welcoming, slightly cool / muted in tone.
  RIGHT HALF (exit portal): the END-of-stage portal. Reads as "go through here to advance" — more active, slightly warmer / more luminous, with a clear sense of pull or invitation.

Both portals are the SAME body of architecture (gateway / shrine / arch / torii / standing stones / runic doorway — pick one form that fits the world's concept), differing only in subtle colour temperature and the energy of any glow / particle / inner-fill detail. They should obviously read as a matched pair AND as TWO DISTINCT portals on the sheet.

CONTRACT for both portals:
  - Each portal stands UPRIGHT and is BUILDING-SIZED — roughly TWICE the height of a small humanoid hero would stand at the same scale.
  - The BASE of each portal sits flat on a thin GREEN GRASS BAND at the bottom of its half — the same grass-contact convention as obstacle tiles. Grass tufts wrap the portal's foot so it integrates with the world's ground. No floating, no shadow gap.
  - The portal has an OPEN INNER AREA (an aperture / archway / doorway) filled with a soft glow or mystical fill that hints at passage — swirling mist, a shimmer, a runic glow, a starfield. Keep this fill INSIDE the portal's frame — do not let it bleed past the architecture.
  - Each portal is centred horizontally inside its half and occupies roughly 70-85% of the half's height (leaving ~15% of headroom and the grass band at the foot).
  - Outside the portal architecture, EVERY pixel is solid magenta (#FF00FF — the EXACT chroma-key colour). Magenta is the chroma key.
  - Each portal is opaque and HARD-edged against the magenta — no soft halos, no glow halos painted as soft alpha. The inner aperture glow must stay inside the architecture's frame and end at hard edges.
  - The two portals share the same overall silhouette and structural style; only colour temperature, glow intensity, and small symbolic accents (e.g. arrival vs departure runes) distinguish them.

Do NOT render any visible vertical divider line between the halves, no labels, no text, no frame numbers, no grid lines. Just two portals on a shared magenta field with green grass bands at their feet.
Output canvas: 2048×1024 (2:1).`;

export interface PortalArgs {
  prompt: string;
  tag: string;
  runDir: string;
  model: string;
  conceptImagePath: string;
}

export async function generatePortal(args: PortalArgs) {
  const { prompt, tag, runDir, model, conceptImagePath } = args;
  const outPath = join(runDir, `portal_${tag}.png`);
  return generateImageAsset({
    stage: "portal",
    userPrompt: prompt,
    promptText: PROMPT,
    refs: [conceptImagePath],
    outPath,
    width: CANVAS_W,
    height: CANVAS_H,
    model,
  });
}
