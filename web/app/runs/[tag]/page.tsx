// Per-run execution view. Renders the derived execution-view.json and only
// that document; a document this build refuses (hard-drop versioning) gets the
// re-export message instead of a migration.

import Link from "next/link";
import { notFound } from "next/navigation";
import { errorBanner, h1, metaLine, page } from "@/app/ui";
import type { ExecutionView } from "@/lib/run-viewer/execution-view";
import { readExecutionView } from "@/lib/shell/execution-view";
import { isSafeRunTag } from "@/lib/shell/runs";
import { runLiveness } from "@/lib/run-viewer/execution-view";
import RunViewer from "./RunViewer";

export const dynamic = "force-dynamic";

export default async function RunPage({ params }: { params: Promise<{ tag: string }> }) {
  const { tag } = await params;
  if (!isSafeRunTag(tag)) notFound();

  let view: ExecutionView | null = null;
  let refusal: string | null = null;
  try {
    view = await readExecutionView(tag);
  } catch (error) {
    refusal = error instanceof Error ? error.message : String(error);
  }

  if (refusal !== null) {
    return (
      <main className={page}>
        <p className={metaLine}>
          <Link className="text-dim no-underline hover:text-accent" href="/runs">
            ← runs
          </Link>
        </p>
        <h1 className={h1}>{tag}</h1>
        <p className={errorBanner}>{refusal}</p>
      </main>
    );
  }
  if (!view) notFound();

  // Full-bleed: the graph is the page, and the viewer floats its own chrome.
  return (
    <main className="fixed inset-0 overflow-hidden bg-bg">
      <RunViewer tag={tag} view={view} liveness={runLiveness(view, Date.now())} />
    </main>
  );
}
