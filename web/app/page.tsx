// Picker view (root URL).
//
// Phase 8 / TC-100..103, 113. Server component renders the input + Generate
// island and a quick-demo list of already-completed projects under out/.

import Link from "next/link";
import Picker from "./Picker";
import { listReadyProjects } from "@/lib/shell/projects";
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

function shortPrompt(s: string, max = 90): string {
  if (s.length <= max) return s;
  return s.slice(0, max - 1).trimEnd() + "…";
}

export default async function Home() {
  const projects = await listReadyProjects();
  return (
    <main className={page}>
      <h1 className={h1}>stage-gen</h1>
      <p className={cx(metaLine, "mb-5")}>
        optional scrolling-preview adapter · reusable generation runs headlessly
      </p>
      <Picker presets={[]} />

      {projects.length > 0 ? (
        <section className="mt-8 border-t border-border pt-4">
          <div className="mb-2 text-[13px]">
            <span className="text-dim">ready preview runs</span>
            <span className="text-dim opacity-60"> · {projects.length} done</span>
          </div>
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
                  <div className="truncate text-[13px] text-fg" title={p.prompt}>
                    {shortPrompt(p.prompt)}
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
                  <Link className={linkGhost} href={`/generate/${p.tag}`}>
                    [ ⌕ details ]
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </main>
  );
}
