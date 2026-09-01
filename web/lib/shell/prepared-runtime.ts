// Server-side readers for the prepared-runtime identity a run may publish.
//
// Both readers go through the hardened run-json sequence; they differ only in
// what they promise. The strict reader validates the whole contract, while the
// identity gate answers "is this run published as a prepared runtime" without
// judging the body, so a claiming-but-invalid manifest still reaches the
// strict reader and fails loudly there rather than being silently hidden.

import {
  parsePreparedRuntimeManifest,
  PREPARED_RUNTIME_KIND,
  PREPARED_RUNTIME_SCHEMA_VERSION,
  type PreparedRuntimeManifest,
} from "@/lib/manifest/prepared-manifest";
import { readRunDocument } from "./run-json";

const MANIFEST_LABELS = {
  label: "prepared runtime manifest",
  noun: "manifest",
} as const;

/**
 * Read and validate the immutable prepared-runtime authority for one safe run.
 * The file is opened without following symlinks and its inode is rechecked
 * after reading so consumers never parse a path-swapped manifest.
 *
 * A manifest published under any other identity is not a prepared run here, exactly as an absent
 * one is not. A manifest that claims this identity and then fails validation still throws,
 * because that is a contract violation rather than a run this build does not read.
 */
export async function readPreparedRuntimeManifest(
  tag: string,
): Promise<PreparedRuntimeManifest | null> {
  const read = await readRunDocument(tag, "manifest.json", MANIFEST_LABELS);
  if (read === null) return null;

  const declared = read.document;
  const kind =
    typeof declared === "object" && declared !== null
      ? (declared as Record<string, unknown>).kind
      : undefined;
  if (kind !== PREPARED_RUNTIME_KIND) return null;
  return parsePreparedRuntimeManifest(declared);
}

/**
 * Identity-only gate: does this run declare the prepared-runtime kind and
 * schema version? Absence and every read failure answer false rather than
 * throwing, because callers use this to decide whether a page exists at all;
 * the strict reader above is what refuses a claiming-but-invalid manifest.
 */
export async function isPreparedRuntimeRun(tag: string): Promise<boolean> {
  try {
    const read = await readRunDocument(tag, "manifest.json", MANIFEST_LABELS);
    if (read === null) return false;
    const declared = read.document;
    if (typeof declared !== "object" || declared === null) return false;
    const record = declared as Record<string, unknown>;
    return (
      record["schema_version"] === PREPARED_RUNTIME_SCHEMA_VERSION &&
      record["kind"] === PREPARED_RUNTIME_KIND
    );
  } catch {
    return false;
  }
}
