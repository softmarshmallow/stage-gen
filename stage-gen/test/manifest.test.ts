import { createHash } from "node:crypto";
import { afterAll, describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { ArtifactRights } from "@stage-gen/core";
import { writeScrollingPreviewManifest } from "../recipes/scrolling-preview/src/manifest.ts";

const roots: string[] = [];
const encoder = new TextEncoder();

afterAll(async () => {
  await Promise.all(roots.map((root) => rm(root, { recursive: true, force: true })));
});

describe("scrolling-preview manifest music fallback", () => {
  test("copies only an approved digest-matched fallback pair and its rights notice", async () => {
    const root = await fixtureRoot();
    const fallback = await writeFallback(root);
    const runDir = join(root, "run");

    const result = await writeScrollingPreviewManifest({
      runDir,
      tag: "neutral-run",
      fallbackMusicPath: fallback.path,
    });
    const manifest = JSON.parse(await readFile(result.manifestPath, "utf8"));

    expect(result.musicSource).toBe("generated-fallback");
    expect(result.musicRightsStatus).toBe("redistribution-approved");
    expect(await readFile(result.musicPath, "utf8")).toBe(fallback.text);
    expect(await readFile(result.musicProvenancePath, "utf8")).toBe(fallback.sidecarText);
    expect(await readFile(result.musicNoticePath!, "utf8")).toBe("Synthetic asset notice.\n");
    expect(manifest.music).toEqual({
      path: "music_neutral-run.mp3",
      provenancePath: "music_neutral-run.mp3.meta.json",
      source: "generated-fallback",
      generationCapability: "generate-music",
      rightsStatus: "redistribution-approved",
      rightsNoticePath: "fallback.LICENSE.md",
    });
    expect(manifest.artifacts).toContain("fallback.LICENSE.md");
  });

  test("preserves an existing per-run unreviewed music pair without requiring a fallback", async () => {
    const root = await fixtureRoot();
    const runDir = join(root, "run");
    const musicPath = join(runDir, "music_custom-run.mp3");
    const sidecarText = `${JSON.stringify({
      rights: rightsFor("unreviewed"),
    }, null, 2)}\n`;
    await writeFile(musicPath, "per-run");
    await writeFile(`${musicPath}.meta.json`, sidecarText);

    const result = await writeScrollingPreviewManifest({
      runDir,
      tag: "custom-run",
      fallbackMusicPath: join(root, "missing-fallback.mp3"),
    });
    const manifest = JSON.parse(await readFile(result.manifestPath, "utf8"));

    expect(result.musicSource).toBe("per-run");
    expect(result.musicRightsStatus).toBe("unreviewed");
    expect(result.musicNoticePath).toBeUndefined();
    expect(await readFile(result.musicPath, "utf8")).toBe("per-run");
    expect(await readFile(result.musicProvenancePath, "utf8")).toBe(sidecarText);
    expect(manifest.music.rightsStatus).toBe("unreviewed");
    expect(manifest.music.rightsNoticePath).toBeUndefined();
  });

  for (const status of ["unreviewed", "restricted"] as const) {
    test(`rejects a ${status} repository fallback`, async () => {
      const root = await fixtureRoot();
      const fallback = await writeFallback(root, { status });

      await expect(
        writeScrollingPreviewManifest({
          runDir: join(root, "run"),
          tag: `${status}-run`,
          fallbackMusicPath: fallback.path,
        }),
      ).rejects.toThrow("not publication-approved");
      await expect(readFile(join(root, "run", `music_${status}-run.mp3`))).rejects.toThrow();
    });
  }

  test("rejects a fallback whose artifact digest does not match", async () => {
    const root = await fixtureRoot();
    const fallback = await writeFallback(root, { sha256: "0".repeat(64) });

    await expect(
      writeScrollingPreviewManifest({
        runDir: join(root, "run"),
        tag: "bad-digest",
        fallbackMusicPath: fallback.path,
      }),
    ).rejects.toThrow("artifact digest does not match");
  });

  test("rejects an approved fallback whose notice file is missing", async () => {
    const root = await fixtureRoot();
    const fallback = await writeFallback(root, { writeNotice: false });

    await expect(
      writeScrollingPreviewManifest({
        runDir: join(root, "run"),
        tag: "missing-notice",
        fallbackMusicPath: fallback.path,
      }),
    ).rejects.toThrow("rights notice is missing");
  });

  test("rejects absolute, temporary, and file input references", async () => {
    for (const [suffix, inputRef] of [
      ["absolute", "/tmp/raw-music.mp3"],
      ["temporary", "tmp:raw-music"],
      ["file-uri", "file:///tmp/raw-music.mp3"],
    ] as const) {
      const root = await fixtureRoot();
      const fallback = await writeFallback(root, { inputRef });
      await expect(
        writeScrollingPreviewManifest({
          runDir: join(root, "run"),
          tag: suffix,
          fallbackMusicPath: fallback.path,
        }),
      ).rejects.toThrow("stable non-temporary reference");
    }
  });

  test("reports an actionable error when neither per-run nor approved fallback music exists", async () => {
    const root = await fixtureRoot();
    await expect(
      writeScrollingPreviewManifest({
        runDir: join(root, "run"),
        tag: "missing-music",
        fallbackMusicPath: join(root, "missing.mp3"),
      }),
    ).rejects.toThrow("generate-music capability");
  });
});

interface FallbackOptions {
  status?: ArtifactRights["status"];
  sha256?: string;
  writeNotice?: boolean;
  inputRef?: string;
}

async function writeFallback(
  root: string,
  options: FallbackOptions = {},
): Promise<{ path: string; text: string; sidecarText: string }> {
  const path = join(root, "fallback.mp3");
  const text = "offline-fallback-fixture";
  const bytes = encoder.encode(text);
  const actualSha256 = createHash("sha256").update(bytes).digest("hex");
  const rights = rightsFor(options.status ?? "redistribution-approved");
  const sidecarText = `${JSON.stringify({
    schema_version: 1,
    artifact: {
      sha256: options.sha256 ?? actualSha256,
      bytes: bytes.length,
      media_type: "audio/mpeg",
    },
    references: [],
    refs: [],
    inputs: [
      {
        ref: options.inputRef ?? `sha256:${actualSha256}`,
        sha256: actualSha256,
        source: "content",
        bytes: bytes.length,
        media_type: "audio/mpeg",
      },
    ],
    rights,
  }, null, 2)}\n`;
  await writeFile(path, bytes);
  await writeFile(`${path}.meta.json`, sidecarText);
  if (options.writeNotice !== false) {
    await writeFile(join(root, "fallback.LICENSE.md"), "Synthetic asset notice.\n");
  }
  return { path, text, sidecarText };
}

function rightsFor(status: ArtifactRights["status"]): ArtifactRights {
  if (status === "unreviewed") {
    return {
      status,
      license_id: null,
      notice: "No redistribution review recorded.",
      attribution: [],
      basis: [],
      reviewed_at: null,
    };
  }
  if (status === "restricted") {
    return {
      status,
      license_id: null,
      notice: "fallback.LICENSE.md",
      attribution: [],
      basis: ["test-rights-review"],
      reviewed_at: "2026-08-14T00:00:00.000Z",
    };
  }
  return {
    status,
    license_id: "LicenseRef-Synthetic-Test",
    notice: "fallback.LICENSE.md",
    attribution: [],
    basis: ["test-rights-review"],
    reviewed_at: "2026-08-14T00:00:00.000Z",
  };
}

async function fixtureRoot(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), "stage-gen-manifest-"));
  roots.push(root);
  await mkdir(join(root, "run"));
  return root;
}
