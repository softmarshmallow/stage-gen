// Per-tag Phaser 4 scene loader (Phase 6).
//
// Builds a full playable stage from a complete `out/<tag>/` asset directory:
//   - skybox (parallax 0, fixed to camera)             → TC-071
//   - parallax layers (TileSprite per layer)           → TC-072 / TC-073
//   - ground (heightmap-driven 12×4 tileset assembly)  → TC-074
//   - obstacles on flat columns                        → TC-075
//   - mobs with looping idle animation                 → TC-076
//   - player anchored bottom-center on ground band     → TC-077
//   - foreground band (high-parallax + blur)           → TC-078
//   - FPS probe                                        → TC-079
//
// A simple auto-pan + arrow-key camera lets us observe parallax behaviour
// before Phase 7 hands movement to the player.

import Phaser from "phaser";
import {
  alphaAt,
  type CellRect,
} from "./image-ops";
import {
  fetchJson,
  loadParallaxLayer,
  loadChromaKeyedSprite,
  loadFrameStrip,
  loadGridSheet,
  loadTileset,
} from "./assets";
import { buildHeightmap, slopeAt, flatRuns, type SlopeKind } from "./heightmap";
import { pickRole } from "./tiles";
import { FpsProbe, type FpsSnapshot } from "./fps";

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
  world: { name: string; one_liner: string; narrative: string };
  mobs: { tier_label: string; body_plan: string; name: string; brief: string }[];
  obstacles: { sheet_theme: string; props: { name: string; brief: string }[] }[];
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
    { layerId: string; leftEdgeAlpha: number; inwardAlpha: number; width: number; height: number; parallax: number; opaque: boolean }
  >;
  spriteChromaProbe: Record<
    string,
    { spriteKey: string; sampledAlpha: number; sampledAt: { x: number; y: number } }
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
};

declare global {
  interface Window {
    __sceneProbes?: SceneProbes;
    __sceneReady?: boolean;
    __sceneFps?: FpsSnapshot;
    __sceneCamera?: { scrollX: number };
  }
}

export type SceneInit = { tag: string };

export class StageScene extends Phaser.Scene {
  private tag: string;
  private probes!: SceneProbes;
  private fpsProbe = new FpsProbe(30);

  // Parallax sprite tracking — index by layer id.
  private parallaxSprites: { id: string; sprite: Phaser.GameObjects.TileSprite; parallax: number }[] = [];
  // Foreground (parallax > 1.0): TileSprites placed in front of gameplay.
  private foregroundSprites: { id: string; sprite: Phaser.GameObjects.TileSprite; parallax: number }[] = [];

  private cursors?: Phaser.Types.Input.Keyboard.CursorKeys;
  private autoPan = true;
  private autoPanSpeed = 100; // px/s

  constructor(init: SceneInit) {
    super({ key: "StageScene" });
    this.tag = init.tag;
  }

  create() {
    this.probes = {
      tag: this.tag,
      loadedAssetKeys: [],
      parallaxAlphaProbe: {},
      spriteChromaProbe: {},
      cellExtractProbe: {},
      consoleErrors: [],
      heightmap: [],
      flatRunCount: 0,
      obstacleCount: 0,
      mobCount: 0,
      playerColumn: 0,
      foregroundLayers: [],
    };
    if (typeof window !== "undefined") window.__sceneProbes = this.probes;

    // Patch console.error to track errors during the first few seconds.
    const origErr = console.error.bind(console);
    console.error = ((...args: unknown[]) => {
      try {
        this.probes.consoleErrors.push(args.map((a) => String(a)).join(" "));
      } catch {}
      origErr(...args);
    }) as typeof console.error;

    // Camera bounds — generous; loadAll() will narrow to STAGE_W after ground.
    this.cameras.main.setBounds(0, 0, STAGE_W, VIEW_H);
    this.cursors = this.input.keyboard?.createCursorKeys();

    this.fpsProbe.start();

    this.loadAll().catch((err) => {
      console.error("[scene] loadAll failed:", err);
      this.probes.consoleErrors.push(String((err as Error)?.message ?? err));
    });

    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
      this.fpsProbe.stop();
    });
  }

  update(_time: number, deltaMs: number) {
    const cam = this.cameras.main;
    const dt = deltaMs / 1000;

    // Manual camera control: arrows override auto-pan.
    let userMoved = false;
    if (this.cursors) {
      if (this.cursors.left?.isDown) {
        cam.scrollX -= 200 * dt;
        userMoved = true;
      }
      if (this.cursors.right?.isDown) {
        cam.scrollX += 200 * dt;
        userMoved = true;
      }
    }
    if (this.autoPan && !userMoved) {
      cam.scrollX += this.autoPanSpeed * dt;
      // Bounce back at the right edge so observation runs forever.
      if (cam.scrollX > STAGE_W - VIEW_W) {
        cam.scrollX = 0;
      }
    }
    if (cam.scrollX < 0) cam.scrollX = 0;

    // Drive parallax tilePosition based on scrollX × parallax.
    // We use TileSprites with scrollFactor=0 (camera-fixed); the wrap is
    // achieved by mutating tilePositionX. Deeper layers (smaller parallax)
    // → smaller displacement; foreground (parallax > 1.0) → larger.
    for (const p of this.parallaxSprites) {
      p.sprite.tilePositionX = cam.scrollX * p.parallax;
    }
    for (const p of this.foregroundSprites) {
      p.sprite.tilePositionX = cam.scrollX * p.parallax;
    }

    if (typeof window !== "undefined") {
      window.__sceneCamera = { scrollX: cam.scrollX };
      if (window.__sceneFps) this.probes.fps = window.__sceneFps;
      // Surface live tilePositionX per layer for headless parallax verification.
      const tiles: Record<string, { parallax: number; tilePositionX: number; depth: number }> = {};
      for (const p of this.parallaxSprites) {
        tiles[p.id] = { parallax: p.parallax, tilePositionX: p.sprite.tilePositionX, depth: p.sprite.depth };
      }
      for (const p of this.foregroundSprites) {
        tiles[p.id] = { parallax: p.parallax, tilePositionX: p.sprite.tilePositionX, depth: p.sprite.depth };
      }
      (window as unknown as { __sceneTiles?: typeof tiles }).__sceneTiles = tiles;
    }
  }

  // ---------- Loading ----------

  private async loadAll() {
    const tag = this.tag;
    const u = (f: string) => assetUrl(tag, f);

    // World spec.
    const spec = await fetchJson<WorldSpec>(u(`world_spec_${tag}.json`));
    this.probes.loadedAssetKeys.push(`spec:${spec.world.name}`);

    // ---------- Heightmap (deterministic from tag) ----------
    const heights = buildHeightmap(tag, { cols: COLS, minH: MIN_H, maxH: MAX_H });
    this.probes.heightmap = heights;

    // ---------- Parallax layers ----------
    // Sort by z_index ascending so we render back-to-front.
    const sortedLayers = [...spec.layers].sort((a, b) => a.z_index - b.z_index);
    for (const layer of sortedLayers) {
      const file = `layer_${tag}_${layer.id}.png`;
      const key = `layer_${layer.id}`;
      try {
        const loaded = await loadParallaxLayer(
          u(file),
          key,
          layer.opaque,
          64,
          this.textures,
        );
        this.probes.loadedAssetKeys.push(key);

        // Probe alpha at left edge + 64 px inward (for non-opaque).
        const yMid = Math.floor(loaded.height / 2);
        const leftEdgeAlpha = layer.opaque ? 255 : alphaAt(loaded.canvas, 0, yMid);
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

        // Mount into the scene. All parallax layers are TileSprites with
        // scrollFactor=0 (we move tilePositionX manually each frame).
        const sprite = this.add.tileSprite(0, 0, VIEW_W, VIEW_H, key);
        sprite.setOrigin(0, 0);
        sprite.setScrollFactor(0);
        // Scale tile so its texture height fills VIEW_H. Phaser TileSprite
        // tiles at the texture's native size; setting tileScale scales the
        // tiled pattern.
        const ts = VIEW_H / loaded.height;
        sprite.setTileScale(ts, ts);

        if (layer.parallax > 1.0) {
          // Foreground accent — render in front of gameplay (depth 1000+).
          sprite.setDepth(1000 + layer.z_index);
          // Apply a Gaussian-ish blur via canvas filter on the WebGL texture.
          // Phaser 4 supports preFX.addBlur on GameObjects.
          try {
            // setPostPipeline requires WebGL. Use the built-in BlurFX where available.
            const fx = (sprite as unknown as {
              postFX?: { addBlur?: (q?: number, x?: number, y?: number, str?: number, color?: number, steps?: number) => unknown };
            }).postFX;
            if (fx?.addBlur) {
              const strength = Math.min(4, (layer.parallax - 1.0) * 6);
              fx.addBlur(0, 2, 2, strength, 0xffffff, 4);
            } else {
              // Canvas fallback: apply a CSS-like blur via a per-frame filter
              // baked into a copy canvas. Skip for now; the depth ordering
              // alone proves "foreground in front".
            }
          } catch {
            // best effort — blur is cosmetic
          }
          this.foregroundSprites.push({ id: layer.id, sprite, parallax: layer.parallax });
          this.probes.foregroundLayers.push(layer.id);
        } else if (layer.opaque) {
          // Skybox: scrollFactor 0, no parallax math needed; tilePositionX
          // stays 0 so it's truly fixed to the camera.
          sprite.setDepth(0);
          this.parallaxSprites.push({ id: layer.id, sprite, parallax: 0 });
        } else {
          // Mid background.
          sprite.setDepth(layer.z_index);
          this.parallaxSprites.push({ id: layer.id, sprite, parallax: layer.parallax });
        }
      } catch (e) {
        this.recordErr(e);
      }
    }

    // ---------- Tileset + ground assembly ----------
    let tileW = TILE_PX;
    let tileH = TILE_PX;
    try {
      const ts = await loadTileset(u(`tileset_${tag}.png`), `tileset`, this.textures);
      this.probes.loadedAssetKeys.push(`tileset`);
      tileW = ts.tileW;
      tileH = ts.tileH;
    } catch (e) {
      this.recordErr(e);
    }
    this.assembleGround(heights, tileW, tileH);

    // ---------- Obstacle sheets ----------
    const obstacleCells: { sheetIdx: number; cellIdx: number; w: number; h: number }[] = [];
    for (let i = 0; i < spec.obstacles.length; i++) {
      const file = `obstacles_${tag}_${i}.png`;
      const key = `obstacles_${i}`;
      try {
        const { cells } = await loadGridSheet(u(file), key, 2, 4, "prop", this.textures);
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

    // Place obstacles on flat columns (footprint width: 1 column).
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
      );
      this.probes.cellExtractProbe[`items`] = cells;
      this.probes.loadedAssetKeys.push(`items`);
    } catch (e) {
      this.recordErr(e);
    }

    // ---------- Mobs (idle + hurt + concept) ----------
    const mobIdleKeys: string[] = [];
    for (let i = 0; i < spec.mobs.length; i++) {
      const idleKey = `mob_${i}_idle`;
      try {
        await loadFrameStrip(
          u(`mob_${tag}_${i}_idle.png`),
          idleKey,
          4,
          this.textures,
        );
        this.probes.loadedAssetKeys.push(idleKey);
        mobIdleKeys.push(idleKey);
        // Build the looping anim if the manager doesn't have it yet.
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
      }
      const hurtKey = `mob_${i}_hurt`;
      try {
        await loadFrameStrip(u(`mob_${tag}_${i}_hurt.png`), hurtKey, 4, this.textures);
        this.probes.loadedAssetKeys.push(hurtKey);
      } catch (e) {
        this.recordErr(e);
      }
      try {
        await loadChromaKeyedSprite(
          u(`mob_concept_${tag}_${i}.png`),
          `mob_concept_${i}`,
          this.textures,
        );
        this.probes.loadedAssetKeys.push(`mob_concept_${i}`);
      } catch (e) {
        this.recordErr(e);
      }
    }

    this.spawnMobs(heights, mobIdleKeys);

    // ---------- Character ----------
    let charSprite: HTMLCanvasElement | null = null;
    try {
      charSprite = await loadChromaKeyedSprite(
        u(`character_concept_${tag}.png`),
        `character_concept`,
        this.textures,
      );
      this.probes.loadedAssetKeys.push(`character_concept`);
      // Spot-check chroma probe (top-left corner is reliably background).
      const sampleAt = { x: 1, y: 1 };
      this.probes.spriteChromaProbe[`character_concept`] = {
        spriteKey: `character_concept`,
        sampledAlpha: alphaAt(charSprite, sampleAt.x, sampleAt.y),
        sampledAt: sampleAt,
      };
    } catch (e) {
      this.recordErr(e);
    }
    // Idle strip (sliced) — preferred for the runtime player avatar.
    try {
      await loadFrameStrip(
        u(`character_${tag}-fromcombined_idle.png`),
        `character_idle`,
        4,
        this.textures,
      );
      this.probes.loadedAssetKeys.push(`character_idle`);
      if (!this.anims.exists(`character_idle`)) {
        this.anims.create({
          key: `character_idle`,
          frames: [0, 1, 2, 3].map((f) => ({ key: `character_idle`, frame: f })),
          frameRate: 4,
          repeat: -1,
        });
      }
    } catch (e) {
      this.recordErr(e);
    }
    // Other states (walk/run/jump/crawl/attack) — load now so Phase 7 can use them.
    for (const state of ["walk", "run", "jump", "crawl"]) {
      try {
        await loadFrameStrip(
          u(`character_${tag}-fromcombined_${state}.png`),
          `character_${state}`,
          4,
          this.textures,
        );
        this.probes.loadedAssetKeys.push(`character_${state}`);
      } catch (e) {
        this.recordErr(e);
      }
    }
    try {
      await loadFrameStrip(u(`character_${tag}_attack.png`), `character_attack`, 4, this.textures);
      this.probes.loadedAssetKeys.push(`character_attack`);
    } catch (e) {
      this.recordErr(e);
    }

    this.spawnPlayer(heights);

    // ---------- Inventory + portal ----------
    try {
      await loadChromaKeyedSprite(u(`inventory_${tag}.png`), `inventory`, this.textures);
      this.probes.loadedAssetKeys.push(`inventory`);
    } catch (e) {
      this.recordErr(e);
    }
    try {
      await loadChromaKeyedSprite(u(`portal_${tag}.png`), `portal`, this.textures);
      this.probes.loadedAssetKeys.push(`portal`);
    } catch (e) {
      this.recordErr(e);
    }

    // Concept (purely for completeness; not displayed).
    try {
      await loadChromaKeyedSprite(u(`concept_${tag}.png`), `concept`, this.textures);
      this.probes.loadedAssetKeys.push(`concept`);
    } catch (e) {
      this.recordErr(e);
    }

    if (typeof window !== "undefined") {
      window.__sceneReady = true;
    }
  }

  // ---------- Ground assembly ----------

  private assembleGround(heights: number[], srcTileW: number, srcTileH: number) {
    // We render at TILE_PX × TILE_PX regardless of source tile size — Phaser
    // scales the texture frame to the sprite's display size.
    const baseY = GROUND_BASELINE_Y; // bottom of surface row
    const groundDepth = 500; // in front of bg layers, behind player

    const sheetKey = `tileset`;
    const variantOfCol = (x: number) => x % 3; // visual variation

    for (let x = 0; x < heights.length; x++) {
      const h = heights[x];
      const slope = slopeAt(heights, x);
      const isLeftEdge = x === 0 || heights[x - 1] < h - 0; // simplistic: treat as edge if neighbour shorter
      const isRightEdge = x === heights.length - 1 || heights[x + 1] < h - 0;
      // We render `h` tiles up from the baseline (depth=0 at the top, depth=h-1 at the bottom).
      for (let depth = 0; depth < h; depth++) {
        const role = pickRole(
          slope,
          depth,
          // Side edges only meaningful below the surface (depth>0).
          depth > 0 && (x === 0 || heights[x - 1] < h),
          depth > 0 && (x === heights.length - 1 || heights[x + 1] < h),
        );
        const variant = variantOfCol(x + depth);
        const frameKey = `${role}_v${variant}`;
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
    // Walk runs and drop one obstacle per run, biased to its centre.
    for (let r = 0; r < runs.length; r++) {
      const run = runs[r];
      // Skip first/last column of run to avoid abutting slopes.
      if (run.len < 3) continue;
      const col = run.start + Math.floor(run.len / 2);
      const cell = cells[(r * 7) % cells.length]; // pseudo-distribute across props
      const sheetKey = `obstacles_${cell.sheetIdx}`;
      const frameKey = `prop_${cell.cellIdx}`;
      const h = heights[col];
      // Surface Y at this column: baseline minus h tiles plus tile/2 (top of top tile)
      const surfaceY = GROUND_BASELINE_Y - h * TILE_PX;
      // Display height: scale prop to ~1.5 tiles tall.
      const targetH = TILE_PX * 1.4;
      const aspect = cell.w / cell.h;
      const targetW = targetH * aspect;
      const x = col * TILE_PX + TILE_PX / 2;
      const y = surfaceY; // bottom of obstacle == top of ground
      const img = this.add.image(x, y, sheetKey, frameKey);
      img.setOrigin(0.5, 1.0); // bottom-center anchor
      img.setDisplaySize(targetW, targetH);
      img.setDepth(700);
      placed++;
    }
    this.probes.obstacleCount = placed;
  }

  // ---------- Mob spawning ----------

  private spawnMobs(heights: number[], mobIdleKeys: string[]) {
    if (mobIdleKeys.length === 0) return;
    const runs = flatRuns(heights, 2);
    let spawned = 0;
    // Deterministic: stride mob spawns evenly across flat runs, modulo mobs.
    // Skip every other run to keep the world breathable.
    let mobIdx = 0;
    for (let r = 0; r < runs.length; r += 2) {
      const run = runs[r];
      const col = run.start + 1; // one column in from the left edge
      const key = mobIdleKeys[mobIdx % mobIdleKeys.length];
      const h = heights[col];
      const surfaceY = GROUND_BASELINE_Y - h * TILE_PX;
      const sprite = this.add.sprite(col * TILE_PX + TILE_PX / 2, surfaceY, key, 0);
      sprite.setOrigin(0.5, 1.0); // bottom-center on the surface
      // Scale to ~2 tiles tall.
      const targetH = TILE_PX * 1.8;
      const tex = this.textures.get(key);
      const frame0 = tex.get(0);
      const aspect = frame0.width / Math.max(1, frame0.height);
      sprite.setDisplaySize(targetH * aspect, targetH);
      sprite.setDepth(800);
      sprite.play(key);
      mobIdx++;
      spawned++;
    }
    this.probes.mobCount = spawned;
  }

  // ---------- Player spawn ----------

  private spawnPlayer(heights: number[]) {
    // Pick the leftmost flat run as the start column.
    const runs = flatRuns(heights, 3);
    const startCol = runs.length > 0 ? runs[0].start + 1 : 4;
    this.probes.playerColumn = startCol;
    const h = heights[startCol];
    const surfaceY = GROUND_BASELINE_Y - h * TILE_PX;
    const x = startCol * TILE_PX + TILE_PX / 2;

    const useStrip = this.textures.exists(`character_idle`);
    const key = useStrip ? `character_idle` : `character_concept`;
    const sprite = this.add.sprite(x, surfaceY, key, useStrip ? 0 : undefined);
    sprite.setOrigin(0.5, 1.0); // bottom-center; feet on the ground band
    const targetH = TILE_PX * 2.2;
    const tex = this.textures.get(key);
    const frame0 = useStrip ? tex.get(0) : tex.getSourceImage(0);
    const w = (frame0 as { width: number }).width;
    const hpx = (frame0 as { height: number }).height;
    const aspect = w / Math.max(1, hpx);
    sprite.setDisplaySize(targetH * aspect, targetH);
    sprite.setDepth(900);
    if (useStrip && this.anims.exists(`character_idle`)) {
      sprite.play(`character_idle`);
    }

    // Centre the camera on the player at start so the play view shows ground + sky.
    this.cameras.main.scrollX = Math.max(0, x - VIEW_W / 2);
  }

  private recordErr(e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    this.probes.consoleErrors.push(msg);
    console.error("[scene]", msg);
  }
}

export function bootGame(parent: HTMLElement, tag: string): Phaser.Game {
  return new Phaser.Game({
    type: Phaser.AUTO,
    width: VIEW_W,
    height: VIEW_H,
    parent,
    backgroundColor: "#000",
    scene: [new StageScene({ tag })],
    scale: { mode: Phaser.Scale.FIT, autoCenter: Phaser.Scale.CENTER_BOTH },
  });
}

// Helper: surface SlopeKind for callers (re-export the type only used here for tests).
export type { SlopeKind };
