// Painted terrain is the second ground discipline, and the manifest is where the two meet.
//
// The parse has one job beyond reading fields: refusing a manifest that carries both
// shapes. A producer that emits an atlas asset alongside painted segments has a defect,
// and silently preferring one of them is how that defect ships.

import { describe, expect, test } from "bun:test";

import { parsePreparedRuntimeManifest } from "@/lib/manifest/prepared-manifest";
import { preparedRuntimeManifestFixture } from "@/lib/shell/prepared-runtime.fixture";

const SEGMENT_ASSET = Object.freeze({
  path: "maps/village/ground/seg00.png",
  sha256: "b".repeat(64),
  bytes: 1024,
  media_type: "image/png",
  role: "asset",
});

function paintedManifest(
  override: (ground: Record<string, unknown>) => void = () => {},
): Record<string, unknown> {
  const manifest = preparedRuntimeManifestFixture();
  const maps = manifest.maps as Record<string, unknown>[];
  const map = maps[0]!;
  const atlas = map.ground as Record<string, unknown>;
  const ground: Record<string, unknown> = {
    mode: "painted-terrain-v1",
    occupancy: atlas.occupancy,
    vertical_fit: atlas.vertical_fit,
    walk_surface_row: atlas.walk_surface_row,
    cell_px: 64,
    silhouette_tolerance: {
      cell_px: 64,
      erode_px: 8,
      dilate_px: 16,
      surface_dilate_px: 8,
    },
    segments: [
      { segment_id: "seg00", start_column: 0, columns: 10, asset: { ...SEGMENT_ASSET } },
      { segment_id: "seg01", start_column: 10, columns: 10, asset: { ...SEGMENT_ASSET } },
    ],
  };
  override(ground);
  map.ground = ground;
  return manifest;
}

describe("painted terrain in the prepared manifest", () => {
  test("parses beside the tile atlas without disturbing it", () => {
    const atlas = parsePreparedRuntimeManifest(preparedRuntimeManifestFixture());
    expect(atlas.maps[0]!.ground.mode).toBe("terrain-atlas-3x3-minimal-v1");

    const painted = parsePreparedRuntimeManifest(paintedManifest());
    const ground = painted.maps[0]!.ground;
    expect(ground.mode).toBe("painted-terrain-v1");
    if (ground.mode !== "painted-terrain-v1") throw new Error("unreachable");
    expect(ground.segments.map((segment) => segment.segment_id)).toEqual([
      "seg00",
      "seg01",
    ]);
    expect(ground.silhouette_tolerance.dilate_px).toBe(16);
  });

  test("keeps every field the geometry needs on both arms", () => {
    // Collision, the world box and every walk_surface anchored layer read these three, and
    // none of them knows how the ground is drawn.
    const painted = parsePreparedRuntimeManifest(paintedManifest()).maps[0]!.ground;
    expect(painted.occupancy.length).toBeGreaterThan(0);
    expect(painted.vertical_fit).toBe("floor_to_screen_bottom");
    expect(typeof painted.walk_surface_row).toBe("number");
  });

  test("refuses a painted ground that also declares a single atlas asset", () => {
    expect(() =>
      parsePreparedRuntimeManifest(
        paintedManifest((ground) => {
          ground.asset = { ...SEGMENT_ASSET };
        }),
      ),
    ).toThrow(/must not declare a single ground asset/);
  });

  test("refuses an atlas ground that declares painted segments", () => {
    const manifest = preparedRuntimeManifestFixture();
    const map = (manifest.maps as Record<string, unknown>[])[0]!;
    (map.ground as Record<string, unknown>).segments = [];
    expect(() => parsePreparedRuntimeManifest(manifest)).toThrow(
      /must not declare painted cell_px or segments/,
    );
  });

  test("refuses segments that leave a gap in the floor", () => {
    expect(() =>
      parsePreparedRuntimeManifest(
        paintedManifest((ground) => {
          const segments = ground.segments as Record<string, unknown>[];
          segments[1]!.start_column = 11;
        }),
      ),
    ).toThrow(/must tile the map in order/);
  });

  test("refuses segments that stop short of the authored columns", () => {
    expect(() =>
      parsePreparedRuntimeManifest(
        paintedManifest((ground) => {
          (ground.segments as Record<string, unknown>[]).pop();
        }),
      ),
    ).toThrow(/must cover every authored column/);
  });

  test("refuses a painted ground with no segments at all", () => {
    expect(() =>
      parsePreparedRuntimeManifest(
        paintedManifest((ground) => {
          ground.segments = [];
        }),
      ),
    ).toThrow(/at least one segment/);
  });
});
