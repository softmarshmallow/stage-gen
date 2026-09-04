// Where a painted band sits, how far it travels, and which shelf it stands on.
//
// Two implementations existed and one of them was the contract: the
// platformer's `prepared-layers.ts` already resolved a producer-measured
// placement against a viewport and a ground datum, named all five anchors, and
// — alone — knew that an anchor also chooses a *space*, because a layer
// registered to the terrain has to travel with the camera and a layer
// registered to the screen must not. The runner's `runnerLayerPlacement` is the
// same arithmetic with one anchor missing and the space fact absent, which is
// what "the lesser duplicate" means. So the promotion goes one way: the
// platformer's is the family, and the runner's becomes a view over it.
//
// Nothing here inspects a raster. The producer measured the layer's reference
// frames and resolved the offset; this turns those facts plus the viewport into
// a transform, so a local review composite and a browser agree by construction
// rather than by coincidence.
//
// The depth ladder is here too, and as an *ordered vocabulary* rather than a
// table of numbers. The two genres' ladders share no value — the runner counts
// in tens from zero, the platformer in hundreds — but they are the same ladder:
// bands behind, the world, the actors on it, bands in front, readouts drawn in
// the world, screen furniture, and whatever covers all of it. A genre states
// its own rungs and the family refuses one that is out of order, which is the
// refusal that "every parallax layer inherits the shake" was the symptom of:
// the ordering was a convention across two files and nothing checked it.

/** Which datum a layer's `topY` registers against. */
export type LayerVerticalAnchor =
  | "canvas_cover"
  | "screen_center"
  | "screen_top"
  | "screen_bottom"
  | "walk_surface";

/**
 * Which space a layer's `topY` is measured in.
 *
 * `screen` layers are viewport furniture — a sky plate, a horizon band, a near
 * frame — and hold still while the world moves past them. A `world` layer is
 * registered to the terrain itself, so the camera has to carry it.
 *
 * The two coincide exactly while the camera rests at the bottom of the world,
 * which is why one anchor vocabulary could stand for both until the platformer
 * grew a camera that leaves the floor.
 */
export type LayerSpace = "screen" | "world";

/** What the producer measured about one layer's raster. */
export interface LayerPlacement {
  readonly verticalAnchor: LayerVerticalAnchor;
  /** Fraction of `trimmedHeight`, positive pushing the layer down past its datum. */
  readonly verticalOffset: number;
  /** Height of the frame the layer was painted in; the scale datum after trimming. */
  readonly sourceHeight: number;
  readonly trimmedHeight: number;
}

export interface LayerContext {
  readonly viewportHeight: number;
  /** World y of the surface a `walk_surface` layer registers its base against. */
  readonly walkSurfaceY: number;
  /** The layer's declared parallax, which is also its vertical scroll factor. */
  readonly parallax: number;
}

export interface LayerLayout {
  /** Uniform scale from painted-frame pixels to screen pixels. */
  readonly scale: number;
  /** Y of the trimmed raster's top edge, measured in `space`. */
  readonly topY: number;
  /** Space `topY` belongs to. A world layer follows camera scroll; a screen layer does not. */
  readonly space: LayerSpace;
  /**
   * How much of the camera's vertical travel this layer takes, as a scroll factor.
   *
   * Horizontal parallax is a texture offset, because a layer repeats on x and
   * can be slid inside itself forever. Vertically it cannot: a layer is exactly
   * one texture tall, so depth on this axis has to be position, and this is
   * that number. It is the layer's own parallax rather than a second
   * declaration, because parallax is already the statement of how far away the
   * layer is and distance does not change with the axis you look along. Only
   * the walk-surface datum is exempt: that layer is registered to the terrain,
   * so it travels with it exactly or it stops meeting the ground it was
   * measured against.
   */
  readonly verticalScrollFactor: number;
  /** Texture height in source pixels, so the tile sprite never repeats vertically. */
  readonly sourceHeight: number;
  readonly renderedHeight: number;
}

/**
 * Resolve one layer's transform from its declared anchor and measured raster.
 *
 * The painted frame stays the scale datum after empty rows are trimmed away, so
 * trimming never changes a layer's apparent size. Bottom-registered anchors
 * place the layer so its measured full-coverage line — not its deepest stray
 * tip — lands on the datum; the offset the producer resolved is exactly the
 * fraction that has to sit past it.
 *
 * The anchor also decides which space the result belongs to. Every `screen_*`
 * datum and the cover plate are viewport features; `walk_surface` is the
 * terrain the player stands on, so it alone resolves against a world coordinate
 * and alone has to move when the camera does.
 */
export function layerLayout(placement: LayerPlacement, context: LayerContext): LayerLayout {
  const { viewportHeight, walkSurfaceY, parallax } = context;
  if (!Number.isFinite(parallax) || parallax < 0) {
    throw new Error("prepared layer layout requires a non-negative parallax");
  }
  if (!Number.isFinite(viewportHeight) || viewportHeight <= 0) {
    throw new Error("prepared layer layout requires a positive viewport height");
  }
  if (!Number.isFinite(walkSurfaceY)) {
    throw new Error("prepared layer layout requires a finite walk surface");
  }
  if (placement.sourceHeight <= 0 || placement.trimmedHeight <= 0) {
    throw new Error("prepared layer layout requires positive raster heights");
  }
  if (!Number.isFinite(placement.verticalOffset)) {
    throw new Error("prepared layer layout requires a finite vertical offset");
  }
  const scale = viewportHeight / placement.sourceHeight;
  const renderedHeight = placement.trimmedHeight * scale;
  const anchor = placement.verticalAnchor;
  let topY: number;
  if (anchor === "canvas_cover") {
    // A cover plate is a full-bleed background. There is nothing to slide, so
    // an offset here is meaningless and the map contract already rejects one.
    topY = 0;
  } else if (anchor === "screen_center") {
    // The most general registration: the trimmed raster's own midline meets the
    // viewport midline, so neither edge is privileged and a band shorter than
    // the screen is free to sit anywhere. This only reads as "centered" because
    // the raster is already cropped to its alpha box.
    topY = viewportHeight / 2 - renderedHeight / 2 + placement.verticalOffset * renderedHeight;
  } else if (anchor === "screen_top") {
    // Top-registered layers hang from the viewport ceiling. A positive offset
    // slides the layer down by that fraction of its rendered height, which is
    // the same sign convention the bottom-registered branch uses, so one number
    // reads the same way on every layer.
    topY = placement.verticalOffset * renderedHeight;
  } else {
    const datum = anchor === "screen_bottom" ? viewportHeight : walkSurfaceY;
    topY = datum - (1 - placement.verticalOffset) * renderedHeight;
  }
  const space: LayerSpace = anchor === "walk_surface" ? "world" : "screen";
  return Object.freeze({
    scale,
    topY,
    space,
    verticalScrollFactor: space === "world" ? 1 : parallax,
    sourceHeight: placement.trimmedHeight,
    renderedHeight,
  });
}

/**
 * Texture-space scroll for one band at a given world scroll.
 *
 * The horizontal half of the same statement `verticalScrollFactor` makes: the
 * band is slid inside its own repeating texture rather than moved, so the
 * offset is divided by the scale that stretched the texture onto the screen.
 */
export function bandTilePosition(scrollX: number, parallax: number, scale: number): number {
  return (scrollX * parallax) / scale;
}

/**
 * The depth ladder, as an ordered vocabulary.
 *
 * The rungs, back to front. A genre supplies its own numbers for the rungs it
 * has; the order is the family's and is the thing that can be got wrong.
 */
export const DEPTH_LADDER = Object.freeze([
  "background",
  "world",
  "actors",
  "foreground",
  "actorHud",
  "hud",
  "overlay",
] as const);

export type DepthRung = (typeof DEPTH_LADDER)[number];

export type DepthLadder = Readonly<Partial<Record<DepthRung, number>>>;

/**
 * Refuse a ladder whose rungs are not in the vocabulary's order.
 *
 * A genre need not have every rung — the runner draws no readouts in the world,
 * so it has no `actorHud` — but the rungs it does have must climb. This is the
 * check that was a convention across two files: the shake that every parallax
 * layer inherited was undeclared *and* the ordering that made it visible was
 * unchecked, and only one of those two was a kernel problem.
 */
export function sealDepthLadder(ladder: DepthLadder): DepthLadder {
  let previousRung: DepthRung | null = null;
  let previousValue = Number.NEGATIVE_INFINITY;
  for (const rung of DEPTH_LADDER) {
    const value = ladder[rung];
    if (value === undefined) continue;
    if (!Number.isFinite(value)) {
      throw new Error(`depth rung ${rung} must be a finite number`);
    }
    if (value <= previousValue) {
      throw new Error(
        `depth ladder is out of order: ${rung} at ${value} is not above ${previousRung} at ${previousValue}`,
      );
    }
    previousRung = rung;
    previousValue = value;
  }
  return Object.freeze({ ...ladder });
}

/**
 * Depth of one band: the plane decides the shelf, authored order stacks within it.
 *
 * A band's plane is the only thing about it that is depth vocabulary; `order`
 * is the author's, and adding it to the rung is what keeps two bands on one
 * shelf in the order they were written rather than in map iteration order.
 */
export function bandDepth(
  ladder: DepthLadder,
  plane: "background" | "foreground",
  order: number,
): number {
  const rung = ladder[plane === "background" ? "background" : "foreground"];
  if (rung === undefined) {
    throw new Error(`depth ladder has no ${plane} rung for a band to stand on`);
  }
  return rung + order;
}
