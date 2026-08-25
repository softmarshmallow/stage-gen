import { describe, expect, test } from "bun:test";
import { buildHeightmapFromSeed, heightmapSeedForTag } from "./heightmap";
import {
  STAGE_PLANS,
  STAGE_LAYOUT_KINDS,
  assertContinuousPopulationCoverage,
  buildStageBook,
  normalizeStageIndex,
  parseMapBookManifest,
  portalDestination,
  stagePlanAt,
  stageTerrainSeed,
  type StagePlan,
} from "./stages";

const HEIGHTMAP_OPTS = { cols: 200, minH: 1, maxH: 4 } as const;
const SOURCE_SHA256 = "a".repeat(64);
const CANONICAL_SHA256 = "b".repeat(64);
const MAP_SOURCE_SHA256 = "c".repeat(64);
const MAP_CANONICAL_SHA256 = "d".repeat(64);

const mapManifestEntry = (
  mapId: string,
  displayName: string,
  soundtrackTrackIds: readonly string[],
  levelProfile: unknown =
    mapId === "village-hub" ? socialHubProfile() : combatFieldProfile(),
) => ({
  map_id: mapId,
  revision: 1,
  display_name: displayName,
  soundtrack_track_ids: soundtrackTrackIds,
  source_ref: `library/games/storybook-preview/maps/${mapId}.toml`,
  source_sha256: MAP_SOURCE_SHA256,
  canonical_sha256: MAP_CANONICAL_SHA256,
  level_profile: levelProfile,
});

function combatFieldProfile() {
  return {
    schema_version: 1,
    kind: "level-profile-v1",
    role: "combat_field",
    view: { projection: "orthographic_2d", viewpoint: "side_on" },
    camera: {
      tracking_mode: "player_follow",
      framing_mode: "dead_zone",
      scroll_axes: ["horizontal", "vertical"],
    },
    traversal: {
      ground_model: "heightfield",
      platform_model: "one_way",
      affordances: [
        "ground_move",
        "jump",
        "air_jump",
        "drop_through",
        "ladder_climb",
      ],
    },
    mechanisms: {
      encounter_model: "continuous_population",
      combat_model: "real_time_action",
      loot_model: "defeat_drops",
      interaction_model: "none",
      transition_model: "bidirectional_portals",
    },
  };
}

function socialHubProfile() {
  return {
    schema_version: 1,
    kind: "level-profile-v1",
    role: "social_hub",
    view: { projection: "orthographic_2d", viewpoint: "side_on" },
    camera: {
      tracking_mode: "player_follow",
      framing_mode: "dead_zone",
      scroll_axes: ["horizontal"],
    },
    traversal: {
      ground_model: "heightfield",
      platform_model: "none",
      affordances: ["ground_move", "jump"],
    },
    mechanisms: {
      encounter_model: "none",
      combat_model: "none",
      loot_model: "none",
      interaction_model: "proximity_dialogue",
      transition_model: "bidirectional_portals",
    },
  };
}

const authoredMapManifest = () => ({
  schema_version: 7,
  soundtrack: {
    schema_version: 2,
    kind: "game-soundtrack-manifest-v2",
    game_id: "storybook-preview",
    source: {
      source_sha256: SOURCE_SHA256,
      canonical_sha256: CANONICAL_SHA256,
    },
    tracks: [
      { track_id: "lantern_road" },
      { track_id: "mossy_steps" },
      { track_id: "village_night" },
    ],
  },
  map_book: {
    schema_version: 2,
    kind: "game-map-book-manifest-v2",
    game_id: "storybook-preview",
    revision: 3,
    entry_map_id: "village-hub",
    source: {
      path: "map_book_storybook.json",
      provenance_path: "map_book_storybook.json.meta.json",
      source_sha256: "e".repeat(64),
      canonical_sha256: "f".repeat(64),
    },
    soundtrack: {
      source_sha256: SOURCE_SHA256,
      canonical_sha256: CANONICAL_SHA256,
    },
    maps: [
      mapManifestEntry("village-hub", "Lantern Village", [
        "lantern_road",
        "village_night",
      ]),
      mapManifestEntry("stage-1-approach", "Sunpetal Approach", [
        "lantern_road",
        "mossy_steps",
      ]),
      mapManifestEntry("stage-2-gauntlet", "Bramble Gauntlet", [
        "lantern_road",
        "mossy_steps",
      ]),
      mapManifestEntry("stage-3-spires", "Highwhim Spires", [
        "mossy_steps",
        "village_night",
      ]),
    ],
  },
});

const authoredMapV2Manifest = authoredMapManifest;

/**
 * The three hunting stages exactly as they shipped before the village existed.
 *
 * Spelled out rather than derived, because the point of the assertion is that adding a village
 * changed none of them. A derived expectation would happily follow a typo in a stage id into the
 * saved runs and captures that already reference it.
 */
const BASELINE_HUNTING_PLANS = [
  {
    index: 0,
    id: "stage-1-approach",
    name: "The Approach",
    layout: "ascent",
    seedSalt: 0,
    mobRunStride: 2,
  },
  {
    index: 1,
    id: "stage-2-gauntlet",
    name: "The Gauntlet",
    layout: "gauntlet",
    seedSalt: 0x9e3779b9,
    mobRunStride: 2,
  },
  {
    index: 2,
    id: "stage-3-spires",
    name: "The Spires",
    layout: "spires",
    seedSalt: 0x85ebca6b,
    mobRunStride: 1,
  },
] as const;

const baselineFields = (plan: StagePlan) => ({
  index: plan.index,
  id: plan.id,
  name: plan.name,
  layout: plan.layout,
  seedSalt: plan.seedSalt,
  mobRunStride: plan.mobRunStride,
});

const huntingBook = () => buildStageBook({ hasVillage: false });
const villageBook = () => buildStageBook({ hasVillage: true });

describe("stage book", () => {
  test("parses and freezes the ordered current authored map book", () => {
    expect(parseMapBookManifest({ schema_version: 7 })).toBeNull();
    expect(() => parseMapBookManifest({})).toThrow(
      "manifest schema_version must be 7",
    );
    expect(() => parseMapBookManifest(null)).toThrow(
      "manifest must be a JSON object",
    );
    const parsed = parseMapBookManifest(authoredMapManifest());
    expect(parsed).toMatchObject({
      gameId: "storybook-preview",
      revision: 3,
      entryMapId: "village-hub",
    });
    expect(parsed?.maps.map(({ mapId, displayName, soundtrackTrackIds }) => ({
      mapId,
      displayName,
      soundtrackTrackIds,
    }))).toEqual([
      {
        mapId: "village-hub",
        displayName: "Lantern Village",
        soundtrackTrackIds: ["lantern_road", "village_night"],
      },
      {
        mapId: "stage-1-approach",
        displayName: "Sunpetal Approach",
        soundtrackTrackIds: ["lantern_road", "mossy_steps"],
      },
      {
        mapId: "stage-2-gauntlet",
        displayName: "Bramble Gauntlet",
        soundtrackTrackIds: ["lantern_road", "mossy_steps"],
      },
      {
        mapId: "stage-3-spires",
        displayName: "Highwhim Spires",
        soundtrackTrackIds: ["mossy_steps", "village_night"],
      },
    ]);
    expect(parsed?.maps.every((gameMap) => gameMap.levelProfile !== undefined)).toBeTrue();
    expect(Object.isFrozen(parsed)).toBeTrue();
    expect(Object.isFrozen(parsed?.maps)).toBeTrue();
    expect(Object.isFrozen(parsed?.maps[0])).toBeTrue();
    expect(Object.isFrozen(parsed?.maps[0]?.soundtrackTrackIds)).toBeTrue();
  });

  test("requires parent v7 and public map-book v2 identities", () => {
    for (const schema_version of [1, 5, 6, 8]) {
      expect(() =>
        parseMapBookManifest({ ...authoredMapManifest(), schema_version }),
      ).toThrow("parent manifest schema_version must be 7");
    }
    for (const identity of [
      { schema_version: 1, kind: "game-map-book-manifest-v1" },
      { schema_version: 3, kind: "game-map-book-manifest-v3" },
    ]) {
      const manifest = authoredMapManifest();
      Object.assign(manifest.map_book, identity);
      expect(() => parseMapBookManifest(manifest)).toThrow("identity is invalid");
    }
  });

  test("parses map-book v2 level profiles and uses them in stage planning", () => {
    const parsed = parseMapBookManifest(authoredMapV2Manifest());
    expect(parsed?.maps.every((gameMap) => gameMap.levelProfile !== undefined)).toBeTrue();
    expect(parsed?.maps[0]?.levelProfile?.role).toBe("social_hub");
    expect(parsed?.maps[1]?.levelProfile?.role).toBe("combat_field");
    expect(Object.isFrozen(parsed?.maps[0]?.levelProfile)).toBeTrue();
    expect(Object.isFrozen(parsed?.maps[0]?.levelProfile?.mechanisms)).toBeTrue();

    const book = buildStageBook({ hasVillage: true, mapBook: parsed });
    expect(book[0]).toMatchObject({
      kind: "village",
      vertical: false,
      mobRunStride: 0,
      levelProfile: {
        role: "social_hub",
        mechanisms: {
          encounter_model: "none",
          interaction_model: "proximity_dialogue",
        },
      },
    });
    expect(book[1]).toMatchObject({
      kind: "hunting",
      vertical: true,
      levelProfile: {
        role: "combat_field",
        mechanisms: {
          encounter_model: "continuous_population",
          interaction_model: "none",
        },
      },
    });

    const populationMapIds = [
      "stage-1-approach",
      "stage-2-gauntlet",
      "stage-3-spires",
    ];
    expect(() =>
      assertContinuousPopulationCoverage(book, populationMapIds),
    ).not.toThrow();
    expect(() =>
      assertContinuousPopulationCoverage(book, populationMapIds.slice(1)),
    ).toThrow("missing: stage-1-approach");
    expect(() =>
      assertContinuousPopulationCoverage(book, [...populationMapIds, "village-hub"]),
    ).toThrow("unexpected: village-hub");
    expect(() => assertContinuousPopulationCoverage(huntingBook(), [])).not.toThrow();
  });

  test("projects authored identity and music onto consumer-owned static geometry", () => {
    const mapBook = parseMapBookManifest(authoredMapManifest());
    const book = buildStageBook({ hasVillage: true, mapBook });
    expect(book.map((plan) => plan.id)).toEqual([
      "village-hub",
      "stage-1-approach",
      "stage-2-gauntlet",
      "stage-3-spires",
    ]);
    expect(book.map((plan) => plan.name)).toEqual([
      "Lantern Village",
      "Sunpetal Approach",
      "Bramble Gauntlet",
      "Highwhim Spires",
    ]);
    expect(stagePlanAt(book, 0)).toMatchObject({
      index: 0,
      kind: "village",
      terrain: "flat",
      vertical: false,
      mobRunStride: 0,
      soundtrackTrackIds: ["lantern_road", "village_night"],
    });
    expect(stagePlanAt(book, 2)).toMatchObject({
      index: 2,
      layout: "gauntlet",
      kind: "hunting",
      terrain: "rolling",
      vertical: true,
      soundtrackTrackIds: ["lantern_road", "mossy_steps"],
    });
  });

  test("fails closed for malformed declared map books and soundtrack bindings", () => {
    expect(() => parseMapBookManifest({ map_book: null })).toThrow(
      "invalid declared map_book",
    );
    const wrongBlockIdentity = authoredMapManifest();
    wrongBlockIdentity.map_book.schema_version = 3;
    expect(() => parseMapBookManifest(wrongBlockIdentity)).toThrow("identity is invalid");
    const wrongDigest = authoredMapManifest();
    wrongDigest.map_book.soundtrack.source_sha256 = "0".repeat(64);
    expect(() => parseMapBookManifest(wrongDigest)).toThrow(
      "soundtrack digest binding",
    );
    const unknownTrack = authoredMapManifest();
    unknownTrack.map_book.maps[0] = {
      ...unknownTrack.map_book.maps[0],
      soundtrack_track_ids: ["lantern_road", "missing_track"],
    };
    expect(() => parseMapBookManifest(unknownTrack)).toThrow(
      "soundtrack_track_ids",
    );
    const duplicateMap = authoredMapManifest();
    duplicateMap.map_book.maps[1] = {
      ...duplicateMap.map_book.maps[1],
      map_id: "village-hub",
    };
    expect(() => parseMapBookManifest(duplicateMap)).toThrow(
      "map entry is invalid",
    );
    const wrongEntry = authoredMapManifest();
    wrongEntry.map_book.entry_map_id = "stage-1-approach";
    expect(() => parseMapBookManifest(wrongEntry)).toThrow(
      "entry_map_id",
    );

    const missingProfileOnV2 = authoredMapV2Manifest();
    const { level_profile: _levelProfile, ...missingProfile } =
      missingProfileOnV2.map_book.maps[1]!;
    missingProfileOnV2.map_book.maps[1] = missingProfile as never;
    expect(() => parseMapBookManifest(missingProfileOnV2)).toThrow(
      "map entry keys are invalid",
    );
  });

  test("rejects authored identities that the static gameplay adapter cannot build", () => {
    const unknown = authoredMapManifest();
    unknown.map_book.maps[3] = mapManifestEntry("moon-cavern", "Moon Cavern", [
      "lantern_road",
      "mossy_steps",
    ]);
    const mapBook = parseMapBookManifest(unknown);
    expect(() => buildStageBook({ hasVillage: true, mapBook })).toThrow(
      "unsupported map_id moon-cavern",
    );

    const noVillage = parseMapBookManifest(authoredMapManifest());
    expect(() => buildStageBook({ hasVillage: false, mapBook: noVillage })).toThrow(
      "village identity",
    );
  });

  test("fails closed when authored semantics exceed or contradict demo capabilities", () => {
    const unsupported = authoredMapV2Manifest();
    const quietCombat = combatFieldProfile();
    quietCombat.mechanisms.encounter_model = "none";
    quietCombat.mechanisms.combat_model = "none";
    quietCombat.mechanisms.loot_model = "none";
    unsupported.map_book.maps[1] = mapManifestEntry(
      "stage-1-approach",
      "Sunpetal Approach",
      ["lantern_road", "mossy_steps"],
      quietCombat,
    );
    const parsedUnsupported = parseMapBookManifest(unsupported);
    expect(() =>
      buildStageBook({ hasVillage: true, mapBook: parsedUnsupported }),
    ).toThrow("role combat_field has an unsupported mechanism combination");

    const contradiction = authoredMapV2Manifest();
    contradiction.map_book.maps[1] = mapManifestEntry(
      "stage-1-approach",
      "Sunpetal Approach",
      ["lantern_road", "mossy_steps"],
      socialHubProfile(),
    );
    const parsedContradiction = parseMapBookManifest(contradiction);
    expect(() =>
      buildStageBook({ hasVillage: true, mapBook: parsedContradiction }),
    ).toThrow("contradicts its scrolling-demo geometry");
  });

  test("declares an ordered, uniquely identified, layout-covering plan", () => {
    for (const book of [huntingBook(), villageBook()]) {
      expect(book.length).toBeGreaterThan(1);
      expect(book.map((plan) => plan.index)).toEqual(
        Array.from({ length: book.length }, (_, index) => index),
      );
      expect(new Set(book.map((plan) => plan.id)).size).toBe(book.length);
      for (const plan of book) {
        expect(plan.id).toMatch(/^[a-z][a-z0-9-]*$/);
        expect(plan.name.length).toBeGreaterThan(0);
        expect(STAGE_LAYOUT_KINDS).toContain(plan.layout);
        expect(Object.isFrozen(plan)).toBeTrue();
      }
      // Every hunting stage is a different world rather than the same one relabelled. The
      // village is excluded because its layout is inert - it lays no platform graph at all - so
      // sharing a layout kind with a hunting stage costs nothing.
      const hunting = book.filter((plan) => plan.kind === "hunting");
      expect(new Set(hunting.map((plan) => plan.layout)).size).toBe(hunting.length);
      for (const plan of hunting) expect(plan.mobRunStride).toBeGreaterThanOrEqual(1);
      expect(() => stagePlanAt(book, book.length)).toThrow("outside the plan");
    }
  });

  test("leaves the no-village book exactly as it was before the village existed", () => {
    // A run without the opt-in has no village artifacts, so it must still see the same three
    // stages, in the same order, with the same salts - otherwise enabling the feature for one
    // run would silently re-terrain every run that never asked for it.
    const book = huntingBook();
    expect(book.map(baselineFields)).toEqual(
      BASELINE_HUNTING_PLANS.map((plan) => ({ ...plan })),
    );
    for (const plan of book) {
      expect(plan.kind).toBe("hunting");
      expect(plan.terrain).toBe("rolling");
      expect(plan.vertical).toBeTrue();
    }
    expect(STAGE_PLANS.map(baselineFields)).toEqual(book.map(baselineFields));
  });

  test("opens the village book with the hub and shifts every hunting stage down one", () => {
    const book = villageBook();
    expect(book.length).toBe(BASELINE_HUNTING_PLANS.length + 1);
    const village = stagePlanAt(book, 0);
    expect(village.id).toBe("village-hub");
    expect(village.name).toBe("Village");
    expect(village.kind).toBe("village");
    // Flat ground and no platform graph are what make the town read as a town rather than as a
    // fourth hunting ground with the monsters switched off.
    expect(village.terrain).toBe("flat");
    expect(village.vertical).toBeFalse();
    // Zero means "spawn no mobs", not "spawn one per flat run"; the scene skips mob spawning on
    // a village outright.
    expect(village.mobRunStride).toBe(0);
    expect(book.slice(1).map(baselineFields)).toEqual(
      BASELINE_HUNTING_PLANS.map((plan) => ({ ...plan, index: plan.index + 1 })),
    );
  });

  test("keeps the run's own terrain on the first hunting stage, not on whatever opens the book", () => {
    const base = heightmapSeedForTag("whimsical-storybook-fantasy-6fa8e3e1-ai");
    const hunting = huntingBook();
    // Without a village the opening stage is the world the generator authored for this tag; a
    // salted seed here would silently replace it with a stranger.
    expect(stageTerrainSeed(base, stagePlanAt(hunting, 0))).toBe(base);

    // With a village in front of it the authored terrain still belongs to the hunting ground.
    // The village is flat ground this adapter invents, so it must take a seed of its own rather
    // than inherit the one the world spec describes.
    const village = villageBook();
    expect(stageTerrainSeed(base, stagePlanAt(village, 1))).toBe(base);
    expect(stageTerrainSeed(base, stagePlanAt(village, 0))).not.toBe(base);
    expect(stagePlanAt(village, 0).seedSalt).not.toBe(0);

    for (const book of [hunting, village]) {
      const seeds = book.map((plan) => stageTerrainSeed(base, plan));
      expect(new Set(seeds).size).toBe(book.length);
      const maps = seeds.map((seed) =>
        JSON.stringify(buildHeightmapFromSeed(seed, HEIGHTMAP_OPTS)),
      );
      expect(new Set(maps).size).toBe(book.length);
      for (const seed of seeds) expect(Number.isSafeInteger(seed)).toBeTrue();
    }
    // Deterministic: the same run always lays out the same stages.
    expect(stageTerrainSeed(base, stagePlanAt(hunting, 1))).toBe(
      stageTerrainSeed(base, stagePlanAt(hunting, 1)),
    );
    expect(() => stageTerrainSeed(1.5, stagePlanAt(hunting, 1))).toThrow(
      "safe integer",
    );
  });

  test("routes each portal end and seals only the way back off the opening stage", () => {
    for (const book of [huntingBook(), villageBook()]) {
      expect(portalDestination(book, 0, "entry")).toBeNull();
      expect(portalDestination(book, 0, "exit")?.index).toBe(1);
      expect(portalDestination(book, 1, "entry")?.index).toBe(0);
      // The forward end always leads somewhere, wrapping past the last stage, so a portal is
      // never a door the player walks into and bounces off.
      expect(portalDestination(book, book.length - 1, "exit")?.index).toBe(0);
    }
  });

  test("makes the village the hub the last hunting stage wraps back to", () => {
    const book = villageBook();
    // This is the whole reason the village sits at index 0: a full circuit of the hunting
    // grounds returns the player to the town they set out from, rather than to a side room they
    // have to walk back through three stages to reach.
    const wrapped = portalDestination(book, book.length - 1, "exit");
    expect(wrapped?.id).toBe("village-hub");
    expect(wrapped?.kind).toBe("village");
    // And the village's own exit opens onto the first hunting stage.
    expect(portalDestination(book, 0, "exit")?.id).toBe("stage-1-approach");
  });

  test("clamps indices that arrive from outside the runtime", () => {
    for (const book of [huntingBook(), villageBook()]) {
      const last = book.length - 1;
      expect(normalizeStageIndex(book, 0)).toBe(0);
      expect(normalizeStageIndex(book, last)).toBe(last);
      expect(normalizeStageIndex(book, -4)).toBe(0);
      expect(normalizeStageIndex(book, book.length + 9)).toBe(last);
      for (const value of [undefined, null, "1", 1.5, Number.NaN]) {
        expect(normalizeStageIndex(book, value)).toBe(0);
      }
    }
    // A three-stage index is still in range in a four-stage book, so travelling between books
    // never silently rewrites a saved index.
    expect(normalizeStageIndex(villageBook(), 3)).toBe(3);
    expect(normalizeStageIndex(huntingBook(), 3)).toBe(2);
    // An empty book has no in-range answer; it reports 0 and leaves stagePlanAt to raise.
    expect(normalizeStageIndex([], 7)).toBe(0);
    expect(() => stagePlanAt([], 0)).toThrow("outside the plan");
  });
});
