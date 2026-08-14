import { isAbsolute, resolve, sep } from "node:path";
import { lstat, mkdir, realpath } from "node:fs/promises";

const SAFE_SEGMENT = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

export function assertSafePathSegment(value: string, label: string): string {
  if (!SAFE_SEGMENT.test(value) || value === "." || value === "..") {
    throw new Error(`${label} must be one safe path segment`);
  }
  return value;
}

export function resolveRelativePathWithinRoot(
  rootPath: string,
  requestedPath: string,
  label: string,
): string {
  if (!requestedPath || requestedPath.includes("\0") || isAbsolute(requestedPath)) {
    throw new Error(`${label} must be relative`);
  }
  if (requestedPath.includes("\\")) {
    throw new Error(`${label} contains an invalid path separator`);
  }
  const segments = requestedPath.split("/");
  if (segments.some((segment) => !segment || segment === "." || segment === "..")) {
    throw new Error(`${label} contains an unsafe path segment`);
  }
  const root = resolve(rootPath);
  const output = resolve(root, ...segments);
  if (!output.startsWith(`${root}${sep}`)) throw new Error(`${label} escapes its root`);
  return output;
}

/** Resolve a future output while rejecting symlinked parent directories. */
export async function resolveWritablePathWithinRoot(
  rootPath: string,
  requestedPath: string,
  label: string,
): Promise<string> {
  // Validate before touching the filesystem.
  resolveRelativePathWithinRoot(rootPath, requestedPath, label);
  await mkdir(rootPath, { recursive: true });
  const root = await realpath(rootPath);
  const segments = requestedPath.split("/");
  let parent = root;
  for (const segment of segments.slice(0, -1)) {
    parent = resolve(parent, segment);
    try {
      const stat = await lstat(parent);
      if (stat.isSymbolicLink()) throw new Error(`${label} has a symlinked parent`);
      if (!stat.isDirectory()) throw new Error(`${label} parent is not a directory`);
    } catch (error) {
      if (isMissing(error)) break;
      throw error;
    }
  }
  return resolveRelativePathWithinRoot(root, requestedPath, label);
}

function isMissing(error: unknown): boolean {
  return (
    error !== null &&
    typeof error === "object" &&
    "code" in error &&
    (error as { code?: unknown }).code === "ENOENT"
  );
}
