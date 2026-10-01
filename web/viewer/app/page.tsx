// Home (root URL): every run under every root `stage-gen view` was given, grouped by the
// workflow that made it.
//
// Each installed workflow leads with its title and promise from the catalog and a link
// to its page, where its offline plan and the commands to run it are. Under it, its runs,
// newest first, each with how it stands and when it last changed; the page refreshes
// itself while any run is live. Runs no workflow claims follow: game runs, whose views
// their game exports, and other runs. Generation happens in the headless CLI; nothing on
// this page starts a run, and nothing on it plays one.

import Link from "next/link";
import { runLiveness } from "@stage-gen/ui/contracts/run-view";
import type { CatalogWorkflow } from "@stage-gen/ui/contracts/catalog";
import LiveRefresh from "./LiveRefresh";
import RunList from "./RunList";
import { groupRuns } from "@/lib/run-groups";
import { readCatalog } from "@/lib/shell/catalog";
import { listRuns, type RunIndexEntry } from "@/lib/shell/run-index";
import { runRoots } from "@/lib/shell/runs";
import { cx, errorBanner, h1, linkGhost, metaLine, page } from "./ui";

export const dynamic = "force-dynamic";

function firstRun(workflow: CatalogWorkflow): string | null {
  const commands = workflow.manifest.tryIt?.commands ?? [];
  return commands.find((command) => /(?:^|\s)stage-gen run /.test(command)) ?? commands[0] ?? null;
}

function WorkflowSection({
  workflow,
  runs,
  now,
}: {
  workflow: CatalogWorkflow;
  runs: readonly RunIndexEntry[];
  now: number;
}) {
  const live = runs.filter((entry) => entry.view && runLiveness(entry.view, now) === "running");
  const command = firstRun(workflow);
  return (
    <section id={workflow.id} className="mt-7">
      <div className="mb-2 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="m-0 text-[13px] font-semibold text-fg">
            {workflow.manifest.title}
            <span className="font-normal text-dim">
              {" "}
              · {workflow.id} · {runs.length} run{runs.length === 1 ? "" : "s"}
              {live.length > 0 ? ` · ${live.length} running` : ""}
            </span>
          </h2>
          <p className="m-0 mt-0.5 text-xs text-dim">{workflow.manifest.promise}</p>
        </div>
        <Link className={cx(linkGhost, "shrink-0")} href={`/workflows/${workflow.id}`}>
          [ ⌕ plan &amp; commands ]
        </Link>
      </div>
      {runs.length > 0 ? (
        <RunList runs={runs} now={now} />
      ) : (
        <p className={cx(metaLine, "border-t border-border pt-1.5")}>
          No runs under these roots yet.
          {command ? (
            <>
              {" "}
              Try <code className="text-fg">{command}</code>
            </>
          ) : null}
        </p>
      )}
    </section>
  );
}

function UnclaimedSection({
  title,
  note,
  runs,
  game = false,
  now,
}: {
  title: string;
  note: string;
  runs: readonly RunIndexEntry[];
  game?: boolean;
  now: number;
}) {
  if (runs.length === 0) return null;
  return (
    <details className="mt-7">
      <summary className="cursor-pointer text-[13px] font-semibold text-fg">
        {title}
        <span className="font-normal text-dim"> · {runs.length}</span>
      </summary>
      <p className={cx(metaLine, "mt-1")}>{note}</p>
      <RunList runs={runs} game={game} now={now} />
    </details>
  );
}

export default async function Home() {
  const [runs, catalogRead] = await Promise.all([listRuns(), readCatalog()]);
  const roots = runRoots();
  const groups = groupRuns(runs, catalogRead.catalog);
  // One clock for the whole page, read on the server: liveness is a judgement about
  // right now, but it must be the same "now" for every row.
  const now = Date.now();
  const live = runs.some((entry) => entry.view && runLiveness(entry.view, now) === "running");
  return (
    <main className={page}>
      <LiveRefresh live={live} />
      <h1 className={h1}>stage-gen</h1>
      <p className={metaLine}>
        the local viewer · {runs.length} run{runs.length === 1 ? "" : "s"} under{" "}
        {roots.map((root, index) => (
          <span key={root.key}>
            {index > 0 ? ", " : ""}
            <code title={root.dir}>{root.label}</code>
          </span>
        ))}{" "}
        · read-only: nothing here starts a run
        {live ? " · refreshing while a run is live" : ""}
      </p>
      {catalogRead.refusal !== null ? (
        <p className={errorBanner}>{catalogRead.refusal}</p>
      ) : catalogRead.catalog === null ? (
        <p className={metaLine}>
          No catalog, so runs are not grouped by workflow. Start the viewer with{" "}
          <code>stage-gen view</code>.
        </p>
      ) : null}
      {groups.workflows.map(({ workflow, runs: owned }) => (
        <WorkflowSection key={workflow.id} workflow={workflow} runs={owned} now={now} />
      ))}
      <UnclaimedSection
        title="Game runs"
        note="Made inside an example game. A game exports its own run views: demo-games export-view --run DIR."
        runs={groups.game}
        game
        now={now}
      />
      <UnclaimedSection
        title="Other runs"
        note="Runs no installed workflow claims: your own SDK pipelines, calibrations, and runs an older build wrote."
        runs={groups.other}
        now={now}
      />
    </main>
  );
}
