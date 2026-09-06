// Home (root URL).
//
// The viewer's index over out/: every run the pipeline published, what each
// one is, and where to open it. Generation happens in the headless CLI;
// nothing on this page starts a run, and nothing on it plays one.
//
// It used to ask four genre readers for their runs, each importing that
// genre's parser for a title and a cover, which made the front page a consumer
// of every runtime at once. It now reads one field — the document's `kind` —
// through `listRuns`, and the table below is the only thing that knows a kind
// can be played at all. Every genre's host is a Godot host (decision 0061), so
// that table is a shrinking list of browser surfaces waiting for their port,
// and it leaves with the last of them.

import Link from "next/link";
import { listReadyCases } from "@/lib/narrative/case-io";
import { listRuns, type RunIndexEntry } from "@/lib/shell/run-index";
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

/**
 * The browser surfaces that still play a kind, by the kind's literal name.
 *
 * Literal strings on purpose: importing a genre's kind constant is importing
 * that genre, which is what this page stopped doing. A row is deleted in the
 * change that lands its Godot host and deletes its route, and when the table
 * is empty it goes with the last row.
 */
const BROWSER_PLAY_ROUTES: Readonly<Record<string, { label: string; href: (tag: string) => string }>> =
  {
    "prepared-game-runtime-v12": {
      label: "[ ▶ open preview ]",
      href: (tag) => `/preview/${encodeURIComponent(tag)}`,
    },
    "pointclick-room-runtime-v3": {
      label: "[ ▶ enter room ]",
      href: (tag) => `/room/${encodeURIComponent(tag)}`,
    },
    "dialogue-scene-bundle-v8": {
      label: "[ ▶ play scene ]",
      href: (tag) => `/scene/${encodeURIComponent(tag)}`,
    },
    "sideview-runner-runtime-v13": {
      label: "[ ▶ run ]",
      href: (tag) => `/runner/${encodeURIComponent(tag)}`,
    },
  };

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
  const play = entry.kind ? BROWSER_PLAY_ROUTES[entry.kind] : undefined;
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
        {play ? (
          <Link
            className={cx(playActive, playSizeCompact)}
            href={play.href(entry.tag)}
          >
            {play.label}
          </Link>
        ) : null}
      </div>
    </li>
  );
}

export default async function Home() {
  const [runs, cases, universes] = await Promise.all([
    listRuns(),
    listReadyCases(),
    listUniverseRuns(),
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

      {/* A case sits above the leaves: several scenarios and rooms played in
          order at one URL, with a shared set of facts crossing between them.
          It is a browser surface like the four above and leaves with them. */}
      <section className="mt-8 border-t border-border pt-4">
        <div className="mb-2 text-[13px]">
          <span className="text-dim">cases</span>
          <span className="text-dim opacity-60"> · {cases.length + 1}</span>
        </div>
        <ul className="flex list-none flex-col gap-1.5">
          {cases.map((entry) => (
            <li
              key={entry.tag}
              className="grid grid-cols-[1fr_auto] items-center gap-3 border border-border px-2.5 py-1.5 hover:border-fg"
            >
              <div className="min-w-0">
                <div className="truncate text-[13px] text-fg">
                  {entry.displayName}
                </div>
                <div className="mt-0.5 truncate text-[11px] text-dim">
                  {entry.tag} · {entry.beats} beats
                </div>
              </div>
              <Link
                className={cx(playActive, playSizeCompact)}
                href={`/case/${encodeURIComponent(entry.tag)}`}
              >
                [ ▶ play case ]
              </Link>
            </li>
          ))}
          <li className="grid grid-cols-[1fr_auto] items-center gap-3 border border-border px-2.5 py-1.5 hover:border-fg">
            <div className="min-w-0">
              <div className="truncate text-[13px] text-fg">
                A demonstration case
              </div>
              <div className="mt-0.5 truncate text-[11px] text-dim">
                demo · scenario, room, scenario · hand-authored fixture
              </div>
            </div>
            <Link className={cx(playActive, playSizeCompact)} href="/case/demo">
              [ ▶ play case ]
            </Link>
          </li>
        </ul>
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
    </main>
  );
}
