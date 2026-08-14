// Deterministic base-tag derivation — mirrors stage-gen/src/tag.ts byte-for-byte.
//
// Kept at the adapter boundary so the web bundle does not import headless
// implementation sources. Both copies must stay in sync because slug + hash
// are part of the per-run URL contract.

import { createHash } from "node:crypto";
import type { TransparencyMode } from "./transparency";

const SLUG_MAX = 40;
const SHORTHASH_LEN = 8;

export function slugify(prompt: string): string {
  const lower = prompt.toLowerCase();
  const collapsed = lower.replace(/[^a-z0-9]+/g, "-");
  const trimmed = collapsed.replace(/^-+|-+$/g, "");
  if (trimmed.length === 0) return "untitled";
  if (trimmed.length <= SLUG_MAX) return trimmed;
  return trimmed.slice(0, SLUG_MAX).replace(/-+$/g, "");
}

export function shortHash(prompt: string): string {
  return createHash("sha256")
    .update(prompt, "utf8")
    .digest("hex")
    .slice(0, SHORTHASH_LEN);
}

export function tagFor(prompt: string, transparencyMode: TransparencyMode): string {
  const recipeTag = `${slugify(prompt)}-${shortHash(prompt)}`;
  return `${recipeTag}-${transparencyMode}`;
}
