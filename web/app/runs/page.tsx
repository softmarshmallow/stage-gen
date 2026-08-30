// Read-only run list: every run under out/ that carries an execution view.
// A run without one is exported on demand: stage-gen export-view --run out/<tag>.

import Link from "next/link";
import { cx, h1, metaLine, page } from "@/app/ui";
import {
  type ExecutionRunLiveness,
  RUN_LIVENESS_LABELS,
  runLiveness,
} from "@/lib/runtime/execution-view";
import {
  type ExecutionViewRunListEntry,
  listExecutionViewRuns,
} from "@/lib/shell/execution-view";

export const dynamic = "force-dynamic";

const BADGES: Record<ExecutionRunLiveness, string> = {
  planned: "border-dim text-dim",
  running: "border-fg text-fg",
  // Started and then abandoned: distinct from a run that is still going, and
  // distinct again from one that failed on its own terms.
  interrupted: "border-dim text-dim",
  canceled: "border-dim text-dim",
  succeeded: "border-accent text-accent",
  failed: "border-error text-error",
};

function badge(
  entry: ExecutionViewRunListEntry,
  now: number,
): { label: string; className: string } {
  if (entry.unreadable || entry.runState === null) {
    return { label: "re-export", className: "border-error text-error" };
  }
  const liveness = runLiveness(
    { runState: entry.runState, traceModifiedAt: entry.traceModifiedAt },
    now,
  );
  return { label: RUN_LIVENESS_LABELS[liveness], className: BADGES[liveness] };
}

function states(entry: ExecutionViewRunListEntry): string {
  const counts = entry.stateCounts;
  if (!counts) return "";
  const parts = [
    counts.succeeded ? `${counts.succeeded}✓` : null,
    counts.running ? `${counts.running}▸` : null,
    counts.pending ? `${counts.pending}·` : null,
    counts.failed ? `${counts.failed}✗` : null,
    counts.skipped ? `${counts.skipped}∅` : null,
  ];
  return parts.filter(Boolean).join(" ");
}

function duration(entry: ExecutionViewRunListEntry): string {
  if (entry.durationMs === null) return "";
  const seconds = entry.durationMs / 1000;
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  return `${Math.floor(seconds / 60)}m ${String(Math.round(seconds % 60)).padStart(2, "0")}s`;
}

export default async function RunsPage() {
  const runs = await listExecutionViewRuns();
  // One clock for the whole list, read on the server: liveness is a judgement
  // about right now, but it must be the same "now" for every row.
  const now = Date.now();
  return (
    <main className={page}>
      <p className={metaLine}>
        <Link className="text-dim no-underline hover:text-accent" href="/">
          ← stage-gen
        </Link>
      </p>
      <h1 className={h1}>Runs</h1>
      <p className={metaLine}>
        {runs.length} run{runs.length === 1 ? "" : "s"} with an execution view · derive one with
        `stage-gen export-view --run out/&lt;tag&gt;`
      </p>
      {runs.length === 0 ? (
        <p className="text-dim">
          No execution views found under out/. Export one, then reload.
        </p>
      ) : (
        <ol className="m-0 list-none border-t border-border">
          {runs.map((entry) => {
            const mark = badge(entry, now);
            return (
              <li key={entry.tag}>
                <Link
                  className="grid grid-cols-[minmax(0,1fr)_auto_auto_auto_auto] items-baseline gap-x-4 border-b border-border px-2 py-2 text-fg no-underline hover:bg-hover max-[700px]:grid-cols-[minmax(0,1fr)_auto]"
                  href={`/runs/${encodeURIComponent(entry.tag)}`}
                >
                  <span className="truncate">
                    {entry.tag}
                    {entry.gameId ? (
                      <span className="ml-2 text-xs text-dim">{entry.gameId}</span>
                    ) : null}
                  </span>
                  <span className="text-xs text-dim max-[700px]:hidden">{states(entry)}</span>
                  <span className="text-xs text-dim max-[700px]:hidden">
                    {entry.nodeCount ? `${entry.nodeCount} nodes` : ""}
                  </span>
                  <span className="text-xs text-dim max-[700px]:hidden">{duration(entry)}</span>
                  <span className={cx("border px-1.5 py-0.5 text-xs", mark.className)}>
                    {mark.label}
                  </span>
                </Link>
              </li>
            );
          })}
        </ol>
      )}
    </main>
  );
}
