// One hardened reader for the JSON documents a run directory publishes.
//
// Every run document (manifest.json, execution-view.json) is read the same
// way: confirm the run directory is real, open the file without following
// symlinks, fstat the open handle, read, then lstat the path again and compare
// device and inode so a path swapped mid-read is refused rather than parsed.
// That sequence lives here once; each caller keeps its own strict parser for
// the document it expects, and names itself through the labels so a refusal
// still says which contract was violated.

import { constants as fsConstants, promises as fs } from "node:fs";
import path from "node:path";
import {
  artifactPathFor,
  assertSafeOutRoot,
  isRealRunDirectory,
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

export interface RunDocumentLabels {
  /** Names the file in refusals, e.g. "prepared runtime manifest". */
  readonly label: string;
  /** Names the document in the directory-swap refusal, e.g. "manifest". */
  readonly noun: string;
}

/**
 * Read one run-relative JSON file with the full hardening sequence and return
 * the parsed document, or null when the run or the file does not exist.
 *
 * The document is wrapped rather than returned bare because JSON `null` is a
 * valid document: absent must stay distinguishable from a file whose content
 * parses to null, so each caller's parser still sees exactly what was read.
 */
export async function readRunDocument(
  tag: string,
  filename: string,
  labels: RunDocumentLabels,
): Promise<{ document: unknown } | null> {
  if (!(await assertSafeOutRoot())) return null;
  if (!(await isRealRunDirectory(tag))) return null;

  const filePath = artifactPathFor(tag, filename);
  const initial = await lstatOrNull(filePath);
  if (!initial) return null;
  if (!initial.isFile() || initial.isSymbolicLink()) {
    throw new Error(`${labels.label} must be a real regular file`);
  }

  const handle = await fs.open(
    filePath,
    fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW,
  );
  let bytes: Buffer;
  let opened: Awaited<ReturnType<typeof handle.stat>>;
  try {
    opened = await handle.stat();
    if (!opened.isFile()) {
      throw new Error(`${labels.label} must be a real regular file`);
    }
    bytes = await handle.readFile();
  } finally {
    await handle.close();
  }

  const current = await fs.lstat(filePath);
  if (
    opened.dev !== initial.dev ||
    opened.ino !== initial.ino ||
    current.isSymbolicLink() ||
    !current.isFile() ||
    current.dev !== opened.dev ||
    current.ino !== opened.ino
  ) {
    throw new Error(`${labels.label} changed while it was being read`);
  }
  const runDir = runDirFor(tag);
  if ((await fs.realpath(runDir)) !== path.resolve(runDir)) {
    throw new Error(
      `run directory changed while its ${labels.noun} was being read`,
    );
  }

  return { document: JSON.parse(bytes.toString("utf8")) as unknown };
}
