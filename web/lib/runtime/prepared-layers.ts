// Consumer-side resolution of producer-measured layer placement.
//
// Nothing here inspects a raster. The producer measured the layer's reference frames and resolved
// the offset; this module only turns those facts plus the viewport into a transform, so the local
// review composite and the browser agree by construction rather than by coincidence.

import type { PreparedLayerPlacement, PreparedMap } from "./prepared-manifest";

/**
 * Which space a layer's `topY` is measured in.
 *
 * `screen` layers are viewport furniture - a sky plate, a horizon band, a near frame - and hold
 * still while the world moves past them. A `world` layer is registered to the terrain itself, so
 * the camera has to carry it.
 *
 * The two coincide exactly while the camera rests at the bottom of the world, which is why one
 * anchor vocabulary could stand for both until now.
 */
export type PreparedLayerSpace = "screen" | "world";

export type PreparedLayerLayout = Readonly<{
  /** Uniform scale from painted-frame pixels to screen pixels. */
  scale: number;
  /** Y of the trimmed raster's top edge, measured in `space`. */
  topY: number;
  /** Space `topY` belongs to. A world layer follows camera scroll; a screen layer does not. */
  space: PreparedLayerSpace;
  /** Texture height in source pixels, so the tile sprite never repeats vertically. */
  sourceHeight: number;
  renderedHeight: number;
}>;

export type PreparedLayerContext = Readonly<{
  viewportHeight: number;
  walkSurfaceY: number;
}>;

/**
 * World y of the floor every map bottoms out on.
 *
 * `floor_to_screen_bottom` means the deepest authored occupancy row bottoms out at the viewport
 * edge. That is what makes a gap below the world impossible rather than merely unlikely, and it
 * replaces the hard-coded baseline the scene used to carry.
 *
 * The value equals the viewport height because the camera rests at the bottom of the world, not
 * because the floor is a screen feature: `projectPreparedTerrainWorld` takes this same number as
 * its world datum.
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
 * World y of the main ground plane, the datum for `walk_surface` anchored layers.
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
 *
 * The anchor also decides which space the result belongs to. Every `screen_*` datum and the cover
 * plate are viewport features; `walk_surface` is the terrain the player stands on, so it alone
 * resolves against a world coordinate and alone has to move when the camera does.
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
  if (anchor === "canvas_cover") {
    // A cover plate is a full-bleed background. There is nothing to slide, so an offset here is
    // meaningless and the map contract already rejects one.
    topY = 0;
  } else if (anchor === "screen_center") {
    // The most general registration: the trimmed raster's own midline meets the viewport midline,
    // so neither edge is privileged and a band shorter than the screen is free to sit anywhere.
    // This only reads as "centered" because the raster is already cropped to its alpha box.
    topY =
      viewportHeight / 2 - renderedHeight / 2 + placement.vertical_offset * renderedHeight;
  } else if (anchor === "screen_top") {
    // Top-registered layers hang from the viewport ceiling. A positive offset slides the layer
    // down by that fraction of its rendered height, which is the same sign convention the
    // bottom-registered branch uses, so one number reads the same way on every layer.
    topY = placement.vertical_offset * renderedHeight;
  } else {
    const datum = anchor === "screen_bottom" ? viewportHeight : walkSurfaceY;
    topY = datum - (1 - placement.vertical_offset) * renderedHeight;
  }
  return Object.freeze({
    scale,
    topY,
    space: anchor === "walk_surface" ? "world" : "screen",
    sourceHeight: placement.trimmed_height,
    renderedHeight,
  });
}
