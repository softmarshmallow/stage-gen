import { describe, expect, test } from "bun:test";
import { defaultDialogueThemeOptions } from "../lib/dialogue-scene/active-fixture";
import { parseDialogueThemeArgs } from "./dialogue-theme";
import { stageGenArgv, stageGenRepositoryRoot } from "./stage-gen";

describe("dialogue theme operator commands", () => {
  test("forwards stage-gen arguments unchanged without constructing a shell command", () => {
    expect(stageGenArgv(["generate", "--recipe", "dialogue-scene", "two words"])).toEqual([
      "uv",
      "run",
      "stage-gen",
      "generate",
      "--recipe",
      "dialogue-scene",
      "two words",
    ]);
    expect(stageGenRepositoryRoot()).toEndWith("/stage-gen");
  });

  test("parses explicit install, activation, status, and rollback operations", () => {
    expect(
      parseDialogueThemeArgs(["install", "--bundle", "../out/bundle.json"]),
    ).toMatchObject({ command: "install", bundleId: null });
    expect(
      parseDialogueThemeArgs(["activate", "--bundle-id", "a".repeat(64)]),
    ).toMatchObject({ command: "activate", bundle: null, bundleId: "a".repeat(64) });
    expect(parseDialogueThemeArgs(["status"])).toMatchObject({
      command: "status",
      options: defaultDialogueThemeOptions(),
    });
    expect(parseDialogueThemeArgs(["rollback"]).command).toBe("rollback");
    expect(
      parseDialogueThemeArgs([
        "status",
        "--state-root",
        "../private-state",
        "--public-root",
        "../public-assets",
      ]).options,
    ).toMatchObject({
      stateRoot: expect.stringContaining("private-state"),
      publicRoot: expect.stringContaining("public-assets"),
    });
    expect(() => parseDialogueThemeArgs(["activate", "--bundle", "x"])).toThrow(
      "usage:",
    );
    expect(() =>
      parseDialogueThemeArgs(["status", "--themes-root", "../legacy"]),
    ).toThrow("usage:");
  });
});
