// Deterministic tag derivation: same prompt -> same tag, every time.
//
// Pure function: no time, no random, no env reads.
// Tag shape: `<slug>-<shorthash>`
//   slug      = lowercased prompt with non-alphanumerics collapsed to '-',
//               trimmed and capped at SLUG_MAX chars.
//   shorthash = first SHORTHASH_LEN hex chars of sha256(prompt).
//
// Used by the orchestrator to pick `out/<tag>/`, and by anything else that
// needs to address a run by its prompt alone.

import { createHash } from "node:crypto";

const SLUG_MAX = 40;
const SHORTHASH_LEN = 8;

export function slugify(prompt: string): string {
  const lower = prompt.toLowerCase();
  // Replace any run of non-alphanumeric chars with a single '-'.
  const collapsed = lower.replace(/[^a-z0-9]+/g, "-");
  // Trim leading/trailing '-'.
  const trimmed = collapsed.replace(/^-+|-+$/g, "");
  if (trimmed.length === 0) return "untitled";
  if (trimmed.length <= SLUG_MAX) return trimmed;
  // Cap at SLUG_MAX, then re-trim trailing '-' that the cut may have created.
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
