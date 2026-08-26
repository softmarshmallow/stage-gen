import { constants as fsConstants, promises as fs } from "node:fs";
import path from "node:path";
import {
  parsePreparedRuntimeManifest,
  type PreparedRuntimeManifest,
} from "@/lib/runtime/prepared-manifest";
import {
  artifactPathFor,
  assertSafeOutRoot,
  runDirFor,
} from "./runs";

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

async function assertRealDirectory(
  target: string,
  label: string,
): Promise<boolean> {
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
 * Read and validate the immutable prepared-runtime authority for one safe run.
 * The file is opened without following symlinks and its inode is rechecked
 * after reading so consumers never parse a path-swapped manifest.
 */
export async function readPreparedRuntimeManifest(
  tag: string,
): Promise<PreparedRuntimeManifest | null> {
  if (!(await assertSafeOutRoot())) return null;

  const runDir = runDirFor(tag);
  if (!(await assertRealDirectory(runDir, "run directory"))) return null;

  const manifestPath = artifactPathFor(tag, "manifest.json");
  const initial = await lstatOrNull(manifestPath);
  if (!initial) return null;
  if (!initial.isFile() || initial.isSymbolicLink()) {
    throw new Error("prepared runtime manifest must be a real regular file");
  }

  const handle = await fs.open(
    manifestPath,
    fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW,
  );
  let bytes: Buffer;
  let opened: Awaited<ReturnType<typeof handle.stat>>;
  try {
    opened = await handle.stat();
    if (!opened.isFile()) {
      throw new Error("prepared runtime manifest must be a real regular file");
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
    throw new Error("prepared runtime manifest changed while it was being read");
  }
  if ((await fs.realpath(runDir)) !== path.resolve(runDir)) {
    throw new Error("run directory changed while its manifest was being read");
  }

  return parsePreparedRuntimeManifest(JSON.parse(bytes.toString("utf8")));
}
