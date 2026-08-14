// One-off: re-run only the tileset generator for an existing tag.
// Reads the world_spec for context shaping (not required by the generator),
// invokes generateTileset directly, prints the new image + meta paths and
// the attempts count from the meta sidecar.
//
// Usage: bun stage-gen/benchmarks/scrolling-preview/regen-tileset.ts <tag>

import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { resolve, join } from "node:path";
import { loadConfig } from "../../src/config.ts";
import { withAiCapabilities } from "../../recipes/scrolling-preview/src/ai/client.ts";
import { generateTileset } from "../../recipes/scrolling-preview/src/ai/tileset.ts";

const tag = process.argv[2];
if (!tag) {
  console.error("usage: bun stage-gen/benchmarks/scrolling-preview/regen-tileset.ts <tag>");
  process.exit(2);
}

const config = loadConfig({ require: ["image-generation"] });

const repoRoot = resolve(import.meta.dir, "../../..");
const runDir = resolve(config.outDir, tag);
const conceptImagePath = join(runDir, `concept_${tag}.png`);
const recipeWireframe = resolve(
  import.meta.dir,
  "../../recipes/scrolling-preview/templates/wireframe.png",
);
const wireframePath = existsSync(recipeWireframe)
  ? recipeWireframe
  : join(repoRoot, "fixtures/image_gen_templates/wireframe.png");

const started = Date.now();
console.error(`[regen-tileset] tag=${tag}`);
console.error(`[regen-tileset] runDir=${runDir}`);
console.error(`[regen-tileset] model=${config.imageModel}`);

const res = await withAiCapabilities(config, new AbortController().signal, () =>
  generateTileset({
    prompt: "regen tileset (re-run after vision FAIL on TC-033)",
    tag,
    runDir,
    model: config.imageModel,
    transparencyMode: config.transparencyMode,
    conceptImagePath,
    wireframePath,
  }),
);

const meta = JSON.parse(await readFile(res.metaPath, "utf8"));
const elapsed = ((Date.now() - started) / 1000).toFixed(1);

console.log(JSON.stringify({
  imagePath: res.imagePath,
  metaPath: res.metaPath,
  attempts: meta?.attempts,
  bytes: meta?.response?.bytes,
  width: meta?.params?.metadata?.requested_width,
  height: meta?.params?.metadata?.requested_height,
  elapsed_s: Number(elapsed),
}, null, 2));
