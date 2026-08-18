// Optional scrolling-preview adapter scene.
//
// Builds a browser demonstration from a complete `out/<tag>/` asset directory.
// Camera, terrain, movement, combat, and portal behavior here are consumer
// assumptions and must not become reusable component or CLI contracts:
//   - skybox (parallax 0, fixed to camera)             → TC-071
//   - parallax layers (TileSprite per layer)           → TC-072 / TC-073
//   - ground (heightmap-driven 12×4 tileset assembly)  → TC-074
//   - obstacles on flat columns                        → TC-075
//   - mobs with looping idle animation + wander        → TC-076 / TC-083
//   - player anchored bottom-center on ground band     → TC-077
//   - foreground band (high-parallax + blur)           → TC-078
//   - FPS probe                                        → TC-079
//   - Phase 7 player controller                        → TC-080..082
//   - Mob HP + hurt + drop                             → TC-084..086
//   - Item pickup → inventory HUD                      → TC-087/088
//   - Exit portal triggers stage-advance               → TC-089

import Phaser from "phaser";
import { alphaAt, type CellRect } from "./image-ops";
import {
  fetchJson,
  loadForegroundLayer,
  loadOpaqueSprite,
  loadParallaxLayer,
  loadTransparentSprite,
  loadFrameStrip,
  loadGridSheet,
  loadTileset,
  type LoadedForegroundLayer,
} from "./assets";
import type { PreviewTransparencyPolicy } from "@/lib/shell/transparency";
import {
  buildHeightmap,
  buildHeightmapFromSeed,
  flatRuns,
  type SlopeKind,
} from "./heightmap";
import { FpsProbe, type FpsSnapshot } from "./fps";
import { Player, type PlayerStateSnapshot } from "./player";
import { Mob } from "./mob";
import { ItemSystem } from "./items";
import { InventoryHud } from "./inventory";
import { PortalSystem } from "./portal";
import {
  SCENE_CONTENT_DEPTH,
  layoutSceneLayer,
  resolveSceneLayerStack,
  sceneLayerProbe,
  type SceneLayerBlend,
  type SceneLayerContract,
  type SceneLayerAssetMetadata,
  type SceneLayerProbe,
  type SceneLayerRenderState,
} from "./layers";
import {
  buildTerrainPlan,
  buildTerrainRenderPlan,
  createTerrainContract,
  terrainHeightAtColumn,
  terrainMaterialOrigin,
  terrainSurfaceY,
  terrainWorldWidth,
  visibleTerrainColumnRange,
  type TerrainColumnRange,
} from "./terrain";
import { TERRAIN_SURFACE_BAND_TEXTURE_HEIGHT } from "./tiles";
import {
  GAMEPLAY_AUTOMATION_ENCOUNTER,
  GAMEPLAY_AUTOMATION_MODE,
  GAMEPLAY_AUTOMATION_VIEWPORT,
  GameplayAutomationClock,
  gameplayAutomationPresentation,
  heightmapSha256,
  readonlyGameplaySnapshot,
  sleepGameplayAutomationLoopAfterBoot,
  type GameplayAutomationMode,
  type GameplayEncounterProbe,
  type GameplayAutomationSnapshot,
  type GameplayFrame,
  type GameplayLadderProbe,
  type GameplayPlatformProbe,
  type GameplayPlatformRouteProbe,
  type GameplayTranscriptEvent,
  type GameplayWorldBoundsProbe,
} from "./automation";
import {
  VERTICAL_CAMERA_MIN_SCROLL_Y,
  activateVerticalFeatureTransaction,
  buildPlatformRenderPlan,
  ladderVisualBounds,
  prepareVerticalTraversalAssets,
  selectDemoVerticalWorld,
  verticalCameraScrollY,
  verticalSceneObjectVisible,
  verticalFeatureAfterAssetLoad,
  verticalSpawnAllowed,
  type LadderZone,
  type PlatformRoute,
  type UpperPlatform,
  type VerticalWorld,
} from "./vertical";

type WorldLayer = {
  id: string;
  title: string;
  z_index: number;
  parallax: number;
  opaque: boolean;
  paint_region: string;
  description: string;
  scene_layer?: unknown;
};

type WorldSpec = {
  terrain_seed?: number;
  world: { name: string; one_liner: string; narrative: string };
  mobs: {
    tier_label: string;
    body_plan: string;
    name: string;
    brief: string;
  }[];
  obstacles: {
    sheet_theme: string;
    props: { name: string; brief: string }[];
  }[];
  items: { kind: string; name: string; brief: string }[];
  layers: WorldLayer[];
};

type TerrainRunSprite = Readonly<{
  startColumn: number;
  endColumn: number;
  sprite: Phaser.GameObjects.TileSprite;
}>;

type VerticalRenderSprite = Readonly<{
  id: string;
  bounds: Readonly<{ left: number; right: number; top: number; bottom: number }>;
  sprites: readonly (Phaser.GameObjects.TileSprite | Phaser.GameObjects.Image)[];
}>;

const VIEW_W = 1280;
const VIEW_H = 720;

// Ground band geometry. The tileset is 2400×800 (12 cols × 4 rows = 200×200
// per cell). At runtime we render tiles smaller for usable column density.
const TILE_PX = 64;
const COLS = 200; // total stage width in columns → 200 × 64 = 12800 px
const TERRAIN_CONTRACT = createTerrainContract({
  columns: COLS,
  tilePixels: TILE_PX,
  baselineY: VIEW_H,
  viewportWidth: VIEW_W,
  viewportHeight: VIEW_H,
});
const STAGE_W = terrainWorldWidth(TERRAIN_CONTRACT);
const GROUND_BASELINE_Y = TERRAIN_CONTRACT.baselineY;
const SCENE_LAYER_CONTEXT = Object.freeze({
  viewportWidth: VIEW_W,
  viewportHeight: VIEW_H,
  worldWidth: STAGE_W,
  groundBaselineY: GROUND_BASELINE_Y,
  foregroundContactScreenY: 704,
  foregroundSafeBandTopY: 540,
  foregroundMaxScale: 0.75,
});
const MIN_H = 1; // tiles
const MAX_H = 4;

function gameplayWorldBounds(
  bounds: Phaser.Geom.Rectangle,
): GameplayWorldBoundsProbe {
  return Object.freeze({
    left: bounds.left,
    right: bounds.right,
    top: bounds.top,
    bottom: bounds.bottom,
  });
}

function sceneLayerBlendMode(blend: SceneLayerBlend): number {
  switch (blend) {
    case "normal":
      return Phaser.BlendModes.NORMAL;
    case "multiply":
      return Phaser.BlendModes.MULTIPLY;
    case "screen":
      return Phaser.BlendModes.SCREEN;
    case "add":
      return Phaser.BlendModes.ADD;
  }
}

function sceneDevicePixelRatio(): number {
  if (typeof window === "undefined") return 1;
  const ratio = window.devicePixelRatio;
  return Number.isFinite(ratio) && ratio >= 1 && ratio <= 8 ? ratio : 1;
}

function applyForegroundBlur(
  sprite: Phaser.GameObjects.TileSprite,
  depthCoefficient: number,
): void {
  try {
    const fx = (
      sprite as unknown as {
        postFX?: {
          addBlur?: (
            quality?: number,
            x?: number,
            y?: number,
            strength?: number,
            color?: number,
            steps?: number,
          ) => unknown;
        };
      }
    ).postFX;
    const strength = Math.min(4, (depthCoefficient - 1) * 6);
    fx?.addBlur?.(0, 2, 2, strength, 0xffffff, 4);
  } catch {
    // Optional post-processing support differs between Phaser renderers.
  }
}

// Asset URL helper.
function assetUrl(tag: string, file: string): string {
  return `/api/assets/${encodeURIComponent(tag)}/${file
    .split("/")
    .map(encodeURIComponent)
    .join("/")}`;
}

// Spot-check probes — written into window.__sceneProbes for E2E verification.
export type SceneProbes = {
  tag: string;
  loadedAssetKeys: string[];
  parallaxAlphaProbe: Record<
    string,
    {
      layerId: string;
      leftEdgeAlpha: number;
      inwardAlpha: number;
      width: number;
      height: number;
      parallax: number;
      opaque: boolean;
    }
  >;
  spriteAlphaProbe: Record<
    string,
    {
      spriteKey: string;
      sampledAlpha: number;
      sampledAt: { x: number; y: number };
    }
  >;
  cellExtractProbe: Record<string, CellRect[]>;
  consoleErrors: string[];
  // Phase 6 additions:
  heightmap: number[];
  flatRunCount: number;
  obstacleCount: number;
  mobCount: number;
  playerColumn: number;
  foregroundLayers: string[];
  sceneLayers: SceneLayerProbe[];
  platforms: GameplayPlatformProbe[];
  platformRoutes: GameplayPlatformRouteProbe[];
  ladders: GameplayLadderProbe[];
  fps?: FpsSnapshot;
  // Phase 7 additions — side-channel for verifiers.
  player?: PlayerStateSnapshot;
  mobs?: ReturnType<Mob["snapshot"]>[];
  inventory?: ReturnType<InventoryHud["snapshot"]>;
  worldItems?: ReturnType<ItemSystem["snapshot"]>;
  portals?: ReturnType<PortalSystem["snapshot"]>;
  events?: { kind: string; t: number; data?: unknown }[];
  itemPalette?: { kind: string; name: string }[];
};

declare global {
  interface Window {
    __sceneProbes?: SceneProbes;
    __sceneReady?: boolean;
    __sceneFps?: FpsSnapshot;
    __sceneCamera?: { scrollX: number };
    __scenePlayerState?: PlayerStateSnapshot;
    __sceneMobsState?: ReturnType<Mob["snapshot"]>[];
    __sceneInventory?: ReturnType<InventoryHud["snapshot"]>;
    __sceneScene?: StageScene;
    readonly __stageGenGameplayProbe?: GameplayAutomationSnapshot;
    readonly __stageGenAdvanceGameplayFrame?: () => Promise<GameplayAutomationSnapshot>;
  }
}

export type SceneInit = {
  tag: string;
  transparencyPolicy: PreviewTransparencyPolicy;
  automationMode: GameplayAutomationMode | null;
};

export class StageScene extends Phaser.Scene {
  private tag: string;
  private transparencyPolicy: PreviewTransparencyPolicy;
  private automationMode: GameplayAutomationMode | null;
  private automationClock?: GameplayAutomationClock;
  private pendingAutomationFrame?: GameplayFrame;
  private automationAdvancePending = false;
  private automationEvents: GameplayTranscriptEvent[] = [];
  private automationEncounterHudSuppressed = false;
  private automationEncounterTargetMob?: Mob;
  private automationLastDropBounds?: GameplayWorldBoundsProbe;
  private automationPickupBounds?: GameplayWorldBoundsProbe;
  private pendingAutomationEncounter?: {
    mob: Mob;
    ladderIndex: number;
    deathFrame: number;
    dropFrame: number;
    pickupFrame: number;
    deathLogged: boolean;
    dropCreated: boolean;
  };
  private heightmapDigest: string | null = null;
  private originalConsoleError?: typeof console.error;
  private probes!: SceneProbes;
  private fpsProbe = new FpsProbe(30);

  // Semantic screen/parallax layers, ordered by canonical depth. Legacy
  // distant/midground layers may retain a fallback partner; the foreground
  // is always one prepared periodic texture and exactly one TileSprite.
  private sceneLayerSprites: {
    contract: SceneLayerContract;
    asset: SceneLayerAssetMetadata;
    sprite: Phaser.GameObjects.TileSprite;
    partner?: Phaser.GameObjects.TileSprite;
    seamOffset: number;
  }[] = [];

  // Phase 7 systems.
  private player?: Player;
  private mobs: Mob[] = [];
  private items?: ItemSystem;
  private inventory?: InventoryHud;
  private portal?: PortalSystem;
  private heights: number[] = [];
  private terrainFillSprites: TerrainRunSprite[] = [];
  private terrainIntegrationSprites: TerrainRunSprite[] = [];
  private terrainBoundarySprites: TerrainRunSprite[] = [];
  private terrainCullRange: TerrainColumnRange | null | undefined;
  private verticalWorld: VerticalWorld = Object.freeze({
    platforms: Object.freeze([]),
    ladders: Object.freeze([]),
  });
  private verticalReservedColumns = new Set<number>();
  private verticalRoutes: readonly PlatformRoute[] = Object.freeze([]);
  private platformRenderSprites: VerticalRenderSprite[] = [];
  private ladderRenderSprites: VerticalRenderSprite[] = [];
  private eventLog: { kind: string; t: number; data?: unknown }[] = [];

  constructor(init: SceneInit) {
    super({ key: "StageScene" });
    this.tag = init.tag;
    this.transparencyPolicy = init.transparencyPolicy;
    this.automationMode = init.automationMode;
    if (this.automationMode)
      this.automationClock = new GameplayAutomationClock();
  }

  create() {
    this.probes = {
      tag: this.tag,
      loadedAssetKeys: [],
      parallaxAlphaProbe: {},
      spriteAlphaProbe: {},
      cellExtractProbe: {},
      consoleErrors: [],
      heightmap: [],
      flatRunCount: 0,
      obstacleCount: 0,
      mobCount: 0,
      playerColumn: 0,
      foregroundLayers: [],
      sceneLayers: [],
      platforms: [],
      platformRoutes: [],
      ladders: [],
      events: this.eventLog,
    };
    if (typeof window !== "undefined" && !this.automationMode) {
      window.__sceneProbes = this.probes;
      window.__sceneScene = this;
    }
    if (this.automationMode) this.installAutomationApi();

    // Patch console.error to track errors during the first few seconds.
    const origErr = console.error.bind(console);
    this.originalConsoleError = console.error;
    console.error = ((...args: unknown[]) => {
      try {
        this.probes.consoleErrors.push(args.map((a) => String(a)).join(" "));
      } catch {}
      origErr(...args);
    }) as typeof console.error;

    // Camera bounds — generous; loadAll() will narrow to STAGE_W after ground.
    this.cameras.main.setBounds(
      0,
      VERTICAL_CAMERA_MIN_SCROLL_Y,
      STAGE_W,
      VIEW_H - VERTICAL_CAMERA_MIN_SCROLL_Y,
    );
    this.cameras.main.setRoundPixels(true);

    if (!this.automationMode) {
      this.fpsProbe.start();
    }

    void this.loadAll()
      .then(() => this.finishLoading())
      .catch((err) => this.failLoading(err));

    this.logEvent("scene-created");

    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
      this.fpsProbe.stop();
      if (this.originalConsoleError) console.error = this.originalConsoleError;
      if (typeof window !== "undefined" && this.automationMode) {
        Reflect.deleteProperty(window, "__stageGenGameplayProbe");
        Reflect.deleteProperty(window, "__stageGenAdvanceGameplayFrame");
      }
    });
  }

  private logEvent(
    kind: string,
    data?: Record<string, string | number | boolean>,
  ) {
    const t = this.automationClock?.simulationMs ?? performance.now();
    this.eventLog.push({ kind, t, data });
    if (this.automationClock) {
      this.automationEvents.push({
        kind,
        frame: this.automationClock.frame,
        simulationMs: this.automationClock.simulationMs,
        data: data ?? null,
      });
    }
  }

  update(_time: number, deltaMs: number) {
    let now: number;
    if (this.automationClock) {
      const fixedFrame = this.pendingAutomationFrame;
      if (!fixedFrame) return;
      deltaMs = fixedFrame.deltaMs;
      now = fixedFrame.simulationMs;
    } else {
      now = performance.now();
    }
    const cam = this.cameras.main;
    const presentation = gameplayAutomationPresentation(
      this.automationClock?.frame ?? 0,
    );
    if (this.automationMode) {
      cam.setZoom(presentation.cameraZoom);
      if (this.inventory) {
        if (
          presentation.inventorySuppressed &&
          !this.automationEncounterHudSuppressed
        ) {
          this.inventory.setVisible(false);
          this.automationEncounterHudSuppressed = true;
        } else if (
          !presentation.inventorySuppressed &&
          this.automationEncounterHudSuppressed
        ) {
          this.inventory.setVisible(true);
          this.automationEncounterHudSuppressed = false;
        }
      }
      this.portal?.applyAutomationPresentation(
        presentation.portalScale,
        presentation.portalAlpha,
      );
    }

    // Player drives the camera (TC-080).
    if (this.player) {
      this.player.update(deltaMs, now);
      // Camera follow uses Phaser's zoom-independent scroll coordinates.
      // During the encounter, center the complete player/action/target/drop
      // union instead of one actor so every required event remains visible.
      const px = this.player.sprite.x;
      const encounter = this.automationEncounterProbe();
      if (
        presentation.encounterFocus &&
        encounter.focusX !== null &&
        encounter.focusY !== null
      ) {
        cam.centerOn(encounter.focusX, encounter.focusY);
      } else {
        cam.centerOnX(px);
        cam.scrollY = verticalCameraScrollY({
          currentScrollY: cam.scrollY,
          footY: this.player.sprite.y,
          zoom: cam.zoom,
          viewportHeight: cam.height,
        });
      }

      // Inventory toggle.
      if (this.player.inventoryToggleRequested && this.inventory) {
        this.inventory.toggle();
        this.player.inventoryToggleRequested = false;
        this.logEvent("inventory-toggle", { visible: this.inventory.visible });
      }

      // Attack collisions vs mobs.
      if (this.player.consumeAttackHit()) {
        const px2 = this.player.sprite.x;
        const py2 = this.player.sprite.y;
        const facing = this.player.facing === "left" ? -1 : 1;
        // Hit reaches ~1 tile in front + 1 tile width.
        const reach = TILE_PX * 1.4;
        const hitX = px2 + facing * reach * 0.5;
        for (const m of this.mobs) {
          if (!m.isAlive()) continue;
          const dx = m.sprite.x - hitX;
          const dy = m.sprite.y - py2;
          if (Math.abs(dx) < reach && Math.abs(dy) < TILE_PX * 2.5) {
            const r = m.takeHit(now, facing as 1 | -1);
            this.logEvent("mob-hit", {
              ladderIndex: m.ladderIndex,
              hpLeft: r.hpLeft,
              died: r.died,
            });
            if (r.died && this.items) {
              if (this.automationClock) {
                const hitFrame = this.automationClock.frame;
                this.automationEncounterTargetMob = m;
                this.pendingAutomationEncounter = {
                  mob: m,
                  ladderIndex: m.ladderIndex,
                  deathFrame:
                    hitFrame + GAMEPLAY_AUTOMATION_ENCOUNTER.deathDelayFrames,
                  dropFrame:
                    hitFrame + GAMEPLAY_AUTOMATION_ENCOUNTER.dropDelayFrames,
                  pickupFrame:
                    hitFrame + GAMEPLAY_AUTOMATION_ENCOUNTER.pickupDelayFrames,
                  deathLogged: false,
                  dropCreated: false,
                };
              } else {
                const drop = this.items.drop(
                  m.sprite.x,
                  m.sprite.y - TILE_PX,
                  m.ladderIndex,
                );
                if (drop) {
                  this.logEvent("mob-drop", {
                    ladderIndex: m.ladderIndex,
                    kindIndex: m.ladderIndex,
                  });
                }
              }
            }
            break; // one hit per swing
          }
        }
      }
    }

    this.updateTerrainCulling(cam);
    this.updateVerticalCulling(cam);

    // Mobs.
    for (const m of this.mobs) {
      if (m.isAlive() || this.automationMode) m.update(deltaMs, now);
    }

    if (this.automationClock && this.pendingAutomationEncounter) {
      const encounter = this.pendingAutomationEncounter;
      const frame = this.automationClock.frame;
      if (!encounter.deathLogged && frame >= encounter.deathFrame) {
        this.logEvent("mob-death", { ladderIndex: encounter.ladderIndex });
        encounter.deathLogged = true;
      }
      if (
        !encounter.dropCreated &&
        frame >= encounter.dropFrame &&
        this.items
      ) {
        const drop = this.items.drop(
          encounter.mob.sprite.x,
          encounter.mob.sprite.y - TILE_PX,
          encounter.ladderIndex,
        );
        if (drop) {
          this.logEvent("mob-drop", {
            ladderIndex: encounter.ladderIndex,
            kindIndex: encounter.ladderIndex,
          });
          encounter.dropCreated = true;
        }
      }
    }

    // Items (gravity + bob).
    if (this.items) this.items.update(deltaMs, now);
    if (this.automationClock) {
      const liveDrop = this.automationLiveDropBounds();
      if (liveDrop) this.automationLastDropBounds = liveDrop;
    }

    // Item pickups.
    const automationPickupAllowed =
      !this.automationClock ||
      !this.pendingAutomationEncounter ||
      this.automationClock.frame >= this.pendingAutomationEncounter.pickupFrame;
    if (this.player && this.items && automationPickupAllowed) {
      const picked = this.items.tryPickup(
        this.player.sprite.x,
        this.player.sprite.y,
        TILE_PX * 0.9,
      );
      for (const p of picked) {
        if (this.inventory) this.inventory.addItem(p.kindIndex);
        this.logEvent("item-pickup", { kindIndex: p.kindIndex });
      }
      if (picked.length > 0) {
        this.automationPickupBounds = this.automationLastDropBounds;
        this.pendingAutomationEncounter = undefined;
      }
    }

    // Portal exit check.
    if (this.player && this.portal) {
      if (this.portal.checkExit(this.player.sprite.x, this.player.sprite.y)) {
        this.logEvent("stage-advance", { portal: "exit" });
        // eslint-disable-next-line no-console
        console.log("[stage-advance] portal entered: exit");
        if (typeof window !== "undefined") {
          try {
            window.dispatchEvent(
              new CustomEvent("stage-advance", {
                detail: { portal: "exit", tag: this.tag },
              }),
            );
          } catch {}
        }
      }
    }

    this.updateSceneLayerTransforms(cam, presentation.foregroundVisible);

    if (typeof window !== "undefined") {
      if (!this.automationMode) {
        window.__sceneCamera = { scrollX: cam.scrollX };
        if (window.__sceneFps) this.probes.fps = window.__sceneFps;
      }
      // Phase 7 side-channel for verifiers.
      if (this.player) {
        const ps = this.player.snapshot();
        if (!this.automationMode) window.__scenePlayerState = ps;
        this.probes.player = ps;
      }
      const ms = this.mobs.map((m) => m.snapshot());
      if (!this.automationMode) window.__sceneMobsState = ms;
      this.probes.mobs = ms;
      if (this.inventory) {
        const inv = this.inventory.snapshot();
        if (!this.automationMode) window.__sceneInventory = inv;
        this.probes.inventory = inv;
      }
      if (this.items) this.probes.worldItems = this.items.snapshot();
      if (this.portal) this.probes.portals = this.portal.snapshot();
      this.probes.platforms = [...this.platformProbes(cam)];
      this.probes.platformRoutes = [...this.platformRouteProbes()];
      this.probes.ladders = [...this.ladderProbes(cam)];
      // Surface live tilePositionX per layer for headless parallax verification.
      const tiles: Record<
        string,
        {
          depthCoefficient: number;
          tilePositionX: number;
          renderDepth: number;
        }
      > = {};
      for (const entry of this.sceneLayerSprites) {
        tiles[entry.contract.id] = {
          depthCoefficient: entry.contract.depthCoefficient,
          tilePositionX: entry.sprite.tilePositionX,
          renderDepth: entry.sprite.depth,
        };
      }
      if (!this.automationMode) {
        (window as unknown as { __sceneTiles?: typeof tiles }).__sceneTiles =
          tiles;
      }
    }
  }

  private updateSceneLayerTransforms(
    camera: Phaser.Cameras.Scene2D.Camera,
    foregroundVisible: boolean,
  ): void {
    const probes: SceneLayerProbe[] = [];
    for (const entry of this.sceneLayerSprites) {
      const layout = layoutSceneLayer(
        entry.contract,
        {
          scrollX: camera.scrollX,
          scrollY: camera.scrollY,
          zoom: camera.zoom,
        },
        SCENE_LAYER_CONTEXT,
        entry.asset,
        sceneDevicePixelRatio(),
      );
      const bounds = layout.screenBounds;
      const intersectsViewport =
        bounds.right > 0 &&
        bounds.bottom > 0 &&
        bounds.left < VIEW_W &&
        bounds.top < VIEW_H;
      const visible =
        (entry.contract.cull === "never" || intersectsViewport) &&
        (entry.contract.kind !== "near-foreground" || foregroundVisible);
      entry.sprite
        .setPosition(layout.x, layout.y)
        .setScale(layout.scale)
        .setTileScale(layout.textureScale, layout.textureScale)
        .setVisible(visible);
      entry.sprite.tilePositionX = layout.tilePositionX;
      if (entry.partner) {
        entry.partner
          .setPosition(layout.x, layout.y)
          .setScale(layout.scale)
          .setTileScale(layout.textureScale, layout.textureScale)
          .setVisible(visible);
        entry.partner.tilePositionX = layout.tilePositionX + entry.seamOffset;
      }
      probes.push(
        sceneLayerProbe(
          entry.contract,
          layout,
          {
            scrollX: camera.scrollX,
            scrollY: camera.scrollY,
            zoom: camera.zoom,
          },
          this.readSceneLayerRenderState(entry, camera),
        ),
      );
    }
    this.probes.sceneLayers = probes;
  }

  private readSceneLayerRenderState(
    entry: (typeof this.sceneLayerSprites)[number],
    camera: Phaser.Cameras.Scene2D.Camera,
  ): SceneLayerRenderState {
    const sprite = entry.sprite;
    const spriteCount = this.children.list.filter(
      (candidate) =>
        candidate instanceof Phaser.GameObjects.TileSprite &&
        candidate.texture.key === sprite.texture.key,
    ).length;
    return Object.freeze({
      x: sprite.x,
      y: sprite.y,
      scaleX: sprite.scaleX,
      scaleY: sprite.scaleY,
      displayWidth: sprite.displayWidth,
      displayHeight: sprite.displayHeight,
      originX: sprite.originX,
      originY: sprite.originY,
      scrollFactorX: sprite.scrollFactorX,
      scrollFactorY: sprite.scrollFactorY,
      tilePositionX: sprite.tilePositionX,
      tilePositionY: sprite.tilePositionY,
      tileScaleX: sprite.tileScaleX,
      tileScaleY: sprite.tileScaleY,
      visible: sprite.visible,
      depth: sprite.depth,
      spriteCount,
      textureWidth: sprite.frame.realWidth,
      textureHeight: sprite.frame.realHeight,
      clipBounds: Object.freeze({
        left: camera.x,
        top: camera.y,
        right: camera.x + camera.width,
        bottom: camera.y + camera.height,
      }),
    });
  }

  private installAutomationApi(): void {
    if (typeof window === "undefined") return;
    Object.defineProperty(window, "__stageGenGameplayProbe", {
      configurable: true,
      enumerable: false,
      get: () => this.automationSnapshot(),
    });
    Object.defineProperty(window, "__stageGenAdvanceGameplayFrame", {
      configurable: true,
      enumerable: false,
      writable: false,
      value: () => this.advanceAutomationFrame(),
    });
  }

  private automationSnapshot(): GameplayAutomationSnapshot {
    const clock = this.automationClock;
    if (!clock) throw new Error("gameplay automation is not enabled");
    const cam = this.cameras.main;
    return readonlyGameplaySnapshot({
      version: GAMEPLAY_AUTOMATION_MODE,
      state: clock.state,
      ready: clock.state === "ready",
      errors: [...new Set(this.probes.consoleErrors)],
      assetKeys: this.probes.loadedAssetKeys,
      frame: clock.frame,
      simulationMs: clock.simulationMs,
      player: this.player?.snapshot() ?? null,
      camera: { scrollX: cam.scrollX, scrollY: cam.scrollY, zoom: cam.zoom },
      layers: this.probes.sceneLayers,
      platforms: this.platformProbes(cam),
      platformRoutes: this.platformRouteProbes(),
      ladders: this.ladderProbes(cam),
      mobs: this.mobs.map((mob) => mob.snapshot()),
      inventory: {
        visible: this.inventory?.visible ?? false,
        slots: this.inventory?.snapshot() ?? [],
      },
      worldItems: this.items?.snapshot() ?? [],
      encounter: this.automationEncounterProbe(),
      portals: this.portal?.snapshot() ?? [],
      presentation: gameplayAutomationPresentation(clock.frame),
      events: this.automationEvents,
      heightmapDigest: this.heightmapDigest,
    });
  }

  private automationFocusMob(): Mob | undefined {
    if (this.automationEncounterTargetMob)
      return this.automationEncounterTargetMob;
    if (!this.player) return undefined;
    const playerX = this.player.sprite.x;
    return this.mobs
      .filter((mob) => mob.isAlive())
      .reduce<Mob | undefined>((nearest, mob) => {
        if (!nearest) return mob;
        return Math.abs(mob.sprite.x - playerX) <
          Math.abs(nearest.sprite.x - playerX)
          ? mob
          : nearest;
      }, undefined);
  }

  private verticalVisible(
    camera: Phaser.Cameras.Scene2D.Camera,
    bounds: Readonly<{ left: number; right: number; top: number; bottom: number }>,
  ): boolean {
    return verticalSceneObjectVisible({
      bounds,
      camera: {
        scrollX: camera.scrollX,
        scrollY: camera.scrollY,
        zoom: camera.zoom,
        viewportWidth: camera.width,
        viewportHeight: camera.height,
      },
      overscan: TILE_PX,
      devicePixelRatio: sceneDevicePixelRatio(),
    });
  }

  private platformProbes(
    camera: Phaser.Cameras.Scene2D.Camera,
  ): readonly GameplayPlatformProbe[] {
    return this.verticalWorld.platforms.map((platform) =>
      Object.freeze({
        id: platform.id,
        left: platform.left,
        right: platform.right,
        deckY: platform.deckY,
        tier: platform.tier,
        thickness: platform.thickness,
        visible: this.verticalVisible(camera, {
          left: platform.left,
          right: platform.right,
          top: platform.deckY,
          bottom: platform.deckY + platform.thickness,
        }),
      }),
    );
  }

  private platformRouteProbes(): readonly GameplayPlatformRouteProbe[] {
    return this.verticalRoutes.map((route) =>
      Object.freeze({
        id: route.id,
        from: route.from,
        to: route.to,
        mode: route.mode,
        rise: route.rise,
        gap: route.gap,
        landingStep: route.landingStep,
        horizontalRange: route.horizontalRange,
        ladderId: route.ladderId,
      }),
    );
  }

  private ladderProbes(
    camera: Phaser.Cameras.Scene2D.Camera,
  ): readonly GameplayLadderProbe[] {
    return this.verticalWorld.ladders.map((ladder) => {
      const visual = ladderVisualBounds(ladder);
      return Object.freeze({
        id: ladder.id,
        platformId: ladder.platformId,
        centerX: ladder.centerX,
        top: visual.top,
        bottom: visual.bottom,
        activationHalfWidth: ladder.activationHalfWidth,
        visualTopOvershoot: ladder.visualTopOvershoot,
        visualBottomOvershoot: ladder.visualBottomOvershoot,
        visible: this.verticalVisible(camera, visual),
      });
    });
  }

  private automationLiveDropBounds(): GameplayWorldBoundsProbe | undefined {
    const item = this.items?.items[0];
    return item ? gameplayWorldBounds(item.sprite.getBounds()) : undefined;
  }

  private automationEncounterProbe(): GameplayEncounterProbe {
    const playerSprite = this.player?.sprite;
    const mobSprite = this.automationFocusMob()?.sprite;
    const player = playerSprite
      ? gameplayWorldBounds(playerSprite.getBounds())
      : null;
    const mob = mobSprite ? gameplayWorldBounds(mobSprite.getBounds()) : null;
    let attack: GameplayWorldBoundsProbe | null = null;
    if (playerSprite && player) {
      const direction = this.player?.facing === "left" ? -1 : 1;
      const attackTip = playerSprite.x + direction * TILE_PX * 1.4;
      attack = Object.freeze({
        left: Math.min(playerSprite.x, attackTip) - TILE_PX * 0.25,
        right: Math.max(playerSprite.x, attackTip) + TILE_PX * 0.25,
        top: player.top,
        bottom: player.bottom,
      });
    }
    const drop = this.automationLiveDropBounds() ?? null;
    const pickup = this.automationPickupBounds ?? null;
    const subjects = [player, mob, attack, drop, pickup].filter(
      (bounds): bounds is GameplayWorldBoundsProbe => bounds !== null,
    );
    return Object.freeze({
      safeMarginPixels: GAMEPLAY_AUTOMATION_ENCOUNTER.safeMarginPixels,
      focusX:
        subjects.length === 0
          ? null
          : (Math.min(...subjects.map((bounds) => bounds.left)) +
              Math.max(...subjects.map((bounds) => bounds.right))) /
            2,
      focusY:
        subjects.length === 0
          ? null
          : (Math.min(...subjects.map((bounds) => bounds.top)) +
              Math.max(...subjects.map((bounds) => bounds.bottom))) /
            2,
      player,
      mob,
      attack,
      drop,
      pickup,
    });
  }

  private async advanceAutomationFrame(): Promise<GameplayAutomationSnapshot> {
    const clock = this.automationClock;
    if (!clock) throw new Error("gameplay automation is not enabled");
    if (this.automationAdvancePending) {
      throw new Error(
        "gameplay automation frame advance is already in progress",
      );
    }
    if (this.game.loop.running) {
      throw new Error("gameplay automation rAF loop must remain asleep");
    }
    this.automationAdvancePending = true;
    const frame = clock.advance();
    this.pendingAutomationFrame = frame;
    try {
      // The normal TimeStep is sleeping. This public Game step advances input,
      // scene systems, tweens, animations, gameplay, and rendering exactly once.
      this.game.step(frame.simulationMs, frame.deltaMs);
      return this.automationSnapshot();
    } finally {
      this.pendingAutomationFrame = undefined;
      this.automationAdvancePending = false;
    }
  }

  private finishLoading(): void {
    if (!this.automationClock) {
      if (typeof window !== "undefined") window.__sceneReady = true;
      return;
    }
    if (this.probes.consoleErrors.length > 0) {
      this.automationClock.markFailed();
      this.logEvent("assets-error", {
        count: this.probes.consoleErrors.length,
      });
      this.game.loop.sleep();
      return;
    }
    // Re-establish frame zero after asynchronous loading and before exposing
    // readiness. Even if a browser schedules unusual boot work, no animation,
    // actor, event, or simulation-clock phase can leak into the transcript.
    this.game.loop.sleep();
    this.automationClock = new GameplayAutomationClock();
    this.eventLog.length = 0;
    this.automationEvents.length = 0;
    this.pendingAutomationFrame = undefined;
    this.automationAdvancePending = false;
    this.automationEncounterHudSuppressed = false;
    this.automationEncounterTargetMob = undefined;
    this.automationLastDropBounds = undefined;
    this.automationPickupBounds = undefined;
    this.pendingAutomationEncounter = undefined;
    this.player?.resetAutomationState();
    for (const mob of this.mobs) mob.resetAutomationState();
    const playerX = this.player?.sprite.x ?? 0;
    this.cameras.main.setZoom(1);
    this.cameras.main.centerOnX(playerX);
    this.cameras.main.scrollY = 0;
    this.updateTerrainCulling(this.cameras.main);
    this.updateVerticalCulling(this.cameras.main);
    this.updateSceneLayerTransforms(this.cameras.main, true);
    this.automationClock.markReady();
    this.logEvent("assets-ready", {
      count: this.probes.loadedAssetKeys.length,
    });
    // Asset requests are complete before frame 0. Stop rAF before publishing
    // readiness; all subsequent full-game updates come through the hook.
    this.game.loop.sleep();
    const renderer = this.game.renderer;
    renderer.preRender();
    this.game.scene.render(renderer);
    renderer.postRender();
  }

  private failLoading(error: unknown): void {
    const message = error instanceof Error ? error.message : String(error);
    console.error("[scene] loadAll failed:", message);
    if (!this.automationClock) return;
    this.automationClock.markFailed();
    this.logEvent("assets-error", { count: this.probes.consoleErrors.length });
    this.game.loop.sleep();
  }

  // ---------- Loading ----------

  private async loadAll() {
    const tag = this.tag;
    const u = (f: string) => assetUrl(tag, f);

    // World spec.
    const spec = await fetchJson<WorldSpec>(u(`world_spec_${tag}.json`));
    this.probes.loadedAssetKeys.push(`spec:${spec.world.name}`);
    this.probes.itemPalette = spec.items.map((i) => ({
      kind: i.kind,
      name: i.name,
    }));

    // ---------- Heightmap (deterministic from tag or explicit run seed) ----------
    if (
      spec.terrain_seed !== undefined &&
      !Number.isSafeInteger(spec.terrain_seed)
    ) {
      throw new Error("world spec terrain_seed must be a safe integer");
    }
    const heightmapOpts = {
      cols: COLS,
      minH: MIN_H,
      maxH: MAX_H,
    };
    const heights =
      spec.terrain_seed === undefined
        ? buildHeightmap(tag, heightmapOpts)
        : buildHeightmapFromSeed(spec.terrain_seed, heightmapOpts);
    this.heights = heights;
    this.probes.heightmap = heights;
    if (this.automationMode)
      this.heightmapDigest = await heightmapSha256(heights);
    // The opening encounter owns columns 0..13. Vertical geometry is selected
    // before prop/mob placement. Selection rejects caller occupancy across
    // the complete raster/collision footprint (start-1 through end), then
    // reserves that same interval from both spawners.
    const openingEncounterColumns = new Set(
      Array.from({ length: 14 }, (_, column) => column),
    );
    const verticalCandidate = selectDemoVerticalWorld({
      heights,
      tilePixels: TILE_PX,
      baselineY: GROUND_BASELINE_Y,
      worldWidth: STAGE_W,
      reservedColumns: openingEncounterColumns,
    });
    const inactiveVertical = verticalFeatureAfterAssetLoad(
      verticalCandidate,
      false,
    );
    this.verticalWorld = inactiveVertical.world;
    this.verticalRoutes = inactiveVertical.routes;
    this.verticalReservedColumns = new Set(inactiveVertical.reservedColumns);
    const { ladderAssetLoaded, climbAssetLoaded } =
      await prepareVerticalTraversalAssets({
        selected: verticalCandidate,
        loadLadder: async () => {
          await loadTransparentSprite(
            u(`ladder_${tag}.png`),
            "ladder",
            this.textures,
            this.transparencyPolicy,
          );
        },
        loadClimb: async () => {
          await loadFrameStrip(
            u(`character_${tag}-fromcombined_climb.png`),
            "character_climb",
            4,
            this.textures,
            this.transparencyPolicy,
          );
        },
        removeAsset: (key) => {
          if (this.textures.exists(key)) this.textures.remove(key);
        },
        recordError: (message) => this.recordErr(message),
      });

    // ---------- Semantic screen/parallax layers ----------
    const layersById = new Map(spec.layers.map((layer) => [layer.id, layer]));
    const resolvedLayers = resolveSceneLayerStack(
      spec.layers,
      SCENE_LAYER_CONTEXT,
    );
    // Runtime-only overlap width. Foreground consumes it into one
    // premultiplied periodic canvas; legacy non-foreground layers keep their
    // existing fade-partner fallback.
    const FADE_PX = 256;
    for (const contract of resolvedLayers) {
      const layer = layersById.get(contract.id);
      if (!layer) throw new Error(`${contract.id} has no world-layer source`);
      const file = `layer_${tag}_${layer.id}.png`;
      const key = `layer_${layer.id}`;
      try {
        const loaded =
          contract.kind === "near-foreground"
            ? await loadForegroundLayer(
                u(file),
                key,
                FADE_PX,
                this.textures,
                this.transparencyPolicy,
              )
            : await loadParallaxLayer(
                u(file),
                key,
                layer.opaque,
                FADE_PX,
                this.textures,
                this.transparencyPolicy,
              );
        this.probes.loadedAssetKeys.push(key);

        // Probe alpha at left edge + 64 px inward (for non-opaque).
        const yMid = Math.floor(loaded.height / 2);
        const leftEdgeAlpha = layer.opaque
          ? 255
          : alphaAt(loaded.canvas, 0, yMid);
        const inwardAlpha = layer.opaque
          ? 255
          : alphaAt(loaded.canvas, Math.min(64, loaded.width - 1), yMid);
        this.probes.parallaxAlphaProbe[key] = {
          layerId: layer.id,
          leftEdgeAlpha,
          inwardAlpha,
          width: loaded.width,
          height: loaded.height,
          parallax: layer.parallax,
          opaque: layer.opaque,
        };

        const asset: SceneLayerAssetMetadata = {
          width: loaded.width,
          height: loaded.height,
          foreground:
            contract.kind === "near-foreground"
              ? (loaded as LoadedForegroundLayer).foreground
              : undefined,
        };
        const initialLayout = layoutSceneLayer(
          contract,
          { scrollX: 0, scrollY: 0, zoom: 1 },
          SCENE_LAYER_CONTEXT,
          asset,
          sceneDevicePixelRatio(),
        );
        const sprite = this.add.tileSprite(
          0,
          0,
          initialLayout.renderWidth,
          initialLayout.renderHeight,
          key,
        );
        sprite.setOrigin(0, 0);
        sprite.setScrollFactor(0);
        sprite.setDepth(contract.renderDepth);
        sprite.setAlpha(contract.opacity.alpha);
        sprite.setBlendMode(sceneLayerBlendMode(contract.blend));
        const ts = initialLayout.textureScale;
        sprite.setTileScale(ts, ts);

        // Helper: build the optional partner TileSprite at the same screen
        // position. The caller offsets it by (naturalWidth - fadePx), making
        // its right linear edge band complement the primary's left edge band.
        // Opaque and non-overlap layers never create this partner.
        const makePartner = () => {
          const partner = this.add.tileSprite(
            0,
            0,
            initialLayout.renderWidth,
            initialLayout.renderHeight,
            key,
          );
          partner.setOrigin(0, 0);
          partner.setScrollFactor(0);
          partner.setTileScale(ts, ts);
          partner.setDepth(contract.renderDepth);
          partner.setAlpha(contract.opacity.alpha);
          partner.setBlendMode(sceneLayerBlendMode(contract.blend));
          return partner;
        };

        const seamOffset = loaded.width - FADE_PX;

        const partner =
          contract.repeat === "repeat-x-seam-overlap"
            ? makePartner()
            : undefined;
        if (contract.kind === "near-foreground") {
          applyForegroundBlur(sprite, contract.depthCoefficient);
          this.probes.foregroundLayers.push(contract.id);
        }
        this.sceneLayerSprites.push({
          contract,
          asset,
          sprite,
          partner,
          seamOffset: partner ? seamOffset : 0,
        });
      } catch (e) {
        this.recordErr(e);
      }
    }

    // ---------- Tileset + ground assembly ----------
    try {
      const tileset = await loadTileset(
        u(`tileset_${tag}.png`),
        `tileset`,
        this.textures,
        this.transparencyPolicy,
      );
      this.probes.loadedAssetKeys.push(`tileset`);
      this.assembleGround(
        heights,
        tileset.fillMaterialKey,
        tileset.surfaceMaterialKey,
        tileset.leftSideMaterialKey,
        tileset.rightSideMaterialKey,
        tileset.surfaceIntegrationKey,
        tileset.leftSideIntegrationKey,
        tileset.rightSideIntegrationKey,
      );
      if (verticalCandidate) {
        try {
          const activated = activateVerticalFeatureTransaction({
            selected: verticalCandidate,
            ladderAssetLoaded,
            climbAssetLoaded,
            platformMaterialsReady: true,
            assemblePlatforms: (platforms) =>
              this.assembleUpperPlatforms(
                platforms,
                tileset.fillMaterialKey,
                tileset.surfaceMaterialKey,
                tileset.leftSideMaterialKey,
                tileset.rightSideMaterialKey,
              ),
            assembleLadders: (ladders) => this.assembleLadders(ladders),
            rollbackRendering: () => this.clearVerticalRendering(),
            commit: (selection) => {
              this.verticalWorld = selection.world;
              this.verticalRoutes = selection.routes;
              this.verticalReservedColumns = new Set(
                selection.reservedColumns,
              );
            },
          });
          if (activated) {
            this.probes.loadedAssetKeys.push("ladder", "character_climb");
          } else {
            if (this.textures.exists("ladder")) this.textures.remove("ladder");
            if (this.textures.exists("character_climb")) {
              this.textures.remove("character_climb");
            }
          }
        } catch (error) {
          if (this.textures.exists("ladder")) this.textures.remove("ladder");
          if (this.textures.exists("character_climb")) {
            this.textures.remove("character_climb");
          }
          this.recordErr(error);
        }
      }
    } catch (e) {
      this.clearVerticalRendering();
      this.verticalWorld = inactiveVertical.world;
      this.verticalRoutes = inactiveVertical.routes;
      this.verticalReservedColumns = new Set(inactiveVertical.reservedColumns);
      if (this.textures.exists("ladder")) this.textures.remove("ladder");
      if (this.textures.exists("character_climb")) {
        this.textures.remove("character_climb");
      }
      this.recordErr(e);
    }

    // ---------- Obstacle sheets ----------
    const obstacleCells: {
      sheetIdx: number;
      cellIdx: number;
      w: number;
      h: number;
    }[] = [];
    for (let i = 0; i < spec.obstacles.length; i++) {
      const file = `obstacles_${tag}_${i}.png`;
      const key = `obstacles_${i}`;
      try {
        const { cells } = await loadGridSheet(
          u(file),
          key,
          2,
          4,
          "prop",
          this.textures,
          this.transparencyPolicy,
        );
        this.probes.cellExtractProbe[key] = cells;
        this.probes.loadedAssetKeys.push(key);
        cells.forEach((c, idx) => {
          if (c.w > 16 && c.h > 16) {
            obstacleCells.push({ sheetIdx: i, cellIdx: idx, w: c.w, h: c.h });
          }
        });
      } catch (e) {
        this.recordErr(e);
      }
    }

    this.placeObstacles(heights, obstacleCells);

    // ---------- Items sheet ----------
    try {
      const { cells } = await loadGridSheet(
        u(`items_${tag}.png`),
        `items`,
        2,
        4,
        "item",
        this.textures,
        this.transparencyPolicy,
      );
      this.probes.cellExtractProbe[`items`] = cells;
      this.probes.loadedAssetKeys.push(`items`);
    } catch (e) {
      this.recordErr(e);
    }

    // ---------- Mobs (idle + hurt + concept) ----------
    const mobIdleKeys: string[] = [];
    const mobHurtKeys: string[] = [];
    for (let i = 0; i < spec.mobs.length; i++) {
      const idleKey = `mob_${i}_idle`;
      try {
        await loadFrameStrip(
          u(`mob_${tag}_${i}_idle.png`),
          idleKey,
          4,
          this.textures,
          this.transparencyPolicy,
        );
        this.probes.loadedAssetKeys.push(idleKey);
        mobIdleKeys.push(idleKey);
        if (!this.anims.exists(idleKey)) {
          this.anims.create({
            key: idleKey,
            frames: [0, 1, 2, 3].map((f) => ({ key: idleKey, frame: f })),
            frameRate: 6,
            repeat: -1,
          });
        }
      } catch (e) {
        this.recordErr(e);
        mobIdleKeys.push("");
      }
      const hurtKey = `mob_${i}_hurt`;
      try {
        await loadFrameStrip(
          u(`mob_${tag}_${i}_hurt.png`),
          hurtKey,
          4,
          this.textures,
          this.transparencyPolicy,
        );
        this.probes.loadedAssetKeys.push(hurtKey);
        mobHurtKeys.push(hurtKey);
      } catch (e) {
        this.recordErr(e);
        mobHurtKeys.push("");
      }
      try {
        await loadTransparentSprite(
          u(`mob_concept_${tag}_${i}.png`),
          `mob_concept_${i}`,
          this.textures,
          this.transparencyPolicy,
        );
        this.probes.loadedAssetKeys.push(`mob_concept_${i}`);
      } catch (e) {
        this.recordErr(e);
      }
    }

    this.spawnMobs(heights, mobIdleKeys, mobHurtKeys);

    // ---------- Character ----------
    let charSprite: HTMLCanvasElement | null = null;
    try {
      charSprite = await loadTransparentSprite(
        u(`character_concept_${tag}.png`),
        `character_concept`,
        this.textures,
        this.transparencyPolicy,
      );
      this.probes.loadedAssetKeys.push(`character_concept`);
      const sampleAt = { x: 1, y: 1 };
      this.probes.spriteAlphaProbe[`character_concept`] = {
        spriteKey: `character_concept`,
        sampledAlpha: alphaAt(charSprite, sampleAt.x, sampleAt.y),
        sampledAt: sampleAt,
      };
    } catch (e) {
      this.recordErr(e);
    }
    // Idle strip (sliced) — used for the runtime player avatar.
    try {
      await loadFrameStrip(
        u(`character_${tag}-fromcombined_idle.png`),
        `character_idle`,
        4,
        this.textures,
        this.transparencyPolicy,
      );
      this.probes.loadedAssetKeys.push(`character_idle`);
    } catch (e) {
      this.recordErr(e);
    }
    // Other states — used by Phase 7 player state machine.
    for (const state of ["walk", "run", "jump", "crawl"]) {
      try {
        await loadFrameStrip(
          u(`character_${tag}-fromcombined_${state}.png`),
          `character_${state}`,
          4,
          this.textures,
          this.transparencyPolicy,
        );
        this.probes.loadedAssetKeys.push(`character_${state}`);
      } catch (e) {
        this.recordErr(e);
      }
    }
    try {
      await loadFrameStrip(
        u(`character_${tag}_attack.png`),
        `character_attack`,
        4,
        this.textures,
        this.transparencyPolicy,
      );
      this.probes.loadedAssetKeys.push(`character_attack`);
    } catch (e) {
      this.recordErr(e);
    }

    this.spawnPlayer(heights);

    // ---------- Inventory + portal ----------
    try {
      await loadTransparentSprite(
        u(`inventory_${tag}.png`),
        `inventory`,
        this.textures,
        this.transparencyPolicy,
      );
      this.probes.loadedAssetKeys.push(`inventory`);
    } catch (e) {
      this.recordErr(e);
    }
    try {
      await loadTransparentSprite(
        u(`portal_${tag}.png`),
        `portal`,
        this.textures,
        this.transparencyPolicy,
      );
      this.probes.loadedAssetKeys.push(`portal`);
    } catch (e) {
      this.recordErr(e);
    }

    // Build the Phase 7 systems.
    this.items = new ItemSystem({
      scene: this,
      tilePx: TILE_PX,
      baselineY: GROUND_BASELINE_Y,
      heightFn: (col) => terrainHeightAtColumn(this.heights, col),
      itemFrameKey: (idx) => `item_${idx % 8}`,
      itemTextureKey: "items",
    });

    this.inventory = new InventoryHud({
      scene: this,
      panelKey: "inventory",
      itemsKey: "items",
      itemFrameKey: (idx) => `item_${idx % 8}`,
      viewW: VIEW_W,
      viewH: VIEW_H,
    });

    this.portal = new PortalSystem({
      scene: this,
      portalKey: "portal",
      tilePx: TILE_PX,
      baselineY: GROUND_BASELINE_Y,
      heightFn: (col) => terrainHeightAtColumn(this.heights, col),
      stageWidthPx: STAGE_W,
    });

    // Concept (purely for completeness; not displayed).
    try {
      await loadOpaqueSprite(u(`concept_${tag}.png`), `concept`, this.textures);
      this.probes.loadedAssetKeys.push(`concept`);
    } catch (e) {
      this.recordErr(e);
    }
  }

  // ---------- Ground assembly ----------

  private assembleGround(
    heights: readonly number[],
    fillMaterialKey: string,
    surfaceMaterialKey: string,
    leftSideMaterialKey: string,
    rightSideMaterialKey: string,
    surfaceIntegrationKey: string,
    leftSideIntegrationKey: string,
    rightSideIntegrationKey: string,
  ) {
    for (const run of [
      ...this.terrainFillSprites,
      ...this.terrainIntegrationSprites,
      ...this.terrainBoundarySprites,
    ]) {
      run.sprite.destroy();
    }
    this.terrainFillSprites = [];
    this.terrainIntegrationSprites = [];
    this.terrainBoundarySprites = [];
    this.terrainCullRange = undefined;

    const plan = buildTerrainPlan(heights, TERRAIN_CONTRACT);
    const renderPlan = buildTerrainRenderPlan(
      plan,
      TERRAIN_SURFACE_BAND_TEXTURE_HEIGHT,
    );
    const initialRange = visibleTerrainColumnRange(0, VIEW_W, TERRAIN_CONTRACT);
    const visibleAtStart = (startColumn: number, endColumn: number) =>
      initialRange !== null &&
      endColumn >= initialRange.start &&
      startColumn <= initialRange.end;

    for (const run of renderPlan.fillRuns) {
      const fill = this.add.tileSprite(
        run.paintRect.x,
        run.paintRect.y,
        run.paintRect.width,
        run.paintRect.height,
        fillMaterialKey,
      );
      fill.setOrigin(0, 0);
      const materialOrigin = terrainMaterialOrigin(run);
      fill.tilePositionX = materialOrigin.x;
      fill.tilePositionY = materialOrigin.y;
      fill.setDepth(SCENE_CONTENT_DEPTH.terrain);
      fill.setVisible(visibleAtStart(run.startColumn, run.endColumn));
      this.terrainFillSprites.push(
        Object.freeze({
          startColumn: run.startColumn,
          endColumn: run.endColumn,
          sprite: fill,
        }),
      );
    }

    for (const patch of renderPlan.integrationPatches) {
      const materialKey =
        patch.kind === "surface"
          ? surfaceIntegrationKey
          : patch.kind === "side-left"
            ? leftSideIntegrationKey
            : rightSideIntegrationKey;
      const integration = this.add.tileSprite(
        patch.paintRect.x,
        patch.paintRect.y,
        patch.paintRect.width,
        patch.paintRect.height,
        materialKey,
      );
      integration.setOrigin(0, 0);
      integration.tilePositionX =
        patch.kind === "surface" ? patch.paintRect.x : 0;
      integration.tilePositionY =
        patch.kind === "surface" ? 0 : patch.paintRect.y;
      integration.setDepth(SCENE_CONTENT_DEPTH.terrain);
      integration.setVisible(
        visibleAtStart(patch.startColumn, patch.endColumn),
      );
      this.terrainIntegrationSprites.push(
        Object.freeze({
          startColumn: patch.startColumn,
          endColumn: patch.endColumn,
          sprite: integration,
        }),
      );
    }

    // Approved contour paint is created last at the same semantic depth so it
    // remains crisp over the inward transition.
    for (const strip of renderPlan.boundaryStrips) {
      const materialKey =
        strip.kind === "surface"
          ? surfaceMaterialKey
          : strip.kind === "side-left"
            ? leftSideMaterialKey
            : rightSideMaterialKey;
      const boundary = this.add.tileSprite(
        strip.paintRect.x,
        strip.paintRect.y,
        strip.paintRect.width,
        strip.paintRect.height,
        materialKey,
      );
      boundary.setOrigin(0, 0);
      boundary.tilePositionX = strip.paintRect.x;
      boundary.tilePositionY = strip.paintRect.y;
      boundary.setDepth(SCENE_CONTENT_DEPTH.terrain);
      boundary.setVisible(visibleAtStart(strip.startColumn, strip.endColumn));
      this.terrainBoundarySprites.push(
        Object.freeze({
          startColumn: strip.startColumn,
          endColumn: strip.endColumn,
          sprite: boundary,
        }),
      );
    }
    this.terrainCullRange = initialRange;
  }

  private updateTerrainCulling(camera: Phaser.Cameras.Scene2D.Camera): void {
    if (
      this.terrainFillSprites.length === 0 &&
      this.terrainIntegrationSprites.length === 0 &&
      this.terrainBoundarySprites.length === 0
    ) {
      return;
    }
    const worldWidth = camera.width / camera.zoom;
    const midpointX = camera.scrollX + camera.width / 2;
    const next = visibleTerrainColumnRange(
      midpointX - worldWidth / 2,
      midpointX + worldWidth / 2,
      TERRAIN_CONTRACT,
    );
    const previous = this.terrainCullRange;
    if (
      previous !== undefined &&
      ((previous === null && next === null) ||
        (previous !== null &&
          next !== null &&
          previous.start === next.start &&
          previous.end === next.end))
    ) {
      return;
    }
    for (const run of [
      ...this.terrainFillSprites,
      ...this.terrainIntegrationSprites,
      ...this.terrainBoundarySprites,
    ]) {
      run.sprite.setVisible(
        next !== null &&
          run.endColumn >= next.start &&
          run.startColumn <= next.end,
      );
    }
    this.terrainCullRange = next;
  }

  private assembleUpperPlatforms(
    platforms: readonly UpperPlatform[],
    fillMaterialKey: string,
    surfaceMaterialKey: string,
    leftSideMaterialKey: string,
    rightSideMaterialKey: string,
  ): void {
    const created: Phaser.GameObjects.GameObject[] = [];
    const next: VerticalRenderSprite[] = [];
    try {
      for (const platform of platforms) {
        const plan = buildPlatformRenderPlan(platform);
        const body = this.add.tileSprite(
          plan.body.x,
          plan.body.y,
          plan.body.width,
          plan.body.height,
          fillMaterialKey,
        );
        created.push(body);
        body.setOrigin(0, 0);
        body.tilePositionX = plan.body.x;
        body.tilePositionY = plan.body.y;
        body.setDepth(SCENE_CONTENT_DEPTH.terrain);

        const cap = this.add.tileSprite(
          plan.cap.x,
          plan.cap.y,
          plan.cap.width,
          plan.cap.height,
          surfaceMaterialKey,
        );
        created.push(cap);
        cap.setOrigin(0, 0);
        cap.tilePositionX = plan.cap.x;
        cap.tilePositionY = plan.cap.y;
        cap.setDepth(SCENE_CONTENT_DEPTH.terrain);

        const sides = plan.sides.map((side) => {
          const sprite = this.add.tileSprite(
            side.x,
            side.y,
            side.width,
            side.height,
            side.edge === "left" ? leftSideMaterialKey : rightSideMaterialKey,
          );
          created.push(sprite);
          sprite.setOrigin(0, 0);
          sprite.tilePositionX = side.x;
          sprite.tilePositionY = side.y;
          sprite.setDepth(SCENE_CONTENT_DEPTH.terrain);
          return sprite;
        });
        next.push(
          Object.freeze({
            id: platform.id,
            bounds: Object.freeze({
              left: platform.left,
              right: platform.right,
              top: platform.deckY,
              bottom: platform.deckY + platform.thickness,
            }),
            sprites: Object.freeze([body, cap, ...sides]),
          }),
        );
      }
    } catch (error) {
      for (const sprite of created) sprite.destroy();
      throw error;
    }
    for (const rendered of this.platformRenderSprites)
      for (const sprite of rendered.sprites) sprite.destroy();
    this.platformRenderSprites = next;
  }

  private assembleLadders(ladders: readonly LadderZone[]): void {
    const created: Phaser.GameObjects.GameObject[] = [];
    const next: VerticalRenderSprite[] = [];
    try {
      for (const ladder of ladders) {
        const visual = ladderVisualBounds(ladder);
        const sprite = this.add.image(ladder.centerX, visual.top, "ladder");
        created.push(sprite);
        sprite.setOrigin(0.5, 0);
        sprite.setDisplaySize(visual.width, visual.height);
        sprite.setDepth(SCENE_CONTENT_DEPTH.prop);
        next.push(
          Object.freeze({
            id: ladder.id,
            bounds: visual,
            sprites: Object.freeze([sprite]),
          }),
        );
      }
    } catch (error) {
      for (const sprite of created) sprite.destroy();
      throw error;
    }
    for (const rendered of this.ladderRenderSprites)
      for (const sprite of rendered.sprites) sprite.destroy();
    this.ladderRenderSprites = next;
  }

  private clearVerticalRendering(): void {
    for (const rendered of [
      ...this.platformRenderSprites,
      ...this.ladderRenderSprites,
    ]) {
      for (const sprite of rendered.sprites) sprite.destroy();
    }
    this.platformRenderSprites = [];
    this.ladderRenderSprites = [];
  }

  private updateVerticalCulling(camera: Phaser.Cameras.Scene2D.Camera): void {
    for (const rendered of [
      ...this.platformRenderSprites,
      ...this.ladderRenderSprites,
    ]) {
      const visible = this.verticalVisible(camera, rendered.bounds);
      for (const sprite of rendered.sprites) sprite.setVisible(visible);
    }
  }

  // ---------- Obstacle placement ----------

  private placeObstacles(
    heights: number[],
    cells: { sheetIdx: number; cellIdx: number; w: number; h: number }[],
  ) {
    if (cells.length === 0) return;
    const runs = flatRuns(heights, 2);
    this.probes.flatRunCount = runs.length;
    let placed = 0;
    for (let r = 0; r < runs.length; r++) {
      const run = runs[r];
      if (run.len < 3) continue;
      const col = run.start + Math.floor(run.len / 2);
      if (!verticalSpawnAllowed(this.verticalReservedColumns, col)) continue;
      const cell = cells[(r * 7) % cells.length];
      const sheetKey = `obstacles_${cell.sheetIdx}`;
      const frameKey = `prop_${cell.cellIdx}`;
      const h = heights[col];
      const surfaceY = terrainSurfaceY(h, TILE_PX, GROUND_BASELINE_Y);
      const targetH = TILE_PX * 1.4;
      const aspect = cell.w / cell.h;
      const targetW = targetH * aspect;
      const x = col * TILE_PX + TILE_PX / 2;
      const y = surfaceY;
      const img = this.add.image(x, y, sheetKey, frameKey);
      img.setOrigin(0.5, 1.0);
      img.setDisplaySize(targetW, targetH);
      img.setDepth(SCENE_CONTENT_DEPTH.prop);
      placed++;
    }
    this.probes.obstacleCount = placed;
  }

  // ---------- Mob spawning ----------

  private spawnMobs(
    heights: number[],
    mobIdleKeys: string[],
    mobHurtKeys: string[],
  ) {
    const hF = (col: number) => terrainHeightAtColumn(heights, col);
    if (mobIdleKeys.filter(Boolean).length === 0) return;
    const runs = flatRuns(heights, 2);
    let spawned = 0;
    let mobIdx = 0;
    for (let r = 0; r < runs.length; r += 2) {
      const run = runs[r];
      const col = run.start + 1;
      if (!verticalSpawnAllowed(this.verticalReservedColumns, col)) continue;
      const ladderIndex = mobIdx % mobIdleKeys.length;
      const idleKey = mobIdleKeys[ladderIndex];
      const hurtKey = mobHurtKeys[ladderIndex] ?? "";
      if (!idleKey) {
        mobIdx++;
        continue;
      }
      const mob = new Mob({
        scene: this,
        ladderIndex,
        spawnCol: col,
        tilePx: TILE_PX,
        worldWidthPx: STAGE_W,
        baselineY: GROUND_BASELINE_Y,
        heightFn: hF,
        spriteHeightPx: TILE_PX * 1.8,
        idleAnimKey: idleKey,
        hurtTextureKey: hurtKey || idleKey,
        fixedStepMotion: Boolean(this.automationMode),
      });
      this.mobs.push(mob);
      mobIdx++;
      spawned++;
    }
    this.probes.mobCount = spawned;
  }

  // ---------- Player spawn ----------

  private spawnPlayer(heights: number[]) {
    const runs = flatRuns(heights, 3);
    const startCol = runs.length > 0 ? runs[0].start + 1 : 4;
    this.probes.playerColumn = startCol;
    const h = heights[startCol];
    const surfaceY = terrainSurfaceY(h, TILE_PX, GROUND_BASELINE_Y);
    const x = startCol * TILE_PX + TILE_PX / 2;

    const hF = (col: number) => terrainHeightAtColumn(heights, col);

    this.player = new Player({
      scene: this,
      startX: x,
      startY: surfaceY,
      tilePx: TILE_PX,
      worldWidthPx: STAGE_W,
      baselineY: GROUND_BASELINE_Y,
      heightFn: hF,
      targetSpriteHeight: TILE_PX * 2.2,
      platforms: this.verticalWorld.platforms,
      ladders: this.verticalWorld.ladders,
      onTransition: (kind, data) => this.logEvent(kind, data),
    });

    this.cameras.main.scrollX = Math.max(0, x - VIEW_W / 2);
  }

  private recordErr(e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    this.probes.consoleErrors.push(msg);
    console.error("[scene]", msg);
  }
}

export type PreviewGameHandle = {
  destroy: (removeCanvas: boolean) => void;
};

export function bootGame(
  parent: HTMLElement,
  tag: string,
  transparencyPolicy: PreviewTransparencyPolicy,
  automationMode: GameplayAutomationMode | null = null,
): PreviewGameHandle {
  const game = new Phaser.Game({
    type: automationMode ? Phaser.CANVAS : Phaser.AUTO,
    width: GAMEPLAY_AUTOMATION_VIEWPORT.width,
    height: GAMEPLAY_AUTOMATION_VIEWPORT.height,
    parent,
    backgroundColor: "#000",
    callbacks: automationMode
      ? {
          postBoot: (bootedGame) => {
            sleepGameplayAutomationLoopAfterBoot(bootedGame.loop);
          },
        }
      : undefined,
    scene: [new StageScene({ tag, transparencyPolicy, automationMode })],
    scale: {
      mode: automationMode ? Phaser.Scale.NONE : Phaser.Scale.FIT,
      autoCenter: Phaser.Scale.CENTER_BOTH,
    },
  });
  if (!automationMode) return game;
  return {
    destroy(removeCanvas: boolean): void {
      game.destroy(removeCanvas);
      // Automation intentionally sleeps the TimeStep, so synchronously run
      // Phaser's pending-destroy branch instead of waiting for a nonexistent rAF.
      if (game.isBooted && !game.loop.running) game.step(0, 0);
    },
  };
}

// Helper: surface SlopeKind for callers (re-export the type only used here for tests).
export type { SlopeKind };
