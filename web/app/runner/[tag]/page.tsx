import Link from "next/link";
import { notFound } from "next/navigation";
import { readRunnerManifest } from "@/lib/shell/sideview-runner";
import { isSafeRunTag } from "@/lib/shell/runs";
import RunnerPlayer from "./RunnerPlayer";

export const dynamic = "force-dynamic";

// The infinite-runner consumer: the run's own manifest, played on the same
// engine as every other stage-gen game. The page gives the canvas the viewport
// and stays out of the way, the same shape the room route uses — the track is
// the whole surface, and the only chrome is one way back out.
export default async function RunnerPage({ params }: { params: Promise<{ tag: string }> }) {
  const { tag } = await params;
  if (!isSafeRunTag(tag)) notFound();
  const manifest = await readRunnerManifest(tag);
  if (!manifest) notFound();
  return (
    <main className="fixed inset-0 flex flex-col bg-black">
      <div className="flex items-center gap-3 px-3 py-1.5 text-[11px] text-dim">
        <Link href="/" className="shrink-0 whitespace-nowrap text-fg no-underline">
          [ ◂ back ]
        </Link>
        <span className="truncate">
          {manifest.displayName} · {manifest.trackDisplayName} ·{" "}
          <span className="text-fg">{tag}</span>
        </span>
      </div>
      <div className="min-h-0 flex-1">
        <RunnerPlayer tag={tag} manifest={manifest} />
      </div>
    </main>
  );
}
