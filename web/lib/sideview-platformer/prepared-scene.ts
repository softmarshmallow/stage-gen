import Phaser from "phaser";
import {
  initialScenarioState,
  reduceScenario,
  scenarioActor,
  scenarioIsFinished,
  scenarioView,
  type ScenarioAction,
  type ScenarioState,
} from "@/lib/scenario/runtime";
import type { ScenarioChoiceOption, ScenarioProgram } from "@/lib/scenario/program";
import { dialogueChoicePrompt } from "./dialogue-choices";
import type { GameplayAutomationMode, GameplayTranscriptEvent } from "./automation";
import { Bot, resolveBotControl, type BotControlSource } from "./bot";
import { HUNTER_BOT_PROFILE } from "./bot-hunter";
import {
  preparedBotWeaponBand,
  preparedBotWorldView,
  preparedNavGraph,
} from "./bot-adapter";
import { EMPTY_NAV_GRAPH, type NavGraph } from "./bot-navigation";
import type { BotWorldView } from "./bot-view";
import { NEUTRAL_PLAYER_INTENT, type PlayerIntent } from "./player-intent";
import type { ScenePlayerIntentSource } from "./player-intent";
import { GAMEPLAY_AUTOMATION_VIEWPORT } from "./automation";
import {
  applyDeviceZoom,
  centeredScroll,
  currentDevicePixelScale,
  deviceCameraBounds,
  deviceFollowOffset,
  deviceGameSize,
  logicalWorldView,
  midpointOffset,
} from "@/lib/device-pixels/device-camera";
import {
  fetchJson,
  loadFrameStrip,
  loadGridSheet,
  loadTerrainAtlas,
  loadTrimmedSprite,
  loadTransparentSprite,
  registerCanvas,
} from "@/lib/sideview/assets";
import { loadVerifiedRepeatLayer } from "./assets";
import { preparedAssetUrl } from "@/lib/shell/asset-url";
import {
  parsePreparedRuntimeManifest,
  type MotionBinding,
  type PreparedMap,
  type PreparedRuntimeManifest,
} from "@/lib/manifest/prepared-manifest";
import type { PreviewTransparencyPolicy } from "@/lib/shell/transparency";
import { Player } from "./player";
import { Mob, type MobDeckFooting } from "./mob";
import { ItemSystem } from "./items";
import { InventoryHud } from "./inventory";
import {
  carried,
  consume as consumeFromBag,
  EMPTY_BAG,
  grant as grantToBag,
  UNLIMITED,
  type CountedBag,
} from "@/lib/families/inventory";
import {
  PortalSystem,
} from "./portal";
import { CombatTextSystem } from "./combat-text";
import {
  FloatingHealthBar,
  PLAYER_HEALTH_BAR_STYLE,
} from "./health-bar";
import {
  aggressionProfile,
  parseAggression,
  attackFootLevelsOverlap,
  resolveCriticalDamage,
} from "./combat";
import {
  healingRestoreAmount,
} from "./vitals";
import {
  experienceForRank,
  grantExperience,
  initialProgression,
  maximumHealthForLevel,
  type ProgressionPolicy,
  type ProgressionState,
} from "./progression";
import {
  StatLogHud,
  formatExperienceLine,
  formatLevelUpLine,
} from "./stat-log";
import {
  hasHealingConsumable,
  selectAmmoItemId,
  selectHealingItemId,
} from "./consumables";
import { ProjectileSystem } from "./projectiles";
import { resolveInstantStrike } from "./strike";
import { ImpactSystem } from "./impact-presentation";
import {
  numberScaleProfile,
  scaleMobHealth,
  scaleOutgoingDamage,
  type NumberScaleProfile,
} from "./number-scale";
import {
  resolveWeaponClassProfile,
  weaponClassProfile,
  type WeaponClass,
  type WeaponClassProfile,
} from "./weapon-class";
import {
  developerKitLabel,
  nextDeveloperKit,
  sameDeveloperKit,
  selectableDeveloperKits,
  type DeveloperKit,
} from "./developer-kit";
import { drawnExtentPx } from "@/lib/manifest/asset-unit";
import { projectileProfile } from "./projectile-class";
import { automatedDefeatConfirmDue, resolveHomeSpawn } from "./respawn";
import { DefeatPanel } from "./defeat-panel";
import { mobRenderEnvelope } from "./mob-geometry";
import {
  MobPopulationDirector,
  type SpawnReservation,
} from "./spawn-director";
import {
  ladderVisualBounds,
  type VerticalWorld,
} from "./vertical";
import { sampleMapNameBanner } from "./fixed-motion";
import {
  DeterministicSoundtrackPlayer,
  type SoundtrackTransport,
} from "./soundtrack";
import type { ScaleReference } from "@/lib/sideview/sprite-scale";
import {
  registerGridPresentationFallback,
  registerPresentationFallback,
  type PresentationFallbackKind,
} from "@/lib/ui-atlas/fallback";
import { UI_ATLAS_SHEETS } from "@/lib/ui-atlas/sheets";
import { NineSliceWidget } from "@/lib/ui-atlas/widget";
import { DEFAULT_DIALOGUE_BOX_KNOBS, dialogueBoxLayout } from "./dialogue-box-layout";
import {
  assertPreparedGameplayManifestClosure,
  parsePreparedGameplayContract,
  type PreparedGameplayContract,
} from "./prepared-gameplay";
import {
  projectPreparedMobPopulation,
  reservedSpawnColumns,
  type PreparedDeckFooting,
} from "./prepared-population";
import {
  anchorRepackedMotionFeet,
  applyMotionPlayback,
  installMotionPlayback,
} from "@/lib/families/sideview/motion";
import {
  PREPARED_PLAYER_PRESERVE_SOURCE_SCALE_STATES,
  parsePlatformerMotionBlocks,
  preparedPlayerClimbArtwork,
  preparedPlayerMotionPlayback,
  resolvePreparedPlayerMotions,
  preparedPlayerStateAdapter,
  preparedPlayerStateRebase,
} from "./prepared-player";
import { frameScaleForHeight } from "@/lib/sideview/sprite-scale";
import { SCENE_CONTENT_DEPTH } from "./depths";
import {
  followBounds,
  NO_SHAKE,
  ShakeCarrier,
  type ShakeOffset,
} from "@/lib/families/camera";
import {
  preparedGroundBaselineY,
  preparedLayerLayout,
  preparedWalkSurfaceY,
} from "./prepared-layers";
import {
  terrainAtlasBoundaryOverscanPlan,
  terrainAtlasWalkSurfaceOffset,
} from "@/lib/sideview/terrain-atlas";
import {
  projectPreparedTerrainWorld,
  type PreparedTerrainWorld,
} from "./prepared-terrain";
import { terrainSurfaceY } from "./terrain";
import { preparedPortalEndpointPlacements } from "./prepared-portals";
import { presentPreparedLayerCanvas } from "@/lib/sideview/prepared-layer-presentation";
import { climbableAtlasFrames, climbableFrameKey } from "./prepared-climbable";
import {
  NPC_TALK_PROMPT_GAP_PX,
  NPC_TALK_PROMPT_STYLE,
  NPC_TALK_PROMPT_TEXT,
  NPC_TALK_RANGE_PX,
} from "./npc";
import { DebugOverlay } from "./debug-overlay";
import { parsePlatformerClockBlock } from "./clock";
import { parsePlatformerTraversalBlocks } from "./vertical";
import { parsePlatformerParallaxBlock } from "./prepared-layers";
import { parsePlatformerNavigationBlock } from "./bot-navigation";
import { parsePlatformerActorAiBlock } from "./combat";
import { parsePlatformerIntentBlock } from "./player-intent";
import { parsePlatformerVitalsBlock } from "./vitals";
import { parsePlatformerCameraBlock } from "./camera";
import { parsePlatformerSoundtrackBlock } from "./soundtrack";
import { parsePlatformerParticlesBlock } from "./impact-presentation";
import { parsePlatformerInventoryBlocks } from "./bag";
import { dropSpread, resolveLootDrops } from "@/lib/families/loot";
import { LOOT_DROP_SPACING_PX, parsePlatformerLootBlocks } from "./loot";
import {
  openSession,
  selectAffordance,
  stepSession,
  type InteractionSession,
} from "@/lib/families/interaction";
import { parsePlatformerInteractionBlock } from "./interaction";
import {
  applyEffects,
  QuestLedger,
  questsCompletedBy,
  resolveEffects,
  sealEffectVocabulary,
  sealQuestCompletions,
  type SealedEffectVocabulary,
} from "@/lib/families/effects";
import {
  parsePlatformerEffectsBlock,
  PLATFORMER_EFFECT_OPERATIONS,
  PLATFORMER_QUEST_ACTIVE,
  PLATFORMER_QUEST_STATE_OPERATION,
} from "./effects";
import type { PreparedGameplayEffect } from "./prepared-gameplay";
import {
  createPlatformerFrameWorld,
  sealPlatformerFrame,
  type PlatformerFrameSteps,
  type PlatformerFrameWorld,
} from "./frame-roster";
import type { SealedSystems } from "@/lib/kernel/systems";

const VIEW_W = 1280;
const VIEW_H = 720;
/** The design space every coordinate in this scene is written in, whatever the canvas size. */
const VIEWPORT = Object.freeze({ width: VIEW_W, height: VIEW_H });
/** Where the followed player rests relative to the screen center, in design pixels. */
const PLAYER_FOLLOW_OFFSET = Object.freeze({ x: 0, y: 50 });
const TILE_PX = 64;
const PLAYER_HEIGHT = 154;
const MOB_HEIGHT = 110;
const NPC_HEIGHT = 150;
const DIALOGUE_PANEL_CENTER_Y = VIEW_H - 128;
const DIALOGUE_PANEL_HEIGHT = 210;
const DIALOGUE_CHOICE_KEYCODES = [
  Phaser.Input.Keyboard.KeyCodes.ONE,
  Phaser.Input.Keyboard.KeyCodes.TWO,
  Phaser.Input.Keyboard.KeyCodes.THREE,
  Phaser.Input.Keyboard.KeyCodes.FOUR,
  Phaser.Input.Keyboard.KeyCodes.FIVE,
  Phaser.Input.Keyboard.KeyCodes.SIX,
  Phaser.Input.Keyboard.KeyCodes.SEVEN,
  Phaser.Input.Keyboard.KeyCodes.EIGHT,
] as const;


type NpcActor = {
  npcId: string;
  sprite: Phaser.GameObjects.Sprite;
  talkPrompt: Phaser.GameObjects.Text;
};

type ContactShadowTarget = Phaser.GameObjects.Sprite | Phaser.GameObjects.Image;

type ContactShadowBinding = Readonly<{
  target: ContactShadowTarget;
  rings: readonly Phaser.GameObjects.Ellipse[];
}>;

function preparedProjectileTextureKey(projectileId: string): string {
  return `prepared_projectile_${projectileId}`;
}

function preparedItemTextureKey(
  manifest: PreparedRuntimeManifest,
  index: number,
): string {
  const item = manifest.items[index];
  if (!item) {
    throw new Error(`prepared item index ${index} is outside the manifest catalog`);
  }
  return `prepared_item_${item.item_id}`;
}

function mobHealthForRank(rank: string): number {
  if (rank === "boss") return 12;
  if (rank === "elite") return 6;
  if (rank === "uncommon") return 3;
  return 2;
}

function motionAnimationKey(textureKey: string, state: string): string {
  return state === "idle" ? textureKey : `${textureKey}_anim`;
}

function installPreparedMotion(
  scene: Phaser.Scene,
  textureKey: string,
  state: string,
  binding: MotionBinding,
): void {
  installMotionPlayback(
    scene,
    motionAnimationKey(textureKey, state),
    textureKey,
    binding.playback,
  );
}

function scaleSpriteFrameToHeight(
  sprite: Phaser.GameObjects.Sprite,
  targetHeight: number,
): void {
  const plan = frameScaleForHeight(
    targetHeight,
    sprite.frame.width,
    sprite.frame.height,
  );
  sprite.setScale(plan.scale);
}

export class PreparedStageScene extends Phaser.Scene {
  private readonly tag: string;
  private readonly transparencyPolicy: PreviewTransparencyPolicy;
  private manifest?: PreparedRuntimeManifest;
  private gameplay?: PreparedGameplayContract;
  private ready = false;
  private loading = false;
  private currentMap?: PreparedMap;
  private player?: Player;
  private keys?: Record<string, Phaser.Input.Keyboard.Key>;
  // Derived from the entered map's ground vertical_fit rather than hard-coded.
  private groundBaselineY = VIEW_H;
  private layerSprites: Phaser.GameObjects.TileSprite[] = [];
  private groundSprites: Phaser.GameObjects.GameObject[] = [];
  private props: Phaser.GameObjects.Image[] = [];
  private contactShadows: ContactShadowBinding[] = [];
  private worldLabels: Phaser.GameObjects.Text[] = [];
  private mobs: Mob[] = [];
  private readonly mobInstanceIds = new Map<Mob, string>();
  private nextMobInstance = 1;
  private mobPopulationDirector?: MobPopulationDirector;
  private mobPopulationMapId?: string;
  private mobIdByPopulationSlot: readonly string[] = [];
  private npcs: NpcActor[] = [];
  private items?: ItemSystem;
  private projectiles?: ProjectileSystem;
  /**
   * How this package fights.
   *
   * Resolved once per world build from the manifest and then read by the controller, the strike
   * resolver, the projectile pool and the bot view alike, so the reach the bot aims for and the
   * reach the scene resolves cannot drift apart.
   */
  private weapon: WeaponClassProfile = weaponClassProfile(null);
  /** Which catalog item a throw is spending, or null for a class that spends nothing. */
  private ammoItemId: string | null = null;
  private inventoryHud?: InventoryHud;
  /**
   * What the player carries, as the `inventory` family's counted bag.
   *
   * A value rather than a mutable map, so the two operations that change it are
   * the family's and nothing else in this file can reach in and set a count.
   * The panel is mirrored from it at every change through the family's port.
   */
  private inventory: CountedBag = EMPTY_BAG;
  /** When the current defeat began, or null while the player is alive. Drives respawn timing. */
  private defeatedAtMs: number | null = null;
  private defeatPanel?: DefeatPanel;
  private bot?: Bot;
  private navGraph: NavGraph = EMPTY_NAV_GRAPH;
  private autoPlayEnabled: boolean;
  private lastHumanInputAtMs: number | null = null;
  private controlSource: BotControlSource = "human";
  private readonly mobBotIds = new Map<Mob, string>();
  private nextMobBotId = 1;
  private statLog?: StatLogHud;
  private progressionPolicy?: ProgressionPolicy;
  private progression?: ProgressionState;
  /**
   * Blows struck this session, and the only varying term in a critical seed.
   *
   * Criticals are rolled from a hash rather than `Math.random` so a replayed run rolls the same
   * criticals; a counter over the blow sequence is the part of that seed that changes when two
   * otherwise identical swings land in the same place.
   */
  private blowSequence = 0;
  private portal?: PortalSystem;
  private combatText?: CombatTextSystem;
  private impact?: ImpactSystem;
  /** The camera nudge applied last frame, subtracted before this frame's is added. */
  /** The tremor the view is carrying, so the next one replaces it rather than adding to it. */
  private readonly shakeCarrier = new ShakeCarrier();
  private healthBar?: FloatingHealthBar;
  private verticalWorld: VerticalWorld = Object.freeze({
    platforms: Object.freeze([]),
    climbables: Object.freeze([]),
  });
  private terrainWorld?: PreparedTerrainWorld;
  private worldWidth = VIEW_W;
  private verticalSprites: Phaser.GameObjects.GameObject[] = [];
  private heights: readonly number[] = Object.freeze([1]);
  private readonly scaleReferences = new Map<string, ScaleReference>();
  private readonly diagnostics: string[] = [];
  /** Which quests are running or finished, as the `effects` family's ledger. */
  private questStates = new QuestLedger();
  /**
   * The authored operation vocabulary, checked against this scene's handlers.
   *
   * Sealed once at boot rather than dispatched with an `if` per call site: an
   * operation a package may name and nothing implements is a refusal here, not
   * an effect that quietly does nothing at the one moment it fires.
   */
  private effects?: SealedEffectVocabulary<PreparedGameplayEffect>;
  private debugOverlay?: DebugOverlay;
  private mapLabel?: Phaser.GameObjects.Text;
  /** The arriving-map announcement and the simulation time it was raised at. */
  private mapBanner?: { text: Phaser.GameObjects.Text; raisedAtMs: number };
  /**
   * A map entry asked for during a frame, applied once that frame has finished.
   *
   * `enterMap` rebuilds the world, and `clearWorld` destroys the player controller. Both callers
   * that can reach it from inside `update` are in the middle of stepping that controller when they
   * do, so the entry has to wait for the end of the frame rather than land in the middle of one.
   */
  private pendingMapEntry?: { mapId: string; normalizedX: number; announce: boolean };
  private dialoguePanel?: NineSliceWidget;
  private dialogueText?: Phaser.GameObjects.Text;
  private dialogueName?: Phaser.GameObjects.Text;
  private dialoguePortrait?: Phaser.GameObjects.Sprite;
  private dialoguePortraitHeight = 0;
  /**
   * The conversation in flight, as the `interaction` family's session.
   *
   * A value rather than a mutable record: which authored interaction the
   * playback belongs to, what an advance does when the program has ended, and
   * who is told the outcome are the family's lifecycle now, and this field is
   * only where the current one is kept.
   */
  private activeScenario?: InteractionSession<ScenarioProgram, ScenarioState>;
  /** Number keys 1-8, so a choice is picked the way the visual novel picks one. */
  private choiceKeys: readonly Phaser.Input.Keyboard.Key[] = [];
  /** The portrait holds on the last speaker while the player reads a choice. */
  private lastSpeakerId: string | null = null;
  /**
   * Track order for the run, and the element the current track is playing on.
   *
   * The order is the player's: a seeded shuffle bag that exhausts before it refills and never
   * repeats across a refill, narrowed to the entered map's pool. The element is only a transport -
   * it holds one track at a time and knows nothing about which.
   */
  private soundtrackPlayer?: DeterministicSoundtrackPlayer;
  private soundtrackAudio?: HTMLAudioElement;
  private developerKit: DeveloperKit | null = null;
  private selectableKits: readonly DeveloperKit[] = [];
  /**
   * A script driving the player in place of the keyboard, for a replay or a demo.
   *
   * The keyboard is still read on every frame it is set, and its answer still thrown away, for the
   * same reason auto-play reads it: an edge-triggered request that is never read stays armed and
   * fires later out of context.
   */
  private intentSource?: ScenePlayerIntentSource;
  /**
   * What happened this frame, cleared at the top of every `update`.
   *
   * Bounded and flat: a replay hashes the world and this list together, so a frame's diff says both
   * that something changed and what the runtime called it.
   */
  private frameEvents: GameplayTranscriptEvent[] = [];
  private transcriptFrame = 0;
  /**
   * The frame, as a sealed roster rather than as seventy calls in a row.
   *
   * Built once, on the first tick that has something to tick — the steps close
   * over `this`, so they are valid for the scene's whole life whatever the world
   * is rebuilt into. `frame-roster.ts` carries the declarations and the edges;
   * this file carries the steps they order.
   */
  private sealedFrame?: SealedSystems<PlatformerFrameWorld>;
  private readonly frameWorld: PlatformerFrameWorld = createPlatformerFrameWorld();
  /**
   * This frame's `step.now`.
   *
   * The tick is the only clock. Everything inside the frame is handed `step.now`
   * by the roster; this field is for the two places that stamp simulation time
   * from outside a system's `update` — the map-name announcement raised by an
   * `enterMap` that a system asked for.
   */
  private stepNowMs = 0;

  constructor(
    tag: string,
    transparencyPolicy: PreviewTransparencyPolicy,
    automationMode: GameplayAutomationMode | null = null,
    developerKit: DeveloperKit | null = null,
  ) {
    super({ key: "PreparedStageScene" });
    this.tag = tag;
    this.transparencyPolicy = transparencyPolicy;
    // A developer's choice of kit, never the package's. It reaches the two places the runtime
    // decides how this character fights and nowhere else: `this.gameplay` stays exactly the object
    // the closure check validated, so nothing downstream can mistake an override for a published
    // fact. Under automation it is always null - see `bootPreparedGame`.
    this.developerKit = developerKit;
    // Auto-play is on for an ordinary preview and off under automation. A fixed-frame capture is
    // a recording of scripted input, and a second actor pressing keys inside it would make the
    // transcript a recording of the bot instead - which is not what that gate is asserting.
    this.autoPlayEnabled = automationMode === null;
    if (automationMode === null) this.bot = new Bot(HUNTER_BOT_PROFILE);
  }

  create(): void {
    // The canvas was sized in device pixels at boot; the camera zooms by the same factor about
    // a top-left origin so everything below keeps addressing the design space. A capture boots
    // a design-space canvas, for which this is the identity.
    applyDeviceZoom(this.cameras.main, VIEWPORT);
    this.cameras.main.setBackgroundColor("#73c7ed");
    this.add
      .text(VIEW_W / 2, VIEW_H / 2, "Preparing game…", {
        color: "#ffffff",
        fontFamily: "system-ui, sans-serif",
        fontSize: "24px",
        backgroundColor: "#15334faa",
        padding: { x: 18, y: 12 },
      })
      .setOrigin(0.5)
      .setScrollFactor(0)
      .setDepth(1000)
      .setName("loading-label");
    void this.loadAll().catch((error: unknown) => this.fail(error));
  }

  /**
   * One fixed step of the platformer, ordered by the sealer rather than by hand.
   *
   * Everything this used to spell out in sequence — which step reads which
   * slice, which one has to wait for which, and which reads a value a frame
   * older than it looks — is a declaration in `frame-roster.ts` now, and the
   * order below is derived from those declarations and pinned by
   * `frame-roster.test.ts`. The clock is the engine's frame time handed through
   * `step.now`, not `performance.now()`: the simulation and everything that
   * samples over it now read one clock, and under a fixed-step capture that
   * clock is the capture's.
   */
  update(time: number, delta: number): void {
    this.transcriptFrame += 1;
    this.frameEvents = [];
    if (!this.ready || this.loading || !this.player || !this.keys) return;
    this.stepNowMs = time;
    this.sealedFrame ??= sealPlatformerFrame(this.frameSteps());
    this.sealedFrame.tick(this.frameWorld, {
      dt: delta,
      now: time,
      frame: this.transcriptFrame,
    });
  }

  /**
   * The steps the roster orders, bound to this scene.
   *
   * A step per system and nothing else: the roster decides when each runs and
   * on what, and this object decides only what "run" means. The methods stay
   * private, so the declarations can be read on their own without the scene,
   * and the scene can rename its internals without touching them.
   */
  private frameSteps(): PlatformerFrameSteps {
    return {
      toggleDebugOverlay: () => {
        const key = this.keys?.debugOverlay;
        if (key) this.debugOverlay?.toggleForKey(key);
      },
      updateAutoPlayToggle: (nowMs) => this.updateAutoPlayToggle(nowMs),
      updateKitSwitch: (nowMs) => this.updateKitSwitch(nowMs),
      updateDebugOverlay: () => this.updateDebugOverlay(),
      updateMapBanner: (nowMs) => this.updateMapBanner(nowMs),
      readIntent: () => this.player?.readKeyboardIntent() ?? NEUTRAL_PLAYER_INTENT,
      dialogueOpen: () => this.activeScenario !== undefined,
      updateDialogueInput: (intent) => this.updateDialogueInput(intent),
      updateStatLog: (nowMs) => {
        this.statLog?.update(nowMs);
      },
      hitstopActive: (nowMs) => this.impact?.hitstopActive(nowMs) ?? false,
      updatePlayer: (deltaMs, nowMs, intent) => this.updatePlayer(deltaMs, nowMs, intent),
      updateMobPopulation: (nowMs) => this.updateMobPopulation(nowMs),
      stepMobs: (deltaMs, nowMs) => this.stepMobs(deltaMs, nowMs),
      updateProjectiles: (deltaMs, nowMs) => this.updateProjectiles(deltaMs, nowMs),
      collectDrops: (deltaMs, nowMs) => this.collectDrops(deltaMs, nowMs),
      updateImpact: (nowMs) => {
        this.impact?.update(nowMs);
      },
      impactShake: (nowMs) => this.impactShake(nowMs),
      carryCameraShake: (next) => this.carryCameraShake(next),
      updateInteractionPrompt: () => this.updateInteractionPrompt(),
      updateContactShadows: () => this.updateContactShadows(),
      scrollParallaxLayers: () => this.scrollParallaxLayers(),
      applyPendingMapEntry: () => this.applyPendingMapEntry(),
    };
  }

  /** Carry every parallax layer by its own fraction of the camera's scroll. */
  private scrollParallaxLayers(): void {
    for (const layer of this.layerSprites) {
      const parallax = Number(layer.getData("parallax") ?? 0);
      layer.tilePositionX = this.cameras.main.scrollX * parallax;
    }
  }

  /**
   * Ask for a map entry, without taking one.
   *
   * The first request of a frame wins. Two portals cannot both be walked into on one frame, and a
   * respawn asked for after a portal was would carry the player somewhere they did not ask to go.
   */
  private requestMapEntry(mapId: string, normalizedX: number, announce = true): void {
    this.pendingMapEntry ??= { mapId, normalizedX, announce };
  }

  /** Take the entry the frame asked for, now that the frame is over. */
  private applyPendingMapEntry(): void {
    const pending = this.pendingMapEntry;
    if (!pending) return;
    this.pendingMapEntry = undefined;
    void this.enterMap(pending.mapId, pending.normalizedX, pending.announce);
  }

  private url(path: string): string {
    return preparedAssetUrl(this.tag, path);
  }

  private async loadAll(): Promise<void> {
    const raw = await fetchJson<unknown>(this.url("manifest.json"));
    const manifest = parsePreparedRuntimeManifest(raw);
    const gameplay = parsePreparedGameplayContract(manifest.gameplay);
    assertPreparedGameplayManifestClosure(manifest, gameplay);
    // Each runtime family gates the block it depends on, by name, for itself.
    // A producer that moves one block gets a refusal naming that block from
    // the family that could not go on, rather than a genre parser speaking on
    // behalf of a dozen consumers it does not know about.
    parsePlatformerTraversalBlocks(manifest.blocks);
    parsePlatformerParallaxBlock(manifest.blocks);
    parsePlatformerMotionBlocks(manifest.blocks);
    parsePlatformerNavigationBlock(manifest.blocks);
    parsePlatformerActorAiBlock(manifest.blocks);
    resolvePreparedPlayerMotions(manifest.player.states);
    parsePlatformerClockBlock(manifest.blocks);
    parsePlatformerIntentBlock(manifest.blocks);
    parsePlatformerVitalsBlock(manifest.blocks);
    parsePlatformerCameraBlock(manifest.blocks);
    parsePlatformerSoundtrackBlock(manifest.blocks);
    parsePlatformerParticlesBlock(manifest.blocks);
    parsePlatformerInventoryBlocks(manifest.blocks);
    parsePlatformerLootBlocks(manifest.blocks);
    parsePlatformerEffectsBlock(manifest.blocks);
    parsePlatformerInteractionBlock(manifest.blocks);
    // A quest that could never finish is refused before the first frame rather
    // than at the moment it would have.
    sealQuestCompletions(gameplay.quests, gameplay.effects, PLATFORMER_QUEST_STATE_OPERATION);
    this.manifest = manifest;
    this.gameplay = gameplay;
    await Promise.all([
      this.loadPlayerAssets(manifest),
      this.loadMobAssets(manifest),
      this.loadNpcAssets(manifest),
      this.loadCatalogAssets(manifest),
      this.loadUiAssets(manifest),
      this.loadMapTextures(manifest),
    ]);
    this.installAnimations(manifest);
    this.prepareGameplayPresentation(manifest);
    this.resolveWeaponClass(manifest, gameplay);
    this.installInput();
    this.inventoryHud = new InventoryHud({
      scene: this,
      panelKey: "inventory",
      itemTextureKey: (index) => preparedItemTextureKey(manifest, index),
      viewW: VIEW_W,
      viewH: VIEW_H,
      layout: manifest.ui.inventory_panel,
    });
    this.healthBar = new FloatingHealthBar(
      this,
      this.gameplay.player.starting_health,
      PLAYER_HEALTH_BAR_STYLE,
    );
    this.combatText = new CombatTextSystem({
      scene: this,
      enabled: this.gameplay.combat_text.enabled,
    });
    this.impact = new ImpactSystem({
      scene: this,
      enabled: this.gameplay.combat.enabled,
    });
    this.progressionPolicy = Object.freeze({
      enabled: this.gameplay.progression.enabled,
      maximumLevel: this.gameplay.progression.maximum_level,
      curve: this.gameplay.progression.experience_curve,
      growth: this.gameplay.progression.stat_growth,
      baseHealth: this.gameplay.player.starting_health,
    });
    this.progression = initialProgression(this.progressionPolicy);
    this.statLog = new StatLogHud({
      scene: this,
      // Low on the left, clear of the top-right inventory panel and the top-left debug overlay.
      x: 28,
      y: VIEW_H - 28,
      enabled: this.gameplay.progression.enabled,
    });
    const tracks = manifest.soundtrack.tracks.map((track) => ({
      track_id: track.track_id,
      path: this.url(track.asset.path),
    }));
    if (tracks.length > 0) {
      this.soundtrackPlayer = new DeterministicSoundtrackPlayer({
        // The package's own digest: two runs of one package hear the same order, two packages do
        // not, and nothing about the order depends on when the run happened to start.
        seed: manifest.package_sha256,
        tracks,
        transport: this.soundtrackTransport(),
      });
    }
    this.effects = sealEffectVocabulary<PreparedGameplayEffect>(PLATFORMER_EFFECT_OPERATIONS, {
      grant_item: (effect) => {
        if (effect.operation !== "grant_item") return;
        this.addInventory(effect.item_id, effect.quantity);
      },
      set_quest_state: (effect) => {
        if (effect.operation !== "set_quest_state") return;
        this.questStates.set(effect.quest_id, effect.state);
      },
    });
    // The bag the run opens with: one of each, the same unit grant the room's
    // `grant_item` performs, which is why a set was ever enough over there.
    for (const itemId of this.gameplay.player.starting_item_ids) this.addInventory(itemId, 1);
    if (!hasHealingConsumable(manifest.items)) {
      // Playable, but only downhill: nothing in the package can put hit points back, so every run
      // ends at the respawn. Worth naming here rather than leaving it to be inferred from a
      // health bar that never rises.
      this.recordDiagnostic(
        "package ships no healing consumable; health can only be restored by respawning",
      );
    }
    const openingSpawn = this.gameplay.spawns.find(
      (spawn) => spawn.spawn_id === this.gameplay?.entry_spawn_id,
    );
    await this.enterMap(
      manifest.entry_map_id,
      openingSpawn?.normalized_x ?? 0.08,
      false,
    );
    this.createInterface(manifest);
    this.children.getByName("loading-label")?.destroy();
    this.ready = true;
    if (typeof window !== "undefined") {
      window.__sceneReady = true;
      this.publishProbe(manifest);
    }
  }

  /**
   * Republish the live probe.
   *
   * Called at load and again after a kit switch, so the probe answers what the run is being played
   * as *now* rather than what it was booted as. A frozen snapshot that silently went stale would
   * be worse than no probe: every check written against it would keep passing.
   */
  private publishProbe(manifest: PreparedRuntimeManifest): void {
    if (typeof window === "undefined") return;
    (window as unknown as { __preparedGame?: unknown }).__preparedGame = Object.freeze({
      manifestKind: manifest.kind,
      gameId: manifest.game_id,
      packageSha256: manifest.package_sha256,
      artifactCount: manifest.closure.artifact_count,
      mapIds: manifest.maps.map((map) => map.map_id),
      // The scale each player texture will draw at, exactly as resolved: the fastest way to
      // check on a live page that a published rebase actually reached the sprite.
      playerSheetScales: Object.freeze(
        Object.fromEntries(this.player ? this.player.resolvedSheetScales() : []),
      ),
      // The kit actually in force, after any developer override and after the weapon resolver
      // had its say. Reported for the same reason the sheet scales are: it is the fastest way to
      // check on a live page what the run is really being played as, and an override is
      // invisible from the outside otherwise. `kitOverridden` distinguishes a package that
      // throws from a package being *played* as one.
      weaponClass: this.weapon.weaponClass,
      projectileId: this.projectiles?.profile.projectileId ?? null,
      kitOverridden: this.developerKit !== null,
      diagnostics: Object.freeze([...this.diagnostics]),
      });
    (window as unknown as { __sceneProbes?: unknown }).__sceneProbes = {
      diagnostics: this.diagnostics,
      consoleErrors: [],
    };
  }

  private async loadPlayerAssets(manifest: PreparedRuntimeManifest): Promise<void> {
    await Promise.all(
      Object.entries(manifest.player.states).flatMap(([state, binding]) => {
        const adapter = preparedPlayerStateAdapter(state);
        if (!adapter) return [];
        const runtimeKey = adapter.texture_key;
        const url = this.url(binding.asset.path);
        return [
          this.loadPresentationOrFallback(
            loadFrameStrip(
              url,
              runtimeKey,
              binding.source_frame_count,
              this.textures,
              this.transparencyPolicy,
            ),
            runtimeKey,
            "four_frame_strip",
          ),
        ];
      }),
    );
    await this.loadGridOrFallback(
      loadGridSheet(
        this.url(manifest.player.dialogue.asset.path),
        "prepared_player_dialogue",
        manifest.player.dialogue.rows,
        manifest.player.dialogue.columns,
        "expression",
        this.textures,
        this.transparencyPolicy,
      ),
      "prepared_player_dialogue",
      manifest.player.dialogue.columns,
      manifest.player.dialogue.rows,
    );
  }

  private async loadMobAssets(manifest: PreparedRuntimeManifest): Promise<void> {
    const consumedStates = new Set(["idle", "hurt", "attack", "death"]);
    await Promise.all(
      manifest.mobs.flatMap((mob) =>
        Object.entries(mob.states).flatMap(([state, binding]) => {
          if (!consumedStates.has(state)) return [];
          const key = `prepared_mob_${mob.mob_id}_${state}`;
          return [
            this.loadPresentationOrFallback(
              loadFrameStrip(
                this.url(binding.asset.path),
                key,
                binding.source_frame_count,
                this.textures,
                this.transparencyPolicy,
              ),
              key,
              "four_frame_strip",
            ),
          ];
        }),
      ),
    );
  }

  private async loadNpcAssets(manifest: PreparedRuntimeManifest): Promise<void> {
    await Promise.all(
      manifest.npcs.flatMap((npc) => {
        const worldKey = `prepared_npc_${npc.npc_id}_world`;
        const dialogueKey = `prepared_npc_${npc.npc_id}_dialogue`;
        return [
          this.loadPresentationOrFallback(
            loadFrameStrip(
              this.url(npc.world.asset.path),
              worldKey,
              npc.world.source_frame_count,
              this.textures,
              this.transparencyPolicy,
            ),
            worldKey,
            "four_frame_strip",
          ),
          this.loadGridOrFallback(
            loadGridSheet(
              this.url(npc.dialogue.asset.path),
              dialogueKey,
              npc.dialogue.rows,
              npc.dialogue.columns,
              "expression",
              this.textures,
              this.transparencyPolicy,
            ),
            dialogueKey,
            npc.dialogue.columns,
            npc.dialogue.rows,
          ),
        ];
      }),
    );
  }

  private async loadCatalogAssets(manifest: PreparedRuntimeManifest): Promise<void> {
    await Promise.all([
      ...manifest.props.map((prop) => {
        const key = `prepared_prop_${prop.prop_id}`;
        return this.loadPresentationOrFallback(
          loadTransparentSprite(
            this.url(prop.asset.path),
            key,
            this.textures,
            this.transparencyPolicy,
          ),
          key,
          "sprite",
        );
      }),
      ...manifest.items.map((item) => {
        const key = `prepared_item_${item.item_id}`;
        return this.loadPresentationOrFallback(
          loadTransparentSprite(
            this.url(item.asset.path),
            key,
            this.textures,
            this.transparencyPolicy,
          ),
          key,
          "sprite",
        );
      }),
      // Trimmed, unlike every other catalog sprite, and it is the one family that needs it. A
      // whole-canvas texture makes a display size a statement about the canvas: the subject then
      // draws smaller than its calibration says, and the origin used for rotation is the middle of
      // the empty frame rather than the middle of the object.
      ...manifest.projectiles.map((projectile) => {
        const key = preparedProjectileTextureKey(projectile.projectile_id);
        return this.loadPresentationOrFallback(
          loadTrimmedSprite(
            this.url(projectile.asset.path),
            key,
            this.textures,
            this.transparencyPolicy,
          ),
          key,
          "sprite",
        );
      }),
    ]);
  }

  private async loadUiAssets(manifest: PreparedRuntimeManifest): Promise<void> {
    await this.loadPresentationOrFallback(
      loadTransparentSprite(
        this.url(manifest.ui.inventory_panel.asset.path),
        "inventory",
        this.textures,
        this.transparencyPolicy,
      ),
      "inventory",
      "inventory_panel",
    );
    await Promise.all(
      UI_ATLAS_SHEETS.map(([role, key, kind]) =>
        this.loadPresentationOrFallback(
          loadTransparentSprite(
            this.url(manifest.ui[role].asset.path),
            key,
            this.textures,
            this.transparencyPolicy,
          ),
          key,
          kind,
        ),
      ),
    );
  }

  private async loadMapTextures(manifest: PreparedRuntimeManifest): Promise<void> {
    await Promise.all(
      manifest.maps.flatMap((map) => {
        const walkSurfaceY = preparedWalkSurfaceY(map, TILE_PX, VIEW_H);
        return [
          ...map.layers.map((layer) => {
            const key = `prepared_map_${map.map_id}_${layer.layer_id}`;
            const layout = preparedLayerLayout(layer.placement, {
              viewportHeight: VIEW_H,
              walkSurfaceY,
              parallax: layer.parallax,
            });
            return this.loadPresentationOrFallback(
              loadVerifiedRepeatLayer(
                this.url(layer.asset.path),
                key,
                layer.alpha_mode === "opaque",
                layer.asset.width ?? 1536,
                this.textures,
              ).then((loaded) => {
                presentPreparedLayerCanvas(
                  loaded.canvas,
                  layer.presentation,
                  1 / layout.scale,
                );
                registerCanvas(this.textures, key, loaded.canvas);
              }),
              key,
              "sprite",
            );
          }),
          this.loadGroundOrFallback(map),
          ...(map.climbable
            ? [
                this.loadPresentationOrFallback(
                  loadTrimmedSprite(
                    this.url(map.climbable.asset.path),
                    `prepared_climbable_${map.map_id}`,
                    this.textures,
                    this.transparencyPolicy,
                  ),
                  `prepared_climbable_${map.map_id}`,
                  "sprite",
                ),
              ]
            : []),
          ...(map.portal
            ? [
                this.loadPresentationOrFallback(
                  loadTransparentSprite(
                    this.url(map.portal.asset.path),
                    `prepared_portal_${map.map_id}`,
                    this.textures,
                    this.transparencyPolicy,
                  ),
                  `prepared_portal_${map.map_id}`,
                  "portal_sheet",
                ),
              ]
            : []),
        ];
      }),
    );
  }

  /** Texture key for one painted segment's full-grid raster. */
  private paintedGroundKey(map: PreparedMap, segmentId: string): string {
    return `prepared_ground_${map.map_id}_${segmentId}`;
  }

  private async loadGroundOrFallback(map: PreparedMap): Promise<void> {
    const key = `prepared_ground_${map.map_id}`;
    try {
      if (map.ground.mode === "painted-terrain-v1") {
        // Each segment is one bespoke full-grid raster, so there is no atlas geometry to
        // assert and no lookup to satisfy - only that the raster is the size its own
        // declared window says it is.
        const ground = map.ground;
        for (const segment of ground.segments) {
          const segmentKey = this.paintedGroundKey(map, segment.segment_id);
          const canvas = await loadTransparentSprite(
            this.url(segment.asset.path),
            segmentKey,
            this.textures,
            this.transparencyPolicy,
          );
          const expectedWidth = segment.columns * ground.cell_px;
          const expectedHeight = ground.occupancy.length * ground.cell_px;
          if (canvas.width !== expectedWidth || canvas.height !== expectedHeight) {
            throw new Error(
              `painted terrain ${segment.segment_id} must be exactly ${expectedWidth}x${expectedHeight}`,
            );
          }
        }
        return;
      }
      await loadTerrainAtlas(
        this.url(map.ground.asset.path),
        key,
        this.textures,
        this.transparencyPolicy,
      );
    } catch (error) {
      if (this.textures.exists(key)) this.textures.remove(key);
      this.recordDiagnostic(
        `Ground presentation for ${map.map_id} failed to load: ${
          error instanceof Error ? error.message : String(error)
        }`,
      );
      registerPresentationFallback(
        this.textures,
        `${key}_fallback`,
        "sprite",
        (message) => this.recordDiagnostic(message),
      );
    }
  }

  /** Keep gameplay constructible when optional presentation roles were not generated. */
  private prepareGameplayPresentation(manifest: PreparedRuntimeManifest): void {
    const report = (message: string) => this.recordDiagnostic(message);
    for (const key of [
      "character_idle",
      "character_walk",
      "character_run",
      "character_jump",
      "character_climb_ladder",
      "character_climb_rope",
      "character_attack",
      "character_skill_cast",
      "character_hurt",
      "character_death",
    ]) {
      if (!this.textures.exists(key)) {
        registerPresentationFallback(this.textures, key, "four_frame_strip", report);
      }
    }
    if (!this.textures.exists("character_crawl")) {
      registerPresentationFallback(
        this.textures,
        "character_crawl",
        "four_frame_strip",
        report,
      );
    }
    if (!this.textures.exists("inventory")) {
      registerPresentationFallback(
        this.textures,
        "inventory",
        "inventory_panel",
        report,
      );
    }
    for (const [, key, kind] of UI_ATLAS_SHEETS) {
      if (!this.textures.exists(key)) {
        registerPresentationFallback(this.textures, key, kind, report);
      }
    }
    // Sheet scale is no longer reconstructed from frame bounds here. A whole-frame extent
    // is exactly what cannot separate a short pose from a small drawing, so the producer
    // judges every atlas against the baseline and publishes the ratio instead.
    if (manifest.player.states.crouch === undefined) {
      this.recordDiagnostic(
        "Player crouch mechanics use a runtime placeholder because no crouch strip was generated.",
      );
    }
  }

  /**
   * Drive the player from a script instead of the keyboard.
   *
   * The seam `player-intent.ts` was written for, finally connected to something: a replay or a demo
   * answers with this frame's intent and the controller cannot tell it from a person. It reaches the
   * controller only — the scene's own latched keys (talk, enter a portal, confirm a death) are not
   * part of `PlayerIntent` and are still pressed on the keyboard.
   */
  driveWithIntent(source: ScenePlayerIntentSource | null): void {
    this.intentSource = source ?? undefined;
  }

  /** Everything the runtime named this frame, in the order it named it. */
  get transcript(): readonly GameplayTranscriptEvent[] {
    return this.frameEvents;
  }

  private recordEvent(
    kind: string,
    data: Readonly<Record<string, string | number | boolean>> | null = null,
  ): void {
    // Bounded so a pathological frame cannot make one entry of the golden unbounded.
    if (this.frameEvents.length >= 64) return;
    this.frameEvents.push(
      Object.freeze({
        kind,
        frame: this.transcriptFrame,
        simulationMs: Math.round(this.time.now),
        data,
      }),
    );
  }

  private recordDiagnostic(message: string): void {
    const bounded = message.trim().slice(0, 256);
    if (!bounded || this.diagnostics.includes(bounded)) return;
    this.diagnostics.push(bounded);
    console.warn(`[prepared-scene] ${bounded}`);
  }

  private async loadPresentationOrFallback(
    operation: Promise<unknown>,
    key: string,
    kind: PresentationFallbackKind,
  ): Promise<void> {
    try {
      await operation;
    } catch {
      registerPresentationFallback(
        this.textures,
        key,
        kind,
        (message) => this.recordDiagnostic(message),
      );
    }
  }

  private async loadGridOrFallback(
    operation: Promise<unknown>,
    key: string,
    columns: number,
    rows: number,
  ): Promise<void> {
    try {
      await operation;
    } catch {
      registerGridPresentationFallback(
        this.textures,
        key,
        columns,
        rows,
        "expression",
        (message) => this.recordDiagnostic(message),
      );
    }
  }

  /**
   * The class this run is being played with: the developer's if one is set, otherwise the package's.
   *
   * Deliberately not `??`. A kit is a pair, and an override of `melee_dps_v1` carries a null round
   * that must win over the package's named one - a coalescing read would leave a swinging character
   * still holding a throwing package's projectile.
   */
  private activeWeaponClass(gameplay: PreparedGameplayContract): WeaponClass | null {
    return this.developerKit ? this.developerKit.weaponClass : gameplay.combat.weapon_class;
  }

  private activeProjectileId(gameplay: PreparedGameplayContract): string | null {
    return this.developerKit ? this.developerKit.projectileId : gameplay.combat.projectile_id;
  }

  /**
   * Settle which class this run fights with, before anything reads it.
   *
   * The decision itself is `resolveWeaponClassProfile`, next to the table it chooses from; this
   * method only supplies what the manifest published, what the developer selected, and where
   * diagnostics go. Resolved before the controller, the strike resolver, the projectile pool and
   * the bot band are built, so all four agree by construction - and re-run on a kit switch, which
   * is why the switch re-enters the map rather than patching those four in place.
   */
  private resolveWeaponClass(
    manifest: PreparedRuntimeManifest,
    gameplay: PreparedGameplayContract,
  ): void {
    this.selectableKits = selectableDeveloperKits({
      publishedWeaponClass: gameplay.combat.weapon_class ?? "melee_dps_v1",
      publishedProjectileId: gameplay.combat.projectile_id,
      projectileCatalog: manifest.projectiles,
      publishedMotionStates: manifest.player.states,
    });
    this.weapon = resolveWeaponClassProfile({
      weaponClass: this.activeWeaponClass(gameplay),
      combatEnabled: gameplay.combat.enabled,
      publishedMotionStates: manifest.player.states,
      projectileNamed: this.activeProjectileId(gameplay) !== null,
      recordDiagnostic: (message) => this.recordDiagnostic(message),
    });
    // Resolution order: the class names its round, otherwise the first catalog entry carrying the
    // role. Null means the class spends nothing, which is what ships today.
    this.ammoItemId =
      this.weapon.ammoKind === null
        ? null
        : selectAmmoItemId(manifest.items);
  }

  /**
   * Give a throwing class somewhere to put its shots.
   *
   * Nothing is constructed for a class that does not throw, so a melee package allocates no pool,
   * loads no extra texture and runs no extra pass. The sprite comes from the catalog item the
   * contract names and is drawn through that item's own calibration, so a thrown object is the
   * size the package says it is rather than a constant this file picked.
   */
  private installProjectiles(manifest: PreparedRuntimeManifest): void {
    const gameplay = this.gameplay;
    if (this.weapon.delivery.kind !== "projectile" || !gameplay) return;
    const published = manifest.projectiles.find(
      (entry) => entry.projectile_id === this.activeProjectileId(gameplay),
    );
    // Unreachable for a package the closure check passed, which proves a named projectile is in
    // the catalog. Kept because `find` can answer undefined and a silent pool of nothing is the
    // failure mode this whole family exists to make impossible.
    if (!published) return;
    this.projectiles = new ProjectileSystem({
      scene: this,
      tilePx: TILE_PX,
      textureKey: preparedProjectileTextureKey(published.projectile_id),
      // The subject's own length, from its own calibration, against a trimmed texture — so the
      // number is the artwork's size rather than the canvas it was generated on.
      drawnLengthPx: drawnExtentPx(published.calibration, manifest.scale, TILE_PX),
      projectile: projectileProfile(published),
      world: {
        minX: 0,
        maxX: this.worldWidth,
        surfaceYAt: (x) => this.surfaceYAtX(x),
      },
    });
  }

  private installAnimations(manifest: PreparedRuntimeManifest): void {
    for (const mob of manifest.mobs) {
      for (const state of ["idle", "attack", "hurt", "death"] as const) {
        const binding = mob.states[state];
        if (!binding) continue;
        const texture = `prepared_mob_${mob.mob_id}_${state}`;
        installPreparedMotion(this, texture, state, binding);
      }
    }
    for (const npc of manifest.npcs) {
      const key = `prepared_npc_${npc.npc_id}_world`;
      installPreparedMotion(this, key, "idle", npc.world);
    }
  }

  private installInput(): void {
    const keyboard = this.input.keyboard;
    if (keyboard) {
      this.keys = {
        jump: keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.SPACE),
        up: keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.UP),
        w: keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.W),
        interact: keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.E),
        enter: keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.ENTER),
        debugOverlay: keyboard.addKey(
          Phaser.Input.Keyboard.KeyCodes.BACKTICK,
        ),
        autoPlay: keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.P),
        switchKit: keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.K),
      };
      this.choiceKeys = DIALOGUE_CHOICE_KEYCODES.map((code) => keyboard.addKey(code));
    }
    const startAudio = () => {
      // The player owns the gate: it answers true exactly once, on the gesture that actually
      // starts playback, so both listeners retire themselves on that answer and on no other.
      if (this.soundtrackPlayer?.beginFromPlayerGesture() !== true) return;
      keyboard?.off("keydown", startAudio);
      this.input.off(Phaser.Input.Events.POINTER_DOWN, startAudio);
    };
    keyboard?.on("keydown", startAudio);
    this.input.on(Phaser.Input.Events.POINTER_DOWN, startAudio);
  }

  private async enterMap(mapId: string, normalizedX: number, announce = true): Promise<void> {
    const manifest = this.manifest;
    const gameplay = this.gameplay;
    if (!manifest || !gameplay) return;
    const map = manifest.maps.find((entry) => entry.map_id === mapId);
    if (!map) throw new Error(`runtime transition names unknown map ${mapId}`);
    this.groundBaselineY = preparedGroundBaselineY(map, VIEW_H);
    const terrainWorld = projectPreparedTerrainWorld(
      map,
      TILE_PX,
      this.groundBaselineY,
    );
    this.loading = true;
    this.currentMap = map;
    this.clearWorld();
    this.terrainWorld = terrainWorld;
    this.worldWidth = terrainWorld.worldWidth;
    this.heights = terrainWorld.heights;
    this.verticalWorld = terrainWorld.verticalWorld;
    this.renderMap(map);
    this.installVerticalWorld(map);
    this.renderPlacements(map);
    // Built here rather than per frame: the graph describes terrain and declared geometry, and
    // neither moves while a map is being played. Built after the vertical world is installed,
    // because the decks and climbable zones it links are part of what it describes.
    this.navGraph = preparedNavGraph({
      heights: this.heights,
      tileUnits: TILE_PX,
      baselineY: this.groundBaselineY,
      platforms: this.verticalWorld.platforms,
      climbables: this.verticalWorld.climbables,
      capabilities: HUNTER_BOT_PROFILE.capabilities,
    });
    this.bot?.reset();
    const startX = Phaser.Math.Clamp(
      normalizedX * this.worldWidth,
      TILE_PX / 2,
      this.worldWidth - TILE_PX / 2,
    );
    this.player = new Player({
      scene: this,
      startX,
      startY: this.surfaceYAtX(startX),
      tilePx: TILE_PX,
      worldWidthPx: this.worldWidth,
      baselineY: this.groundBaselineY,
      heightFn: (column) => this.heightAt(column),
      targetSpriteHeight: PLAYER_HEIGHT,
      platforms: this.verticalWorld.platforms,
      climbables: this.verticalWorld.climbables,
      maximumAirJumps: 1,
      combatEnabled: gameplay.combat.enabled,
      weaponClass: this.weapon,
      // The level's pool, not the authored one. A map change and a respawn both rebuild the
      // controller, and a player who levelled twice must not walk through a door back to six HP.
      startingHealth:
        this.progression?.maximumHealth ?? gameplay.player.starting_health,
      motionPlayback: preparedPlayerMotionPlayback(manifest.player.states),
      climbArtwork: preparedPlayerClimbArtwork(manifest.player.states),
      scaleReferences: this.scaleReferences,
      preserveSourceScaleStates:
        PREPARED_PLAYER_PRESERVE_SOURCE_SCALE_STATES,
      stateRebase: preparedPlayerStateRebase(manifest.player.calibration),
    });
    this.addContactShadow(this.player.sprite);
    this.items = new ItemSystem({
      scene: this,
      tilePx: TILE_PX,
      baselineY: this.groundBaselineY,
      heightFn: (column) => this.heightAt(column),
      itemTextureKey: (index) => preparedItemTextureKey(manifest, index),
      worldWidthPx: this.worldWidth,
    });
    this.installProjectiles(manifest);
    this.installPortals(map);
    if (map.hostile_population_enabled) this.initializeMobPopulation(map);
    // The map declares which axes the camera may follow and the scene obeys, rather than the
    // scene assuming a shape every map has to fit. The follow itself is unconditional - Phaser
    // has always been asked to track both axes with the same dead zone - so an axis is enabled or
    // disabled purely by the world box the camera is allowed to move inside. Without a vertical
    // axis that box is exactly one viewport tall, which is what pins the camera to the floor.
    const bounds = followBounds({
      followAxes: map.camera.follow_axes,
      worldWidth: this.worldWidth,
      topY: terrainWorld.topY,
      baselineY: this.groundBaselineY,
      viewportHeight: VIEW_H,
    });
    // Bounds, follow offset and dead zone are Phaser midpoint helpers: they place the visible
    // center half a canvas right of the scroll, which the device-zoom camera's top-left origin
    // no longer does. Each is shifted by the same offset so the framing the map asked for holds
    // at every device pixel ratio; at ratio one the offset is zero and nothing moves.
    const camera = this.cameras.main;
    const midpoint = midpointOffset(camera, VIEWPORT);
    const worldBox = deviceCameraBounds(bounds, midpoint);
    const followOffset = deviceFollowOffset(PLAYER_FOLLOW_OFFSET, midpoint);
    camera.setBounds(worldBox.x, worldBox.y, worldBox.width, worldBox.height);
    camera.startFollow(this.player.sprite, true, 0.12, 0.12, followOffset.x, followOffset.y);
    camera.setDeadzone(300, 180);
    // Phaser's snap on follow start is midpoint-based as well; land the first frame where the
    // dead zone would otherwise drag the camera over the following half second.
    const snap = centeredScroll(this.player.sprite, PLAYER_FOLLOW_OFFSET, VIEWPORT);
    camera.setScroll(snap.scrollX, snap.scrollY);
    if (!map.camera.follow_axes.includes("y")) camera.scrollY = 0;
    this.mapLabel?.setText(map.display_name);
    this.selectSoundtrack(map);
    this.loading = false;
    this.recordEvent("map-entered", { mapId: map.map_id, startX: Math.round(startX) });
    if (announce) this.flashMapName(map.display_name);
  }

  private clearWorld(): void {
    this.mobPopulationDirector?.dispose();
    this.mobPopulationDirector = undefined;
    this.mobPopulationMapId = undefined;
    this.mobIdByPopulationSlot = [];
    this.mobInstanceIds.clear();
    this.mobBotIds.clear();
    this.navGraph = EMPTY_NAV_GRAPH;
    this.player?.destroy();
    this.player = undefined;
    for (const binding of this.contactShadows) {
      for (const ring of binding.rings) ring.destroy();
    }
    this.contactShadows = [];
    for (const sprite of [
      ...this.layerSprites,
      ...this.groundSprites,
      ...this.props,
      ...this.worldLabels,
    ])
      sprite.destroy();
    for (const mob of this.mobs) mob.destroy();
    for (const npc of this.npcs) npc.sprite.destroy();
    this.items?.clearAll();
    this.items = undefined;
    this.projectiles?.clearAll();
    this.projectiles = undefined;
    this.combatText?.clear();
    this.carryCameraShake(NO_SHAKE);
    this.impact?.clear();
    this.statLog?.clear();
    this.portal?.destroy();
    this.portal = undefined;
    for (const sprite of this.verticalSprites) sprite.destroy();
    this.layerSprites = [];
    this.groundSprites = [];
    this.props = [];
    this.worldLabels = [];
    this.mobs = [];
    this.npcs = [];
    this.verticalSprites = [];
    this.verticalWorld = Object.freeze({ platforms: Object.freeze([]), climbables: Object.freeze([]) });
  }

  private renderMap(map: PreparedMap): void {
    const ordered = [...map.layers].sort((left, right) => {
      const plane = left.plane === right.plane ? 0 : left.plane === "background" ? -1 : 1;
      return plane || left.order - right.order;
    });
    const walkSurfaceY = preparedWalkSurfaceY(map, TILE_PX, VIEW_H);
    ordered.forEach((layer, index) => {
      const key = `prepared_map_${map.map_id}_${layer.layer_id}`;
      const layout = preparedLayerLayout(layer.placement, {
        viewportHeight: VIEW_H,
        walkSurfaceY,
        parallax: layer.parallax,
      });
      const sprite = this.add.tileSprite(
        0,
        layout.topY,
        VIEW_W / layout.scale,
        layout.sourceHeight,
        key,
      );
      sprite
        .setOrigin(0, 0)
        .setScale(layout.scale)
        // X is always screen-locked because horizontal parallax is applied as a texture offset
        // below rather than as position. Y cannot be, because a layer is exactly one texture
        // tall and has nothing to slide inside, so depth on this axis is position and the
        // factor is the layer's own parallax. Every layer renders identically while the camera
        // rests at the bottom of the world, which is why a map that never scrolls vertically
        // sees no change at all.
        .setScrollFactor(0, layout.verticalScrollFactor)
        .setDepth(layer.plane === "foreground" ? 80 + index : index - 20)
        .setData("parallax", layer.parallax);
      this.layerSprites.push(sprite);
    });
    const groundKey = `prepared_ground_${map.map_id}`;
    const terrainWorld = this.terrainWorld;
    if (!terrainWorld) {
      throw new Error("prepared map render requires projected terrain geometry");
    }
    if (map.ground.mode === "painted-terrain-v1") {
      // One image per segment at its own start column, and nothing else. There is no
      // walk-surface inset and no boundary overscan: the atlas needs both because its
      // cells are transparent above the cap and along a boundary contour, while a painted
      // segment already fills its cells and already overhangs them by as much as the
      // published silhouette band allows.
      const ground = map.ground;
      const everySegmentLoaded = ground.segments.every((segment) =>
        this.textures.exists(this.paintedGroundKey(map, segment.segment_id)),
      );
      if (everySegmentLoaded) {
        for (const segment of ground.segments) {
          this.groundSprites.push(
            this.add
              .image(
                segment.start_column * TILE_PX,
                terrainWorld.topY,
                this.paintedGroundKey(map, segment.segment_id),
              )
              .setOrigin(0, 0)
              .setDisplaySize(
                segment.columns * TILE_PX,
                ground.occupancy.length * TILE_PX,
              )
              .setDepth(10),
          );
        }
        return;
      }
      // Fall through to the flat fallback below, which is keyed off the map rather than
      // off a segment and so serves either discipline.
    }
    if (this.textures.exists(groundKey)) {
      const visibleSurfaceOffset = terrainAtlasWalkSurfaceOffset(TILE_PX);
      for (const cell of terrainAtlasBoundaryOverscanPlan(
        terrainWorld.occupancy,
      )) {
        const sprite = this.add
          .image(
            cell.mapColumn * TILE_PX,
            terrainWorld.topY + cell.mapRow * TILE_PX - visibleSurfaceOffset,
            groundKey,
            cell.frame,
          )
          .setOrigin(0, 0)
          .setDisplaySize(TILE_PX, TILE_PX)
          .setDepth(10);
        this.groundSprites.push(sprite);
      }
    } else {
      for (const cell of terrainAtlasBoundaryOverscanPlan(
        terrainWorld.occupancy,
      )) {
        this.groundSprites.push(
          this.add
            .image(
              cell.mapColumn * TILE_PX,
              terrainWorld.topY + cell.mapRow * TILE_PX,
              `${groundKey}_fallback`,
            )
            .setOrigin(0, 0)
            .setDisplaySize(TILE_PX, TILE_PX)
            .setDepth(10),
        );
      }
    }
  }

  private renderPlacements(map: PreparedMap): void {
    const manifest = this.manifest;
    const gameplay = this.gameplay;
    if (!manifest || !gameplay) return;
    for (const placement of gameplay.prop_placements.filter((entry) => entry.map_id === map.map_id)) {
      const prop = manifest.props.find((entry) => entry.prop_id === placement.prop_id);
      if (!prop) continue;
      const x = placement.normalized_x * this.worldWidth;
      const sprite = this.add
        .image(x, this.surfaceYAtX(x), `prepared_prop_${prop.prop_id}`)
        .setOrigin(0.5, prop.ground_contact_y_normalized)
        .setDepth(25);
      const height = prop.prop_id.includes("stall") ? 170 : 110;
      sprite.setDisplaySize(Math.min(220, (sprite.width / sprite.height) * height), height);
      this.props.push(sprite);
      this.addContactShadow(sprite);
    }
    for (const placement of gameplay.npc_placements.filter((entry) => entry.map_id === map.map_id)) {
      const npc = manifest.npcs.find((entry) => entry.npc_id === placement.npc_id);
      if (!npc) continue;
      const x = placement.normalized_x * this.worldWidth;
      const surfaceY = this.surfaceYAtX(x);
      const sprite = this.add
        .sprite(x, surfaceY, `prepared_npc_${npc.npc_id}_world`, 0)
        .setOrigin(0.5, 1)
        .setDepth(35);
      applyMotionPlayback(
        sprite,
        `prepared_npc_${npc.npc_id}_world`,
        `prepared_npc_${npc.npc_id}_world`,
        npc.world.playback,
      );
      scaleSpriteFrameToHeight(sprite, NPC_HEIGHT);
      anchorRepackedMotionFeet(sprite);
      this.addContactShadow(sprite);
      const label = this.add
        .text(sprite.x, surfaceY - NPC_HEIGHT - 12, npc.display_name, {
          fontFamily: "system-ui, sans-serif",
          fontSize: "15px",
          color: "#fff7dc",
          stroke: "#283b46",
          strokeThickness: 4,
        })
        .setOrigin(0.5, 1)
        .setDepth(36);
      const talkPrompt = this.add
        .text(
          sprite.x,
          label.y - label.displayHeight - NPC_TALK_PROMPT_GAP_PX,
          NPC_TALK_PROMPT_TEXT,
          NPC_TALK_PROMPT_STYLE,
        )
        .setOrigin(0.5, 1)
        .setScrollFactor(1)
        .setDepth(SCENE_CONTENT_DEPTH.effect)
        .setVisible(false);
      this.npcs.push({ npcId: npc.npc_id, sprite, talkPrompt });
      this.worldLabels.push(label, talkPrompt);
    }
  }

  private installVerticalWorld(map: PreparedMap): void {
    const atlasKey = `prepared_climbable_${map.map_id}`;
    const byVariant = new Map(
      (map.climbable?.variants ?? []).map((entry) => [entry.variant_id, entry]),
    );
    if (this.textures.exists(atlasKey)) {
      const texture = this.textures.get(atlasKey);
      for (const frame of climbableAtlasFrames(map)) {
        // Replace rather than skip, as the portal does, so a re-entered map can never draw a
        // frame whose geometry belongs to an earlier texture.
        if (texture.has(frame.frameKey)) texture.remove(frame.frameKey);
        texture.add(frame.frameKey, 0, frame.x, frame.y, frame.width, frame.height);
      }
    }
    for (const ladder of this.verticalWorld.climbables) {
      const bounds = ladderVisualBounds(ladder);
      const variant = byVariant.get(ladder.variantId);
      if (!variant) {
        throw new Error(`prepared climbable zone ${ladder.id} names an undeclared variant`);
      }
      // Draw the variant's own frame. Masking the shared atlas instead would leave origin and
      // display size bound to the full texture, so the artwork would land at the wrong size and
      // off-centre from the zone the player actually climbs.
      const sprite = this.add
        .image(ladder.centerX, bounds.bottom, atlasKey, climbableFrameKey(ladder.variantId))
        .setOrigin(0.5, 1)
        .setDepth(23);
      sprite.setDisplaySize(bounds.width, bounds.height);
      this.verticalSprites.push(sprite);
    }
  }

  private heightAt(column: number): number {
    const index = Phaser.Math.Clamp(Math.floor(column), 0, this.heights.length - 1);
    return this.heights[index] ?? 1;
  }

  /**
   * The decks a body could stand on in one column, lowest first.
   *
   * A column is measured at its center, the same point a spawn is placed at and the same test
   * `platformAtX` makes, so a deck counts here exactly when a creature placed in this column
   * would land on it.
   */
  private deckFootingsAtColumn(column: number): readonly PreparedDeckFooting[] {
    const centerX = column * TILE_PX + TILE_PX / 2;
    return this.verticalWorld.platforms
      .filter((platform) => centerX >= platform.left && centerX <= platform.right)
      .map((platform) =>
        Object.freeze({ deck_id: platform.id, surface_y: platform.deckY }),
      )
      .sort((left, right) => right.surface_y - left.surface_y);
  }

  /** Resolve a deck the spawn director named into the geometry a mob is bound by. */
  private deckFooting(deckId: string): MobDeckFooting | null {
    const platform = this.verticalWorld.platforms.find((entry) => entry.id === deckId);
    if (!platform) return null;
    return Object.freeze({
      id: platform.id,
      leftX: platform.left,
      rightX: platform.right,
      surfaceY: platform.deckY,
    });
  }

  private surfaceYAtX(x: number): number {
    return terrainSurfaceY(
      this.heightAt(x / TILE_PX),
      TILE_PX,
      this.groundBaselineY,
    );
  }

  private installPortals(map: PreparedMap): void {
    const gameplay = this.gameplay;
    const manifest = this.manifest;
    if (!gameplay || !manifest || !map.portal) return;
    const portalKey = `prepared_portal_${map.map_id}`;
    const endpoints = preparedPortalEndpointPlacements({
      map,
      maps: manifest.maps,
      transitions: gameplay.transitions,
      worldWidth: this.worldWidth,
      portalKey,
    });
    this.portal = new PortalSystem({
      scene: this,
      portalKey,
      tilePx: TILE_PX,
      baselineY: this.groundBaselineY,
      heightFn: (column) => this.heightAt(column),
      stageWidthPx: this.worldWidth,
      destinations: { entry: null, exit: null },
      endpoints,
    });
  }

  private transitionForPortal(
    destinationMapId: string,
    portalId: string,
  ): PreparedGameplayContract["transitions"][number] | undefined {
    return this.gameplay?.transitions.find(
      (transition) =>
        transition.from_map_id === this.currentMap?.map_id &&
        transition.to_map_id === destinationMapId &&
        transition.from_anchor === portalId,
    );
  }

  private createMobAtColumn(
    mobSlot: number,
    spawnColumn: number,
    behaviorSeed?: number,
    spawnedAtMs?: number,
    deck?: MobDeckFooting,
  ): Mob | null {
    const spec = this.manifest?.mobs[mobSlot];
    if (!spec) return null;
    const idleKey = `prepared_mob_${spec.mob_id}_idle`;
    const hurtKey = `prepared_mob_${spec.mob_id}_hurt`;
    if (!this.textures.exists(idleKey)) return null;
    const idleFrame = this.textures.get(idleKey).get(0);
    const hurtFrame = this.textures.exists(hurtKey)
      ? this.textures.get(hurtKey).get(0)
      : idleFrame;
    const renderEnvelope = mobRenderEnvelope({
      idleFrames: [
        {
          w: Math.max(1, idleFrame?.width ?? 64),
          h: Math.max(1, idleFrame?.height ?? 64),
        },
      ],
      hurtFrames: [
        {
          w: Math.max(1, hurtFrame?.width ?? idleFrame?.width ?? 64),
          h: Math.max(1, hurtFrame?.height ?? idleFrame?.height ?? 64),
        },
      ],
      targetFrameZeroHeight: MOB_HEIGHT,
    });
    const attackKey = `prepared_mob_${spec.mob_id}_attack`;
    const deathKey = `prepared_mob_${spec.mob_id}_death`;
    // The package may name the archetype; a rank maps to one otherwise. Common creatures are
    // prey - the hunting-ground read, where most of what stands on the route is there to be
    // hunted and hurts only on contact - and the threat ladder climbs with the rank.
    const aggression =
      parseAggression(spec.aggression) ??
      (spec.rank === "boss"
        ? "relentless"
        : spec.rank === "elite"
          ? "hunting"
          : spec.rank === "uncommon"
            ? "territorial"
            : "passive");
    const mob = new Mob({
      scene: this,
      ladderIndex: mobSlot,
      startingHealth: scaleMobHealth(mobHealthForRank(spec.rank), this.numberScale),
      spawnCol: spawnColumn,
      tilePx: TILE_PX,
      worldWidthPx: this.worldWidth,
      baselineY: this.groundBaselineY,
      heightFn: (column) => this.heightAt(column),
      deck,
      spriteHeightPx: spec.rank === "boss" ? MOB_HEIGHT * 1.45 : MOB_HEIGHT,
      idleAnimKey: idleKey,
      hurtTextureKey: this.textures.exists(hurtKey) ? hurtKey : idleKey,
      renderEnvelope,
      aggression,
      attackTextureKey: this.textures.exists(attackKey) ? attackKey : undefined,
      deathTextureKey: this.textures.exists(deathKey) ? deathKey : undefined,
      behaviorSeed,
      spawnedAtMs,
      // Simulation time, never the engine's. A knockback tween and a death timer are stepped by
      // whatever wall-clock delta the browser handed the loop, so the same run recorded twice puts
      // a corpse in two different places; `sampleFixedMobHit` reproduces the identical ease and
      // fade from `nowMs`, which is the clock the rest of this frame is already resolved against.
      fixedStepMotion: true,
    });
    this.addContactShadow(mob.sprite);
    // Identity for anything that has to follow one mob across frames. The director's own instance
    // ids cover only the mobs it manages, and array position is reused the moment one dies.
    this.mobBotIds.set(mob, `mob_${this.nextMobBotId}`);
    this.nextMobBotId += 1;
    return mob;
  }

  private addContactShadow(target: ContactShadowTarget): void {
    const style = this.manifest?.presentation.contact_shadows;
    if (!style?.enabled || style.opacity <= 0) return;
    const ringAlpha = [0.22, 0.32, 0.46] as const;
    const rings = ringAlpha.map((alpha) =>
      this.add
        .ellipse(0, 0, 8, 4, 0x172520, style.opacity * alpha)
        .setDepth(24),
    );
    this.contactShadows.push(Object.freeze({ target, rings: Object.freeze(rings) }));
    this.updateContactShadows();
  }

  private updateContactShadows(): void {
    const style = this.manifest?.presentation.contact_shadows;
    if (!style?.enabled) return;
    const spreadFactors = [1.5, 0.75, 0.15] as const;
    const alphaFactors = [0.22, 0.32, 0.46] as const;
    const retained: ContactShadowBinding[] = [];
    for (const binding of this.contactShadows) {
      const { target } = binding;
      if (!target.active) {
        for (const ring of binding.rings) ring.destroy();
        continue;
      }
      retained.push(binding);
      const visible = target.active && target.visible;
      const surfaceY = this.surfaceYAtX(target.x);
      const airbornePixels = Math.max(0, surfaceY - target.y);
      const distanceScale = Math.max(0.55, 1 - airbornePixels / 480);
      const distanceAlpha = Math.max(0.35, 1 - airbornePixels / 360);
      const baseWidth = Phaser.Math.Clamp(target.displayWidth * 0.58 * distanceScale, 28, 150);
      const baseHeight = Phaser.Math.Clamp(baseWidth * 0.12, 5, 18);
      binding.rings.forEach((ring, index) => {
        const spread = style.softness_screen_pixels * spreadFactors[index]!;
        ring
          .setPosition(target.x, surfaceY + 2)
          .setDisplaySize(baseWidth + spread * 2, baseHeight + spread)
          .setAlpha(style.opacity * alphaFactors[index]! * distanceAlpha)
          .setVisible(visible);
      });
    }
    this.contactShadows = retained;
  }

  private initializeMobPopulation(map: PreparedMap): void {
    const gameplay = this.gameplay;
    const manifest = this.manifest;
    if (!gameplay || !manifest) return;
    const reservedColumns = reservedSpawnColumns({
      worldColumns: this.heights.length,
      portalAnchorFractions: (map.portal?.endpoints ?? []).map(
        (endpoint) => endpoint.normalized_x,
      ),
    });
    const projection = projectPreparedMobPopulation(
      gameplay.mob_population,
      map.map_id,
      {
        world_columns: this.heights.length,
        tile_pixels: TILE_PX,
        baseline_y: this.groundBaselineY,
        height_at_column: (column) => this.heightAt(column),
        is_spawnable_column: (column) =>
          !reservedColumns.has(column) && this.heightAt(column) > 0,
        deck_footings_at_column: (column) => this.deckFootingsAtColumn(column),
      },
      // The hunting-ground policy. Spawns may land in view - they fade in rather than appear -
      // stand half a tile apart rather than more than one, and usually join a group already
      // standing rather than spreading evenly along the zone. Consumer numbers, deliberately: the
      // package names populations and species, and how those bodies are arranged is how the
      // route feels, which this scene owns.
      {
        spawn_visibility: "allow_onscreen",
        minimum_spawn_separation_px: Math.round(TILE_PX * 0.5),
        placement: "clustered",
        cluster_radius_px: Math.round(TILE_PX * 2.5),
      },
    );
    if (projection) {
      this.mobIdByPopulationSlot = projection.mob_id_by_slot;
      this.mobPopulationDirector = new MobPopulationDirector(
        projection.manifest,
        projection.candidates,
        { seed: gameplay.revision },
      );
      this.mobPopulationMapId = map.map_id;
    }

    for (const encounter of gameplay.boss_encounters.filter(
      (entry) => entry.map_id === map.map_id,
    )) {
      const mobSlot = manifest.mobs.findIndex(
        (candidate) => candidate.mob_id === encounter.mob_id,
      );
      if (mobSlot < 0) continue;
      const mob = this.createMobAtColumn(
        mobSlot,
        Math.floor(this.heights.length * 0.91),
      );
      if (mob) this.mobs.push(mob);
    }
  }

  private updateMobPopulation(now: number): void {
    const director = this.mobPopulationDirector;
    const mapId = this.mobPopulationMapId;
    if (!director || !mapId) return;
    const nowMs = Math.max(0, Math.trunc(now));
    for (const [mob, instanceId] of this.mobInstanceIds) {
      if (!mob.isAlive()) continue;
      director.updateInstancePosition(instanceId, {
        x_px: mob.sprite.x,
        y_px: mob.sprite.y,
      });
    }
    const view = logicalWorldView(this.cameras.main, VIEWPORT);
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
        ...this.props
          .filter((sprite) => sprite.active)
          .map((sprite) => ({ x_px: sprite.x, y_px: sprite.y })),
        ...this.mobs
          .filter((mob) => !mob.isAlive() && mob.sprite.active)
          .map((mob) => ({ x_px: mob.sprite.x, y_px: mob.sprite.y })),
      ],
    });
    for (const reservation of reservations) {
      this.materializeMobReservation(director, reservation, nowMs);
    }
  }

  private materializeMobReservation(
    director: MobPopulationDirector,
    reservation: SpawnReservation,
    nowMs: number,
  ): void {
    const mobId = this.mobIdByPopulationSlot[reservation.mob_slot];
    const mobSlot = this.manifest?.mobs.findIndex((candidate) => candidate.mob_id === mobId) ?? -1;
    let mob: Mob | null = null;
    try {
      if (mobSlot < 0) {
        director.reject(reservation.reservation_id, nowMs);
        return;
      }
      const deck =
        reservation.deck_id === undefined ? null : this.deckFooting(reservation.deck_id);
      if (reservation.deck_id !== undefined && !deck) {
        director.reject(reservation.reservation_id, nowMs);
        this.recordDiagnostic(
          `Mob reservation ${reservation.reservation_id} named unknown deck ${reservation.deck_id}`,
        );
        return;
      }
      mob = this.createMobAtColumn(
        mobSlot,
        reservation.candidate_column,
        this.nextMobInstance,
        nowMs,
        deck ?? undefined,
      );
      if (!mob) {
        director.reject(reservation.reservation_id, nowMs);
        return;
      }
      const instanceId =
        `${reservation.map_id}/mob/${this.nextMobInstance++}`;
      director.confirm(reservation.reservation_id, instanceId);
      this.recordEvent("mob-spawned", {
        instanceId,
        column: reservation.candidate_column,
      });
      this.mobs.push(mob);
      this.mobInstanceIds.set(mob, instanceId);
    } catch (error) {
      mob?.destroy();
      director.reject(reservation.reservation_id, nowMs);
      this.recordDiagnostic(
        `Mob reservation ${reservation.reservation_id} was rejected: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }

  private updatePlayer(delta: number, now: number, keyboardIntent: PlayerIntent): void {
    const player = this.player;
    const keys = this.keys;
    const gameplay = this.gameplay;
    if (!player || !keys || !gameplay || !this.currentMap) return;
    const intent = this.resolveIntent(delta, now, keyboardIntent);
    player.update(delta, now, intent);
    if (intent.toggleInventory) this.inventoryHud?.toggle();
    if (intent.useHealing) this.useHealingItem();

    const health = player.healthState;
    if (health.defeated) {
      if (this.defeatedAtMs === null) this.recordEvent("player-defeated", null);
      this.defeatedAtMs ??= now;
      // The recovery is asked for rather than taken: the world is rebuilt at the end of this
      // frame, so nothing below this line steps a controller that is about to be retired.
      if (this.updateDefeatPrompt(now, keyboardIntent)) return;
    } else {
      this.defeatedAtMs = null;
      this.defeatPanel?.hide();
    }
    if (gameplay.combat.enabled && gameplay.combat.contact_damage) {
      for (const mob of this.mobs) {
        if (!mob.isAlive()) continue;
        mob.observePlayer(player.sprite.x, player.sprite.y, health.defeated);
        const strike = mob.consumeStrike();
        if (!strike || strike.damage <= 0) continue;
        const profile = aggressionProfile(mob.snapshot().aggression);
        if (
          Math.abs(mob.sprite.x - player.sprite.x) > profile.strikeRangePx * 1.35 ||
          !attackFootLevelsOverlap(mob.sprite.y, player.sprite.y, TILE_PX)
        ) {
          continue;
        }
        const blow = resolveCriticalDamage(
          strike.damage,
          gameplay.combat.critical_profile,
          this.nextBlowSeed(mob.sprite.x, mob.ladderIndex),
        );
        const resolution = player.takeDamage(
          blow.amount,
          now,
          strike.dirSign,
          blow.critical,
        );
        if (resolution.connected) {
          this.recordEvent("player-damaged", {
            applied: resolution.appliedAmount,
            hp: resolution.hpAfter,
            critical: resolution.critical,
          });
          this.combatText?.showDamage({
            resolution,
            direction: "incoming",
            x: player.sprite.x,
            y: player.sprite.getBounds().top - 18,
            nowMs: now,
          });
        }
      }
    } else {
      for (const mob of this.mobs) mob.observePlayer(null, null, health.defeated);
    }

    const hitTick = gameplay.combat.enabled ? player.consumeAttackHit(now) : null;
    if (hitTick !== null) {
      const facing: 1 | -1 = player.facing === "left" ? -1 : 1;
      if (this.weapon.delivery.kind === "instant") {
        // The arc is drawn on the first blow whether or not it connects: it is the band made
        // visible, and a swing that whiffs still swung. Its radius is the band's reach, so the
        // shape on screen and the rule in `strike.ts` cannot disagree.
        if (hitTick === 0) {
          this.impact?.showSwing({
            x: player.sprite.x,
            y: player.sprite.y - PLAYER_HEIGHT * 0.55,
            dirSign: facing,
            radiusPx: TILE_PX * this.weapon.delivery.reachTiles * 0.9,
            nowMs: now,
          });
        }
        // Re-resolved on every blow rather than once per action, so a creature killed by the
        // second blow frees its slot for the third, and one that wandered into the band mid-swing
        // is struck by the blows that remain.
        const living = this.mobs.filter((mob) => mob.isAlive());
        for (const index of resolveInstantStrike({
          profile: this.weapon,
          attackerX: player.sprite.x,
          attackerFootY: player.sprite.y,
          dirSign: facing,
          tilePixels: TILE_PX,
          targets: living.map((mob) => ({ x: mob.sprite.x, footY: mob.sprite.y })),
        })) {
          this.applyPlayerBlow(living[index], player.sprite.x, facing, now, hitTick === 0);
        }
      } else if (hitTick === 0 && this.throwOne(player.sprite.x, player.sprite.y, facing)) {
        this.recordEvent("projectile-thrown", { x: Math.round(player.sprite.x), dirSign: facing });
        // The shot is the effect, so the round is spent only once one is actually in the air —
        // the inverse of drinking, where the bag opens only if the heal connected.
        if (this.ammoItemId) this.consumeInventory(this.ammoItemId, 1);
      }
    }

    const enterRequested =
      Phaser.Input.Keyboard.JustDown(keys.up) ||
      Phaser.Input.Keyboard.JustDown(keys.w);
    const activation = this.portal?.update({
      nowMs: now,
      playerX: player.sprite.x,
      playerFootY: player.sprite.y,
      enterRequested,
      shimmer: true,
    });
    if (activation) {
      const destination = this.manifest?.maps[activation.destinationIndex];
      const transition = destination
        ? this.transitionForPortal(destination.map_id, activation.portalId)
        : undefined;
      const spawn = gameplay.spawns.find(
        (candidate) => candidate.spawn_id === transition?.to_spawn_id,
      );
      if (destination && transition && spawn) {
        this.requestMapEntry(destination.map_id, spawn.normalized_x);
      }
    }

    const currentHealth = player.healthState;
    this.healthBar?.update({
      hp: currentHealth.hp,
      maxHp: currentHealth.maxHp,
      invulnerable: now < currentHealth.invulnerableUntilMs,
      actorX: player.sprite.x,
      actorFootY: player.sprite.y,
    });
    this.combatText?.update(now);
  }

  /**
   * Step every creature, and retire the ones whose bodies are gone.
   *
   * Split from the population director it used to be called by, because the two
   * read the world at different ages: the director reasons about where the
   * creatures stood last frame and this steps them to where they stand now.
   * `frame-roster.ts` carries that edge as an explicit `after`.
   */
  private stepMobs(delta: number, now: number): void {
    for (const mob of this.mobs) {
      // A dead body is stepped too, for as long as its sprite survives. Its fade and the
      // retirement that fade ends in are sampled from simulation time inside `update`, so a loop
      // that stepped only the living would leave every corpse standing at full opacity forever -
      // which is what a fixed-clock death actually did before this line was widened.
      if (mob.isAlive() || mob.sprite.active) mob.update(delta, now);
    }
    this.mobs = this.mobs.filter((mob) => mob.isAlive() || mob.sprite.active);
  }

  /**
   * Turn one connected blow into damage, presentation and consequences.
   *
   * Shared by both delivery kinds on purpose: a thrown hit and a swung hit differ in how they
   * arrived and in nothing else. `seedX` is where the blow *originated* — the character for a
   * swing, the release point for a throw — because the critical roll is seeded from it, and a
   * throw seeded at the impact point would roll differently depending on how far the target had
   * walked while the object was in the air.
   */
  private applyPlayerBlow(
    mob: Mob,
    seedX: number,
    dirSign: 1 | -1,
    nowMs: number,
    knockback = true,
  ): void {
    const gameplay = this.gameplay;
    if (!gameplay) return;
    const blowSeed = this.nextBlowSeed(seedX, mob.ladderIndex);
    const blow = resolveCriticalDamage(
      scaleOutgoingDamage(this.weapon.damage, this.numberScale, blowSeed),
      gameplay.combat.critical_profile,
      blowSeed,
    );
    const result = mob.takeHit(nowMs, dirSign, blow.amount, blow.critical, knockback ? 1 : 0);
    const bounds = mob.sprite.getBounds();
    this.combatText?.showDamage({
      resolution: result,
      direction: "outgoing",
      x: mob.sprite.x,
      y: bounds.top - 18,
      nowMs,
    });
    if (result.connected) {
      // Seeded from the same roll as the critical, so the spark a capture shows is the one the
      // damage number belongs to.
      this.impact?.showHit({
        x: mob.sprite.x,
        y: bounds.centerY,
        dirSign,
        critical: result.critical,
        died: result.died,
        seed: blowSeed,
        nowMs,
        target: mob,
      });
    }
    if (result.died) {
      this.recordEvent("mob-defeated", {
        ladderIndex: mob.ladderIndex,
        x: Math.round(mob.sprite.x),
      });
      this.recordManagedMobDeath(mob, nowMs);
      this.dropLoot(mob, dirSign);
      this.awardExperience(mob, nowMs);
    }
  }

  /**
   * Put one shot in the air, reporting whether anything was actually thrown.
   *
   * False for a full pool, a missing texture, or a class holding no round — all ordinary states,
   * none of them an error, and all of them meaning the caller must not spend anything.
   */
  private throwOne(originX: number, footY: number, dirSign: 1 | -1): boolean {
    const projectiles = this.projectiles;
    if (!projectiles) return false;
    if (this.weapon.ammoKind !== null) {
      const rounds = this.ammoItemId ? carried(this.inventory, this.ammoItemId) : 0;
      if (rounds < 1) return false;
    }
    return (
      projectiles.fire({
        originX,
        footY,
        bodyHeightPx: PLAYER_HEIGHT,
        dirSign,
      }) !== null
    );
  }

  /**
   * Step every shot and pay out what it hit.
   *
   * Runs after the mobs have moved this frame and before drops are collected, so a kill lands in
   * the same frame's loot pass rather than a frame later. The pool never holds a `Mob`: it is
   * handed this frame's boxes and returns indices into them, which is what keeps combat resolving
   * in exactly one place.
   */
  private updateProjectiles(delta: number, now: number): void {
    const projectiles = this.projectiles;
    if (!projectiles) return;
    const living = this.mobs.filter((mob) => mob.isAlive());
    const hits = projectiles.update(
      delta,
      living.map((mob) => ({ bounds: mob.snapshot().renderBounds })),
    );
    for (const hit of hits) {
      const mob = living[hit.targetIndex];
      if (!mob || !mob.isAlive()) continue;
      this.applyPlayerBlow(mob, hit.spawnX, hit.dirSign, now);
    }
  }

  private recordManagedMobDeath(mob: Mob, now: number): void {
    const instanceId = this.mobInstanceIds.get(mob);
    if (!instanceId) return;
    this.mobPopulationDirector?.recordDeath(instanceId, Math.max(0, Math.trunc(now)));
    this.mobInstanceIds.delete(mob);
  }

  /**
   * Nudge the camera by this frame's kill shake.
   *
   * Written as a scroll offset rather than `cameras.main.shake`, whose direction comes from
   * `Math.random` and would differ between two captures of the same run. Last frame's nudge is
   * removed before this frame's is added, so the offsets never accumulate; the follow lerp that
   * runs before render pulls a fraction of each nudge back toward the target, which is what
   * makes the shake settle rather than what makes it move. `null` removes the nudge outright,
   * for a world about to be torn down.
   */
  /**
   * What is shaking the view this frame.
   *
   * Which events shake it at all is this genre's answer and stays here; the
   * decay, the pattern and the sum are the `screen-fx` family's, and where the
   * view ends up is the `camera` family's.
   */
  private impactShake(nowMs: number): ShakeOffset {
    return this.impact?.shakeOffset(nowMs) ?? NO_SHAKE;
  }

  /** Move the camera from the offset it carries to `next`, through the family's carrier. */
  private carryCameraShake(next: ShakeOffset): void {
    const camera = this.cameras.main;
    const moved = this.shakeCarrier.shift({ scrollX: camera.scrollX, scrollY: camera.scrollY }, next);
    camera.scrollX = moved.scrollX;
    camera.scrollY = moved.scrollY;
  }

  /** The scale the package named, resolved through the table on every read like the weapon. */
  private get numberScale(): NumberScaleProfile {
    return numberScaleProfile(this.gameplay?.combat.number_scale);
  }

  /**
   * Knock this creature's loot loose.
   *
   * The rule is the `loot` family's — which stacks the authored `[[loot_rules]]`
   * turn into for one seeded death, and where the units of a stack land relative
   * to the body — and what is left here is the two things that are this genre's:
   * the seed (the corpse's column and its ladder index, so the same kill in the
   * same run drops the same things twice) and the catalog lookup that turns an
   * authored item id into the palette index the drop is drawn from.
   */
  private dropLoot(mob: Mob, dirSign: 1 | -1 = 1): void {
    const manifest = this.manifest;
    const gameplay = this.gameplay;
    const items = this.items;
    const spec = manifest?.mobs[mob.ladderIndex];
    if (!manifest || !gameplay || !items || !spec) return;
    const seed = (Math.floor(mob.sprite.x) * 2654435761 + mob.ladderIndex * 2246822519) >>> 0;
    for (const drop of resolveLootDrops(gameplay.loot_rules, spec.mob_id, seed)) {
      const itemIndex = manifest.items.findIndex((item) => item.item_id === drop.itemId);
      if (itemIndex < 0) continue;
      for (const offset of dropSpread(drop.quantity, LOOT_DROP_SPACING_PX)) {
        items.drop(mob.sprite.x + offset, mob.sprite.y - TILE_PX, itemIndex, dirSign);
      }
    }
  }

  private collectDrops(delta: number, now: number): void {
    const player = this.player;
    const items = this.items;
    const manifest = this.manifest;
    if (!player || !items || !manifest) return;
    items.update(delta, now);
    for (const item of items.tryPickup(
      player.sprite.x,
      player.sprite.y,
      TILE_PX * 0.9,
    )) {
      const itemId = manifest.items[item.kindIndex]?.item_id;
      if (!itemId) continue;
      this.recordEvent("item-collected", { itemId });
      this.addInventory(itemId, 1);
    }
  }

  /**
   * Offer the nearest villager the player can talk to, and open it if asked.
   *
   * The pick is the `interaction` family's: a candidate is *available* when the
   * package binds it a scenario and the player is inside talking range, and
   * between two available ones the nearer wins. Both of those conditions are
   * this genre's to evaluate — a range in pixels and a binding in `gameplay` —
   * and the rule that turns them into one offer is not.
   */
  private updateInteractionPrompt(): void {
    const player = this.player;
    const keys = this.keys;
    if (!player || !keys || !this.currentMap) return;
    const nearest = selectAffordance<NpcActor>({
      candidates: this.npcs,
      available: (npc) =>
        Math.abs(npc.sprite.x - player.sprite.x) < NPC_TALK_RANGE_PX &&
        this.scenarioForNpc(npc.npcId) !== undefined,
      distance: (npc) => Math.abs(npc.sprite.x - player.sprite.x),
    });
    for (const npc of this.npcs) {
      npc.talkPrompt.setVisible(npc === nearest);
    }
    if (nearest && (Phaser.Input.Keyboard.JustDown(keys.interact) || Phaser.Input.Keyboard.JustDown(keys.enter))) {
      this.openInteraction(nearest.npcId);
    }
  }

  /** The conversation this NPC offers on this map, if gameplay binds one. */
  private scenarioForNpc(
    npcId: string,
  ): { program: ScenarioProgram; interactionId: string } | undefined {
    const interaction = this.gameplay?.interactions.find(
      (entry) => entry.map_id === this.currentMap?.map_id && entry.actor_id === npcId,
    );
    const program = this.manifest?.scenarios.find(
      (entry) => entry.scenarioId === interaction?.scenario_id,
    );
    if (!interaction || !program) return undefined;
    return { program, interactionId: interaction.interaction_id };
  }

  private openInteraction(npcId: string): void {
    const bound = this.scenarioForNpc(npcId);
    if (!bound) return;
    const { program, interactionId } = bound;
    for (const npc of this.npcs) npc.talkPrompt.setVisible(false);
    this.activeScenario = openSession(interactionId, program, initialScenarioState(program));
    this.recordEvent("dialogue-opened", { npcId, interactionId });
    this.renderDialogueNode();
  }

  private updateDialogueInput(keyboardIntent: PlayerIntent): void {
    const keys = this.keys;
    if (!keys) return;
    const active = this.activeScenario;
    if (!active) return;
    const view = scenarioView(active.program, active.state);
    if (view?.kind === "choice") {
      // A choice is chosen, not advanced past. Number keys pick an option; the
      // scenario runtime already filtered the list to what the flags allow.
      for (const [index, key] of this.choiceKeys.entries()) {
        if (index < view.options.length && Phaser.Input.Keyboard.JustDown(key)) {
          this.applyScenarioAction({ kind: "choose", option: index });
          return;
        }
      }
      return;
    }
    if (
      Phaser.Input.Keyboard.JustDown(keys.interact) ||
      Phaser.Input.Keyboard.JustDown(keys.enter) ||
      // The jump the frame's one keyboard read already took, rather than a second `JustDown` on
      // the same `Key`: space could not advance a conversation while the read ran first.
      keyboardIntent.jump
    ) {
      this.applyScenarioAction({ kind: "advance" });
    }
  }

  private applyScenarioAction(action: ScenarioAction): void {
    const active = this.activeScenario;
    if (!active) return;
    const step = stepSession({
      session: active,
      action,
      reduce: reduceScenario,
      finished: scenarioIsFinished,
      outcome: (state) => state.outcome,
    });
    // "The action did nothing" is separate from "it advanced": redrawing on a
    // no-op is what makes the panel flicker on every key a conversation does
    // not answer.
    if (step.kind === "unchanged") return;
    this.activeScenario = step.session;
    if (step.kind === "finished") {
      this.applyOutcome(step.interactionId, step.outcome);
      this.closeDialogue();
      return;
    }
    this.renderDialogueNode();
  }

  private renderDialogueNode(): void {
    const active = this.activeScenario;
    const manifest = this.manifest;
    if (!active || !manifest) return;
    const view = scenarioView(active.program, active.state);
    if (view === null || view.kind === "end") {
      this.applyOutcome(active.interactionId, active.state.outcome);
      this.closeDialogue();
      return;
    }
    // Whoever spoke last owns the portrait: a choice is the player weighing what
    // that person just said, so the panel keeps showing them.
    const speakerId = view.kind === "line" ? (view.speaker ?? this.lastSpeakerId) : this.lastSpeakerId;
    if (speakerId === null) return;
    this.lastSpeakerId = speakerId;
    const expression = scenarioActor(active.state, speakerId)?.expression ?? "neutral";
    const playerSpeaker = speakerId === manifest.player.player_id;
    const npc = manifest.npcs.find((entry) => entry.npc_id === speakerId);
    const binding = playerSpeaker ? manifest.player.dialogue : npc?.dialogue;
    const texture = playerSpeaker ? "prepared_player_dialogue" : `prepared_npc_${speakerId}_dialogue`;
    const expressionIndex = binding?.expressions.indexOf(expression) ?? 0;
    this.ensureDialogueUi();
    this.dialogueName?.setText(playerSpeaker ? manifest.player.display_name : npc?.display_name ?? speakerId);
    this.dialogueText?.setText(
      view.kind === "line" ? view.text : dialogueChoicePrompt(view.options),
    );
    this.dialoguePortrait?.setTexture(texture, `expression_${Math.max(0, expressionIndex)}`);
    if (this.dialoguePortrait) {
      scaleSpriteFrameToHeight(this.dialoguePortrait, this.dialoguePortraitHeight);
    }
    this.dialoguePortrait?.setVisible(true);
  }

  private applyOutcome(interactionId: string, outcome: string | null): void {
    if (outcome === null) return;
    // The scenario reached an ending; gameplay says what that ending means here.
    const interaction = this.gameplay?.interactions.find(
      (entry) => entry.interaction_id === interactionId,
    );
    const bound = interaction?.outcomes.find((entry) => entry.outcome_id === outcome);
    if (!bound) return;
    this.performEffects(bound.effect_ids);
  }

  /**
   * Perform the effects an outcome or a quest named, in the order it named them.
   *
   * Resolution and dispatch are the `effects` family's; what each operation
   * *means* is this scene's, and every one of them reaches another family
   * through its own API rather than writing a slice the family does not own.
   */
  private performEffects(effectIds: readonly string[]): void {
    const vocabulary = this.effects;
    const table = this.gameplay?.effects;
    if (!vocabulary || !table) return;
    applyEffects(
      vocabulary,
      resolveEffects(table, effectIds).map((effect) => ({
        operation: effect.operation,
        payload: effect,
      })),
    );
  }

  private ensureDialogueUi(): void {
    if (this.dialoguePanel) {
      this.dialoguePanel.image.setVisible(true);
      this.dialogueText?.setVisible(true);
      this.dialogueName?.setVisible(true);
      return;
    }
    const manifest = this.manifest;
    if (!manifest) throw new Error("dialogue opened before the manifest loaded");
    // The conversation box is the package's own panel frame, the same sheet the defeat panel
    // draws from, so every framed surface in the game shares one generated vocabulary.
    this.dialoguePanel = new NineSliceWidget({
      scene: this,
      sheetKey: "ui_panel_frame",
      layout: manifest.ui.panel_frame,
      width: VIEW_W - 80,
      height: DIALOGUE_PANEL_HEIGHT,
      x: VIEW_W / 2,
      y: DIALOGUE_PANEL_CENTER_Y,
      depth: SCENE_CONTENT_DEPTH.dialogue,
    });
    // Name, line, and portrait are placed from the frame's measured safe rect, so a corner cap
    // that curls inward moves them rather than sitting on top of them.
    const layout = dialogueBoxLayout(this.dialoguePanel.safeRect(), DEFAULT_DIALOGUE_BOX_KNOBS);
    this.dialogueName = this.add.text(layout.name.x, layout.name.y, "", { fontFamily: "Georgia, serif", fontSize: "25px", color: "#ffe6a9", fontStyle: "bold" }).setScrollFactor(0).setDepth(SCENE_CONTENT_DEPTH.dialogue + 1);
    this.dialogueText = this.add.text(layout.text.x, layout.text.y, "", { fontFamily: "system-ui, sans-serif", fontSize: "22px", color: "#ffffff", wordWrap: { width: layout.text.wrapWidth }, lineSpacing: 7 }).setScrollFactor(0).setDepth(SCENE_CONTENT_DEPTH.dialogue + 1);
    this.dialoguePortrait = this.add.sprite(layout.portrait.centerX, layout.portrait.bottomY, "prepared_player_dialogue", "expression_0").setOrigin(0.5, 1).setScrollFactor(0).setDepth(SCENE_CONTENT_DEPTH.dialogue + 1);
    this.dialoguePortraitHeight = layout.portrait.height;
    scaleSpriteFrameToHeight(this.dialoguePortrait, this.dialoguePortraitHeight);
  }

  private closeDialogue(): void {
    this.recordEvent("dialogue-closed", {
      interactionId: this.activeScenario?.interactionId ?? "",
    });
    this.activeScenario = undefined;
    this.lastSpeakerId = null;
    this.dialoguePanel?.image.setVisible(false);
    this.dialogueText?.setVisible(false);
    this.dialogueName?.setVisible(false);
    this.dialoguePortrait?.setVisible(false);
  }

  private createInterface(manifest: PreparedRuntimeManifest): void {
    this.debugOverlay = new DebugOverlay(this);
    this.defeatPanel = new DefeatPanel({ scene: this, ui: manifest.ui });
    this.mapLabel = this.add.text(VIEW_W / 2, 20, this.currentMap?.display_name ?? "", { fontFamily: "Georgia, serif", fontSize: "22px", color: "#fff3cc", stroke: "#1a3342", strokeThickness: 5 }).setOrigin(0.5, 0).setScrollFactor(0).setDepth(850);
    this.updateDebugOverlay();
  }

  private updateDebugOverlay(): void {
    const manifest = this.manifest;
    if (!manifest || !this.debugOverlay) return;
    const health = this.player?.healthState;
    this.debugOverlay.update({
      health: health?.hp ?? 0,
      maximumHealth:
        health?.maxHp ?? this.gameplay?.player.starting_health ?? 0,
      progression:
        this.progressionPolicy?.enabled && this.progression
          ? {
              level: this.progression.level,
              experienceIntoLevel: this.progression.experienceIntoLevel,
              experienceForNext: this.progression.experienceForNext,
            }
          : null,
      autoPlay: this.bot
        ? {
            enabled: this.autoPlayEnabled,
            driving: this.controlSource === "bot",
            goal: this.bot.lastDecision?.goal ?? null,
            reason: this.bot.lastDecision?.reason ?? null,
          }
        : null,
      kit:
        this.selectableKits.length > 1
          ? {
              label: developerKitLabel(this.developerKit ?? this.selectableKits[0]),
              published: this.developerKit === null,
            }
          : null,
      inventory: [...this.inventory.entries()].map(([itemId, quantity]) => ({
        label:
          manifest.items.find((item) => item.item_id === itemId)?.display_name ??
          itemId,
        quantity,
      })),
    });
  }

  /**
   * Take units into the bag, and settle whatever carrying them completes.
   *
   * The bag arithmetic is the family's; what is left here is the two things
   * that are this genre's — mirroring the panel, and asking whether the stack
   * that just grew finishes a quest.
   *
   * The bag is instantiated with no capacity, deliberately. `[inventory]
   * starting_capacity` is still parsed and unread: what the number counts —
   * stacks or units — is not authored, and binding it adds a refusal the golden
   * cannot observe (the scripted run carries six units against a published
   * capacity of twenty-four). The family holds the rule so the contract bump
   * that decides the meaning has somewhere to land.
   */
  private addInventory(itemId: string, quantity: number): void {
    const verdict = grantToBag(this.inventory, itemId, quantity, UNLIMITED);
    if (verdict.moved <= 0) return;
    this.inventory = verdict.bag;
    this.mirrorInventorySlot(itemId);
    // The completion rule is the family's; the word for "running" is this
    // genre's. The effect a completed quest names is performed through the same
    // dispatch every other effect goes through — it used to be filtered down to
    // the state change at this one call site, which is why a completion that
    // named anything else silently did nothing, and why that shape is refused
    // at boot now instead.
    for (const quest of questsCompletedBy(
      this.gameplay?.quests ?? [],
      this.questStates,
      itemId,
      carried(this.inventory, itemId),
      PLATFORMER_QUEST_ACTIVE,
    )) {
      this.performEffects([quest.completion_effect_id]);
    }
  }

  /** Spend from the bag, and redraw the slot that pictures it. */
  private consumeInventory(itemId: string, quantity: number): void {
    const verdict = consumeFromBag(this.inventory, itemId, quantity);
    if (verdict.moved <= 0) return;
    this.inventory = verdict.bag;
    this.mirrorInventorySlot(itemId);
  }

  /**
   * Redraw one stack's square from the bag.
   *
   * The panel is told the count rather than a delta, which is the family port's
   * contract: a view that missed a change cannot drift, and a kind the catalog
   * does not carry has no square to draw at all.
   */
  private mirrorInventorySlot(itemId: string): void {
    const panel = this.inventoryHud;
    const itemIndex = this.manifest?.items.findIndex((item) => item.item_id === itemId) ?? -1;
    if (!panel || itemIndex < 0) return;
    panel.setSlot(panel.slotFor(itemIndex), itemIndex, carried(this.inventory, itemId));
  }

  /**
   * The next seed in the deterministic critical sequence.
   *
   * Mixes the blow's ordinal with the two facts that distinguish one swing from another at the
   * same moment — where it happened and who it was aimed at — so two mobs struck on the same frame
   * do not share a roll. Every term replays identically, which is the whole requirement.
   */
  private nextBlowSeed(x: number, targetIndex: number): number {
    this.blowSequence = (this.blowSequence + 1) >>> 0;
    return (
      (Math.imul(this.blowSequence, 2654435761) +
        Math.imul(Math.trunc(x), 2246822519) +
        Math.imul(targetIndex + 1, 3266489917)) >>>
      0
    );
  }

  /**
   * Bank a kill's experience and settle whatever it buys.
   *
   * Silent when the package ships progression disabled, because `grantExperience` awards nothing
   * and there is then no line worth writing. A level raises the pool immediately and fills it: the
   * fight that earned the level is usually still going.
   */
  private awardExperience(mob: Mob, nowMs: number): void {
    const policy = this.progressionPolicy;
    const state = this.progression;
    const spec = this.manifest?.mobs[mob.ladderIndex];
    if (!policy || !state || !spec) return;
    const award = grantExperience(state, experienceForRank(spec.rank), policy);
    if (award.awarded <= 0) return;
    this.progression = award.state;
    this.statLog?.push({
      kind: "experience",
      text: formatExperienceLine(award.awarded),
      nowMs,
    });
    if (award.levelsGained <= 0) return;
    this.statLog?.push({
      kind: "level_up",
      text: formatLevelUpLine(award.state.level),
      nowMs,
    });
    // The bar itself is redrawn at the end of this same frame's player update, from the player's
    // own position. Redrawing it here would only anchor it to the corpse for one frame.
    this.player?.growMaximumHealth(
      maximumHealthForLevel(policy.baseHealth, award.state.level, policy.growth),
    );
  }

  /**
   * Spend one carried healing consumable on the player.
   *
   * The health pool answers first and the bag is only opened if it says the restore connected, so
   * a request at full health, or while defeated, costs nothing. Doing it the other way round —
   * spend, then heal — is how a player loses a potion to a mistimed key press.
   */
  private useHealingItem(): void {
    const player = this.player;
    const manifest = this.manifest;
    if (!player || !manifest) return;
    const itemId = selectHealingItemId(manifest.items, this.inventory);
    if (!itemId) return;
    const resolution = player.heal(
      healingRestoreAmount(player.healthState.maxHp),
    );
    if (!resolution.connected) return;
    this.consumeInventory(itemId, 1);
  }

  /**
   * Flip auto-play, and say so.
   *
   * The toggle key is not part of the intent the controller reads, so pressing it is not a
   * takeover: it changes who is allowed to drive rather than driving. The bot is suspended on the
   * way through in either direction, because the target and the stuck counter it was holding
   * describe a frame that is no longer the one about to run.
   */
  private updateAutoPlayToggle(nowMs: number): void {
    const key = this.keys?.autoPlay;
    if (!this.bot || !key || !Phaser.Input.Keyboard.JustDown(key)) return;
    this.autoPlayEnabled = !this.autoPlayEnabled;
    this.bot.suspend();
    this.statLog?.push({
      kind: "notice",
      text: this.autoPlayEnabled ? "AUTO-PLAY ON" : "AUTO-PLAY OFF",
      nowMs,
    });
  }

  /**
   * Cycle to the next kit this run can be played with, in place.
   *
   * The developer affordance the package cannot cheaply give: a kit is one decision with the
   * drawn equipment, so trying the other arm by authoring means re-rendering the character. Here
   * it costs a keypress.
   *
   * The switch itself is `switchDeveloperKit`, which both this key and the console's buttons call,
   * so there is one implementation rather than two that could drift.
   */
  private updateKitSwitch(nowMs: number): void {
    const key = this.keys?.switchKit;
    if (!key || !Phaser.Input.Keyboard.JustDown(key)) return;
    if (this.selectableKits.length < 2) {
      this.statLog?.push({ kind: "notice", text: "ONLY ONE KIT IN THIS RUN", nowMs });
      return;
    }
    // `nextDeveloperKit` answers null only for an empty list, which the guard above already
    // excludes, and `switchDeveloperKit` is what decides that wrapping onto the published kit
    // means no override - so the key hands its answer straight over.
    this.switchDeveloperKit(nextDeveloperKit(this.developerKit, this.selectableKits));
  }

  /**
   * Play this run as a different kit, now, without reloading it.
   *
   * The one entry point: the `K` key and the console's buttons both arrive here, so there is no
   * second version of the switch that could drift from the first. Null restores the kit the
   * package published.
   *
   * Returns false when the scene is not in a state that can be switched - still loading, or between
   * maps - so a caller can leave its own control alone rather than showing a change that did not
   * happen.
   */
  switchDeveloperKit(kit: DeveloperKit | null): boolean {
    const map = this.currentMap;
    const player = this.player;
    const manifest = this.manifest;
    const gameplay = this.gameplay;
    if (!map || !player || !manifest || !gameplay || !this.ready) return false;
    // Normalised, not stored verbatim. Cycling wraps back onto the published kit as an object, and
    // storing that would make the run report itself as overridden while being played exactly as it
    // shipped - which is the one thing `kitOverridden` and the overlay's "(override)" mark exist to
    // say. Being played as the published kit *is* not being overridden, however you arrived there.
    const published = this.selectableKits[0];
    this.developerKit = kit && published && sameDeveloperKit(kit, published) ? null : kit;
    this.resolveWeaponClass(manifest, gameplay);
    // Re-entered rather than patched, because `this.weapon` is read by the controller, the strike
    // resolver, the projectile pool and the bot band, and re-entry is the one path that rebuilds
    // all four together - the same path a respawn already takes. Re-entered where they are
    // standing, so a switch reads as a change of kit rather than as being sent back to the gate.
    void this.enterMap(map.map_id, player.sprite.x / this.worldWidth, false);
    // After the re-entry, never before it: `enterMap` runs synchronously to `clearWorld`, which
    // clears the stat log, so a notice pushed first is destroyed in the same call that was meant
    // to announce it.
    this.statLog?.push({
      kind: "notice",
      text: `KIT ${developerKitLabel(this.developerKit ?? published).toUpperCase()}`,
      nowMs: this.time.now,
    });
    this.publishProbe(manifest);
    return true;
  }

  /** Every kit this run can be played as, for a console that has to render the choice. */
  developerKitOptions(): readonly DeveloperKit[] {
    return this.selectableKits;
  }

  /**
   * The kit in force, or null while the run is being played as published.
   *
   * A reader rather than a notification, because the scene is the source of truth and the console
   * is a mirror of it: `K` changes the kit without React ever hearing about it, so a console that
   * tracked only its own clicks would sit on a stale answer the moment anyone used the keyboard.
   */
  activeDeveloperKit(): DeveloperKit | null {
    return this.developerKit;
  }


  /**
   * This frame's intent, from whichever of the two sources owns it.
   *
   * The keyboard is read on every frame without exception, whoever is driving. Edge-triggered
   * requests latch until something reads them, so a frame the bot owns still has to drain the
   * human's - otherwise a jump pressed during auto-play would be queued and fired later, at the
   * moment control happened to come back.
   */
  private resolveIntent(
    delta: number,
    now: number,
    keyboardIntent: PlayerIntent,
  ): PlayerIntent {
    const player = this.player;
    if (!player) return NEUTRAL_PLAYER_INTENT;
    const humanIntent = this.intentSource ? this.intentSource() : keyboardIntent;
    const control = resolveBotControl({
      humanIntent,
      enabled: this.autoPlayEnabled && this.bot !== undefined,
      nowMs: now,
      lastHumanInputAtMs: this.lastHumanInputAtMs,
    });
    this.lastHumanInputAtMs = control.humanInputAtMs;
    if (control.source !== this.controlSource && control.source === "human") {
      this.bot?.suspend();
    }
    this.controlSource = control.source;
    if (control.source === "human" || !this.bot) return humanIntent;
    const view = this.botWorldView(delta, now);
    return view ? this.bot.decide(view).intent : NEUTRAL_PLAYER_INTENT;
  }

  /**
   * Fill in what the bot is allowed to know about this frame.
   *
   * Only live mobs and existing drops appear, which is what makes "no target" an ordinary answer
   * rather than something every behaviour has to guard against. Nothing here reaches back into the
   * bot; the scene supplies, the bot decides.
   */
  private botWorldView(delta: number, now: number): BotWorldView | null {
    const player = this.player;
    const manifest = this.manifest;
    const gameplay = this.gameplay;
    if (!player || !manifest || !gameplay) return null;
    const threats: { id: string; x: number; y: number; hp: number }[] = [];
    for (const mob of this.mobs) {
      const id = this.mobBotIds.get(mob);
      if (!id || !mob.isAlive()) continue;
      threats.push({ id, x: mob.sprite.x, y: mob.sprite.y, hp: mob.snapshot().hp });
    }
    return preparedBotWorldView({
      nowMs: now,
      deltaMs: delta,
      player: player.snapshot(now),
      threats,
      pickups: (this.items?.items ?? []).map((item) => ({
        id: item.id,
        x: item.body.x,
        y: item.body.y,
        settled: item.body.settled,
      })),
      healingCarried: selectHealingItemId(manifest.items, this.inventory) !== null,
      // True for a class that spends nothing, so a free-throwing or swinging policy never has to
      // ask whether the question applied to it.
      ammoCarried:
        this.weapon.ammoKind === null ||
        (this.ammoItemId !== null && carried(this.inventory, this.ammoItemId) >= 1),
      weaponBand: preparedBotWeaponBand(
        this.weapon,
        TILE_PX,
        this.projectiles?.profile ?? null,
        PLAYER_HEIGHT,
      ),
      combatEnabled: gameplay.combat.enabled,
      navigation: this.navGraph,
      // The same profile the projectile's own terrain test reads, handed over as plain numbers so
      // targeting can ask what a shot would run into before one is in the air.
      terrain: Object.freeze({
        columnSurfaceY: this.heights.map((height) =>
          terrainSurfaceY(height, TILE_PX, this.groundBaselineY),
        ),
        tileUnits: TILE_PX,
      }),
      worldWidth: this.worldWidth,
    });
  }

  /**
   * Raise the death screen and act on it. Returns true when the world has just been replaced.
   *
   * The panel is offered to everyone and answered by whoever is playing. A person answers it with
   * the button or a confirm key, and nothing happens until they do — which is the point of showing
   * it at all. A run the bot is driving answers it on its own after a beat, because the alternative
   * is an unattended run that stops forever at its first death; that is a property of who is at the
   * keyboard, not a decision any behaviour makes, so it is settled here rather than in the roster.
   */
  private updateDefeatPrompt(nowMs: number, keyboardIntent: PlayerIntent): boolean {
    const defeatedAtMs = this.defeatedAtMs;
    const gameplay = this.gameplay;
    const panel = this.defeatPanel;
    if (defeatedAtMs === null || !gameplay) return false;
    const home = resolveHomeSpawn(gameplay);
    panel?.update({
      defeatedAtMs,
      nowMs,
      destinationName:
        this.manifest?.maps.find((map) => map.map_id === home.map_id)?.display_name ?? "",
    });
    if (panel?.visible && this.confirmKeyPressed(keyboardIntent)) panel.requestConfirm();
    const confirmed = panel?.consumeConfirm() ?? false;
    const unattended =
      this.controlSource === "bot" &&
      automatedDefeatConfirmDue({ defeatedAtMs, nowMs });
    if (!confirmed && !unattended) return false;
    this.respawnAtHome();
    return true;
  }

  /** The same keys that advance a conversation also accept the death screen. */
  private confirmKeyPressed(keyboardIntent: PlayerIntent): boolean {
    const keys = this.keys;
    if (!keys) return false;
    return (
      Phaser.Input.Keyboard.JustDown(keys.interact) ||
      Phaser.Input.Keyboard.JustDown(keys.enter) ||
      // Same reason as the conversation's: the frame has already read space once, and the answer
      // it got is the only one there is.
      keyboardIntent.jump
    );
  }

  /**
   * Send a defeated player back to the village.
   *
   * Recovery is a map entry like any other, which is what makes it cheap and safe: the same
   * transition that carries a portal rebuilds the world, retires the defeated controller, and
   * constructs a fresh one at full health. What the player carried survives, because the bag is
   * scene state rather than world state; defeat costs progress through the route, not the run.
   */
  private respawnAtHome(): void {
    const gameplay = this.gameplay;
    if (!gameplay) return;
    this.defeatedAtMs = null;
    this.defeatPanel?.hide();
    const home = resolveHomeSpawn(gameplay);
    this.recordEvent("player-respawned", { mapId: home.map_id });
    this.requestMapEntry(home.map_id, home.normalized_x);
  }

  /**
   * Narrow playback to the entered map's pool.
   *
   * The scene names the pool and stops there. Which of its tracks plays, in what order, and
   * whether the one already playing survives the change are the player's decisions, and they are
   * seeded, which is why the same run hears the same order twice.
   */
  private selectSoundtrack(map: PreparedMap): void {
    if (map.track_ids.length === 0) return;
    this.soundtrackPlayer?.setTrackPool(map.track_ids);
  }

  /**
   * Play one track, and say when it has finished.
   *
   * The transport is the whole of what this scene knows about audio: one element, replaced per
   * track, never looped - a looped element would never end, and the bag that decides what comes
   * next advances on the end of the track before it.
   */
  private soundtrackTransport(): SoundtrackTransport {
    return {
      play: (track, onEnded) => {
        this.soundtrackAudio?.pause();
        const audio = new Audio(track.path);
        audio.volume = 0.34;
        audio.addEventListener("ended", onEnded, { once: true });
        this.soundtrackAudio = audio;
        // A browser may still refuse this one; the order has already moved on, which is the price
        // of an order that does not depend on which attempts a browser happened to allow.
        void audio.play().catch(() => undefined);
      },
      stop: () => {
        this.soundtrackAudio?.pause();
        this.soundtrackAudio = undefined;
      },
    };
  }

  /**
   * Silence the run.
   *
   * A scene that is torn down while a track is playing leaves an element playing into a page that
   * no longer has a game on it: nothing else holds a reference to it, so nothing else can stop it.
   */
  stopSoundtrack(): void {
    this.soundtrackPlayer?.stop();
    this.soundtrackPlayer = undefined;
  }

  /**
   * Announce the map being entered.
   *
   * Raised here and stepped in `update` rather than handed to `tweens.add`, because a tween is
   * advanced by the engine's own frame delta: under a fixed-step capture the announcement lasted a
   * different number of frames on every recording of the same run, and under a paused loop it did
   * not advance at all. `sampleMapNameBanner` is the same fade-hold-fade shape read off simulation
   * time, which is the clock everything else in the frame is already resolved against.
   */
  private flashMapName(name: string): void {
    this.mapBanner?.text.destroy();
    this.mapBanner = {
      text: this.add
        .text(VIEW_W / 2, 105, name, { fontFamily: "Georgia, serif", fontSize: "36px", color: "#fff4cf", stroke: "#203849", strokeThickness: 7 })
        .setOrigin(0.5)
        .setScrollFactor(0)
        .setDepth(870)
        .setAlpha(0),
      // Simulation time, not the machine's: the banner is stepped by
      // `banner/map-name` against `step.now`, and a stamp from a different clock
      // would make its fade a different length on every recording of one run.
      raisedAtMs: this.stepNowMs,
    };
  }

  private updateMapBanner(nowMs: number): void {
    const banner = this.mapBanner;
    if (!banner) return;
    const sample = sampleMapNameBanner(banner.raisedAtMs, nowMs);
    if (sample.done) {
      banner.text.destroy();
      this.mapBanner = undefined;
      return;
    }
    banner.text.setAlpha(sample.alpha);
  }

  /**
   * Everything a replay hashes: the world this frame, and what the runtime called what happened.
   *
   * Composed out of the snapshots each family already publishes rather than re-reading their
   * internals, so a family that changes what it considers state changes what the golden sees by
   * saying so. Presentation nothing reads back - layer scroll offsets, contact shadow rings, the
   * loading label - is deliberately absent; the camera is not, because the spawn director asks it
   * what is on screen.
   */
  replaySnapshot(): Readonly<Record<string, unknown>> {
    const camera = this.cameras.main;
    return Object.freeze({
      ready: this.ready,
      loading: this.loading,
      mapId: this.currentMap?.map_id ?? null,
      diagnostics: [...this.diagnostics],
      weaponClass: this.weapon.weaponClass,
      ammoItemId: this.ammoItemId,
      camera: { scrollX: camera.scrollX, scrollY: camera.scrollY, zoom: camera.zoom },
      player: this.player?.snapshot(this.time.now) ?? null,
      platforms: this.verticalWorld.platforms.map((platform) => ({ ...platform })),
      climbables: this.verticalWorld.climbables.map((climbable) => ({ ...climbable })),
      mobs: this.mobs.map((mob) => ({
        botId: this.mobBotIds.get(mob) ?? null,
        instanceId: this.mobInstanceIds.get(mob) ?? null,
        alpha: mob.sprite.alpha,
        active: mob.sprite.active,
        ...mob.snapshot(),
      })),
      worldItems: this.items?.snapshot() ?? [],
      projectiles: this.projectiles?.snapshot() ?? [],
      portals: this.portal?.snapshot() ?? [],
      inventory: {
        carried: [...this.inventory.entries()].sort(([left], [right]) => (left < right ? -1 : 1)),
        slots: this.inventoryHud?.snapshot() ?? [],
      },
      combatText: this.combatText?.snapshot() ?? null,
      impact: this.impact?.snapshot() ?? null,
      statLog: this.statLog?.snapshot() ?? null,
      defeatPanel: this.defeatPanel?.snapshot() ?? null,
      defeatedAtMs: this.defeatedAtMs,
      progression: this.progression ?? null,
      questStates: this.questStates.entries(),
      dialogue: this.activeScenario
        ? {
            interaction: this.activeScenario.interactionId,
            label: this.activeScenario.state.label,
            index: this.activeScenario.state.index,
            flags: [...this.activeScenario.state.flags],
            outcome: this.activeScenario.state.outcome,
          }
        : null,
      npcPrompts: this.npcs.map((npc) => ({ npcId: npc.npcId, visible: npc.talkPrompt.visible })),
      mapLabel: this.mapLabel?.text ?? null,
      soundtrack: this.soundtrackPlayer?.snapshot() ?? null,
      // Absent rather than null while nothing is announced, so a frame with no banner carries no
      // banner field at all and the golden's quiet frames stay quiet.
      banner: this.mapBanner
        ? { text: this.mapBanner.text.text, alpha: this.mapBanner.text.alpha }
        : undefined,
    });
  }

  private fail(error: unknown): void {
    const message = error instanceof Error ? error.message : String(error);
    console.error("[prepared-scene] load failed:", message);
    this.children.getByName("loading-label")?.destroy();
    this.add.text(VIEW_W / 2, VIEW_H / 2, `Unable to load prepared game\n${message}`, { align: "center", color: "#ffffff", fontFamily: "system-ui, sans-serif", fontSize: "20px", backgroundColor: "#5b1720dd", padding: { x: 22, y: 16 }, wordWrap: { width: 900 } }).setOrigin(0.5).setScrollFactor(0).setDepth(1200);
  }
}

export type PreparedPreviewGameHandle = {
  destroy: (removeCanvas: boolean) => void;
  /**
   * Play the running scene as a different kit, without reloading it.
   *
   * Returns false when the scene cannot take the switch yet - still loading, or between maps - so
   * a console can leave its own control where it was rather than showing a change that did not
   * happen. Always false under automation, where an override is refused outright.
   */
  setDeveloperKit: (kit: DeveloperKit | null) => boolean;
  /** Every kit this run can be played as, or empty until the manifest has loaded. */
  developerKitOptions: () => readonly DeveloperKit[];
  /**
   * The kit in force, or null while the run is being played as published.
   *
   * Read rather than pushed, because the scene also changes it on its own - the `K` key switches
   * without React hearing anything - so a console that tracked only its own clicks would show a
   * stale answer the moment anyone used the keyboard.
   */
  activeDeveloperKit: () => DeveloperKit | null;
};

export function bootPreparedGame(
  parent: HTMLElement,
  tag: string,
  transparencyPolicy: PreviewTransparencyPolicy,
  automationMode: GameplayAutomationMode | null = null,
  developerKit: DeveloperKit | null = null,
): PreparedPreviewGameHandle {
  // A capture is a recording of one published run, so a developer override is refused here rather
  // than merely defaulted: the transcript digests carry no record of an override, so a frame hash
  // taken under one would be attributed to the package it is not showing.
  const scene = new PreparedStageScene(
    tag,
    transparencyPolicy,
    automationMode,
    automationMode === null ? developerKit : null,
  );
  // A capture keeps the design-space canvas so its frame hashes are the same on every screen; a
  // person gets one sized in device pixels, which the scene's camera zooms back to design space.
  const canvasSize = automationMode
    ? GAMEPLAY_AUTOMATION_VIEWPORT
    : deviceGameSize(GAMEPLAY_AUTOMATION_VIEWPORT, currentDevicePixelScale());
  const game = new Phaser.Game({
    type: automationMode ? Phaser.CANVAS : Phaser.AUTO,
    width: canvasSize.width,
    height: canvasSize.height,
    parent,
    backgroundColor: "#000000",
    scene: [scene],
    scale: {
      mode: automationMode ? Phaser.Scale.NONE : Phaser.Scale.FIT,
      autoCenter: Phaser.Scale.CENTER_BOTH,
    },
  });
  return {
    destroy: (removeCanvas: boolean) => {
      // Before the game, not after: `game.destroy` drops every reference to the scene, and the
      // element the soundtrack is playing on is not one of the things it knows how to stop.
      scene.stopSoundtrack();
      game.destroy(removeCanvas);
    },
    // Refused for a capture at the handle as well as at the scene, so neither is the single place
    // an override could leak into a recording.
    setDeveloperKit: (kit) => (automationMode === null ? scene.switchDeveloperKit(kit) : false),
    developerKitOptions: () => scene.developerKitOptions(),
    activeDeveloperKit: () => (automationMode === null ? scene.activeDeveloperKit() : null),
  };
}
