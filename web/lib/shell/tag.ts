// Deterministic tag derivation — mirrors pipeline/src/tag.ts byte-for-byte.
//
// Duplicated (not imported) because pipeline/ is a separate Bun workspace and
// the web bundler cannot pull arbitrary files from outside web/. Both copies
// MUST stay in sync — the slug + sha256 contract is part of the per-tag URL.

import { createHash } from "node:crypto";

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

export function tagFor(prompt: string): string {
  return `${slugify(prompt)}-${shortHash(prompt)}`;
}
