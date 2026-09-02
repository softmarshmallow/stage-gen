// The runner's world drawing: unbounded parallax bands and the streamed
// ground strip.
//
// Bands are TileSprites because the track is endless: each authored layer is
// one admitted horizontal repeat, and the band scrolls by `scrollX * parallax`
// forever without ever running out of painting. The ground is different — it
// is the streamed occupancy made visible. Atlas tracks draw cell by cell from
// the locked 47-mask atlas; structural tracks draw one full canonical raster
// per streamed segment instance. Both are presentation-only mirrors of the
// same occupancy that physics reads.
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
import type { GameSystem } from "@/lib/game-systems/systems";
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
  sourceFrameHeight = layer.height,
): LayerBandPlacement {
  if (viewHeight <= 0 || layer.height <= 0 || sourceFrameHeight <= 0) {
    throw new Error("layer placement requires positive heights");
  }
  // Transparent bands are vertically trimmed but keep the same authored
  // 1536-wide frame as the opaque cover. When that cover is available its
  // height remains the scale datum, so a low foreground strip stays a strip
  // instead of being inflated to an entire screen.
  const scale = viewHeight / sourceFrameHeight;
  const renderedHeight = layer.height * scale;
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

/**
 * Recover the common painted-frame height from the opaque cover.
 *
 * Repeat admission may widen each layer by a different generated bridge, so
 * final repeat width is not evidence of a different authored frame. Every
 * layer in one runner track is painted against the same full-height canvas;
 * the opaque canvas-cover layer preserves that scale datum after transparent
 * bands are vertically trimmed.
 */
export function runnerLayerFrameHeight(
  layer: Pick<RunnerLayer, "width" | "height" | "alphaMode" | "verticalAnchor">,
  layers: readonly Pick<
    RunnerLayer,
    "width" | "height" | "alphaMode" | "verticalAnchor"
  >[],
): number {
  if (layer.alphaMode === "opaque" || layer.verticalAnchor === "canvas_cover") {
    return layer.height;
  }
  const cover = layers.find(
    (candidate) =>
      candidate.alphaMode === "opaque" &&
      candidate.verticalAnchor === "canvas_cover",
  );
  return cover?.height ?? layer.height;
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

/**
 * Atlas tile identity includes the selected frame, not only its world cell.
 * Boundary masks can change when the stream grows or a new seed replaces the
 * chunks at the same coordinates; the old image must then be retired.
 */
export function atlasGroundTileKey(column: number, row: number, frame: string): string {
  return `${column}:${row}:${frame}`;
}

export type RunnerGroundTextures =
  | Readonly<{
      mode: "terrain-atlas-3x3-minimal-v1";
      key: string;
    }>
  | Readonly<{
      mode: "runner-structural-ground-v1";
      keys: ReadonlyMap<string, string>;
    }>;

export interface StructuralGroundPlacement {
  readonly leftX: number;
  readonly topY: number;
  readonly width: number;
  readonly height: number;
}

export function structuralGroundSourceSize(
  columns: number,
  rows: number,
  cellPx: number,
): Readonly<{ width: number; height: number }> {
  if (
    !Number.isSafeInteger(columns) ||
    columns <= 0 ||
    !Number.isSafeInteger(rows) ||
    rows <= 0 ||
    !Number.isSafeInteger(cellPx) ||
    cellPx <= 0
  ) {
    throw new Error("structural ground source size requires a valid grid and cell size");
  }
  return Object.freeze({ width: columns * cellPx, height: rows * cellPx });
}

/** Full-grid segment raster placement in the same row/column projection as occupancy. */
export function structuralGroundPlacement(
  startColumn: number,
  columns: number,
  rows: number,
  tilePx: number,
  viewHeight = RUNNER_VIEW_HEIGHT,
): StructuralGroundPlacement {
  if (
    !Number.isSafeInteger(startColumn) ||
    !Number.isSafeInteger(columns) ||
    columns <= 0 ||
    !Number.isSafeInteger(rows) ||
    rows <= 0 ||
    !Number.isSafeInteger(tilePx) ||
    tilePx <= 0 ||
    !Number.isFinite(viewHeight) ||
    viewHeight <= 0
  ) {
    throw new Error("structural ground placement requires a valid grid and tile size");
  }
  return Object.freeze({
    leftX: startColumn * tilePx,
    topY: viewHeight - rows * tilePx,
    width: columns * tilePx,
    height: rows * tilePx,
  });
}

/** Build the parallax bands and the streaming ground strip on a live scene. */
export function buildParallaxStage(
  scene: Phaser.Scene,
  bands: readonly RunnerBandTexture[],
  groundTextures: RunnerGroundTextures,
  tilePx: number,
  groundLine: number,
): ParallaxStageView {
  const built = bands.map(({ layer, key }) => {
    const sourceFrameHeight = runnerLayerFrameHeight(
      layer,
      bands.map((entry) => entry.layer),
    );
    const placement = runnerLayerPlacement(
      layer,
      RUNNER_VIEW_HEIGHT,
      groundLine,
      sourceFrameHeight,
    );
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
    // The seed is part of the signature: a restart replays the same world
    // columns with different chunks, and stale tiles must not survive it.
    const signature = `${world.run.seed}:${world.segments.chunks[0]?.startColumn ?? 0}:${world.segments.nextColumn}`;
    if (signature === windowSignature) return;
    windowSignature = signature;
    const wanted = new Map<
      string,
      | { mode: "atlas"; column: number; row: number; frame: string }
      | {
          mode: "structural";
          segmentId: string;
          startColumn: number;
          columns: number;
        }
    >();
    if (groundTextures.mode === "terrain-atlas-3x3-minimal-v1") {
      const { startColumn, grid } = windowOccupancyGrid(world.segments);
      if (grid.length > 0) {
        for (const cell of terrainAtlasBoundaryOverscanPlan(grid)) {
          const column = startColumn + cell.mapColumn;
          wanted.set(atlasGroundTileKey(column, cell.mapRow, cell.frame), {
            mode: "atlas",
            column,
            row: cell.mapRow,
            frame: cell.frame,
          });
        }
      }
    } else {
      for (const chunk of world.segments.chunks) {
        wanted.set(`${chunk.startColumn}:${chunk.segmentId}`, {
          mode: "structural",
          segmentId: chunk.segmentId,
          startColumn: chunk.startColumn,
          columns: chunk.width,
        });
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
      let tile: Phaser.GameObjects.Image;
      if (cell.mode === "atlas") {
        if (groundTextures.mode !== "terrain-atlas-3x3-minimal-v1") {
          throw new Error("atlas draw plan requires an atlas texture");
        }
        tile = scene.add
          .image(
            cell.column * tilePx,
            rowToScreenY(cell.row, world.config) - capInset,
            groundTextures.key,
            cell.frame,
          )
          .setOrigin(0, 0)
          .setDisplaySize(tilePx, tilePx);
      } else {
        if (groundTextures.mode !== "runner-structural-ground-v1") {
          throw new Error("structural draw plan requires structural textures");
        }
        const textureKey = groundTextures.keys.get(cell.segmentId);
        if (!textureKey) {
          throw new Error(`structural ground has no texture for ${cell.segmentId}`);
        }
        const placement = structuralGroundPlacement(
          cell.startColumn,
          cell.columns,
          world.config.rows,
          tilePx,
        );
        tile = scene.add
          .image(placement.leftX, placement.topY, textureKey)
          .setOrigin(0, 0)
          .setDisplaySize(placement.width, placement.height);
      }
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
