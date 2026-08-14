import { describe, expect, test } from "bun:test";
import {
  ConfigError,
  assertCapabilities,
  loadConfig,
  parseTransparencyMode,
  transparencyCapabilities,
} from "../src/config.ts";

describe("headless config", () => {
  test("loads provider-neutral model configuration without requiring secrets", () => {
    const config = loadConfig({ env: {} });
    expect(config.outDir).toBe("out");
    expect(config.imageModel).toBe("openai/gpt-image-2");
    expect(config.musicModel).toBe("google/lyria-3-pro-preview");
    expect(config.openRouterApiKey).toBeUndefined();
    expect(config.transparencyMode).toBe("ai");
  });

  test("reports names but never values for missing capability configuration", () => {
    const config = loadConfig({ env: { OPENROUTER_API_KEY: "secret-value" } });
    expect(() => assertCapabilities(config, ["background-removal"])).toThrow(
      new ConfigError(["FAL_KEY"]),
    );
    try {
      assertCapabilities(config, ["background-removal"]);
    } catch (error) {
      expect(String(error)).not.toContain("secret-value");
    }
  });

  test("loads and strictly validates the transparency mode", () => {
    expect(loadConfig({ env: { TRANSPARENCY_MODE: "chroma" } }).transparencyMode).toBe(
      "chroma",
    );
    expect(parseTransparencyMode("ai")).toBe("ai");
    expect(() => loadConfig({ env: { TRANSPARENCY_MODE: "none" } })).toThrow(
      "TRANSPARENCY_MODE must be ai or chroma",
    );
    expect(() => parseTransparencyMode("AI", "--transparency")).toThrow(
      "--transparency must be ai or chroma",
    );
  });

  test("requires background removal only for ai transparency", () => {
    expect(transparencyCapabilities("ai")).toEqual(["background-removal"]);
    expect(transparencyCapabilities("chroma")).toEqual([]);
  });
});
