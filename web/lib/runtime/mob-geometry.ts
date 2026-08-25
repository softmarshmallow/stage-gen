export type MobAlphaFrame = Readonly<{ w: number; h: number }>;

export type MobRenderEnvelope = Readonly<{
  scale: number;
  halfWidth: number;
  height: number;
}>;

export type MobWorldLane = Readonly<{
  spawnX: number;
  wanderMin: number;
  wanderMax: number;
}>;

function positiveFinite(value: number, label: string): number {
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(`${label} must be positive and finite`);
  }
  return value;
}

/**
 * Measure the conservative rendered alpha envelope across every animation
 * frame. Phaser keeps the frame-zero scale while animation frames change, so
 * the widest/tallest idle or hurt crop is the only safe world-edge contract.
 */
export function mobRenderEnvelope(input: Readonly<{
  idleFrames: readonly MobAlphaFrame[];
  hurtFrames: readonly MobAlphaFrame[];
  targetFrameZeroHeight: number;
}>): MobRenderEnvelope {
  if (input.idleFrames.length === 0) {
    throw new Error("mob idle frames must not be empty");
  }
  const frames = [...input.idleFrames, ...input.hurtFrames];
  for (const frame of frames) {
    positiveFinite(frame.w, "mob alpha frame width");
    positiveFinite(frame.h, "mob alpha frame height");
  }
  const frameZeroHeight = positiveFinite(
    input.idleFrames[0]!.h,
    "mob frame-zero alpha height",
  );
  const scale =
    positiveFinite(input.targetFrameZeroHeight, "mob target height") /
    frameZeroHeight;
  return Object.freeze({
    scale,
    halfWidth: (Math.max(...frames.map((frame) => frame.w)) * scale) / 2,
    height: Math.max(...frames.map((frame) => frame.h)) * scale,
  });
}

/** Keep the complete alpha envelope inside both the world and wander lane. */
export function mobWorldLane(input: Readonly<{
  candidateSpawnX: number;
  wanderExtent: number;
  worldWidth: number;
  renderedHalfWidth: number;
}>): MobWorldLane {
  const worldWidth = positiveFinite(input.worldWidth, "mob world width");
  const halfWidth = positiveFinite(
    input.renderedHalfWidth,
    "mob rendered half-width",
  );
  if (!Number.isFinite(input.candidateSpawnX)) {
    throw new Error("mob candidate spawn must be finite");
  }
  if (!Number.isFinite(input.wanderExtent) || input.wanderExtent < 0) {
    throw new Error("mob wander extent must be finite and nonnegative");
  }
  if (halfWidth * 2 > worldWidth) {
    throw new Error("mob alpha envelope is wider than the world");
  }
  const clamp = (value: number) =>
    Math.min(worldWidth - halfWidth, Math.max(halfWidth, value));
  const spawnX = clamp(input.candidateSpawnX);
  return Object.freeze({
    spawnX,
    wanderMin: Math.max(halfWidth, spawnX - input.wanderExtent),
    wanderMax: Math.min(
      worldWidth - halfWidth,
      spawnX + input.wanderExtent,
    ),
  });
}

/**
 * Which way a struck mob turns.
 *
 * The knockback direction points away from whoever landed the hit, so facing
 * is its negation: a mob shoved right was hit from its left and turns to look
 * that way. Keeping the relationship in one named place matters because the
 * two are opposites and an inverted sign reads as a mob calmly walking away
 * from a sword rather than rounding on it.
 */
export function mobHitFacing(knockbackDir: 1 | -1): 1 | -1 {
  return knockbackDir === 1 ? -1 : 1;
}

export function mobFullAlphaBounds(
  x: number,
  footY: number,
  envelope: MobRenderEnvelope,
): Readonly<{ left: number; right: number; top: number; bottom: number }> {
  if (!Number.isFinite(x) || !Number.isFinite(footY)) {
    throw new Error("mob alpha bounds position must be finite");
  }
  return Object.freeze({
    left: x - envelope.halfWidth,
    right: x + envelope.halfWidth,
    top: footY - envelope.height,
    bottom: footY,
  });
}
