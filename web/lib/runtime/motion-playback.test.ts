import { describe, expect, test } from "bun:test";
import type Phaser from "phaser";
import {
  anchorRepackedMotionFeet,
  applyMotionPlayback,
  installMotionPlayback,
  repackedMotionFootOriginY,
} from "./motion-playback";

describe("resolved motion playback", () => {
  test("holds one canonical frame without creating or starting an animation", () => {
    const created: unknown[] = [];
    const scene = {
      anims: {
        exists: () => false,
        create: (config: unknown) => created.push(config),
      },
    } as unknown as Phaser.Scene;
    const calls: unknown[] = [];
    const sprite = {
      anims: { stop: () => calls.push("stop") },
      setTexture: (texture: string, frame: number) =>
        calls.push(["texture", texture, frame]),
      play: (key: string) => calls.push(["play", key]),
    } as unknown as Phaser.GameObjects.Sprite;
    const playback = {
      mode: "hold" as const,
      canonical_frame_indices: [2],
    };

    installMotionPlayback(scene, "player_idle", "character_idle", playback);
    applyMotionPlayback(sprite, "player_idle", "character_idle", playback);

    expect(created).toEqual([]);
    expect(calls).toEqual(["stop", ["texture", "character_idle", 2]]);
  });

  test("installs and starts only the selected loop frames", () => {
    const created: unknown[] = [];
    const scene = {
      anims: {
        exists: () => false,
        create: (config: unknown) => created.push(config),
      },
    } as unknown as Phaser.Scene;
    const calls: unknown[] = [];
    const sprite = {
      anims: { stop: () => calls.push("stop") },
      setTexture: () => undefined,
      play: (key: string, ignoreIfPlaying: boolean) =>
        calls.push(["play", key, ignoreIfPlaying]),
    } as unknown as Phaser.GameObjects.Sprite;
    const playback = {
      mode: "loop" as const,
      canonical_frame_indices: [0, 2, 3],
      frames_per_second: 9,
    };

    installMotionPlayback(scene, "player_run", "character_run", playback);
    applyMotionPlayback(sprite, "player_run", "character_run", playback);

    expect(created).toEqual([
      {
        key: "player_run",
        frames: [0, 2, 3].map((frame) => ({
          key: "character_run",
          frame,
        })),
        frameRate: 9,
        repeat: -1,
      },
    ]);
    expect(calls).toEqual([["play", "player_run", true]]);
  });

  test("anchors the visible crop bottom instead of the repacked cell bottom", () => {
    expect(repackedMotionFootOriginY(205.5)).toBeCloseTo(1 - 12 / 205.5);
    const calls: unknown[] = [];
    const sprite = {
      frame: { height: 205.5 },
      setOrigin: (x: number, y: number) => calls.push([x, y]),
    } as unknown as Phaser.GameObjects.Sprite;
    anchorRepackedMotionFeet(sprite);
    expect(calls).toHaveLength(1);
    expect(calls[0]).toEqual([0.5, repackedMotionFootOriginY(205.5)]);
    expect(() => repackedMotionFootOriginY(12)).toThrow("valid frame height");
  });
});
