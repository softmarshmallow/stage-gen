// Parallax depth layer generator (Wave 2).
//
// One per entry in world_spec.layers[]. Each entry is fully agent-designed
// (id, z_index, parallax, opaque, paint_region, description).
// The opaque layer IS the skybox (TC-030); transparent layers use #FF00FF
// magenta as the chroma key (TC-032).
//
// Generates all L layers in parallel via generateAllLayers() — fans out from
// the stage runner.

import { join } from "node:path";
import type { WorldSpec } from "../schema/world.ts";
import { generateImageAsset } from "./image-helper.ts";

const CANVAS_W = 2400;
const CANVAS_H = 800;

function depthPhrase(parallax: number, opaque: boolean): string {
  if (opaque) return "static distant backdrop (no scrolling)";
  if (parallax < 0.25) return "FAR distance — atmospheric, hazier, low contrast";
  if (parallax < 0.6) return "MID distance — softer detail, partial atmospheric haze";
  if (parallax < 1.0) return "NEAR distance — sharper detail, fuller saturation";
  return "FOREGROUND — sharp, high-contrast, very close to camera";
}

function opaqueClause(opaque: boolean): string {
  if (opaque) {
    return (
      "OPAQUE BACKDROP — fill the ENTIRE canvas. Do NOT use any magenta chroma key. " +
      "Every pixel is part of the layer. There is no transparent region. " +
      "This is the skybox / deepest backdrop the rest of the world sits in front of."
    );
  }
  return (
    "TRANSPARENT LAYER — paint only inside the region described above; everywhere else stays SOLID MAGENTA " +
    "(#FF00FF — the EXACT chroma-key colour, not a pinkish near-magenta and not transparent). " +
    "The runtime keys magenta to alpha 0 so deeper layers show through."
  );
}

function buildLayerPrompt(layer: WorldSpec["layers"][number]): string {
  return (
    `Parallax depth layer for a 2D side-scrolling platformer.\n` +
    `The provided image is the world's concept art — match its painterly rendering, palette, lighting, and overall mood EXACTLY.\n\n` +
    `LAYER METADATA (designed by the world-design agent for this world):\n` +
    `  • Title: "${layer.title}"\n` +
    `  • Z-index: ${layer.z_index} (${layer.opaque ? "deepest backdrop" : "transparent overlay; deeper layers show through where you leave magenta"})\n` +
    `  • Parallax: ${layer.parallax} (${depthPhrase(layer.parallax, layer.opaque)})\n\n` +
    `WHAT TO PAINT (one sentence): ${layer.description}\n\n` +
    `WHERE TO PAINT (canvas-fraction language; Y axis runs 0/5 top to 5/5 bottom, X axis 0/5 left to 5/5 right):\n` +
    `${layer.paint_region}\n\n` +
    `Honour the paint region literally. Painted content fills the described region edge-to-edge with full painterly detail; outside the described region the rules below apply.\n\n` +
    `${opaqueClause(layer.opaque)}\n\n` +
    `LOOPING — handled by the runtime. The image will be rendered twice with overlap and crossfaded at the L/R edges, so seams disappear automatically. You do NOT need to paint any loop-fade gradient, alpha taper, or "fade-to-edge" effect. Paint the content edge-to-edge as if the canvas were a single isolated panel; the runtime takes care of seamless tiling.\n\n` +
    `Output canvas: 2400×800 (3:1).\n` +
    `Same painterly style as the concept. Do NOT render any text in the output. No labels, no borders.`
  );
}

export interface LayerArgs {
  prompt: string;
  tag: string;
  runDir: string;
  model: string;
  conceptImagePath: string;
  layer: WorldSpec["layers"][number];
}

export async function generateLayer(args: LayerArgs) {
  const { prompt, tag, runDir, model, conceptImagePath, layer } = args;
  const outPath = join(runDir, `layer_${tag}_${layer.id}.png`);
  return generateImageAsset({
    stage: `layer-${layer.id}`,
    userPrompt: prompt,
    promptText: buildLayerPrompt(layer),
    refs: [conceptImagePath],
    outPath,
    width: CANVAS_W,
    height: CANVAS_H,
    model,
    extra: {
      layer_id: layer.id,
      z_index: layer.z_index,
      parallax: layer.parallax,
      opaque: layer.opaque,
    },
  });
}

export async function generateAllLayers(args: {
  prompt: string;
  tag: string;
  runDir: string;
  model: string;
  conceptImagePath: string;
  layers: WorldSpec["layers"];
}) {
  return Promise.all(
    args.layers.map((layer) =>
      generateLayer({
        prompt: args.prompt,
        tag: args.tag,
        runDir: args.runDir,
        model: args.model,
        conceptImagePath: args.conceptImagePath,
        layer,
      }),
    ),
  );
}
