// Home (root URL).
//
// The viewer's index over out/: every run the pipeline published, what each
// one is, and where to open it. Generation happens in the headless CLI;
// nothing on this page starts a run, and nothing on it plays one.
//
// It used to ask four genre readers for their runs, each importing that
// genre's parser for a title and a cover, which made the front page a consumer
// of every runtime at once. It now reads one field — the document's `kind` —
// through `listRuns`, and knows nothing else about what a run contains.
//
// It also used to hold a table of the kinds a browser surface could still
// play, which shrank as each genre landed its Godot host (decision 0061). The
// platformer was the last row, and the table left with it: no run is playable
// from here, and a reader who wants to play one runs the host.

import Link from "next/link";
import { listRuns, type RunIndexEntry } from "@/lib/shell/run-index";
import { listStorefrontRuns } from "@/lib/shell/storefront";
import { listUniverseRuns } from "@/lib/shell/universe";
import {
  cx,
  h1,
  linkGhost,
  metaLine,
  page,
  playActive,
  playSizeCompact,
} from "./ui";

export const dynamic = "force-dynamic";

/** What a run says it is, for the reader: the kind, or why there is none. */
function identity(entry: RunIndexEntry): string {
  if (entry.kind) {
    return entry.schemaVersion === null
      ? entry.kind
      : `${entry.kind} · schema ${entry.schemaVersion}`;
  }
  if (entry.document) return `${entry.document} · declares no kind`;
  return "no published document";
}

function RunRow({ entry }: { entry: RunIndexEntry }) {
  return (
    <li className="grid grid-cols-[1fr_auto] items-center gap-3 border border-border px-2.5 py-1.5 hover:border-fg">
      <div className="min-w-0">
        <div className="truncate text-[13px] text-fg">{entry.tag}</div>
        <div className="mt-0.5 truncate text-[11px] text-dim">
          {identity(entry)}
        </div>
      </div>
      <div className="flex items-center gap-1.5">
        {entry.hasExecutionView ? (
          <Link
            className={linkGhost}
            href={`/runs/${encodeURIComponent(entry.tag)}`}
          >
            [ ⌕ run ]
          </Link>
        ) : null}
        {entry.hasExecutionView ? (
          <Link
            className={linkGhost}
            href={`/runs/${encodeURIComponent(entry.tag)}/artifacts`}
          >
            [ ⌕ assets ]
          </Link>
        ) : null}
      </div>
    </li>
  );
}

export default async function Home() {
  const [runs, universes, storefronts] = await Promise.all([
    listRuns(),
    listUniverseRuns(),
    listStorefrontRuns(),
  ]);
  const withView = runs.filter((entry) => entry.hasExecutionView).length;
  return (
    <main className={page}>
      <h1 className={h1}>stage-gen</h1>
      <p className={cx(metaLine, "mb-5")}>
        the run viewer over <code>out/</code> · generation runs headlessly ·
        games are played by their Godot host
      </p>

      <section>
        <div className="mb-2 text-[13px]">
          <span className="text-dim">runs</span>
          <span className="text-dim opacity-60"> · {runs.length}</span>
        </div>
        <p className={cx(metaLine, "mb-2")}>
          {withView} of {runs.length} carry a derived view.{" "}
          <Link className={linkGhost} href="/runs">
            [ ⌕ open the run viewer ]
          </Link>
        </p>
        {runs.length > 0 ? (
          <ul className="flex list-none flex-col gap-1.5">
            {runs.map((entry) => (
              <RunRow key={entry.tag} entry={entry} />
            ))}
          </ul>
        ) : (
          <p className={metaLine}>
            None yet. Publish one with <code>stage-gen generate</code>.
          </p>
        )}
      </section>

      {/* A universe is a world, not a game: nothing plays it, and the gallery
          is a viewer surface that stays. */}
      <section className="mt-8 border-t border-border pt-4">
        <div className="mb-2 text-[13px]">
          <span className="text-dim">universes</span>
          <span className="text-dim opacity-60"> · {universes.length}</span>
        </div>
        {universes.length > 0 ? (
          <ul className="flex list-none flex-col gap-1.5">
            {universes.map((entry) => (
              <li
                key={entry.tag}
                className="grid grid-cols-[1fr_auto] items-center gap-3 border border-border px-2.5 py-1.5 hover:border-fg"
              >
                <div className="min-w-0">
                  <div className="truncate text-[13px] text-fg">
                    {entry.title}
                  </div>
                  <div className="mt-0.5 truncate text-[11px] text-dim">
                    {entry.tag} · {entry.entityCount} entities ·{" "}
                    {entry.counts.admitted ?? 0} admitted
                  </div>
                </div>
                <Link
                  className={cx(playActive, playSizeCompact)}
                  href={`/universe/${encodeURIComponent(entry.tag)}`}
                >
                  [ ▶ open gallery ]
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className={metaLine}>
            None yet. Generate one with <code>stage-gen universe gallery</code>.
          </p>
        )}
      </section>

      {/* A storefront is the face a game is listed behind, not the game: it has
          no player either, and its own viewer surface stays. */}
      <section className="mt-8 border-t border-border pt-4">
        <div className="mb-2 text-[13px]">
          <span className="text-dim">storefronts</span>
          <span className="text-dim opacity-60"> · {storefronts.length}</span>
        </div>
        {storefronts.length > 0 ? (
          <ul className="flex list-none flex-col gap-1.5">
            {storefronts.map((entry) => (
              <li
                key={entry.tag}
                className="grid grid-cols-[1fr_auto] items-center gap-3 border border-border px-2.5 py-1.5 hover:border-fg"
              >
                <div className="min-w-0">
                  <div className="truncate text-[13px] text-fg">
                    {entry.displayName}
                  </div>
                  <div className="mt-0.5 truncate text-[11px] text-dim">
                    {entry.tag} · {entry.surfaceCount} surfaces ·{" "}
                    {entry.admitted} admitted
                  </div>
                </div>
                <Link
                  className={cx(playActive, playSizeCompact)}
                  href={`/storefront/${encodeURIComponent(entry.tag)}`}
                >
                  [ ▶ open storefront ]
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className={metaLine}>
            None yet. Generate one with{" "}
            <code>stage-gen storefront generate</code>.
          </p>
        )}
      </section>
    </main>
  );
}
