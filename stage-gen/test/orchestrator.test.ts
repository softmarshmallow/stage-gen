import { afterAll, describe, expect, test } from "bun:test";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { runRecipe } from "../src/orchestrator.ts";
import type { Recipe } from "../src/types.ts";

const roots: string[] = [];

afterAll(async () => {
  await Promise.all(roots.map((root) => rm(root, { recursive: true, force: true })));
});

describe("generic recipe runner", () => {
  test("runs an arbitrary recipe without gameplay assumptions", async () => {
    const outDir = await mkdtemp(join(tmpdir(), "stage-gen-runner-"));
    roots.push(outDir);
    type Input = { assetId: string } & Record<string, unknown>;
    const recipe: Recipe<Input> = {
      id: "test-asset",
      description: "test",
      requiredCapabilities: [],
      parseInput(value) {
        return value as Input;
      },
      tagFor(input) {
        return input.assetId;
      },
      stages: [
        {
          name: "emit",
          wave: 1,
          description: "emit artifact",
          async run(context) {
            const path = join(context.runDir, "artifact.txt");
            await writeFile(path, context.input.assetId, "utf8");
            return { artifacts: [path] };
          },
        },
      ],
    };

    const summary = await runRecipe({
      recipe,
      input: { assetId: "neutral-asset" },
      config: loadTestConfig(outDir),
      log: () => {},
    });

    expect(summary.ok).toBe(true);
    expect(summary.recipe).toBe("test-asset");
    expect(await readFile(join(outDir, "neutral-asset-ai", "artifact.txt"), "utf8")).toBe(
      "neutral-asset",
    );
    expect(JSON.parse(await readFile(join(outDir, "neutral-asset-ai", "run.json"), "utf8"))).toMatchObject({
      recipe: "test-asset",
      input: { transparencyMode: "ai" },
      tag: "neutral-asset-ai",
      ok: true,
    });
  });

  test("rejects recipe tags that could escape the output root", async () => {
    const outDir = await mkdtemp(join(tmpdir(), "stage-gen-runner-"));
    roots.push(outDir);
    const recipe: Recipe<{ assetId: string }> = {
      id: "unsafe",
      description: "test",
      requiredCapabilities: [],
      parseInput: (value) => value as { assetId: string },
      tagFor: () => "../outside",
      stages: [],
    };
    await expect(
      runRecipe({
        recipe,
        input: { assetId: "x" },
        config: loadTestConfig(outDir),
        log: () => {},
      }),
    ).rejects.toThrow("recipe tag must be one safe path segment");
  });

  test("propagates a stage timeout through the stage signal", async () => {
    const outDir = await mkdtemp(join(tmpdir(), "stage-gen-runner-"));
    roots.push(outDir);
    const recipe: Recipe<{ assetId: string }> = {
      id: "timeout",
      description: "test",
      requiredCapabilities: [],
      parseInput: (value) => value as { assetId: string },
      tagFor: () => "timeout",
      stages: [
        {
          name: "wait",
          wave: 1,
          description: "wait for cancellation",
          async run({ signal }) {
            await new Promise<void>((_resolve, reject) => {
              signal.addEventListener("abort", () => reject(signal.reason), { once: true });
            });
            return { artifacts: [] };
          },
        },
      ],
    };
    const config = { ...loadTestConfig(outDir), stageTimeoutMs: 10 };
    const summary = await runRecipe({
      recipe,
      input: { assetId: "x" },
      config,
      log: () => {},
    });
    expect(summary.ok).toBe(false);
    expect(summary.stages[0]?.error).toContain("timed out");
  });

  test("propagates the request transparency override to every stage", async () => {
    const outDir = await mkdtemp(join(tmpdir(), "stage-gen-runner-"));
    roots.push(outDir);
    let observedMode: string | undefined;
    const recipe: Recipe<{ assetId: string; transparencyMode?: string }> = {
      id: "mode",
      description: "test",
      requiredCapabilities: [],
      parseInput: (value) => value as { assetId: string; transparencyMode?: string },
      tagFor: (input) => input.assetId,
      stages: [
        {
          name: "observe",
          wave: 1,
          description: "observe mode",
          async run({ config }) {
            observedMode = config.transparencyMode;
            return { artifacts: [] };
          },
        },
      ],
    };
    const summary = await runRecipe({
      recipe,
      input: { assetId: "asset", transparencyMode: "chroma" },
      config: loadTestConfig(outDir),
      log: () => {},
    });
    expect(summary.tag).toBe("asset-chroma");
    expect(summary.input.transparencyMode).toBe("chroma");
    expect(observedMode).toBe("chroma");
  });
});

function loadTestConfig(outDir: string) {
  return {
    outDir,
    imageModel: "test/image",
    textModel: "test/text",
    musicModel: "test/music",
    backgroundRemovalModel: "test/remove",
    transparencyMode: "ai" as const,
    stageTimeoutMs: 1_000,
    capabilityTimeoutMs: 1_000,
  };
}
