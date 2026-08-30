// Server-side helper: read one run's manifest.json bytes safely.
//
// Every genre runtime publishes its authority as out/<tag>/manifest.json with
// a declared `kind`; this module owns the one hardened way those bytes are
// read (no symlinks, inode rechecked after the read) so each genre's reader
// validates its own contract instead of re-implementing filesystem hygiene.

import { constants as fsConstants, promises as fs } from "node:fs";
import path from "node:path";
import { artifactPathFor, assertSafeOutRoot, runDirFor } from "./runs";

async function lstatOrNull(
  target: string,
): Promise<Awaited<ReturnType<typeof fs.lstat>> | null> {
  try {
    return await fs.lstat(target);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  }
}

async function assertRealDirectory(target: string, label: string): Promise<boolean> {
  const stat = await lstatOrNull(target);
  if (!stat) return false;
  if (!stat.isDirectory() || stat.isSymbolicLink()) {
    throw new Error(`${label} must be a real directory`);
  }
  if ((await fs.realpath(target)) !== path.resolve(target)) {
    throw new Error(`${label} must not traverse a symlink`);
  }
  return true;
}

/**
 * Read out/<tag>/manifest.json and return the parsed JSON with its declared
 * kind, or null when the run or manifest does not exist. The file is opened
 * without following symlinks and its inode is rechecked after reading so
 * consumers never parse a path-swapped manifest.
 */
export async function readRunManifestDocument(
  tag: string,
): Promise<{ declared: unknown; kind: string | undefined } | null> {
  if (!(await assertSafeOutRoot())) return null;

  const runDir = runDirFor(tag);
  if (!(await assertRealDirectory(runDir, "run directory"))) return null;

  const manifestPath = artifactPathFor(tag, "manifest.json");
  const initial = await lstatOrNull(manifestPath);
  if (!initial) return null;
  if (!initial.isFile() || initial.isSymbolicLink()) {
    throw new Error("run manifest must be a real regular file");
  }

  const handle = await fs.open(manifestPath, fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW);
  let bytes: Buffer;
  let opened: Awaited<ReturnType<typeof handle.stat>>;
  try {
    opened = await handle.stat();
    if (!opened.isFile()) {
      throw new Error("run manifest must be a real regular file");
    }
    bytes = await handle.readFile();
  } finally {
    await handle.close();
  }

  const current = await fs.lstat(manifestPath);
  if (
    opened.dev !== initial.dev ||
    opened.ino !== initial.ino ||
    current.isSymbolicLink() ||
    !current.isFile() ||
    current.dev !== opened.dev ||
    current.ino !== opened.ino
  ) {
    throw new Error("run manifest changed while it was being read");
  }
  if ((await fs.realpath(runDir)) !== path.resolve(runDir)) {
    throw new Error("run directory changed while its manifest was being read");
  }

  const declared: unknown = JSON.parse(bytes.toString("utf8"));
  const kind =
    typeof declared === "object" && declared !== null
      ? typeof (declared as Record<string, unknown>).kind === "string"
        ? ((declared as Record<string, unknown>).kind as string)
        : undefined
      : undefined;
  return { declared, kind };
}
