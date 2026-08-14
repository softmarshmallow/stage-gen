import { describe, expect, test } from "bun:test";
import type { StageGenConfig } from "../src/config.ts";
import { prepareGenerateRequest } from "../src/service.ts";

describe("generic transparency orchestration contract", () => {
  test("defaults to ai and makes the mode part of input and run identity", () => {
    const prepared = prepareGenerateRequest(
      { input: { prompt: "neutral asset set" } },
      config({ openRouterApiKey: "test", falKey: "test" }),
    );
    expect(prepared.input.transparencyMode).toBe("ai");
    expect(prepared.tag).toEndWith("-ai");
    expect(prepared.requiredCapabilities).toContain("background-removal");
  });

  test("accepts both explicit modes and gives the same prompt distinct tags", () => {
    const runtime = config({ openRouterApiKey: "test", falKey: "test" });
    const ai = prepareGenerateRequest(
      { input: { prompt: "same prompt" }, transparencyMode: "ai" },
      runtime,
    );
    const chroma = prepareGenerateRequest(
      { input: { prompt: "same prompt" }, transparencyMode: "chroma" },
      runtime,
    );
    expect(ai.tag).not.toBe(chroma.tag);
    expect(ai.tag).toEndWith("-ai");
    expect(chroma.tag).toEndWith("-chroma");
    expect(chroma.input.transparencyMode).toBe("chroma");
  });

  test("requires FAL for ai but never for chroma", () => {
    const withoutFal = config({ openRouterApiKey: "test" });
    expect(() =>
      prepareGenerateRequest(
        { input: { prompt: "asset" }, transparencyMode: "ai" },
        withoutFal,
      ),
    ).toThrow("FAL_KEY");
    const chroma = prepareGenerateRequest(
      { input: { prompt: "asset" }, transparencyMode: "chroma" },
      withoutFal,
    );
    expect(chroma.requiredCapabilities).not.toContain("background-removal");
  });

  test("rejects invalid request data before checking capabilities", () => {
    const withoutKeys = config();
    expect(() =>
      prepareGenerateRequest(
        { input: { prompt: "asset" }, transparencyMode: "none" },
        withoutKeys,
      ),
    ).toThrow("transparencyMode must be ai or chroma");
    expect(() => prepareGenerateRequest({ input: {} }, withoutKeys)).toThrow(
      "scrolling-preview input requires a non-empty prompt",
    );
  });

  test("accepts nested mode and rejects conflicting public fields", () => {
    const runtime = config({ openRouterApiKey: "test", falKey: "test" });
    expect(
      prepareGenerateRequest(
        { input: { prompt: "asset", transparencyMode: "chroma" } },
        runtime,
      ).input.transparencyMode,
    ).toBe("chroma");
    expect(() =>
      prepareGenerateRequest(
        {
          input: { prompt: "asset", transparencyMode: "chroma" },
          transparencyMode: "ai",
        },
        runtime,
      ),
    ).toThrow("transparencyMode conflicts with input.transparencyMode");
  });
});

function config(
  overrides: Partial<StageGenConfig> = {},
): StageGenConfig {
  return {
    outDir: "out",
    imageModel: "test/image",
    textModel: "test/text",
    musicModel: "test/music",
    backgroundRemovalModel: "test/remove",
    transparencyMode: "ai",
    stageTimeoutMs: 1_000,
    capabilityTimeoutMs: 1_000,
    ...overrides,
  };
}
