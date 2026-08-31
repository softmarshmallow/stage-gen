// Home (root URL).
//
// A consumer index over out/: the published runtime packages that can be previewed,
// and the traced runs that can be read back. Generation happens in the headless CLI;
// nothing on this page starts a run.

import Link from "next/link";
import { listReadyProjects } from "@/lib/shell/projects";
import { listReadyScenes } from "@/lib/shell/dialogue-scene";
import { listReadyRooms } from "@/lib/shell/pointclick-room";
import { listExecutionViewRuns } from "@/lib/shell/execution-view";
import { sceneModuleForKind } from "@/lib/shell/scene-modules";
import { POINTCLICK_RUNTIME_KIND } from "@/lib/pointclick/contract";
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

export default async function Home() {
  const [projects, rooms, scenes, views] = await Promise.all([
    listReadyProjects(),
    listReadyRooms(),
    listReadyScenes(),
    listExecutionViewRuns(),
  ]);
  const roomModule = sceneModuleForKind(POINTCLICK_RUNTIME_KIND);
  return (
    <main className={page}>
      <h1 className={h1}>stage-gen</h1>
      <p className={cx(metaLine, "mb-5")}>
        consumer surfaces over <code>out/</code> · generation runs headlessly
      </p>

      <section>
        <div className="mb-2 text-[13px]">
          <span className="text-dim">published runtime packages</span>
          <span className="text-dim opacity-60"> · {projects.length}</span>
        </div>
        {projects.length > 0 ? (
          <ul className="flex list-none flex-col gap-1.5">
            {projects.map((p) => (
              <li
                key={p.tag}
                className="grid grid-cols-[64px_1fr_auto] items-center gap-3 border border-border px-2.5 py-1.5 hover:border-fg max-[480px]:grid-cols-[48px_1fr]"
              >
                <div className="flex h-12 w-16 items-center justify-center overflow-hidden bg-well text-dim">
                  {p.conceptFile ? (
                    /* eslint-disable-next-line @next/next/no-img-element */
                    <img
                      className="h-full w-full object-cover"
                      src={`/api/assets/${p.tag}/${p.conceptFile}`}
                      alt=""
                      aria-hidden
                    />
                  ) : (
                    <span aria-hidden>·</span>
                  )}
                </div>
                <div className="min-w-0">
                  <div className="truncate text-[13px] text-fg">
                    {p.displayName}
                  </div>
                  <div className="mt-0.5 truncate text-[11px] text-dim">
                    {p.tag}
                  </div>
                </div>
                <div className="flex items-center gap-1.5 max-[480px]:col-span-full max-[480px]:justify-end">
                  <Link
                    className={cx(playActive, playSizeCompact)}
                    href={`/preview/${p.tag}`}
                  >
                    [ ▶ open preview ]
                  </Link>
                  <Link className={linkGhost} href={`/packages/${p.tag}`}>
                    [ ⌕ assets ]
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className={metaLine}>
            None yet. Publish one with{" "}
            <code>stage-gen generate --checkpoint integration</code>.
          </p>
        )}
      </section>

      <section className="mt-8 border-t border-border pt-4">
        <div className="mb-2 text-[13px]">
          <span className="text-dim">point-and-click rooms</span>
          <span className="text-dim opacity-60"> · {rooms.length}</span>
        </div>
        {rooms.length > 0 && roomModule ? (
          <ul className="flex list-none flex-col gap-1.5">
            {rooms.map((room) => (
              <li
                key={room.tag}
                className="grid grid-cols-[64px_1fr_auto] items-center gap-3 border border-border px-2.5 py-1.5 hover:border-fg max-[480px]:grid-cols-[48px_1fr]"
              >
                <div className="flex h-12 w-16 items-center justify-center overflow-hidden bg-well text-dim">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    className="h-full w-full object-cover"
                    src={`/api/assets/${room.tag}/${room.cover}`}
                    alt=""
                    aria-hidden
                  />
                </div>
                <div className="min-w-0">
                  <div className="truncate text-[13px] text-fg">{room.displayName}</div>
                  <div className="mt-0.5 truncate text-[11px] text-dim">{room.tag}</div>
                </div>
                <Link
                  className={cx(playActive, playSizeCompact, "max-[480px]:col-span-full max-[480px]:justify-self-end")}
                  href={roomModule.route(room.tag)}
                >
                  [ ▶ enter room ]
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className={metaLine}>
            None yet. Generate one with <code>stage-gen pointclick-room generate</code>.
          </p>
        )}
      </section>

      <section className="mt-8 border-t border-border pt-4">
        <div className="mb-2 text-[13px]">
          <span className="text-dim">visual-novel scenes</span>
          <span className="text-dim opacity-60"> · {scenes.length}</span>
        </div>
        {scenes.length > 0 ? (
          <ul className="flex list-none flex-col gap-1.5">
            {scenes.map((scene) => (
              <li
                key={scene.tag}
                className="grid grid-cols-[64px_1fr_auto] items-center gap-3 border border-border px-2.5 py-1.5 hover:border-fg max-[480px]:grid-cols-[48px_1fr]"
              >
                <div className="flex h-12 w-16 items-center justify-center overflow-hidden bg-well text-dim">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    className="h-full w-full object-cover"
                    src={`/api/assets/${scene.tag}/${scene.identityReference}`}
                    alt=""
                    aria-hidden
                  />
                </div>
                <div className="min-w-0">
                  <div className="truncate text-[13px] text-fg">{scene.title}</div>
                  <div className="mt-0.5 truncate text-[11px] text-dim">{scene.tag}</div>
                </div>
                <Link
                  className={cx(playActive, playSizeCompact, "max-[480px]:col-span-full max-[480px]:justify-self-end")}
                  href={`/scene/${encodeURIComponent(scene.tag)}`}
                >
                  [ ▶ play scene ]
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className={metaLine}>
            None yet. Generate one with <code>stage-gen dialogue-scene generate</code>.
          </p>
        )}
      </section>

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
