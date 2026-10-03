// Server-side reader for the catalog `gnode view` exported before it started.
//
// The catalog says what every installed workflow is: its title and promise, its steps,
// the identities its runs carry and the graph it plans offline. The viewer groups runs
// by it and draws each workflow's plan from it; it never plans anything itself. Started
// without `gnode view`, the viewer has no catalog and lists every run ungrouped.

import { promises as fs } from "node:fs";
import { type Catalog, parseCatalog } from "@stage-gen/ui/contracts/catalog";
import { catalogPath } from "./runs";

export type CatalogRead =
  | { readonly catalog: Catalog; readonly refusal: null }
  | { readonly catalog: null; readonly refusal: string | null };

let memo: { readonly file: string; readonly mtimeMs: number; readonly read: CatalogRead } | null =
  null;

/** The parsed catalog; `refusal` says why there is none when one was configured. */
export async function readCatalog(): Promise<CatalogRead> {
  const file = catalogPath();
  if (file === null) return { catalog: null, refusal: null };
  let mtimeMs: number;
  try {
    const stat = await fs.stat(file);
    mtimeMs = stat.mtimeMs;
  } catch {
    return { catalog: null, refusal: `no catalog at ${file}; restart gnode view` };
  }
  if (memo !== null && memo.file === file && memo.mtimeMs === mtimeMs) return memo.read;
  let read: CatalogRead;
  try {
    read = {
      catalog: parseCatalog(JSON.parse(await fs.readFile(file, "utf8")) as unknown),
      refusal: null,
    };
  } catch (error) {
    read = { catalog: null, refusal: error instanceof Error ? error.message : String(error) };
  }
  memo = { file, mtimeMs, read };
  return read;
}
