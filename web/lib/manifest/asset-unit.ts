// The one projection from authored magnitude onto screen pixels.
//
// Nothing an image model returns carries a size: a generated subject is normalized to fill its
// own canvas, so its pixels encode aspect ratio and nothing else about how large the thing is.
// Magnitude is therefore authored as a multiple of the canonical player height, and the producer
// measures how many source pixels each subject's artwork actually spent on one of those units.
//
// A consumer holds exactly one scale constant - the tile - and derives everything else. No
// per-class height constant exists here: a boss is large because it is authored large, not
// because the runtime multiplies a shared constant by a rank-specific fudge factor.

/** Which painted dimension a declared magnitude describes. */
export type SubjectExtentAxis = "height" | "width";

/**
 * How many source pixels one subject's artwork spends on one player height.
 *
 * `extentAxis` names the dimension the producer measured, because it is not the same for every
 * family. A character, a creature, a prop, and a dropped item all stand still and declare a
 * height. A projectile is drawn lying along its own travel axis, so its declared magnitude is its
 * length and the measurement runs across rather than up. Published rather than derived from the
 * family, so a consumer never has to hold a second copy of that rule.
 */
export type SubjectCalibration = Readonly<{
  heightUnits: number;
  heightUnitsSource: string;
  sourcePxPerUnit: number;
  measuredSha256: string;
  subjectExtentPx: number;
  extentAxis: SubjectExtentAxis;
}>;

/** The game's size vocabulary, and the single seam where it meets a render projection. */
export type ScaleVocabulary = Readonly<{
  unit: "player_height";
  playerHeightTiles: number;
  minimum: number;
  steps: readonly number[];
  ranks: Readonly<Record<string, number>>;
}>;

/**
 * The uniform draw scale for one calibrated subject.
 *
 * Uniform on both axes, always: width and height are never set independently, because a subject
 * whose proportions change with its magnitude is a different subject.
 */
export function spriteScale(
  calibration: SubjectCalibration,
  scale: ScaleVocabulary,
  tilePx: number,
): number {
  if (!Number.isFinite(tilePx) || tilePx <= 0) {
    throw new Error("tile size must be a positive finite number");
  }
  return (scale.playerHeightTiles * tilePx) / calibration.sourcePxPerUnit;
}

/**
 * The extent one calibrated subject draws at, in screen pixels, along its own measured axis.
 *
 * For every standing family that is a height, which is what the older name said. For a projectile
 * it is a length, and calling it a height would have made a dart declared half a player tall
 * several player-heights long. The axis is on the record; nothing here has to know the family.
 */
export function drawnExtentPx(
  calibration: SubjectCalibration,
  scale: ScaleVocabulary,
  tilePx: number,
): number {
  return calibration.subjectExtentPx * spriteScale(calibration, scale, tilePx);
}

/** The height one calibrated subject draws at, for the families that declare one. */
export function drawnHeightPx(
  calibration: SubjectCalibration,
  scale: ScaleVocabulary,
  tilePx: number,
): number {
  if (calibration.extentAxis !== "height") {
    throw new Error("this subject declares a length, so ask for its drawn extent instead");
  }
  return drawnExtentPx(calibration, scale, tilePx);
}
