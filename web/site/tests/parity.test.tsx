// Parity with the showcase, element by element. Skipped unless SITE_REFERENCE names the
// reference the showcase rendered (local/refactor/site/dump_reference.py), so CI stays green.
//
//   SITE_REFERENCE=$PWD/local/refactor/site/reference bun test --cwd web/site tests/parity.test.tsx
//
// For each of the eight pages it compiles the page source through the site's own pipeline
// (lib/mdx.ts, bound to the page lib/pages.ts builds), renders every top-level element on
// its own with renderToStaticMarkup, and compares it with the showcase's fragment for the
// same element after tests/html.ts normalisation. It also compares the node graph section
// (NodeGraph), the drawer data (Drawer) and the landing's cards (Landing).
//
// Filters, comma separated:
//   SITE_PARITY_COMPONENTS=Painter,Compare   only these names (components, h2/h3/p/ul/pre,
//                                            NodeGraph, Drawer, Shell, Landing)
//   SITE_PARITY_PAGES=terrain-tiles          only these showcase slugs
// With no component filter the element count and order are checked too.

import { describe, test } from "bun:test";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { createElement, type ReactElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import NodeGraph from "@/blocks/NodeGraph";
import { drawerData } from "@/blocks/drawer";
import { blockName, nodesOf } from "@/blocks/shared";
import { Cards } from "@/components/Landing";
import PageShell from "@/components/PageShell";
import { catalogStaged } from "@/lib/catalog";
import { compileSource, makeComponents, pageSource } from "@/lib/mdx";
import { landingCards, pageForExample } from "@/lib/pages";
import { compactDiff, normalize, reduceMedia } from "./html";

const REFERENCE = process.env.SITE_REFERENCE ? path.resolve(process.env.SITE_REFERENCE) : null;
const listOf = (value: string | undefined) =>
  new Set((value ?? "").split(",").map((entry) => entry.trim()).filter(Boolean));
const COMPONENTS = listOf(process.env.SITE_PARITY_COMPONENTS);
const PAGES = listOf(process.env.SITE_PARITY_PAGES);
const wanted = (name: string) => COMPONENTS.size === 0 || COMPONENTS.has(name);

interface ReferencePage {
  readonly slug: string;
  readonly owner: string;
  readonly example: string;
  readonly title: string;
  readonly elements: readonly string[];
}

const ready = REFERENCE !== null && existsSync(path.join(REFERENCE, "index.json")) && catalogStaged();
if (REFERENCE !== null && !ready) {
  console.warn(
    `parity: skipped; ${REFERENCE}/index.json or the staged catalog is missing ` +
      "(run local/refactor/site/dump_reference.py and `uv run python scripts/site.py stage`)",
  );
}
const index: ReferencePage[] = ready
  ? (JSON.parse(readFileSync(path.join(REFERENCE as string, "index.json"), "utf8")) as ReferencePage[])
  : [];

function read(...parts: string[]): string {
  return readFileSync(path.join(REFERENCE as string, ...parts), "utf8");
}

/** Renders one node, or reports what it threw. */
function render(node: ReactNode): { html: string } | { error: string } {
  try {
    return { html: renderToStaticMarkup(node) };
  } catch (error) {
    return { error: error instanceof Error ? error.message : String(error) };
  }
}

let compared = 0;

function compare(label: string, expected: string, node: ReactNode, failures: string[]): void {
  compared += 1;
  const result = render(node);
  if ("error" in result) {
    failures.push(`${label}: throws: ${result.error}`);
    return;
  }
  const diff = compactDiff(normalize(expected), normalize(result.html));
  if (diff !== null) failures.push(`${label}: ${diff}`);
}

/** Pretty, key-sorted JSON lines with media reduced, so two drawer documents diff by line. */
function jsonLines(value: unknown): string[] {
  const sort = (entry: unknown): unknown =>
    Array.isArray(entry)
      ? entry.map(sort)
      : entry !== null && typeof entry === "object"
        ? Object.fromEntries(
            Object.entries(entry as Record<string, unknown>)
              .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
              .map(([key, inner]) => [key, sort(inner)]),
          )
        : entry;
  return reduceMedia(JSON.stringify(sort(value), null, 1)).split("\n");
}

// Two differences in the node graph come from the new data model, not from a port:
// - The showcase's stages held several rows of cards; the catalog's steps are flat, so each
//   stage is one row. The graph player turns every row into `display: contents` before ELK
//   places the cards, so the rows never reach the screen; the reference's rows are merged.
// - character-3d's steps are the workflow's own (workflow.py), written in S5 to describe every
//   path of the workflow, where the showcase's front matter described the cover run alone.
const ROW_BREAK = '</div><div class="mt-4 flex items-start gap-5 first-of-type:mt-0">';
const WORKFLOW_NOTES: Readonly<Record<string, readonly (readonly [string, string])[]>> = {
  "character-3d": [
    [
      "renders five views in the matte finish the export will wear.</p>",
      "renders five views in the matte finish the export will wear. Supplied part meshes are converted and measured as they arrived.</p>",
    ],
    [
      "measured, and reviewed again.</p>",
      "measured, and reviewed again. Without review, the exported assembly is selected instead.</p>",
    ],
    [
      "Tripo adds bones and weights. The worker proves the rigged mesh is still the admitted mesh, bakes six diagnostic clips and exports at profile height. The reviewer sees one labelled atlas per pose.</p>",
      "Tripo adds bones and weights, or an agent locates the joints and binds the skin. The worker proves the rigged mesh is still the admitted mesh, bakes diagnostic clips and exports at profile height. A rig-only run starts from an admitted assembly, verified and measured first.</p>",
    ],
    [
      "a clean report cannot waive a visible one.</p>",
      "a clean report cannot waive a visible one. A run without review selects the intact export instead.</p>",
    ],
  ],
};

function referenceGraph(slug: string): string {
  let html = read(slug, "graph.html").replaceAll(ROW_BREAK, "");
  for (const [before, after] of WORKFLOW_NOTES[slug] ?? []) {
    if (!html.includes(before)) throw new Error(`${slug} graph.html no longer holds the note ${before}`);
    html = html.replace(before, after);
  }
  return html;
}

// The page shell (header.html, head.html, footer.html) differs from the showcase in two
// data-model ways: "See also" links that workflow.toml or a game entry's `related` now
// declares where the showcase's front matter had none, and the production notes of an
// example made with an earlier version, behind a disclosure in the footer (amendment A5).
// The parts page's route is new as well, as on the landing.
const NEW_RELATED: Readonly<Record<string, readonly string[]>> = {
  "movie-sprite": ["Portrait motion"],
  "portrait-motion": ["Movie sprite"],
  "parallax-backgrounds": ["Looping parallax"],
};

function between(html: string, start: string, end: string): string {
  const from = html.indexOf(start);
  const to = html.indexOf(end, from);
  if (from < 0 || to < 0) throw new Error(`the shell has no ${start}...${end}`);
  return html.slice(from, to + end.length);
}

function shellParts(slug: string, shell: string): Record<"header" | "head" | "footer", string> {
  const html = shell.replaceAll('href="/workflows/character-3d/tavi-parts/"', 'href="character-3d-parts/index.html"');
  let head = between(html, "<h1", "</p>");
  const after = html.slice(html.indexOf(head) + head.length);
  const related = /^<p class="mt-4 text-sm text-zinc-500">See also:.*?<\/p>/.exec(after)?.[0] ?? "";
  const titles = [...related.matchAll(/>([^<]+)<\/a>/g)].map((match) => match[1]);
  const declared = NEW_RELATED[slug];
  if (declared === undefined || titles.join(",") !== declared.join(",")) head += related;
  return {
    header: between(html, "<header", "</header>"),
    head,
    footer: between(html, "<footer", "</footer>").replace(/<details[^]*?<\/details>/, ""),
  };
}

function report(failures: string[]): void {
  if (failures.length > 0) {
    throw new Error(`${failures.length} mismatch(es)\n\n${failures.join("\n\n")}`);
  }
}

describe.skipIf(!ready)("parity with the showcase", () => {
  for (const reference of index) {
    if (PAGES.size > 0 && !PAGES.has(reference.slug)) continue;

    test(reference.slug, async () => {
      const page = pageForExample(reference.owner, reference.example);
      const failures: string[] = [];
      compared = 0;

      // The body: every top-level element captured by the MDX wrapper, then rendered alone.
      let captured: ReactNode[] = [];
      const Content = await compileSource(pageSource(page.data.source));
      // MDX hands its wrapper the unrendered body component; calling it gives the fragment
      // of top-level elements, each already bound to this page's components.
      const Capture = ({ children }: { children?: ReactNode }) => {
        const body = children as ReactElement<Record<string, unknown>, (props: object) => ReactElement<{ children?: ReactNode }>>;
        captured = nodesOf(body.type(body.props).props.children);
        return null;
      };
      renderToStaticMarkup(createElement(Content, { components: { ...makeComponents(page), wrapper: Capture } }));
      const names = captured.map((node) => blockName(node) ?? "?");
      if (COMPONENTS.size === 0) {
        const expected = reference.elements.map((stem) => stem.slice(3));
        if (expected.join(",") !== names.join(",")) {
          failures.push(
            `${reference.slug} elements: the showcase had ${expected.length} (${expected.join(", ")}), ` +
              `the site has ${names.length} (${names.join(", ")})`,
          );
        }
      }
      reference.elements.forEach((stem, position) => {
        const name = stem.slice(3);
        if (!wanted(name)) return;
        const node = captured[position];
        if (node === undefined || names[position] !== name) {
          failures.push(`${reference.slug} ${stem}: the site has ${names[position] ?? "nothing"} here`);
          return;
        }
        compare(`${reference.slug} ${stem}`, read(reference.slug, `${stem}.html`), node, failures);
      });

      if (wanted("NodeGraph")) {
        compare(`${reference.slug} NodeGraph`, referenceGraph(reference.slug), createElement(NodeGraph, { page }), failures);
      }
      if (wanted("Shell")) {
        const shell = render(createElement(PageShell, { page, body: null }));
        if ("error" in shell) failures.push(`${reference.slug} Shell: throws: ${shell.error}`);
        else {
          const parts = shellParts(reference.slug, shell.html);
          for (const part of ["header", "head", "footer"] as const) {
            compared += 1;
            const diff = compactDiff(normalize(read(reference.slug, `${part}.html`)), normalize(parts[part]));
            if (diff !== null) failures.push(`${reference.slug} ${part}: ${diff}`);
          }
        }
      }
      if (wanted("Drawer")) {
        try {
          const diff = compactDiff(jsonLines(JSON.parse(read(reference.slug, "drawer.json"))), jsonLines(drawerData(page)));
          if (diff !== null) failures.push(`${reference.slug} Drawer: ${diff}`);
        } catch (error) {
          failures.push(`${reference.slug} Drawer: throws: ${error instanceof Error ? error.message : String(error)}`);
        }
        compared += 1;
      }
      console.log(`${reference.slug}: ${compared - failures.length} of ${compared} compared match`);
      report(failures);
    });
  }

  if (wanted("Landing") && PAGES.size === 0) {
    test("landing", () => {
      const failures: string[] = [];
      // Two differences are the new data model's, not regressions: each game-made card's
      // "Made inside ..." line (amendment A1), and the parts page's new route.
      const site = renderToStaticMarkup(createElement(Cards, { cards: landingCards() }))
        .replace(/<p[^>]*>Made inside the [^<]* example game<\/p>/g, "")
        .replace('href="/workflows/character-3d/tavi-parts/"', 'href="character-3d-parts/index.html"');
      const diff = compactDiff(normalize(read("landing.html")), normalize(site));
      if (diff !== null) failures.push(`landing: ${diff}`);
      report(failures);
    });
  }
});
