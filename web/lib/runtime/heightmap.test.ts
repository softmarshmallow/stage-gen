import { describe, expect, test } from "bun:test";
import { buildHeightmap, buildHeightmapFromSeed } from "./heightmap";

const STAGE_OPTIONS = Object.freeze({ cols: 200, minH: 1, maxH: 4 });

describe("heightmap seeding", () => {
  test("preserves the legacy tag terrain through its explicit seed", () => {
    expect(buildHeightmapFromSeed(1_235_206_006, STAGE_OPTIONS)).toEqual(
      buildHeightmap(
        "original-deterministic-gameplay-showcase-532c8ee7-chroma",
        STAGE_OPTIONS,
      ),
    );
  });

  test("is deterministic for a numeric seed and changes with the seed", () => {
    const first = buildHeightmapFromSeed(1_235_206_006, STAGE_OPTIONS);
    expect(buildHeightmapFromSeed(1_235_206_006, STAGE_OPTIONS)).toEqual(first);
    expect(buildHeightmapFromSeed(1_235_206_007, STAGE_OPTIONS)).not.toEqual(first);
  });
});
