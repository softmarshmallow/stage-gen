// The catalog the site builds from: web/site/.catalog/catalog.json, written by
// `scripts/site.py stage|build` (the export `scripts/catalog.py` writes), plus the page sources that
// script stages beside it under .catalog/pages/. Read once per process, at build time.
//
// Example documents carry run-relative media paths ("media/input.webp"). They are made
// absolute here, before parsing, so every block reads a URL it can put in src= as is:
// /examples/<owner>/<id>/media/<file>, where scripts/site.py copied the file.

import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { parseCatalog, type Catalog } from "@stage-gen/ui/contracts/catalog";
import { exampleMediaBase } from "./media";

/** web/site, found from the working directory whether Next (web/site) or Bun (web/) runs. */
export function siteRoot(): string {
  const override = process.env.SITE_ROOT;
  if (override) return path.resolve(override);
  const cwd = process.cwd();
  for (const candidate of [cwd, path.join(cwd, "site"), path.join(cwd, "web", "site")]) {
    const manifest = path.join(candidate, "package.json");
    if (existsSync(manifest) && JSON.parse(readFileSync(manifest, "utf8")).name === "@stage-gen/site") {
      return candidate;
    }
  }
  throw new Error(`cannot find web/site from ${cwd}; set SITE_ROOT`);
}

export function catalogDir(): string {
  return path.join(siteRoot(), ".catalog");
}

/** A staged page source, by its path under .catalog/pages/ ("workflows/movie-sprite/page.mdx"). */
export function pageSourcePath(relative: string): string {
  return path.join(catalogDir(), "pages", relative);
}

export function readPageSource(relative: string): string | null {
  const file = pageSourcePath(relative);
  return existsSync(file) ? readFileSync(file, "utf8") : null;
}

/** Rewrites every "media/..." string of an example document to its served URL. */
export function absoluteMedia(value: unknown, base: string): unknown {
  if (typeof value === "string") return value.startsWith("media/") ? `${base}/${value}` : value;
  if (Array.isArray(value)) return value.map((entry) => absoluteMedia(entry, base));
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, entry]) => [key, absoluteMedia(entry, base)]),
    );
  }
  return value;
}

type Raw = Record<string, unknown>;

function rewriteMedia(raw: Raw): Raw {
  const workflows = (raw.workflows as Raw[]).map((workflow) => ({
    ...workflow,
    examples: (workflow.examples as Raw[]).map((example) =>
      example.example == null
        ? example
        : {
            ...example,
            example: absoluteMedia(
              example.example,
              exampleMediaBase(workflow.id as string, example.id as string),
            ),
          },
    ),
  }));
  const gameExamples = (raw.game_examples as Raw[]).map((example) => ({
    ...example,
    example: absoluteMedia(
      example.example,
      exampleMediaBase(example.owner as string, example.id as string),
    ),
  }));
  return { ...raw, workflows, game_examples: gameExamples };
}

let cached: Catalog | null = null;

/** The parsed catalog with absolute media URLs; throws with the staging command when absent. */
export function loadCatalog(): Catalog {
  if (cached) return cached;
  const file = path.join(catalogDir(), "catalog.json");
  if (!existsSync(file)) {
    throw new Error(`${file} is missing; run \`uv run python scripts/site.py stage\` first`);
  }
  const raw = JSON.parse(readFileSync(file, "utf8")) as Raw;
  cached = parseCatalog(rewriteMedia(raw));
  return cached;
}

/** Whether the catalog has been staged, for tests that skip without it. */
export function catalogStaged(): boolean {
  try {
    return existsSync(path.join(catalogDir(), "catalog.json"));
  } catch {
    return false;
  }
}
