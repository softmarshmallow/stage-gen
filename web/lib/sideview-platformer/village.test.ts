import { describe, expect, test } from "bun:test";
import { buildHeightmapFromSeed, slopeAt } from "./heightmap";
import {
  NPC_INTERACT_RANGE_PX,
  npcInteractionTarget,
  parseVillageManifest,
  planNpcPlacements,
} from "./village";

const TILE_PX = 64;
const COLUMNS = 200;
const WORLD_WIDTH_PX = COLUMNS * TILE_PX;

/** The village stage's own terrain: flat, so the town reads as a town. */
const FLAT_HEIGHTS = Object.freeze(Array.from({ length: COLUMNS }, () => 2));

/** A hunting stage's terrain, used to prove residents only ever stand on flat columns. */
const ROLLING_HEIGHTS = Object.freeze(
  buildHeightmapFromSeed(0x6fa8e3e1, { cols: COLUMNS, minH: 1, maxH: 4 }),
);

/** One villager as the manifest publishes them, in wire `lower_snake_case`. */
const wireNpc = (slot: number, name: string, roleLabel: string) => ({
  slot,
  name,
  role_label: roleLabel,
  lines: [`${name} greets you.`, `${name} remarks.`, `${name} says goodbye.`],
});

/** A complete village block as `village_manifest_block` writes it. */
const wireBlock = () => ({
  schema_version: 2,
  name: "Thornhollow",
  one_liner: "A lantern-lit waystation between the hunting grounds.",
  fixtures_theme: "carved timber and hanging lanterns",
  render: {
    frames: 1,
    orientation: "front",
    animation: "still",
    state: "still",
  },
  npcs: [
    wireNpc(0, "Merrow", "Provisioner"),
    wireNpc(1, "Halden", "Toolwright"),
    wireNpc(2, "Sable", "Archivist"),
    wireNpc(3, "Corrin", "Beastwarden"),
  ],
});

/** A whole manifest, as the scene fetches it once from `manifest_<tag>.json`. */
const wireManifest = (village?: unknown) => ({
  schema_version: 7,
  tag: "whimsical-storybook-fantasy-6fa8e3e1-ai",
  ...(village === undefined ? {} : { village }),
});

const placementInput = (
  overrides: Partial<Parameters<typeof planNpcPlacements>[0]> = {},
) => ({
  npcCount: 4,
  heights: FLAT_HEIGHTS,
  tilePx: TILE_PX,
  reservedColumns: new Set<number>(),
  worldWidthPx: WORLD_WIDTH_PX,
  ...overrides,
});

describe("parseVillageManifest", () => {
  test("reads the current published village out of a whole manifest", () => {
    const spec = parseVillageManifest(wireManifest(wireBlock()));
    expect(spec).not.toBeNull();
    // The wire is lower_snake_case and the runtime is camelCase; this is the one boundary that
    // translates, exactly as parseScaleReference does for the published scale references.
    expect(spec?.name).toBe("Thornhollow");
    expect(spec?.oneLiner).toBe(
      "A lantern-lit waystation between the hunting grounds.",
    );
    expect(spec?.fixturesTheme).toBe("carved timber and hanging lanterns");
    expect(spec?.render).toEqual({
      frames: 1,
      orientation: "front",
      animation: "still",
      state: "still",
    });
    expect(spec?.npcs.map((npc) => npc.slot)).toEqual([0, 1, 2, 3]);
    expect(spec?.npcs[0]).toEqual({
      slot: 0,
      name: "Merrow",
      roleLabel: "Provisioner",
      lines: ["Merrow greets you.", "Merrow remarks.", "Merrow says goodbye."],
    });
    // Frozen so a scene cannot mutate the village it was handed and leave the next stage build
    // reading someone else's edits.
    expect(Object.isFrozen(spec)).toBeTrue();
    expect(Object.isFrozen(spec?.npcs)).toBeTrue();
  });

  test("returns null only for true absence in a current envelope", () => {
    expect(parseVillageManifest(wireManifest())).toBeNull();
    for (const invalid of [undefined, null, "village", 7, [], true]) {
      expect(() => parseVillageManifest(invalid)).toThrow(
        "manifest must be a JSON object",
      );
    }
    expect(() => parseVillageManifest({})).toThrow(
      "manifest schema_version must be 7",
    );
  });

  test("requires parent v7 and village v2, with no legacy block fallback", () => {
    for (const schemaVersion of [1, 2, 6, 8]) {
      expect(() =>
        parseVillageManifest({
          ...wireManifest(wireBlock()),
          schema_version: schemaVersion,
        }),
      ).toThrow("manifest schema_version must be 7");
    }
    for (const schemaVersion of [1, 3, "2"]) {
      expect(() =>
        parseVillageManifest(
          wireManifest({ ...wireBlock(), schema_version: schemaVersion }),
        ),
      ).toThrow("schema_version must be 2");
    }
  });

  test("reads the v2 render profile and rejects malformed declarations", () => {
    const withRender = (render: unknown) =>
      wireManifest({ ...wireBlock(), render });
    expect(
      parseVillageManifest(
        withRender({
          frames: 1,
          orientation: "front",
          animation: "still",
          state: "still",
        }),
      )?.render,
    ).toEqual({
      frames: 1,
      orientation: "front",
      animation: "still",
      state: "still",
    });
    // A still has exactly one cell. The two fields are published separately and a sheet loaded
    // under the wrong one renders a fraction of the artwork without raising, so a block that
    // disagrees with itself is refused rather than reconciled.
    expect(() =>
      parseVillageManifest(
        withRender({
          frames: 4,
          orientation: "front",
          animation: "still",
          state: "still",
        }),
      ),
    ).toThrow("render animation and frames disagree");
    for (const bad of [
      null,
      "still",
      [],
      { frames: 0, orientation: "front", animation: "still", state: "still" },
      { frames: 1, orientation: "sideways", animation: "still", state: "still" },
      { frames: 4, orientation: "side", animation: "loop", state: "idle" },
      { frames: 4, orientation: "side", animation: "strip", state: "" },
    ]) {
      expect(() => parseVillageManifest(withRender(bad))).toThrow(
        "invalid declared village",
      );
    }
  });

  test("rejects the whole declared block when any resident is unusable", () => {
    const withNpcs = (npcs: unknown) => wireManifest({ ...wireBlock(), npcs });
    expect(() => parseVillageManifest(withNpcs([]))).toThrow(
      "exactly four residents",
    );
    expect(() => parseVillageManifest(withNpcs("Merrow"))).toThrow(
      "exactly four residents",
    );
    const bad = [
      { ...wireNpc(0, "Merrow", "Provisioner"), name: "" },
      { ...wireNpc(0, "Merrow", "Provisioner"), name: "   " },
      { ...wireNpc(0, "Merrow", "Provisioner"), role_label: undefined },
      { ...wireNpc(0, "Merrow", "Provisioner"), lines: [] },
      { ...wireNpc(0, "Merrow", "Provisioner"), lines: ["ok", ""] },
      { ...wireNpc(0, "Merrow", "Provisioner"), lines: "greeting" },
      { ...wireNpc(0, "Merrow", "Provisioner"), slot: -1 },
      { ...wireNpc(0, "Merrow", "Provisioner"), slot: 1.5 },
      { ...wireNpc(0, "Merrow", "Provisioner"), slot: "0" },
    ];
    for (const npc of bad) {
      const residents = wireBlock().npcs;
      residents[0] = npc as (typeof residents)[number];
      expect(() => parseVillageManifest(withNpcs(residents))).toThrow(
        "invalid declared village",
      );
    }
  });

  test("requires exact lower_snake_case block and resident keys", () => {
    expect(() =>
      parseVillageManifest(
        wireManifest({ ...wireBlock(), oneLiner: "camel alias" }),
      ),
    ).toThrow("village keys are invalid");
    const residentAlias = wireBlock();
    Object.assign(residentAlias.npcs[0], { roleLabel: "alias" });
    expect(() => parseVillageManifest(wireManifest(residentAlias))).toThrow(
      "village.npcs[0] keys are invalid",
    );
    for (const key of ["name", "one_liner", "fixtures_theme"] as const) {
      for (const value of ["", undefined, 12]) {
        expect(() =>
          parseVillageManifest(wireManifest({ ...wireBlock(), [key]: value })),
        ).toThrow("invalid declared village");
      }
    }
  });
});

describe("planNpcPlacements", () => {
  test("stands four residents on the flat middle of the town, evenly spread", () => {
    const placements = planNpcPlacements(placementInput());
    expect(placements.length).toBe(4);
    expect(placements.map((placement) => placement.slot)).toEqual([0, 1, 2, 3]);

    const columns = placements.map((placement) => placement.column);
    // Left to right in slot order, so slot 0 is the first resident the player meets.
    expect([...columns].sort((a, b) => a - b)).toEqual(columns);
    expect(new Set(columns).size).toBe(columns.length);

    // Clear of both portals: the entry stands at column 3 and the exit four columns from the
    // far end, and a resident inside a portal mouth competes with stage travel for a key press.
    expect(Math.min(...columns)).toBeGreaterThan(4);
    expect(Math.max(...columns)).toBeLessThan(COLUMNS - 5);

    // Evenly spread rather than clustered: the gaps between neighbours agree with each other and
    // with the gaps to the ends of the usable span.
    const gaps = columns.slice(1).map((column, i) => column - columns[i]!);
    expect(new Set(gaps).size).toBe(1);
    expect(gaps[0]).toBeGreaterThan(20);

    for (const placement of placements) {
      // Column midpoint, the same anchor obstacles, mobs, and portals use.
      expect(placement.x).toBe(placement.column * TILE_PX + TILE_PX / 2);
      expect(placement.x).toBeLessThan(WORLD_WIDTH_PX);
    }
    expect(Object.isFrozen(placements)).toBeTrue();
    expect(Object.isFrozen(placements[0])).toBeTrue();
  });

  test("is deterministic, so a village looks the same on every visit", () => {
    const first = planNpcPlacements(placementInput());
    const second = planNpcPlacements(placementInput());
    expect(second).toEqual(first);
    // Same heightmap, different Set instance holding the same reservations.
    const third = planNpcPlacements(
      placementInput({ reservedColumns: new Set<number>() }),
    );
    expect(third).toEqual(first);
  });

  test("never stands a resident on a slope column", () => {
    // A resident is bottom-anchored to the surface of the column they are on. On a slope column
    // that surface is not the one their neighbours share, and they read as sunk into the hill.
    const heights = [...ROLLING_HEIGHTS];
    const placements = planNpcPlacements(placementInput({ heights }));
    expect(placements.length).toBe(4);
    for (const placement of placements) {
      expect(slopeAt(heights, placement.column)).toBe("flat");
    }
  });

  test("skips reserved columns, the same gate mobs and obstacles pass", () => {
    const unreserved = planNpcPlacements(placementInput()).map(
      (placement) => placement.column,
    );
    const reservedColumns = new Set(unreserved);
    const placements = planNpcPlacements(placementInput({ reservedColumns }));
    expect(placements.length).toBe(4);
    for (const placement of placements) {
      expect(reservedColumns.has(placement.column)).toBeFalse();
    }
    // Reserving a whole band pushes the residents out of it rather than dropping them.
    const band = new Set(
      Array.from({ length: 60 }, (_, offset) => 20 + offset),
    );
    const shifted = planNpcPlacements(
      placementInput({ reservedColumns: band }),
    );
    expect(shifted.length).toBe(4);
    for (const placement of shifted) {
      expect(band.has(placement.column)).toBeFalse();
    }
  });

  test("places fewer residents rather than stacking two on one column", () => {
    // A town with almost nowhere to stand is honest about it. Two villagers sharing a column
    // would overlap exactly, and the interaction target would flip between them at random.
    const heights = Array.from({ length: 20 }, () => 2);
    const reservedColumns = new Set([6, 7, 8, 9, 10, 11, 13]);
    const placements = planNpcPlacements({
      npcCount: 4,
      heights,
      tilePx: TILE_PX,
      reservedColumns,
      worldWidthPx: 20 * TILE_PX,
    });
    expect(placements.map((placement) => placement.column)).toEqual([12]);
  });

  test("returns nothing when there is nowhere in the middle to stand", () => {
    expect(planNpcPlacements(placementInput({ npcCount: 0 }))).toEqual([]);
    // A stage narrower than the reserved margins at both ends has no middle at all.
    expect(
      planNpcPlacements({
        npcCount: 4,
        heights: Array.from({ length: 10 }, () => 2),
        tilePx: TILE_PX,
        reservedColumns: new Set<number>(),
        worldWidthPx: 10 * TILE_PX,
      }),
    ).toEqual([]);
    expect(
      planNpcPlacements(
        placementInput({
          reservedColumns: new Set(
            Array.from({ length: COLUMNS }, (_, column) => column),
          ),
        }),
      ),
    ).toEqual([]);
  });

  test("rejects a malformed world instead of guessing one", () => {
    expect(() => planNpcPlacements(placementInput({ npcCount: -1 }))).toThrow(
      "non-negative",
    );
    expect(() => planNpcPlacements(placementInput({ npcCount: 1.5 }))).toThrow(
      "non-negative",
    );
    expect(() => planNpcPlacements(placementInput({ tilePx: 0 }))).toThrow(
      "positive tile size",
    );
    expect(() =>
      planNpcPlacements(placementInput({ worldWidthPx: Number.NaN })),
    ).toThrow("positive world width");
    expect(() => planNpcPlacements(placementInput({ heights: [] }))).toThrow(
      "at least one terrain column",
    );
  });
});

describe("npcInteractionTarget", () => {
  const npcs = [
    { slot: 0, x: 1000 },
    { slot: 1, x: 4000 },
    { slot: 2, x: 7000 },
  ];

  test("names the nearest resident inside talking range", () => {
    expect(npcInteractionTarget(1000, npcs)).toBe(0);
    expect(npcInteractionTarget(4040, npcs)).toBe(1);
    expect(npcInteractionTarget(6960, npcs)).toBe(2);
  });

  test("treats the range as inclusive on both sides", () => {
    // The boundary is what the player feels: stopping a stride short of a villager and being
    // told there is nobody there reads as a broken prompt.
    expect(npcInteractionTarget(1000 + NPC_INTERACT_RANGE_PX, npcs)).toBe(0);
    expect(npcInteractionTarget(1000 - NPC_INTERACT_RANGE_PX, npcs)).toBe(0);
    expect(npcInteractionTarget(1000 + NPC_INTERACT_RANGE_PX + 1, npcs)).toBeNull();
    expect(npcInteractionTarget(1000 - NPC_INTERACT_RANGE_PX - 1, npcs)).toBeNull();
  });

  test("returns null when there is nobody to talk to", () => {
    expect(npcInteractionTarget(4000, [])).toBeNull();
    expect(npcInteractionTarget(2500, npcs)).toBeNull();
    // A non-finite player x during a teardown frame means "no target this frame", not a crash
    // that takes the update loop with it.
    expect(npcInteractionTarget(Number.NaN, npcs)).toBeNull();
    expect(npcInteractionTarget(Number.POSITIVE_INFINITY, npcs)).toBeNull();
    // A resident with a non-finite x is skipped rather than winning on a NaN comparison.
    expect(npcInteractionTarget(1000, [{ slot: 9, x: Number.NaN }])).toBeNull();
  });

  test("picks the closer of two neighbours, and the earlier one on a tie", () => {
    const pair = [
      { slot: 0, x: 1000 },
      { slot: 1, x: 1100 },
    ];
    expect(npcInteractionTarget(1010, pair)).toBe(0);
    expect(npcInteractionTarget(1090, pair)).toBe(1);
    // Standing exactly between them, the prompt must name the same resident every frame rather
    // than flicker as floating-point noise moves the comparison.
    expect(npcInteractionTarget(1050, pair)).toBe(0);
    expect(npcInteractionTarget(1050, [...pair].reverse())).toBe(1);
  });
});
