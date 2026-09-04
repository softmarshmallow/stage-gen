// What the `ui` family reads out of a manifest.
//
// `ui.toml`, and it is the one family in this step whose block genuinely is its
// own. The nine-slice roles, the icon grid and the inventory panel's geometry
// are art direction: what a frame's ornament-free interior is, which cell a
// glyph lives in, where the slots sit on the panel. Three strict block parsers
// already read it (`ui-atlas-layout`, `ui-icon-layout`, `inventory-layout`);
// what was missing is a *consumer* taking the dependency, because until this
// step `ui-atlas/` was a directory rather than a family.
//
// The runner publishes no `ui` block at all, which is an answer and not a gap:
// its HUD is drawn from primitives and it owns no sheet. So the gate is the
// platformer's, and the room's — whose roles are inside its own versioned
// document rather than in a block table.

import { gateFamilyBlock, type FamilyBlockBinding, type FamilyBlockView } from "../block-gate";
import type { BlockTable } from "@/lib/manifest/blocks";

export type UiBlockBinding = FamilyBlockBinding;
export type UiBlockView = FamilyBlockView;

export function parseUiBlock(blocks: BlockTable, binding: UiBlockBinding): UiBlockView {
  return gateFamilyBlock(blocks, binding);
}
