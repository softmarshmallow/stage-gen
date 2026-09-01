// The runner's world drawing: unbounded parallax bands and the streamed
// ground strip.
//
// Bands are TileSprites because the track is endless: each authored layer is
// one admitted horizontal repeat, and the band scrolls by `scrollX * parallax`
// forever without ever running out of painting. The ground is different — it
// is the streamed occupancy made visible, drawn cell by cell from the locked
// 47-mask terrain atlas, appearing with the window and vanishing behind it.
//
// Only the placement math is exported for tests; the builders take a live
// scene. Phaser enters as types alone so the module stays importable headless.

import type Phaser from "phaser";
import {
  terrainAtlasBoundaryOverscanPlan,
  terrainAtlasWalkSurfaceOffset,
} from "@/lib/sideview/terrain-atlas";
import type { RunnerLayer } from "./contract";
import { windowOccupancyGrid } from "./segments";
import type { GameSystem } from "./systems";
import { rowToScreenY, RUNNER_VIEW_HEIGHT, RUNNER_VIEW_WIDTH, type RunnerWorld } from "./world";

/** Depth rungs: background bands, ground, actors, foreground bands, HUD. */
export const RUNNER_DEPTHS = Object.freeze({
  background: 0, // + layer order
  ground: 20,
  shadow: 24,
  pickup: 26,
  hazard: 27,
  avatar: 30,
  foreground: 40, // + layer order
  hud: 100,
});

export interface LayerBandPlacement {
  /** Screen y of the band's top edge. */
  readonly topY: number;
  readonly renderedHeight: number;
  /** Uniform source-pixel to screen-pixel scale. */
  readonly scale: number;
}

/**
 * Resolve one band's vertical placement from its declared anchor.
 *
 * Every layer is painted at full frame height, so the viewport height is the
 * one scale datum; anchors then choose which edge registers where, with the
 * same sign convention the platformer uses — a positive offset slides the
 * layer down by that fraction of its rendered height. `walk_surface` is the
 * only world-registered anchor: its base meets the ground line the avatar
 * actually runs on.
 */
export function runnerLayerPlacement(
  layer: Pick<RunnerLayer, "height" | "verticalAnchor" | "verticalOffset">,
  viewHeight: number,
  groundLine: number,
): LayerBandPlacement {
  if (viewHeight <= 0 || layer.height <= 0) {
    throw new Error("layer placement requires positive heights");
  }
  const scale = viewHeight / layer.height;
  const renderedHeight = viewHeight;
  const offset = layer.verticalOffset ?? 0;
  let topY: number;
  switch (layer.verticalAnchor) {
    case "canvas_cover":
      topY = 0;
      break;
    case "screen_top":
      topY = offset * renderedHeight;
      break;
    case "screen_bottom":
      topY = viewHeight - (1 - offset) * renderedHeight;
      break;
    case "walk_surface":
      topY = groundLine - (1 - offset) * renderedHeight;
      break;
  }
  return Object.freeze({ topY, renderedHeight, scale });
}

/** Depth of one band: plane decides the shelf, authored order stacks within it. */
export function layerBandDepth(layer: Pick<RunnerLayer, "plane" | "order">): number {
  return layer.plane === "background"
    ? RUNNER_DEPTHS.background + layer.order
    : RUNNER_DEPTHS.foreground + layer.order;
}

/** Texture-space scroll for one band at a given world scroll. */
export function bandTilePositionX(scrollX: number, parallax: number, scale: number): number {
  return (scrollX * parallax) / scale;
}

/** What the world-presentation system needs from the built stage. */
export interface ParallaxStageView {
  sync(world: RunnerWorld): void;
}

/**
 * The world-presentation system: bands, ground, and whatever actor drawing
 * the boot composes into the view. It consumes this frame's camera, window,
 * avatar, and obstacle results and writes only to the screen, so it seals
 * after every simulation system.
 */
export function createParallaxSystem(view: ParallaxStageView): GameSystem<RunnerWorld> {
  return {
    id: "runner/parallax",
    contractVersion: "parallax-system-v1",
    reads: ["camera", "segments", "avatar", "obstacles"],
    writes: [],
    update(world) {
      view.sync(world);
    },
  };
}

export interface RunnerBandTexture {
  readonly layer: RunnerLayer;
  /** Texture key already registered with the scene's texture manager. */
  readonly key: string;
}

/** Build the parallax bands and the streaming ground strip on a live scene. */
export function buildParallaxStage(
  scene: Phaser.Scene,
  bands: readonly RunnerBandTexture[],
  groundTextureKey: string,
  tilePx: number,
  groundLine: number,
): ParallaxStageView {
  const built = bands.map(({ layer, key }) => {
    const placement = runnerLayerPlacement(layer, RUNNER_VIEW_HEIGHT, groundLine);
    const band = scene.add
      .tileSprite(0, placement.topY, RUNNER_VIEW_WIDTH, placement.renderedHeight, key)
      .setOrigin(0, 0)
      .setDepth(layerBandDepth(layer));
    band.setTileScale(placement.scale, placement.scale);
    return { layer, band, placement };
  });

  // Ground tiles live in one container that carries the whole strip left as
  // the world scrolls; each tile sits at its world-pixel position inside it.
  const groundContainer = scene.add.container(0, 0).setDepth(RUNNER_DEPTHS.ground);
  const tiles = new Map<string, Phaser.GameObjects.Image>();
  const capInset = terrainAtlasWalkSurfaceOffset(tilePx);
  let windowSignature = "";

  const syncGround = (world: RunnerWorld): void => {
    const signature = `${world.segments.chunks[0]?.startColumn ?? 0}:${world.segments.nextColumn}`;
    if (signature === windowSignature) return;
    windowSignature = signature;
    const { startColumn, grid } = windowOccupancyGrid(world.segments);
    const wanted = new Map<string, { column: number; row: number; frame: string }>();
    if (grid.length > 0) {
      for (const cell of terrainAtlasBoundaryOverscanPlan(grid)) {
        const column = startColumn + cell.mapColumn;
        wanted.set(`${column}:${cell.mapRow}`, { column, row: cell.mapRow, frame: cell.frame });
      }
    }
    for (const [key, tile] of tiles) {
      if (!wanted.has(key)) {
        tile.destroy();
        tiles.delete(key);
      }
    }
    for (const [key, cell] of wanted) {
      if (tiles.has(key)) continue;
      const tile = scene.add
        .image(cell.column * tilePx, rowToScreenY(cell.row, world.config) - capInset, groundTextureKey, cell.frame)
        .setOrigin(0, 0)
        .setDisplaySize(tilePx, tilePx);
      groundContainer.add(tile);
      tiles.set(key, tile);
    }
  };

  return {
    sync(world: RunnerWorld): void {
      for (const { layer, band, placement } of built) {
        band.tilePositionX = bandTilePositionX(
          world.camera.scrollX,
          layer.parallax,
          placement.scale,
        );
      }
      syncGround(world);
      groundContainer.x = -world.camera.scrollX;
    },
  };
}
