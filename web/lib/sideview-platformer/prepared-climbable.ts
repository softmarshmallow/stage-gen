import type { PreparedMap } from "@/lib/manifest/prepared-manifest";

/**
 * One addressable frame inside a map's climbable atlas.
 *
 * The atlas is a single texture holding every declared variant. A consumer must address a
 * variant as its own frame rather than masking the shared texture: a mask leaves the sprite's
 * origin and display size bound to the full atlas, so the artwork lands at the wrong size and
 * the wrong offset. Deriving frames here keeps that decision in one tested place instead of
 * inside the scene's draw call.
 */
export type ClimbableAtlasFrame = Readonly<{
  variantId: string;
  frameKey: string;
  x: number;
  y: number;
  width: number;
  height: number;
}>;

/** Stable per-variant frame name inside the map's atlas texture. */
export function climbableFrameKey(variantId: string): string {
  return `climbable:${variantId}`;
}

/**
 * Derive one frame per declared variant from the producer-measured cell rectangles.
 *
 * Returns an empty list when the map declares no climbable, so a caller can register
 * unconditionally.
 */
export function climbableAtlasFrames(
  map: Pick<PreparedMap, "climbable">,
): readonly ClimbableAtlasFrame[] {
  const climbable = map.climbable;
  if (!climbable) return Object.freeze([]);
  return Object.freeze(
    climbable.variants.map((variant) => {
      const cell = variant.cell;
      if (cell.width <= 0 || cell.height <= 0) {
        throw new Error(
          `climbable variant ${variant.variant_id} has an empty atlas cell`,
        );
      }
      return Object.freeze({
        variantId: variant.variant_id,
        frameKey: climbableFrameKey(variant.variant_id),
        x: cell.x,
        y: cell.y,
        width: cell.width,
        height: cell.height,
      });
    }),
  );
}

/**
 * On-screen width for a variant drawn at `visualHeight`, preserving its own artwork aspect.
 *
 * Every zone spans the same visual height, so width is what distinguishes a rope from a ladder.
 * A shared constant paints a 109-pixel strand at a 334-pixel ladder's width.
 */
export function climbableVisualWidth(
  cell: Readonly<{ width: number; height: number }>,
  visualHeight: number,
): number {
  if (cell.width <= 0 || cell.height <= 0 || visualHeight <= 0) {
    throw new Error("climbable visual width requires positive cell and height");
  }
  return Math.max(1, Math.round((visualHeight * cell.width) / cell.height));
}
