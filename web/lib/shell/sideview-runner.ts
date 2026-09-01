// Server-side helper: read and enumerate infinite-runner runs.

import { promises as fs } from "node:fs";
import {
  parseRunnerRuntimeManifest,
  RUNNER_RUNTIME_KIND,
  type RunnerRuntimeManifest,
} from "@/lib/sideview-runner/contract";
import { readRunManifestDocument } from "./manifest-io";
import { assertSafeOutRoot, isSafeRunTag, OUT_ROOT } from "./runs";

/**
 * A manifest published under any other identity is not a runner run here,
 * exactly as an absent one is not. A manifest that claims this identity and
 * then fails validation still throws, because that is a contract violation
 * rather than a run this build does not read.
 */
export async function readRunnerManifest(tag: string): Promise<RunnerRuntimeManifest | null> {
  const document = await readRunManifestDocument(tag);
  if (document === null || document.kind !== RUNNER_RUNTIME_KIND) return null;
  return parseRunnerRuntimeManifest(document.declared);
}

export interface ReadyRunnerRun {
  tag: string;
  displayName: string;
  trackDisplayName: string;
  gameId: string;
  trackId: string;
  /** Run-relative ref of the avatar concept, the run's natural cover art. */
  cover: string;
}

export async function listReadyRunnerRuns(): Promise<ReadyRunnerRun[]> {
  if (!(await assertSafeOutRoot())) return [];
  const entries = await fs.readdir(OUT_ROOT, { withFileTypes: true });
  const out: ReadyRunnerRun[] = [];
  await Promise.all(
    entries.map(async (entry) => {
      if (!entry.isDirectory()) return;
      const tag = entry.name;
      if (!isSafeRunTag(tag)) return;
      try {
        const manifest = await readRunnerManifest(tag);
        if (manifest) {
          out.push({
            tag,
            displayName: manifest.displayName,
            trackDisplayName: manifest.trackDisplayName,
            gameId: manifest.gameId,
            trackId: manifest.trackId,
            cover: manifest.avatar.concept,
          });
        }
      } catch {
        // An invalid runner manifest is not a ready run.
      }
    }),
  );
  out.sort((a, b) => a.tag.localeCompare(b.tag));
  return out;
}
