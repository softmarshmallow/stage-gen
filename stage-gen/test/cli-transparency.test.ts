import { describe, expect, test } from "bun:test";
import { loadConfig } from "../src/config.ts";
import {
  createDoctorReport,
  parseDoctorArguments,
  parseGenerateArguments,
} from "../src/cli.ts";

describe("transparency CLI contract", () => {
  test("parses default and explicit generate modes", () => {
    expect(parseGenerateArguments(["a", "neutral", "asset"])).toMatchObject({
      recipe: "scrolling-preview",
      prompt: "a neutral asset",
      transparencyMode: undefined,
    });
    expect(
      parseGenerateArguments(["--transparency", "chroma", "asset"])
        .transparencyMode,
    ).toBe("chroma");
    expect(
      parseGenerateArguments(["--transparency", "ai", "asset"]).transparencyMode,
    ).toBe("ai");
    expect(() => parseGenerateArguments(["--transparency", "none", "asset"])).toThrow(
      "--transparency must be ai or chroma",
    );
  });

  test("doctor accepts the same flag and reports conditional requirements", () => {
    expect(parseDoctorArguments(["--json", "--transparency", "chroma"])).toEqual({
      json: true,
      transparencyMode: "chroma",
    });
    const withoutFal = loadConfig({ env: { OPENROUTER_API_KEY: "test" } });
    expect(createDoctorReport(withoutFal, "chroma")).toMatchObject({
      ok: true,
      transparencyMode: "chroma",
      requirements: { backgroundRemoval: false },
      capabilities: { fal: false },
    });
    expect(createDoctorReport(withoutFal, "ai")).toMatchObject({
      ok: false,
      transparencyMode: "ai",
      requirements: { backgroundRemoval: true },
      capabilities: { fal: false },
    });
  });
});
