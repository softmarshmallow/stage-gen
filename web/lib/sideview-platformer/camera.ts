// The platformer's binding of the `camera` family: `player_follow`, which is
// the follow mode.
//
// The scene does not compute a scroll. It hands Phaser a world box, a follow
// target and a dead zone, and the engine moves the view; the only thing the
// frame does to the camera is carry the tremor a blow raised. So the binding
// states the mode, answers what is shaking the view this frame, and hands the
// answer back through the family's `ShakeCarrier` — the object that remembers
// what is currently applied, which is what keeps the offset an *input* rather
// than a displacement that walks the view away from the follow.
//
// The bounds box is the other half of the mode, and it is not a frame step: it
// is stated once per map entry, out of the map's own `follow_axes`, and the
// family owns the derivation because "an axis is switched off by giving the
// camera no room to travel along it" is a camera rule and not a scene one.

import { createCameraSystem, type CameraBlockView, type ShakeOffset } from "@/lib/families/camera";
import { parseCameraBlock } from "@/lib/families/camera/manifest";
import { PREPARED_RUNTIME_BLOCKS } from "@/lib/manifest/prepared-manifest";
import type { BlockTable } from "@/lib/manifest/blocks";
import type { PlatformerFrameSteps, PlatformerFrameSystem, PlatformerFrameWorld } from "./frame-roster";

/**
 * The block this genre's camera is authored in.
 *
 * There is no `[camera]` block here: the vocabulary is `camera.follow_axes` on
 * each map, so the block the family depends on is the map book. A producer that
 * moves it gets `manifest block "maps" is published as …; this build reads
 * platformer-maps-block-v1`, from the camera.
 */
export const PLATFORMER_CAMERA_BLOCK = Object.freeze({
  block: "maps",
  version: PREPARED_RUNTIME_BLOCKS.maps,
});

/** Gate the platformer's camera block. Refuses by naming `maps`. */
export function parsePlatformerCameraBlock(blocks: BlockTable): CameraBlockView {
  return parseCameraBlock(blocks, PLATFORMER_CAMERA_BLOCK);
}

/**
 * The frame's one camera step: carry this frame's shake.
 *
 * `shake` and `carry` are the scene's, because the offset's source is this
 * genre's own answer to "which events shake the view" and the camera object is
 * the engine's. What the family contributes is the sequencing and the rule that
 * the previous offset comes off before the next goes on.
 */
export function createPlatformerCameraSystem(steps: PlatformerFrameSteps): PlatformerFrameSystem {
  return createCameraSystem<PlatformerFrameWorld>({
    mode: "follow",
    id: "camera/shake",
    contractVersion: "camera-system-v1",
    reads: ["hold", "impact"],
    writes: ["camera"],
    quiet: (world) => world.hold,
    shake: (_world, nowMs): ShakeOffset => steps.impactShake(nowMs),
    carry: (_world, next) => steps.carryCameraShake(next),
  });
}
