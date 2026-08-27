import { describe, expect, test } from "bun:test";
import type { PreparedMap } from "./prepared-manifest";
import { projectPreparedTerrainWorld } from "./prepared-terrain";

function mapGeometry(
  occupancy: readonly string[],
  normalizedX = 0.45,
): Pick<PreparedMap, "ground" | "ladder"> {
  return {
    ground: {
      mode: "terrain-atlas-3x3-minimal-v1",
      occupancy,
      asset: {
        path: "maps/road/ground.png",
        sha256: "a".repeat(64),
        bytes: 1,
        media_type: "image/png",
      },
    },
    ladder: {
      mode: "ladder-4-tile-v1",
      asset: {
        path: "maps/road/ladder.png",
        sha256: "b".repeat(64),
        bytes: 1,
        media_type: "image/png",
      },
      placements: [
        {
          ladder_id: "bellroot_ladder",
          normalized_x: normalizedX,
          bottom_surface: "terrain",
          rise_tiles: 4,
        },
      ],
    },
  };
}

describe("prepared terrain world projection", () => {
  test("derives width, bottom heightfield, floating collision, and ladder geometry", () => {
    const world = projectPreparedTerrainWorld(
      mapGeometry([
        "0000000000",
        "0001110000",
        "0000000000",
        "0000000000",
        "0000000000",
        "1111111111",
      ]),
      64,
      674,
    );

    expect(world.worldWidth).toBe(640);
    expect(world.topY).toBe(290);
    expect(world.heights).toEqual(Array.from({ length: 10 }, () => 1));
    expect(world.verticalWorld.platforms).toHaveLength(1);
    expect(world.verticalWorld.platforms[0]).toMatchObject({
      id: "terrain-platform-r1-c3",
      left: 192,
      right: 384,
      deckY: 354,
      sourceColumns: { start: 3, end: 6 },
    });
    expect(world.verticalWorld.ladders[0]).toMatchObject({
      id: "bellroot_ladder",
      platformId: "terrain-platform-r1-c3",
      centerX: 288,
      upperDeckY: 354,
      lowerSurfaceY: 610,
    });
    expect(Object.isFrozen(world)).toBeTrue();
    expect(Object.isFrozen(world.occupancy)).toBeTrue();
  });

  test("does not invent collision platforms for bottom-contiguous terrain", () => {
    const source = mapGeometry([
      "0000000000",
      "0000000000",
      "0000000000",
      "0000000000",
      "0001110000",
      "1111111111",
    ]);
    expect(() => projectPreparedTerrainWorld(source, 64, 674)).toThrow(
      "does not attach to an exposed four-tile platform",
    );
  });

  test("rejects authored ladders whose lower terrain endpoint is not flat", () => {
    const source = mapGeometry([
      "0001110000",
      "0000000000",
      "0000000000",
      "0000000000",
      "0000100000",
      "1111111111",
    ]);
    expect(() => projectPreparedTerrainWorld(source, 64, 674)).toThrow(
      "flat lower terrain endpoint",
    );
  });
});
