import { describe, expect, test } from "bun:test";
import { buildHeightmapFromSeed } from "./heightmap";
import {
  LADDER_ENDPOINT_TOLERANCE,
  VERTICAL_ASSET_ERROR_MAX_LENGTH,
  activateVerticalFeatureTransaction,
  advanceLadderMotion,
  buildPlatformRenderPlan,
  createVerticalWorld,
  ladderEntryAt,
  ladderJumpOffVelocity,
  ladderVisualBounds,
  platformDropThroughActive,
  prepareVerticalTraversalAssets,
  resolveVerticalLanding,
  selectDemoVerticalWorld,
  simulatePlatformJump,
  platformDropRecoverySteps,
  verticalCameraScrollY,
  verticalFeatureAfterAssetLoad,
  verticalObjectVisible,
  verticalSceneObjectVisible,
  verticalSpawnAllowed,
  verticalViewportWorldBounds,
  type UpperPlatform,
} from "./vertical";

const HEIGHTS = buildHeightmapFromSeed(1235206006, {
  cols: 200,
  minH: 1,
  maxH: 4,
});
const ENCOUNTER_RESERVED = new Set(
  Array.from({ length: 14 }, (_, column) => column),
);

function approvedWorld() {
  const selected = selectDemoVerticalWorld({
    heights: HEIGHTS,
    tilePixels: 64,
    baselineY: 720,
    worldWidth: 12_800,
    reservedColumns: ENCOUNTER_RESERVED,
  });
  if (!selected) throw new Error("approved world selection failed");
  return selected;
}

describe("vertical world contracts", () => {
  test("selects, sorts, freezes, and reserves the approved seed geometry", () => {
    const selected = approvedWorld();
    expect(selected.world.platforms).toEqual([
      {
        id: "tier-1-launch",
        left: 1280,
        right: 1664,
        deckY: 528,
        tier: 1,
        thickness: 32,
        sourceColumns: { start: 20, end: 26 },
      },
      {
        id: "tier-2-transfer",
        left: 1728,
        right: 2112,
        deckY: 464,
        tier: 2,
        thickness: 32,
        sourceColumns: { start: 27, end: 33 },
      },
      {
        id: "tier-3-bridge",
        left: 2176,
        right: 2560,
        deckY: 400,
        tier: 3,
        thickness: 32,
        sourceColumns: { start: 34, end: 40 },
      },
      {
        id: "tier-4-summit",
        left: 2624,
        right: 3008,
        deckY: 336,
        tier: 4,
        thickness: 32,
        sourceColumns: { start: 41, end: 47 },
      },
    ]);
    expect(selected.world.ladders).toEqual([
      {
        id: "ladder-summit",
        platformId: "tier-4-summit",
        centerX: 2976,
        upperDeckY: 336,
        lowerSurfaceY: 592,
        activationHalfWidth: 30,
        visualTopOvershoot: 32,
        visualBottomOvershoot: 32,
        visualWidth: 80,
      },
    ]);
    expect(selected.reservedColumns).toEqual(
      Array.from({ length: 29 }, (_, index) => index + 19),
    );
    expect(selected.routes).toEqual([
      { id: "jump-1", from: "terrain", to: "tier-1-launch", mode: "jump", rise: 64, gap: 0, landingStep: 15, horizontalRange: 270, ladderId: null },
      { id: "jump-2", from: "tier-1-launch", to: "tier-2-transfer", mode: "jump", rise: 64, gap: 64, landingStep: 15, horizontalRange: 270, ladderId: null },
      { id: "jump-3", from: "tier-2-transfer", to: "tier-3-bridge", mode: "jump", rise: 64, gap: 64, landingStep: 15, horizontalRange: 270, ladderId: null },
      { id: "jump-4", from: "tier-3-bridge", to: "tier-4-summit", mode: "jump", rise: 64, gap: 64, landingStep: 15, horizontalRange: 270, ladderId: null },
      { id: "drop-1", from: "tier-1-launch", to: "terrain", mode: "drop", rise: -64, gap: 0, landingStep: 9, horizontalRange: null, ladderId: null },
      { id: "drop-2", from: "tier-2-transfer", to: "terrain", mode: "drop", rise: -192, gap: 0, landingStep: 15, horizontalRange: null, ladderId: null },
      { id: "drop-3", from: "tier-3-bridge", to: "terrain", mode: "drop", rise: -256, gap: 0, landingStep: 18, horizontalRange: null, ladderId: null },
      { id: "drop-4", from: "tier-4-summit", to: "terrain", mode: "drop", rise: -320, gap: 0, landingStep: 20, horizontalRange: null, ladderId: null },
      { id: "ladder-up", from: "terrain", to: "tier-4-summit", mode: "ladder", rise: 256, gap: 0, landingStep: null, horizontalRange: null, ladderId: "ladder-summit" },
      { id: "ladder-down", from: "tier-4-summit", to: "terrain", mode: "ladder", rise: -256, gap: 0, landingStep: null, horizontalRange: null, ladderId: "ladder-summit" },
    ]);
    expect(
      selected.reservedColumns.filter((column) => ENCOUNTER_RESERVED.has(column)),
    ).toEqual([]);
    const reservation = new Set(selected.reservedColumns);
    for (const column of selected.reservedColumns) {
      expect(verticalSpawnAllowed(reservation, column)).toBeFalse();
    }
    expect(verticalSpawnAllowed(reservation, 18)).toBeTrue();
    expect(verticalSpawnAllowed(reservation, 48)).toBeTrue();
    expect(Object.isFrozen(selected)).toBeTrue();
    expect(Object.isFrozen(selected.world.platforms[0]!.sourceColumns)).toBeTrue();
    for (const ladder of selected.world.ladders) {
      expect(Object.keys(ladder).sort()).toEqual([
        "activationHalfWidth",
        "centerX",
        "id",
        "lowerSurfaceY",
        "platformId",
        "upperDeckY",
        "visualBottomOvershoot",
        "visualTopOvershoot",
        "visualWidth",
      ]);
      expect(ladder.activationHalfWidth).toBe(30);
    }
  });

  test("returns null when no eligible flat run remains", () => {
    expect(
      selectDemoVerticalWorld({
        heights: HEIGHTS,
        tilePixels: 64,
        baselineY: 720,
        worldWidth: 12_800,
        reservedColumns: new Set(HEIGHTS.map((_, column) => column)),
      }),
    ).toBeNull();
  });

  test("rejects caller occupancy across the complete graph footprint", () => {
    const heights = Array.from({ length: 80 }, () => 1);
    for (const occupied of [0, 28]) {
      expect(
        selectDemoVerticalWorld({
          heights,
          tilePixels: 64,
          baselineY: 720,
          worldWidth: 5120,
          reservedColumns: new Set([occupied]),
          afterColumn: 0,
          maximumColumnExclusive: 29,
        }),
      ).toBeNull();
    }
  });

  test("keeps gameplay geometry atomic with required ladder asset loading", () => {
    const selected = approvedWorld();
    const disabled = verticalFeatureAfterAssetLoad(selected, false);
    expect(disabled.world.platforms).toEqual([]);
    expect(disabled.world.ladders).toEqual([]);
    expect(disabled.routes).toEqual([]);
    expect(disabled.reservedColumns).toEqual([]);
    expect(
      ladderEntryAt({
        ladders: disabled.world.ladders,
        support: "terrain",
        supportId: null,
        x: 1312,
        footY: 592,
        up: true,
        down: false,
      }),
    ).toBeNull();
    expect(
      resolveVerticalLanding({
        x: 1400,
        previousFootY: 300,
        nextFootY: 400,
        vy: 100,
        terrainY: 592,
        platforms: disabled.world.platforms,
      }).support,
    ).toBe("air");
    expect(verticalFeatureAfterAssetLoad(selected, true)).toBe(selected);
  });

  test("rolls back rendering and gameplay for either assembly failure", () => {
    for (const failure of ["platform", "ladder", "commit"] as const) {
      const selected = approvedWorld();
      let committed = selected;
      const live: string[] = [];
      const destroyed: string[] = [];
      const loadedKeys: string[] = [];
      expect(() => {
        const activated = activateVerticalFeatureTransaction({
          selected,
          ladderAssetLoaded: true,
          climbAssetLoaded: true,
          platformMaterialsReady: true,
          assemblePlatforms: () => {
            live.push("platform");
            if (failure === "platform") throw new Error("platform assembly");
          },
          assembleLadders: () => {
            live.push("ladder");
            if (failure === "ladder") throw new Error("ladder assembly");
          },
          rollbackRendering: () => {
            destroyed.push(...live);
            live.length = 0;
          },
          commit: (selection) => {
            if (failure === "commit" && selection.routes.length > 0) {
              throw new Error("commit assembly");
            }
            committed = selection;
          },
        });
        if (activated) loadedKeys.push("ladder");
      }).toThrow(`${failure} assembly`);
      expect(live).toEqual([]);
      expect(destroyed).toEqual(
        failure === "platform" ? ["platform"] : ["platform", "ladder"],
      );
      expect(committed.world.platforms).toEqual([]);
      expect(committed.world.ladders).toEqual([]);
      expect(committed.routes).toEqual([]);
      expect(committed.reservedColumns).toEqual([]);
      expect(loadedKeys).toEqual([]);
    }
  });

  test("a thrown climb load is surfaced, bounded, and leaves no traversal state", async () => {
    const selected = approvedWorld();
    let committed = selected;
    const assembled: string[] = [];
    const registeredKeys = new Set<string>();
    const errors: string[] = [];
    let rollbackCount = 0;

    const readiness = await prepareVerticalTraversalAssets({
      selected,
      loadLadder: async () => {
        registeredKeys.add("ladder");
      },
      loadClimb: async () => {
        registeredKeys.add("character_climb");
        throw new Error(`decoder rejected ${"x".repeat(400)}`);
      },
      removeAsset: (key) => {
        registeredKeys.delete(key);
      },
      recordError: (message) => errors.push(message),
    });

    const activated = activateVerticalFeatureTransaction({
      selected,
      ...readiness,
      platformMaterialsReady: true,
      assemblePlatforms: () => assembled.push("platform"),
      assembleLadders: () => assembled.push("ladder"),
      rollbackRendering: () => {
        rollbackCount += 1;
        assembled.length = 0;
      },
      commit: (selection) => {
        committed = selection;
      },
    });

    expect(activated).toBeFalse();
    expect(readiness).toEqual({
      ladderAssetLoaded: false,
      climbAssetLoaded: false,
    });
    expect(rollbackCount).toBe(1);
    expect(assembled).toEqual([]);
    expect(committed.world.platforms).toEqual([]);
    expect(committed.world.ladders).toEqual([]);
    expect(committed.routes).toEqual([]);
    expect(committed.reservedColumns).toEqual([]);
    expect([...registeredKeys]).toEqual([]);
    expect(errors).toHaveLength(1);
    expect(errors[0]).toStartWith(
      "required vertical character climb asset failed: decoder rejected ",
    );
    expect(errors[0]!.length).toBe(VERTICAL_ASSET_ERROR_MAX_LENGTH);
  });

  test("skips a graph whose remote ladder endpoint is a terrain step", () => {
    expect(
      selectDemoVerticalWorld({
        heights: Array.from({ length: 40 }, (_, index) =>
          index === 27 ? 2 : 1,
        ),
        tilePixels: 64,
        baselineY: 720,
        worldWidth: 2560,
        afterColumn: 0,
        maximumColumnExclusive: 29,
      }),
    ).toBeNull();
  });

  test("continues after an invalid graph and selects the next complete footprint", () => {
    const heights = Array.from({ length: 80 }, () => 1);
    heights[27] = 2;
    const selected = selectDemoVerticalWorld({
      heights,
      tilePixels: 64,
      baselineY: 720,
      worldWidth: 5120,
      afterColumn: 0,
      maximumColumnExclusive: 70,
    });
    expect(selected?.world.platforms[0]?.sourceColumns).toEqual({
      start: 2,
      end: 8,
    });
    expect(selected?.world.ladders.map((ladder) => ladder.centerX)).toEqual([
      1824,
    ]);
  });

  test("proves the skilled jump chain without relying on ladder edges", () => {
    const selected = approvedWorld();
    const jumps = selected.routes.filter((route) => route.mode === "jump");
    expect(jumps).toHaveLength(4);
    expect(jumps.every((route) => route.ladderId === null)).toBeTrue();
    expect(jumps.map((route) => route.to)).toEqual([
      "tier-1-launch",
      "tier-2-transfer",
      "tier-3-bridge",
      "tier-4-summit",
    ]);
    expect(simulatePlatformJump({ rise: 64, gap: 64 })).toMatchObject({
      reachable: true,
      landingStep: 15,
      horizontalRange: 270,
    });
    expect(simulatePlatformJump({ rise: 64, gap: 64 }).apexRise).toBeCloseTo(
      81.6666666667,
      9,
    );
    expect(simulatePlatformJump({ rise: 96, gap: 0 }).reachable).toBeFalse();
    expect(simulatePlatformJump({ rise: 64, gap: 271 }).reachable).toBeFalse();
    expect(platformDropRecoverySteps({ fallDistance: 64 })).toBe(9);
    for (const platform of selected.world.platforms) {
      const route = selected.routes.find(
        (candidate) =>
          candidate.mode === "drop" && candidate.from === platform.id,
      )!;
      for (
        let column = platform.sourceColumns.start;
        column < platform.sourceColumns.end;
        column += 1
      ) {
        const terrainY = 720 - HEIGHTS[column]! * 64;
        const steps = platformDropRecoverySteps({
          fallDistance: terrainY - platform.deckY,
        });
        expect(steps).not.toBeNull();
        expect(steps!).toBeLessThanOrEqual(route.landingStep!);
        expect(
          resolveVerticalLanding({
            x: column * 64 + 32,
            previousFootY: platform.deckY + 1,
            nextFootY: terrainY + 1,
            vy: 500,
            terrainY,
            platforms: [],
          }).support,
        ).toBe("terrain");
      }
    }
  });

  test("rejects malformed, overlapping, non-flat, and out-of-world geometry", () => {
    const base = approvedWorld().world;
    const ladder = base.ladders[0]!;
    const platform = base.platforms.find(
      (candidate) => candidate.id === ladder.platformId,
    )!;
    const make = (
      platforms: Parameters<typeof createVerticalWorld>[0]["platforms"],
      ladders: Parameters<typeof createVerticalWorld>[0]["ladders"],
      heights: readonly number[] = HEIGHTS,
    ) =>
      createVerticalWorld({
        platforms,
        ladders,
        heights,
        tilePixels: 64,
        baselineY: 720,
        worldWidth: 12_800,
      });
    const plainPlatform = {
      id: platform.id,
      left: platform.left,
      right: platform.right,
      deckY: platform.deckY,
      tier: platform.tier,
      sourceColumns: platform.sourceColumns,
    };
    const plainLadder = {
      id: ladder.id,
      platformId: ladder.platformId,
      centerX: ladder.centerX,
      upperDeckY: ladder.upperDeckY,
      lowerSurfaceY: ladder.lowerSurfaceY,
    };
    expect(() => make([{ ...plainPlatform, left: Number.NaN }], [])).toThrow();
    expect(() => make([{ ...plainPlatform, deckY: 336.5 }], [])).toThrow();
    expect(() =>
      make([plainPlatform, { ...plainPlatform, id: "upper-copy" }], []),
    ).toThrow("overlap");
    expect(() => make([plainPlatform], [{ ...plainLadder, id: platform.id }])).toThrow(
      "unique",
    );
    expect(() =>
      make([plainPlatform], [{ ...plainLadder, centerX: platform.right + 1 }]),
    ).toThrow("endpoints");
    expect(() =>
      make([plainPlatform], [{ ...plainLadder, lowerSurfaceY: 529 }]),
    ).toThrow("four-tile");
    const brokenHeights = [...HEIGHTS];
    brokenHeights[47] = 1;
    expect(() => make([plainPlatform], [plainLadder], brokenHeights)).toThrow(
      "flat lower",
    );
    const edgeSurface = 720 - HEIGHTS[199]! * 64;
    const edgePlatform = {
      id: "edge-platform",
      left: 190 * 64,
      right: 200 * 64,
      deckY: edgeSurface - 256,
      tier: 1,
      sourceColumns: { start: 190, end: 200 },
    };
    expect(() =>
      make(
        [edgePlatform],
        [
          {
            id: "edge-ladder",
            platformId: edgePlatform.id,
            centerX: 199 * 64 + 32,
            upperDeckY: edgePlatform.deckY,
            lowerSurfaceY: edgeSurface,
          },
        ],
      ),
    ).toThrow("right terrain neighbor");
  });
});

describe("one-way platform geometry", () => {
  const platform: UpperPlatform = approvedWorld().world.platforms[0]!;

  test("ignores upward motion and catches downward high-delta crossings", () => {
    expect(
      resolveVerticalLanding({
        x: 1400,
        previousFootY: 400,
        nextFootY: 300,
        vy: -300,
        terrainY: 592,
        platforms: [platform],
      }).support,
    ).toBe("air");
    expect(
      resolveVerticalLanding({
        x: 1400,
        previousFootY: 100,
        nextFootY: 600,
        vy: 1_000,
        terrainY: 592,
        platforms: [platform],
      }),
    ).toEqual({
      footY: 528,
      vy: 0,
      support: "platform",
      supportId: "tier-1-launch",
    });
  });

  test("supports exact edges, stationary decks, terrain, and drop-through", () => {
    for (const x of [platform.left, platform.right]) {
      expect(
        resolveVerticalLanding({
          x,
          previousFootY: platform.deckY,
          nextFootY: platform.deckY,
          vy: 0,
          terrainY: 592,
          platforms: [platform],
        }).support,
      ).toBe("platform");
    }
    expect(
      resolveVerticalLanding({
        x: platform.left - 0.01,
        previousFootY: 320,
        nextFootY: 400,
        vy: 30,
        terrainY: 592,
        platforms: [platform],
      }).support,
    ).toBe("air");
    expect(
      resolveVerticalLanding({
        x: 1400,
        previousFootY: 528,
        nextFootY: 600,
        vy: 30,
        terrainY: 592,
        platforms: [platform],
        ignoredPlatformId: platform.id,
      }),
    ).toEqual({ footY: 592, vy: 0, support: "terrain", supportId: null });
  });

  test("recovers when horizontal motion enters raised terrain below its surface", () => {
    expect(
      resolveVerticalLanding({
        x: 2000,
        previousFootY: 610,
        nextFootY: 620,
        vy: 300,
        terrainY: 592,
        platforms: [],
      }),
    ).toEqual({ footY: 592, vy: 0, support: "terrain", supportId: null });
  });

  test("an ignored upper deck still lands a crossed lower support", () => {
    const lower = { ...platform, id: "lower-support", deckY: 560 };
    expect(
      resolveVerticalLanding({
        x: 1400,
        previousFootY: 528,
        nextFootY: 570,
        vy: 300,
        terrainY: 592,
        platforms: [platform, lower],
        ignoredPlatformId: platform.id,
      }),
    ).toEqual({
      footY: 560,
      vy: 0,
      support: "platform",
      supportId: "lower-support",
    });
  });

  test("chooses the highest crossed deck", () => {
    const lower = { ...platform, id: "lower", deckY: 560 };
    const result = resolveVerticalLanding({
      x: 1400,
      previousFootY: 200,
      nextFootY: 600,
      vy: 100,
      terrainY: 528,
      platforms: [lower, platform],
    });
    expect(result.supportId).toBe("tier-1-launch");
    expect(result.footY).toBe(528);
  });
});

describe("ladder endpoints, camera, culling, and rendering", () => {
  const world = approvedWorld().world;
  const up = world.ladders[0]!;

  test("accepts exact endpoint tolerances and rejects just-outside values", () => {
    for (const dx of [-30, 30]) {
      const entry = ladderEntryAt({
        ladders: world.ladders,
        support: "terrain",
        supportId: null,
        x: up.centerX + dx,
        footY: up.lowerSurfaceY + LADDER_ENDPOINT_TOLERANCE,
        up: true,
        down: false,
      });
      expect(entry?.ladder.id).toBe("ladder-summit");
    }
    expect(
      ladderEntryAt({
        ladders: world.ladders,
        support: "terrain",
        supportId: null,
        x: up.centerX + 31,
        footY: up.lowerSurfaceY,
        up: true,
        down: false,
      }),
    ).toBeNull();
    expect(
      ladderEntryAt({
        ladders: world.ladders,
        support: "platform",
        supportId: "tier-4-summit",
        x: up.centerX,
        footY: up.upperDeckY,
        up: false,
        down: true,
      })?.direction,
    ).toBe("down");
    expect(
      ladderEntryAt({
        ladders: world.ladders,
        support: "terrain",
        supportId: null,
        x: up.centerX,
        footY: up.lowerSurfaceY,
        up: true,
        down: true,
      }),
    ).toBeNull();
  });

  test("locks ladder motion, holds on neutral input, clamps exits, and jumps off", () => {
    expect(
      advanceLadderMotion({
        ladder: up,
        footY: 400,
        deltaSeconds: 1 / 30,
        up: false,
        down: false,
      }),
    ).toEqual({ footY: 400, vy: 0, exit: null });
    expect(
      advanceLadderMotion({
        ladder: up,
        footY: 400,
        deltaSeconds: 1 / 30,
        up: true,
        down: true,
      }),
    ).toEqual({ footY: 400, vy: 0, exit: null });
    expect(
      advanceLadderMotion({
        ladder: up,
        footY: 338,
        deltaSeconds: 1 / 30,
        up: true,
        down: false,
      }),
    ).toEqual({ footY: 336, vy: 0, exit: "platform" });
    expect(
      advanceLadderMotion({
        ladder: up,
        footY: 590,
        deltaSeconds: 1 / 30,
        up: false,
        down: true,
      }),
    ).toEqual({ footY: 592, vy: 0, exit: "terrain" });
    expect(ladderJumpOffVelocity({ left: true, right: false, facing: "right" })).toEqual({
      vx: -200,
      vy: -350,
    });
    expect(ladderJumpOffVelocity({ left: false, right: false, facing: "right" })).toEqual({
      vx: 200,
      vy: -350,
    });
  });

  test("expires drop-through only after time and deck clearance", () => {
    expect(
      platformDropThroughActive({ nowMs: 200, expiresAtMs: 180, footY: 352, deckY: 336 }),
    ).toBeTrue();
    expect(
      platformDropThroughActive({ nowMs: 180, expiresAtMs: 180, footY: 464, deckY: 336 }),
    ).toBeTrue();
    expect(
      platformDropThroughActive({ nowMs: 181, expiresAtMs: 180, footY: 353, deckY: 336 }),
    ).toBeFalse();
  });

  test("keeps randomized fixed-step ladder and landing sequences finite and bounded", () => {
    let seed = 0x51a7e;
    const random = () => {
      seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
      return seed / 0x1_0000_0000;
    };
    let footY = 400;
    for (let iteration = 0; iteration < 10_000; iteration += 1) {
      const choice = Math.floor(random() * 4);
      const motion = advanceLadderMotion({
        ladder: up,
        footY,
        deltaSeconds: 1 / 30,
        up: choice === 0 || choice === 3,
        down: choice === 1 || choice === 3,
      });
      expect(Number.isFinite(motion.footY)).toBeTrue();
      expect(motion.footY).toBeGreaterThanOrEqual(up.upperDeckY);
      expect(motion.footY).toBeLessThanOrEqual(up.lowerSurfaceY);
      footY = motion.exit ? 400 : motion.footY;

      const previous = 100 + random() * 450;
      const next = previous + (random() - 0.25) * 300;
      const landing = resolveVerticalLanding({
        x: 1200 + random() * 500,
        previousFootY: previous,
        nextFootY: next,
        vy: next - previous,
        terrainY: 592,
        platforms: world.platforms,
      });
      expect(Number.isFinite(landing.footY)).toBeTrue();
      expect(Number.isFinite(landing.vy)).toBeTrue();
      expect(landing.support === "air" || landing.vy === 0).toBeTrue();
    }
  });

  test("uses a deterministic zoom-aware deadzone with exact demo limits", () => {
    const scroll = (currentScrollY: number, footY: number, zoom: number) =>
      verticalCameraScrollY({
        currentScrollY,
        footY,
        zoom,
        viewportHeight: 720,
      });
    expect(scroll(0, 592, 1)).toBe(0);
    expect(scroll(0, 336, 1)).toBe(-84);
    expect(scroll(-84, 336, 1)).toBe(-84);
    expect(scroll(-84, 592, 1)).toBe(0);
    expect(scroll(0, -1000, 1)).toBe(-512);
    expect(scroll(0, 300, 2)).toBe(-90);
    expect(scroll(-90, 330, 2)).toBe(-90);
    expect(scroll(-90, 528, 2)).toBe(0);
  });

  test("culls by camera world view with one-tile overscan", () => {
    expect(
      verticalObjectVisible({
        left: 1280,
        right: 1600,
        top: 304,
        bottom: 624,
        cameraLeft: 0,
        cameraRight: 1280,
        cameraTop: 0,
        cameraBottom: 720,
        overscan: 64,
      }),
    ).toBeTrue();
    expect(
      verticalObjectVisible({
        left: 1280,
        right: 1600,
        top: 304,
        bottom: 624,
        cameraLeft: 1700,
        cameraRight: 2980,
        cameraTop: 0,
        cameraBottom: 720,
        overscan: 64,
      }),
    ).toBeFalse();
  });

  test("matches Phaser's centered zoom world view at zoom 1 and 1.2", () => {
    expect(
      verticalViewportWorldBounds({
        scrollX: 0,
        scrollY: 0,
        zoom: 1,
        viewportWidth: 1280,
        viewportHeight: 720,
      }),
    ).toEqual({ left: 0, right: 1280, top: 0, bottom: 720 });
    const zoomed = verticalViewportWorldBounds({
      scrollX: 672,
      scrollY: -84,
      zoom: 1.2,
      viewportWidth: 1280,
      viewportHeight: 720,
    });
    expect(zoomed.left).toBeCloseTo(778.6666666667, 8);
    expect(zoomed.right).toBeCloseTo(1845.3333333333, 8);
    expect(zoomed.top).toBeCloseTo(-24, 8);
    expect(zoomed.bottom).toBeCloseTo(576, 8);
  });

  test("scene culling keeps platform/ladders at real zoom boundaries across DPR", () => {
    const camera = {
      scrollX: 672,
      scrollY: -84,
      zoom: 1.2,
      viewportWidth: 1280,
      viewportHeight: 720,
    } as const;
    const platformBounds = { left: 1280, right: 1600, top: 336, bottom: 368 };
    const ladderBounds = { left: 1272, right: 1352, top: 304, bottom: 624 };
    for (const devicePixelRatio of [1, 2, 3, 4]) {
      for (const bounds of [platformBounds, ladderBounds]) {
        expect(
          verticalSceneObjectVisible({
            bounds,
            camera,
            overscan: 64,
            devicePixelRatio,
          }),
        ).toBeTrue();
      }
      // These two objects distinguish centered Phaser projection from treating
      // scroll as the zoomed world view's top-left corner.
      expect(
        verticalSceneObjectVisible({
          bounds: { left: 690, right: 700, top: 200, bottom: 210 },
          camera,
          overscan: 64,
          devicePixelRatio,
        }),
      ).toBeFalse();
      expect(
        verticalSceneObjectVisible({
          bounds: { left: 1880, right: 1890, top: 200, bottom: 210 },
          camera,
          overscan: 64,
          devicePixelRatio,
        }),
      ).toBeTrue();
      expect(
        verticalSceneObjectVisible({
          bounds: { left: 1300, right: 1310, top: 600, bottom: 610 },
          camera,
          overscan: 0,
          devicePixelRatio,
        }),
      ).toBeFalse();
      expect(
        verticalSceneObjectVisible({
          bounds: { left: 1300, right: 1310, top: 600, bottom: 610 },
          camera,
          overscan: 64,
          devicePixelRatio,
        }),
      ).toBeTrue();
    }
  });

  test("renders one connected body/cap and endpoint-only sides", () => {
    const plan = buildPlatformRenderPlan(world.platforms[0]!);
    expect(plan.body).toEqual({ x: 1280, y: 528, width: 384, height: 32 });
    expect(plan.cap).toEqual({ x: 1280, y: 528, width: 384, height: 12 });
    expect(plan.sides).toHaveLength(2);
    for (const zoom of [1, 1.2, 2]) {
      for (const dpr of [1, 2, 3, 4]) {
        for (const rect of [plan.body, plan.cap, ...plan.sides]) {
          const deviceX = rect.x * zoom * dpr * 5;
          const deviceWidth = rect.width * zoom * dpr * 5;
          expect(Math.abs(deviceX - Math.round(deviceX))).toBeLessThan(1e-6);
          expect(Math.abs(deviceWidth - Math.round(deviceWidth))).toBeLessThan(1e-6);
        }
      }
    }
  });

  test("binds visual overshoot once and rejects mutation drift", () => {
    expect(ladderVisualBounds(up)).toEqual({
      left: 2936,
      right: 3016,
      top: 304,
      bottom: 624,
      width: 80,
      height: 320,
    });
    const mutated = {
      ...up,
      visualTopOvershoot: 24,
    } as unknown as typeof up;
    expect(() => ladderVisualBounds(mutated)).toThrow("visual contract drifted");
  });
});
