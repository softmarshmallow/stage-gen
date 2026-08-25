import path from "node:path";

import { describe, expect, test } from "bun:test";

import { stageGenArgv, stageGenRepositoryRoot } from "./stage-gen";

describe("stage-gen repository command", () => {
  test("forwards arguments unchanged without constructing a shell command", () => {
    expect(stageGenArgv(["generate", "--recipe", "dialogue-scene", "two words"])).toEqual([
      "uv",
      "run",
      "stage-gen",
      "generate",
      "--recipe",
      "dialogue-scene",
      "two words",
    ]);
  });

  test("runs the Python CLI from the repository root", () => {
    expect(stageGenRepositoryRoot()).toBe(path.resolve(import.meta.dir, "../.."));
  });
});
