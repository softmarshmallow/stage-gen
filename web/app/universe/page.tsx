// The universe viewer's home: every gallery run under out/.
//
// A universe is not a playable scene, so it does not register in SCENE_MODULES
// and does not appear in the home page's genre sections. It gets its own index
// here, listing what the run produced and what review made of it.

import Link from "next/link";
import { cx, h1, metaLine, page } from "@/app/ui";
import {
  listUniverseRuns,
  type UniverseRunListEntry,
} from "@/lib/shell/universe";

export const dynamic = "force-dynamic";

function duration(entry: UniverseRunListEntry): string {
  if (entry.durationMs === null) return "";
  const seconds = entry.durationMs / 1000;
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  return `${Math.floor(seconds / 60)}m ${String(Math.round(seconds % 60)).padStart(2, "0")}s`;
}

function cost(entry: UniverseRunListEntry): string {
  return entry.knownCostUsd === null ? "" : `$${entry.knownCostUsd.toFixed(2)}`;
}

/** Admitted over total, with the rest of the terminal statuses spelled out. */
function outcome(entry: UniverseRunListEntry): string {
  const admitted = entry.counts.admitted ?? 0;
  const rest = Object.entries(entry.counts)
    .filter(([status]) => status !== "admitted")
    .map(([status, count]) => `${count} ${status.replace(/_/g, " ")}`);
  return [`${admitted}/${entry.entityCount} admitted`, ...rest].join(" · ");
}

export default async function UniverseIndexPage() {
  const runs = await listUniverseRuns();
  return (
    <main className={page}>
      <p className={metaLine}>
        <Link className="text-dim no-underline hover:text-accent" href="/">
          ← stage-gen
        </Link>
      </p>
      <h1 className={h1}>Universes</h1>
      <p className={cx(metaLine, "mb-4")}>
        {runs.length} gallery run{runs.length === 1 ? "" : "s"} under{" "}
        <code>out/</code> · generate one with{" "}
        <code>stage-gen universe gallery</code>
      </p>
      {runs.length === 0 ? (
        <p className="text-dim">
          No universe galleries found. Run the semantic phase, then the gallery
          phase, and reload.
        </p>
      ) : (
        <ol className="m-0 list-none border-t border-border">
          {runs.map((entry) => (
            <li key={entry.tag}>
              <Link
                className="grid grid-cols-[72px_minmax(0,1fr)_auto_auto] items-center gap-x-4 border-b border-border px-2 py-2.5 text-fg no-underline hover:bg-hover max-[700px]:grid-cols-[56px_minmax(0,1fr)]"
                href={`/universe/${encodeURIComponent(entry.tag)}`}
              >
                <div className="flex h-14 w-[72px] items-center justify-center overflow-hidden bg-well text-dim max-[700px]:w-14">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    className="h-full w-full object-cover"
                    src={`/api/assets/${encodeURIComponent(entry.tag)}/${entry.poster
                      .split("/")
                      .map(encodeURIComponent)
                      .join("/")}`}
                    alt=""
                    aria-hidden
                  />
                </div>
                <div className="min-w-0">
                  <div className="truncate text-[13px] text-fg">
                    {entry.title}
                  </div>
                  <div className="mt-0.5 truncate text-[11px] text-dim">
                    {entry.tag} · {entry.mediumId.replace(/_/g, " ")} ·{" "}
                    {outcome(entry)}
                  </div>
                </div>
                <span className="text-xs text-dim max-[700px]:hidden">
                  {duration(entry)}
                </span>
                <span className="text-xs text-dim max-[700px]:hidden">
                  {cost(entry)}
                </span>
              </Link>
            </li>
          ))}
        </ol>
      )}
    </main>
  );
}
