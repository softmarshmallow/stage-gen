// Server-side helpers for reading one run directory under out/.
//
// The shell is a consumer: it locates and validates paths, and never generates.
// Every tag is checked against the producer's one-safe-segment contract, and every
// artifact path is confined to its own run directory before a byte is read.

import { promises as fs } from "node:fs";
import path from "node:path";

export const REPO_ROOT = path.resolve(process.cwd(), "..");
export const OUT_ROOT = process.env.STAGE_GEN_OUT_DIR?.trim()
  ? path.resolve(REPO_ROOT, process.env.STAGE_GEN_OUT_DIR.trim())
  : path.join(REPO_ROOT, "out");

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
  const root = path.resolve(OUT_ROOT);
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
  return assertRealDirectory(OUT_ROOT, "run output root");
}

export async function isRealRunDirectory(tag: string): Promise<boolean> {
  return assertRealDirectory(runDirFor(tag), "run directory");
}
