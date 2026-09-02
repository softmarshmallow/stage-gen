// Pure presentation math for runner pickups and hazards.
//
// These transforms never feed simulation. Occupancy and the published AABBs
// remain the only gameplay geometry; this module only makes those authored
// opportunities and threats easier to read at runner speed.

const TAU = Math.PI * 2;

export interface CollectiblePresentation {
  readonly bobRows: number;
  readonly scaleXMultiplier: number;
  readonly scaleYMultiplier: number;
  readonly haloAlpha: number;
  readonly haloScale: number;
}

/** Stable per-instance phase so a trail ripples instead of moving as one slab. */
export function presentationPhase(key: string): number {
  let hash = 2166136261;
  for (let index = 0; index < key.length; index += 1) {
    hash ^= key.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return ((hash >>> 0) / 0x100000000) * TAU;
}

/** A continuous flip, hover, and glint for a single-image collectible. */
export function collectiblePresentation(
  elapsedMilliseconds: number,
  phaseOffset: number,
): CollectiblePresentation {
  if (!Number.isFinite(elapsedMilliseconds) || !Number.isFinite(phaseOffset)) {
    throw new Error("collectible presentation requires finite time and phase");
  }
  const phase = (elapsedMilliseconds / 1000) * TAU * 1.4 + phaseOffset;
  const face = Math.abs(Math.cos(phase));
  const hover = Math.sin(phase * 0.5);
  return Object.freeze({
    bobRows: hover * 0.1,
    // Never collapse all the way to zero: a one-pixel edge can disappear
    // under canvas filtering and look like a dropped frame.
    scaleXMultiplier: 0.16 + face * 0.84,
    scaleYMultiplier: 0.96 + (1 - face) * 0.04,
    haloAlpha: 0.1 + face * 0.22,
    haloScale: 0.82 + face * 0.18,
  });
}

/**
 * Preserve authored vertical calibration while keeping the visible hazard
 * footprint inside the exact published collision column.
 */
export function hazardVisualScale(
  calibratedScale: number,
  sourceWidth: number,
  collisionWidthPixels: number,
): Readonly<{ scaleX: number; scaleY: number }> {
  if (
    !Number.isFinite(calibratedScale) ||
    calibratedScale <= 0 ||
    !Number.isFinite(sourceWidth) ||
    sourceWidth <= 0 ||
    !Number.isFinite(collisionWidthPixels) ||
    collisionWidthPixels <= 0
  ) {
    throw new Error("hazard visual scale requires positive finite dimensions");
  }
  return Object.freeze({
    scaleX: Math.min(calibratedScale, collisionWidthPixels / sourceWidth),
    scaleY: calibratedScale,
  });
}

/** A restrained approach cue; behind the player it vanishes immediately. */
export function hazardCueAlpha(
  distanceAheadColumns: number,
  elapsedMilliseconds: number,
): number {
  if (!Number.isFinite(distanceAheadColumns) || !Number.isFinite(elapsedMilliseconds)) {
    throw new Error("hazard cue requires finite distance and time");
  }
  if (distanceAheadColumns < 0 || distanceAheadColumns > 8) return 0;
  const proximity = 1 - distanceAheadColumns / 8;
  const pulse = 0.75 + Math.sin((elapsedMilliseconds / 1000) * TAU * 2.2) * 0.25;
  return (0.12 + proximity * 0.24) * pulse;
}
