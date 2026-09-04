import { describe, expect, test } from "bun:test";
import type Phaser from "phaser";
import {
  anchorRepackedMotionFeet,
  anchorRepackedMotionHead,
  applyMotionPlayback,
  installMotionPlayback,
  repackedMotionFootOriginY,
  repackedMotionHeadOriginY,
} from "./playback";

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

  test("hangs a motion from one top edge once frames arrive as tight crops", () => {
    // Frames reach the runtime already trimmed to their painted pixels, so a producer's packing
    // offsets are gone and every frame is flush. Registration has to be re-applied here or a
    // grip-anchored motion silently reverts to standing on its own feet - which is exactly what
    // shipped once, and read in play as the character bouncing.
    const tallest = 3080;
    const shorter = 2484;

    // The tallest pose is placed exactly where the foot anchor would place it, so a fully extended
    // climb still puts its feet on the logical actor Y and the ground contract is unchanged.
    expect(repackedMotionHeadOriginY(tallest, tallest)).toBeCloseTo(
      repackedMotionFootOriginY(tallest),
    );
    // A shorter pose is pushed down by the difference, which lifts its feet and fixes its top edge.
    const shorterOrigin = repackedMotionHeadOriginY(shorter, tallest);
    expect(shorterOrigin).toBeGreaterThan(1);
    expect(shorterOrigin * shorter).toBeCloseTo(
      repackedMotionFootOriginY(tallest) * tallest,
    );

    const calls: unknown[] = [];
    const sprite = {
      frame: { height: shorter },
      setOrigin: (x: number, y: number) => calls.push([x, y]),
    } as unknown as Phaser.GameObjects.Sprite;
    anchorRepackedMotionHead(sprite, tallest);
    expect(calls).toEqual([[0.5, shorterOrigin]]);

    expect(() => repackedMotionHeadOriginY(tallest, shorter)).toThrow("valid frame heights");
  });
});
