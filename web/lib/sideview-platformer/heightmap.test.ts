import { describe, expect, test } from "bun:test";
import { buildHeightmap, buildHeightmapFromSeed } from "./heightmap";

const STAGE_OPTIONS = Object.freeze({ cols: 200, minH: 1, maxH: 4 });

describe("heightmap seeding", () => {
  test("an explicit numeric seed reproduces what string hashing produced", () => {
    // Terrain used to be seeded by hashing a run tag. The seed is explicit now; this
    // pins the equivalence so the migration cannot silently change a generated map.
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
