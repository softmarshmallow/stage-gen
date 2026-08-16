import { afterEach, describe, expect, test } from "bun:test";
import { mkdir, rm, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import {
  artifactPathFor,
  isSafeRunTag,
  promptFromRunManifest,
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
import {
  DEFAULT_TRANSPARENCY_MODE,
  modeForAiBackgroundRemoval,
  parseWebRunInput,
  previewPolicyForRunMode,
  transparencyModeFromRunManifest,
  transparencyModeLabel,
  type TransparencyMode,
} from "./transparency";

const cleanup: string[] = [];

afterEach(async () => {
  await Promise.all(cleanup.splice(0).map((target) => rm(target, { recursive: true, force: true })));
});

describe("web run boundary", () => {
  test("API input defaults to AI and validates an explicit strategy", () => {
    expect(DEFAULT_TRANSPARENCY_MODE).toBe("ai");
    expect(parseWebRunInput({ prompt: "  neutral request  " })).toEqual({
      prompt: "neutral request",
      transparencyMode: "ai",
    });
    expect(
      parseWebRunInput({ prompt: "neutral request", transparencyMode: "chroma" }),
    ).toEqual({ prompt: "neutral request", transparencyMode: "chroma" });
    expect(
      parseWebRunInput({
        input: { prompt: "nested request", transparencyMode: "chroma" },
      }),
    ).toEqual({ prompt: "nested request", transparencyMode: "chroma" });
    expect(() =>
      parseWebRunInput({ prompt: "neutral request", transparencyMode: "legacy" }),
    ).toThrow("transparencyMode must be ai or chroma");
    expect(() => parseWebRunInput({ prompt: " " })).toThrow("prompt is required");
  });

  test("the picker control maps on to AI and off to the degraded fallback", () => {
    expect(modeForAiBackgroundRemoval(true)).toBe("ai");
    expect(modeForAiBackgroundRemoval(false)).toBe("chroma");
  });

  test("mode is part of the run tag and public CLI arguments", () => {
    const prompt = "neutral request";
    const aiTag = tagFor(prompt, "ai");
    const chromaTag = tagFor(prompt, "chroma");
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

  test("new manifests use canonical alpha while missing strategy stays legacy-only", () => {
    const current = { input: { prompt: "neutral", transparencyMode: "chroma" } };
    const legacy = { input: { prompt: "neutral" } };
    expect(transparencyModeFromRunManifest(current)).toBe("chroma");
    expect(previewPolicyForRunMode("ai")).toBe("canonical-alpha");
    expect(previewPolicyForRunMode("chroma")).toBe("canonical-alpha");
    expect(transparencyModeFromRunManifest(legacy)).toBeNull();
    expect(previewPolicyForRunMode(null)).toBe("legacy-chroma");
    expect(transparencyModeLabel(null)).toContain("legacy");
    expect(() =>
      transparencyModeFromRunManifest({
        input: { prompt: "neutral", transparencyMode: "unknown" },
      }),
    ).toThrow("run manifest input.transparencyMode must be ai or chroma");
  });

  test("accepts generated tags and rejects traversal or encoded separators", () => {
    expect(isSafeRunTag("rain-dark-stone-0123abcd")).toBe(true);
    expect(isSafeRunTag("a")).toBe(true);

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
      "UPPER-0123abcd",
    ]) {
      expect(isSafeRunTag(tag)).toBe(false);
      expect(() => runDirFor(tag)).toThrow("invalid run tag");
    }
  });

  test("resolves only a bare artifact inside the selected run", () => {
    const tag = "neutral-run-0123abcd";
    const runDir = runDirFor(tag);
    const artifact = artifactPathFor(tag, `world_spec_${tag}.json`);
    expect(path.dirname(artifact)).toBe(runDir);

    for (const name of [
      "",
      ".hidden",
      "..",
      "../secret",
      "nested/asset.png",
      "nested\\asset.png",
      "asset%2Fsecret.png",
      "asset%252Fsecret.png",
    ]) {
      expect(() => artifactPathFor(tag, name)).toThrow("invalid artifact name");
    }
  });

  test("reads the prompt and strategy from the current headless run manifest", async () => {
    expect(
      promptFromRunManifest({
        recipe: "scrolling-preview",
        input: { prompt: "original rain-dark ruins" },
        ok: false,
      }),
    ).toBe("original rain-dark ruins");
    expect(promptFromRunManifest({ prompt: "legacy shape" })).toBeUndefined();
    expect(promptFromRunManifest({ input: { prompt: "  " } })).toBeUndefined();

    const tag = `test-input-${process.pid}`;
    const runDir = runDirFor(tag);
    cleanup.push(runDir);
    await mkdir(runDir, { recursive: true });
    await writeFile(
      path.join(runDir, "run.json"),
      JSON.stringify({
        input: { prompt: "current neutral request", transparencyMode: "ai" },
        ok: true,
      }),
      "utf8",
    );
    expect(await readRunInput(tag)).toEqual({
      prompt: "current neutral request",
      transparencyMode: "ai",
    });
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
      JSON.stringify({
        input: { prompt, transparencyMode: "ai" },
        ok: false,
      }),
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

  test("a legacy retry fails without deleting data or inventing a strategy", async () => {
    const tag = `test-legacy-retry-${process.pid}`;
    const runDir = runDirFor(tag);
    cleanup.push(runDir);
    await mkdir(runDir, { recursive: true });
    const asset = "legacy-artifact.txt";
    const target = artifactPathFor(tag, asset);
    await writeFile(
      path.join(runDir, "run.json"),
      JSON.stringify({ input: { prompt: "legacy neutral retry" }, ok: false }),
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
      reason: "legacy run has no transparencyMode; restart it from the picker",
    });
    expect(starts).toHaveLength(0);
    expect(existsSync(target)).toBe(true);
  });
});
