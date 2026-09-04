// Consumer-side resolution of producer-measured layer placement.
//
// Nothing here inspects a raster. The producer measured the layer's reference frames and resolved
// the offset; this module only turns those facts plus the viewport into a transform, so the local
// review composite and the browser agree by construction rather than by coincidence.

import type { PreparedLayerPlacement, PreparedMap } from "@/lib/manifest/prepared-manifest";
import {
  layerLayout,
  parseParallaxBlock,
  type LayerLayout,
  type LayerSpace,
  type ParallaxBlockView,
} from "@/lib/families/sideview/parallax";
import { PREPARED_RUNTIME_BLOCKS } from "@/lib/manifest/prepared-manifest";
import type { BlockTable } from "@/lib/manifest/blocks";

/**
 * The block this genre authors its bands in.
 *
 * `maps`, and not a layer block of its own: a platformer band belongs to one
 * map, and the `walk_surface_row` a world-registered band resolves against is
 * in the same map's ground. Layers and their datum are one authored fact here,
 * so they are one block, and the parallax family gates it by name.
 */
export const PLATFORMER_PARALLAX_BLOCK = Object.freeze({
  block: "maps",
  version: PREPARED_RUNTIME_BLOCKS.maps,
});

/** Gate the platformer's parallax block. Refuses by naming `maps`. */
export function parsePlatformerParallaxBlock(blocks: BlockTable): ParallaxBlockView {
  return parseParallaxBlock(blocks, PLATFORMER_PARALLAX_BLOCK);
}

/**
 * Which space a layer's `topY` is measured in.
 *
 * The family's own vocabulary, aliased: this module was where the fact was
 * discovered, and promoting it is what made the runner's placement — which had
 * no notion of space at all — the lesser copy rather than a second opinion.
 */
export type PreparedLayerSpace = LayerSpace;

export type PreparedLayerLayout = LayerLayout;

export type PreparedLayerContext = Readonly<{
  viewportHeight: number;
  walkSurfaceY: number;
  /** The layer's declared parallax, which is also its vertical scroll factor. */
  parallax: number;
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
 * The arithmetic and the five anchors are the family's now; this is the genre's
 * adapter onto its own authored field names. Nothing about the resolution moved
 * — the promotion was of this file's contract, not away from it.
 */
export function preparedLayerLayout(
  placement: PreparedLayerPlacement,
  context: PreparedLayerContext,
): PreparedLayerLayout {
  return layerLayout(
    {
      verticalAnchor: placement.vertical_anchor,
      verticalOffset: placement.vertical_offset,
      sourceHeight: placement.source_height,
      trimmedHeight: placement.trimmed_height,
    },
    context,
  );
}
