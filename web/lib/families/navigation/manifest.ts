// What the `navigation` family reads out of a manifest.
//
// The composition table says "none; derived from the space family", and that is
// right about the *geometry*: nodes and links come from the traversal core's
// surfaces, not from an authored graph, and there is no navigation block to
// move. It is not right about the repertoire. `[navigation].allowed_movements`
// is what admits a link at all — a package that does not list `climb` is a
// package whose ladders are not routes — and that is authored, inside
// `gameplay`.
//
// So one block, gated for the reason a family gates one: this is the consumer
// that cannot go on without it, and the refusal should come from here rather
// than from a parser speaking for a dozen consumers it does not know about.

import { gateFamilyBlock, type FamilyBlockBinding, type FamilyBlockView } from "../block-gate";
import type { BlockTable } from "@/lib/manifest/blocks";

export type NavigationBlockBinding = FamilyBlockBinding;
export type NavigationBlockView = FamilyBlockView;

export function parseNavigationBlock(
  blocks: BlockTable,
  binding: NavigationBlockBinding,
): NavigationBlockView {
  return gateFamilyBlock(blocks, binding);
}
