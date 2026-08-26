// Server-side helper: enumerate completed projects under out/.
//
// A "ready" project is either a validated prepared-runtime package or a
// successful legacy prompt run. Used by the picker home page to surface direct
// Preview / Details links without making the page infer generated filenames.

import { promises as fs } from "node:fs";
import { existsSync } from "node:fs";
import path from "node:path";
import {
  assertSafeOutRoot,
  artifactPathFor,
  isSafeRunTag,
  OUT_ROOT,
  promptFromRunSummary,
  readRunSummary,
  runJsonPathFor,
} from "./runs";
import { readPreparedRuntimeManifest } from "./prepared-runtime";

export interface ReadyProject {
  tag: string;
  prompt: string;
  endedAt: string | null;
  conceptFile: string | null;
}

async function isRealRegularFile(target: string, root: string): Promise<boolean> {
  try {
    const stat = await fs.lstat(target);
    if (!stat.isFile() || stat.isSymbolicLink()) return false;
    const realRoot = await fs.realpath(root);
    const realTarget = await fs.realpath(target);
    return realTarget.startsWith(`${realRoot}${path.sep}`);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return false;
    throw error;
  }
}

export async function listReadyProjects(): Promise<ReadyProject[]> {
  if (!(await assertSafeOutRoot())) return [];
  const entries = await fs.readdir(OUT_ROOT, { withFileTypes: true });
  const out: ReadyProject[] = [];
  await Promise.all(
    entries.map(async (e) => {
      if (!e.isDirectory()) return;
      const tag = e.name;
      if (!isSafeRunTag(tag)) return;

      try {
        const manifest = await readPreparedRuntimeManifest(tag);
        if (manifest) {
          const runDir = path.join(OUT_ROOT, tag);
          const conceptPath = artifactPathFor(tag, manifest.player.concept.path);
          out.push({
            tag,
            prompt: manifest.display_name,
            endedAt: null,
            conceptFile: (await isRealRegularFile(conceptPath, runDir))
              ? manifest.player.concept.path
              : null,
          });
          return;
        }
      } catch {
        // An invalid prepared manifest is not a ready prepared project. A
        // successful legacy run.json in the same directory may still be valid.
      }

      const runJson = runJsonPathFor(tag);
      if (!existsSync(runJson)) return;
      try {
        const summary = await readRunSummary(tag);
        if (summary?.ok !== true) return;
        const conceptName = `concept_${tag}.png`;
        const conceptPath = artifactPathFor(tag, conceptName);
        const conceptFile = existsSync(conceptPath) ? conceptName : null;
        out.push({
          tag,
          prompt: promptFromRunSummary(summary) ?? "",
          endedAt: summary.ended_at,
          conceptFile,
        });
      } catch {
        // skip malformed run.json
      }
    }),
  );
  out.sort((a, b) => {
    const ax = a.endedAt ?? "";
    const bx = b.endedAt ?? "";
    return bx.localeCompare(ax) || a.tag.localeCompare(b.tag);
  });
  return out;
}
