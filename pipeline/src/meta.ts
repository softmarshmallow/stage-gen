// Reproducibility sidecar writer.
//
// Every generated artifact in the pipeline gets `<artifact>.meta.json`
// alongside it, recording everything needed to reproduce or retry the call
// without the main agent ever having to load the artifact itself.
//
// Today the stub stages call `writeMeta` with a minimal `{ stage, prompt, ts }`
// payload. Phase 2+ generators will pass the full payload (model, seed, refs,
// params, prompt text). The writer is intentionally schema-loose — the
// recorded metadata is operational, not user-facing.

import { writeFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";

export interface MetaPayload {
  // Stage that produced the artifact (e.g. "concept", "world-spec", "layer-0").
  stage: string;
  // The user's world prompt the run was started from.
  prompt: string;
  // Wall-clock ISO timestamp of when the artifact was written.
  ts: string;
  // Optional reproducibility fields — populated by real generators.
  model?: string;
  seed?: number | string;
  refs?: string[];
  params?: Record<string, unknown>;
  // Free-form bag for stage-specific notes (size, frame count, etc.).
  extra?: Record<string, unknown>;
}

/**
 * Write `<artifactPath>.meta.json` next to the artifact.
 *
 * Creates the parent directory if it doesn't exist. Overwrites any existing
 * sidecar — meta is always derived from the most recent generation attempt.
 */
export async function writeMeta(
  artifactPath: string,
  payload: MetaPayload,
): Promise<string> {
  const metaPath = `${artifactPath}.meta.json`;
  await mkdir(dirname(metaPath), { recursive: true });
  await writeFile(metaPath, JSON.stringify(payload, null, 2) + "\n", "utf8");
  return metaPath;
}

/** Convenience constructor for the minimal payload stub stages emit today. */
export function stubMeta(stage: string, prompt: string): MetaPayload {
  return { stage, prompt, ts: new Date().toISOString() };
}
