// Server-side helpers for reading one run directory under out/.
//
// The shell is a consumer: it locates and validates paths, and never generates.
// Every tag is checked against the producer's one-safe-segment contract, and every
// artifact path is confined to its own run directory before a byte is read.

import { promises as fs, readFileSync } from "node:fs";
import path from "node:path";

const PROJECT_NAME = "stage-gen";

// The `name` of the `[project]` table, read without a TOML parser: the table runs from
// its header to the next header, and the name is one quoted string on its own line.
function projectName(pyproject: string): string | null {
  const table = /^\[project\][ \t]*$([\s\S]*?)(?=^\[|(?![\s\S]))/m.exec(pyproject);
  const name = table && /^name[ \t]*=[ \t]*["']([^"'\n]+)["'][ \t]*$/m.exec(table[1]);
  return name ? name[1] : null;
}

function readOrNull(file: string): string | null {
  try {
    return readFileSync(file, "utf8");
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === "ENOENT" || code === "ENOTDIR" || code === "EISDIR") return null;
    throw error;
  }
}

/**
 * The checkout the viewer reads runs from. `STAGE_GEN_REPO_ROOT` wins when it is set;
 * otherwise the first directory at or above `start` whose pyproject.toml names the
 * `stage-gen` project. The working directory is never assumed to sit one level below
 * it: the viewer is started from web/viewer, its tests from web/.
 */
export function findRepoRoot(
  start: string = process.cwd(),
  env: Readonly<Record<string, string | undefined>> = process.env,
): string {
  const configured = env.STAGE_GEN_REPO_ROOT?.trim();
  if (configured) return path.resolve(configured);
  let directory = path.resolve(start);
  for (;;) {
    const pyproject = readOrNull(path.join(directory, "pyproject.toml"));
    if (pyproject !== null && projectName(pyproject) === PROJECT_NAME) return directory;
    const parent = path.dirname(directory);
    if (parent === directory) {
      throw new Error(
        `no ${PROJECT_NAME} checkout at or above ${path.resolve(start)}; ` +
          "set STAGE_GEN_REPO_ROOT",
      );
    }
    directory = parent;
  }
}

const roots = new Map<string, string>();

/** The run output root, resolved on first use and once per working directory and setting. */
export function outRoot(): string {
  const configured = process.env.STAGE_GEN_OUT_DIR?.trim() ?? "";
  const key = `${process.cwd()}\0${process.env.STAGE_GEN_REPO_ROOT ?? ""}\0${configured}`;
  let root = roots.get(key);
  if (root === undefined) {
    const repository = findRepoRoot();
    root = configured ? path.resolve(repository, configured) : path.join(repository, "out");
    roots.set(key, root);
  }
  return root;
}

// Match the current producer's one-safe-segment contract exactly. Generated prompt tags happen
// to be lower-case, but explicit producer tags may also contain upper-case letters, `_`, or `.`.
const RUN_TAG_MAXIMUM_LENGTH = 128;
const RUN_TAG_PATTERN = new RegExp(
  `^[A-Za-z0-9][A-Za-z0-9._-]{0,${RUN_TAG_MAXIMUM_LENGTH - 1}}$`,
);
const ARTIFACT_SEGMENT_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$/;
function isAlreadyDecoded(value: string): boolean {
  try {
    return decodeURIComponent(value) === value;
  } catch {
    return false;
  }
}

export function isSafeRunTag(tag: string): boolean {
  return isAlreadyDecoded(tag) && tag !== "." && tag !== ".." && RUN_TAG_PATTERN.test(tag);
}

export function assertSafeRunTag(tag: string): void {
  if (!isSafeRunTag(tag)) {
    throw new Error("invalid run tag");
  }
}

export function runDirFor(tag: string): string {
  assertSafeRunTag(tag);
  const root = path.resolve(outRoot());
  const runDir = path.resolve(root, tag);
  if (!runDir.startsWith(`${root}${path.sep}`)) {
    throw new Error("run tag escapes OUT_DIR");
  }
  return runDir;
}

export function artifactPathFor(tag: string, asset: string): string {
  const segments = asset.split("/");
  if (
    !isAlreadyDecoded(asset) ||
    segments.length === 0 ||
    segments.some(
      (segment) =>
        segment === "." ||
        segment === ".." ||
        !ARTIFACT_SEGMENT_PATTERN.test(segment),
    )
  ) {
    throw new Error("invalid artifact path");
  }
  const runDir = runDirFor(tag);
  const target = path.resolve(runDir, ...segments);
  if (!target.startsWith(`${runDir}${path.sep}`)) {
    throw new Error("artifact path escapes run directory");
  }
  return target;
}

async function lstatOrNull(target: string): Promise<Awaited<ReturnType<typeof fs.lstat>> | null> {
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

export async function assertSafeOutRoot(): Promise<boolean> {
  return assertRealDirectory(outRoot(), "run output root");
}

export async function isRealRunDirectory(tag: string): Promise<boolean> {
  return assertRealDirectory(runDirFor(tag), "run directory");
}
