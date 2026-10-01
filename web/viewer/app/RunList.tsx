// The run rows the home page and a workflow page list: each run's name, what it is,
// how it stands, its node states and when it last changed. A run's badge is its view's
// liveness when it has a view; otherwise what its own record says, or, for a game run,
// that its game has not exported a view.

import Link from "next/link";
import {
  type ExecutionRunLiveness,
  RUN_LIVENESS_LABELS,
  runLiveness,
} from "@stage-gen/ui/contracts/run-view";
import { ago } from "@/lib/ago";
import type { RunIndexEntry } from "@/lib/shell/run-index";
import { runHref } from "@/lib/shell/run-ref";
import { cx, linkGhost } from "./ui";

/** How many of a group's runs show before the rest fold away. */
const VISIBLE_RUNS = 8;

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

interface Badge {
  readonly label: string;
  readonly className: string;
}

function badge(entry: RunIndexEntry, game: boolean, now: number): Badge {
  if (entry.view !== null) {
    const liveness = runLiveness(entry.view, now);
    return { label: RUN_LIVENESS_LABELS[liveness], className: BADGES[liveness] };
  }
  if (entry.viewRefusal !== null) return { label: "re-derive", className: "border-error text-error" };
  if (game) return { label: "view not exported", className: "border-border text-dim" };
  return { label: entry.recordState ?? "no view", className: "border-border text-dim" };
}

function states(entry: RunIndexEntry): string {
  const counts = entry.view?.stateCounts;
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

/** What a run says it is, for the reader: its label, its kind, or its record. */
function identity(entry: RunIndexEntry): string {
  const parts = [entry.view?.label ?? null, entry.identity.kind ?? entry.view?.kind ?? null];
  if (entry.view === null && entry.recordState) parts.push(entry.recordState);
  return parts.filter((part, index) => part && parts.indexOf(part) === index).join(" · ");
}

function RunRow({ entry, game, now }: { entry: RunIndexEntry; game: boolean; now: number }) {
  const mark = badge(entry, game, now);
  return (
    <li className="grid grid-cols-[minmax(0,1fr)_auto_auto_auto] items-center gap-x-4 border-b border-border px-2 py-1.5 hover:bg-hover max-[700px]:grid-cols-[minmax(0,1fr)_auto]">
      <div className="min-w-0">
        <Link className="block truncate text-[13px] text-fg no-underline hover:text-accent" href={runHref(entry.run)}>
          {entry.relative}
        </Link>
        <div className="mt-0.5 truncate text-[11px] text-dim">
          {entry.rootLabel} · {identity(entry) || "declares no kind"}
        </div>
      </div>
      <span className="text-xs text-dim max-[700px]:hidden">
        {states(entry)}
        {entry.view?.source === "cache" ? <span title="derived by stage-gen view"> ⁺</span> : null}
      </span>
      <span
        className="text-xs text-dim max-[700px]:hidden"
        title={entry.updatedAt ? `last changed ${entry.updatedAt}` : undefined}
      >
        {ago(entry.updatedAt, now)}
      </span>
      <span className="flex items-center justify-end gap-1.5">
        <span className={cx("border px-1.5 py-0.5 text-xs whitespace-nowrap", mark.className)}>
          {mark.label}
        </span>
        {entry.view !== null ? (
          <Link className={cx(linkGhost, "max-[700px]:hidden")} href={runHref(entry.run, "artifacts")}>
            [ ⌕ assets ]
          </Link>
        ) : null}
      </span>
    </li>
  );
}

export default function RunList({
  runs,
  game = false,
  now,
}: {
  runs: readonly RunIndexEntry[];
  game?: boolean;
  now: number;
}) {
  const shown = runs.slice(0, VISIBLE_RUNS);
  const folded = runs.slice(VISIBLE_RUNS);
  return (
    <>
      <ul className="m-0 list-none border-t border-border p-0">
        {shown.map((entry) => (
          <RunRow key={`${entry.run.root}/${entry.run.tag}`} entry={entry} game={game} now={now} />
        ))}
      </ul>
      {folded.length > 0 ? (
        <details className="mt-1">
          <summary className="cursor-pointer text-xs text-dim hover:text-fg">
            {folded.length} older run{folded.length === 1 ? "" : "s"}
          </summary>
          <ul className="m-0 list-none p-0">
            {folded.map((entry) => (
              <RunRow key={`${entry.run.root}/${entry.run.tag}`} entry={entry} game={game} now={now} />
            ))}
          </ul>
        </details>
      ) : null}
    </>
  );
}

