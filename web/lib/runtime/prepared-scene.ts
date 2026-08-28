import Phaser from "phaser";
import type { GameplayAutomationMode } from "./automation";
import { GAMEPLAY_AUTOMATION_VIEWPORT } from "./automation";
import {
  fetchJson,
  loadFrameStrip,
  loadGridSheet,
  loadTerrainAtlas,
  loadTrimmedSprite,
  loadTransparentSprite,
  loadVerifiedRepeatLayer,
  registerCanvas,
} from "./assets";
import {
  parsePreparedRuntimeManifest,
  preparedAssetUrl,
  type MotionBinding,
  type PreparedMap,
  type PreparedRuntimeManifest,
} from "./prepared-manifest";
import type { PreviewTransparencyPolicy } from "@/lib/shell/transparency";
import { Player } from "./player";
import { Mob } from "./mob";
import { ItemSystem } from "./items";
import { InventoryHud } from "./inventory";
import {
  PortalSystem,
} from "./portal";
import { CombatTextSystem } from "./combat-text";
import {
  FloatingHealthBar,
  PLAYER_HEALTH_BAR_STYLE,
} from "./health-bar";
import { aggressionProfile, attackFootLevelsOverlap } from "./combat";
import { mobRenderEnvelope } from "./mob-geometry";
import {
  MobPopulationDirector,
  type SpawnReservation,
} from "./spawn-director";
import {
  ladderVisualBounds,
  type VerticalWorld,
} from "./vertical";
import type { ScaleReference } from "./sprite-scale";
import {
  registerGridPresentationFallback,
  registerPresentationFallback,
  type PresentationFallbackKind,
} from "./presentation-fallback";
import {
  assertPreparedGameplayManifestClosure,
  parsePreparedGameplayContract,
  type PreparedGameplayContract,
} from "./prepared-gameplay";
import { projectPreparedMobPopulation } from "./prepared-population";
import {
  anchorRepackedMotionFeet,
  applyMotionPlayback,
  installMotionPlayback,
} from "./motion-playback";
import {
  PREPARED_PLAYER_PRESERVE_SOURCE_SCALE_STATES,
  preparedPlayerClimbArtwork,
  preparedPlayerMotionPlayback,
  preparedPlayerStateAdapter,
} from "./prepared-player";
import { frameScaleForHeight } from "./sprite-scale";
import { SCENE_CONTENT_DEPTH } from "./layers";
import {
  preparedGroundBaselineY,
  preparedLayerLayout,
  preparedWalkSurfaceY,
} from "./prepared-layers";
import {
  terrainAtlasBoundaryOverscanPlan,
  terrainAtlasWalkSurfaceOffset,
} from "./terrain-atlas";
import {
  projectPreparedTerrainWorld,
  type PreparedTerrainWorld,
} from "./prepared-terrain";
import { terrainSurfaceY } from "./terrain";
import { preparedPortalEndpointPlacements } from "./prepared-portals";
import { presentPreparedLayerCanvas } from "./prepared-layer-presentation";
import { climbableAtlasFrames, climbableFrameKey } from "./prepared-climbable";
import {
  NPC_TALK_PROMPT_GAP_PX,
  NPC_TALK_PROMPT_STYLE,
  NPC_TALK_PROMPT_TEXT,
} from "./npc";
import { DebugOverlay } from "./debug-overlay";

const VIEW_W = 1280;
const VIEW_H = 720;
const TILE_PX = 64;
const PLAYER_HEIGHT = 154;
const MOB_HEIGHT = 110;
const NPC_HEIGHT = 150;
const DIALOGUE_PORTRAIT_HEIGHT = 190;
const DIALOGUE_PANEL_CENTER_Y = VIEW_H - 128;
const DIALOGUE_PANEL_HEIGHT = 210;
const DIALOGUE_PANEL_BOTTOM_Y =
  DIALOGUE_PANEL_CENTER_Y + DIALOGUE_PANEL_HEIGHT / 2;

type SequenceNode = Readonly<Record<string, unknown>>;
type Sequence = Readonly<{
  sequence_id: string;
  entry_node_id: string;
  nodes: readonly SequenceNode[];
}>;

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

function asSequences(values: readonly Record<string, unknown>[]): readonly Sequence[] {
  return values as unknown as readonly Sequence[];
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
  private inventoryHud?: InventoryHud;
  private readonly inventory = new Map<string, number>();
  private portal?: PortalSystem;
  private combatText?: CombatTextSystem;
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
  private questStates = new Map<string, string>();
  private debugOverlay?: DebugOverlay;
  private mapLabel?: Phaser.GameObjects.Text;
  private dialoguePanel?: Phaser.GameObjects.Rectangle;
  private dialogueText?: Phaser.GameObjects.Text;
  private dialogueName?: Phaser.GameObjects.Text;
  private dialoguePortrait?: Phaser.GameObjects.Sprite;
  private activeSequence?: { sequence: Sequence; nodeId: string };
  private soundtrack?: HTMLAudioElement;
  private audioUnlocked = false;

  constructor(
    tag: string,
    transparencyPolicy: PreviewTransparencyPolicy,
  ) {
    super({ key: "PreparedStageScene" });
    this.tag = tag;
    this.transparencyPolicy = transparencyPolicy;
  }

  create(): void {
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

  update(_time: number, delta: number): void {
    if (!this.ready || this.loading || !this.player || !this.keys) return;
    const now = performance.now();
    this.debugOverlay?.toggleForKey(this.keys.debugOverlay);
    this.updateDebugOverlay();
    if (this.activeSequence) {
      this.player.inventoryToggleRequested = false;
      this.updateDialogueInput();
      return;
    }
    this.updatePlayer(delta, now);
    this.updateMobs(delta, now);
    this.collectDrops(delta, now);
    this.updateInteractionPrompt();
    this.updateContactShadows();
    for (const layer of this.layerSprites) {
      const parallax = Number(layer.getData("parallax") ?? 0);
      layer.tilePositionX = this.cameras.main.scrollX * parallax;
    }
  }

  private url(path: string): string {
    return preparedAssetUrl(this.tag, path);
  }

  private async loadAll(): Promise<void> {
    const raw = await fetchJson<unknown>(this.url("manifest.json"));
    const manifest = parsePreparedRuntimeManifest(raw);
    const gameplay = parsePreparedGameplayContract(manifest.gameplay);
    assertPreparedGameplayManifestClosure(manifest, gameplay);
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
    for (const itemId of this.gameplay.player.starting_item_ids) this.addInventory(itemId, 1);
    const openingSpawn = this.gameplay.spawns.find(
      (spawn) => spawn.spawn_id === this.gameplay?.entry_spawn_id,
    );
    await this.enterMap(
      manifest.entry_map_id,
      openingSpawn?.normalized_x ?? 0.08,
      false,
    );
    this.createInterface();
    this.children.getByName("loading-label")?.destroy();
    this.ready = true;
    if (typeof window !== "undefined") {
      window.__sceneReady = true;
      (window as unknown as { __preparedGame?: unknown }).__preparedGame = Object.freeze({
        manifestKind: manifest.kind,
        gameId: manifest.game_id,
        packageSha256: manifest.package_sha256,
        artifactCount: manifest.closure.artifact_count,
        mapIds: manifest.maps.map((map) => map.map_id),
        diagnostics: Object.freeze([...this.diagnostics]),
      });
      (window as unknown as { __sceneProbes?: unknown }).__sceneProbes = {
        diagnostics: this.diagnostics,
        consoleErrors: [],
      };
    }
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

  private async loadGroundOrFallback(map: PreparedMap): Promise<void> {
    const key = `prepared_ground_${map.map_id}`;
    try {
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
    this.scaleReferences.clear();
    for (const key of [
      "character_idle",
      "character_walk",
      "character_run",
      "character_jump",
      "character_crawl",
      "character_climb_ladder",
      "character_climb_rope",
      "character_attack",
    ]) {
      const frame = this.textures.get(key).get(0);
      const width = Math.max(1, frame?.width ?? 64);
      const height = Math.max(1, frame?.height ?? 64);
      this.scaleReferences.set(
        key,
        Object.freeze({
          part: "body",
          topFraction: 0,
          bottomFraction: 1,
          leftFraction: 0,
          rightFraction: 1,
          extentPixels: height,
          confident: false,
          evidence: "Runtime frame bounds fallback for prepared package.",
          frameIndex: 0,
          cellWidth: width,
          cellHeight: height,
        }),
      );
    }
    if (manifest.player.states.crouch === undefined) {
      this.recordDiagnostic(
        "Player crouch mechanics use a runtime placeholder because no crouch strip was generated.",
      );
    }
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
      };
    }
    let unlockPending = false;
    const releaseAudioUnlock = () => {
      keyboard?.off("keydown", startAudio);
      this.input.off(Phaser.Input.Events.POINTER_DOWN, startAudio);
    };
    const startAudio = () => {
      const soundtrack = this.soundtrack;
      if (!soundtrack || this.audioUnlocked || unlockPending) return;
      unlockPending = true;
      void soundtrack.play().then(
        () => {
          this.audioUnlocked = true;
          releaseAudioUnlock();
        },
        () => {
          // Autoplay policies vary. Keep both gesture routes armed until one
          // playback attempt actually succeeds.
          unlockPending = false;
        },
      );
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
      startingHealth: gameplay.player.starting_health,
      motionPlayback: preparedPlayerMotionPlayback(manifest.player.states),
      climbArtwork: preparedPlayerClimbArtwork(manifest.player.states),
      scaleReferences: this.scaleReferences,
      preserveSourceScaleStates:
        PREPARED_PLAYER_PRESERVE_SOURCE_SCALE_STATES,
    });
    this.addContactShadow(this.player.sprite);
    this.items = new ItemSystem({
      scene: this,
      tilePx: TILE_PX,
      baselineY: this.groundBaselineY,
      heightFn: (column) => this.heightAt(column),
      itemTextureKey: (index) => preparedItemTextureKey(manifest, index),
    });
    this.installPortals(map);
    if (map.hostile_population_enabled) this.initializeMobPopulation(map);
    this.cameras.main.setBounds(0, 0, this.worldWidth, VIEW_H);
    this.cameras.main.startFollow(this.player.sprite, true, 0.12, 0.12, 0, 50);
    this.cameras.main.setDeadzone(300, 180);
    this.cameras.main.scrollY = 0;
    this.mapLabel?.setText(map.display_name);
    this.selectSoundtrack(map);
    this.loading = false;
    if (announce) this.flashMapName(map.display_name);
  }

  private clearWorld(): void {
    this.mobPopulationDirector?.dispose();
    this.mobPopulationDirector = undefined;
    this.mobPopulationMapId = undefined;
    this.mobIdByPopulationSlot = [];
    this.mobInstanceIds.clear();
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
    this.combatText?.clear();
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
        .setScrollFactor(0)
        .setDepth(layer.plane === "foreground" ? 80 + index : index - 20)
        .setData("parallax", layer.parallax);
      this.layerSprites.push(sprite);
    });
    const groundKey = `prepared_ground_${map.map_id}`;
    const terrainWorld = this.terrainWorld;
    if (!terrainWorld) {
      throw new Error("prepared map render requires projected terrain geometry");
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
    const aggression =
      spec.rank === "boss" || spec.rank === "elite"
        ? "relentless"
        : spec.rank === "uncommon"
          ? "hunting"
          : "territorial";
    const mob = new Mob({
      scene: this,
      ladderIndex: mobSlot,
      startingHealth: mobHealthForRank(spec.rank),
      spawnCol: spawnColumn,
      tilePx: TILE_PX,
      worldWidthPx: this.worldWidth,
      baselineY: this.groundBaselineY,
      heightFn: (column) => this.heightAt(column),
      spriteHeightPx: spec.rank === "boss" ? MOB_HEIGHT * 1.45 : MOB_HEIGHT,
      idleAnimKey: idleKey,
      hurtTextureKey: this.textures.exists(hurtKey) ? hurtKey : idleKey,
      renderEnvelope,
      aggression,
      attackTextureKey: this.textures.exists(attackKey) ? attackKey : undefined,
      deathTextureKey: this.textures.exists(deathKey) ? deathKey : undefined,
      behaviorSeed,
    });
    this.addContactShadow(mob.sprite);
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
    const reservedColumns = new Set<number>([0, 1, 2, 3, 4, 5]);
    for (
      let column = Math.max(0, this.heights.length - 6);
      column < this.heights.length;
      column += 1
    ) {
      reservedColumns.add(column);
    }
    for (const endpoint of map.portal?.endpoints ?? []) {
      const anchorColumn = Math.floor(
        endpoint.normalized_x * this.heights.length,
      );
      for (let offset = -2; offset <= 2; offset += 1) {
        const column = anchorColumn + offset;
        if (column >= 0 && column < this.heights.length) {
          reservedColumns.add(column);
        }
      }
    }
    for (const platform of this.verticalWorld.platforms) {
      for (
        let column = platform.sourceColumns.start;
        column < platform.sourceColumns.end;
        column += 1
      ) {
        reservedColumns.add(column);
      }
    }
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
    const view = this.cameras.main.worldView;
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
      mob = this.createMobAtColumn(
        mobSlot,
        reservation.candidate_column,
        this.nextMobInstance,
      );
      if (!mob) {
        director.reject(reservation.reservation_id, nowMs);
        return;
      }
      const instanceId =
        `${reservation.map_id}/mob/${this.nextMobInstance++}`;
      director.confirm(reservation.reservation_id, instanceId);
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

  private updatePlayer(delta: number, now: number): void {
    const player = this.player;
    const keys = this.keys;
    const gameplay = this.gameplay;
    if (!player || !keys || !gameplay || !this.currentMap) return;
    player.update(delta, now);
    if (player.inventoryToggleRequested) {
      this.inventoryHud?.toggle();
      player.inventoryToggleRequested = false;
    }

    const health = player.healthState;
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
        const resolution = player.takeDamage(strike.damage, now, strike.dirSign);
        if (resolution.connected) {
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

    if (gameplay.combat.enabled && player.consumeAttackHit()) {
      const facing = player.facing === "left" ? -1 : 1;
      const reach = TILE_PX * 1.4;
      const hitX = player.sprite.x + facing * reach * 0.5;
      for (const mob of this.mobs) {
        if (!mob.isAlive()) continue;
        if (
          Math.abs(mob.sprite.x - hitX) >= reach ||
          !attackFootLevelsOverlap(player.sprite.y, mob.sprite.y, TILE_PX)
        ) {
          continue;
        }
        const result = mob.takeHit(now, facing as 1 | -1);
        this.combatText?.showDamage({
          resolution: result,
          direction: "outgoing",
          x: mob.sprite.x,
          y: mob.sprite.getBounds().top - 18,
          nowMs: now,
        });
        if (result.died) {
          this.recordManagedMobDeath(mob, now);
          this.dropLoot(mob);
        }
        break;
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
        void this.enterMap(destination.map_id, spawn.normalized_x);
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

  private updateMobs(delta: number, now: number): void {
    this.updateMobPopulation(now);
    for (const mob of this.mobs) {
      if (mob.isAlive()) mob.update(delta, now);
    }
    this.mobs = this.mobs.filter((mob) => mob.isAlive() || mob.sprite.active);
  }

  private recordManagedMobDeath(mob: Mob, now: number): void {
    const instanceId = this.mobInstanceIds.get(mob);
    if (!instanceId) return;
    this.mobPopulationDirector?.recordDeath(instanceId, Math.max(0, Math.trunc(now)));
    this.mobInstanceIds.delete(mob);
  }

  private dropLoot(mob: Mob): void {
    const manifest = this.manifest;
    const gameplay = this.gameplay;
    const items = this.items;
    const spec = manifest?.mobs[mob.ladderIndex];
    if (!manifest || !gameplay || !items || !spec) return;
    const rules = gameplay.loot_rules.filter((entry) => entry.mob_id === spec.mob_id);
    for (const rule of rules) {
      const seed =
        (Math.floor(mob.sprite.x) * 2654435761 + mob.ladderIndex * 2246822519) >>> 0;
      if (seed / 0xffffffff > rule.chance) continue;
      const itemIndex = manifest.items.findIndex((item) => item.item_id === rule.item_id);
      if (itemIndex < 0) continue;
      const span = rule.quantity_max - rule.quantity_min + 1;
      const quantity = rule.quantity_min + (seed % span);
      for (let index = 0; index < quantity; index += 1) {
        items.drop(
          mob.sprite.x + (index - (quantity - 1) / 2) * 28,
          mob.sprite.y - TILE_PX,
          itemIndex,
        );
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
      if (itemId) this.addInventory(itemId, 1);
    }
  }

  private updateInteractionPrompt(): void {
    const player = this.player;
    const keys = this.keys;
    if (!player || !keys || !this.currentMap) return;
    const nearest = this.npcs
      .filter(
        (npc) =>
          Math.abs(npc.sprite.x - player.sprite.x) < 145 &&
          this.interactionSequenceForNpc(npc.npcId) !== undefined,
      )
      .sort(
        (left, right) =>
          Math.abs(left.sprite.x - player.sprite.x) -
          Math.abs(right.sprite.x - player.sprite.x),
      )[0];
    for (const npc of this.npcs) {
      npc.talkPrompt.setVisible(npc === nearest);
    }
    if (nearest && (Phaser.Input.Keyboard.JustDown(keys.interact) || Phaser.Input.Keyboard.JustDown(keys.enter))) {
      this.openInteraction(nearest.npcId);
    }
  }

  private openInteraction(npcId: string): void {
    const sequence = this.interactionSequenceForNpc(npcId);
    if (!sequence) return;
    for (const npc of this.npcs) npc.talkPrompt.setVisible(false);
    this.activeSequence = { sequence, nodeId: sequence.entry_node_id };
    this.renderDialogueNode();
  }

  private interactionSequenceForNpc(npcId: string): Sequence | undefined {
    const interaction = this.gameplay?.interactions.find(
      (entry) => entry.map_id === this.currentMap?.map_id && entry.actor_id === npcId,
    );
    return asSequences(this.manifest?.sequences ?? []).find(
      (entry) => entry.sequence_id === interaction?.sequence_id,
    );
  }

  private updateDialogueInput(): void {
    const keys = this.keys;
    if (!keys) return;
    if (
      Phaser.Input.Keyboard.JustDown(keys.interact) ||
      Phaser.Input.Keyboard.JustDown(keys.enter) ||
      Phaser.Input.Keyboard.JustDown(keys.jump)
    ) {
      this.advanceDialogue();
    }
  }

  private renderDialogueNode(): void {
    const active = this.activeSequence;
    const manifest = this.manifest;
    if (!active || !manifest) return;
    const node = active.sequence.nodes.find((entry) => entry.node_id === active.nodeId);
    if (!node || node.node_kind !== "dialogue") {
      this.applyOutcome(node);
      this.closeDialogue();
      return;
    }
    const speakerId = String(node.speaker_id);
    const expression = String(node.expression);
    const playerSpeaker = speakerId === manifest.player.player_id;
    const npc = manifest.npcs.find((entry) => entry.npc_id === speakerId);
    const binding = playerSpeaker ? manifest.player.dialogue : npc?.dialogue;
    const texture = playerSpeaker ? "prepared_player_dialogue" : `prepared_npc_${speakerId}_dialogue`;
    const expressionIndex = binding?.expressions.indexOf(expression) ?? 0;
    this.ensureDialogueUi();
    this.dialogueName?.setText(playerSpeaker ? manifest.player.display_name : npc?.display_name ?? speakerId);
    this.dialogueText?.setText(String(node.text));
    this.dialoguePortrait?.setTexture(texture, `expression_${Math.max(0, expressionIndex)}`);
    if (this.dialoguePortrait) {
      scaleSpriteFrameToHeight(this.dialoguePortrait, DIALOGUE_PORTRAIT_HEIGHT);
    }
    this.dialoguePortrait?.setVisible(true);
  }

  private advanceDialogue(): void {
    const active = this.activeSequence;
    if (!active) return;
    const node = active.sequence.nodes.find((entry) => entry.node_id === active.nodeId);
    if (!node || node.node_kind !== "dialogue") return;
    active.nodeId = String(node.next_node_id);
    this.renderDialogueNode();
  }

  private applyOutcome(node: SequenceNode | undefined): void {
    if (!node || node.node_kind !== "outcome" || !Array.isArray(node.effect_ids)) return;
    for (const effectId of node.effect_ids) {
      const effect = this.gameplay?.effects.find((entry) => entry.effect_id === effectId);
      if (!effect) continue;
      if (effect.operation === "grant_item") this.addInventory(String(effect.item_id), Number(effect.quantity));
      if (effect.operation === "set_quest_state") this.questStates.set(String(effect.quest_id), String(effect.state));
    }
  }

  private ensureDialogueUi(): void {
    if (this.dialoguePanel) {
      this.dialoguePanel.setVisible(true);
      this.dialogueText?.setVisible(true);
      this.dialogueName?.setVisible(true);
      return;
    }
    this.dialoguePanel = this.add.rectangle(VIEW_W / 2, DIALOGUE_PANEL_CENTER_Y, VIEW_W - 80, DIALOGUE_PANEL_HEIGHT, 0x182a3a, 0.94).setScrollFactor(0).setDepth(SCENE_CONTENT_DEPTH.dialogue);
    this.dialoguePanel.setStrokeStyle(4, 0xf1d69a, 1);
    this.dialogueName = this.add.text(300, VIEW_H - 205, "", { fontFamily: "Georgia, serif", fontSize: "25px", color: "#ffe6a9", fontStyle: "bold" }).setScrollFactor(0).setDepth(SCENE_CONTENT_DEPTH.dialogue + 1);
    this.dialogueText = this.add.text(300, VIEW_H - 160, "", { fontFamily: "system-ui, sans-serif", fontSize: "22px", color: "#ffffff", wordWrap: { width: 870 }, lineSpacing: 7 }).setScrollFactor(0).setDepth(SCENE_CONTENT_DEPTH.dialogue + 1);
    this.dialoguePortrait = this.add.sprite(175, DIALOGUE_PANEL_BOTTOM_Y, "prepared_player_dialogue", "expression_0").setOrigin(0.5, 1).setScrollFactor(0).setDepth(SCENE_CONTENT_DEPTH.dialogue + 1);
    scaleSpriteFrameToHeight(this.dialoguePortrait, DIALOGUE_PORTRAIT_HEIGHT);
  }

  private closeDialogue(): void {
    this.activeSequence = undefined;
    this.dialoguePanel?.setVisible(false);
    this.dialogueText?.setVisible(false);
    this.dialogueName?.setVisible(false);
    this.dialoguePortrait?.setVisible(false);
  }

  private createInterface(): void {
    this.debugOverlay = new DebugOverlay(this);
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
      inventory: [...this.inventory.entries()].map(([itemId, quantity]) => ({
        label:
          manifest.items.find((item) => item.item_id === itemId)?.display_name ??
          itemId,
        quantity,
      })),
    });
  }

  private addInventory(itemId: string, quantity: number): void {
    if (!Number.isFinite(quantity) || quantity <= 0) return;
    const integerQuantity = Math.floor(quantity);
    this.inventory.set(itemId, (this.inventory.get(itemId) ?? 0) + integerQuantity);
    const itemIndex = this.manifest?.items.findIndex((item) => item.item_id === itemId) ?? -1;
    if (itemIndex >= 0) {
      for (let index = 0; index < integerQuantity; index += 1) {
        this.inventoryHud?.addItem(itemIndex);
      }
    }
    for (const quest of this.gameplay?.quests ?? []) {
      if (
        quest.completion_item_id !== itemId ||
        this.questStates.get(quest.quest_id) !== "active" ||
        (this.inventory.get(itemId) ?? 0) < quest.completion_count
      )
        continue;
      const effect = this.gameplay?.effects.find(
        (entry) => entry.effect_id === quest.completion_effect_id,
      );
      if (effect?.operation === "set_quest_state") {
        this.questStates.set(String(effect.quest_id), String(effect.state));
      }
    }
  }

  private selectSoundtrack(map: PreparedMap): void {
    const manifest = this.manifest;
    const track = manifest?.soundtrack.tracks.find((entry) => entry.track_id === map.track_ids[0]);
    if (!track) return;
    this.soundtrack?.pause();
    this.soundtrack = new Audio(this.url(track.asset.path));
    this.soundtrack.loop = true;
    this.soundtrack.volume = 0.34;
    if (this.audioUnlocked) void this.soundtrack.play().catch(() => undefined);
  }

  private flashMapName(name: string): void {
    const banner = this.add.text(VIEW_W / 2, 105, name, { fontFamily: "Georgia, serif", fontSize: "36px", color: "#fff4cf", stroke: "#203849", strokeThickness: 7 }).setOrigin(0.5).setScrollFactor(0).setDepth(870).setAlpha(0);
    this.tweens.add({ targets: banner, alpha: 1, duration: 250, yoyo: true, hold: 1000, onComplete: () => banner.destroy() });
  }

  private fail(error: unknown): void {
    const message = error instanceof Error ? error.message : String(error);
    console.error("[prepared-scene] load failed:", message);
    this.children.getByName("loading-label")?.destroy();
    this.add.text(VIEW_W / 2, VIEW_H / 2, `Unable to load prepared game\n${message}`, { align: "center", color: "#ffffff", fontFamily: "system-ui, sans-serif", fontSize: "20px", backgroundColor: "#5b1720dd", padding: { x: 22, y: 16 }, wordWrap: { width: 900 } }).setOrigin(0.5).setScrollFactor(0).setDepth(1200);
  }
}

export type PreparedPreviewGameHandle = { destroy: (removeCanvas: boolean) => void };

export function bootPreparedGame(
  parent: HTMLElement,
  tag: string,
  transparencyPolicy: PreviewTransparencyPolicy,
  automationMode: GameplayAutomationMode | null = null,
): PreparedPreviewGameHandle {
  return new Phaser.Game({
    type: automationMode ? Phaser.CANVAS : Phaser.AUTO,
    width: GAMEPLAY_AUTOMATION_VIEWPORT.width,
    height: GAMEPLAY_AUTOMATION_VIEWPORT.height,
    parent,
    backgroundColor: "#000000",
    scene: [new PreparedStageScene(tag, transparencyPolicy)],
    scale: {
      mode: automationMode ? Phaser.Scale.NONE : Phaser.Scale.FIT,
      autoCenter: Phaser.Scale.CENTER_BOTH,
    },
  });
}
