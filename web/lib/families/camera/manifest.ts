// What the `camera` family reads out of a manifest: which mode a package
// authored, and how far the view may travel in it.
//
// Two authored vocabularies, and this is the family that has to answer for
// both. The runner authors `[camera] mode = "auto_run_x_v1"` in a block of its
// own; the platformer authors `camera.follow_axes` per map, inside the map
// book. So the block is not the same one in both genres and the family does not
// pretend it is — what is the same is that a package that moved it gets the
// refusal from the camera, by name, rather than from a genre parser gating a
// dozen blocks on a dozen consumers' behalf.

import { gateFamilyBlock, type FamilyBlockBinding, type FamilyBlockView } from "../block-gate";
import type { BlockTable } from "@/lib/manifest/blocks";

export type CameraBlockBinding = FamilyBlockBinding;
export type CameraBlockView = FamilyBlockView;

export function parseCameraBlock(blocks: BlockTable, binding: CameraBlockBinding): CameraBlockView {
  return gateFamilyBlock(blocks, binding);
}
