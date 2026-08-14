import { afterEach, describe, expect, test } from "bun:test";
import { mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { sha256Hex, writeArtifactWithProvenance } from "@stage-gen/core";
import {
  createFfmpegAudioNormalizer,
  runProcessCommand,
  type AudioProcessRunner,
} from "../src/index.ts";

const temporaryDirectories: string[] = [];
const mp3Bytes = Uint8Array.from([
  0x49, 0x44, 0x33, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0xff, 0xfb, 0x90, 0x64,
]);

afterEach(async () => {
  await Promise.all(
    temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true, force: true })),
  );
});

test("normalizes a generated artifact and writes one combined reproducible sidecar", async () => {
  const directory = await mkdtemp(join(tmpdir(), "stage-gen-normalize-"));
  temporaryDirectories.push(directory);
  const sourcePath = join(directory, "raw.mp3");
  const sourceProvenancePath = await writeArtifactWithProvenance(
    sourcePath,
    { bytes: mp3Bytes, mediaType: "audio/mpeg" },
    {
      provider: "provider",
      model: "author/music-model",
      seed: 1234,
      prompt: "Original instrumental test input",
      refs: ["brief.json"],
      params: { output_format: "mp3", temperature: 0.5 },
      validation: { signature: "matched" },
      component: { name: "@stage-gen/music-generation", version: "0.0.0" },
      tool: { name: "stage-gen", version: "0.0.0" },
      timestamp: "2026-08-14T01:00:00.000Z",
      attempts: 2,
      response: { source_shape: "sse" },
      rights: {
        status: "unreviewed",
        license_id: null,
        notice: "No redistribution approval has been recorded.",
        attribution: [],
        basis: [],
        reviewed_at: null,
      },
    },
  );
  const outputPath = join(directory, "normalized.mp3");
  let measurements = 0;
  const run: AudioProcessRunner = async (command, args, options) => {
    expect(options.timeoutMs).toBe(4_000);
    expect(options.signal).toBeUndefined();
    if (command === "ffprobe") {
      return {
        stdout: JSON.stringify({
          format: { format_name: "mp3", duration: "52.01", bit_rate: "192000" },
        }),
        stderr: "",
      };
    }
    if (args[0] === "-version") {
      return { stdout: "ffmpeg version 8.0-test\n", stderr: "" };
    }
    if (args.at(-1) === "-") {
      measurements += 1;
      const values = measurements === 1
        ? { input_i: "-20.00", input_tp: "-3.00", input_lra: "4.00", input_thresh: "-30.00", target_offset: "0.10" }
        : { input_i: "-16.10", input_tp: "-1.40", input_lra: "4.10", input_thresh: "-26.00", target_offset: "0.00" };
      return { stdout: "", stderr: `measurement\n${JSON.stringify(values, null, 2)}\n` };
    }
    const tempOutput = args.at(-1);
    if (!tempOutput) throw new Error("normalization output path missing");
    await writeFile(tempOutput, mp3Bytes);
    return { stdout: "", stderr: "" };
  };
  const normalizer = createFfmpegAudioNormalizer({
    run,
    timeoutMs: 4_000,
    now: () => new Date("2026-08-14T02:00:00.000Z"),
  });

  const result = await normalizer.normalize({
    sourcePath,
    sourceProvenancePath,
    artifactPath: outputPath,
  });

  expect(result.truePeakDbtp).toBe(-1.4);
  expect(result.integratedLufs).toBe(-16.1);
  expect(result.durationSeconds).toBe(52.01);
  expect(result.sourceSha256).toBe(sha256Hex(mp3Bytes));
  expect(result.outputSha256).toBe(sha256Hex(mp3Bytes));
  expect(new Uint8Array(await readFile(outputPath))).toEqual(mp3Bytes);
  const sidecar = JSON.parse(await readFile(result.provenancePath, "utf8"));
  expect(sidecar).toMatchObject({
    provider: "provider",
    model: "author/music-model",
    seed: 1234,
    prompt: "Original instrumental test input",
    references: ["brief.json"],
    attempts: 2,
    retries: 1,
    params: {
      generation: { output_format: "mp3", temperature: 0.5 },
      generation_timestamp: "2026-08-14T01:00:00.000Z",
      postprocess: {
        processor: "ffmpeg",
        version: "ffmpeg version 8.0-test",
        filter: "loudnorm",
        filter_params: { true_peak_dbtp: -1.5, linear: true },
      },
    },
    validation: {
      postprocess: {
        non_silent: true,
        true_peak_dbtp: -1.4,
        max_true_peak_dbtp: -1,
        duration_seconds: 52.01,
      },
    },
    response: {
      postprocess: {
        source_sha256: sha256Hex(mp3Bytes),
        output_sha256: sha256Hex(mp3Bytes),
      },
    },
  });
  expect(sidecar.artifact.sha256).toBe(sha256Hex(mp3Bytes));
  expect(sidecar.rights).toEqual({
    status: "unreviewed",
    license_id: null,
    notice: "No redistribution approval has been recorded.",
    attribution: [],
    basis: [],
    reviewed_at: null,
  });
  expect(sidecar.inputs.at(-1)).toMatchObject({
    ref: `sha256:${sha256Hex(mp3Bytes)}`,
    sha256: sha256Hex(mp3Bytes),
    source: "content",
  });
  expect(JSON.stringify(sidecar)).not.toContain(directory);
  expect((await readdir(directory)).some((entry) => entry.includes(".normalized."))).toBe(false);
});

test("rejects digest drift and unsafe source references before invoking audio tools", async () => {
  const directory = await mkdtemp(join(tmpdir(), "stage-gen-normalize-guard-"));
  temporaryDirectories.push(directory);
  const sourcePath = join(directory, "raw.mp3");
  const sourceProvenancePath = await writeArtifactWithProvenance(
    sourcePath,
    { bytes: mp3Bytes, mediaType: "audio/mpeg" },
    {
      provider: "provider",
      model: "author/music-model",
      prompt: "Original instrumental test input",
      attempts: 1,
    },
  );
  let processCalls = 0;
  const normalizer = createFfmpegAudioNormalizer({
    run: async () => {
      processCalls += 1;
      throw new Error("audio tool must not run");
    },
  });

  await writeFile(sourcePath, Uint8Array.from([...mp3Bytes, 0x00]));
  await expect(normalizer.normalize({
    sourcePath,
    sourceProvenancePath,
    artifactPath: join(directory, "digest-output.mp3"),
  })).rejects.toThrow("does not match its provenance digest");
  expect(processCalls).toBe(0);

  await writeFile(sourcePath, mp3Bytes);
  const approvedProvenancePath = await writeArtifactWithProvenance(
    sourcePath,
    { bytes: mp3Bytes, mediaType: "audio/mpeg" },
    {
      provider: "provider",
      model: "author/music-model",
      prompt: "Original instrumental test input",
      attempts: 1,
      rights: {
        status: "redistribution-approved",
        license_id: "LicenseRef-Project",
        notice: "RIGHTS.md",
        attribution: [],
        basis: ["Recorded project authorization."],
        reviewed_at: "2026-08-14T10:00:00.000Z",
      },
    },
  );
  await expect(normalizer.normalize({
    sourcePath,
    sourceProvenancePath: approvedProvenancePath,
    sourceRef: "/Users/private/raw.mp3",
    artifactPath: join(directory, "private-ref-output.mp3"),
  })).rejects.toThrow("unsafe reference");
  expect(processCalls).toBe(0);

  await expect(normalizer.normalize({
    sourcePath,
    sourceProvenancePath: approvedProvenancePath,
    sourceRef: "/tmp/raw.mp3",
    artifactPath: join(directory, "temp-ref-output.mp3"),
  })).rejects.toThrow("temporary path");
  expect(processCalls).toBe(0);
});

test("keeps absent rights absent and persists an explicit portable sourceRef", async () => {
  const directory = await mkdtemp(join(tmpdir(), "stage-gen-normalize-portable-"));
  temporaryDirectories.push(directory);
  const sourcePath = join(directory, "raw.mp3");
  const sourceProvenancePath = await writeArtifactWithProvenance(
    sourcePath,
    { bytes: mp3Bytes, mediaType: "audio/mpeg" },
    {
      provider: "provider",
      model: "author/music-model",
      prompt: "Original instrumental test input",
      attempts: 1,
    },
  );
  const outputPath = join(directory, "normalized.mp3");
  const result = await createFfmpegAudioNormalizer({
    run: successfulAudioRunner(mp3Bytes),
    now: () => new Date("2026-08-14T11:00:00.000Z"),
  }).normalize({
    sourcePath,
    sourceProvenancePath,
    sourceRef: "assets/music/raw-source.mp3",
    artifactPath: outputPath,
  });

  const sidecar = JSON.parse(await readFile(result.provenancePath, "utf8"));
  expect(sidecar.rights).toBeUndefined();
  expect(sidecar.inputs.at(-1).ref).toBe("assets/music/raw-source.mp3");
  expect(JSON.stringify(sidecar)).not.toContain(directory);
});

describe("runProcessCommand", () => {
  test("enforces its timeout", async () => {
    try {
      await runProcessCommand(
        process.execPath,
        ["-e", "setTimeout(() => {}, 1000)"],
        { timeoutMs: 20 },
      );
      throw new Error("expected process timeout");
    } catch (error) {
      expect(String(error)).toContain("timed out");
    }
  });

  test("propagates cancellation to the child process", async () => {
    const controller = new AbortController();
    const pending = runProcessCommand(
      process.execPath,
      ["-e", "setTimeout(() => {}, 1000)"],
      { timeoutMs: 2_000, signal: controller.signal },
    );
    setTimeout(() => controller.abort(), 20);
    try {
      await pending;
      throw new Error("expected process cancellation");
    } catch (error) {
      expect((error as Error).name).toBe("AbortError");
    }
  });
});

function successfulAudioRunner(bytes: Uint8Array): AudioProcessRunner {
  let measurements = 0;
  return async (command, args) => {
    if (command === "ffprobe") {
      return {
        stdout: JSON.stringify({
          format: { format_name: "mp3", duration: "30.0", bit_rate: "192000" },
        }),
        stderr: "",
      };
    }
    if (args[0] === "-version") {
      return { stdout: "ffmpeg version 8.0-test\n", stderr: "" };
    }
    if (args.at(-1) === "-") {
      measurements += 1;
      const values = measurements === 1
        ? { input_i: "-20.00", input_tp: "-3.00", input_lra: "4.00", input_thresh: "-30.00", target_offset: "0.10" }
        : { input_i: "-16.00", input_tp: "-1.50", input_lra: "4.00", input_thresh: "-26.00", target_offset: "0.00" };
      return { stdout: "", stderr: JSON.stringify(values) };
    }
    const outputPath = args.at(-1);
    if (!outputPath) throw new Error("normalization output path missing");
    await writeFile(outputPath, bytes);
    return { stdout: "", stderr: "" };
  };
}
