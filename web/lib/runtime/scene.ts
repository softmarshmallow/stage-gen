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
  loadOpaqueSprite,
  loadParallaxLayer,
  loadTransparentSprite,
  loadFrameStrip,
  loadGridSheet,
  loadTileset,
} from "./assets";
import type { PreviewTransparencyPolicy } from "@/lib/shell/transparency";
import {
  buildHeightmap,
  buildHeightmapFromSeed,
  flatRuns,
  type SlopeKind,
} from "./heightmap";
// pickRole / slopeAt no longer needed — assembleGround uses a single
// ground_fill cell (registered by loadTileset) for every tile.
import { FpsProbe, type FpsSnapshot } from "./fps";
import { Player, type PlayerStateSnapshot } from "./player";
import { Mob } from "./mob";
import { ItemSystem } from "./items";
import { InventoryHud } from "./inventory";
import { PortalSystem } from "./portal";
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
  type GameplayTranscriptEvent,
  type GameplayWorldBoundsProbe,
} from "./automation";

type WorldLayer = {
  id: string;
  title: string;
  z_index: number;
  parallax: number;
  opaque: boolean;
  paint_region: string;
  description: string;
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

const VIEW_W = 1280;
const VIEW_H = 720;

// Ground band geometry. The tileset is 2400×800 (12 cols × 4 rows = 200×200
// per cell). At runtime we render tiles smaller for usable column density.
const TILE_PX = 64;
const COLS = 200; // total stage width in columns → 200 × 64 = 12800 px
const STAGE_W = COLS * TILE_PX;
const GROUND_BASELINE_Y = VIEW_H - 8; // Y of the painted ground band (where player feet sit)
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

  // Parallax sprite tracking — index by layer id.
  // For fading layers we render TWO TileSprites at the same screen position.
  // The partner is offset by (naturalWidth − fadePx) in source space so its
  // RIGHT fade band lands exactly on the primary's LEFT fade band (and vice
  // versa). With linear taper the two alphas sum to ~1 across the entire
  // fade band — the seam disappears.
  private parallaxSprites: {
    id: string;
    sprite: Phaser.GameObjects.TileSprite;
    parallax: number;
    partner?: Phaser.GameObjects.TileSprite;
    naturalWidth: number;
    seamOffset: number;
  }[] = [];
  // Foreground (parallax > 1.0): TileSprites placed in front of gameplay.
  private foregroundSprites: {
    id: string;
    sprite: Phaser.GameObjects.TileSprite;
    parallax: number;
    partner?: Phaser.GameObjects.TileSprite;
    naturalWidth: number;
    seamOffset: number;
  }[] = [];

  // Phase 7 systems.
  private player?: Player;
  private mobs: Mob[] = [];
  private items?: ItemSystem;
  private inventory?: InventoryHud;
  private portal?: PortalSystem;
  private heights: number[] = [];
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
    this.cameras.main.setBounds(0, 0, STAGE_W, VIEW_H);

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
      for (const foreground of this.foregroundSprites) {
        foreground.sprite.setVisible(presentation.foregroundVisible);
        foreground.partner?.setVisible(presentation.foregroundVisible);
      }
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
        cam.scrollY = 0;
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

    // Drive parallax tilePosition based on scrollX × parallax.
    // For fading layers the partner is offset by seamOffset = (W − fadePx)
    // in source space so its right fade band lands directly on top of the
    // primary's left fade band → composited alpha stays opaque across seam.
    for (const p of this.parallaxSprites) {
      const tx = cam.scrollX * p.parallax;
      p.sprite.tilePositionX = tx;
      if (p.partner) p.partner.tilePositionX = tx + p.seamOffset;
    }
    for (const p of this.foregroundSprites) {
      const tx = cam.scrollX * p.parallax;
      p.sprite.tilePositionX = tx;
      if (p.partner) p.partner.tilePositionX = tx + p.seamOffset;
    }

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
      // Surface live tilePositionX per layer for headless parallax verification.
      const tiles: Record<
        string,
        { parallax: number; tilePositionX: number; depth: number }
      > = {};
      for (const p of this.parallaxSprites) {
        tiles[p.id] = {
          parallax: p.parallax,
          tilePositionX: p.sprite.tilePositionX,
          depth: p.sprite.depth,
        };
      }
      for (const p of this.foregroundSprites) {
        tiles[p.id] = {
          parallax: p.parallax,
          tilePositionX: p.sprite.tilePositionX,
          depth: p.sprite.depth,
        };
      }
      if (!this.automationMode) {
        (window as unknown as { __sceneTiles?: typeof tiles }).__sceneTiles =
          tiles;
      }
    }
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

    // ---------- Parallax layers ----------
    // Sort by z_index ascending so we render back-to-front.
    const sortedLayers = [...spec.layers].sort((a, b) => a.z_index - b.z_index);
    // Fade band width on each tile edge (and the overlap width with the
    // partner sprite). Larger = more of the texture cross-blends at the
    // seam = softer / less visible wrap. seamOffset stays = W − FADE_PX
    // so primary's left fade lands exactly on partner's right fade.
    const FADE_PX = 256;
    for (const layer of sortedLayers) {
      const file = `layer_${tag}_${layer.id}.png`;
      const key = `layer_${layer.id}`;
      try {
        const loaded = await loadParallaxLayer(
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

        const sprite = this.add.tileSprite(0, 0, VIEW_W, VIEW_H, key);
        sprite.setOrigin(0, 0);
        sprite.setScrollFactor(0);
        const ts = VIEW_H / loaded.height;
        sprite.setTileScale(ts, ts);

        // Helper: build a half-phase partner TileSprite that renders at the
        // same screen position but tiled at +naturalWidth/2 in source space.
        // This stitches the fade seams: at any screen-x where sprite A is in
        // its fade band, sprite B is mid-tile (full alpha) and covers it.
        // Skipped for opaque layers (no fade gap to stitch).
        const makePartner = (depth: number) => {
          const partner = this.add.tileSprite(0, 0, VIEW_W, VIEW_H, key);
          partner.setOrigin(0, 0);
          partner.setScrollFactor(0);
          partner.setTileScale(ts, ts);
          partner.setDepth(depth);
          return partner;
        };

        // Tight edge-overlap: partner is shifted by (W − fadePx) so its
        // RIGHT fade band lands directly on top of primary's LEFT fade band.
        // Linear taper sum c/F + (F−1−c)/F ≈ 1 across the band → seamless.
        const seamOffset = loaded.width - FADE_PX;

        if (layer.parallax > 1.0) {
          sprite.setDepth(1000 + layer.z_index);
          try {
            const fx = (
              sprite as unknown as {
                postFX?: {
                  addBlur?: (
                    q?: number,
                    x?: number,
                    y?: number,
                    str?: number,
                    color?: number,
                    steps?: number,
                  ) => unknown;
                };
              }
            ).postFX;
            if (fx?.addBlur) {
              const strength = Math.min(4, (layer.parallax - 1.0) * 6);
              fx.addBlur(0, 2, 2, strength, 0xffffff, 4);
            }
          } catch {}
          // Foreground partner sits at the same depth slot; mirror the blur.
          const partner = makePartner(1000 + layer.z_index);
          try {
            const fx = (
              partner as unknown as {
                postFX?: {
                  addBlur?: (
                    q?: number,
                    x?: number,
                    y?: number,
                    str?: number,
                    color?: number,
                    steps?: number,
                  ) => unknown;
                };
              }
            ).postFX;
            if (fx?.addBlur) {
              const strength = Math.min(4, (layer.parallax - 1.0) * 6);
              fx.addBlur(0, 2, 2, strength, 0xffffff, 4);
            }
          } catch {}
          this.foregroundSprites.push({
            id: layer.id,
            sprite,
            parallax: layer.parallax,
            partner,
            naturalWidth: loaded.width,
            seamOffset,
          });
          this.probes.foregroundLayers.push(layer.id);
        } else if (layer.opaque) {
          sprite.setDepth(0);
          // Opaque skybox doesn't fade → no seam to stitch → no partner.
          this.parallaxSprites.push({
            id: layer.id,
            sprite,
            parallax: 0,
            naturalWidth: loaded.width,
            seamOffset: 0,
          });
        } else {
          sprite.setDepth(layer.z_index);
          const partner = makePartner(layer.z_index);
          this.parallaxSprites.push({
            id: layer.id,
            sprite,
            parallax: layer.parallax,
            partner,
            naturalWidth: loaded.width,
            seamOffset,
          });
        }
      } catch (e) {
        this.recordErr(e);
      }
    }

    // ---------- Tileset + ground assembly ----------
    let tileW = TILE_PX;
    let tileH = TILE_PX;
    try {
      const ts = await loadTileset(
        u(`tileset_${tag}.png`),
        `tileset`,
        this.textures,
        this.transparencyPolicy,
      );
      this.probes.loadedAssetKeys.push(`tileset`);
      tileW = ts.tileW;
      tileH = ts.tileH;
    } catch (e) {
      this.recordErr(e);
    }
    this.assembleGround(heights, tileW, tileH);

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
      heightFn: (col) =>
        this.heights[Math.max(0, Math.min(this.heights.length - 1, col))] ??
        MIN_H,
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
      heightFn: (col) =>
        this.heights[Math.max(0, Math.min(this.heights.length - 1, col))] ??
        MIN_H,
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
    heights: number[],
    srcTileW: number,
    srcTileH: number,
  ) {
    const baseY = GROUND_BASELINE_Y;
    const groundDepth = 500;

    const sheetKey = `tileset`;
    // Quick ship: the 12×4 role contract is unreliable (gpt-image-2 doesn't
    // always honour it). Use the single best-opacity cell (registered as
    // `ground_fill` by loadTileset) for every ground tile. Loses
    // slope/corner variety but every column renders as a clean solid block.
    const frameKey = "ground_fill";

    for (let x = 0; x < heights.length; x++) {
      const h = heights[x];
      for (let depth = 0; depth < h; depth++) {
        const tx = x * TILE_PX + TILE_PX / 2;
        const ty = baseY - depth * TILE_PX - TILE_PX / 2;
        const img = this.add.image(tx, ty, sheetKey, frameKey);
        img.setDisplaySize(TILE_PX, TILE_PX);
        img.setDepth(groundDepth);
      }
    }
    void srcTileW;
    void srcTileH;
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
      const cell = cells[(r * 7) % cells.length];
      const sheetKey = `obstacles_${cell.sheetIdx}`;
      const frameKey = `prop_${cell.cellIdx}`;
      const h = heights[col];
      const surfaceY = GROUND_BASELINE_Y - h * TILE_PX;
      const targetH = TILE_PX * 1.4;
      const aspect = cell.w / cell.h;
      const targetW = targetH * aspect;
      const x = col * TILE_PX + TILE_PX / 2;
      const y = surfaceY;
      const img = this.add.image(x, y, sheetKey, frameKey);
      img.setOrigin(0.5, 1.0);
      img.setDisplaySize(targetW, targetH);
      img.setDepth(700);
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
    const hF = (col: number) =>
      heights[Math.max(0, Math.min(heights.length - 1, col))] ?? MIN_H;
    if (mobIdleKeys.filter(Boolean).length === 0) return;
    const runs = flatRuns(heights, 2);
    let spawned = 0;
    let mobIdx = 0;
    for (let r = 0; r < runs.length; r += 2) {
      const run = runs[r];
      const col = run.start + 1;
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
    const surfaceY = GROUND_BASELINE_Y - h * TILE_PX;
    const x = startCol * TILE_PX + TILE_PX / 2;

    const hF = (col: number) =>
      heights[Math.max(0, Math.min(heights.length - 1, col))] ?? MIN_H;

    this.player = new Player({
      scene: this,
      startX: x,
      startY: surfaceY,
      tilePx: TILE_PX,
      baselineY: GROUND_BASELINE_Y,
      heightFn: hF,
      targetSpriteHeight: TILE_PX * 2.2,
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
