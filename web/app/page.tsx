// Picker view (root URL).
//
// Phase 8 / TC-100..103, 113. Server component renders the input + Generate
// island and a quick-demo list of already-completed projects under out/.

import Link from "next/link";
import Picker from "./Picker";
import { listReadyProjects } from "@/lib/shell/projects";

export const dynamic = "force-dynamic";

function shortPrompt(s: string, max = 90): string {
  if (s.length <= max) return s;
  return s.slice(0, max - 1).trimEnd() + "…";
}

export default async function Home() {
  const projects = await listReadyProjects();
  return (
    <main className="sg-page">
      <h1 className="sg-h1">stage-gen</h1>
      <Picker presets={[]} />

      {projects.length > 0 ? (
        <section className="sg-projects">
          <div className="sg-projects-h">
            <span style={{ color: "var(--dim)" }}>ready projects</span>
            <span style={{ color: "var(--dim)", opacity: 0.6 }}>
              {" "}
              · {projects.length} done
            </span>
          </div>
          <ul className="sg-projects-list">
            {projects.map((p) => (
              <li key={p.tag} className="sg-project-row">
                <div className="sg-project-thumb">
                  {p.conceptFile ? (
                    /* eslint-disable-next-line @next/next/no-img-element */
                    <img
                      src={`/api/assets/${p.tag}/${p.conceptFile}`}
                      alt=""
                      aria-hidden
                    />
                  ) : (
                    <span aria-hidden>·</span>
                  )}
                </div>
                <div className="sg-project-meta">
                  <div className="sg-project-prompt" title={p.prompt}>
                    {shortPrompt(p.prompt)}
                  </div>
                  <div className="sg-project-tag">{p.tag}</div>
                </div>
                <div className="sg-project-actions">
                  <Link
                    className="sg-play is-active sg-mini"
                    href={`/play/${p.tag}`}
                  >
                    [ ▶ play ]
                  </Link>
                  <Link className="sg-mini sg-mini-ghost" href={`/generate/${p.tag}`}>
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
