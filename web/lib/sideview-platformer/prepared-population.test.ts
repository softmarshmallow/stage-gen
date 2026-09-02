import { describe, expect, test } from "bun:test";

import type { PreparedGameplayContract } from "./prepared-gameplay";
import {
  PreparedPopulationProjectionError,
  projectPreparedMobPopulation,
  reservedSpawnColumns,
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

describe("ground a mob may not stand on", () => {
  test("reserves both map ends and every portal doorway", () => {
    const reserved = reservedSpawnColumns({
      worldColumns: 56,
      portalAnchorFractions: [0.05, 0.95],
    });

    expect([...reserved].sort((a, b) => a - b)).toEqual([
      0, 1, 2, 3, 4, 5, 50, 51, 52, 53, 54, 55,
    ]);
  });

  test("keeps a portal doorway inside the map when its anchor sits mid-span", () => {
    const reserved = reservedSpawnColumns({ worldColumns: 56, portalAnchorFractions: [0.5] });

    expect([...reserved].filter((column) => column > 5 && column < 50).sort((a, b) => a - b)).toEqual(
      [26, 27, 28, 29, 30],
    );
  });

  test("a map stacked with storeys still has ground to stand on", () => {
    // The regression this rule exists for. Reserving every column a deck floats over covered
    // Crowncrag Road's zones end to end once its storeys interlocked, and the projection then
    // rejected the map for having nowhere to spawn. Ground under a deck is still ground: the
    // decks below must change nothing about which columns come back.
    const reserved = reservedSpawnColumns({ worldColumns: 56, portalAnchorFractions: [0.05, 0.95] });
    const zone = { left: 20, rightExclusive: 38 };
    const spawnable = [];
    for (let column = zone.left; column < zone.rightExclusive; column += 1) {
      if (!reserved.has(column)) spawnable.push(column);
    }

    expect(spawnable).toHaveLength(zone.rightExclusive - zone.left);
  });
});

describe("decks as places to stand", () => {
  const geometry = {
    world_columns: 20,
    tile_pixels: 64,
    baseline_y: 674,
    height_at_column: () => 1,
    // Two storeys over the middle of the map, the interlocking shape a shelves chunk builds.
    deck_footings_at_column: (column: number) =>
      column >= 3 && column <= 5
        ? [
            { deck_id: `lower-${column}`, surface_y: 482 },
            { deck_id: `upper-${column}`, surface_y: 354 },
          ]
        : [],
  };

  function deckZonePopulation(): Population {
    const source = populationFixture();
    return {
      ...source,
      maps: [
        {
          ...source.maps[0]!,
          zones: source.maps[0]!.zones.map((zone) => ({
            ...zone,
            surface: "terrain_and_decks" as const,
          })),
        },
      ],
    };
  }

  test("a zone allowing decks offers the ground and every storey over it", () => {
    const projection = projectPreparedMobPopulation(
      deckZonePopulation(),
      "crowncrag-road",
      geometry,
    )!;

    expect(projection.candidates[0]!.candidate_columns).toEqual([
      { column: 3, x_px: 224, y_px: 610 },
      { column: 3, x_px: 224, y_px: 482, deck_id: "lower-3" },
      { column: 3, x_px: 224, y_px: 354, deck_id: "upper-3" },
      { column: 4, x_px: 288, y_px: 610 },
      { column: 4, x_px: 288, y_px: 482, deck_id: "lower-4" },
      { column: 4, x_px: 288, y_px: 354, deck_id: "upper-4" },
      { column: 5, x_px: 352, y_px: 610 },
      { column: 5, x_px: 352, y_px: 482, deck_id: "lower-5" },
      { column: 5, x_px: 352, y_px: 354, deck_id: "upper-5" },
    ]);
  });

  test("a terrain zone ignores the decks over it", () => {
    // The permission is the zone's, not the map's: the same geometry, populated by a zone that
    // never asked for decks, is the floor-only route every package shipped before storeys.
    const projection = projectPreparedMobPopulation(
      populationFixture(),
      "crowncrag-road",
      geometry,
    )!;

    expect(
      projection.candidates[0]!.candidate_columns.every(
        (candidate) => candidate.deck_id === undefined,
      ),
    ).toBeTrue();
  });

  test("the director accepts a footing per storey in one column", () => {
    const projection = projectPreparedMobPopulation(
      deckZonePopulation(),
      "crowncrag-road",
      geometry,
    )!;

    expect(
      () => new MobPopulationDirector(projection.manifest, projection.candidates),
    ).not.toThrow();
  });

  test("a map with no decks populates its ground either way", () => {
    const withDecks = projectPreparedMobPopulation(deckZonePopulation(), "crowncrag-road", {
      world_columns: 20,
      tile_pixels: 64,
      baseline_y: 674,
      height_at_column: () => 1,
    })!;

    expect(withDecks.candidates[0]!.candidate_columns).toEqual([
      { column: 3, x_px: 224, y_px: 610 },
      { column: 4, x_px: 288, y_px: 610 },
      { column: 5, x_px: 352, y_px: 610 },
    ]);
  });

  test("an unnamed deck is refused rather than placed nowhere", () => {
    expect(() =>
      projectPreparedMobPopulation(deckZonePopulation(), "crowncrag-road", {
        ...geometry,
        deck_footings_at_column: () => [{ deck_id: "", surface_y: 482 }],
      }),
    ).toThrow("unnamed deck");
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
