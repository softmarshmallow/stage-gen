// The page shell of every workflow, example and game page: the port of the retired
// showcase's page template. The sticky header with the breadcrumb and the overview/graph
// switch, the overview (title, promise, related links, body, footer), the graph view with
// its toolbar, viewport and stage, and the node drawer. The scripts the template inlined are
// the players: the graph view is <GraphPlayer>, given the drawer data, and each block renders
// its own player's root.

import { Fragment, type ReactElement, type ReactNode } from "react";
import NodeGraph from "@/blocks/NodeGraph";
import { drawerData } from "@/blocks/drawer";
import { href } from "@/lib/media";
import type { Page } from "@/lib/page";
import ModelViewer from "./ModelViewer";
import GraphPlayer from "./players/GraphPlayer";

/** Whether a page shows a 3D model, so it loads <model-viewer>. */
export function showsModel(page: Page): boolean {
  return (
    page.hasExample && Object.values(page.record.outputs).some((output) => output.kind === "model")
  );
}

/** A line under the promise naming the pages this one points to (related_links). */
function Related({ page }: { page: Page }): ReactElement | null {
  const links = page.data.related;
  if (links.length === 0) return null;
  return (
    <p className="mt-4 text-sm text-zinc-500">
      See also:{" "}
      {links.map((link, index) => (
        <Fragment key={link.href}>
          {index > 0 ? ", " : null}
          <a
            className="underline decoration-zinc-300 underline-offset-2 hover:text-zinc-900 dark:hover:text-zinc-100"
            href={link.href}
          >
            {link.title}
          </a>
        </Fragment>
      ))}
    </p>
  );
}

/**
 * The production notes, behind a disclosure (amendment A5): reader pages carry no status
 * borders, and an example made with an earlier version of its workflow says so only here.
 * Nothing shows for a current example.
 */
function ProductionNotes({ page }: { page: Page }): ReactElement | null {
  if (page.data.currency !== "earlier_version") return null;
  return (
    <details className="mt-3">
      <summary className="cursor-pointer select-none hover:text-zinc-900 dark:hover:text-zinc-100">
        Production notes
      </summary>
      <p className="mt-2 leading-relaxed">
        Made with an earlier version of Stage Gen. The node graph shows the nodes its run had.
      </p>
    </details>
  );
}

// Runs before the body paints, as the old page script did at the end of the body: a page opened
// at #graph… shows the graph view from its first paint (globals.css reads data-view), and the
// graph player clears the attribute when it takes over. The predicate is route()'s.
const FIRST_VIEW = `if(location.hash.slice(1).startsWith("graph"))document.documentElement.dataset.view="graph"`;

const VIEW_BUTTON =
  "border-b-2 border-transparent px-3 text-zinc-500 aria-pressed:border-zinc-900 aria-pressed:text-zinc-900 dark:aria-pressed:border-zinc-100 dark:aria-pressed:text-zinc-100";

export default function PageShell({ page, body }: { page: Page; body: ReactNode }): ReactElement {
  const title = page.data.title;
  // A workflow without an example has no run to draw: no node graph, no view switch, no drawer.
  const graph = page.hasExample;
  const nodes = JSON.stringify(graph ? drawerData(page) : {});
  return (
    <>
      {graph ? <script dangerouslySetInnerHTML={{ __html: FIRST_VIEW }} /> : null}
      <header className="sticky top-0 z-20 border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
          <nav className="flex items-center gap-2 text-sm text-zinc-500">
            <a className="hover:text-zinc-900 dark:hover:text-zinc-100" href={href("/")}>
              Stage Gen
            </a>{" "}
            <span>/</span>
            <span className="text-zinc-900 dark:text-zinc-100">{title}</span>
          </nav>
          <div className="flex h-full items-center gap-4 text-sm">
            {graph ? (
              <div className="flex h-full" role="group" aria-label="View">
                <button id="to-overview" aria-pressed="true" className={VIEW_BUTTON}>
                  Overview
                </button>{" "}
                <button id="to-graph" aria-pressed="false" className={VIEW_BUTTON}>
                  Node graph
                </button>
              </div>
            ) : null}
            <a className="text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100" href={href("/docs/")}>
              Docs
            </a>
          </div>
        </div>
      </header>

      <main id="overview" className="mx-auto max-w-6xl px-6 pb-16 pt-12">
        <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-2 text-lg text-zinc-600 dark:text-zinc-400">{page.data.promise}</p>
        <Related page={page} />
        {body}
        {page.data.footer === null ? null : (
          <footer className="mt-16 border-t border-zinc-200 pt-6 text-sm text-zinc-500 dark:border-zinc-800">
            {page.data.footer}
            <ProductionNotes page={page} />
          </footer>
        )}
      </main>

      {graph ? (
      <GraphPlayer nodes={nodes} className="hidden">
        <div className="flex items-center justify-between border-b border-zinc-200 px-6 py-2.5 text-xs text-zinc-500 dark:border-zinc-800">
          <div className="flex flex-wrap items-center gap-5">
            <span className="flex items-center gap-2">
              <i className="inline-block h-3 w-4 rounded-sm border border-zinc-300"></i>ran
            </span>
            <span className="flex items-center gap-2">
              <i className="inline-block h-3 w-4 rounded-sm border border-dashed border-zinc-400"></i>planned, not needed
            </span>
            <span>Click a node to open its record. Scroll or drag to pan, pinch to zoom.</span>
          </div>
          <div className="flex items-center gap-1">
            <span id="zpct" className="w-10 pr-1 text-right tabular-nums"></span>
            <button id="zout" title="Zoom out" className="size-7 rounded-sm border border-zinc-300 hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-900">
              −
            </button>
            <button id="zfit" title="Fit" className="h-7 rounded-sm border border-zinc-300 px-2 hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-900">
              fit
            </button>
            <button id="zin" title="Zoom in" className="size-7 rounded-sm border border-zinc-300 hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-900">
              +
            </button>
          </div>
        </div>
        <div
          id="vp"
          className="relative h-[calc(100vh-6.5rem)] cursor-grab touch-none select-none overflow-clip overscroll-none bg-zinc-50 bg-[radial-gradient(circle,#d4d4d8_1px,transparent_1px)] dark:bg-zinc-900 dark:bg-[radial-gradient(circle,#3f3f46_1px,transparent_1px)]"
        >
          <div id="stage" className="absolute left-0 top-0 flex w-[2280px] origin-top-left flex-wrap items-start gap-x-10 gap-y-14 p-10">
            <svg id="edges" className="pointer-events-none absolute left-0 top-0 z-[1] overflow-visible text-zinc-900 dark:text-zinc-100"></svg>
            <NodeGraph page={page} />
          </div>
        </div>
      </GraphPlayer>
      ) : null}

      {graph ? (
      <aside
        id="drawer"
        className="fixed inset-y-0 right-0 z-30 w-[min(440px,92vw)] translate-x-full overflow-y-auto border-l border-zinc-200 bg-white px-6 pb-10 pt-5 transition-transform dark:border-zinc-800 dark:bg-zinc-950"
      >
        <button id="dx" aria-label="Close" className="absolute right-4 top-3 text-xl text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100">
          ×
        </button>
        <div id="dbody"></div>
      </aside>
      ) : null}

      {showsModel(page) ? <ModelViewer /> : null}
    </>
  );
}
