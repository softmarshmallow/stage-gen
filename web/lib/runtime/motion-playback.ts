import type Phaser from "phaser";

export type RuntimeMotionPlayback = Readonly<{
  mode: "hold" | "loop" | "once" | "gameplay_driven";
  canonical_frame_indices: readonly number[];
  frames_per_second?: number;
}>;

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
