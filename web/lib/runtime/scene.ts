// Per-tag Phaser 4 scene loader.
//
// Loads a complete `out/<tag>/` worth of assets via the
// /api/assets/<tag>/<...> route, applies the runtime image-processing
// primitives (chroma-key, alpha-bbox crop, parallax edge-fade), and
// registers all textures with the Phaser texture manager so Phase 6 scene
// composition can consume them by stable key.
//
// Phase 5 deliverable: the scene mounts, loads everything, and shows the
// opaque skybox layer + one parallax layer to prove asset loading +
// runtime processing both work end-to-end.
// Phase 6 will add ground, mobs, character, parallax composition, etc.

import Phaser from "phaser";
import {
  chromaKeyToAlpha,
  extractCellsBbox,
  fadeParallaxEdges,
  alphaAt,
  type CellRect,
} from "./image-ops";

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

// Spot-check probes — written into window.__sceneProbes for E2E verification.
export type SceneProbes = {
  tag: string;
  loadedAssetKeys: string[];
  // For each non-opaque parallax layer key, sampled in-memory alpha at the
  // leftmost column (x=0) and at x=fadePx inward, both at y=H/2.
  parallaxAlphaProbe: Record<
    string,
    { layerId: string; leftEdgeAlpha: number; inwardAlpha: number; width: number; height: number }
  >;
  // For one chroma-keyed sprite, sample alpha at a previously-magenta pixel.
  spriteChromaProbe: Record<
    string,
    { spriteKey: string; sampledAlpha: number; sampledAt: { x: number; y: number } }
  >;
  // Per-cell alpha-bbox crops for obstacle/item sheets. Number of cells = rows*cols.
  cellExtractProbe: Record<string, CellRect[]>;
  consoleErrors: string[];
};

declare global {
  interface Window {
    __sceneProbes?: SceneProbes;
  }
}

// Asset URL helper — every fetch goes through the dev API route.
function assetUrl(tag: string, file: string): string {
  return `/api/assets/${encodeURIComponent(tag)}/${file
    .split("/")
    .map(encodeURIComponent)
    .join("/")}`;
}

async function fetchImage(url: string): Promise<HTMLImageElement> {
  return await new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = (e) => reject(new Error(`image load failed: ${url} (${e})`));
    img.src = url;
  });
}

async function fetchJson<T>(url: string): Promise<T> {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`${url} → HTTP ${r.status}`);
  return (await r.json()) as T;
}

// Replace any existing texture under key with a fresh canvas-backed one.
function registerCanvas(textures: Phaser.Textures.TextureManager, key: string, canvas: HTMLCanvasElement) {
  if (textures.exists(key)) textures.remove(key);
  textures.addCanvas(key, canvas);
}

export type SceneInit = { tag: string };

export class StageScene extends Phaser.Scene {
  private tag: string;
  private probes!: SceneProbes;

  constructor(init: SceneInit) {
    super({ key: "StageScene" });
    this.tag = init.tag;
  }

  // Phaser calls preload() before create(). We do all our loading in create()
  // because we control fetching directly (need image-ops mutation before
  // registering as a texture); preload's loader queue isn't a fit.
  create() {
    this.probes = {
      tag: this.tag,
      loadedAssetKeys: [],
      parallaxAlphaProbe: {},
      spriteChromaProbe: {},
      cellExtractProbe: {},
      consoleErrors: [],
    };
    if (typeof window !== "undefined") window.__sceneProbes = this.probes;

    // Kick off async loading without blocking create() return.
    this.loadAll().catch((err) => {
      console.error("[scene] loadAll failed:", err);
      this.probes.consoleErrors.push(String(err?.message ?? err));
    });
  }

  private async loadAll() {
    const tag = this.tag;
    const specUrl = assetUrl(tag, `world_spec_${tag}.json`);
    const spec = await fetchJson<WorldSpec>(specUrl);
    this.probes.loadedAssetKeys.push(`spec:${spec.world.name}`);

    // ---- Concept image ----
    await this.loadChromaKeyedSprite(`concept_${tag}.png`, `concept`).catch((e) =>
      this.recordErr(e),
    );

    // ---- Character concept (chroma-keyed) — used for the spriteChromaProbe ----
    const charConceptKey = "character_concept";
    const charConceptCanvas = await this.loadChromaKeyedSprite(
      `character_concept_${tag}.png`,
      charConceptKey,
    ).catch((e) => {
      this.recordErr(e);
      return null;
    });
    if (charConceptCanvas) {
      // Sample top-left corner — it's almost always magenta on these sheets.
      const sampleAt = { x: 1, y: 1 };
      const a = alphaAt(charConceptCanvas, sampleAt.x, sampleAt.y);
      this.probes.spriteChromaProbe[charConceptKey] = {
        spriteKey: charConceptKey,
        sampledAlpha: a,
        sampledAt,
      };
    }

    // ---- Character motion strips (5 states) ----
    for (const state of ["idle", "walk", "run", "jump", "crawl"]) {
      const file = `character_${tag}-fromcombined_${state}.png`;
      await this.loadChromaKeyedSprite(file, `character_${state}`).catch((e) =>
        this.recordErr(e),
      );
    }
    // Character attack strip
    await this.loadChromaKeyedSprite(`character_${tag}_attack.png`, `character_attack`).catch(
      (e) => this.recordErr(e),
    );

    // ---- Parallax layers ----
    let firstNonOpaqueShown = false;
    let opaqueShown = false;
    for (const layer of spec.layers) {
      const file = `layer_${tag}_${layer.id}.png`;
      const url = assetUrl(tag, file);
      let img: HTMLImageElement;
      try {
        img = await fetchImage(url);
      } catch (e) {
        this.recordErr(e);
        continue;
      }
      const key = `layer_${layer.id}`;
      let canvas: HTMLCanvasElement;
      if (layer.opaque) {
        // Opaque skybox: NO chroma-key, NO edge-fade.
        // Just register raw pixels in a canvas-backed texture for consistency.
        const c = document.createElement("canvas");
        c.width = img.naturalWidth;
        c.height = img.naturalHeight;
        c.getContext("2d")!.drawImage(img, 0, 0);
        canvas = c;
      } else {
        const keyed = chromaKeyToAlpha(img);
        canvas = fadeParallaxEdges(keyed, 64);
        // Probe — sample left-edge alpha + inward (x=64) alpha at vertical mid.
        const yMid = Math.floor(canvas.height / 2);
        const leftEdgeAlpha = alphaAt(canvas, 0, yMid);
        const inwardX = Math.min(64, canvas.width - 1);
        const inwardAlpha = alphaAt(canvas, inwardX, yMid);
        this.probes.parallaxAlphaProbe[key] = {
          layerId: layer.id,
          leftEdgeAlpha,
          inwardAlpha,
          width: canvas.width,
          height: canvas.height,
        };
      }
      registerCanvas(this.textures, key, canvas);
      this.probes.loadedAssetKeys.push(key);

      // Phase 5 mounting: just show the opaque skybox + the first non-opaque layer.
      if (layer.opaque && !opaqueShown) {
        const sky = this.add.image(0, 0, key).setOrigin(0, 0);
        // Scale to fit viewport.
        sky.setDisplaySize(VIEW_W, VIEW_H);
        sky.setDepth(0);
        opaqueShown = true;
      } else if (!layer.opaque && !firstNonOpaqueShown) {
        const lyr = this.add.image(0, 0, key).setOrigin(0, 0);
        lyr.setDisplaySize(VIEW_W, VIEW_H);
        lyr.setDepth(layer.z_index + 1);
        firstNonOpaqueShown = true;
      }
    }

    // ---- Tileset ----
    await this.loadChromaKeyedSprite(`tileset_${tag}.png`, `tileset`).catch((e) =>
      this.recordErr(e),
    );

    // ---- Mobs (idle + hurt strips) ----
    for (let i = 0; i < spec.mobs.length; i++) {
      await this.loadChromaKeyedSprite(`mob_${tag}_${i}_idle.png`, `mob_${i}_idle`).catch(
        (e) => this.recordErr(e),
      );
      await this.loadChromaKeyedSprite(`mob_${tag}_${i}_hurt.png`, `mob_${i}_hurt`).catch(
        (e) => this.recordErr(e),
      );
      // Concept turnaround for the body
      await this.loadChromaKeyedSprite(
        `mob_concept_${tag}_${i}.png`,
        `mob_concept_${i}`,
      ).catch((e) => this.recordErr(e));
    }

    // ---- Obstacle sheets (4×2) → per-cell bbox extraction ----
    for (let i = 0; i < spec.obstacles.length; i++) {
      const file = `obstacles_${tag}_${i}.png`;
      const sheetKey = `obstacles_${i}`;
      const keyed = await this.loadChromaKeyedSprite(file, sheetKey).catch((e) => {
        this.recordErr(e);
        return null;
      });
      if (keyed) {
        const { cells } = extractCellsBbox(keyed, 2, 4);
        this.probes.cellExtractProbe[sheetKey] = cells;
        // Register one sub-texture per non-empty prop cell.
        cells.forEach((cell, idx) => {
          if (cell.w > 1 || cell.h > 1) {
            this.textures.get(sheetKey).add(`prop_${idx}`, 0, cell.x, cell.y, cell.w, cell.h);
          }
        });
      }
    }

    // ---- Items sheet (4×2) → per-cell bbox extraction ----
    {
      const file = `items_${tag}.png`;
      const sheetKey = `items`;
      const keyed = await this.loadChromaKeyedSprite(file, sheetKey).catch((e) => {
        this.recordErr(e);
        return null;
      });
      if (keyed) {
        const { cells } = extractCellsBbox(keyed, 2, 4);
        this.probes.cellExtractProbe[sheetKey] = cells;
        cells.forEach((cell, idx) => {
          if (cell.w > 1 || cell.h > 1) {
            this.textures.get(sheetKey).add(`item_${idx}`, 0, cell.x, cell.y, cell.w, cell.h);
          }
        });
      }
    }

    // ---- Inventory + portal (chroma-keyed; no per-cell extract today) ----
    await this.loadChromaKeyedSprite(`inventory_${tag}.png`, `inventory`).catch((e) =>
      this.recordErr(e),
    );
    await this.loadChromaKeyedSprite(`portal_${tag}.png`, `portal`).catch((e) =>
      this.recordErr(e),
    );

    // Mark ready for headless probes.
    if (typeof window !== "undefined") {
      (window as unknown as { __sceneReady?: boolean }).__sceneReady = true;
    }
  }

  // Centralised "load + chroma-key + register" helper. Returns the keyed
  // canvas so callers may further process or sample it.
  private async loadChromaKeyedSprite(
    filename: string,
    key: string,
  ): Promise<HTMLCanvasElement> {
    const url = assetUrl(this.tag, filename);
    const img = await fetchImage(url);
    const keyed = chromaKeyToAlpha(img);
    registerCanvas(this.textures, key, keyed);
    this.probes.loadedAssetKeys.push(key);
    return keyed;
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
