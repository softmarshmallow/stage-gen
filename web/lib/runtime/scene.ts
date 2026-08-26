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
  loadVerifiedForegroundRepeat,
  loadVerifiedRepeatLayer,
  loadTransparentSprite,
  loadFrameStrip,
  loadGridSheet,
  loadTileset,
  type LoadedForegroundLayer,
  loadTrimmedSprite,
  type AssetUrlFn,
} from "./assets";
import type { ScaleReference } from "./sprite-scale";
import type { PreviewTransparencyPolicy } from "@/lib/shell/transparency";
import {
  buildHeightmapFromSeed,
  flatRuns,
  heightmapSeedForTag,
  type SlopeKind,
} from "./heightmap";
import { FpsProbe, type FpsSnapshot } from "./fps";
import { Player, type PlayerStateSnapshot } from "./player";
import { Mob } from "./mob";
import {
  MobPopulationDirector,
  parseMobPopulationManifest,
  type MobPopulationManifest,
  type MobPopulationMapManifest,
  type PopulationSnapshot,
  type SpawnReservation,
  type ZoneCandidateColumns,
} from "./spawn-director";
import { PLAYER_MAX_HP, aggressionProfile, parseAggression } from "./combat";
import {
  CombatTextSystem,
  type CombatTextSystemSnapshot,
} from "./combat-text";
import { loadBrowserCombatTextFont } from "./combat-font";
import { mobRenderEnvelope } from "./mob-geometry";
import { ItemSystem, type DroppedItem } from "./items";
import { InventoryHud } from "./inventory";
import { FloatingHealthBar, PLAYER_HEALTH_BAR_STYLE } from "./health-bar";
import { PortalSystem, type PortalKind, type PortalSpec } from "./portal";
import { Npc } from "./npc";
import {
  DialogueBox,
  type DialoguePortraitTextureKeys,
  type DialoguePresentationBeat,
} from "./dialogue-box";
import {
  DIALOGUE_EXPRESSION_STATES,
  loadVerifiedDialogueSprite,
  parseDialogueCharactersManifest,
  type DialogueCharacterRuntimeSpec,
} from "./dialogue-sequence";
import {
  npcInteractionTarget,
  parseVillageManifest,
  planNpcPlacements,
  type VillageSpec,
} from "./village";
import {
  assertContinuousPopulationCoverage,
  buildStageBook,
  normalizeStageIndex,
  parseMapBookManifest,
  portalDestination,
  stagePlanAt,
  stageTerrainSeed,
  type StageKind,
  type StagePlan,
} from "./stages";
import {
  DeterministicSoundtrackPlayer,
  createBrowserSoundtrackTransport,
  parseSoundtrackForMapPool,
  type SoundtrackSnapshot,
} from "./soundtrack";
import {
  horizontalImageRepeats,
  parseScrollingManifestEnvelope,
  resolveCombatTextManifest,
  runtimeScaleReferences,
  type CombatTextManifest,
} from "./manifest";
import {
  scrollingDemoLevelCapabilities,
  type ScrollingDemoLevelCapabilities,
} from "./level-profile";
import { horizontalCameraScrollX } from "./camera-follow";
import {
  SCENE_CONTENT_DEPTH,
  layoutSceneLayer,
  resolveSceneLayerStack,
  sceneLayerProbe,
  withVerifiedHorizontalRepeat,
  type SceneLayerBlend,
  type SceneLayerContract,
  type SceneLayerAssetMetadata,
  type SceneLayerImageRepeatSelection,
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
  gameplayStillComposition,
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
  type GameplayStillComposition,
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
  // The near foreground meets the ground where the ground actually is. This was
  // a standalone 704, one quarter-tile above the baseline, so the layer's own
  // last painted row landed 16px short of the frame and the bottom of every
  // screen showed a full-width band of the terrain behind it.
  foregroundContactScreenY: GROUND_BASELINE_Y,
  foregroundSafeBandTopY: 540,
  foregroundMaxScale: 0.75,
});
const MIN_H = 1; // tiles
const MAX_H = 4;

/**
 * Drawn height of the player, in world pixels.
 *
 * Hoisted out of `spawnPlayer` because it is no longer only the player's business: every NPC is
 * head-matched against the player's idle sheet, and that match multiplies through this number.
 * Two copies of it would drift the moment one was tuned, and the failure would be silent -
 * villagers rendering at a plausible but wrong size next to the player they are supposed to match.
 */
const PLAYER_TARGET_SPRITE_HEIGHT = TILE_PX * 2.2;

/**
 * Ground height, in tiles, of the village's flat terrain.
 *
 * Mid-range rather than `MIN_H`, so the town still sits on a visible body of ground: the
 * terrain assembler paints fill below the surface band, and a one-tile village would leave the
 * surface strip resting directly on the bottom of the frame.
 */
const VILLAGE_TERRAIN_HEIGHT_TILES = 2;

/**
 * Drawn height of a village fixture, in world pixels.
 *
 * Taller than an obstacle prop's `TILE_PX * 1.4`, and deliberately just below the player's
 * `TILE_PX * 2.2`: fixtures are stalls, awnings and poles that a person walks under, so drawing
 * them at obstacle scale makes the town read as scattered scenery rather than as buildings.
 */
const VILLAGE_FIXTURE_HEIGHT_PX = TILE_PX * 1.8;

/**
 * Columns kept clear at each end of the village when placing fixtures.
 *
 * The same margin `planNpcPlacements` applies to residents, and for the same reason: the portals
 * stand at column 3 and at (last - 4), and a fixture painted over a portal mouth hides the one
 * object on the stage the player has to be able to find.
 */
const VILLAGE_FIXTURE_EDGE_MARGIN_COLUMNS = 6;

/**
 * Columns kept clear on each side of a resident when placing fixtures.
 *
 * A fixture is bottom-anchored on the same terrain surface as the villager beside it and is drawn
 * at nearly the player's height, so one placed on an adjacent column overlaps the villager's name
 * label and their "▲ Talk" prompt - the two pieces of the interaction the player reads before
 * pressing anything.
 */
const VILLAGE_FIXTURE_NPC_CLEARANCE_COLUMNS = 2;

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

/** The runtime-asset entries from the one current lower_snake_case manifest. */
function manifestRuntimeAssets(
  manifest: Record<string, unknown>,
): readonly Record<string, unknown>[] {
  const entries = manifest["runtime_assets"];
  if (
    !Array.isArray(entries) ||
    entries.some(
      (entry) =>
        typeof entry !== "object" || entry === null || Array.isArray(entry),
    )
  ) {
    throw new Error("current scrolling manifest runtime_assets are invalid");
  }
  return entries as readonly Record<string, unknown>[];
}

/** Return the optional v2 population subsystem from a normalized run manifest. */
function manifestMobPopulation(manifest: unknown): unknown | null {
  if (typeof manifest !== "object" || manifest === null || Array.isArray(manifest)) {
    return null;
  }
  const gameplay = (manifest as Record<string, unknown>)["gameplay"];
  if (gameplay === undefined) return null;
  if (typeof gameplay !== "object" || gameplay === null || Array.isArray(gameplay)) {
    throw new Error("manifest gameplay must be an object");
  }
  const record = gameplay as Record<string, unknown>;
  return Object.prototype.hasOwnProperty.call(record, "mob_population")
    ? record["mob_population"]
    : null;
}

function browserPrefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/** The runtime slot one current manifest entry names, or "" when it names none. */
function manifestRuntimeSlot(entry: Record<string, unknown>): string {
  const slot = entry["runtime_slot"];
  return typeof slot === "string" ? slot : "";
}

type RunManifestFetchResponse = Readonly<{
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
}>;

type RunManifestFetch = (
  url: string,
  init: Readonly<{ cache: "no-store" }>,
) => Promise<RunManifestFetchResponse>;

/** Fetch and validate the one required current scrolling manifest. */
async function fetchCurrentRunManifest(
  url: string,
  tag: string,
  request: RunManifestFetch = fetch,
): Promise<Record<string, unknown>> {
  const response = await request(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${url} → HTTP ${response.status}`);
  return parseScrollingManifestEnvelope(await response.json(), tag);
}

/**
 * The village slot a runtime role names, or null when the role is not a resident's drawn sheet.
 *
 * Parsed rather than matched against a precomputed set of the four expected role names, so a run
 * whose manifest publishes its residents in a different order, or under slots that are not
 * 0..3, still binds each reference to the resident it was measured from.
 *
 * Both drawn states are matched here, and the turnaround is not. `village-npc-<i>-concept` is
 * three views of one resident on one sheet, so a scale reference is never measured from it, and
 * a role pattern loose enough to catch it would bind a reference that does not exist.
 */
function villageNpcDrawnSlot(role: string): number | null {
  const match = /^village-npc-(\d+)-(?:idle|still)$/.exec(role);
  if (!match) return null;
  const slot = Number(match[1]);
  return Number.isSafeInteger(slot) && slot >= 0 ? slot : null;
}

/**
 * The nearest column to `ideal` that clears every resident, or null when none does.
 *
 * Searches outward one step at a time so a fixture nudged off a villager lands as close to its
 * even spacing as the town allows, rather than being pushed to whichever end the scan happened
 * to start from. Returning null is the honest answer for a village whose residents cover the
 * whole street: one fixture short is a smaller lie than one drawn over somebody's talk prompt.
 */
function clearVillageFixtureColumn(
  ideal: number,
  firstColumn: number,
  lastColumn: number,
  npcColumns: ReadonlySet<number>,
): number | null {
  const clear = (column: number) => {
    if (column < firstColumn || column > lastColumn) return false;
    for (
      let offset = -VILLAGE_FIXTURE_NPC_CLEARANCE_COLUMNS;
      offset <= VILLAGE_FIXTURE_NPC_CLEARANCE_COLUMNS;
      offset += 1
    ) {
      if (npcColumns.has(column + offset)) return false;
    }
    return true;
  };
  const reach = Math.max(ideal - firstColumn, lastColumn - ideal);
  for (let step = 0; step <= reach; step += 1) {
    if (clear(ideal - step)) return ideal - step;
    if (clear(ideal + step)) return ideal + step;
  }
  return null;
}

// Spot-check probes — written into window.__sceneProbes for E2E verification.
export type SceneProbes = {
  tag: string;
  /** Position in the stage plan the world currently shows. */
  stageIndex: number;
  stageId: string;
  /**
   * What the current stage is for.
   *
   * Published because "no mobs on screen" and "this stage spawns no mobs" are indistinguishable
   * from a probe otherwise: a hunting stage whose mob sheets all failed to load also reports
   * `mobCount: 0`. The kind says which of the two a verifier is looking at without a screenshot.
   */
  stageKind: StageKind;
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
  diagnostics: string[];
  // Phase 6 additions:
  heightmap: number[];
  flatRunCount: number;
  obstacleCount: number;
  mobCount: number;
  /** Live state of the configured hunting-ground population director. */
  mobPopulation?: PopulationSnapshot;
  /** Stage-scoped floating combat text (FCT) presentation state. */
  combatText?: CombatTextSystemSnapshot;
  playerColumn: number;
  foregroundLayers: string[];
  sceneLayers: SceneLayerProbe[];
  platforms: GameplayPlatformProbe[];
  platformRoutes: GameplayPlatformRouteProbe[];
  ladders: GameplayLadderProbe[];
  fps?: FpsSnapshot;
  /** Consumer playback state. Track selection is global to the run, never to a map. */
  soundtrack?: SoundtrackSnapshot;
  // Phase 7 additions — side-channel for verifiers.
  player?: PlayerStateSnapshot;
  mobs?: ReturnType<Mob["snapshot"]>[];
  inventory?: ReturnType<InventoryHud["snapshot"]>;
  /** Whether the inventory panel itself is visible, separate from its slot contents. */
  inventoryVisible?: boolean;
  worldItems?: ReturnType<ItemSystem["snapshot"]>;
  portals?: ReturnType<PortalSystem["snapshot"]>;
  events?: { kind: string; t: number; data?: unknown }[];
  itemPalette?: { kind: string; name: string }[];
  /**
   * The hub, while the hub is the stage on screen.
   *
   * Absent on every hunting stage, including on a run that has a village, so a verifier reading
   * this key is always reading the town it is standing in rather than a stale description of one
   * it left. Everything a village capture is meant to show - that residents exist, where they
   * stand, which of them is in talking range, and what is currently on screen in the dialogue
   * panel - is here, so the village can be asserted without decoding a frame.
   */
  village?: {
    name: string;
    npcs: ReturnType<Npc["snapshot"]>[];
    dialogue: ReturnType<DialogueBox["snapshot"]>;
  };
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
  /** Position in the stage plan to open on. Defaults to the first stage. */
  stageIndex?: number;
};

/**
 * Everything a stage rebuild needs that does not change between stages.
 *
 * Travelling through a portal replaces the world, not the run's art, so the
 * loaded texture keys and measured alpha frames are captured once and reused.
 * Reloading them per stage would re-register every texture underneath the
 * animations already pointing at it.
 */
type StageBuildInputs = Readonly<{
  tileset: Readonly<{
    fillMaterialKey: string;
    surfaceMaterialKey: string;
    leftSideMaterialKey: string;
    rightSideMaterialKey: string;
    surfaceIntegrationKey: string;
    leftSideIntegrationKey: string;
    rightSideIntegrationKey: string;
  }> | null;
  obstacleCells: readonly {
    sheetIdx: number;
    cellIdx: number;
    w: number;
    h: number;
  }[];
  mobIdleKeys: readonly string[];
  mobHurtKeys: readonly string[];
  mobAttackKeys: readonly string[];
  mobAlphaFrames: readonly Readonly<{
    idle: readonly CellRect[];
    hurt: readonly CellRect[];
  }>[];
  ladderAssetLoaded: boolean;
  climbAssetLoaded: boolean;
  baseTerrainSeed: number;
  /**
   * Loaded idle-strip texture key per village slot, keyed by the manifest's own slot number.
   *
   * A map rather than an array indexed by position, because the slot is what names the published
   * artifact (`npc_<tag>_<slot>_idle.png`) and what the dialogue lines are ordered by. A slot
   * whose strip failed to load is simply absent, so the spawner skips that resident instead of
   * constructing one against a texture key Phaser has never seen.
   */
  villageNpcIdleKeys: ReadonlyMap<number, string>;
  /** Cells measured out of the village fixture sheet, in sheet order. */
  villageFixtureCells: readonly {
    cellIdx: number;
    w: number;
    h: number;
  }[];
}>;

type DialogueCharacterBinding = Readonly<{
  npcName: string;
  beats: readonly DialoguePresentationBeat[];
  portraitTextureKeys: DialoguePortraitTextureKeys;
}>;

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
  private automationStillActive = false;
  private automationStillPickup?: DroppedItem;
  private automationStillPortal?: Readonly<{
    portal: PortalSpec;
    x: number;
    y: number;
  }>;
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
  private stageIndex = 0;
  private levelCapabilities!: ScrollingDemoLevelCapabilities;
  /**
   * The stage index this run was asked to open on, before any book existed to clamp it against.
   *
   * Kept unclamped on purpose. Which stages a run *has* is decided by its manifest, which is not
   * read until `loadAll`, so clamping the request at construction time would clamp it against the
   * wrong book: a request for stage 3 on a village run is in range, but the provisional
   * no-village book would have already flattened it to 2 and the clamp is not reversible.
   */
  private readonly requestedStageIndex: number;
  /**
   * The stage order this run offers.
   *
   * Provisionally the no-village book so `create()` has something to name a stage with while the
   * manifest is still in flight; replaced once, in `loadAll`, before the first `buildStageWorld`.
   */
  private stageBook: readonly StagePlan[] = buildStageBook({
    hasVillage: false,
  });
  /** The run's village bible, or null when this run has no village. */
  private villageSpec: VillageSpec | null = null;
  private stageBuildInputs?: StageBuildInputs;
  private readonly heightmapOpts = Object.freeze({
    cols: COLS,
    minH: MIN_H,
    maxH: MAX_H,
  });
  private readonly stageHeightmapDigests = new Map<number, string>();
  private stageAdvancePending = false;
  private pendingStageIndex: number | null = null;
  private pendingArrivalEnd: PortalKind | null = null;
  private obstacleSprites: Phaser.GameObjects.Image[] = [];
  private portalEnterKeys: Phaser.Input.Keyboard.Key[] = [];
  private stageBanner?: Phaser.GameObjects.Text;
  private healthBar?: FloatingHealthBar;
  /** Every runtime role declared by the required current manifest. */
  private manifestRuntimeRoles: ReadonlySet<string> = new Set();

  /** Per-mob aggression archetypes published by the manifest, keyed by mob slot. */
  private combatAggressions: ReadonlyMap<number, string> = new Map();
  private originalConsoleError?: typeof console.error;
  private probes!: SceneProbes;
  private fpsProbe = new FpsProbe(30);
  private soundtrackPlayer?: DeterministicSoundtrackPlayer;
  private soundtrackGestureListener?: () => void;

  // Semantic screen/parallax layers, ordered by canonical depth. Current layers without a
  // verified repeat artifact may retain an overlap partner; foreground uses exactly one
  // TileSprite backed by either a verified period or the current prepared repeat texture.
  private sceneLayerSprites: {
    contract: SceneLayerContract;
    asset: SceneLayerAssetMetadata;
    sprite: Phaser.GameObjects.TileSprite;
    partner?: Phaser.GameObjects.TileSprite;
    seamOffset: number;
    imageRepeat: SceneLayerImageRepeatSelection | null;
  }[] = [];

  // Phase 7 systems.
  private player?: Player;
  private mobs: Mob[] = [];
  /** Optional current population authoring; null selects the static one-shot spawner. */
  private mobPopulationManifest: MobPopulationManifest | null = null;
  /** Stage-scoped population state. Disposed on every portal transition. */
  private mobPopulationDirector?: MobPopulationDirector;
  private mobPopulationMapId?: string;
  private readonly mobPopulationInstanceIds = new Map<Mob, string>();
  private nextMobPopulationInstance = 1;
  /** Optional current policy resolved once from the manifest; absence defaults on. */
  private combatTextManifest: CombatTextManifest =
    resolveCombatTextManifest(undefined);
  /** Stage-owned FCT renderer; recreated on every portal transition. */
  private combatText?: CombatTextSystem;
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
  /**
   * Scale reference per character texture key, as published by the recipe.
   */
  private readonly characterScaleReferences = new Map<string, ScaleReference>();
  /**
   * Scale reference per village slot, as published beside that resident's idle strip.
   *
   * Separate from `characterScaleReferences` because it is keyed differently - by slot, not by
   * texture key - and because the two are matched against each other rather than merged: a
   * villager's reference is only meaningful opposite the player's idle reference, which is what
   * makes the two sprites agree on screen.
   */
  private readonly villageNpcScaleReferences = new Map<number, ScaleReference>();
  private ladderRenderSprites: VerticalRenderSprite[] = [];
  private npcs: Npc[] = [];
  private dialogue?: DialogueBox;
  /**
   * Inventory visibility immediately before a conversation opened.
   *
   * Null means no conversation owns the HUD. A boolean is a visibility lease held by the open
   * dialogue: the inventory stays hidden for the whole lease, then returns to exactly the state
   * the player chose beforehand. This keeps the full-body portrait unobscured without turning a
   * locally hidden inventory back on when the conversation ends.
   */
  private dialogueInventoryWasVisible: boolean | null = null;
  /** Strictly parsed imports awaiting their all-four-assets load transaction. */
  private dialogueCharacterSpecs: readonly DialogueCharacterRuntimeSpec[] =
    Object.freeze([]);
  /** Rich presentation bound only after all four verified textures are available. */
  private readonly dialogueCharacterBindings = new Map<
    number,
    DialogueCharacterBinding
  >();
  /**
   * The villager whose conversation is on screen, or null when none is.
   *
   * Pinned for the whole conversation rather than re-resolved per frame. The player is frozen
   * while the panel is open so the nearest villager cannot change, but the camera can still move
   * during the automation encounter presentation, and a target that drifted mid-sentence would
   * hand the next line to somebody who never said the first one.
   */
  private speakingNpcSlot: number | null = null;
  /** Interact keys, read as edges each frame. `E` and `Enter`; never `Up`/`W` or `I`. */
  private interactKeys: Phaser.Input.Keyboard.Key[] = [];
  private eventLog: { kind: string; t: number; data?: unknown }[] = [];

  constructor(init: SceneInit) {
    super({ key: "StageScene" });
    this.tag = init.tag;
    this.transparencyPolicy = init.transparencyPolicy;
    this.automationMode = init.automationMode;
    this.requestedStageIndex = init.stageIndex ?? 0;
    this.stageIndex = normalizeStageIndex(
      this.stageBook,
      this.requestedStageIndex,
    );
    if (this.automationMode)
      this.automationClock = new GameplayAutomationClock();
  }

  create() {
    const openingPlan = stagePlanAt(this.stageBook, this.stageIndex);
    this.probes = {
      tag: this.tag,
      stageIndex: this.stageIndex,
      stageId: openingPlan.id,
      stageKind: openingPlan.kind,
      loadedAssetKeys: [],
      parallaxAlphaProbe: {},
      spriteAlphaProbe: {},
      cellExtractProbe: {},
      consoleErrors: [],
      diagnostics: [],
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
    this.bindPortalKeys();

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
      this.disposeMobPopulation();
      this.combatText?.dispose();
      this.combatText = undefined;
      // The dialogue panel outlives every stage - it belongs to the player's screen, not to a
      // town - so nothing before this point ever destroys it. Shutdown is where it ends.
      this.dialogue?.destroy();
      this.dialogue = undefined;
      this.releaseInteractInput();
      this.releaseSoundtrackGesture();
      this.soundtrackPlayer?.stop();
      this.soundtrackPlayer = undefined;
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

    // The interact edge is read before anything consumes it, and exactly once, so the key press
    // that ends a conversation cannot also open the next one in the same frame.
    const interactPressed = this.consumeInteractPress();
    // A conversation freezes the player rather than drawing a panel over a walking one. The
    // controller is not stepped at all, so there is no movement, no jump, and no attack to
    // suppress downstream - the only place an input could still reach the player is the swing
    // resolution below, which is gated on the same flag.
    const dialogueOpen = this.dialogue?.isOpen ?? false;
    if (dialogueOpen) this.suppressInventoryForDialogue();

    // Player drives the camera (TC-080).
    if (this.player) {
      if (!dialogueOpen) this.player.update(deltaMs, now);
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
        if (this.levelCapabilities.horizontalDeadZoneEnabled) {
          cam.scrollX = horizontalCameraScrollX({
            currentScrollX: cam.scrollX,
            targetX: px,
            zoom: cam.zoom,
            viewportWidth: cam.width,
            worldWidth: STAGE_W,
          });
        } else {
          cam.centerOnX(px);
        }
        cam.scrollY = this.levelCapabilities.verticalCameraTrackingEnabled
          ? verticalCameraScrollY({
              currentScrollY: cam.scrollY,
              footY: this.player.sprite.y,
              zoom: cam.zoom,
              viewportHeight: cam.height,
            })
          : 0;
      }
      if (!this.levelCapabilities.verticalCameraTrackingEnabled) cam.scrollY = 0;

      // Inventory toggle. Gated on the conversation too: the toggle is latched by a DOM
      // keydown listener rather than inside the controller, so freezing the controller does
      // not stop `I` from arriving - it only stops it from being read. Without this guard the
      // panel opens behind the dialogue box mid-sentence. The latch is cleared either way so a
      // press made during a conversation does not fire the moment it ends.
      if (this.player.inventoryToggleRequested && this.inventory) {
        if (dialogueOpen) {
          this.player.inventoryToggleRequested = false;
        } else {
          this.inventory.toggle();
          this.player.inventoryToggleRequested = false;
          this.logEvent("inventory-toggle", { visible: this.inventory.visible });
        }
      }

      // Mob -> player. Runs before the player's own swing so a mob that committed to a blow
      // lands it on the same frame the player attacks, rather than being pre-emptively killed by
      // a swing resolved earlier in the same tick. A trade should be a trade.
      //
      // Every mob is told where the player is each frame; the Mob class holds no reference to
      // the player, so its whole awareness is this one call and it stays unit-testable.
      {
        const health = this.player.healthState;
        const px3 = this.player.sprite.x;
        for (const m of this.mobs) {
          if (!m.isAlive()) continue;
          m.observePlayer(dialogueOpen ? null : px3, health.defeated);
          const strike = m.consumeStrike();
          if (!strike || strike.damage <= 0) continue;
          // Re-checked at the moment the blow lands, not when it was committed: backing out of
          // reach during the wind-up is how a player dodges, and it is the only thing that makes
          // the wind-up a warning rather than decoration.
          const profile = aggressionProfile(m.snapshot().aggression);
          if (Math.abs(m.sprite.x - this.player.sprite.x) > profile.strikeRangePx * 1.35) {
            this.logEvent("mob-strike-missed", { ladderIndex: m.ladderIndex });
            continue;
          }
          const resolution = this.player.takeDamage(
            strike.damage,
            now,
            strike.dirSign,
          );
          if (resolution.connected) {
            const playerBounds = this.player.sprite.getBounds();
            this.combatText?.showDamage({
              resolution,
              direction: "incoming",
              x: this.player.sprite.x,
              y: playerBounds.top - 18,
              nowMs: now,
            });
            this.logEvent("player-hurt", {
              ladderIndex: m.ladderIndex,
              damage: resolution.appliedAmount,
              hpLeft: resolution.hpAfter,
            });
            if (resolution.defeated) {
              this.logEvent("player-defeated", { ladderIndex: m.ladderIndex });
            }
          }
        }
      }

      // Attack collisions vs mobs. Skipped outright while a conversation is open: a swing that
      // was already in its hit window when the panel opened would otherwise land a frame later,
      // from a player the input gate has already frozen.
      if (!dialogueOpen && this.player.consumeAttackHit()) {
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
            const mobBounds = m.sprite.getBounds();
            this.combatText?.showDamage({
              resolution: r,
              direction: "outgoing",
              x: m.sprite.x,
              y: mobBounds.top - 18,
              nowMs: now,
            });
            this.logEvent("mob-hit", {
              ladderIndex: m.ladderIndex,
              damage: r.appliedAmount,
              hpLeft: r.hpLeft,
              died: r.died,
            });
            if (r.died) this.recordManagedMobDeath(m, now);
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

    // Villagers face, offer their prompt, and hold their conversation after the player has moved
    // and before the camera is resolved, so the prompt above a resident is placed against the
    // same player position the rest of this frame renders.
    this.updateVillage(interactPressed);

    // Resolve bounded scroll before screen-space layers and visibility probes
    // consume camera coordinates. Phaser repeats this in its render pass.
    cam.preRender();
    this.updateTerrainCulling(cam);
    this.updateVerticalCulling(cam);
    this.updateMobPopulation(now, cam);

    // Mobs.
    for (const m of this.mobs) {
      if (m.isAlive() || this.automationMode) m.update(deltaMs, now);
    }
    // A normal tween destroys a defeated body after its death fade. Managed stages may run for
    // hours, so retire those controller objects too instead of retaining one per historical kill.
    // Automation deliberately keeps its fixed-step corpse for encounter probes.
    if (this.mobPopulationDirector && !this.automationMode) {
      this.mobs = this.mobs.filter((mob) => mob.isAlive() || mob.sprite.active);
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

    // Portals. Both ends are live and travel is a deliberate press, so this
    // resolves either direction rather than watching one end-of-stage
    // tripwire that fires on contact.
    if (this.player && this.portal) {
      const activation = this.portal.update({
        nowMs: now,
        playerX: this.player.sprite.x,
        playerFootY: this.player.sprite.y,
        enterRequested: this.consumePortalEnterRequest(),
        shimmer: !this.automationMode,
      });
      if (activation) {
        this.requestStageTravel(activation.destinationIndex, activation.kind);
      }
    }

    // Health last among the readouts, because it is now anchored to the character: knockback
    // resolved in the combat exchange above moves the player, and a bar written before that
    // trails a frame behind the body it is attached to at exactly the moment it is being read.
    this.followHealthBar(now);

    // FCT samples the same explicit gameplay clock as combat. It is world-space actor feedback,
    // never a camera effect, and its snapshot makes the complete lifecycle observable in E2E.
    this.combatText?.update(now);
    if (this.combatText) this.probes.combatText = this.combatText.snapshot();

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
        this.probes.inventoryVisible = this.inventory.visible;
      }
      if (this.items) this.probes.worldItems = this.items.snapshot();
      if (this.portal) this.probes.portals = this.portal.snapshot();
      this.publishVillageProbe();
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

    // Travel last: the rebuild destroys the player, mobs, and portals that
    // everything above this line is still reading.
    if (this.pendingStageIndex !== null) {
      const destination = this.pendingStageIndex;
      this.pendingStageIndex = null;
      this.stageAdvancePending = false;
      this.buildStageWorld(destination);
      if (!this.automationMode) {
        this.showStageBanner(stagePlanAt(this.stageBook, destination));
      }
      const arrival = this.cameras.main;
      arrival.scrollY = 0;
      // Then finish the frame in the world that now exists. Probes read live
      // objects, but the layer pass caches its result, so leaving it behind
      // published one frame describing the new stage's camera against the old
      // stage's parallax phase.
      arrival.preRender();
      this.updateTerrainCulling(arrival);
      this.updateVerticalCulling(arrival);
      this.updateSceneLayerTransforms(arrival, presentation.foregroundVisible);
      // The bar outlived the teardown but its anchor did not. Left alone it would spend the
      // arrival frame hanging over the spot in the new stage that matches where the departing
      // player stood in the old one.
      this.followHealthBar(now);
    }
  }

  /**
   * Anchor the health bar under whichever player currently exists.
   *
   * Reads the sprite rather than being handed a position, because the two callers reach it at
   * different points - once at the end of a normal frame, once after a stage rebuild has
   * replaced the player object outright - and the only thing both can agree on is "wherever the
   * player is now". A frame with no player at all is a torn-down world, and the bar simply holds
   * its last position for the rest of it.
   */
  private followHealthBar(now: number): void {
    if (!this.healthBar || !this.player) return;
    const health = this.player.healthState;
    this.healthBar.update({
      hp: health.hp,
      maxHp: health.maxHp,
      invulnerable: now < health.invulnerableUntilMs,
      actorX: this.player.sprite.x,
      actorFootY: this.player.sprite.y,
    });
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
          entry.imageRepeat,
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
      diagnostics: [...new Set(this.probes.diagnostics)],
      assetKeys: this.probes.loadedAssetKeys,
      stageIndex: this.stageIndex,
      stageId: stagePlanAt(this.stageBook, this.stageIndex).id,
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
        bounds: this.inventory?.bounds() ?? null,
        slots: this.inventory?.snapshot() ?? [],
      },
      worldItems: this.items?.snapshot() ?? [],
      encounter: this.automationEncounterProbe(),
      portals: this.portal?.snapshot() ?? [],
      presentation: gameplayAutomationPresentation(clock.frame),
      combatText: this.combatText?.snapshot(),
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
    const mobEntity = this.automationFocusMob();
    const player = playerSprite
      ? gameplayWorldBounds(playerSprite.getBounds())
      : null;
    const mob = mobEntity ? mobEntity.snapshot().renderBounds : null;
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
    try {
      if (clock.frame === 0) this.restoreAutomationStillCheckpoint();
      const frame = clock.advance();
      this.pendingAutomationFrame = frame;
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
    this.restoreAutomationStillCheckpoint();
    this.player?.resetAutomationState();
    for (const mob of this.mobs) mob.resetAutomationState();
    const playerX = this.player?.sprite.x ?? 0;
    const still = gameplayStillComposition({
      platforms: this.verticalWorld.platforms,
      ladders: this.verticalWorld.ladders.map((ladder) =>
        ladderVisualBounds(ladder),
      ),
    });
    if (still) {
      this.stageAutomationStillCheckpoint(still);
      this.cameras.main.setZoom(still.camera.zoom);
      this.cameras.main.scrollX = still.camera.scrollX;
      this.cameras.main.scrollY = still.camera.scrollY;
    } else {
      this.cameras.main.setZoom(1);
      this.cameras.main.centerOnX(playerX);
      this.cameras.main.scrollY = 0;
    }
    this.cameras.main.preRender();
    this.updateTerrainCulling(this.cameras.main);
    this.updateVerticalCulling(this.cameras.main);
    this.updateSceneLayerTransforms(this.cameras.main, true);
    const renderer = this.game.renderer;
    this.automationClock.markReady();
    this.logEvent("assets-ready", {
      count: this.probes.loadedAssetKeys.length,
    });
    // Asset requests are complete before frame 0. Stop rAF before publishing
    // readiness; all subsequent full-game updates come through the hook.
    this.game.loop.sleep();
    renderer.preRender();
    this.game.scene.render(renderer);
    renderer.postRender();
  }

  private stageAutomationStillCheckpoint(
    composition: GameplayStillComposition,
  ): void {
    const player = this.player;
    const mob = this.mobs.find((candidate) => candidate.isAlive());
    const portal = this.portal?.portals.find(
      (candidate) => candidate.kind === "entry",
    );
    if (!player || !mob || !portal || !this.items) {
      throw new Error(
        "gameplay still checkpoint requires player, live mob, portal, and items",
      );
    }
    player.sprite.setPosition(composition.player.x, composition.player.y);
    for (const candidate of this.mobs) candidate.setVisible(candidate === mob);
    mob.sprite.setPosition(composition.mob.x, composition.mob.y);
    this.automationStillPortal = Object.freeze({
      portal,
      x: portal.x,
      y: portal.y,
    });
    portal.x = composition.portal.x;
    portal.y = composition.portal.y;
    portal.sprite.setPosition(composition.portal.x, composition.portal.y);

    const pickup = this.items.drop(
      composition.pickup.x,
      composition.pickup.y,
      0,
    );
    if (!pickup) {
      throw new Error("gameplay still checkpoint could not stage a pickup");
    }
    pickup.settled = true;
    pickup.sprite.setPosition(composition.pickup.x, composition.pickup.y);
    pickup.sprite.setData("groundY", composition.pickup.y);
    this.automationStillPickup = pickup;
    this.automationStillActive = true;
  }

  private restoreAutomationStillCheckpoint(): void {
    if (!this.automationStillActive) return;
    this.player?.resetAutomationState();
    for (const mob of this.mobs) mob.resetAutomationState();
    if (this.automationStillPortal) {
      const { portal, x, y } = this.automationStillPortal;
      portal.x = x;
      portal.y = y;
      portal.sprite.setPosition(x, y);
    }
    if (this.automationStillPickup) {
      this.items?.remove(this.automationStillPickup);
    }
    this.automationStillPortal = undefined;
    this.automationStillPickup = undefined;
    this.automationStillActive = false;
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

    // ---------- Run manifest (fetched exactly once) ----------
    // Per-sheet scale references, optional systems, and stage ownership all come from this one
    // document. Reading the required manifest once keeps every consumer on the same validated
    // bytes; a missing or malformed manifest fails the boot transaction.
    const manifest = await this.fetchRunManifest(u, tag);
    const horizontalRepeats = horizontalImageRepeats(manifest);
    this.manifestRuntimeRoles = new Set(
      manifestRuntimeAssets(manifest).map(manifestRuntimeSlot).filter(Boolean),
    );
    this.villageSpec = parseVillageManifest(manifest);
    this.loadCharacterScaleReferences(manifest);
    this.assertMeasuredActorClosure(spec);
    this.dialogueCharacterBindings.clear();
    const dialogueCharacters = parseDialogueCharactersManifest(manifest);
    this.dialogueCharacterSpecs = dialogueCharacters.characters;
    this.combatTextManifest = resolveCombatTextManifest(manifest);
    if (this.combatTextManifest.enabled) {
      await loadBrowserCombatTextFont();
    }
    // The book is built here and nowhere else: this is the first moment the scene knows whether
    // the run has a village or an authored map order, and the last moment before anything reads
    // a stage plan. Static geometry remains this adapter's registry; the map book supplies only
    // durable identity, display text, order, and game-global soundtrack references.
    const mapBook = parseMapBookManifest(manifest);
    this.stageBook = buildStageBook({
      hasVillage: this.villageSpec !== null,
      mapBook,
    });
    const mobPopulationBlock = manifestMobPopulation(manifest);
    this.mobPopulationManifest =
      mobPopulationBlock === null
        ? null
        : parseMobPopulationManifest(mobPopulationBlock);
    assertContinuousPopulationCoverage(
      this.stageBook,
      this.mobPopulationManifest?.maps.map((map) => map.map_id) ?? [],
    );
    if (this.mobPopulationManifest) {
      const huntingMapIds = new Set(
        this.stageBook.filter((stage) => stage.kind === "hunting").map((stage) => stage.id),
      );
      for (const map of this.mobPopulationManifest.maps) {
        if (!huntingMapIds.has(map.map_id)) {
          throw new Error(
            `mob population map_id ${JSON.stringify(map.map_id)} is not a hunting stage`,
          );
        }
      }
    }
    this.stageIndex = normalizeStageIndex(
      this.stageBook,
      this.requestedStageIndex,
    );
    this.installSoundtrack(
      manifest,
      u,
      stagePlanAt(this.stageBook, this.stageIndex).soundtrackTrackIds,
    );

    // ---------- Heightmap (deterministic from tag or explicit run seed) ----------
    if (
      spec.terrain_seed !== undefined &&
      !Number.isSafeInteger(spec.terrain_seed)
    ) {
      throw new Error("world spec terrain_seed must be a safe integer");
    }
    const baseTerrainSeed = spec.terrain_seed ?? heightmapSeedForTag(tag);
    const heights = this.stageHeights(this.stageIndex, baseTerrainSeed);
    this.heights = heights;
    this.probes.heightmap = heights;
    if (this.automationMode) {
      // Every stage's digest is taken once, here, so a portal can swap worlds
      // synchronously later without leaving the automation probe describing
      // the terrain the player just left.
      for (let index = 0; index < this.stageBook.length; index += 1) {
        this.stageHeightmapDigests.set(
          index,
          await heightmapSha256(this.stageHeights(index, baseTerrainSeed)),
        );
      }
      this.heightmapDigest = this.stageHeightmapDigests.get(this.stageIndex) ?? null;
    }
    // Ladder and climb art is loaded once for the whole run, not once per stage, so the plan
    // consulted here is the first one that actually lays a platform graph rather than whichever
    // stage the run opens on. A run that opens in the village has no vertical geometry to prepare
    // for, and asking the village would leave every hunting ground it leads to with no ladder
    // texture and no climb strip - the whole platform feature silently rolled back.
    const verticalAssetStage = this.verticalAssetStageIndex();
    const verticalCandidate =
      verticalAssetStage === null
        ? null
        : this.selectStageVerticalWorld(
            this.stageHeights(verticalAssetStage, baseTerrainSeed),
            verticalAssetStage,
          );
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
          // Trimmed, so LADDER_VISUAL_WIDTH sizes the rails rather than the canvas they sit in.
          await loadTrimmedSprite(
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
        recordError: (message) => this.recordDiagnostic(message),
      });

    // ---------- Semantic screen/parallax layers ----------
    const layersById = new Map(spec.layers.map((layer) => [layer.id, layer]));
    const resolvedLayers = resolveSceneLayerStack(
      spec.layers,
      SCENE_LAYER_CONTEXT,
    );
    // Current fallback overlap for an optional deferred repeat. A verified repeat bypasses every
    // fade/overlap path and uses its producer-declared exact period instead.
    const FADE_PX = 256;
    for (const sourceContract of resolvedLayers) {
      const layer = layersById.get(sourceContract.id);
      if (!layer) throw new Error(`${sourceContract.id} has no world-layer source`);
      const file = `layer_${tag}_${layer.id}.png`;
      const key = `layer_${layer.id}`;
      const repeatArtifact = horizontalRepeats.get(file);
      const imageRepeat: SceneLayerImageRepeatSelection | null = repeatArtifact
        ? Object.freeze({
            schemaVersion: 2,
            axis: "x",
            decision: repeatArtifact.decision,
            sourcePath: repeatArtifact.sourcePath,
            repeatUnitPath: repeatArtifact.repeatUnitPath,
            periodPx: repeatArtifact.periodPx,
          })
        : null;
      const contract = imageRepeat
        ? withVerifiedHorizontalRepeat(sourceContract)
        : sourceContract;
      try {
        const loaded = imageRepeat
          ? contract.kind === "near-foreground"
            ? await loadVerifiedForegroundRepeat(
                u(imageRepeat.repeatUnitPath),
                key,
                imageRepeat.periodPx,
                this.textures,
              )
            : await loadVerifiedRepeatLayer(
                u(imageRepeat.repeatUnitPath),
                key,
                layer.opaque,
                imageRepeat.periodPx,
                this.textures,
              )
          : contract.kind === "near-foreground"
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
          imageRepeat,
        });
      } catch (e) {
        this.recordErr(e);
      }
    }

    // ---------- Tileset ----------
    let tilesetKeys: StageBuildInputs["tileset"] = null;
    try {
      const tileset = await loadTileset(
        u(`tileset_${tag}.png`),
        `tileset`,
        this.textures,
        this.transparencyPolicy,
      );
      this.probes.loadedAssetKeys.push(`tileset`);
      tilesetKeys = {
        fillMaterialKey: tileset.fillMaterialKey,
        surfaceMaterialKey: tileset.surfaceMaterialKey,
        leftSideMaterialKey: tileset.leftSideMaterialKey,
        rightSideMaterialKey: tileset.rightSideMaterialKey,
        surfaceIntegrationKey: tileset.surfaceIntegrationKey,
        leftSideIntegrationKey: tileset.leftSideIntegrationKey,
        rightSideIntegrationKey: tileset.rightSideIntegrationKey,
      };
    } catch (e) {
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

    // ---------- Mobs (idle + hurt + attack + concept) ----------
    const mobIdleKeys: string[] = [];
    const mobHurtKeys: string[] = [];
    // Empty string where a run drew no attack strip. An undirected run never draws one, so a
    // missing sheet here is the normal case rather than a fault - the Mob still swings, it just
    // has no dedicated pose to play while doing it.
    const mobAttackKeys: string[] = [];
    const mobAlphaFrames: Array<{
      idle: readonly CellRect[];
      hurt: readonly CellRect[];
    }> = [];
    for (let i = 0; i < spec.mobs.length; i++) {
      let idleCells: readonly CellRect[] = [];
      let hurtCells: readonly CellRect[] = [];
      let attackCells: readonly CellRect[] = [];
      const idleKey = `mob_${i}_idle`;
      try {
        const loaded = await loadFrameStrip(
          u(`mob_${tag}_${i}_idle.png`),
          idleKey,
          4,
          this.textures,
          this.transparencyPolicy,
        );
        idleCells = loaded.cells;
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
      const attackKey = `mob_${i}_attack`;
      // The required current manifest is authoritative. A missing optional attack role is not
      // probed by filename, avoiding a predictable 404 and an invented asset contract.
      const attackDeclared = this.manifestRuntimeRoles.has(`mob-${i}-attack`);
      try {
        if (!attackDeclared) throw new Error("no attack strip in this run");
        const loaded = await loadFrameStrip(
          u(`mob_${tag}_${i}_attack.png`),
          attackKey,
          4,
          this.textures,
          this.transparencyPolicy,
        );
        attackCells = loaded.cells;
        this.probes.loadedAssetKeys.push(attackKey);
        mobAttackKeys.push(attackKey);
        // Played once per swing rather than looped: an attack that repeats reads as a creature
        // flailing, and the wind-up is timed by the combat system, not by the animation.
        const attackAnimKey = `${attackKey}_anim`;
        if (!this.anims.exists(attackAnimKey)) {
          this.anims.create({
            key: attackAnimKey,
            frames: [0, 1, 2, 3].map((f) => ({ key: attackKey, frame: f })),
            frameRate: 12,
            repeat: 0,
          });
        }
      } catch {
        // Expected on every run that drew no attack strip. Deliberately not recorded as a scene
        // error: an undirected run is not faulty for lacking artwork it never generated.
        mobAttackKeys.push("");
      }
      const hurtKey = `mob_${i}_hurt`;
      try {
        const loaded = await loadFrameStrip(
          u(`mob_${tag}_${i}_hurt.png`),
          hurtKey,
          4,
          this.textures,
          this.transparencyPolicy,
        );
        hurtCells = loaded.cells;
        this.probes.loadedAssetKeys.push(hurtKey);
        mobHurtKeys.push(hurtKey);
      } catch (e) {
        this.recordErr(e);
        mobHurtKeys.push("");
      }
      // Attack frames join the envelope: a lunging creature is the widest it ever gets, and
      // `mobWorldLane` clamps the lane so that envelope stays inside the world.
      mobAlphaFrames.push({
        idle: idleCells,
        hurt: [...hurtCells, ...attackCells],
      });
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
    // Player hurt is a producer-owned optional current role. A declaration makes a missing or
    // invalid strip a real load failure instead of silently using an unrelated pose.
    if (this.manifestRuntimeRoles.has("character-hurt")) {
      try {
        await loadFrameStrip(
          u(`character_${tag}_hurt.png`),
          `character_hurt`,
          4,
          this.textures,
          this.transparencyPolicy,
        );
        this.probes.loadedAssetKeys.push(`character_hurt`);
      } catch (e) {
        this.recordErr(e);
      }
    }

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

    // Health travels with the player exactly as the inventory does: built once, never
    // rebuilt per stage, so walking through a portal does not blink the bar. It is anchored to
    // the character rather than to the viewport, so the arriving player's own position is what
    // places it on the far side - see `followHealthBar`.
    this.healthBar = new FloatingHealthBar(
      this,
      PLAYER_MAX_HP,
      PLAYER_HEALTH_BAR_STYLE,
    );

    // The inventory HUD is the player's, not the stage's, so it is built once
    // and travels with them between worlds.
    this.inventory = new InventoryHud({
      scene: this,
      panelKey: "inventory",
      itemsKey: "items",
      itemFrameKey: (idx) => `item_${idx % 8}`,
      viewW: VIEW_W,
      viewH: VIEW_H,
    });

    // ---------- Village (residents + fixtures) ----------
    const { villageNpcIdleKeys, villageFixtureCells } =
      await this.loadVillageAssets(u, tag);

    // Concept (purely for completeness; not displayed).
    try {
      await loadOpaqueSprite(u(`concept_${tag}.png`), `concept`, this.textures);
      this.probes.loadedAssetKeys.push(`concept`);
    } catch (e) {
      this.recordErr(e);
    }

    this.stageBuildInputs = Object.freeze({
      tileset: tilesetKeys,
      obstacleCells: Object.freeze([...obstacleCells]),
      mobIdleKeys: Object.freeze([...mobIdleKeys]),
      mobHurtKeys: Object.freeze([...mobHurtKeys]),
      mobAttackKeys: Object.freeze([...mobAttackKeys]),
      mobAlphaFrames: Object.freeze(
        mobAlphaFrames.map((frames) => Object.freeze({ ...frames })),
      ),
      ladderAssetLoaded,
      climbAssetLoaded,
      baseTerrainSeed,
      villageNpcIdleKeys,
      villageFixtureCells,
    });
    this.buildStageWorld(this.stageIndex);
  }

  // ---------- Stage lifecycle ----------

  /**
   * Deterministic heightmap for one stage of the plan.
   *
   * A village is level ground, and level ground is one case the seeded builder cannot express.
   * `buildHeightmapFromSeed` floors its range at `Math.max(1, maxH - minH)`, so with
   * `minH === maxH` it still draws its opening height from a two-value range before any clamp to
   * `maxH` applies: measured on this build, seed `0x27d4eb2f` with `minH = maxH = 2` returns a
   * leading run of height 3 that only settles to 2 at the first drift. That is a ledge across the
   * mouth of the town rather than a flat street, so the flat case is built here instead - and
   * built as a constant, not as a near-constant that happens to look level on most seeds.
   */
  private stageHeights(stageIndex: number, baseTerrainSeed: number): number[] {
    const plan = stagePlanAt(this.stageBook, stageIndex);
    if (plan.terrain === "flat") {
      return new Array<number>(COLS).fill(VILLAGE_TERRAIN_HEIGHT_TILES);
    }
    return buildHeightmapFromSeed(
      stageTerrainSeed(baseTerrainSeed, plan),
      this.heightmapOpts,
    );
  }

  /**
   * The stage whose platform graph decides whether ladder and climb art is loaded.
   *
   * Null only for a book with no vertical stage at all, which no book this build produces
   * contains - the village is always followed by the hunting grounds - but the caller has to
   * handle it anyway rather than index a `findIndex` result that can be -1.
   */
  private verticalAssetStageIndex(): number | null {
    if (stagePlanAt(this.stageBook, this.stageIndex).vertical) {
      return this.stageIndex;
    }
    const index = this.stageBook.findIndex((plan) => plan.vertical);
    return index < 0 ? null : index;
  }

  /** Pick the stage's platform graph outside the opening encounter's columns. */
  private selectStageVerticalWorld(
    heights: readonly number[],
    stageIndex: number,
  ) {
    // The opening encounter owns columns 0..13. Vertical geometry is selected
    // before prop/mob placement. Selection rejects caller occupancy across
    // the complete raster/collision footprint (start-1 through end), then
    // reserves that same interval from both spawners.
    const openingEncounterColumns = new Set(
      Array.from({ length: 14 }, (_, column) => column),
    );
    return selectDemoVerticalWorld({
      heights,
      tilePixels: TILE_PX,
      baselineY: GROUND_BASELINE_Y,
      worldWidth: STAGE_W,
      reservedColumns: openingEncounterColumns,
      layout: stagePlanAt(this.stageBook, stageIndex).layout,
    });
  }

  /**
   * Tear down the current world and lay out `stageIndex` in its place.
   *
   * Textures, animations, and the inventory survive; terrain, platforms,
   * props, mobs, drops, portals, and the player controller do not. Rebuilding
   * in place rather than restarting the scene keeps every already-registered
   * texture pointing at the frames its animations were built from.
   */
  private buildStageWorld(stageIndex: number): void {
    const inputs = this.stageBuildInputs;
    if (!inputs) throw new Error("stage world requires loaded build inputs");
    this.stageIndex = normalizeStageIndex(this.stageBook, stageIndex);
    const plan = stagePlanAt(this.stageBook, this.stageIndex);
    this.levelCapabilities = scrollingDemoLevelCapabilities(plan.levelProfile);
    if (plan.soundtrackTrackIds !== undefined) {
      this.soundtrackPlayer?.setTrackPool(plan.soundtrackTrackIds);
    }

    this.teardownStageWorld();

    const heights = this.stageHeights(this.stageIndex, inputs.baseTerrainSeed);
    this.heights = heights;
    this.probes.heightmap = heights;
    this.probes.stageIndex = this.stageIndex;
    this.probes.stageId = plan.id;
    this.probes.stageKind = plan.kind;
    // A village probe describes the town the player is standing in, so leaving one behind on a
    // hunting stage would have a verifier assert residents against a world that has none.
    if (plan.kind !== "village") delete this.probes.village;
    if (this.automationMode) {
      this.heightmapDigest =
        this.stageHeightmapDigests.get(this.stageIndex) ?? null;
    }

    // A stage that declares no vertical geometry gets no selection at all rather than a selection
    // that is then rolled back. `verticalFeatureAfterAssetLoad(null, ...)` is the empty world, so
    // the reserved-column set, the platform list, and the ladder list are all genuinely empty -
    // nothing downstream is handed a graph belonging to a stage the player is not on.
    const verticalCandidate = plan.vertical
      ? this.selectStageVerticalWorld(heights, this.stageIndex)
      : null;
    const inactiveVertical = verticalFeatureAfterAssetLoad(
      verticalCandidate,
      false,
    );
    this.verticalWorld = inactiveVertical.world;
    this.verticalRoutes = inactiveVertical.routes;
    this.verticalReservedColumns = new Set(inactiveVertical.reservedColumns);

    const tileset = inputs.tileset;
    if (tileset) {
      try {
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
      } catch (e) {
        this.recordErr(e);
      }
      if (verticalCandidate) {
        try {
          const activated = activateVerticalFeatureTransaction({
            selected: verticalCandidate,
            ladderAssetLoaded: inputs.ladderAssetLoaded,
            climbAssetLoaded: inputs.climbAssetLoaded,
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
              this.verticalReservedColumns = new Set(selection.reservedColumns);
            },
          });
          if (activated && !this.probes.loadedAssetKeys.includes("ladder")) {
            this.probes.loadedAssetKeys.push("ladder", "character_climb");
          }
        } catch (error) {
          this.recordErr(error);
        }
      }
    }

    if (plan.kind === "village") {
      // Residents first, fixtures around them: a stall painted on a villager's column covers the
      // name label and the talk prompt, and the resident is the reason the stage exists.
      const npcColumns = this.spawnVillageNpcs(
        heights,
        inputs.villageNpcIdleKeys,
      );
      this.placeVillageFixtures(
        heights,
        inputs.villageFixtureCells,
        npcColumns,
      );
      // Stated rather than left over from the previous stage. The hub spawns no mobs at all, and
      // a stale count would read as "the mob sheets failed to load" to anything checking probes.
      this.probes.mobCount = 0;
    } else {
      this.placeObstacles(heights, [...inputs.obstacleCells]);
      if (this.mobPopulationManifest) {
        this.initializeMobPopulation(
          plan,
          heights,
          inputs.baseTerrainSeed,
        );
      } else {
        this.spawnMobs(
          heights,
          [...inputs.mobIdleKeys],
          [...inputs.mobHurtKeys],
          [...inputs.mobAttackKeys],
          inputs.mobAlphaFrames,
          plan.mobRunStride,
        );
      }
    }

    this.items = new ItemSystem({
      scene: this,
      tilePx: TILE_PX,
      baselineY: GROUND_BASELINE_Y,
      heightFn: (col) => terrainHeightAtColumn(this.heights, col),
      itemFrameKey: (idx) => `item_${idx % 8}`,
      itemTextureKey: "items",
    });

    this.portal = new PortalSystem({
      scene: this,
      portalKey: "portal",
      tilePx: TILE_PX,
      baselineY: GROUND_BASELINE_Y,
      heightFn: (col) => terrainHeightAtColumn(this.heights, col),
      stageWidthPx: STAGE_W,
      destinations: {
        entry:
          portalDestination(this.stageBook, this.stageIndex, "entry")?.index ??
          null,
        exit:
          portalDestination(this.stageBook, this.stageIndex, "exit")?.index ??
          null,
      },
    });

    this.spawnPlayer(heights);
    if (this.mobPopulationDirector) {
      // Materialize the first deterministic warm-start batch before frame zero. Production gets
      // populated stage entry, and automation can stage its still checkpoint without advancing
      // the sleeping gameplay clock. Subsequent batches remain governed by authored cadence.
      this.cameras.main.preRender();
      this.updateMobPopulation(0, this.cameras.main);
    }
    // Presentation feedback is the final stage-scoped dependency: it consumes authoritative
    // player/mob damage resolutions and never participates in terrain, traversal, or population.
    this.combatText = new CombatTextSystem({
      scene: this,
      enabled: this.combatTextManifest.enabled,
      reducedMotion: browserPrefersReducedMotion(),
    });
    this.probes.combatText = this.combatText.snapshot();
    this.logEvent("stage-enter", {
      stageIndex: this.stageIndex,
      stageId: plan.id,
      layout: plan.layout,
    });
  }

  /** Destroy everything a stage owns, leaving textures and the HUD alone. */
  private teardownStageWorld(): void {
    this.disposeMobPopulation();
    this.combatText?.dispose();
    this.combatText = undefined;
    if (this.probes) delete this.probes.combatText;
    this.player?.destroy();
    this.player = undefined;
    for (const mob of this.mobs) mob.destroy();
    this.mobs = [];
    // Residents belong to the town, not to the run: a villager, their name label, and their talk
    // prompt are three world-space objects each, and leaving them behind would carry twelve
    // sprites of a settlement into the hunting ground on the far side of the portal.
    for (const npc of this.npcs) npc.destroy();
    this.npcs = [];
    // The panel itself survives - it is screen furniture, like the inventory - but the
    // conversation does not. A box left open would keep the arriving player's input gated behind
    // a villager who no longer exists on this stage.
    this.closeDialogue();
    this.items?.clearAll();
    this.items = undefined;
    this.portal?.destroy();
    this.portal = undefined;
    for (const sprite of this.obstacleSprites) sprite.destroy();
    this.obstacleSprites = [];
    this.clearVerticalRendering();
    this.automationStillPortal = undefined;
    this.automationStillPickup = undefined;
    this.automationEncounterTargetMob = undefined;
    this.pendingAutomationEncounter = undefined;
    this.automationLastDropBounds = undefined;
    this.automationPickupBounds = undefined;
  }

  /**
   * Travel to another stage through a portal.
   *
   * Deferred to the end of the frame: the rebuild destroys the player and mob
   * objects the rest of `update` is still walking.
   */
  /**
   * Bind the portal's enter key.
   *
   * The scene owns it rather than the player: stepping through a door is not a
   * movement state, and routing it through the controller would put a
   * stage-lifecycle concern inside the support machine. Both the arrow and the
   * WASD key answer, matching every other action in this preview.
   */
  private bindPortalKeys(): void {
    const keyboard = this.input.keyboard;
    if (!keyboard) return;
    this.portalEnterKeys = [
      keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.UP),
      keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.W),
    ];
  }

  /** True once per fresh press, so holding the key cannot re-enter a portal. */
  private consumePortalEnterRequest(): boolean {
    let pressed = false;
    for (const key of this.portalEnterKeys) {
      if (Phaser.Input.Keyboard.JustDown(key)) pressed = true;
    }
    return pressed;
  }

  private requestStageTravel(destinationIndex: number, via: string): void {
    if (this.stageAdvancePending) return;
    this.stageAdvancePending = true;
    const plan = stagePlanAt(
      this.stageBook,
      normalizeStageIndex(this.stageBook, destinationIndex),
    );
    this.logEvent("stage-advance", {
      portal: via,
      fromStageIndex: this.stageIndex,
      toStageIndex: plan.index,
      toStageId: plan.id,
    });
    // eslint-disable-next-line no-console
    console.log(`[stage-advance] portal entered: ${via} -> ${plan.id}`);
    if (typeof window !== "undefined") {
      try {
        window.dispatchEvent(
          new CustomEvent("stage-advance", {
            detail: {
              portal: via,
              tag: this.tag,
              fromStageIndex: this.stageIndex,
              toStageIndex: plan.index,
              toStageId: plan.id,
            },
          }),
        );
      } catch {}
    }
    this.pendingStageIndex = plan.index;
    // Leaving by the forward end puts the player at the next stage's entry;
    // going back puts them at the previous stage's exit.
    this.pendingArrivalEnd = via === "exit" ? "entry" : "exit";
  }

  /** Show the arriving stage's name briefly so travel is legible on screen. */
  private showStageBanner(plan: StagePlan): void {
    this.stageBanner?.destroy();
    const banner = this.add.text(
      VIEW_W / 2,
      64,
      `${plan.index + 1}/${this.stageBook.length}  ${plan.name}`,
      {
        fontFamily: "monospace",
        fontSize: "28px",
        color: "#f4f4f4",
        backgroundColor: "#000000a0",
        padding: { x: 16, y: 8 },
      },
    );
    banner.setOrigin(0.5, 0);
    banner.setScrollFactor(0);
    banner.setDepth(SCENE_CONTENT_DEPTH.hud);
    this.stageBanner = banner;
    this.time.delayedCall(2200, () => {
      if (this.stageBanner === banner) {
        banner.destroy();
        this.stageBanner = undefined;
      }
    });
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

  /** Fetch the required current manifest and reject missing or malformed runs. */
  private async fetchRunManifest(
    u: AssetUrlFn,
    tag: string,
  ): Promise<Record<string, unknown>> {
    const url = u(`manifest_${tag}.json`);
    return fetchCurrentRunManifest(url, tag);
  }

  /**
   * Arms soundtrack playback for the next real pointer or keyboard gesture.
   *
   * Audio is omitted from automation. The current catalog requires the opening map's pool, then
   * `buildStageWorld` updates that pool during portal travel without rebuilding the player.
   */
  private installSoundtrack(
    manifest: unknown,
    u: AssetUrlFn,
    openingTrackIds?: readonly string[],
  ): void {
    const soundtrack = parseSoundtrackForMapPool(manifest, openingTrackIds);
    if (this.automationMode || typeof Audio === "undefined") return;
    if (!soundtrack) return;

    const player = new DeterministicSoundtrackPlayer({
      tracks: soundtrack.tracks,
      ...(openingTrackIds === undefined ? {} : { trackIds: openingTrackIds }),
      seed: `${this.tag}\0game-soundtrack-v2`,
      transport: createBrowserSoundtrackTransport((track) => u(track.path)),
      onStateChange: (snapshot) => {
        this.probes.soundtrack = snapshot;
      },
    });
    this.soundtrackPlayer = player;
    this.probes.soundtrack = player.snapshot();

    const begin = () => {
      // Remove both routes before playback. Only the event currently on the
      // stack may unlock media, and a later second gesture must not restart it.
      this.releaseSoundtrackGesture();
      player.beginFromPlayerGesture();
    };
    this.soundtrackGestureListener = begin;
    this.input.once(Phaser.Input.Events.POINTER_DOWN, begin);
    this.input.keyboard?.once("keydown", begin);
  }

  private releaseSoundtrackGesture(): void {
    const listener = this.soundtrackGestureListener;
    if (!listener) return;
    this.input.off(Phaser.Input.Events.POINTER_DOWN, listener);
    this.input.keyboard?.off("keydown", listener);
    this.soundtrackGestureListener = undefined;
  }

  /**
   * Read published scale references out of an already-fetched run manifest.
   *
   * The measurement is part of the required v7 runtime-asset contract. `manifest.ts` owns the
   * public boundary; this adapter only translates its validated runtime roles into texture keys
   * and village slots.
   */
  private loadCharacterScaleReferences(manifest: Record<string, unknown>): void {
    const slots: Readonly<Record<string, string>> = {
      "character-idle": "character_idle",
      "character-walk": "character_walk",
      "character-run": "character_run",
      "character-jump": "character_jump",
      "character-crawl": "character_crawl",
      "character-climb": "character_climb",
      "character-attack": "character_attack",
      "character-hurt": "character_hurt",
    };
    this.characterScaleReferences.clear();
    this.villageNpcScaleReferences.clear();
    for (const [role, reference] of runtimeScaleReferences(manifest)) {
      const key = slots[role];
      if (key) {
        this.characterScaleReferences.set(key, reference);
        continue;
      }
      // The village's residents publish their references through the same list under
      // `village-npc-<slot>-idle`, which is the entire reason an NPC can be drawn at the player's
      // apparent size instead of at a guessed pixel height.
      const npcSlot = villageNpcDrawnSlot(role);
      if (npcSlot !== null) this.villageNpcScaleReferences.set(npcSlot, reference);
    }
  }

  /** Reject a current run whose world or optional village lacks a measured actor role. */
  private assertMeasuredActorClosure(spec: WorldSpec): void {
    for (let slot = 0; slot < spec.mobs.length; slot += 1) {
      for (const state of ["idle", "hurt"] as const) {
        const role = `mob-${slot}-${state}`;
        if (!this.manifestRuntimeRoles.has(role)) {
          throw new Error(`current scrolling manifest requires measured runtime role ${role}`);
        }
      }
    }
    const village = this.villageSpec;
    if (!village) return;
    for (const npc of village.npcs) {
      const role = `village-npc-${npc.slot}-${village.render.state}`;
      if (!this.villageNpcScaleReferences.has(npc.slot)) {
        throw new Error(`current scrolling manifest requires measured runtime role ${role}`);
      }
    }
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
      this.obstacleSprites.push(img);
      placed++;
    }
    this.probes.obstacleCount = placed;
  }

  // ---------- Mob spawning ----------

  /** Start one stage-scoped population director from the authored map and terrain. */
  private initializeMobPopulation(
    plan: StagePlan,
    heights: number[],
    baseTerrainSeed: number,
  ): void {
    const manifest = this.mobPopulationManifest;
    if (!manifest) return;
    const map = manifest.maps.find((candidate) => candidate.map_id === plan.id);
    this.probes.mobCount = 0;
    if (!map) {
      // The current population block is authoritative. Omitting a hunting map means that map has
      // no managed population; it never falls through to the optional static spawner.
      delete this.probes.mobPopulation;
      return;
    }

    const candidateSets = this.mobPopulationCandidates(map, heights);
    const stageManifest: MobPopulationManifest = {
      ...manifest,
      maps: [map],
    };
    const director = new MobPopulationDirector(stageManifest, candidateSets, {
      seed: stageTerrainSeed(baseTerrainSeed, plan),
    });
    this.mobPopulationDirector = director;
    this.mobPopulationMapId = map.map_id;
    this.publishMobPopulationProbe();
  }

  /** Resolve authored spawn zones onto flat, walkable terrain columns for this stage instance. */
  private mobPopulationCandidates(
    map: MobPopulationMapManifest,
    heights: number[],
  ): readonly ZoneCandidateColumns[] {
    const flatColumns = new Set<number>();
    for (const run of flatRuns(heights, 2)) {
      for (let column = run.start; column < run.start + run.len; column += 1) {
        flatColumns.add(column);
      }
    }

    return map.zones.map((zone) => {
      const zoneLeftPx = zone.left_column * TILE_PX;
      const zoneRightPx = zone.right_column_exclusive * TILE_PX;
      const candidateColumns = [...flatColumns]
        .filter((column) => {
          if (column < zone.left_column || column >= zone.right_column_exclusive) {
            return false;
          }
          if (!verticalSpawnAllowed(this.verticalReservedColumns, column)) return false;
          const x = column * TILE_PX + TILE_PX / 2;
          // The spawn territory owns the patrol lane. Aggro pursuit may use its separately
          // authored leash, but an idle mob must not wander into a neighboring zone.
          return (
            x - zone.wander_radius_px >= zoneLeftPx &&
            x + zone.wander_radius_px < zoneRightPx
          );
        })
        .sort((left, right) => left - right)
        .map((column) => ({
          column,
          x_px: column * TILE_PX + TILE_PX / 2,
          y_px: terrainSurfaceY(heights[column] ?? 0, TILE_PX, GROUND_BASELINE_Y),
        }));
      if (candidateColumns.length === 0) {
        throw new Error(
          `mob population zone ${JSON.stringify(map.map_id + "/" + zone.zone_id)} ` +
            "has no walkable terrain spawn points",
        );
      }
      return {
        map_id: map.map_id,
        zone_id: zone.zone_id,
        candidate_columns: candidateColumns,
      };
    });
  }

  /** Advance spawn tickets, reserve positions, and materialize accepted mob instances. */
  private updateMobPopulation(
    now: number,
    camera: Phaser.Cameras.Scene2D.Camera,
  ): void {
    const director = this.mobPopulationDirector;
    const mapId = this.mobPopulationMapId;
    if (!director || !mapId) return;
    const nowMs = Math.max(0, Math.trunc(now));

    for (const [mob, instanceId] of this.mobPopulationInstanceIds) {
      if (!mob.isAlive()) continue;
      director.updateInstancePosition(instanceId, {
        x_px: mob.sprite.x,
        y_px: mob.sprite.y,
      });
    }

    const view = camera.worldView;
    const reservations = director.update(mapId, nowMs, {
      players: this.player
        ? [{ x_px: this.player.sprite.x, y_px: this.player.sprite.y }]
        : [],
      cameras: [
        {
          left_px: view.left,
          right_px_exclusive: view.right,
          top_px: view.top,
          bottom_px_exclusive: view.bottom,
        },
      ],
      occupied_points: [
        ...this.obstacleSprites
          .filter((sprite) => sprite.active)
          .map((sprite) => ({ x_px: sprite.x, y_px: sprite.y })),
        // A death immediately leaves the live population, but its visual body occupies the lane
        // through the fade. This keeps a zero-delay replacement from materializing inside it.
        ...this.mobs
          .filter((mob) => !mob.isAlive() && mob.sprite.active)
          .map((mob) => ({ x_px: mob.sprite.x, y_px: mob.sprite.y })),
      ],
    });
    for (const reservation of reservations) {
      this.materializeMobReservation(director, reservation, nowMs);
    }
    this.publishMobPopulationProbe();
  }

  /** Turn a pure reservation into a Phaser-owned mob, confirming only after construction. */
  private materializeMobReservation(
    director: MobPopulationDirector,
    reservation: SpawnReservation,
    nowMs: number,
  ): void {
    const inputs = this.stageBuildInputs;
    if (!inputs) {
      director.reject(reservation.reservation_id, nowMs);
      return;
    }

    let mob: Mob | null = null;
    try {
      mob = this.createMobAtColumn(
        reservation.mob_slot,
        reservation.candidate_column,
        inputs.mobIdleKeys,
        inputs.mobHurtKeys,
        inputs.mobAttackKeys,
        inputs.mobAlphaFrames,
        reservation.wander_radius_px,
        reservation.pursuit_leash_px,
      );
      if (!mob) {
        director.reject(reservation.reservation_id, nowMs);
        return;
      }
      const instanceId = `${reservation.map_id}/mob/${this.nextMobPopulationInstance++}`;
      director.confirm(reservation.reservation_id, instanceId);
      this.mobs.push(mob);
      this.mobPopulationInstanceIds.set(mob, instanceId);
      this.logEvent("mob-spawned", {
        mobSlot: reservation.mob_slot,
        zoneId: reservation.zone_id,
        initialFill: reservation.ticket_reason === "initial_fill",
      });
    } catch (error) {
      mob?.destroy();
      director.reject(reservation.reservation_id, nowMs);
      this.recordErr(error);
    }
  }

  /** Convert one confirmed death into exactly one delayed replacement ticket. */
  private recordManagedMobDeath(mob: Mob, now: number): void {
    const director = this.mobPopulationDirector;
    const instanceId = this.mobPopulationInstanceIds.get(mob);
    if (!director || !instanceId) return;
    const receipt = director.recordDeath(instanceId, Math.max(0, Math.trunc(now)));
    this.mobPopulationInstanceIds.delete(mob);
    if (receipt) {
      this.logEvent("mob-respawn-scheduled", {
        zoneId: receipt.zone_id,
        dueAtMs: receipt.due_at_ms,
        sameArchetype: receipt.locked_mob_slot !== undefined,
      });
    }
    this.publishMobPopulationProbe();
  }

  private publishMobPopulationProbe(): void {
    const director = this.mobPopulationDirector;
    if (!director) return;
    const snapshot = director.snapshot();
    this.probes.mobPopulation = snapshot;
    this.probes.mobCount = snapshot.maps.reduce(
      (mapTotal, map) =>
        mapTotal +
        map.zones.reduce((zoneTotal, zone) => zoneTotal + zone.alive_count, 0),
      0,
    );
  }

  /** Cancel all tickets/reservations before the stage's Phaser objects are destroyed. */
  private disposeMobPopulation(): void {
    const director = this.mobPopulationDirector;
    const mapId = this.mobPopulationMapId;
    if (director) {
      const disposed = director.dispose();
      this.logEvent("mob-population-disposed", {
        mapId: mapId ?? "unknown",
        liveInstances: disposed.instance_ids.length,
        reservations: disposed.reservation_ids.length,
        cancelledTickets: disposed.cancelled_ticket_count,
      });
    }
    this.mobPopulationDirector = undefined;
    this.mobPopulationMapId = undefined;
    this.mobPopulationInstanceIds.clear();
    if (this.probes) delete this.probes.mobPopulation;
  }

  /** Construct one mob archetype at a terrain column without mutating population state. */
  private createMobAtColumn(
    mobSlot: number,
    spawnColumn: number,
    mobIdleKeys: readonly string[],
    mobHurtKeys: readonly string[],
    mobAttackKeys: readonly string[],
    mobAlphaFrames: readonly Readonly<{
      idle: readonly CellRect[];
      hurt: readonly CellRect[];
    }>[],
    wanderExtentPx?: number,
    pursuitLeashPx?: number,
  ): Mob | null {
    const idleKey = mobIdleKeys[mobSlot];
    const hurtKey = mobHurtKeys[mobSlot] ?? "";
    if (!idleKey) return null;
    const frames = mobAlphaFrames[mobSlot];
    if (!frames || frames.idle.length === 0) {
      this.recordErr(`mob ${mobSlot} has no measured idle alpha frames`);
      return null;
    }
    const spriteHeightPx = TILE_PX * 1.8;
    const renderEnvelope = mobRenderEnvelope({
      idleFrames: frames.idle,
      hurtFrames: frames.hurt,
      targetFrameZeroHeight: spriteHeightPx,
    });
    return new Mob({
      scene: this,
      ladderIndex: mobSlot,
      spawnCol: spawnColumn,
      tilePx: TILE_PX,
      worldWidthPx: STAGE_W,
      baselineY: GROUND_BASELINE_Y,
      heightFn: (column) => terrainHeightAtColumn(this.heights, column),
      spriteHeightPx,
      idleAnimKey: idleKey,
      hurtTextureKey: hurtKey || idleKey,
      renderEnvelope,
      aggression: this.combatAggressionForSlot(mobSlot),
      attackTextureKey: mobAttackKeys[mobSlot] || undefined,
      fixedStepMotion: Boolean(this.automationMode),
      wanderExtentPx,
      pursuitLeashPx,
    });
  }

  private spawnMobs(
    heights: number[],
    mobIdleKeys: string[],
    mobHurtKeys: string[],
    mobAttackKeys: string[],
    mobAlphaFrames: readonly Readonly<{
      idle: readonly CellRect[];
      hurt: readonly CellRect[];
    }>[],
    runStride = 2,
  ) {
    if (mobIdleKeys.filter(Boolean).length === 0) return;
    const runs = flatRuns(heights, 2);
    const stride = Math.max(1, Math.trunc(runStride));
    let spawned = 0;
    let mobIdx = 0;
    for (let r = 0; r < runs.length; r += stride) {
      const run = runs[r];
      const col = run.start + 1;
      if (!verticalSpawnAllowed(this.verticalReservedColumns, col)) continue;
      const ladderIndex = mobIdx % mobIdleKeys.length;
      const mob = this.createMobAtColumn(
        ladderIndex,
        col,
        mobIdleKeys,
        mobHurtKeys,
        mobAttackKeys,
        mobAlphaFrames,
      );
      mobIdx++;
      if (!mob) continue;
      this.mobs.push(mob);
      spawned++;
    }
    this.probes.mobCount = spawned;
  }

  // ---------- Village ----------

  /**
   * Load the run's residents and its fixture sheet.
   *
   * Nothing is requested unless the manifest declared a village, so a run without one issues no
   * request and cannot log a 404. A run that declared one but whose sheets do not answer records
   * the failure and continues: the manifest is what decided the stage book, and unwinding that
   * decision here would mean rebuilding the book after asset load, at which point the automation
   * heightmap digests - already taken per stage - would describe a book that no longer exists.
   * A town with fewer residents than its bible names is a legible failure; a book that disagrees
   * with the digests beside it is not.
   */
  private async loadVillageAssets(
    u: AssetUrlFn,
    tag: string,
  ): Promise<{
    villageNpcIdleKeys: ReadonlyMap<number, string>;
    villageFixtureCells: readonly { cellIdx: number; w: number; h: number }[];
  }> {
    const villageNpcIdleKeys = new Map<number, string>();
    const villageFixtureCells: { cellIdx: number; w: number; h: number }[] = [];
    const village = this.villageSpec;
    if (!village) return { villageNpcIdleKeys, villageFixtureCells };

    // Both the filename and the slice count come from the run's published render profile.
    // Neither may be assumed: a still is `npc_<tag>_<slot>_still.png` and has one cell, and
    // slicing a single portrait into the four columns a strip has renders its left quarter
    // without raising anything - the failure is entirely visual.
    const { state, frames } = village.render;
    for (const npc of village.npcs) {
      const key = `npc_${npc.slot}_${state}`;
      try {
        await loadFrameStrip(
          u(`npc_${tag}_${npc.slot}_${state}.png`),
          key,
          frames,
          this.textures,
          this.transparencyPolicy,
        );
        this.probes.loadedAssetKeys.push(key);
        villageNpcIdleKeys.set(npc.slot, key);
        // No animation is registered, whichever profile this run drew. A still has one cell to
        // play. A strip has four, but `Npc` draws cell zero and holds it, so a loop created
        // here would be built, held in the animation manager and never played.
      } catch (e) {
        this.recordErr(e);
      }
    }

    try {
      const { cells } = await loadGridSheet(
        u(`village_fixtures_${tag}.png`),
        "village_fixtures",
        2,
        4,
        "prop",
        this.textures,
        this.transparencyPolicy,
      );
      this.probes.cellExtractProbe["village_fixtures"] = cells;
      this.probes.loadedAssetKeys.push("village_fixtures");
      // The same 16px floor the obstacle sheets apply. A cell that measured smaller than this is
      // a nearly empty crop rather than a fixture, and scaling it to fixture height would stretch
      // a few stray pixels across the width of a market stall.
      cells.forEach((cell, index) => {
        if (cell.w > 16 && cell.h > 16) {
          villageFixtureCells.push({ cellIdx: index, w: cell.w, h: cell.h });
        }
      });
    } catch (e) {
      this.recordErr(e);
    }

    // A rich conversation is an all-or-nothing runtime import. Every declared PNG is fetched,
    // byte/hash checked, decoded, dimension checked, alpha checked, and registered under a
    // run-local texture key before the slot becomes usable. If any one state fails, remove every
    // texture from that attempted set and leave the resident on their current village lines.
    for (const character of this.dialogueCharacterSpecs) {
      const matchingNpc = village.npcs.find(
        (npc) =>
          npc.slot === character.npcSlot && npc.name === character.npcName,
      );
      if (!matchingNpc) continue;
      const portraitTextureKeys = Object.freeze(
        Object.fromEntries(
          DIALOGUE_EXPRESSION_STATES.map((state) => [
            state,
            `dialogue_character_${character.npcSlot}_${state}`,
          ]),
        ),
      ) as DialoguePortraitTextureKeys;
      const results = await Promise.allSettled(
        character.assets.map((asset) =>
          loadVerifiedDialogueSprite({
            url: u(asset.path),
            key: portraitTextureKeys[asset.state],
            asset,
            textures: this.textures,
          }),
        ),
      );
      const rejected = results.find(
        (result): result is PromiseRejectedResult =>
          result.status === "rejected",
      );
      if (rejected) {
        for (const key of Object.values(portraitTextureKeys)) {
          if (this.textures.exists(key)) this.textures.remove(key);
        }
        this.recordErr(rejected.reason);
        continue;
      }
      this.probes.loadedAssetKeys.push(...Object.values(portraitTextureKeys));
      this.dialogueCharacterBindings.set(
        character.npcSlot,
        Object.freeze({
          npcName: character.npcName,
          beats: character.dialogue,
          portraitTextureKeys,
        }),
      );
    }

    // The panel and its keys belong to the run, not to the stage: built once here, closed on
    // every stage teardown, destroyed only when the scene shuts down. A run with no village
    // builds neither, so it can never gate its own input behind a box it cannot open.
    this.dialogue = new DialogueBox({
      scene: this,
      viewW: VIEW_W,
      viewH: VIEW_H,
    });
    this.bindInteractInput();

    return { villageNpcIdleKeys, villageFixtureCells };
  }

  /**
   * Stand the run's residents on the village street.
   *
   * Returns the columns they occupy so fixture placement can leave them clear. A resident whose
   * strip failed to load is skipped rather than constructed against a texture key Phaser has
   * never seen, which would draw a green placeholder square wearing that villager's name.
   */
  private spawnVillageNpcs(
    heights: number[],
    idleKeys: ReadonlyMap<number, string>,
  ): ReadonlySet<number> {
    const village = this.villageSpec;
    const columns = new Set<number>();
    if (!village) return columns;
    const placements = planNpcPlacements({
      npcCount: village.npcs.length,
      heights,
      tilePx: TILE_PX,
      reservedColumns: this.verticalReservedColumns,
      worldWidthPx: STAGE_W,
    });
    const playerReference = this.characterScaleReferences.get("character_idle");
    if (!playerReference) {
      throw new Error("current scrolling manifest requires character-idle scale_reference");
    }
    const playerStandingFrameHeight = this.playerStandingFrameHeight();
    for (const placement of placements) {
      const spec = village.npcs[placement.slot];
      if (!spec) continue;
      const idleTextureKey = idleKeys.get(spec.slot);
      if (!idleTextureKey) continue;
      const scaleReference = this.villageNpcScaleReferences.get(spec.slot);
      if (!scaleReference) {
        throw new Error(
          `current scrolling manifest requires village NPC ${spec.slot} scale_reference`,
        );
      }
      const npc = new Npc({
        scene: this,
        slot: spec.slot,
        name: spec.name,
        spawnX: placement.x,
        tilePx: TILE_PX,
        worldWidthPx: STAGE_W,
        baselineY: GROUND_BASELINE_Y,
        heightFn: (col) => terrainHeightAtColumn(this.heights, col),
        idleTextureKey,
        // A front-facing resident is already looking at the player, so turning them toward one
        // is a no-op that reverses everything asymmetric about them - which hand a tool is in,
        // which side an apron ties on. Only a side-view resident is mirrored.
        facesPlayer: village.render.orientation === "side",
        scaleReference,
        playerScaleReference: playerReference,
        playerTargetSpriteHeight: PLAYER_TARGET_SPRITE_HEIGHT,
        playerStandingFrameHeight,
        lines: spec.lines,
      });
      this.npcs.push(npc);
      columns.add(placement.column);
    }
    return columns;
  }

  /**
   * Frame-zero height of the player's idle sheet, in that sheet's own source pixels.
   *
   * The denominator of the player's master scale, and therefore of every head match taken
   * against them. Missing texture geometry is a load failure, never a substitute denominator.
   */
  /** The archetype published for one mob slot, or null when the run published none. */
  private combatAggressionForSlot(slot: number) {
    return parseAggression(this.combatAggressions.get(slot));
  }

  private playerStandingFrameHeight(): number {
    if (!this.textures.exists("character_idle")) {
      throw new Error("current player idle texture is missing");
    }
    const height = this.textures.get("character_idle").get(0)?.height;
    if (typeof height !== "number" || !Number.isFinite(height) || height <= 0) {
      throw new Error("current player idle frame height is invalid");
    }
    return height;
  }

  /**
   * Dress the street with the run's eight fixtures.
   *
   * Deliberately not `placeObstacles`. That spreads props by flat run, which is the right unit on
   * rolling terrain and collapses to a single run on a village: the whole town is one flat run,
   * so obstacle placement would put exactly one stall at column 100 and leave the rest of the
   * street bare. Fixtures are spread by count across the walkable span instead, which is what
   * makes eight of them read as a settlement.
   */
  private placeVillageFixtures(
    heights: number[],
    cells: readonly { cellIdx: number; w: number; h: number }[],
    npcColumns: ReadonlySet<number>,
  ): void {
    this.probes.flatRunCount = flatRuns(heights, 2).length;
    this.probes.obstacleCount = 0;
    if (cells.length === 0) return;
    const firstColumn = VILLAGE_FIXTURE_EDGE_MARGIN_COLUMNS;
    const lastColumn =
      heights.length - 1 - VILLAGE_FIXTURE_EDGE_MARGIN_COLUMNS;
    if (lastColumn <= firstColumn) return;
    const span = lastColumn - firstColumn;
    let placed = 0;
    for (let index = 0; index < cells.length; index += 1) {
      // Half-step offsets, matching `planNpcPlacements`, so the fixtures sit inside the span
      // rather than one landing on its first column and the last trailing off the far end.
      const ideal =
        firstColumn + Math.round(((index + 0.5) * span) / cells.length);
      const column = clearVillageFixtureColumn(
        ideal,
        firstColumn,
        lastColumn,
        npcColumns,
      );
      if (column === null) continue;
      const cell = cells[index]!;
      const surfaceY = terrainSurfaceY(
        terrainHeightAtColumn(heights, column),
        TILE_PX,
        GROUND_BASELINE_Y,
      );
      const aspect = cell.w / Math.max(1, cell.h);
      const image = this.add.image(
        column * TILE_PX + TILE_PX / 2,
        surfaceY,
        "village_fixtures",
        `prop_${cell.cellIdx}`,
      );
      image.setOrigin(0.5, 1.0);
      image.setDisplaySize(
        VILLAGE_FIXTURE_HEIGHT_PX * aspect,
        VILLAGE_FIXTURE_HEIGHT_PX,
      );
      image.setDepth(SCENE_CONTENT_DEPTH.prop);
      // Tracked as an obstacle sprite so one teardown path clears every prop the stage owns,
      // whichever kind of stage laid it.
      this.obstacleSprites.push(image);
      placed += 1;
    }
    this.probes.obstacleCount = placed;
  }

  /**
   * Bind the interact keys.
   *
   * `E` and `Enter`, and neither of the two keys already spoken for: `Up`/`W` mounts a ladder and
   * `I` opens the inventory, so reusing either would make one press mean two things at once in
   * front of a villager standing at the foot of a ladder.
   *
   * `Key` objects read as edges rather than an event listener, because Phaser's `Key` suppresses
   * the browser's auto-repeat for us - `_justDown` is set on the down transition only. A listener
   * on `keydown-E` fires once per repeat instead, and a player resting a finger on the key would
   * watch a whole conversation scroll past at the keyboard's repeat rate.
   *
   * Neither key is captured. Phaser's capture list calls `preventDefault` on `window` for as long
   * as the game is alive, not only while the canvas has focus, and the preview page around the
   * canvas has a link on it - so capturing `Enter` would stop a keyboard user activating the
   * page's own navigation. Neither key has a default action inside the canvas worth suppressing.
   */
  private bindInteractInput(): void {
    const keyboard = this.input.keyboard;
    if (!keyboard || this.interactKeys.length > 0) return;
    this.interactKeys = [
      keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.E, false),
      keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.ENTER, false),
    ];
  }

  private releaseInteractInput(): void {
    const keyboard = this.input.keyboard;
    for (const key of this.interactKeys) keyboard?.removeKey(key);
    this.interactKeys = [];
  }

  /**
   * Whether the interact key went down this frame.
   *
   * Every key is read, not just until one answers true: `JustDown` clears the flag it reports, so
   * short-circuiting on the first hit would leave the other key's edge pending and spend it on
   * the following frame, advancing the conversation twice for one press.
   */
  private consumeInteractPress(): boolean {
    let pressed = false;
    for (const key of this.interactKeys) {
      if (Phaser.Input.Keyboard.JustDown(key)) pressed = true;
    }
    return pressed;
  }

  /**
   * Face the residents, offer the talk prompt, and run the conversation.
   *
   * The target is resolved once per frame and reused for both halves, so the villager who is
   * offered the prompt is always the villager the key press reaches. While a conversation is open
   * no resident advertises a second interaction; `speakingNpcSlot` independently pins the speaker
   * until the sequence closes.
   */
  private updateVillage(interactPressed: boolean): void {
    const dialogue = this.dialogue;
    if (!dialogue) return;
    const playerX = this.player?.sprite.x ?? Number.NaN;
    const nearest = npcInteractionTarget(playerX, this.npcs);
    for (const npc of this.npcs) {
      npc.update(playerX, !dialogue.isOpen && npc.slot === nearest);
    }
    // Published every frame rather than on the transitions, because a verifier samples the probe
    // at an arbitrary frame and needs the residents' live positions and the box's current line,
    // not whatever they were when the conversation last changed state.
    this.publishVillageProbe();
    if (!interactPressed) return;
    if (dialogue.isOpen) {
      // The box does not close itself on its last line - see `DialogueBox.advance` - so the
      // caller is what turns "there is nothing after this" into a closed panel.
      if (!dialogue.advance()) this.closeDialogue();
      return;
    }
    if (nearest === null) return;
    const npc = this.npcs.find((candidate) => candidate.slot === nearest);
    if (!npc) return;
    const rich = this.dialogueCharacterBindings.get(npc.slot);
    if (rich?.npcName === npc.name) {
      dialogue.openBeats(rich.beats, rich.portraitTextureKeys);
    } else {
      dialogue.open(npc.name, npc.lines);
    }
    // A villager the manifest published no lines for leaves the box closed. Recording them as the
    // speaker anyway would gate the player's input behind a panel that is not on screen.
    if (!dialogue.isOpen) return;
    this.suppressInventoryForDialogue();
    this.speakingNpcSlot = npc.slot;
    this.logEvent("dialogue-open", {
      slot: npc.slot,
      name: npc.name,
      lines: dialogue.snapshot().lineCount,
    });
  }

  /** Hold the inventory out of the portrait's screen space for the active conversation. */
  private suppressInventoryForDialogue(): void {
    const inventory = this.inventory;
    if (!inventory) return;
    if (this.dialogueInventoryWasVisible === null) {
      this.dialogueInventoryWasVisible = inventory.visible;
    }
    if (inventory.visible) inventory.setVisible(false);
  }

  /** Release the dialogue's HUD lease without overriding a previously hidden inventory. */
  private restoreInventoryAfterDialogue(): void {
    const wasVisible = this.dialogueInventoryWasVisible;
    this.dialogueInventoryWasVisible = null;
    if (wasVisible === null || !this.inventory) return;
    // Deterministic encounter presentation can hold the same HUD hidden independently. Releasing
    // the dialogue lease must not make it visible for one or more frames while that owner still
    // holds its lease; normal presentation restores the player's exact pre-dialogue choice.
    this.inventory.setVisible(
      this.automationEncounterHudSuppressed ? false : wasVisible,
    );
  }

  /**
   * End the conversation and hand the keyboard back.
   *
   * The reset is the other half of the input gate. Freezing the player leaves the keys they
   * pressed during the conversation unread, and Phaser holds a `_justDown` edge until somebody
   * reads it - so without this, the jump or the swing the player spent mid-sentence would fire on
   * the first frame after the panel closed, from a standing start, for no visible reason. Held
   * movement keys re-register on the browser's next auto-repeat, so walking out of a conversation
   * costs nothing.
   *
   * The interact keys are exempted by hand, because for them the re-registration is the bug. A
   * `Key` only reports `JustDown` on a false-to-true transition, which is what stops a held key
   * running through a conversation; resetting one that is still physically held manufactures that
   * transition on the next auto-repeat, and the key press that ended the conversation would
   * reopen it a frame later. Carrying the held state across the reset keeps the edge suppressed
   * until the player actually lets go, and `Key.onUp` clears it from there as usual.
   */
  private closeDialogue(): void {
    const dialogue = this.dialogue;
    if (!dialogue) return;
    const wasOpen = dialogue.isOpen;
    dialogue.close();
    this.speakingNpcSlot = null;
    this.restoreInventoryAfterDialogue();
    if (!wasOpen) return;
    this.logEvent("dialogue-close");
    const heldInteractKeys = this.interactKeys.filter((key) => key.isDown);
    this.input.keyboard?.resetKeys();
    for (const key of heldInteractKeys) {
      key.isDown = true;
      key.isUp = false;
    }
  }

  /** Publish the town, while the town is the stage on screen. */
  private publishVillageProbe(): void {
    const village = this.villageSpec;
    const dialogue = this.dialogue;
    if (!village || !dialogue || this.probes.stageKind !== "village") return;
    this.probes.village = {
      name: village.name,
      npcs: this.npcs.map((npc) => npc.snapshot()),
      dialogue: dialogue.snapshot(),
    };
  }

  // ---------- Player spawn ----------

  private spawnPlayer(heights: number[]) {
    const runs = flatRuns(heights, 3);
    const startCol = runs.length > 0 ? runs[0].start + 1 : 4;
    const h = heights[startCol];
    // Arriving through a portal steps the player out of the matching end of
    // the new stage rather than dropping them at its first flat run, so the
    // two worlds read as connected. The opening stage has no arrival end and
    // keeps the run's own start column.
    const arrival = this.pendingArrivalEnd
      ? this.portal?.portalAt(this.pendingArrivalEnd)
      : undefined;
    this.pendingArrivalEnd = null;
    const spawnColumn = arrival ? Math.floor(arrival.x / TILE_PX) : startCol;
    this.probes.playerColumn = spawnColumn;
    const surfaceY = arrival
      ? arrival.y
      : terrainSurfaceY(h, TILE_PX, GROUND_BASELINE_Y);
    const x = arrival ? arrival.x : startCol * TILE_PX + TILE_PX / 2;

    const hF = (col: number) => terrainHeightAtColumn(heights, col);

    this.player = new Player({
      scene: this,
      startX: x,
      startY: surfaceY,
      tilePx: TILE_PX,
      worldWidthPx: STAGE_W,
      baselineY: GROUND_BASELINE_Y,
      heightFn: hF,
      targetSpriteHeight: PLAYER_TARGET_SPRITE_HEIGHT,
      scaleReferences: this.characterScaleReferences,
      platforms: this.verticalWorld.platforms,
      ladders: this.verticalWorld.ladders,
      maximumAirJumps: this.levelCapabilities.maximumAirJumps,
      combatEnabled: this.levelCapabilities.combatEnabled,
      onTransition: (kind, data) => this.logEvent(kind, data),
    });

    this.cameras.main.scrollX = Math.max(0, x - VIEW_W / 2);
  }

  private recordErr(e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error("[scene]", msg);
  }

  private recordDiagnostic(value: unknown): void {
    const message = value instanceof Error ? value.message : String(value);
    this.probes.diagnostics.push(message);
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
