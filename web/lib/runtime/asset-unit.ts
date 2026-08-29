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

/** How many source pixels one subject's artwork spends on one player height. */
export type SubjectCalibration = Readonly<{
  heightUnits: number;
  heightUnitsSource: string;
  sourcePxPerUnit: number;
  measuredSha256: string;
  subjectExtentPx: number;
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

/** The height one calibrated subject draws at, in screen pixels. */
export function drawnHeightPx(
  calibration: SubjectCalibration,
  scale: ScaleVocabulary,
  tilePx: number,
): number {
  return calibration.subjectExtentPx * spriteScale(calibration, scale, tilePx);
}
