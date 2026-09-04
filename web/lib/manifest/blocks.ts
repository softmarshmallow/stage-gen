// Per-block versions in a published runtime manifest (contract rule C-R3).
//
// A manifest root carries a `blocks` table: block key -> the block's own version. A
// consumer gates the block it parses on that entry, so a producer that changes one
// block moves one version and the refusal names the block rather than the run. The
// document's own `kind` moves only when the set of blocks or the root fields change
// shape. Until the runtime family layer parses blocks one family at a time, the genre
// parsers gate every block up front and the message names which one refused.

export type BlockTable = Readonly<Record<string, string>>;

export type ExpectedBlocks = Readonly<Record<string, string>>;

/**
 * Parse the `blocks` table and gate every expected block against the version this build
 * reads. A block listed in `optional` may be absent from the table (the run does not
 * publish it) but, when present, must still carry the expected version.
 */
export function parseBlockTable(
  value: unknown,
  expected: ExpectedBlocks,
  options: { readonly optional?: readonly string[] } = {},
): BlockTable {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("manifest blocks table is missing; this build reads per-block versions");
  }
  const table = value as Record<string, unknown>;
  const optional = new Set(options.optional ?? []);
  const parsed: Record<string, string> = {};
  for (const [key, entry] of Object.entries(table)) {
    if (typeof entry !== "string" || entry.length === 0) {
      throw new Error(`manifest block "${key}" declares an invalid version`);
    }
    parsed[key] = entry;
  }
  for (const [key, version] of Object.entries(expected)) {
    const found = parsed[key];
    if (found === undefined) {
      if (optional.has(key)) continue;
      throw new Error(`manifest block "${key}" is not published; this build reads ${version}`);
    }
    if (found !== version) {
      throw new Error(
        `manifest block "${key}" is published as ${found}; this build reads ${version}`,
      );
    }
  }
  return Object.freeze(parsed);
}
