// What the `clock` family reads out of a manifest: which holders a package has.
//
// The family has no block of its own — a hold is a runtime fact, not an
// authored one — but *whether a genre's holder can exist at all* is authored,
// and it is authored in a block somebody else owns: the runner's moment hold
// exists only for a package that published an `fx` block with a moment in it,
// and the platformer's hitstop hold exists only for a package whose `gameplay`
// block enables combat. So the family gates that one block itself, by name,
// through the per-block table, instead of trusting the genre parser to have
// gated everything up front on its behalf.
//
// The gate is the point, not the fields. A producer that moves the block this
// family reads gets a refusal that names the block and the version this build
// reads, from the family that could not go on — which is what `blocks.ts`
// says the per-block table is for.

import { parseBlockTable, type BlockTable } from "@/lib/manifest/blocks";

export interface ClockBlockBinding {
  /** The block key this genre authors the clock's holders in. */
  readonly block: string;
  /** The version of that block this build reads. */
  readonly version: string;
  /** True when a package may publish no such block at all. */
  readonly optional?: boolean;
}

export interface ClockBlockView {
  readonly block: string;
  /** The version the package published, or null when an optional block is absent. */
  readonly version: string | null;
  /** Whether the package published the block the genre's holders come from. */
  readonly published: boolean;
}

/**
 * Gate the one block this genre's clock holders are authored in.
 *
 * `blocks` is the manifest's own per-block table, already parsed; re-gating it
 * here is not redundant, it is the family taking its own dependency instead of
 * inheriting the genre's.
 */
export function parseClockBlock(blocks: BlockTable, binding: ClockBlockBinding): ClockBlockView {
  const gated = parseBlockTable(
    blocks,
    { [binding.block]: binding.version },
    binding.optional ? { optional: [binding.block] } : {},
  );
  const version = gated[binding.block] ?? null;
  return Object.freeze({ block: binding.block, version, published: version !== null });
}
