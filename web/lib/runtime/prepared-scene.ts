import Phaser from "phaser";
import type { GameplayAutomationMode } from "./automation";
import { GAMEPLAY_AUTOMATION_VIEWPORT } from "./automation";
import {
  fetchJson,
  loadFrameStrip,
  loadGridSheet,
  loadOpaqueSprite,
  loadTileset,
  loadTransparentSprite,
  loadVerifiedRepeatLayer,
} from "./assets";
import {
  parsePreparedRuntimeManifest,
  preparedAssetUrl,
  type PreparedMap,
  type PreparedRuntimeManifest,
} from "./prepared-manifest";
import type { PreviewTransparencyPolicy } from "@/lib/shell/transparency";

const VIEW_W = 1280;
const VIEW_H = 720;
const WORLD_W = 12800;
const GROUND_Y = 610;
const PLAYER_HEIGHT = 154;
const MOB_HEIGHT = 110;
const NPC_HEIGHT = 150;

type Gameplay = Readonly<{
  entry_map_id: string;
  entry_spawn_id: string;
  player: Readonly<{ starting_health: number; starting_item_ids: readonly string[] }>;
  spawns: readonly Readonly<{ spawn_id: string; map_id: string; normalized_x: number }>[];
  transitions: readonly Readonly<{ from_map_id: string; to_map_id: string; to_spawn_id: string }>[];
  mob_population: Readonly<{
    maps: readonly Readonly<{
      map_id: string;
      zones: readonly Readonly<{
        left_fraction: number;
        right_fraction: number;
        initial_population: number;
        spawn_table: readonly Readonly<{ mob_id: string; weight: number }>[];
      }>[];
    }>[];
  }>;
  boss_encounters: readonly Readonly<{
    map_id: string;
    mob_id: string;
  }>[];
  loot_rules: readonly Readonly<{
    mob_id: string;
    item_id: string;
    chance: number;
    quantity_min: number;
    quantity_max: number;
  }>[];
  npc_placements: readonly Readonly<{ map_id: string; npc_id: string; normalized_x: number }>[];
  prop_placements: readonly Readonly<{ map_id: string; prop_id: string; normalized_x: number }>[];
  interactions: readonly Readonly<{ map_id: string; actor_id: string; sequence_id: string }>[];
  quests: readonly Readonly<{
    quest_id: string;
    completion_item_id: string;
    completion_count: number;
    completion_effect_id: string;
  }>[];
  effects: readonly Record<string, unknown>[];
}>;

type SequenceNode = Readonly<Record<string, unknown>>;
type Sequence = Readonly<{
  sequence_id: string;
  entry_node_id: string;
  nodes: readonly SequenceNode[];
}>;

type MobActor = {
  mobId: string;
  sprite: Phaser.GameObjects.Sprite;
  homeX: number;
  direction: 1 | -1;
  hp: number;
  hurtUntil: number;
  defeated: boolean;
};

type NpcActor = {
  npcId: string;
  sprite: Phaser.GameObjects.Sprite;
};

type DropActor = {
  itemId: string;
  sprite: Phaser.GameObjects.Image;
  quantity: number;
};

function asGameplay(value: Record<string, unknown>): Gameplay {
  return value as unknown as Gameplay;
}

function asSequences(values: readonly Record<string, unknown>[]): readonly Sequence[] {
  return values as unknown as readonly Sequence[];
}

function frameRate(state: string): number {
  if (state === "run") return 13;
  if (state === "walk" || state === "move") return 8;
  if (state.includes("attack") || state === "skill_cast") return 11;
  return 6;
}

function hpForRank(rank: string): number {
  if (rank === "boss") return 12;
  if (rank === "elite") return 6;
  if (rank === "uncommon") return 3;
  return 2;
}

export class PreparedStageScene extends Phaser.Scene {
  private readonly tag: string;
  private readonly transparencyPolicy: PreviewTransparencyPolicy;
  private manifest?: PreparedRuntimeManifest;
  private gameplay?: Gameplay;
  private ready = false;
  private loading = false;
  private currentMap?: PreparedMap;
  private player?: Phaser.GameObjects.Sprite;
  private playerFacing: "left" | "right" = "right";
  private playerVy = 0;
  private playerHp = 1;
  private playerAttackUntil = 0;
  private playerHurtUntil = 0;
  private keys?: Record<string, Phaser.Input.Keyboard.Key>;
  private layerSprites: Phaser.GameObjects.TileSprite[] = [];
  private groundSprites: Phaser.GameObjects.TileSprite[] = [];
  private props: Phaser.GameObjects.Image[] = [];
  private worldLabels: Phaser.GameObjects.Text[] = [];
  private mobs: MobActor[] = [];
  private npcs: NpcActor[] = [];
  private drops: DropActor[] = [];
  private inventory = new Map<string, number>();
  private questStates = new Map<string, string>();
  private hud?: Phaser.GameObjects.Text;
  private mapLabel?: Phaser.GameObjects.Text;
  private prompt?: Phaser.GameObjects.Text;
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
    _automationMode: GameplayAutomationMode | null,
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
    if (this.activeSequence) {
      this.updateDialogueInput();
      return;
    }
    this.updatePlayer(delta, now);
    this.updateMobs(delta, now);
    this.collectDrops();
    this.updateInteractionPrompt();
    this.updateHud();
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
    this.manifest = manifest;
    this.gameplay = asGameplay(manifest.gameplay);
    await Promise.all([
      this.loadPlayerAssets(manifest),
      this.loadMobAssets(manifest),
      this.loadNpcAssets(manifest),
      this.loadCatalogAssets(manifest),
      this.loadMapTextures(manifest),
    ]);
    this.installAnimations(manifest);
    this.installInput();
    for (const itemId of this.gameplay.player.starting_item_ids) this.addInventory(itemId, 1);
    this.playerHp = this.gameplay.player.starting_health;
    const openingSpawn = this.gameplay.spawns.find(
      (spawn) => spawn.spawn_id === this.gameplay?.entry_spawn_id,
    );
    await this.enterMap(
      manifest.entry_map_id,
      openingSpawn?.normalized_x ?? 0.08,
      false,
    );
    this.createHud();
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
      });
    }
  }

  private async loadPlayerAssets(manifest: PreparedRuntimeManifest): Promise<void> {
    await Promise.all(
      Object.entries(manifest.player.states).map(([state, binding]) =>
        loadFrameStrip(
          this.url(binding.asset.path),
          `prepared_player_${state}`,
          4,
          this.textures,
          this.transparencyPolicy,
        ),
      ),
    );
    await loadGridSheet(
      this.url(manifest.player.dialogue.asset.path),
      "prepared_player_dialogue",
      manifest.player.dialogue.rows,
      manifest.player.dialogue.columns,
      "expression",
      this.textures,
      this.transparencyPolicy,
    );
  }

  private async loadMobAssets(manifest: PreparedRuntimeManifest): Promise<void> {
    await Promise.all(
      manifest.mobs.flatMap((mob) =>
        Object.entries(mob.states).map(([state, binding]) =>
          loadFrameStrip(
            this.url(binding.asset.path),
            `prepared_mob_${mob.mob_id}_${state}`,
            4,
            this.textures,
            this.transparencyPolicy,
          ),
        ),
      ),
    );
  }

  private async loadNpcAssets(manifest: PreparedRuntimeManifest): Promise<void> {
    await Promise.all(
      manifest.npcs.flatMap((npc) => [
        loadFrameStrip(
          this.url(npc.world.asset.path),
          `prepared_npc_${npc.npc_id}_world`,
          4,
          this.textures,
          this.transparencyPolicy,
        ),
        loadGridSheet(
          this.url(npc.dialogue.asset.path),
          `prepared_npc_${npc.npc_id}_dialogue`,
          npc.dialogue.rows,
          npc.dialogue.columns,
          "expression",
          this.textures,
          this.transparencyPolicy,
        ),
      ]),
    );
  }

  private async loadCatalogAssets(manifest: PreparedRuntimeManifest): Promise<void> {
    await Promise.all([
      ...manifest.props.map((prop) =>
        loadTransparentSprite(
          this.url(prop.asset.path),
          `prepared_prop_${prop.prop_id}`,
          this.textures,
          this.transparencyPolicy,
        ),
      ),
      ...manifest.items.map((item) =>
        loadTransparentSprite(
          this.url(item.asset.path),
          `prepared_item_${item.item_id}`,
          this.textures,
          this.transparencyPolicy,
        ),
      ),
    ]);
  }

  private async loadMapTextures(manifest: PreparedRuntimeManifest): Promise<void> {
    await Promise.all(
      manifest.maps.flatMap((map) => [
        ...map.layers.map((layer) =>
          loadVerifiedRepeatLayer(
            this.url(layer.asset.path),
            `prepared_map_${map.map_id}_${layer.layer_id}`,
            layer.alpha_mode === "opaque",
            layer.asset.width ?? 1536,
            this.textures,
          ),
        ),
        loadTileset(
          this.url(map.ground.asset.path),
          `prepared_ground_${map.map_id}`,
          this.textures,
          this.transparencyPolicy,
        ),
      ]),
    );
  }

  private installAnimations(manifest: PreparedRuntimeManifest): void {
    for (const state of Object.keys(manifest.player.states)) {
      const key = `prepared_player_${state}`;
      this.anims.create({
        key,
        frames: [0, 1, 2, 3].map((frame) => ({ key, frame })),
        frameRate: frameRate(state),
        repeat: state.includes("attack") || state === "hurt" || state === "death" ? 0 : -1,
      });
    }
    for (const mob of manifest.mobs) {
      for (const state of Object.keys(mob.states)) {
        const texture = `prepared_mob_${mob.mob_id}_${state}`;
        this.anims.create({
          key: texture,
          frames: [0, 1, 2, 3].map((frame) => ({ key: texture, frame })),
          frameRate: frameRate(state),
          repeat: state === "death" || state === "hurt" || state === "attack" ? 0 : -1,
        });
      }
    }
    for (const npc of manifest.npcs) {
      const key = `prepared_npc_${npc.npc_id}_world`;
      this.anims.create({
        key,
        frames: [0, 1, 2, 3].map((frame) => ({ key, frame })),
        frameRate: 5,
        repeat: -1,
      });
    }
  }

  private installInput(): void {
    const keyboard = this.input.keyboard;
    if (!keyboard) return;
    this.keys = {
      left: keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.LEFT),
      right: keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.RIGHT),
      a: keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.A),
      d: keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.D),
      jump: keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.SPACE),
      up: keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.UP),
      w: keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.W),
      attack: keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.J),
      attack2: keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.X),
      attack3: keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.Z),
      interact: keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.E),
      enter: keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.ENTER),
      shift: keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.SHIFT),
    };
    const startAudio = () => {
      if (!this.soundtrack) return;
      this.audioUnlocked = true;
      void this.soundtrack?.play().catch(() => undefined);
      keyboard.off("keydown", startAudio);
    };
    keyboard.on("keydown", startAudio);
  }

  private async enterMap(mapId: string, normalizedX: number, announce = true): Promise<void> {
    const manifest = this.manifest;
    const gameplay = this.gameplay;
    if (!manifest || !gameplay) return;
    const map = manifest.maps.find((entry) => entry.map_id === mapId);
    if (!map) throw new Error(`runtime transition names unknown map ${mapId}`);
    this.loading = true;
    this.currentMap = map;
    this.clearWorld();
    this.renderMap(map);
    this.renderPlacements(map);
    if (map.hostile_population_enabled) this.spawnMapMobs(map);
    const player = this.add.sprite(normalizedX * WORLD_W, GROUND_Y, "prepared_player_idle", 0);
    player.setOrigin(0.5, 1).setDisplaySize(PLAYER_HEIGHT * 0.8, PLAYER_HEIGHT).setDepth(40);
    player.play("prepared_player_idle");
    this.player = player;
    this.cameras.main.setBounds(0, 0, WORLD_W, VIEW_H);
    this.cameras.main.startFollow(player, true, 0.12, 0.12, 0, 50);
    this.cameras.main.setDeadzone(300, 180);
    this.cameras.main.scrollY = 0;
    this.mapLabel?.setText(map.display_name);
    this.selectSoundtrack(map);
    this.loading = false;
    if (announce) this.flashMapName(map.display_name);
  }

  private clearWorld(): void {
    this.player?.destroy();
    this.player = undefined;
    for (const sprite of [
      ...this.layerSprites,
      ...this.groundSprites,
      ...this.props,
      ...this.worldLabels,
    ])
      sprite.destroy();
    for (const mob of this.mobs) mob.sprite.destroy();
    for (const npc of this.npcs) npc.sprite.destroy();
    for (const drop of this.drops) drop.sprite.destroy();
    this.layerSprites = [];
    this.groundSprites = [];
    this.props = [];
    this.worldLabels = [];
    this.mobs = [];
    this.npcs = [];
    this.drops = [];
  }

  private renderMap(map: PreparedMap): void {
    const ordered = [...map.layers].sort((left, right) => {
      const plane = left.plane === right.plane ? 0 : left.plane === "background" ? -1 : 1;
      return plane || left.order - right.order;
    });
    ordered.forEach((layer, index) => {
      const key = `prepared_map_${map.map_id}_${layer.layer_id}`;
      const sourceHeight = layer.asset.height ?? 1024;
      const scale = VIEW_H / sourceHeight;
      const sprite = this.add.tileSprite(0, 0, VIEW_W / scale, VIEW_H / scale, key);
      sprite
        .setOrigin(0, 0)
        .setScale(scale)
        .setScrollFactor(0)
        .setDepth(layer.plane === "foreground" ? 80 + index : index - 20)
        .setData("parallax", layer.parallax);
      this.layerSprites.push(sprite);
    });
    const groundKey = `prepared_ground_${map.map_id}`;
    const fill = this.add
      .tileSprite(0, GROUND_Y, WORLD_W, VIEW_H - GROUND_Y, `${groundKey}_continuous_fill`)
      .setOrigin(0, 0)
      .setDepth(10);
    const surface = this.add
      .tileSprite(0, GROUND_Y - 22, WORLD_W, 30, `${groundKey}_continuous_surface`)
      .setOrigin(0, 0)
      .setDepth(11);
    this.groundSprites.push(fill, surface);
  }

  private renderPlacements(map: PreparedMap): void {
    const manifest = this.manifest;
    const gameplay = this.gameplay;
    if (!manifest || !gameplay) return;
    for (const placement of gameplay.prop_placements.filter((entry) => entry.map_id === map.map_id)) {
      const prop = manifest.props.find((entry) => entry.prop_id === placement.prop_id);
      if (!prop) continue;
      const sprite = this.add
        .image(placement.normalized_x * WORLD_W, GROUND_Y, `prepared_prop_${prop.prop_id}`)
        .setOrigin(0.5, 1)
        .setDepth(25);
      const height = prop.prop_id.includes("stall") ? 170 : 110;
      sprite.setDisplaySize(Math.min(220, (sprite.width / sprite.height) * height), height);
      this.props.push(sprite);
    }
    for (const placement of gameplay.npc_placements.filter((entry) => entry.map_id === map.map_id)) {
      const npc = manifest.npcs.find((entry) => entry.npc_id === placement.npc_id);
      if (!npc) continue;
      const sprite = this.add
        .sprite(placement.normalized_x * WORLD_W, GROUND_Y, `prepared_npc_${npc.npc_id}_world`, 0)
        .setOrigin(0.5, 1)
        .setDisplaySize(NPC_HEIGHT * 0.75, NPC_HEIGHT)
        .setDepth(35);
      sprite.play(`prepared_npc_${npc.npc_id}_world`);
      this.npcs.push({ npcId: npc.npc_id, sprite });
      const label = this.add
        .text(sprite.x, GROUND_Y - NPC_HEIGHT - 12, npc.display_name, {
          fontFamily: "system-ui, sans-serif",
          fontSize: "15px",
          color: "#fff7dc",
          stroke: "#283b46",
          strokeThickness: 4,
        })
        .setOrigin(0.5, 1)
        .setDepth(36);
      this.worldLabels.push(label);
    }
  }

  private spawnMapMobs(map: PreparedMap): void {
    const manifest = this.manifest;
    const population = this.gameplay?.mob_population.maps.find((entry) => entry.map_id === map.map_id);
    if (!manifest || !population) return;
    for (const zone of population.zones) {
      for (let index = 0; index < zone.initial_population; index += 1) {
        const tableWeight = zone.spawn_table.reduce((sum, entry) => sum + entry.weight, 0);
        let cursor = (index * 7 + zone.initial_population) % tableWeight;
        const selected = zone.spawn_table.find((entry) => {
          cursor -= entry.weight;
          return cursor < 0;
        }) ?? zone.spawn_table[0];
        if (!selected) continue;
        const spec = manifest.mobs.find((entry) => entry.mob_id === selected.mob_id);
        if (!spec) continue;
        const fraction = zone.left_fraction + ((index + 1) / (zone.initial_population + 1)) * (zone.right_fraction - zone.left_fraction);
        const sprite = this.add
          .sprite(fraction * WORLD_W, GROUND_Y, `prepared_mob_${spec.mob_id}_idle`, 0)
          .setOrigin(0.5, 1)
          .setDisplaySize(MOB_HEIGHT, MOB_HEIGHT)
          .setDepth(38);
        sprite.play(`prepared_mob_${spec.mob_id}_idle`);
        this.mobs.push({
          mobId: spec.mob_id,
          sprite,
          homeX: sprite.x,
          direction: index % 2 === 0 ? 1 : -1,
          hp: hpForRank(spec.rank),
          hurtUntil: 0,
          defeated: false,
        });
      }
    }
    for (const encounter of this.gameplay?.boss_encounters.filter(
      (entry) => entry.map_id === map.map_id,
    ) ?? []) {
      const spec = manifest.mobs.find((entry) => entry.mob_id === encounter.mob_id);
      if (!spec) continue;
      const sprite = this.add
        .sprite(WORLD_W * 0.91, GROUND_Y, `prepared_mob_${spec.mob_id}_idle`, 0)
        .setOrigin(0.5, 1)
        .setDisplaySize(MOB_HEIGHT * 1.55, MOB_HEIGHT * 1.55)
        .setDepth(39);
      sprite.play(`prepared_mob_${spec.mob_id}_idle`);
      this.mobs.push({
        mobId: spec.mob_id,
        sprite,
        homeX: sprite.x,
        direction: -1,
        hp: hpForRank(spec.rank),
        hurtUntil: 0,
        defeated: false,
      });
    }
  }

  private updatePlayer(delta: number, now: number): void {
    const player = this.player;
    const keys = this.keys;
    if (!player || !keys || !this.currentMap) return;
    const left = keys.left.isDown || keys.a.isDown;
    const right = keys.right.isDown || keys.d.isDown;
    const running = keys.shift.isDown;
    const speed = running ? 380 : 235;
    let vx = 0;
    if (left !== right) {
      vx = left ? -speed : speed;
      this.playerFacing = left ? "left" : "right";
    }
    const grounded = player.y >= GROUND_Y - 0.5;
    if (grounded && Phaser.Input.Keyboard.JustDown(keys.jump)) this.playerVy = -570;
    this.playerVy += 1550 * (delta / 1000);
    player.x = Phaser.Math.Clamp(player.x + vx * (delta / 1000), 30, WORLD_W - 30);
    player.y = Math.min(GROUND_Y, player.y + this.playerVy * (delta / 1000));
    if (player.y >= GROUND_Y) this.playerVy = 0;
    player.setFlipX(this.playerFacing === "left");

    const attacking =
      Phaser.Input.Keyboard.JustDown(keys.attack) ||
      Phaser.Input.Keyboard.JustDown(keys.attack2) ||
      Phaser.Input.Keyboard.JustDown(keys.attack3);
    if (attacking && now >= this.playerAttackUntil) {
      this.playerAttackUntil = now + 380;
      player.play("prepared_player_basic_attack", true);
      for (const mob of this.mobs) {
        if (!mob.defeated && Math.abs(mob.sprite.x - player.x) < 145) this.hitMob(mob, now);
      }
    }
    if (now < this.playerAttackUntil || now < this.playerHurtUntil) return;
    const state = !grounded ? "jump" : vx === 0 ? "idle" : running ? "run" : "walk";
    const animation = `prepared_player_${state}`;
    if (player.anims.currentAnim?.key !== animation) player.play(animation, true);

    const travelRequested =
      Phaser.Input.Keyboard.JustDown(keys.up) || Phaser.Input.Keyboard.JustDown(keys.w);
    if (travelRequested && (player.x < 110 || player.x > WORLD_W - 110)) {
      const transition = this.gameplay?.transitions.find(
        (entry) => entry.from_map_id === this.currentMap?.map_id,
      );
      const spawn = this.gameplay?.spawns.find((entry) => entry.spawn_id === transition?.to_spawn_id);
      if (transition && spawn) void this.enterMap(transition.to_map_id, spawn.normalized_x);
    }
  }

  private updateMobs(delta: number, now: number): void {
    const player = this.player;
    if (!player) return;
    for (const mob of this.mobs) {
      if (mob.defeated || now < mob.hurtUntil) continue;
      const distance = player.x - mob.sprite.x;
      if (Math.abs(distance) < 420) mob.direction = distance < 0 ? -1 : 1;
      else if (Math.abs(mob.sprite.x - mob.homeX) > 170) mob.direction = mob.sprite.x < mob.homeX ? 1 : -1;
      const speed = Math.abs(distance) < 420 ? 62 : 32;
      mob.sprite.x += mob.direction * speed * (delta / 1000);
      mob.sprite.setFlipX(mob.direction < 0);
      const animation = `prepared_mob_${mob.mobId}_${Math.abs(distance) < 420 ? "move" : "idle"}`;
      if (mob.sprite.anims.currentAnim?.key !== animation) mob.sprite.play(animation, true);
      if (Math.abs(distance) < 62 && now >= this.playerHurtUntil) {
        this.playerHp = Math.max(0, this.playerHp - 1);
        this.playerHurtUntil = now + 800;
        this.player?.play("prepared_player_hurt", true);
      }
    }
  }

  private hitMob(mob: MobActor, now: number): void {
    mob.hp -= 1;
    if (mob.hp > 0) {
      mob.hurtUntil = now + 420;
      mob.sprite.play(`prepared_mob_${mob.mobId}_hurt`, true);
      return;
    }
    mob.defeated = true;
    mob.sprite.play(`prepared_mob_${mob.mobId}_death`, true);
    this.tweens.add({ targets: mob.sprite, alpha: 0, duration: 650, onComplete: () => mob.sprite.destroy() });
    this.rollLoot(mob);
  }

  private rollLoot(mob: MobActor): void {
    const rules = this.gameplay?.loot_rules.filter((entry) => entry.mob_id === mob.mobId) ?? [];
    for (const rule of rules) {
      const deterministicRoll = ((Math.floor(mob.homeX) * 2654435761) >>> 0) / 0xffffffff;
      if (deterministicRoll > rule.chance) continue;
      const span = rule.quantity_max - rule.quantity_min + 1;
      const quantity = rule.quantity_min + (Math.floor(mob.homeX / 64) % span);
      const sprite = this.add
        .image(mob.sprite.x, GROUND_Y - 20, `prepared_item_${rule.item_id}`)
        .setDisplaySize(54, 54)
        .setDepth(42);
      this.drops.push({ itemId: rule.item_id, sprite, quantity });
    }
  }

  private collectDrops(): void {
    const player = this.player;
    if (!player) return;
    for (const drop of [...this.drops]) {
      if (Math.abs(drop.sprite.x - player.x) > 70) continue;
      this.addInventory(drop.itemId, drop.quantity);
      drop.sprite.destroy();
      this.drops.splice(this.drops.indexOf(drop), 1);
    }
  }

  private updateInteractionPrompt(): void {
    const player = this.player;
    const keys = this.keys;
    if (!player || !keys || !this.currentMap) return;
    const nearest = this.npcs
      .filter((npc) => Math.abs(npc.sprite.x - player.x) < 145)
      .sort((left, right) => Math.abs(left.sprite.x - player.x) - Math.abs(right.sprite.x - player.x))[0];
    const atPortal = player.x < 110 || player.x > WORLD_W - 110;
    this.prompt?.setText(nearest ? "E  Talk" : atPortal ? "W / ↑  Travel" : "");
    if (nearest && (Phaser.Input.Keyboard.JustDown(keys.interact) || Phaser.Input.Keyboard.JustDown(keys.enter))) {
      this.openInteraction(nearest.npcId);
    }
  }

  private openInteraction(npcId: string): void {
    const interaction = this.gameplay?.interactions.find(
      (entry) => entry.map_id === this.currentMap?.map_id && entry.actor_id === npcId,
    );
    const sequence = asSequences(this.manifest?.sequences ?? []).find(
      (entry) => entry.sequence_id === interaction?.sequence_id,
    );
    if (!sequence) return;
    this.activeSequence = { sequence, nodeId: sequence.entry_node_id };
    this.renderDialogueNode();
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
    this.dialoguePanel = this.add.rectangle(VIEW_W / 2, VIEW_H - 128, VIEW_W - 80, 210, 0x182a3a, 0.94).setScrollFactor(0).setDepth(900);
    this.dialoguePanel.setStrokeStyle(4, 0xf1d69a, 1);
    this.dialogueName = this.add.text(300, VIEW_H - 205, "", { fontFamily: "Georgia, serif", fontSize: "25px", color: "#ffe6a9", fontStyle: "bold" }).setScrollFactor(0).setDepth(902);
    this.dialogueText = this.add.text(300, VIEW_H - 160, "", { fontFamily: "system-ui, sans-serif", fontSize: "22px", color: "#ffffff", wordWrap: { width: 870 }, lineSpacing: 7 }).setScrollFactor(0).setDepth(902);
    this.dialoguePortrait = this.add.sprite(175, VIEW_H - 35, "prepared_player_dialogue", "expression_0").setOrigin(0.5, 1).setDisplaySize(190, 190).setScrollFactor(0).setDepth(902);
  }

  private closeDialogue(): void {
    this.activeSequence = undefined;
    this.dialoguePanel?.setVisible(false);
    this.dialogueText?.setVisible(false);
    this.dialogueName?.setVisible(false);
    this.dialoguePortrait?.setVisible(false);
  }

  private createHud(): void {
    this.hud = this.add.text(18, 18, "", { fontFamily: "system-ui, sans-serif", fontSize: "17px", color: "#ffffff", backgroundColor: "#122536bb", padding: { x: 12, y: 9 } }).setScrollFactor(0).setDepth(850);
    this.mapLabel = this.add.text(VIEW_W / 2, 20, this.currentMap?.display_name ?? "", { fontFamily: "Georgia, serif", fontSize: "22px", color: "#fff3cc", stroke: "#1a3342", strokeThickness: 5 }).setOrigin(0.5, 0).setScrollFactor(0).setDepth(850);
    this.prompt = this.add.text(VIEW_W / 2, VIEW_H - 42, "", { fontFamily: "system-ui, sans-serif", fontSize: "20px", color: "#ffffff", backgroundColor: "#172b3ccc", padding: { x: 13, y: 7 } }).setOrigin(0.5).setScrollFactor(0).setDepth(850);
    this.updateHud();
  }

  private updateHud(): void {
    const manifest = this.manifest;
    if (!manifest || !this.hud) return;
    const inventory = [...this.inventory.entries()]
      .filter(([, quantity]) => quantity > 0)
      .map(([itemId, quantity]) => `${manifest.items.find((item) => item.item_id === itemId)?.display_name ?? itemId} ×${quantity}`)
      .join("  ·  ");
    this.hud.setText(`HP ${this.playerHp}/${this.gameplay?.player.starting_health ?? this.playerHp}\n${inventory}`);
  }

  private addInventory(itemId: string, quantity: number): void {
    if (!Number.isFinite(quantity) || quantity <= 0) return;
    this.inventory.set(itemId, (this.inventory.get(itemId) ?? 0) + Math.floor(quantity));
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
    scene: [new PreparedStageScene(tag, transparencyPolicy, automationMode)],
    scale: {
      mode: automationMode ? Phaser.Scale.NONE : Phaser.Scale.FIT,
      autoCenter: Phaser.Scale.CENTER_BOTH,
    },
  });
}
