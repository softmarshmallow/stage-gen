import { afterEach, expect, test } from "bun:test";
import { createHash } from "node:crypto";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { writeArtifactWithProvenance } from "@stage-gen/core";
import { writeScrollingPreviewManifest } from "../src/manifest.ts";

const temporaryDirectories: string[] = [];
const png = Uint8Array.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

afterEach(async () => {
  await Promise.all(
    temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true })),
  );
});

test("recipe manifest classifies generated, composite, sliced, and opaque images from provenance", async () => {
  const directory = await mkdtemp(join(tmpdir(), "stage-gen-manifest-transparency-"));
  temporaryDirectories.push(directory);
  const rawPath = join(directory, "sprite.raw.png");
  const canonicalPath = join(directory, "sprite.png");
  const combinedPath = join(directory, "character_fixture_combined.png");
  const slicedPath = join(directory, "character_fixture-fromcombined_idle.png");
  const conceptPath = join(directory, "concept.png");
  const backdropPath = join(directory, "layer_fixture_sky.png");
  const artifactSha256 = createHash("sha256").update(png).digest("hex");
  await writeArtifactWithProvenance(rawPath, { bytes: png, mediaType: "image/png" }, baseMeta());
  await writeArtifactWithProvenance(
    canonicalPath,
    { bytes: png, mediaType: "image/png" },
    {
      ...baseMeta(),
      params: {
        transparency: {
          mode: "chroma",
          retained_raw_path: rawPath,
          canonical_path: canonicalPath,
          raw_sha256: artifactSha256,
          output_sha256: artifactSha256,
          processor: { kind: "chroma-key" },
        },
      },
      tool: { name: "global-chroma-alpha", version: "1" },
    },
  );
  await writeArtifactWithProvenance(
    combinedPath,
    { bytes: png, mediaType: "image/png" },
    {
      ...baseMeta(),
      refs: [canonicalPath],
      params: {
        stage: "character-master",
        transparency: {
          mode: "chroma",
          processor: "deterministic-alpha-composite",
          source_paths: { idle: canonicalPath },
          source_hashes: [{ path: canonicalPath, sha256: artifactSha256 }],
          output_sha256: artifactSha256,
        },
      },
      tool: { name: "sharp-alpha-composite", version: "test" },
    },
  );
  await writeArtifactWithProvenance(
    slicedPath,
    { bytes: png, mediaType: "image/png" },
    {
      ...baseMeta(),
      refs: [combinedPath],
      params: {
        stage: "post-split",
        transparency: {
          mode: "chroma",
          processor: "deterministic-png-slice",
          source_path: combinedPath,
          source_sha256: artifactSha256,
          output_sha256: artifactSha256,
        },
      },
      tool: { name: "sharp-png-slice", version: "test" },
    },
  );
  await writeArtifactWithProvenance(
    conceptPath,
    { bytes: png, mediaType: "image/png" },
    { ...baseMeta(), params: { metadata: { stage: "concept" } } },
  );
  await writeArtifactWithProvenance(
    backdropPath,
    { bytes: png, mediaType: "image/png" },
    {
      ...baseMeta(),
      params: { metadata: { stage: "layer-sky", opaque: true } },
    },
  );
  const fallback = join(directory, "fallback.mp3");
  await writeArtifactWithProvenance(
    fallback,
    { bytes: Uint8Array.from([1, 2, 3]), mediaType: "audio/mpeg" },
    {
      provider: "test",
      model: "test-music",
      prompt: "test music",
      attempts: 1,
      rights: {
        status: "redistribution-approved",
        license_id: "LicenseRef-Synthetic-Test",
        notice: "fallback.LICENSE.md",
        attribution: [],
        basis: ["test-rights-review"],
        reviewed_at: "2026-08-14T00:00:00.000Z",
      },
    },
  );
  await writeFile(join(directory, "fallback.LICENSE.md"), "Synthetic asset notice.\n");

  const result = await writeScrollingPreviewManifest({
    runDir: directory,
    tag: "fixture-chroma",
    transparencyMode: "chroma",
    fallbackMusicPath: fallback,
  });
  const manifest = JSON.parse(await readFile(result.manifestPath, "utf8"));
  expect(manifest.schemaVersion).toBe(2);
  expect(manifest.transparencyMode).toBe("chroma");
  expect(manifest.artifacts.some((path: string) => path.includes(".raw.png"))).toBe(false);
  const sprite = manifest.canonicalArtifacts.find(
    (artifact: { path: string }) => artifact.path === "sprite.png",
  );
  expect(sprite).toMatchObject({
    path: "sprite.png",
    provenancePath: "sprite.png.meta.json",
    transparency: {
      mode: "chroma",
      canonicalPath: "sprite.png",
      retainedRawPath: "sprite.raw.png",
      rawProvenancePath: "sprite.raw.png.meta.json",
      derivation: { kind: "chroma-key", sourceSha256: artifactSha256 },
      lineage: {
        kind: "generated",
        sourcePaths: ["sprite.raw.png"],
        sourceProvenancePaths: ["sprite.raw.png.meta.json"],
      },
    },
  });
  const combined = manifest.canonicalArtifacts.find(
    (artifact: { path: string }) => artifact.path === "character_fixture_combined.png",
  );
  expect(combined).toMatchObject({
    transparency: {
      mode: "chroma",
      derivation: { kind: "alpha-composite", outputSha256: artifactSha256 },
      lineage: {
        kind: "derived",
        sourcePaths: ["sprite.png"],
        sourceProvenancePaths: ["sprite.png.meta.json"],
      },
    },
  });
  const sliced = manifest.canonicalArtifacts.find(
    (artifact: { path: string }) =>
      artifact.path === "character_fixture-fromcombined_idle.png",
  );
  expect(sliced).toMatchObject({
    transparency: {
      mode: "chroma",
      derivation: { kind: "png-slice", sourceSha256: artifactSha256 },
      lineage: {
        kind: "derived",
        sourcePaths: ["character_fixture_combined.png"],
        sourceProvenancePaths: ["character_fixture_combined.png.meta.json"],
      },
    },
  });
  const concept = manifest.canonicalArtifacts.find(
    (artifact: { path: string }) => artifact.path === "concept.png",
  );
  const backdrop = manifest.canonicalArtifacts.find(
    (artifact: { path: string }) => artifact.path === "layer_fixture_sky.png",
  );
  expect(concept.transparency).toBeUndefined();
  expect(backdrop.transparency).toBeUndefined();
  expect(
    manifest.canonicalArtifacts.some((artifact: { path: string }) =>
      artifact.path.includes(".raw.png"),
    ),
  ).toBe(false);
});

function baseMeta() {
  return {
    provider: "test",
    model: "test-model",
    seed: null,
    prompt: "test prompt",
    refs: [],
    params: {},
    validation: {},
    component: { name: "test", version: "1" },
    tool: { name: "test", version: "1" },
    attempts: 1,
  } as const;
}
