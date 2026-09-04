// The platformer's instantiation of the `ui` family.
//
// `ui`, the block this genre publishes its art direction in: the panel frame
// the conversation box and the defeat screen are both cut from, the button
// rect, the preview icon grid, and the inventory panel's slot geometry. It is
// the only block in this step that is a family's own rather than a table inside
// somebody else's.

import { parseUiBlock, type UiBlockView } from "@/lib/families/ui";
import type { BlockTable } from "@/lib/manifest/blocks";
import { PREPARED_RUNTIME_BLOCKS } from "@/lib/manifest/prepared-manifest";

export const PLATFORMER_UI_BLOCK = Object.freeze({
  block: "ui",
  version: PREPARED_RUNTIME_BLOCKS.ui,
});

/** Gate the platformer's ui block. Refuses by naming `ui`. */
export function parsePlatformerUiBlock(blocks: BlockTable): UiBlockView {
  return parseUiBlock(blocks, PLATFORMER_UI_BLOCK);
}
