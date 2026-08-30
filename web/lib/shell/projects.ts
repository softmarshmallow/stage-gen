// Server-side helper: enumerate published runtime packages under out/.
//
// A "ready" project is one validated prepared-runtime package. The home page uses
// this to link straight into a preview without inferring generated filenames.

import { promises as fs } from "node:fs";
import path from "node:path";
import {
  assertSafeOutRoot,
  artifactPathFor,
  isSafeRunTag,
  OUT_ROOT,
} from "./runs";
import { readPreparedRuntimeManifest } from "./prepared-runtime";

export interface ReadyProject {
  tag: string;
  displayName: string;
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
            displayName: manifest.display_name,
            conceptFile: (await isRealRegularFile(conceptPath, runDir))
              ? manifest.player.concept.path
              : null,
          });
          return;
        }
      } catch {
        // An invalid prepared manifest is not a ready prepared project.
      }
    }),
  );
  out.sort((a, b) => a.tag.localeCompare(b.tag));
  return out;
}
