// Draw-scale reconciliation for an actor's animation strips.
//
// A player's states arrive as several separately generated sheets with unrelated cell geometry -
// 600x688 for each master state, 600x800 for attack, 64x128 for the ladder climb. Every one is
// its own provider call, so nothing in the pixels ties their draw scale together. Measured on a
// real run, the same character's head spans 223px idle, 220px walking, 161px crawling, 152px
// attacking and 47px climbing, and the artwork really is drawn at those different sizes.
//
// Two deterministic attempts at reconstructing scale from the sheets alone both failed, for the
// same reason: silhouette height conflates pose with draw scale. A crawling character is shorter
// because of the pose; a climbing one is shorter because the artwork is smaller, and a height
// cannot tell those apart. The second attempt - "all four frames the same height means a held
// pose, so trust its height" - held on one run's climb loop (124px on every frame) and broke on
// the next (103, 109, 117, 109), because a climb cycle is supposed to move vertically.
//
// So the reference is measured once per sheet by a vision model in the recipe and published
// beside the artifact, and the runtime matches heads. A head is a fact about the character
// rather than about the pose: crawling, lunging, and climbing heads are the same size.

/** An anatomical reference measured for one source sheet, in that sheet's source pixels. */
export type ScaleReference = Readonly<{
  /** "head" for a subject with a distinguishable head, "body" for an undivided one. */
  part: "head" | "body";
  /** Largest dimension of the reference, in source pixels of that sheet's cell. */
  extentPixels: number;
  confident: boolean;
}>;

/** Scale that maps a standing reference frame onto the target sprite height. */
export function masterSheetScale(
  targetSpriteHeight: number,
  standingFrameHeight: number,
): number {
  return targetSpriteHeight / Math.max(1, standingFrameHeight);
}

/**
 * Scale that renders `sheet`'s subject at the same apparent size as the reference sheet's.
 *
 * Both extents are in their own sheet's source pixels, and scale converts source pixels to
 * screen pixels, so equating `extent * scale` is what makes two sheets agree on screen -
 * independent of cell geometry, of trimming, and of the pose in the frame.
 *
 * Returns null when either measurement is unusable, so the caller falls back rather than
 * resizing a character off a bad number. An unconfident reading is still used: measured against
 * the alternative it is dramatically closer, and the climb sheet - the one most often read
 * unconfidently, being a small rear view - is the sheet the fallback serves worst.
 */
export function headMatchedScale(
  reference: Readonly<{ extentPixels: number; scale: number }>,
  sheet: ScaleReference | null,
): number | null {
  if (!sheet) return null;
  if (!Number.isFinite(sheet.extentPixels) || sheet.extentPixels <= 0) return null;
  if (!Number.isFinite(reference.extentPixels) || reference.extentPixels <= 0) return null;
  if (!Number.isFinite(reference.scale) || reference.scale <= 0) return null;
  return (reference.extentPixels * reference.scale) / sheet.extentPixels;
}

/** Parse a published scale reference, or null when the run predates the measurement. */
export function parseScaleReference(value: unknown): ScaleReference | null {
  if (typeof value !== "object" || value === null) return null;
  const record = value as Record<string, unknown>;
  const extent = record["extent_pixels"];
  const part = record["part"];
  if (typeof extent !== "number" || !Number.isFinite(extent) || extent <= 0) return null;
  if (part !== "head" && part !== "body") return null;
  return Object.freeze({
    part,
    extentPixels: extent,
    confident: record["confident"] === true,
  });
}
