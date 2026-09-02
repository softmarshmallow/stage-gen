import { describe, expect, test } from "bun:test";

import type { PreparedGameplayContract } from "./prepared-gameplay";
import {
  PreparedPopulationProjectionError,
  projectPreparedMobPopulation,
} from "./prepared-population";
import { MobPopulationDirector } from "./spawn-director";

type Population = PreparedGameplayContract["mob_population"];

function populationFixture(): Population {
  return {
    update_interval_ms: 250,
    max_spawn_batch_per_update: 2,
    maps: [
      {
        map_id: "crowncrag-road",
        seed_salt: 1705,
        zones: [
          {
            zone_id: "amberbell_edge",
            surface: "terrain",
            left_fraction: 0.1,
            right_fraction: 0.4,
            initial_population: 2,
            target_population: 3,
            population_cap: 4,
            respawn_delay_ms: 6_500,
            spawn_table: [
              { mob_id: "zeta_mob", weight: 4 },
              { mob_id: "alpha_mob", weight: 3 },
            ],
          },
          {
            zone_id: "crowncrag_approach",
            surface: "terrain",
            left_fraction: 0.6,
            right_fraction: 0.9,
            initial_population: 1,
            target_population: 1,
            population_cap: 2,
            respawn_delay_ms: 8_000,
            spawn_table: [{ mob_id: "zeta_mob", weight: 1 }],
          },
        ],
      },
    ],
  };
}

describe("population policy overrides", () => {
  const geometry = {
    world_columns: 20,
    tile_pixels: 64,
    baseline_y: 674,
    height_at_column: () => 1,
  };

  test("the defaults are the established uniform, off-screen-preferred policy", () => {
    const zone = projectPreparedMobPopulation(populationFixture(), "crowncrag-road", geometry)!
      .manifest.maps[0]!.zones[0]!;
    expect(zone.placement).toBe("uniform");
    expect(zone.cluster_radius_px).toBe(0);
    expect(zone.spawn_visibility).toBe("offscreen_preferred");
    expect(zone.minimum_spawn_separation_px).toBe(80);
  });

  test("a consumer may ask for clustered, on-screen, tighter placement", () => {
    const zone = projectPreparedMobPopulation(populationFixture(), "crowncrag-road", geometry, {
      spawn_visibility: "allow_onscreen",
      minimum_spawn_separation_px: 32,
      placement: "clustered",
      cluster_radius_px: 160,
    })!.manifest.maps[0]!.zones[0]!;
    expect(zone.placement).toBe("clustered");
    expect(zone.cluster_radius_px).toBe(160);
    expect(zone.spawn_visibility).toBe("allow_onscreen");
    expect(zone.minimum_spawn_separation_px).toBe(32);
  });

  test("clustered placement without a radius is refused at projection", () => {
    expect(() =>
      projectPreparedMobPopulation(populationFixture(), "crowncrag-road", geometry, {
        placement: "clustered",
      }),
    ).toThrow("cluster_radius_px must be positive");
  });
});

describe("prepared mob population projection", () => {
  test("projects fractional authored zones into a valid mature director contract", () => {
    const projection = projectPreparedMobPopulation(
      populationFixture(),
      "crowncrag-road",
      {
        world_columns: 20,
        tile_pixels: 64,
        baseline_y: 674,
        height_at_column: () => 1,
      },
    );

    expect(projection).not.toBeNull();
    expect(projection!.mob_id_by_slot).toEqual(["alpha_mob", "zeta_mob"]);
    expect(projection!.zone_id_by_source_id).toEqual({
      amberbell_edge: "amberbell-edge",
      crowncrag_approach: "crowncrag-approach",
    });
    const firstZone = projection!.manifest.maps[0]!.zones[0]!;
    expect(firstZone.left_column).toBe(2);
    expect(firstZone.right_column_exclusive).toBe(8);
    expect(firstZone.spawn_batch_size).toBe(2);
    expect(firstZone.spawn_table.map((entry) => entry.mob_slot)).toEqual([1, 0]);
    expect(projection!.candidates[0]!.candidate_columns).toEqual([
      { column: 3, x_px: 224, y_px: 610 },
      { column: 4, x_px: 288, y_px: 610 },
      { column: 5, x_px: 352, y_px: 610 },
    ]);
    expect(
      () => new MobPopulationDirector(projection!.manifest, projection!.candidates),
    ).not.toThrow();
    expect(Object.isFrozen(projection!.candidates[0]!.candidate_columns)).toBeTrue();
  });

  test("keeps slot assignment stable across authored zone and table order", () => {
    const source = populationFixture();
    const reordered: Population = {
      ...source,
      maps: [
        {
          ...source.maps[0]!,
          zones: [...source.maps[0]!.zones]
            .reverse()
            .map((zone) => ({ ...zone, spawn_table: [...zone.spawn_table].reverse() })),
        },
      ],
    };
    const geometry = {
      world_columns: 20,
      tile_pixels: 64,
      baseline_y: 674,
      height_at_column: () => 1,
    };

    expect(projectPreparedMobPopulation(source, "crowncrag-road", geometry)!.mob_id_by_slot)
      .toEqual(projectPreparedMobPopulation(reordered, "crowncrag-road", geometry)!.mob_id_by_slot);
  });

  test("uses runtime geometry and exclusion gates for candidate positions", () => {
    const projection = projectPreparedMobPopulation(
      populationFixture(),
      "crowncrag-road",
      {
        world_columns: 20,
        tile_pixels: 40,
        baseline_y: 500,
        height_at_column: (column) => column % 2,
        is_spawnable_column: (column) => column !== 4,
      },
      { wander_radius_px: 40 },
    )!;

    expect(projection.candidates[0]!.candidate_columns).toEqual([
      { column: 3, x_px: 140, y_px: 460 },
      { column: 5, x_px: 220, y_px: 460 },
      { column: 6, x_px: 260, y_px: 500 },
    ]);
  });

  test("returns null when this authored map has no managed population", () => {
    expect(
      projectPreparedMobPopulation(populationFixture(), "sunpetal-crossing", {
        world_columns: 20,
        tile_pixels: 64,
        baseline_y: 674,
        height_at_column: () => 1,
      }),
    ).toBeNull();
  });

  test("fails clearly when world resolution cannot realize an authored zone", () => {
    const source = populationFixture();
    const tiny: Population = {
      ...source,
      maps: [
        {
          ...source.maps[0]!,
          zones: [
            {
              ...source.maps[0]!.zones[0]!,
              left_fraction: 0.1,
              right_fraction: 0.11,
            },
          ],
        },
      ],
    };

    expect(() =>
      projectPreparedMobPopulation(tiny, "crowncrag-road", {
        world_columns: 20,
        tile_pixels: 64,
        baseline_y: 674,
        height_at_column: () => 1,
      }),
    ).toThrow(PreparedPopulationProjectionError);
    expect(() =>
      projectPreparedMobPopulation(tiny, "crowncrag-road", {
        world_columns: 20,
        tile_pixels: 64,
        baseline_y: 674,
        height_at_column: () => 1,
      }),
    ).toThrow("does not contain a column center");
  });
});
