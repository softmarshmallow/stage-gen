import { afterEach, expect, test } from "bun:test";
import { mkdtemp, readFile, readdir, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import sharp from "sharp";
import { z } from "zod";
import { writeArtifactWithProvenance } from "@stage-gen/core";
import type {
  BackgroundMaskArtifact,
  BackgroundRemovalResult,
} from "@stage-gen/background-removal";
import { promptForImageAsset } from "../src/ai/image-helper.ts";
import {
  buildLayerPrompt,
  transparencyModeForLayer,
} from "../src/ai/parallax.ts";
import { TRANSPARENCY_PROMPT_FRAGMENTS } from "../src/ai/transparency-prompt.ts";
import {
  WORLD_SPEC_SYSTEM_PROMPT,
  buildWorldSpecUserPrompt,
} from "../src/ai/world-spec.ts";
import { applyTransparency } from "../src/post/transparency.ts";
import { WorldLayerSchema } from "../src/schema/world.ts";

const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(
    temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true })),
  );
});

test("world layer schema reaches provider-neutral AI, chroma, and opaque prompts", () => {
  const forbidden = /magenta|#ff00ff|chroma/i;
  const emittedSchema = JSON.stringify(z.toJSONSchema(WorldLayerSchema));
  expect(emittedSchema).toContain("Artwork/foreground bounds");
  expect(emittedSchema).not.toMatch(forbidden);

  const layer = WorldLayerSchema.parse({
    id: "near_ruins",
    title: "Near Ruins",
    z_index: 2,
    parallax: 0.8,
    opaque: false,
    paint_region:
      "Artwork occupies Y 2/5..5/5; the upper region remains outside the artwork bounds.",
    description: "Broken arches and wind-bent reeds form a bounded foreground silhouette.",
  });
  const body = buildLayerPrompt(layer);
  expect(body).toContain("ARTWORK / FOREGROUND BOUNDS");
  expect(body).not.toMatch(forbidden);

  const ai = promptForImageAsset(body, "ai");
  expect(ai).toContain("neutral grey");
  expect(ai).not.toMatch(forbidden);
  const chroma = promptForImageAsset(body, "chroma");
  expect(chroma).toContain("solid exact #FF00FF");
  expect(chroma).toContain("Never use #FF00FF anywhere on the foreground subject");

  const opaqueLayer = WorldLayerSchema.parse({
    id: "sky",
    title: "Sky",
    z_index: 0,
    parallax: 0,
    opaque: true,
    paint_region: "Artwork fills the full canvas.",
    description: "A luminous cloud bank fills the distant sky.",
  });
  const opaque = buildLayerPrompt(opaqueLayer);
  expect(opaque).toContain("OPAQUE BACKDROP");
  expect(opaque).not.toMatch(forbidden);
  expect(promptForImageAsset(opaque)).toBe(opaque);
  expect(transparencyModeForLayer(opaqueLayer, "ai")).toBeUndefined();
  expect(transparencyModeForLayer(layer, "ai")).toBe("ai");

  expect(WORLD_SPEC_SYSTEM_PROMPT).not.toMatch(forbidden);
  expect(buildWorldSpecUserPrompt("windswept ruins", 4, 2)).not.toMatch(
    forbidden,
  );
  expect(TRANSPARENCY_PROMPT_FRAGMENTS.ai).not.toMatch(forbidden);
  expect(TRANSPARENCY_PROMPT_FRAGMENTS.chroma).toMatch(/#ff00ff/i);
});

test("recipe prompt sources reserve key-colour language for the chroma fragment", async () => {
  const forbidden = /magenta|#ff00ff|chroma/i;
  const aiDirectory = resolve(import.meta.dir, "../src/ai");
  const promptSources = (await readdir(aiDirectory))
    .filter((name) => name.endsWith(".ts") && name !== "transparency-prompt.ts")
    .sort();
  for (const sourceName of promptSources) {
    expect(await readFile(join(aiDirectory, sourceName), "utf8")).not.toMatch(
      forbidden,
    );
  }
  expect(
    await readFile(resolve(import.meta.dir, "../src/schema/world.ts"), "utf8"),
  ).not.toMatch(forbidden);
});

test("chroma mode converts disconnected key regions to alpha and retains raw provenance", async () => {
  const directory = await temporaryDirectory("stage-gen-chroma-");
  const rawPath = join(directory, "sprite.raw.png");
  const canonicalPath = join(directory, "sprite.png");
  const rgba = Buffer.from([
    255, 0, 255, 255, 20, 30, 40, 255, 20, 30, 40, 255,
    20, 30, 40, 255, 255, 0, 255, 255, 20, 30, 40, 255,
    20, 30, 40, 255, 20, 30, 40, 255, 20, 30, 40, 255,
  ]);
  const rawBytes = new Uint8Array(
    await sharp(rgba, { raw: { width: 3, height: 3, channels: 4 } }).png().toBuffer(),
  );
  await writeRawPair(rawPath, rawBytes);

  const result = await applyTransparency({
    mode: "chroma",
    rawPath,
    canonicalPath,
    width: 3,
    height: 3,
    stage: "test-chroma",
    control: requestControl(),
  });

  const decoded = await sharp(await readFile(canonicalPath))
    .ensureAlpha()
    .raw()
    .toBuffer();
  expect(decoded[3]).toBe(0);
  expect(decoded[4 * 4 + 3]).toBe(0);
  expect(decoded[1 * 4 + 3]).toBe(255);
  expect(result.transparentPixels).toBe(2);
  expect(await fileExists(rawPath)).toBe(true);
  expect(await fileExists(`${rawPath}.meta.json`)).toBe(true);
  const provenance = JSON.parse(await readFile(result.metaPath, "utf8"));
  expect(provenance.prompt).toBe("source prompt");
  expect(provenance.params.transparency).toMatchObject({
    mode: "chroma",
    retained_raw_path: rawPath,
    canonical_path: canonicalPath,
  });
  expect(provenance.params.transparency.processor).toMatchObject({
    method: "global-color-distance-to-alpha",
    connectivity: "none",
  });
  expect(provenance.validation).toMatchObject({
    alpha_nontrivial: true,
    transparent_pixels: 2,
    nontransparent_pixels: 7,
  });
  expect(provenance.artifact.sha256).toBe(provenance.validation.output_sha256);
});

test("ai mode prefers the returned mask, preserves raw RGB, and chains remover provenance", async () => {
  const directory = await temporaryDirectory("stage-gen-ai-alpha-");
  const rawPath = join(directory, "sprite.raw.png");
  const canonicalPath = join(directory, "sprite.png");
  const rawRgba = Buffer.from([
    90, 40, 10, 255, 90, 40, 10, 255,
    90, 40, 10, 255, 90, 40, 10, 255,
  ]);
  const rawBytes = new Uint8Array(
    await sharp(rawRgba, { raw: { width: 2, height: 2, channels: 4 } }).png().toBuffer(),
  );
  await writeRawPair(rawPath, rawBytes);
  const maskBytes = new Uint8Array(
    await sharp(Buffer.from([0, 255, 255, 255]), {
      raw: { width: 2, height: 2, channels: 1 },
    })
      .png()
      .toBuffer(),
  );
  const mask: BackgroundMaskArtifact = {
    url: "data:image/png;base64,masked",
    bytes: maskBytes,
    mediaType: "image/png",
    width: 2,
    height: 2,
  };
  let calls = 0;
  const remover = {
    async remove(request: Parameters<import("@stage-gen/background-removal").FalBackgroundRemover["remove"]>[0]) {
      calls += 1;
      expect(request.outputMask).toBe(true);
      expect(request.metadata).toMatchObject({ transparency_mode: "ai" });
      await request.validate?.(
        { bytes: rawBytes, mediaType: "image/png" },
        { mask },
      );
      const provenancePath = await writeArtifactWithProvenance(
        request.artifactPath,
        { bytes: rawBytes, mediaType: "image/png" },
        {
          provider: "fal",
          model: "test-remover",
          seed: null,
          prompt: "remove test background",
          refs: [rawPath],
          params: {
            metadata: request.metadata ?? {},
            output_mask: true,
          },
          validation: {
            dimensions_preserved: true,
            alpha_nontrivial: true,
            mask_used: true,
          },
          component: { name: "test-remover", version: "1" },
          tool: { name: "test-remover-tool", version: "1" },
          attempts: 2,
        },
      );
      return {
        bytes: rawBytes,
        mediaType: "image/png",
        sourceUrl: "data:image/png;base64,removed",
        width: 2,
        height: 2,
        mask,
        provider: "fal",
        model: "test-remover",
        attempts: 2,
        provenancePath,
        responseMetadata: {},
      } satisfies BackgroundRemovalResult;
    },
  };

  const result = await applyTransparency({
    mode: "ai",
    rawPath,
    canonicalPath,
    width: 2,
    height: 2,
    stage: "test-ai",
    remover,
    control: requestControl(),
  });

  expect(calls).toBe(1);
  const decoded = await sharp(await readFile(canonicalPath))
    .ensureAlpha()
    .raw()
    .toBuffer();
  expect([...decoded.slice(0, 3)]).toEqual([90, 40, 10]);
  expect(decoded[3]).toBe(0);
  expect(decoded[7]).toBe(255);
  const provenance = JSON.parse(await readFile(result.metaPath, "utf8"));
  expect(provenance.params.transparency.removal).toMatchObject({
    provider: "fal",
    model: "test-remover",
    attempts: 2,
    maskUsed: true,
    provenance: {
      provider: "fal",
      model: "test-remover",
      attempts: 2,
      validation: {
        dimensions_preserved: true,
        alpha_nontrivial: true,
        mask_used: true,
      },
    },
  });
  expect(provenance.response.transparency.removal_provenance).toBe("inline");
  const referencedPaths = collectAbsolutePaths(provenance);
  expect(referencedPaths.length).toBeGreaterThan(0);
  for (const path of referencedPaths) {
    expect(await fileExists(path)).toBe(true);
    expect(path).not.toContain(".removal-");
  }
  const leftovers = (await readdir(directory)).filter(
    (name) => name.includes(".removal-"),
  );
  expect(leftovers).toEqual([]);
  expect(provenance.validation.alpha_nontrivial).toBe(true);
});

test("ai mode fails closed and never creates a canonical pair after removal failure", async () => {
  const directory = await temporaryDirectory("stage-gen-ai-failure-");
  const rawPath = join(directory, "sprite.raw.png");
  const canonicalPath = join(directory, "sprite.png");
  const rawBytes = new Uint8Array(
    await sharp({
      create: { width: 2, height: 2, channels: 4, background: "grey" },
    })
      .png()
      .toBuffer(),
  );
  await writeRawPair(rawPath, rawBytes);
  await expect(
    applyTransparency({
      mode: "ai",
      rawPath,
      canonicalPath,
      width: 2,
      height: 2,
      stage: "test-failure",
      remover: { remove: async () => { throw new Error("provider unavailable"); } },
      control: requestControl(),
    }),
  ).rejects.toThrow("provider unavailable");
  expect(await fileExists(canonicalPath)).toBe(false);
  expect(await fileExists(`${canonicalPath}.meta.json`)).toBe(false);
  expect(await fileExists(rawPath)).toBe(true);
});

async function writeRawPair(path: string, bytes: Uint8Array): Promise<void> {
  await writeArtifactWithProvenance(
    path,
    { bytes, mediaType: "image/png" },
    {
      provider: "openrouter",
      model: "test-image-model",
      seed: null,
      prompt: "source prompt",
      refs: [],
      params: { metadata: { stage: "test" } },
      validation: { exact_contract_dimensions: true },
      component: { name: "test-generator", version: "1" },
      tool: { name: "test-tool", version: "1" },
      attempts: 2,
    },
  );
}

function requestControl(): { signal: AbortSignal; timeoutMs: number } {
  return { signal: new AbortController().signal, timeoutMs: 1_000 };
}

async function temporaryDirectory(prefix: string): Promise<string> {
  const path = await mkdtemp(join(tmpdir(), prefix));
  temporaryDirectories.push(path);
  return path;
}

async function fileExists(path: string): Promise<boolean> {
  try {
    return (await stat(path)).isFile();
  } catch {
    return false;
  }
}

function collectAbsolutePaths(value: unknown, paths = new Set<string>()): string[] {
  if (typeof value === "string") {
    if (value.startsWith("/")) paths.add(value);
  } else if (Array.isArray(value)) {
    for (const entry of value) collectAbsolutePaths(entry, paths);
  } else if (value && typeof value === "object") {
    for (const entry of Object.values(value as Record<string, unknown>)) {
      collectAbsolutePaths(entry, paths);
    }
  }
  return [...paths];
}
