// Consumer-side resolution of producer-measured layer placement.
//
// Nothing here inspects a raster. The producer measured the layer's reference frames and resolved
// the offset; this module only turns those facts plus the viewport into a transform, so the local
// review composite and the browser agree by construction rather than by coincidence.

import type { PreparedLayerPlacement, PreparedMap } from "./prepared-manifest";

export type PreparedLayerLayout = Readonly<{
  /** Uniform scale from painted-frame pixels to screen pixels. */
  scale: number;
  /** Screen y of the trimmed raster's top edge. */
  topY: number;
  /** Texture height in source pixels, so the tile sprite never repeats vertically. */
  sourceHeight: number;
  renderedHeight: number;
}>;

export type PreparedLayerContext = Readonly<{
  viewportHeight: number;
  walkSurfaceY: number;
}>;

/**
 * Screen y of the world floor.
 *
 * `floor_to_screen_bottom` means the deepest authored occupancy row bottoms out at the viewport
 * edge. That is what makes a gap below the world impossible rather than merely unlikely, and it
 * replaces the hard-coded baseline the scene used to carry.
 */
export function preparedGroundBaselineY(
  map: Pick<PreparedMap, "ground">,
  viewportHeight: number,
): number {
  if (!Number.isFinite(viewportHeight) || viewportHeight <= 0) {
    throw new Error("prepared ground baseline requires a positive viewport height");
  }
  if (map.ground.vertical_fit !== "floor_to_screen_bottom") {
    throw new Error("prepared ground vertical_fit is unsupported");
  }
  return viewportHeight;
}

/**
 * Screen y of the main ground plane, the datum for `walk_surface` anchored layers.
 *
 * This is the top edge of the authored `walk_surface_row`, so a midground layer's solid base meets
 * the terrain the player actually stands on rather than the buried floor beneath it.
 */
export function preparedWalkSurfaceY(
  map: Pick<PreparedMap, "ground">,
  tilePixels: number,
  viewportHeight: number,
): number {
  if (!Number.isSafeInteger(tilePixels) || tilePixels <= 0) {
    throw new Error("prepared walk surface requires a positive integer tile size");
  }
  const rows = map.ground.occupancy.length;
  const row = map.ground.walk_surface_row;
  if (!Number.isSafeInteger(row) || row < 0 || row >= rows) {
    throw new Error("prepared walk_surface_row must index an authored occupancy row");
  }
  return preparedGroundBaselineY(map, viewportHeight) - (rows - row) * tilePixels;
}

/**
 * Resolve one layer's transform from its declared anchor and measured raster.
 *
 * The painted frame stays the scale datum after empty rows are trimmed away, so trimming never
 * changes a layer's apparent size. Bottom-registered anchors place the layer so its measured
 * full-coverage line — not its deepest stray tip — lands on the datum; the offset the producer
 * resolved is exactly the fraction that has to sit past it.
 */
export function preparedLayerLayout(
  placement: PreparedLayerPlacement,
  context: PreparedLayerContext,
): PreparedLayerLayout {
  const { viewportHeight, walkSurfaceY } = context;
  if (!Number.isFinite(viewportHeight) || viewportHeight <= 0) {
    throw new Error("prepared layer layout requires a positive viewport height");
  }
  if (!Number.isFinite(walkSurfaceY)) {
    throw new Error("prepared layer layout requires a finite walk surface");
  }
  if (placement.source_height <= 0 || placement.trimmed_height <= 0) {
    throw new Error("prepared layer layout requires positive raster heights");
  }
  if (!Number.isFinite(placement.vertical_offset)) {
    throw new Error("prepared layer layout requires a finite vertical offset");
  }
  const scale = viewportHeight / placement.source_height;
  const renderedHeight = placement.trimmed_height * scale;
  const anchor = placement.vertical_anchor;
  let topY: number;
  if (anchor === "canvas_cover" || anchor === "screen_top") {
    topY = 0;
  } else {
    const datum = anchor === "screen_bottom" ? viewportHeight : walkSurfaceY;
    topY = datum - (1 - placement.vertical_offset) * renderedHeight;
  }
  return Object.freeze({
    scale,
    topY,
    sourceHeight: placement.trimmed_height,
    renderedHeight,
  });
}
