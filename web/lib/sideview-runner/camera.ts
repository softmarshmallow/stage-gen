// The runner's binding of the `camera` family: `auto_run_x_v1`, which is the
// anchored mode.
//
// The avatar never moves horizontally on screen — it is pinned at
// `avatarScreenX` and the world scrolls under it — so the scroll is a pure
// function of how far the run has travelled, and the family's `anchoredScroll`
// is the whole of the arithmetic. There is no follow, no dead zone and no
// bounds box here: this genre's world is streamed rather than bounded, and a
// box would have nothing to clamp.
//
// Shake is the other mode's input and this genre raises none — the runner has
// no impact source — so the binding states the mode and stops. That asymmetry
// is the family's, not a missing feature: a genre that later shakes an anchored
// camera carries a `ShakeCarrier` the same way the platformer does.
//
// It used to declare a read of `run` it never performed, to buy the ordering
// edge that put it after the run loop. That is what `after` is for, and the
// edge is still wanted: the session is where a run ends, and the frame the
// camera draws should be the one the lifecycle has finished deciding.

import {
  anchoredScroll,
  createCameraSystem,
  type CameraBlockView,
} from "@/lib/families/camera";
import { parseCameraBlock } from "@/lib/families/camera/manifest";
import type { BlockTable } from "@/lib/manifest/blocks";
import type { GameSystem } from "@/lib/kernel/systems";
import { RUNNER_BLOCKS } from "./contract";
import type { RunnerWorld, RunnerWorldConfig } from "./world";

/**
 * The block this genre's camera is authored in.
 *
 * `[camera] mode` is one authored word and it is the whole of the vocabulary:
 * a package that names `auto_run_x_v1` is asking for the anchored mode. A
 * producer that moves the block gets `manifest block "camera" is published as
 * …; this build reads runner-camera-block-v1`, from the camera.
 */
export const RUNNER_CAMERA_BLOCK = Object.freeze({
  block: "camera",
  version: RUNNER_BLOCKS.camera,
});

/** Gate the runner's camera block. Refuses by naming `camera`. */
export function parseRunnerCameraBlock(blocks: BlockTable): CameraBlockView {
  return parseCameraBlock(blocks, RUNNER_CAMERA_BLOCK);
}

/** Horizontal world scroll that pins the avatar to its screen anchor. */
export function cameraScrollX(distanceColumns: number, config: RunnerWorldConfig): number {
  return anchoredScroll(distanceColumns * config.tilePx, config.avatarScreenX);
}

export function createRunnerCameraSystem(): GameSystem<RunnerWorld> {
  return createCameraSystem<RunnerWorld>({
    mode: "anchored",
    id: "runner/camera",
    contractVersion: "camera-system-v2",
    reads: ["avatar"],
    owns: ["camera"],
    after: ["session/run"],
    track: (world) => world.avatar.distanceColumns * world.config.tilePx,
    anchor: (world) => world.config.avatarScreenX,
    apply: (world, scrollX) => {
      world.camera.scrollX = scrollX;
    },
  });
}
