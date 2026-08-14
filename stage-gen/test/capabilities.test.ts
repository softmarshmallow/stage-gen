import { afterAll, describe, expect, test } from "bun:test";
import { access, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  generateMusic,
  type MusicCapabilityRuntime,
} from "../src/capabilities.ts";

const roots: string[] = [];

afterAll(async () => {
  await Promise.all(roots.map((root) => rm(root, { recursive: true, force: true })));
});

describe("generic music capability", () => {
  test("normalizes to the authoritative output and removes the raw pair", async () => {
    const root = await mkdtemp(join(tmpdir(), "stage-gen-music-"));
    roots.push(root);
    const output = join(root, "final.mp3");
    let rawPath = "";
    const runtime: MusicCapabilityRuntime = {
      randomId: () => "test-id",
      async generate(request) {
        rawPath = request.artifactPath;
        expect(request.rights).toEqual({
          status: "unreviewed",
          license_id: null,
          notice: "No redistribution review has been recorded for this generated output.",
          attribution: [],
          basis: [],
          reviewed_at: null,
        });
        await writeFile(rawPath, "offline-raw-fixture");
        await writeFile(
          `${rawPath}.meta.json`,
          `${JSON.stringify({ rights: request.rights }, null, 2)}\n`,
        );
        return {
          bytes: new TextEncoder().encode("offline-raw-fixture"),
          mediaType: "audio/mpeg",
          provider: "openrouter",
          model: "test/music",
          attempts: 1,
          provenancePath: `${rawPath}.meta.json`,
          responseMetadata: {},
        };
      },
      async normalize(request) {
        expect(request.sourcePath).toBe(rawPath);
        expect(request.sourceProvenancePath).toBe(`${rawPath}.meta.json`);
        expect(request.artifactPath).toBe(output);
        const sourceSidecar = JSON.parse(await readFile(request.sourceProvenancePath, "utf8"));
        await writeFile(output, "offline-normalized-fixture");
        await writeFile(
          `${output}.meta.json`,
          `${JSON.stringify({ rights: sourceSidecar.rights }, null, 2)}\n`,
        );
        return {
          artifactPath: output,
          provenancePath: `${output}.meta.json`,
          bytes: new TextEncoder().encode("offline-normalized-fixture"),
          mediaType: "audio/mpeg",
          sourceSha256: "source-hash",
          outputSha256: "output-hash",
          durationSeconds: 30,
          integratedLufs: -16,
          truePeakDbtp: -1.5,
          ffmpegVersion: "ffmpeg version test",
        };
      },
    };

    const result = await generateMusic(
      "original instrumental loop",
      output,
      "mp3",
      {
        outDir: root,
        openRouterApiKey: "synthetic-test-key",
        imageModel: "test/image",
        textModel: "test/text",
        musicModel: "test/music",
        backgroundRemovalModel: "test/remove",
        transparencyMode: "ai",
        stageTimeoutMs: 1_000,
        capabilityTimeoutMs: 1_000,
      },
      undefined,
      runtime,
    );

    expect(result.artifactPath).toBe(output);
    expect(await readFile(output, "utf8")).toBe("offline-normalized-fixture");
    const finalSidecar = JSON.parse(await readFile(`${output}.meta.json`, "utf8"));
    expect(finalSidecar.rights.status).toBe("unreviewed");
    await expect(access(rawPath)).rejects.toThrow();
    await expect(access(`${rawPath}.meta.json`)).rejects.toThrow();
  });
});
