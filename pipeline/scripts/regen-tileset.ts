// One-off: re-run only the tileset generator for an existing tag.
// Reads the world_spec for context shaping (not required by the generator),
// invokes generateTileset directly, prints the new image + meta paths and
// the attempts count from the meta sidecar.
//
// Usage: bun run pipeline/scripts/regen-tileset.ts <tag>

import { readFile } from "node:fs/promises";
import { resolve, join } from "node:path";
import { loadEnv } from "../src/env.ts";
import { configureAi } from "../src/ai/client.ts";
import { generateTileset } from "../src/ai/tileset.ts";

const tag = process.argv[2];
if (!tag) {
  console.error("usage: bun run pipeline/scripts/regen-tileset.ts <tag>");
  process.exit(2);
}

const env = loadEnv();
configureAi(env);

const repoRoot = resolve(import.meta.dir, "../..");
const runDir = join(repoRoot, env.OUT_DIR, tag);
const conceptImagePath = join(runDir, `concept_${tag}.png`);
const wireframePath = join(
  repoRoot,
  "fixtures/image_gen_templates/wireframe.png",
);

const started = Date.now();
console.error(`[regen-tileset] tag=${tag}`);
console.error(`[regen-tileset] runDir=${runDir}`);
console.error(`[regen-tileset] model=${env.IMAGE_MODEL}`);

const res = await generateTileset({
  prompt: "regen tileset (re-run after vision FAIL on TC-033)",
  tag,
  runDir,
  model: env.IMAGE_MODEL,
  conceptImagePath,
  wireframePath,
});

const meta = JSON.parse(await readFile(res.metaPath, "utf8"));
const elapsed = ((Date.now() - started) / 1000).toFixed(1);

console.log(JSON.stringify({
  imagePath: res.imagePath,
  metaPath: res.metaPath,
  attempts: meta?.extra?.attempts,
  bytes: meta?.extra?.bytes,
  width: meta?.extra?.width,
  height: meta?.extra?.height,
  elapsed_s: Number(elapsed),
}, null, 2));
