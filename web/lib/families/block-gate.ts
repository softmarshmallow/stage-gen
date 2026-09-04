// How a family takes its own dependency on a manifest block.
//
// `manifest/blocks.ts` says what the per-block table is for: a producer that
// changes one block moves one version, and the refusal names the block rather
// than the run. It also says what was missing — "until the runtime family
// layer parses blocks one family at a time, the genre parsers gate every block
// up front". This is that layer's half of it.
//
// A family gates the block it depends on itself, by name, and does it whether
// or not the genre parser has already gated the same block. That is not
// redundant, it is the point: the dependency belongs to the consumer that
// cannot go on without it, so the refusal comes from the family that reads the
// block instead of from a parser speaking on behalf of a dozen consumers it
// knows nothing about. A family that is dropped from a roster takes its gate
// with it, and one that is added brings its own.

import { parseBlockTable, type BlockTable } from "@/lib/manifest/blocks";

export interface FamilyBlockBinding {
  /** The block key this genre authors the family's input in. */
  readonly block: string;
  /** The version of that block this build reads. */
  readonly version: string;
  /** True when a package may publish no such block at all. */
  readonly optional?: boolean;
}

export interface FamilyBlockView {
  readonly block: string;
  /** The version the package published, or null when an optional block is absent. */
  readonly version: string | null;
  /** Whether the package published the block at all. */
  readonly published: boolean;
}

/**
 * Gate one named block out of a manifest's own per-block table.
 *
 * `blocks` is the table the genre parser already produced; re-gating it here
 * is the family taking its own dependency rather than inheriting the genre's.
 */
export function gateFamilyBlock(blocks: BlockTable, binding: FamilyBlockBinding): FamilyBlockView {
  const gated = parseBlockTable(
    blocks,
    { [binding.block]: binding.version },
    binding.optional ? { optional: [binding.block] } : {},
  );
  const version = gated[binding.block] ?? null;
  return Object.freeze({ block: binding.block, version, published: version !== null });
}
