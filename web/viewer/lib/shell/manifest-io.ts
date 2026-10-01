// Server-side helper: read one run's manifest.json bytes safely.
//
// A run that publishes a consumer document writes it as <run>/manifest.json with
// a declared `kind`; this module owns the one way those bytes are read (the
// hardened sequence in run-json.ts) so each genre's reader validates its own
// contract instead of re-implementing filesystem hygiene.

import { readRunDocument } from "./run-json";
import type { RunRef } from "./run-ref";

/**
 * Read <run>/manifest.json and return the parsed JSON with its declared
 * kind, or null when the run or manifest does not exist. The file is opened
 * without following symlinks and its inode is rechecked after reading so
 * consumers never parse a path-swapped manifest.
 */
export async function readRunManifestDocument(
  run: RunRef,
): Promise<{ declared: unknown; kind: string | undefined } | null> {
  const read = await readRunDocument(run, "manifest.json", {
    label: "run manifest",
    noun: "manifest",
  });
  if (read === null) return null;

  const declared = read.document;
  const kind =
    typeof declared === "object" && declared !== null
      ? typeof (declared as Record<string, unknown>).kind === "string"
        ? ((declared as Record<string, unknown>).kind as string)
        : undefined
      : undefined;
  return { declared, kind };
}
