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
  topFraction: number;
  bottomFraction: number;
  leftFraction: number;
  rightFraction: number;
  /** Largest dimension of the reference, in source pixels of that sheet's cell. */
  extentPixels: number;
  confident: boolean;
  evidence: string;
  frameIndex: number;
  cellWidth: number;
  cellHeight: number;
}>;

export type AspectPreservingFrameScale = Readonly<{
  scale: number;
  displayWidth: number;
  displayHeight: number;
}>;

/** Player sheets that the current producer measures and publishes on every run. */
export const REQUIRED_PLAYER_SCALE_REFERENCE_ROLES = Object.freeze([
  "character-idle",
  "character-walk",
  "character-run",
  "character-jump",
  "character-crawl",
  "character-climb",
  "character-attack",
] as const);

const REQUIRED_PLAYER_SCALE_REFERENCE_ROLE_SET = new Set<string>(
  REQUIRED_PLAYER_SCALE_REFERENCE_ROLES,
);

const SCALE_REFERENCE_KEYS = new Set([
  "part",
  "top_fraction",
  "bottom_fraction",
  "left_fraction",
  "right_fraction",
  "extent_pixels",
  "confident",
  "evidence",
  "frame_index",
  "cell_width",
  "cell_height",
]);

/** Whether one current runtime role owns a producer-published anatomical measurement. */
export function runtimeRoleOwnsScaleReference(role: string): boolean {
  return (
    REQUIRED_PLAYER_SCALE_REFERENCE_ROLE_SET.has(role) ||
    /^mob-(?:0|[1-9]\d*)-(?:idle|hurt|attack)$/.test(role) ||
    /^village-npc-(?:0|[1-9]\d*)-(?:idle|still)$/.test(role)
  );
}

function positiveFinite(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
    throw new Error(`${label} must be a positive finite number`);
  }
  return value;
}

/** Uniformly scale one decoded frame to a target height without changing its proportions. */
export function frameScaleForHeight(
  targetDisplayHeight: number,
  sourceFrameWidth: number,
  sourceFrameHeight: number,
): AspectPreservingFrameScale {
  const targetHeight = positiveFinite(targetDisplayHeight, "target display height");
  const sourceWidth = positiveFinite(sourceFrameWidth, "source frame width");
  const sourceHeight = positiveFinite(sourceFrameHeight, "source frame height");
  const scale = targetHeight / sourceHeight;
  return Object.freeze({
    scale,
    displayWidth: sourceWidth * scale,
    displayHeight: targetHeight,
  });
}

function unitFraction(value: unknown, label: string): number {
  if (
    typeof value !== "number" ||
    !Number.isFinite(value) ||
    value < 0 ||
    value > 1
  ) {
    throw new Error(`${label} must be a finite number from 0 through 1`);
  }
  return value;
}

/** Scale that maps a standing reference frame onto the target sprite height. */
export function masterSheetScale(
  targetSpriteHeight: number,
  standingFrameHeight: number,
): number {
  return (
    positiveFinite(targetSpriteHeight, "target sprite height") /
    positiveFinite(standingFrameHeight, "standing frame height")
  );
}

/**
 * Scale that renders `sheet`'s subject at the same apparent size as the reference sheet's.
 *
 * Both extents are in their own sheet's source pixels, and scale converts source pixels to
 * screen pixels, so equating `extent * scale` is what makes two sheets agree on screen -
 * independent of cell geometry, of trimming, and of the pose in the frame.
 *
 * The current manifest boundary has already rejected an unusable measurement. An unconfident
 * reading is still used: measured against the alternative it is dramatically closer, and the
 * climb sheet - the one most often read unconfidently, being a small rear view - is the sheet
 * whose raw cell scale is furthest from the player anchor.
 */
export function headMatchedScale(
  reference: Readonly<{ extentPixels: number; scale: number }>,
  sheet: ScaleReference,
): number {
  return (
    (positiveFinite(reference.extentPixels, "reference extent") *
      positiveFinite(reference.scale, "reference scale")) /
    positiveFinite(sheet.extentPixels, "sheet extent")
  );
}

/**
 * Resolve one player state's sheet scale while preserving an authored pose's
 * canonical atlas scale when the consumer explicitly requests that policy.
 */
export function playerSheetScaleForState(input: Readonly<{
  state: string;
  masterSheetScale: number;
  measuredSheetScale: number;
  preserveSourceScaleStates: readonly string[];
}>): number {
  const master = positiveFinite(input.masterSheetScale, "master sheet scale");
  const measured = positiveFinite(input.measuredSheetScale, "measured sheet scale");
  return input.preserveSourceScaleStates.includes(input.state)
    ? master
    : measured;
}

/**
 * Compose a published per-state rebase with the baseline's anchor into one scale per sheet.
 *
 * The two contracts multiply: the baseline's magnitude sets how large the actor reads, and the
 * rebase makes every other state of that actor agree with it. This is the whole runtime side of
 * motion rebase - the ratio is a fact about the artwork that the pixels cannot yield, so it is
 * judged once by the producer and applied here rather than re-measured per frame.
 */
export function rebasedSheetScales(
  baselineSheetScale: number,
  stateRebase: ReadonlyMap<string, number>,
): ReadonlyMap<string, number> {
  const master = positiveFinite(baselineSheetScale, "baseline sheet scale");
  if (stateRebase.size === 0) {
    throw new Error("a published rebase must cover at least the baseline state");
  }
  const resolved = new Map<string, number>();
  for (const [textureKey, multiplier] of stateRebase) {
    resolved.set(textureKey, master * positiveFinite(multiplier, `rebase for ${textureKey}`));
  }
  return resolved;
}

/** Parse the one exact current scale-reference payload or reject the manifest boundary. */
export function parseScaleReference(
  value: unknown,
  label = "scale_reference",
): ScaleReference {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  const record = value as Record<string, unknown>;
  for (const key of Object.keys(record)) {
    if (!SCALE_REFERENCE_KEYS.has(key)) {
      throw new Error(`${label}.${key} is not supported`);
    }
  }
  for (const key of SCALE_REFERENCE_KEYS) {
    if (!Object.prototype.hasOwnProperty.call(record, key)) {
      throw new Error(`${label} is missing required key ${key}`);
    }
  }

  const part = record["part"];
  if (part !== "head" && part !== "body") {
    throw new Error(`${label}.part must be head or body`);
  }
  const topFraction = unitFraction(record["top_fraction"], `${label}.top_fraction`);
  const bottomFraction = unitFraction(
    record["bottom_fraction"],
    `${label}.bottom_fraction`,
  );
  const leftFraction = unitFraction(record["left_fraction"], `${label}.left_fraction`);
  const rightFraction = unitFraction(
    record["right_fraction"],
    `${label}.right_fraction`,
  );
  if (topFraction >= bottomFraction || leftFraction >= rightFraction) {
    throw new Error(`${label} bounds must be ordered inside the measured cell`);
  }
  const heightFraction = bottomFraction - topFraction;
  if (heightFraction < 0.02) {
    throw new Error(`${label} occupies too little of the measured cell`);
  }
  if (part === "head" && heightFraction > 0.75) {
    throw new Error(`${label} head bounds describe the whole sprite`);
  }

  const extentPixels = positiveFinite(record["extent_pixels"], `${label}.extent_pixels`);
  if (typeof record["confident"] !== "boolean") {
    throw new Error(`${label}.confident must be a boolean`);
  }
  const evidence = record["evidence"];
  if (typeof evidence !== "string" || evidence.length === 0 || evidence.length > 300) {
    throw new Error(`${label}.evidence must contain 1 through 300 characters`);
  }
  const frameIndex = record["frame_index"];
  if (!Number.isSafeInteger(frameIndex) || (frameIndex as number) < 0) {
    throw new Error(`${label}.frame_index must be a nonnegative integer`);
  }
  const cellWidth = record["cell_width"];
  const cellHeight = record["cell_height"];
  if (!Number.isSafeInteger(cellWidth) || (cellWidth as number) <= 0) {
    throw new Error(`${label}.cell_width must be a positive integer`);
  }
  if (!Number.isSafeInteger(cellHeight) || (cellHeight as number) <= 0) {
    throw new Error(`${label}.cell_height must be a positive integer`);
  }
  const expectedExtent = Math.max(
    (bottomFraction - topFraction) * (cellHeight as number),
    (rightFraction - leftFraction) * (cellWidth as number),
  );
  // The producer publishes the evaluated extent rounded to three decimals.
  if (Math.abs(extentPixels - expectedExtent) > 0.001) {
    throw new Error(`${label}.extent_pixels does not match its measured bounds`);
  }

  return Object.freeze({
    part,
    topFraction,
    bottomFraction,
    leftFraction,
    rightFraction,
    extentPixels,
    confident: record["confident"],
    evidence,
    frameIndex: frameIndex as number,
    cellWidth: cellWidth as number,
    cellHeight: cellHeight as number,
  });
}
