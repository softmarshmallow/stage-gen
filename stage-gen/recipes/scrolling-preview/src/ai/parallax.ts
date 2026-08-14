// Parallax depth layer generator (Wave 2).
//
// One per entry in world_spec.layers[]. Each entry is fully agent-designed
// (id, z_index, parallax, opaque, paint_region, description).
// The opaque layer IS the skybox (TC-030); other layers use the configured
// removable-background contract.
//
// Generates all L layers in parallel via generateAllLayers() — fans out from
// the stage runner.

import { join } from "node:path";
import type { WorldSpec } from "../schema/world.ts";
import type { TransparencyMode } from "../../../../src/config.ts";
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
      "OPAQUE BACKDROP — fill the ENTIRE canvas. Do not use a removable background field. " +
      "Every pixel is part of the layer. There is no transparent region. " +
      "This is the skybox / deepest backdrop the rest of the world sits in front of."
    );
  }
  return (
    "TRANSPARENCY-BEARING LAYER — paint only inside the region described above; everywhere else is the BACKGROUND FIELD. " +
    "Keep the painted layer visually isolated from that field so the configured transparency processor can remove it."
  );
}

export function buildLayerPrompt(layer: WorldSpec["layers"][number]): string {
  return (
    `Parallax depth layer for a 2D side-scrolling platformer.\n` +
    `The provided image is the world's concept art — match its painterly rendering, palette, lighting, and overall mood EXACTLY.\n\n` +
    `LAYER METADATA (designed by the world-design agent for this world):\n` +
    `  • Title: "${layer.title}"\n` +
    `  • Z-index: ${layer.z_index} (${layer.opaque ? "deepest backdrop" : "overlay; deeper layers show through outside the artwork bounds"})\n` +
    `  • Parallax: ${layer.parallax} (${depthPhrase(layer.parallax, layer.opaque)})\n\n` +
    `WHAT TO PAINT (one sentence): ${layer.description}\n\n` +
    `ARTWORK / FOREGROUND BOUNDS (paint_region; Y axis runs 0/5 top to 5/5 bottom, X axis 0/5 left to 5/5 right):\n` +
    `${layer.paint_region}\n\n` +
    `Honour these bounds literally. Visible layer artwork fills the described bounds with full painterly detail; outside those bounds the rules below apply.\n\n` +
    `${opaqueClause(layer.opaque)}\n\n` +
    `LOOPING — handled by the runtime. The image will be rendered twice with overlap and crossfaded at the L/R edges, so seams disappear automatically. You do NOT need to paint any loop-fade gradient, alpha taper, or "fade-to-edge" effect. Paint the content edge-to-edge as if the canvas were a single isolated panel; the runtime takes care of seamless tiling.\n\n` +
    `Output canvas: 2400×800 (3:1).\n` +
    `Same painterly style as the concept. Do NOT render any text in the output. No labels, no borders.`
  );
}

export function transparencyModeForLayer(
  layer: { opaque: boolean },
  mode: TransparencyMode,
): TransparencyMode | undefined {
  return layer.opaque ? undefined : mode;
}

export interface LayerArgs {
  prompt: string;
  tag: string;
  runDir: string;
  model: string;
  conceptImagePath: string;
  layer: WorldSpec["layers"][number];
  transparencyMode: TransparencyMode;
}

export async function generateLayer(args: LayerArgs) {
  const { prompt, tag, runDir, model, conceptImagePath, layer, transparencyMode } = args;
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
    ...(transparencyModeForLayer(layer, transparencyMode)
      ? { transparencyMode }
      : {}),
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
  transparencyMode: TransparencyMode;
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
        transparencyMode: args.transparencyMode,
      }),
    ),
  );
}
