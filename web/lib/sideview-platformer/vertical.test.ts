import { describe, expect, test } from "bun:test";
import { buildHeightmapFromSeed } from "./heightmap";
import { PREPARED_RUNTIME_BLOCKS } from "@/lib/manifest/prepared-manifest";
import {
  advanceClimbMotion,
  resolveVerticalLanding as resolveFamilyVerticalLanding,
} from "@/lib/families/sideview/traversal";
import {
  CLIMBABLE_JUMP_HORIZONTAL_SPEED,
  CLIMBABLE_JUMP_VELOCITY,
  CLIMBABLE_SPEED,
  PLATFORMER_CLIMB_PROFILE,
  parsePlatformerTraversalBlocks,
} from "./vertical";

/** One ladder, stated flat, for the "the genre's call is the family's call" assertions. */
const familyLadder = {
  id: "ladder-family",
  platformId: "deck-family",
  variantId: "v",
  role: "ladder",
  centerX: 320,
  upperDeckY: 500,
  lowerSurfaceY: 628,
  activationHalfWidth: 30,
  visualTopOvershoot: 32,
  visualBottomOvershoot: 32,
  visualWidth: 64,
} as const;
import {
  DEMO_VERTICAL_LAYOUT_KINDS,
  CLIMBABLE_ENDPOINT_TOLERANCE,
  PLATFORMER_AIR_JUMP_VELOCITY,
  PLATFORMER_COYOTE_MS,
  PLATFORMER_JUMP_VELOCITY,
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
  resolveCrouchHorizontalVelocity,
  resolveJumpRequest,
  resolveTerrainStep,
  resolveTerrainWalk,
  resolveVerticalLanding,
  selectDemoVerticalWorld,
  simulatePlatformJump,
  platformDropRecoverySteps,
  verticalFeatureAfterAssetLoad,
  verticalObjectVisible,
  verticalSceneObjectVisible,
  verticalSpawnAllowed,
  verticalViewportWorldBounds,
  type UpperPlatform,
  CLIMBABLE_VISUAL_WIDTH,
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
      {"id":"tier-1-launch","left":1280,"right":1664,"deckY":528,"tier":1,"sourceColumns":{"start":20,"end":26},"thickness":32},
      {"id":"tier-2-transfer","left":1728,"right":2112,"deckY":464,"tier":2,"sourceColumns":{"start":27,"end":33},"thickness":32},
      {"id":"tier-3-bridge","left":2176,"right":2560,"deckY":400,"tier":3,"sourceColumns":{"start":34,"end":40},"thickness":32},
      {"id":"sky-ledge","left":2304,"right":2560,"deckY":208,"tier":6,"sourceColumns":{"start":36,"end":40},"thickness":32},
      {"id":"tier-4-summit","left":2624,"right":3008,"deckY":336,"tier":4,"sourceColumns":{"start":41,"end":47},"thickness":32},
      {"id":"sky-cap","left":2688,"right":2944,"deckY":144,"tier":7,"sourceColumns":{"start":42,"end":46},"thickness":32},
      {"id":"stone-first","left":3072,"right":3200,"deckY":336,"tier":4,"sourceColumns":{"start":48,"end":50},"thickness":32},
      {"id":"stone-second","left":3264,"right":3392,"deckY":208,"tier":6,"sourceColumns":{"start":51,"end":53},"thickness":32},
      {"id":"sky-span","left":3456,"right":3776,"deckY":208,"tier":6,"sourceColumns":{"start":54,"end":59},"thickness":32},
    ]);
    expect(selected.world.climbables).toEqual([
      {"id":"ladder-summit","platformId":"tier-4-summit","variantId":"ladder-summit","role":"ladder","centerX":2976,"upperDeckY":336,"lowerSurfaceY":592,"activationHalfWidth":30,"visualTopOvershoot":32,"visualBottomOvershoot":32,"visualWidth":64},
    ]);
    expect(selected.reservedColumns).toEqual(
      Array.from({ length: 40 }, (_, index) => index + 19),
    );
    expect(selected.routes).toEqual([
      {"id":"jump-1","from":"terrain","to":"tier-1-launch","mode":"jump","rise":64,"gap":0,"landingStep":15,"horizontalRange":270,"ladderId":null},
      {"id":"jump-2","from":"tier-1-launch","to":"tier-2-transfer","mode":"jump","rise":64,"gap":64,"landingStep":15,"horizontalRange":270,"ladderId":null},
      {"id":"jump-3","from":"tier-2-transfer","to":"tier-3-bridge","mode":"jump","rise":64,"gap":64,"landingStep":15,"horizontalRange":270,"ladderId":null},
      {"id":"jump-4","from":"tier-3-bridge","to":"tier-4-summit","mode":"jump","rise":64,"gap":64,"landingStep":15,"horizontalRange":270,"ladderId":null},
      {"id":"jump-5","from":"tier-4-summit","to":"sky-ledge","mode":"double-jump","rise":128,"gap":64,"landingStep":25,"horizontalRange":450,"ladderId":null},
      {"id":"jump-6","from":"sky-ledge","to":"sky-cap","mode":"jump","rise":64,"gap":128,"landingStep":15,"horizontalRange":270,"ladderId":null},
      {"id":"jump-7","from":"tier-4-summit","to":"stone-first","mode":"jump","rise":0,"gap":64,"landingStep":20,"horizontalRange":360,"ladderId":null},
      {"id":"jump-8","from":"stone-first","to":"stone-second","mode":"double-jump","rise":128,"gap":64,"landingStep":25,"horizontalRange":450,"ladderId":null},
      {"id":"jump-9","from":"stone-second","to":"sky-span","mode":"jump","rise":0,"gap":64,"landingStep":20,"horizontalRange":360,"ladderId":null},
      {"id":"drop-tier-1-launch","from":"tier-1-launch","to":"terrain","mode":"drop","rise":-64,"gap":0,"landingStep":9,"horizontalRange":null,"ladderId":null},
      {"id":"drop-tier-2-transfer","from":"tier-2-transfer","to":"terrain","mode":"drop","rise":-192,"gap":0,"landingStep":15,"horizontalRange":null,"ladderId":null},
      {"id":"drop-tier-3-bridge","from":"tier-3-bridge","to":"terrain","mode":"drop","rise":-256,"gap":0,"landingStep":18,"horizontalRange":null,"ladderId":null},
      {"id":"drop-sky-ledge","from":"sky-ledge","to":"tier-3-bridge","mode":"drop","rise":-192,"gap":0,"landingStep":15,"horizontalRange":null,"ladderId":null},
      {"id":"drop-tier-4-summit","from":"tier-4-summit","to":"terrain","mode":"drop","rise":-320,"gap":0,"landingStep":20,"horizontalRange":null,"ladderId":null},
      {"id":"drop-sky-cap","from":"sky-cap","to":"tier-4-summit","mode":"drop","rise":-192,"gap":0,"landingStep":15,"horizontalRange":null,"ladderId":null},
      {"id":"drop-stone-first","from":"stone-first","to":"terrain","mode":"drop","rise":-256,"gap":0,"landingStep":18,"horizontalRange":null,"ladderId":null},
      {"id":"drop-stone-second","from":"stone-second","to":"terrain","mode":"drop","rise":-448,"gap":0,"landingStep":23,"horizontalRange":null,"ladderId":null},
      {"id":"drop-sky-span","from":"sky-span","to":"terrain","mode":"drop","rise":-448,"gap":0,"landingStep":23,"horizontalRange":null,"ladderId":null},
      {"id":"ladder-summit-up","from":"terrain","to":"tier-4-summit","mode":"climbable","rise":256,"gap":0,"landingStep":null,"horizontalRange":null,"ladderId":"ladder-summit"},
      {"id":"ladder-summit-down","from":"tier-4-summit","to":"terrain","mode":"climbable","rise":-256,"gap":0,"landingStep":null,"horizontalRange":null,"ladderId":"ladder-summit"},
    ]);
    expect(
      selected.reservedColumns.filter((column) => ENCOUNTER_RESERVED.has(column)),
    ).toEqual([]);
    const reservation = new Set(selected.reservedColumns);
    for (const column of selected.reservedColumns) {
      expect(verticalSpawnAllowed(reservation, column)).toBeFalse();
    }
    expect(verticalSpawnAllowed(reservation, 18)).toBeTrue();
    expect(verticalSpawnAllowed(reservation, 59)).toBeTrue();
    expect(Object.isFrozen(selected)).toBeTrue();
    expect(Object.isFrozen(selected.world.platforms[0]!.sourceColumns)).toBeTrue();
    for (const climbable of selected.world.climbables) {
      expect(Object.keys(climbable).sort()).toEqual([
        "activationHalfWidth",
        "centerX",
        "id",
        "lowerSurfaceY",
        "platformId",
        "role",
        "upperDeckY",
        "variantId",
        "visualBottomOvershoot",
        "visualTopOvershoot",
        "visualWidth",
      ]);
      expect(climbable.activationHalfWidth).toBe(30);
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
    expect(disabled.world.climbables).toEqual([]);
    expect(disabled.routes).toEqual([]);
    expect(disabled.reservedColumns).toEqual([]);
    expect(
      ladderEntryAt({
        climbables: disabled.world.climbables,
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
    for (const failure of ["platform", "climbable", "commit"] as const) {
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
          assembleClimbables: () => {
            live.push("climbable");
            if (failure === "climbable") throw new Error("climbable assembly");
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
        if (activated) loadedKeys.push("climbable");
      }).toThrow(`${failure} assembly`);
      expect(live).toEqual([]);
      expect(destroyed).toEqual(
        failure === "platform" ? ["platform"] : ["platform", "climbable"],
      );
      expect(committed.world.platforms).toEqual([]);
      expect(committed.world.climbables).toEqual([]);
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
        registeredKeys.add("climbable");
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
      assembleClimbables: () => assembled.push("climbable"),
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
    expect(committed.world.climbables).toEqual([]);
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
    expect(selected?.world.climbables.map((ladder) => ladder.centerX)).toEqual([
      1824,
    ]);
  });

  test("proves the skilled jump chain without relying on ladder edges", () => {
    const selected = approvedWorld();
    const jumps = selected.routes.filter(
      (route) => route.mode === "jump" || route.mode === "double-jump",
    );
    expect(jumps).toHaveLength(9);
    expect(jumps.every((route) => route.ladderId === null)).toBeTrue();
    expect(jumps.map((route) => route.to)).toEqual([
      "tier-1-launch",
      "tier-2-transfer",
      "tier-3-bridge",
      "tier-4-summit",
      "sky-ledge",
      "sky-cap",
      "stone-first",
      "stone-second",
      "sky-span",
    ]);
    expect(simulatePlatformJump({ rise: 64, gap: 64 })).toMatchObject({
      reachable: true,
      landingStep: 15,
      horizontalRange: 270,
      airJumpStep: null,
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
      // Stacked decks fall onto the deck below them, so only the platforms
      // whose route actually names terrain are checked against terrain here.
      if (route.to !== "terrain") continue;
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

  test("declares an air-jump gate only where the ground jump falls short", () => {
    const selected = approvedWorld();
    const gates = selected.routes.filter((route) => route.mode === "double-jump");
    expect(gates.map((route) => route.id)).toEqual(["jump-5", "jump-8"]);
    for (const gate of gates) {
      // Both halves of the claim: out of reach from the ground, in reach with
      // the second impulse. A gate a single jump clears is mislabelled.
      expect(
        simulatePlatformJump({ rise: gate.rise, gap: gate.gap }).reachable,
      ).toBeFalse();
      expect(
        simulatePlatformJump({
          rise: gate.rise,
          gap: gate.gap,
          airJumpVelocity: PLATFORMER_AIR_JUMP_VELOCITY,
        }),
      ).toMatchObject({ reachable: true, airJumpStep: 11 });
    }
    for (const route of selected.routes) {
      if (route.mode !== "jump") continue;
      expect(
        simulatePlatformJump({
          rise: Math.max(0, route.rise),
          gap: route.gap,
        }).reachable,
      ).toBeTrue();
    }
    const doubled = simulatePlatformJump({
      rise: 128,
      gap: 0,
      airJumpVelocity: PLATFORMER_AIR_JUMP_VELOCITY,
    });
    expect(doubled.apexRise).toBeGreaterThan(128);
    expect(doubled.apexRise).toBeLessThan(
      simulatePlatformJump({ rise: 128, gap: 0 }).apexRise * 2,
    );
  });

  test("stacks decks that share columns and drops onto the one below", () => {
    const selected = approvedWorld();
    const byId = new Map(
      selected.world.platforms.map((platform) => [platform.id, platform]),
    );
    const ledge = byId.get("sky-ledge")!;
    const bridge = byId.get("tier-3-bridge")!;
    // Columns shared, bands apart: the branch runs directly over the spine.
    expect(ledge.left).toBeGreaterThanOrEqual(bridge.left);
    expect(ledge.right).toBeLessThanOrEqual(bridge.right);
    expect(bridge.deckY - ledge.deckY).toBe(192);
    expect(
      selected.routes.find((route) => route.id === "drop-sky-ledge"),
    ).toMatchObject({ to: "tier-3-bridge", rise: -192 });
    expect(
      selected.routes.find((route) => route.id === "drop-sky-cap"),
    ).toMatchObject({ to: "tier-4-summit", rise: -192 });
    // And the runtime resolver agrees: a foot falling through both bands
    // stops on the higher deck rather than the ground under them.
    expect(
      resolveVerticalLanding({
        x: ledge.left + 32,
        previousFootY: ledge.deckY - 4,
        nextFootY: bridge.deckY + 40,
        vy: 600,
        terrainY: 592,
        platforms: selected.world.platforms,
      }),
    ).toMatchObject({ support: "platform", supportId: "sky-ledge" });
  });

  test("selects a distinct graph for every stage layout", () => {
    const shapes = DEMO_VERTICAL_LAYOUT_KINDS.map((layout) => {
      const selected = selectDemoVerticalWorld({
        heights: HEIGHTS,
        tilePixels: 64,
        baselineY: 720,
        worldWidth: 12_800,
        reservedColumns: ENCOUNTER_RESERVED,
        layout,
      });
      if (!selected) throw new Error(`layout ${layout} selected nothing`);
      return { layout, selected };
    });
    const signatures = new Set(
      shapes.map(({ selected }) =>
        JSON.stringify(
          selected.world.platforms.map((platform) => [
            platform.id,
            platform.left,
            platform.deckY,
          ]),
        ),
      ),
    );
    expect(signatures.size).toBe(DEMO_VERTICAL_LAYOUT_KINDS.length);
    for (const { selected } of shapes) {
      expect(selected.world.platforms.length).toBeGreaterThanOrEqual(7);
      expect(selected.world.climbables).toHaveLength(1);
      expect(
        selected.routes.some((route) => route.mode === "double-jump"),
      ).toBeTrue();
      expect(
        selected.reservedColumns.filter((column) =>
          ENCOUNTER_RESERVED.has(column),
        ),
      ).toEqual([]);
    }
  });

  test("resolves a ledge as a fall and recovers a foot under solid ground", () => {
    // Walking off a raised column used to snap the foot straight down onto the
    // new surface, so a four-tile cliff read exactly like flat ground.
    expect(resolveTerrainStep({ footY: 528, surfaceY: 592 })).toEqual({
      footY: 528,
      support: "air",
    });
    // Lifting is a recovery, not a climb: the walk resolver stops a foot at
    // the face before it can arrive here, and the alternative to lifting is a
    // player sealed inside a hill.
    expect(resolveTerrainStep({ footY: 592, surfaceY: 528 })).toEqual({
      footY: 528,
      support: "terrain",
    });
    expect(resolveTerrainStep({ footY: 592, surfaceY: 592 })).toEqual({
      footY: 592,
      support: "terrain",
    });
    // Sub-pixel drift is absorbed rather than launching a fall every frame.
    expect(resolveTerrainStep({ footY: 591.5, surfaceY: 592 }).support).toBe(
      "terrain",
    );
    expect(() =>
      resolveTerrainStep({ footY: Number.NaN, surfaceY: 592 }),
    ).toThrow("finite");
    expect(() =>
      resolveTerrainStep({ footY: 592, surfaceY: 592, tolerance: -1 }),
    ).toThrow("nonnegative");
  });

  test("stops a walk at a raised column face so the way up is a jump", () => {
    // Columns 0-1 at 592, column 2 raised to 528, column 3 dropped to 656.
    const surfaceAt = (column: number) =>
      column === 2 ? 528 : column >= 3 ? 656 : 592;
    const walk = (previousX: number, nextX: number, footY: number) =>
      resolveTerrainWalk({
        previousX,
        nextX,
        footY,
        tilePixels: 64,
        surfaceAt,
      });
    // Walking right into the raised face stops a pixel short of it, still
    // inside column 1, instead of climbing a whole tile for free.
    expect(walk(120, 140, 592)).toEqual({
      x: 127,
      blocked: true,
      blockedColumn: 2,
    });
    // Held against it, the resolved position is stable rather than creeping.
    expect(walk(127, 145, 592).x).toBe(127);
    // Coming back the other way stops on the open side of the same face.
    expect(walk(200, 180, 656)).toEqual({
      x: 192,
      blocked: true,
      blockedColumn: 2,
    });
    // A jump that has cleared the surface passes over it.
    expect(walk(120, 140, 520)).toEqual({
      x: 140,
      blocked: false,
      blockedColumn: null,
    });
    // Descents are never walls: walking off column 2 stays a fall.
    expect(walk(180, 200, 528).blocked).toBeFalse();
    // A shelf-bound actor stops before the same descent instead of walking into a pit.
    expect(
      resolveTerrainWalk({
        previousX: 180,
        nextX: 200,
        footY: 528,
        tilePixels: 64,
        surfaceAt,
        allowDescents: false,
      }),
    ).toEqual({ x: 191, blocked: true, blockedColumn: 3 });
    // Movement inside one column is never resolved against a neighbour.
    expect(walk(130, 140, 592).blocked).toBeFalse();
    expect(() =>
      walk(Number.NaN, 140, 592),
    ).toThrow("finite");
    expect(() =>
      resolveTerrainWalk({
        previousX: 0,
        nextX: 10,
        footY: 0,
        tilePixels: 0,
        surfaceAt,
      }),
    ).toThrow("positive");
  });

  test("clears a one-tile rise with the grounded jump it now requires", () => {
    // Every terrain step in this heightfield is a whole tile, so the wall the
    // walk resolver puts up has to be one the grounded jump can actually clear
    // — otherwise a rise would be an unpassable seam rather than a climb.
    const oneTile = simulatePlatformJump({ rise: 64, gap: 0 });
    expect(oneTile.reachable).toBeTrue();
    expect(oneTile.apexRise).toBeGreaterThan(64);
    // And the clearance window is wide enough to cross the face while over it:
    // at run speed the foot travels more than a tile inside that window.
    expect(oneTile.horizontalRange!).toBeGreaterThan(64);
  });

  test("crouch walking stays directional and slower than ordinary walking", () => {
    expect(resolveCrouchHorizontalVelocity(420)).toBe(80);
    expect(resolveCrouchHorizontalVelocity(-420)).toBe(-80);
    expect(resolveCrouchHorizontalVelocity(40)).toBe(40);
    expect(resolveCrouchHorizontalVelocity(0)).toBe(0);
    expect(() => resolveCrouchHorizontalVelocity(Number.NaN)).toThrow("finite");
  });

  test("spends one air jump per airborne stretch and honours coyote time", () => {
    expect(
      resolveJumpRequest({
        support: "terrain",
        airJumpsUsed: 0,
        nowMs: 1000,
        coyoteExpiresAtMs: null,
        crouching: false,
      }),
    ).toEqual({
      kind: "ground",
      vy: -PLATFORMER_JUMP_VELOCITY,
      airJumpsUsed: 0,
    });
    expect(
      resolveJumpRequest({
        support: "air",
        airJumpsUsed: 0,
        nowMs: 1000,
        coyoteExpiresAtMs: null,
        crouching: false,
      }),
    ).toEqual({
      kind: "air",
      vy: -PLATFORMER_AIR_JUMP_VELOCITY,
      airJumpsUsed: 1,
    });
    // The budget is one: a third press in the same airborne stretch buys
    // nothing, which is what keeps a double jump from becoming flight.
    expect(
      resolveJumpRequest({
        support: "air",
        airJumpsUsed: 1,
        nowMs: 1000,
        coyoteExpiresAtMs: null,
        crouching: false,
      }),
    ).toEqual({ kind: "none", vy: 0, airJumpsUsed: 1 });
    // Inside the grace window a lost ledge still buys the full launch.
    expect(
      resolveJumpRequest({
        support: "air",
        airJumpsUsed: 0,
        nowMs: 1000,
        coyoteExpiresAtMs: 1000 + PLATFORMER_COYOTE_MS,
        crouching: false,
      }).kind,
    ).toBe("ground");
    expect(
      resolveJumpRequest({
        support: "air",
        airJumpsUsed: 0,
        nowMs: 1000 + PLATFORMER_COYOTE_MS + 1,
        coyoteExpiresAtMs: 1000 + PLATFORMER_COYOTE_MS,
        crouching: false,
      }).kind,
    ).toBe("air");
    // A spent air jump closes the grace window too, so one press cannot be
    // redeemed twice by a stale deadline.
    expect(
      resolveJumpRequest({
        support: "air",
        airJumpsUsed: 1,
        nowMs: 1000,
        coyoteExpiresAtMs: 1000 + PLATFORMER_COYOTE_MS,
        crouching: false,
      }).kind,
    ).toBe("none");
    expect(
      resolveJumpRequest({
        support: "terrain",
        airJumpsUsed: 0,
        nowMs: 0,
        coyoteExpiresAtMs: null,
        crouching: true,
      }).kind,
    ).toBe("none");
    expect(
      resolveJumpRequest({
        support: "climbable",
        airJumpsUsed: 0,
        nowMs: 0,
        coyoteExpiresAtMs: null,
        crouching: false,
      }).kind,
    ).toBe("none");
    expect(() =>
      resolveJumpRequest({
        support: "air",
        airJumpsUsed: -1,
        nowMs: 0,
        coyoteExpiresAtMs: null,
        crouching: false,
      }),
    ).toThrow("nonnegative");
  });

  test("rejects malformed, overlapping, non-flat, and out-of-world geometry", () => {
    const base = approvedWorld().world;
    const ladder = base.climbables[0]!;
    const platform = base.platforms.find(
      (candidate) => candidate.id === ladder.platformId,
    )!;
    const make = (
      platforms: Parameters<typeof createVerticalWorld>[0]["platforms"],
      climbables: Parameters<typeof createVerticalWorld>[0]["climbables"],
      heights: readonly number[] = HEIGHTS,
    ) =>
      createVerticalWorld({
        platforms,
        climbables,
        heights,
        tilePixels: 64,
        baselineY: 720,
        topY: 0,
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
      variantId: ladder.variantId,
      centerX: ladder.centerX,
      upperDeckY: ladder.upperDeckY,
      lowerSurfaceY: ladder.lowerSurfaceY,
    };
    expect(() => make([{ ...plainPlatform, left: Number.NaN }], [])).toThrow();
    expect(() => make([{ ...plainPlatform, deckY: 336.5 }], [])).toThrow();
    expect(() => make([{ ...plainPlatform, deckY: -64 }], [])).toThrow(
      "outside its world",
    );
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
            variantId: "edge-ladder",
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
  const up = world.climbables[0]!;

  test("accepts exact endpoint tolerances and rejects just-outside values", () => {
    for (const dx of [-30, 30]) {
      const entry = ladderEntryAt({
        climbables: world.climbables,
        support: "terrain",
        supportId: null,
        x: up.centerX + dx,
        footY: up.lowerSurfaceY + CLIMBABLE_ENDPOINT_TOLERANCE,
        up: true,
        down: false,
      });
      expect(entry?.ladder.id).toBe("ladder-summit");
    }
    expect(
      ladderEntryAt({
        climbables: world.climbables,
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
        climbables: world.climbables,
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
        climbables: world.climbables,
        support: "terrain",
        supportId: null,
        x: up.centerX,
        footY: up.lowerSurfaceY,
        up: true,
        down: true,
      }),
    ).toBeNull();
  });

  test("captures an overlapping airborne player on Up and naturally permits jump-regrab", () => {
    expect(
      ladderEntryAt({
        climbables: world.climbables,
        support: "air",
        supportId: null,
        x: up.centerX + up.activationHalfWidth,
        footY: 500,
        up: true,
        down: false,
      })?.ladder.id,
    ).toBe("ladder-summit");
    expect(
      ladderEntryAt({
        climbables: world.climbables,
        support: "air",
        supportId: null,
        x: up.centerX,
        footY: up.upperDeckY - 1,
        up: true,
        down: false,
      }),
    ).toBeNull();
    expect(
      ladderEntryAt({
        climbables: world.climbables,
        support: "air",
        supportId: null,
        x: up.centerX,
        footY: 500,
        up: false,
        down: true,
      }),
    ).toBeNull();

    const jump = ladderJumpOffVelocity({
      left: false,
      right: false,
      facing: "right",
    });
    const deltaSeconds = 1 / 30;
    const regrab = ladderEntryAt({
      climbables: world.climbables,
      support: "air",
      supportId: null,
      x: up.centerX + jump.vx * deltaSeconds,
      footY: 500 + jump.vy * deltaSeconds,
      up: true,
      down: false,
    });
    expect(regrab?.ladder.id).toBe("ladder-summit");
    expect(regrab?.direction).toBe("up");
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

  test("scene culling keeps platform/climbables at real zoom boundaries across DPR", () => {
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
    // Overshoot is what this pins, so the vertical numbers stay literal. The horizontal ones
    // derive from the width constant: it sizes the trimmed rails and is a presentation choice,
    // and re-pinning it here would only mean editing two files to change one number.
    const halfWidth = CLIMBABLE_VISUAL_WIDTH / 2;
    expect(ladderVisualBounds(up)).toEqual({
      left: 2976 - halfWidth,
      right: 2976 + halfWidth,
      top: 304,
      bottom: 624,
      width: CLIMBABLE_VISUAL_WIDTH,
      height: 320,
    });
    const mutated = {
      ...up,
      visualTopOvershoot: 24,
    } as unknown as typeof up;
    expect(() => ladderVisualBounds(mutated)).toThrow("visual contract drifted");
  });
});

describe("the platformer's traversal is the family's, in pixels", () => {
  test("the climb profile is four of this genre's numbers over the family's rule", () => {
    expect(PLATFORMER_CLIMB_PROFILE).toEqual({
      speed: CLIMBABLE_SPEED,
      endpointTolerance: CLIMBABLE_ENDPOINT_TOLERANCE,
      jumpVelocity: CLIMBABLE_JUMP_VELOCITY,
      jumpHorizontalSpeed: CLIMBABLE_JUMP_HORIZONTAL_SPEED,
    });
    // The genre's function *is* the family's under that profile, not merely
    // equal to it: the same call, spelled twice, has to agree exactly.
    expect(
      advanceLadderMotion({ ladder: familyLadder, footY: 600, deltaSeconds: 1 / 30, up: true, down: false }),
    ).toEqual(
      advanceClimbMotion({
        geometry: {
          centerX: familyLadder.centerX,
          activationHalfWidth: familyLadder.activationHalfWidth,
          upperY: familyLadder.upperDeckY,
          lowerY: familyLadder.lowerSurfaceY,
          deckId: familyLadder.platformId,
        },
        profile: PLATFORMER_CLIMB_PROFILE,
        footY: 600,
        deltaSeconds: 1 / 30,
        up: true,
        down: false,
      }),
    );
  });

  test("this genre takes the clamping terrain entry, and says so", () => {
    // A descending foot already inside a raised column is pinned to it here.
    // The runner buries the same foot; the difference is a parameter, and this
    // is the platformer's half of it asserted rather than described.
    expect(
      resolveVerticalLanding({
        x: 100,
        previousFootY: 700,
        nextFootY: 710,
        vy: 300,
        terrainY: 688,
        platforms: [],
      }),
    ).toEqual({ footY: 688, vy: 0, support: "terrain", supportId: null });
    expect(
      resolveFamilyVerticalLanding({
        x: 100,
        previousFootY: 700,
        nextFootY: 710,
        vy: 300,
        terrainY: 688,
        terrainEntry: "crossing",
      }).support,
    ).toBe("buried");
  });

  test("the traversal blocks are gated by the family, by name, and there are two", () => {
    expect(parsePlatformerTraversalBlocks(PREPARED_RUNTIME_BLOCKS).map((view) => view.block)).toEqual([
      "gameplay",
      "maps",
    ]);
    expect(() =>
      parsePlatformerTraversalBlocks({
        ...PREPARED_RUNTIME_BLOCKS,
        maps: "platformer-maps-block-v2",
      }),
    ).toThrow('manifest block "maps" is published as platformer-maps-block-v2');
    expect(() =>
      parsePlatformerTraversalBlocks({
        ...PREPARED_RUNTIME_BLOCKS,
        gameplay: "platformer-gameplay-block-v2",
      }),
    ).toThrow('manifest block "gameplay" is published as platformer-gameplay-block-v2');
  });
});
