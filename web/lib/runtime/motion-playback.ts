import type Phaser from "phaser";

export type RuntimeMotionPlayback = Readonly<{
  mode: "hold" | "loop" | "once" | "gameplay_driven";
  canonical_frame_indices: readonly number[];
  frames_per_second?: number;
}>;

/** Canonical alpha-component repacking preserves this isolation gutter below every actor crop. */
export const REPACKED_MOTION_BOTTOM_GUTTER_PX = 12;

export function repackedMotionFootOriginY(
  frameHeight: number,
  bottomGutterPixels = REPACKED_MOTION_BOTTOM_GUTTER_PX,
): number {
  if (
    !Number.isFinite(frameHeight) ||
    frameHeight <= 0 ||
    !Number.isFinite(bottomGutterPixels) ||
    bottomGutterPixels < 0 ||
    bottomGutterPixels >= frameHeight
  ) {
    throw new Error("repacked motion foot anchor requires a valid frame height and gutter");
  }
  return 1 - bottomGutterPixels / frameHeight;
}

/**
 * Origin that keeps a motion's frames hanging from a fixed top edge.
 *
 * Frames reach the runtime as tight alpha crops - `loadFrameStrip` re-measures each cell's painted
 * bounding box - so however the producer packed the strip, every frame arrives flush and a
 * bottom-relative origin registers each pose on its own lowest pixel. For an actor standing on a
 * surface that is right. For one hanging from its hands it is not: it pins the feet and swings the
 * head instead.
 *
 * The tallest frame keeps exactly the placement `repackedMotionFootOriginY` gives it, so a
 * fully extended pose still puts its feet on the logical actor Y. Shorter frames are pushed down by
 * the difference, which lifts their feet off that line and leaves every frame's top edge fixed.
 * Values above 1 are intentional and valid: the origin sits below a short frame's own height.
 */
export function repackedMotionHeadOriginY(
  frameHeight: number,
  tallestFrameHeight: number,
  bottomGutterPixels = REPACKED_MOTION_BOTTOM_GUTTER_PX,
): number {
  if (
    !Number.isFinite(frameHeight) ||
    frameHeight <= 0 ||
    !Number.isFinite(tallestFrameHeight) ||
    tallestFrameHeight < frameHeight ||
    !Number.isFinite(bottomGutterPixels) ||
    bottomGutterPixels < 0 ||
    bottomGutterPixels >= tallestFrameHeight
  ) {
    throw new Error("repacked motion head anchor requires valid frame heights and gutter");
  }
  return (tallestFrameHeight - bottomGutterPixels) / frameHeight;
}

/** Hang every frame of a motion from one top edge instead of standing it on its own feet. */
export function anchorRepackedMotionHead(
  sprite: Phaser.GameObjects.Sprite,
  tallestFrameHeight: number,
  bottomGutterPixels = REPACKED_MOTION_BOTTOM_GUTTER_PX,
): void {
  sprite.setOrigin(
    0.5,
    repackedMotionHeadOriginY(sprite.frame.height, tallestFrameHeight, bottomGutterPixels),
  );
}

/** Keep the visible feet on the logical actor Y while leaving the producer's isolation gutter intact. */
export function anchorRepackedMotionFeet(
  sprite: Phaser.GameObjects.Sprite,
  bottomGutterPixels = REPACKED_MOTION_BOTTOM_GUTTER_PX,
): void {
  sprite.setOrigin(
    0.5,
    repackedMotionFootOriginY(sprite.frame.height, bottomGutterPixels),
  );
}

/** Install a timeline animation when playback owns time; held and gameplay-driven poses need none. */
export function installMotionPlayback(
  scene: Phaser.Scene,
  animationKey: string,
  textureKey: string,
  playback: RuntimeMotionPlayback,
): void {
  if (playback.mode === "hold" || scene.anims.exists(animationKey)) {
    return;
  }
  const framesPerSecond =
    playback.mode === "gameplay_driven" ? 1 : playback.frames_per_second;
  if (framesPerSecond === undefined) {
    throw new Error(`${animationKey} timeline playback is missing frames_per_second`);
  }
  scene.anims.create({
    key: animationKey,
    frames: playback.canonical_frame_indices.map((frame) => ({
      key: textureKey,
      frame,
    })),
    frameRate: framesPerSecond,
    repeat:
      playback.mode === "loop" || playback.mode === "gameplay_driven" ? -1 : 0,
  });
}

/** Apply a resolved policy without inferring behavior from an actor role or state name. */
export function applyMotionPlayback(
  sprite: Phaser.GameObjects.Sprite,
  animationKey: string,
  textureKey: string,
  playback: RuntimeMotionPlayback,
): void {
  if (playback.mode === "hold" || playback.mode === "gameplay_driven") {
    sprite.anims.stop();
    sprite.setTexture(textureKey, playback.canonical_frame_indices[0] ?? 0);
    return;
  }
  sprite.play(animationKey, true);
}
