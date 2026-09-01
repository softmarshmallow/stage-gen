// Home (root URL).
//
// A consumer index over out/: the published runtime packages that can be previewed,
// and the traced runs that can be read back. Generation happens in the headless CLI;
// nothing on this page starts a run.
//
// The per-genre sections iterate the SCENE_MODULES registry rather than being
// hand-written per genre: the registry says which kinds this build plays and
// where, and this page only adds how each kind lists itself. A new genre gets
// a section by registering, not by editing this file's markup.

import Link from "next/link";
import { listReadyProjects } from "@/lib/shell/projects";
import { listReadyScenes } from "@/lib/shell/dialogue-scene";
import { listReadyRooms } from "@/lib/shell/pointclick-room";
import { listReadyRunnerRuns } from "@/lib/shell/sideview-runner";
import { listExecutionViewRuns } from "@/lib/shell/execution-view";
import { DIALOGUE_SCENE_BUNDLE_KIND } from "@/lib/dialogue-scene/bundle";
import { SCENE_MODULES, type SceneModule } from "@/lib/shell/scene-modules";
import { POINTCLICK_RUNTIME_KIND } from "@/lib/pointclick/contract";
import { PREPARED_RUNTIME_KIND } from "@/lib/manifest/prepared-manifest";
import { RUNNER_RUNTIME_KIND } from "@/lib/sideview-runner/contract";
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

interface GenreRunRow {
  readonly tag: string;
  readonly title: string;
  /** Run-relative asset ref for the row's thumbnail, when the run has one. */
  readonly thumb: string | null;
  /** Additional per-run links beside the play action (e.g. the asset explorer). */
  readonly extraLinks?: readonly { readonly label: string; readonly href: string }[];
}

interface GenreSectionSpec {
  readonly heading: string;
  readonly action: string;
  /** The empty state's lead-in, e.g. "Publish one with". */
  readonly emptyLead: string;
  /** The CLI invocation named in the empty state. */
  readonly generateHint: string;
  readonly load: () => Promise<readonly GenreRunRow[]>;
}

/**
 * How each registered kind lists itself. The registry owns identity and
 * route; this map owns only index presentation, so a kind missing here still
 * plays — it just has no section yet, and the render below skips it.
 */
const GENRE_SECTIONS: Readonly<Record<string, GenreSectionSpec>> = {
  [PREPARED_RUNTIME_KIND]: {
    heading: "published runtime packages",
    action: "[ ▶ open preview ]",
    emptyLead: "Publish one with",
    generateHint: "stage-gen generate --checkpoint integration",
    load: async () =>
      (await listReadyProjects()).map((project) => ({
        tag: project.tag,
        title: project.displayName,
        thumb: project.conceptFile ?? null,
        extraLinks: [{ label: "[ ⌕ assets ]", href: `/packages/${project.tag}` }],
      })),
  },
  [POINTCLICK_RUNTIME_KIND]: {
    heading: "point-and-click rooms",
    action: "[ ▶ enter room ]",
    emptyLead: "Generate one with",
    generateHint: "stage-gen pointclick-room generate",
    load: async () =>
      (await listReadyRooms()).map((room) => ({
        tag: room.tag,
        title: room.displayName,
        thumb: room.cover,
      })),
  },
  [DIALOGUE_SCENE_BUNDLE_KIND]: {
    heading: "visual-novel scenes",
    action: "[ ▶ play scene ]",
    emptyLead: "Generate one with",
    generateHint: "stage-gen dialogue-scene generate",
    load: async () =>
      (await listReadyScenes()).map((scene) => ({
        tag: scene.tag,
        title: scene.title,
        thumb: scene.styleReference,
      })),
  },
  [RUNNER_RUNTIME_KIND]: {
    heading: "infinite runners",
    action: "[ ▶ run ]",
    emptyLead: "Generate one with",
    generateHint: "stage-gen generate --genre runner",
    load: async () =>
      (await listReadyRunnerRuns()).map((run) => ({
        tag: run.tag,
        title: `${run.displayName} · ${run.trackDisplayName}`,
        thumb: run.cover,
      })),
  },
};

function GenreSection({
  module,
  spec,
  rows,
  first,
}: {
  module: SceneModule;
  spec: GenreSectionSpec;
  rows: readonly GenreRunRow[];
  first: boolean;
}) {
  return (
    <section className={first ? undefined : "mt-8 border-t border-border pt-4"}>
      <div className="mb-2 text-[13px]">
        <span className="text-dim">{spec.heading}</span>
        <span className="text-dim opacity-60"> · {rows.length}</span>
      </div>
      {rows.length > 0 ? (
        <ul className="flex list-none flex-col gap-1.5">
          {rows.map((row) => (
            <li
              key={row.tag}
              className="grid grid-cols-[64px_1fr_auto] items-center gap-3 border border-border px-2.5 py-1.5 hover:border-fg max-[480px]:grid-cols-[48px_1fr]"
            >
              <div className="flex h-12 w-16 items-center justify-center overflow-hidden bg-well text-dim">
                {row.thumb ? (
                  /* eslint-disable-next-line @next/next/no-img-element */
                  <img
                    className="h-full w-full object-cover"
                    src={`/api/assets/${row.tag}/${row.thumb}`}
                    alt=""
                    aria-hidden
                  />
                ) : (
                  <span aria-hidden>·</span>
                )}
              </div>
              <div className="min-w-0">
                <div className="truncate text-[13px] text-fg">{row.title}</div>
                <div className="mt-0.5 truncate text-[11px] text-dim">{row.tag}</div>
              </div>
              {row.extraLinks?.length ? (
                <div className="flex items-center gap-1.5 max-[480px]:col-span-full max-[480px]:justify-end">
                  <Link className={cx(playActive, playSizeCompact)} href={module.route(row.tag)}>
                    {spec.action}
                  </Link>
                  {row.extraLinks.map((link) => (
                    <Link key={link.href} className={linkGhost} href={link.href}>
                      {link.label}
                    </Link>
                  ))}
                </div>
              ) : (
                <Link
                  className={cx(
                    playActive,
                    playSizeCompact,
                    "max-[480px]:col-span-full max-[480px]:justify-self-end",
                  )}
                  href={module.route(row.tag)}
                >
                  {spec.action}
                </Link>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className={metaLine}>
          None yet. {spec.emptyLead} <code>{spec.generateHint}</code>.
        </p>
      )}
    </section>
  );
}

export default async function Home() {
  const listed = SCENE_MODULES.filter((module) => module.kind in GENRE_SECTIONS);
  const [views, sections] = await Promise.all([
    listExecutionViewRuns(),
    Promise.all(listed.map((module) => GENRE_SECTIONS[module.kind].load())),
  ]);
  return (
    <main className={page}>
      <h1 className={h1}>stage-gen</h1>
      <p className={cx(metaLine, "mb-5")}>
        consumer surfaces over <code>out/</code> · generation runs headlessly
      </p>

      {listed.map((module, index) => (
        <GenreSection
          key={module.kind}
          module={module}
          spec={GENRE_SECTIONS[module.kind]}
          rows={sections[index]}
          first={index === 0}
        />
      ))}

      <section className="mt-8 border-t border-border pt-4">
        <div className="mb-2 text-[13px]">
          <span className="text-dim">exported runs</span>
          <span className="text-dim opacity-60"> · {views.length}</span>
        </div>
        <p className={cx(metaLine, "mb-2")}>
          <Link className={linkGhost} href="/runs">
            [ ⌕ open the run viewer ]
          </Link>
        </p>
      </section>
    </main>
  );
}
