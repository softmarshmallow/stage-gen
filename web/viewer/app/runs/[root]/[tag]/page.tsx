// One run. What it renders depends on what the run carries:
//
// - a universe gallery is shown as the reader would see it, with the run's graph one
//   link away (`?view=graph`);
// - otherwise its execution view — the run's own, or the one `stage-gen view` derived
//   into the cache — fills the window as a graph, and refreshes while the run is live;
// - a run with neither says what its own record says and how a view is made. A game
//   run's view is exported by its game; the viewer never derives one.
//
// A document this build refuses (hard-drop versioning) gets the re-derive message
// instead of a migration.

import Link from "next/link";
import { notFound } from "next/navigation";
import { errorBanner, h1, metaLine, page } from "@/app/ui";
import LiveRefresh from "@/app/LiveRefresh";
import { runLiveness } from "@stage-gen/ui/contracts/run-view";
import { type CatalogWorkflow, findWorkflow } from "@stage-gen/ui/contracts/catalog";
import { isGameRun, workflowOf } from "@/lib/run-groups";
import { buildEntityCards, presentClasses, tallyReviewChecks } from "@/lib/universe/gallery-view";
import { readCatalog } from "@/lib/shell/catalog";
import { type ReadView, readExecutionView } from "@/lib/shell/execution-view";
import { readRunEntry, type RunIndexEntry } from "@/lib/shell/run-index";
import { type RunRef, relativeOf } from "@/lib/shell/run-ref";
import { isRealRunDirectory, isSafeRunTag, rootFor, runDirFor } from "@/lib/shell/runs";
import { readUniverseGallery, type UniverseGallery } from "@/lib/shell/universe";
import RunViewer from "./RunViewer";
import UniverseViewer from "./UniverseViewer";

export const dynamic = "force-dynamic";

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function Refused({ run, refusal }: { run: RunRef; refusal: string }) {
  return (
    <main className={page}>
      <p className={metaLine}>
        <Link className="text-dim no-underline hover:text-accent" href="/">
          ← runs
        </Link>
      </p>
      <h1 className={h1}>{relativeOf(run.tag)}</h1>
      <p className={errorBanner}>{refusal}</p>
    </main>
  );
}

interface NoViewFacts {
  readonly run: RunRef;
  readonly runDir: string;
  readonly rootLabel: string;
  readonly entry: RunIndexEntry | null;
  readonly workflow: CatalogWorkflow | null;
  readonly game: boolean;
}

/** What a run without a view is: its root, its workflow or a game, its own record. */
async function noViewFacts(run: RunRef, runDir: string): Promise<NoViewFacts> {
  const root = rootFor(run.root);
  const entry = root
    ? await readRunEntry({ run, root, relative: relativeOf(run.tag), dir: runDir })
    : null;
  const { catalog } = await readCatalog();
  const workflowId = entry && catalog ? workflowOf(entry.identity, catalog) : null;
  const workflow = workflowId && catalog ? findWorkflow(catalog, workflowId) : null;
  return {
    run,
    runDir,
    rootLabel: root?.label ?? run.root,
    entry,
    workflow,
    game: entry !== null && workflow === null && isGameRun(entry.identity),
  };
}

/** A run with no view: what its own record says, and where a view comes from. */
function NoView({ run, runDir, rootLabel, entry, workflow, game }: NoViewFacts) {
  return (
    <main className={page}>
      <p className={metaLine}>
        <Link className="text-dim no-underline hover:text-accent" href="/">
          ← runs
        </Link>
      </p>
      <h1 className={h1}>{relativeOf(run.tag)}</h1>
      <p className={metaLine}>
        {rootLabel} · {workflow ? workflow.manifest.title : game ? "game run" : "other run"}
        {entry?.identity.kind ? ` · ${entry.identity.kind}` : ""}
        {entry?.recordState ? ` · ${entry.recordState}` : ""}
      </p>
      {entry?.viewRefusal ? <p className={errorBanner}>{entry.viewRefusal}</p> : null}
      {game ? (
        <p className="text-dim">
          View not exported. A game exports its own run view:{" "}
          <code>demo-games export-view --run {runDir}</code>
        </p>
      ) : (
        <p className="text-dim">
          This run has no view yet. While it runs, <code>stage-gen view</code> derives one
          into its cache whenever the run&apos;s plan and trace can be joined; a run prepared
          but never run, or one whose trace is missing, keeps only its own record. Write one
          with <code>stage-gen inspect {runDir} --write-view DIR</code>.
        </p>
      )}
      {workflow ? (
        <p className="mt-3">
          <Link className="text-dim hover:text-accent" href={`/workflows/${workflow.id}`}>
            {workflow.manifest.title}: plan and commands
          </Link>
        </p>
      ) : null}
    </main>
  );
}

export default async function RunPage({
  params,
  searchParams,
}: {
  params: Promise<{ root: string; tag: string }>;
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { root, tag } = await params;
  if (!isSafeRunTag(tag) || rootFor(root) === null) notFound();
  const run: RunRef = { root, tag };
  if (!(await isRealRunDirectory(run))) notFound();
  const runDir = runDirFor(run);
  const graphOnly = (await searchParams)?.view === "graph";

  if (!graphOnly) {
    let gallery: UniverseGallery | null = null;
    try {
      gallery = await readUniverseGallery(run);
    } catch (error) {
      return <Refused run={run} refusal={message(error)} />;
    }
    if (gallery !== null) {
      const cards = buildEntityCards(gallery.manifest, gallery.universe, gallery.records);
      return (
        <UniverseViewer
          run={run}
          manifest={gallery.manifest}
          universe={gallery.universe}
          cards={cards}
          classes={presentClasses(cards)}
          tallies={tallyReviewChecks(cards)}
          unreadableRecords={gallery.unreadableRecords}
          hasExecutionView={gallery.hasExecutionView}
        />
      );
    }
  }

  let read: ReadView | null = null;
  try {
    read = await readExecutionView(run);
  } catch (error) {
    return <Refused run={run} refusal={message(error)} />;
  }
  if (read === null) {
    if (graphOnly) {
      return <Refused run={run} refusal="this run has no execution view to draw" />;
    }
    return <NoView {...await noViewFacts(run, runDir)} />;
  }

  const liveness = runLiveness(read.view, Date.now());
  // Full-bleed: the graph is the page, and the viewer floats its own chrome.
  return (
    <main className="fixed inset-0 overflow-hidden bg-bg">
      <LiveRefresh live={liveness === "running"} />
      <RunViewer run={run} view={read.view} liveness={liveness} />
    </main>
  );
}
