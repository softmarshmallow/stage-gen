import { afterEach, describe, expect, test } from "bun:test";
import { mkdir, rm, symlink, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import {
  artifactPathFor,
  isSafeRunTag,
  promptFromRunSummary,
  readRunInput,
  readRunStatus,
  retryAsset,
  resolveStageGenExecutable,
  runDirFor,
  startRun,
  stageGenArgsFor,
  stageGenCommandFor,
} from "./runs";
import { tagFor } from "./tag";
import { parseRecipeRunSummary } from "./run-summary";
import {
  DEFAULT_TRANSPARENCY_MODE,
  parseWebRunInput,
  previewPolicyForRunMode,
  transparencyModeFromRunSummary,
  transparencyModeLabel,
  type TransparencyMode,
} from "./transparency";

const cleanup: string[] = [];

function successfulRunSummary(
  prompt: string,
  transparencyMode: TransparencyMode,
  tag = tagFor(prompt, transparencyMode),
): Record<string, unknown> {
  return {
    schema_version: 3,
    kind: "recipe_run_v3",
    recipe: "scrolling-preview",
    input: { prompt, transparency_mode: transparencyMode },
    tag,
    run_dir: tag,
    started_at: "2026-08-25T00:00:00Z",
    ended_at: "2026-08-25T00:00:01Z",
    duration_ms: 1_000,
    ok: true,
    stages: [
      { stage: "concept", ok: true, duration_ms: 1_000, artifacts: ["concept.png"] },
    ],
  };
}

function failedRunSummary(
  prompt: string,
  transparencyMode: TransparencyMode,
  tag = tagFor(prompt, transparencyMode),
): Record<string, unknown> {
  return {
    ...successfulRunSummary(prompt, transparencyMode, tag),
    ok: false,
    failed_stage: "concept",
    stages: [
      {
        stage: "concept",
        ok: false,
        duration_ms: 1_000,
        artifacts: [],
        error: "fixture failure",
      },
    ],
  };
}

afterEach(async () => {
  await Promise.all(cleanup.splice(0).map((target) => rm(target, { recursive: true, force: true })));
});

describe("web run boundary", () => {
  test("API input defaults to native alpha and validates explicit strategies", () => {
    expect(DEFAULT_TRANSPARENCY_MODE).toBe("native");
    expect(parseWebRunInput({ prompt: "  neutral request  " })).toEqual({
      prompt: "neutral request",
      transparencyMode: "native",
    });
    expect(
      parseWebRunInput({ prompt: "neutral request", transparency_mode: "ai" }),
    ).toEqual({ prompt: "neutral request", transparencyMode: "ai" });
    expect(
      parseWebRunInput({ prompt: "neutral request", transparency_mode: "chroma" }),
    ).toEqual({ prompt: "neutral request", transparencyMode: "chroma" });
    expect(() =>
      parseWebRunInput({
        input: { prompt: "nested request", transparencyMode: "chroma" },
      }),
    ).toThrow("request body.input is not a supported key");
    expect(() =>
      parseWebRunInput({ prompt: "neutral request", unknown: true }),
    ).toThrow("request body.unknown is not a supported key");
    expect(() =>
      parseWebRunInput({ prompt: "neutral request", transparency_mode: "unsupported" }),
    ).toThrow("transparency_mode must be native, ai, or chroma");
    expect(() =>
      parseWebRunInput({ prompt: "neutral request", transparencyMode: "ai" }),
    ).toThrow("request body.transparencyMode is not a supported key");
    expect(() => parseWebRunInput({ prompt: " " })).toThrow("prompt is required");
  });

  test("mode is part of the run tag and public CLI arguments", () => {
    const prompt = "neutral request";
    const nativeTag = tagFor(prompt, "native");
    const aiTag = tagFor(prompt, "ai");
    const chromaTag = tagFor(prompt, "chroma");
    expect(nativeTag).toEndWith("-native");
    expect(aiTag).toEndWith("-ai");
    expect(chromaTag).toEndWith("-chroma");
    expect(aiTag).not.toBe(chromaTag);
    expect(stageGenArgsFor({ prompt, transparencyMode: "ai" })).toEqual([
      "run",
      "stage-gen",
      "generate",
      "--recipe",
      "scrolling-preview",
      "--transparency",
      "ai",
      prompt,
    ]);
    expect(stageGenCommandFor({ prompt, transparencyMode: "ai" }, "stage-gen")).toEqual({
      executable: "stage-gen",
      args: [
        "generate",
        "--recipe",
        "scrolling-preview",
        "--transparency",
        "ai",
        prompt,
      ],
    });
  });

  test("validates a configurable Python CLI executable without shell parsing", () => {
    expect(resolveStageGenExecutable()).toBe("uv");
    expect(resolveStageGenExecutable("stage-gen-py")).toBe("stage-gen-py");
    expect(resolveStageGenExecutable(path.resolve("/opt/stage-gen/bin/stage-gen"))).toBe(
      path.resolve("/opt/stage-gen/bin/stage-gen"),
    );
    for (const executable of [
      "uv --project /tmp/other",
      "../stage-gen",
      "/bin/sh",
      "/opt/stage-gen/../bin/stage-gen",
      " stage-gen",
    ]) {
      expect(() => resolveStageGenExecutable(executable)).toThrow("STAGE_GEN_EXECUTABLE");
    }
  });

  test("launch rejects a prompt, mode, and tag identity collision", async () => {
    await expect(
      startRun({
        prompt: "neutral request",
        transparencyMode: "ai",
        tag: tagFor("neutral request", "chroma"),
      }),
    ).rejects.toThrow("run tag does not match prompt and transparencyMode");
  });

  test("current summaries require an explicit mode and always use canonical alpha", () => {
    const current = successfulRunSummary("neutral", "chroma");
    const missingMode = successfulRunSummary("neutral", "chroma");
    missingMode["input"] = { prompt: "neutral" };
    expect(transparencyModeFromRunSummary(current)).toBe("chroma");
    expect(previewPolicyForRunMode("native")).toBe("canonical-alpha");
    expect(previewPolicyForRunMode("ai")).toBe("canonical-alpha");
    expect(previewPolicyForRunMode("chroma")).toBe("canonical-alpha");
    expect(() => transparencyModeFromRunSummary(missingMode)).toThrow(
      "run_summary.input.transparency_mode must be native, ai, or chroma",
    );
    expect(() => previewPolicyForRunMode(null)).toThrow(
      "current preview requires a transparency mode",
    );
    expect(() => transparencyModeLabel(null)).toThrow(
      "current preview requires a transparency mode",
    );
    expect(() =>
      transparencyModeFromRunSummary({
        ...successfulRunSummary("neutral", "chroma"),
        input: { prompt: "neutral", transparency_mode: "unknown" },
      }),
    ).toThrow("run_summary.input.transparency_mode must be native, ai, or chroma");
  });

  test("accepts generated tags and rejects traversal or encoded separators", () => {
    expect(isSafeRunTag("rain-dark-stone-0123abcd")).toBe(true);
    expect(isSafeRunTag("Explicit_Tag.v3")).toBe(true);
    expect(isSafeRunTag("a")).toBe(true);
    expect(isSafeRunTag("a".repeat(128))).toBe(true);
    expect(isSafeRunTag("a".repeat(129))).toBe(false);

    for (const tag of [
      "",
      ".",
      "..",
      "../escape",
      "safe/escape",
      "safe\\escape",
      "%2e%2e",
      "safe%2Fescape",
      "safe%252Fescape",
    ]) {
      expect(isSafeRunTag(tag)).toBe(false);
      expect(() => runDirFor(tag)).toThrow("invalid run tag");
    }
  });

  test("resolves portable nested artifacts inside the selected run", () => {
    const tag = "neutral-run-0123abcd";
    const runDir = runDirFor(tag);
    const artifact = artifactPathFor(tag, `world_spec_${tag}.json`);
    expect(path.dirname(artifact)).toBe(runDir);
    expect(
      artifactPathFor(tag, "content/players/wayfarer/states/idle.png"),
    ).toBe(
      path.join(runDir, "content", "players", "wayfarer", "states", "idle.png"),
    );

    for (const name of [
      "",
      ".hidden",
      "..",
      "../secret",
      "nested\\asset.png",
      "asset%2Fsecret.png",
      "asset%252Fsecret.png",
    ]) {
      expect(() => artifactPathFor(tag, name)).toThrow("invalid artifact path");
    }
  });

  test("reads the prompt and strategy from the current headless run summary", async () => {
    const promptSummary = successfulRunSummary("original rain-dark ruins", "ai");
    expect(promptFromRunSummary(parseRecipeRunSummary(promptSummary))).toBe(
      "original rain-dark ruins",
    );

    const tag = `test-input-${process.pid}`;
    const runDir = runDirFor(tag);
    cleanup.push(runDir);
    await mkdir(runDir, { recursive: true });
    await writeFile(
      path.join(runDir, "run.json"),
      JSON.stringify(successfulRunSummary("current neutral request", "ai", tag)),
      "utf8",
    );
    expect(await readRunInput(tag)).toEqual({
      prompt: "current neutral request",
      transparencyMode: "ai",
    });
    expect(await readRunStatus(tag)).toEqual({ status: "done", ok: true });
  });

  test("maps a validated failure and rejects a legacy terminal run", async () => {
    const failedTag = `test-failed-summary-${process.pid}`;
    const failedDir = runDirFor(failedTag);
    cleanup.push(failedDir);
    await mkdir(failedDir, { recursive: true });
    await writeFile(
      path.join(failedDir, "run.json"),
      JSON.stringify(failedRunSummary("current failed request", "ai", failedTag)),
      "utf8",
    );
    expect(await readRunStatus(failedTag)).toEqual({
      status: "failed",
      ok: false,
      failedStage: "concept",
    });

    const legacyTag = `test-legacy-summary-${process.pid}`;
    const legacyDir = runDirFor(legacyTag);
    cleanup.push(legacyDir);
    await mkdir(legacyDir, { recursive: true });
    await writeFile(
      path.join(legacyDir, "run.json"),
      JSON.stringify({
        recipe: "scrolling-preview",
        input: { prompt: "legacy", transparencyMode: "ai" },
        ok: true,
      }),
      "utf8",
    );
    await expect(readRunStatus(legacyTag)).rejects.toThrow(
      "run_summary.schema_version is required",
    );
  });

  test("binds the persisted tag and run_dir to the requested directory", async () => {
    const tag = `test-summary-identity-${process.pid}`;
    const runDir = runDirFor(tag);
    cleanup.push(runDir);
    await mkdir(runDir, { recursive: true });

    await writeFile(
      path.join(runDir, "run.json"),
      JSON.stringify(
        successfulRunSummary("identity mismatch", "ai", `${tag}-other`),
      ),
      "utf8",
    );
    await expect(readRunStatus(tag)).rejects.toThrow(
      "run summary tag does not match its run directory",
    );

    await writeFile(
      path.join(runDir, "run.json"),
      JSON.stringify({
        ...successfulRunSummary("directory mismatch", "ai", tag),
        run_dir: `${tag}-other`,
      }),
      "utf8",
    );
    await expect(readRunStatus(tag)).rejects.toThrow(
      "run_summary.run_dir must equal run_summary.tag",
    );
  });

  test("rejects symlinked run directories and run summary files", async () => {
    const directoryTag = `test-symlink-directory-${process.pid}`;
    const directoryPath = runDirFor(directoryTag);
    const directoryTarget = runDirFor(`${directoryTag}-target`);
    cleanup.push(directoryPath, directoryTarget);
    await mkdir(directoryTarget, { recursive: true });
    await symlink(directoryTarget, directoryPath, "dir");
    await expect(readRunStatus(directoryTag)).rejects.toThrow(
      "run directory must be a real directory",
    );

    const fileTag = `test-symlink-file-${process.pid}`;
    const fileRunDir = runDirFor(fileTag);
    const fileTargetDir = runDirFor(`${fileTag}-target`);
    const fileTarget = path.join(fileTargetDir, "foreign-run.json");
    cleanup.push(fileRunDir, fileTargetDir);
    await mkdir(fileRunDir, { recursive: true });
    await mkdir(fileTargetDir, { recursive: true });
    await writeFile(
      fileTarget,
      JSON.stringify(successfulRunSummary("symlink file", "ai", fileTag)),
      "utf8",
    );
    await symlink(fileTarget, path.join(fileRunDir, "run.json"), "file");
    await expect(readRunStatus(fileTag)).rejects.toThrow(
      "run summary file must be a real regular file",
    );
  });

  test("treats an orphaned run directory as interrupted, not running", async () => {
    const tag = `test-interrupted-${process.pid}`;
    const runDir = runDirFor(tag);
    cleanup.push(runDir);
    await mkdir(runDir, { recursive: true });
    expect(await readRunStatus(tag)).toEqual({
      status: "failed",
      ok: false,
      failedStage: "interrupted",
    });
  });

  test("retries from input.prompt and removes only the validated artifact pair", async () => {
    const prompt = `original neutral retry ${process.pid}`;
    const tag = tagFor(prompt, "ai");
    const runDir = runDirFor(tag);
    cleanup.push(runDir);
    await mkdir(runDir, { recursive: true });
    const asset = "artifact.txt";
    const artifactPath = artifactPathFor(tag, asset);
    await writeFile(
      path.join(runDir, "run.json"),
      JSON.stringify(failedRunSummary(prompt, "ai", tag)),
      "utf8",
    );
    await writeFile(artifactPath, "partial", "utf8");
    await writeFile(`${artifactPath}.meta.json`, "{}", "utf8");

    const starts: Array<{
      prompt: string;
      tag: string;
      transparencyMode?: TransparencyMode;
    }> = [];
    const result = await retryAsset(
      { tag, asset },
      async (request) => {
        starts.push(request);
        return { started: true };
      },
    );

    expect(result).toEqual({ ok: true });
    expect(starts).toEqual([
      { prompt, tag, transparencyMode: "ai" },
    ]);
    expect(existsSync(artifactPath)).toBe(false);
    expect(existsSync(`${artifactPath}.meta.json`)).toBe(false);
    expect(existsSync(path.join(runDir, "run.json"))).toBe(true);
  });

  test("an invalid current retry fails without deleting data or inventing a strategy", async () => {
    const tag = `test-invalid-retry-${process.pid}`;
    const runDir = runDirFor(tag);
    cleanup.push(runDir);
    await mkdir(runDir, { recursive: true });
    const asset = "invalid-artifact.txt";
    const target = artifactPathFor(tag, asset);
    await writeFile(
      path.join(runDir, "run.json"),
      JSON.stringify({
        ...failedRunSummary("invalid neutral retry", "ai", tag),
        input: { prompt: "invalid neutral retry" },
      }),
      "utf8",
    );
    await writeFile(target, "partial", "utf8");

    const starts: Array<{ transparencyMode?: TransparencyMode }> = [];
    const result = await retryAsset({ tag, asset }, async (request) => {
      starts.push(request);
      return { started: true };
    });

    expect(result).toEqual({
      ok: false,
      reason: "run_summary.input.transparency_mode must be native, ai, or chroma",
    });
    expect(starts).toHaveLength(0);
    expect(existsSync(target)).toBe(true);
  });
});
