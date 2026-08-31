import Link from "next/link";
import { notFound } from "next/navigation";
import ScenePlayer from "./ScenePlayer";
import { readSceneFixture } from "@/lib/shell/dialogue-scene";
import { isSafeRunTag } from "@/lib/shell/runs";

export const dynamic = "force-dynamic";

// The visual-novel consumer, played straight out of the run that produced it —
// the same shape the point-and-click room uses, on the same engine. Installing a
// scene as the site's active theme is a separate, deliberate act; this page is
// for looking at what you just generated, so it reads `out/<tag>/bundle.json`
// and streams that run's own assets. The only chrome is one way back out.
export default async function ScenePage({ params }: { params: Promise<{ tag: string }> }) {
  const { tag } = await params;
  if (!isSafeRunTag(tag)) notFound();
  const fixture = await readSceneFixture(tag);
  if (!fixture) notFound();
  return (
    <main className="fixed inset-0 flex flex-col bg-black">
      <div className="flex items-center gap-3 px-3 py-1.5 text-[11px] text-dim">
        <Link href="/" className="shrink-0 whitespace-nowrap text-fg no-underline">
          [ ◂ back ]
        </Link>
        <span className="truncate">
          {fixture.title} · <span className="text-fg">{tag}</span>
        </span>
      </div>
      <div className="min-h-0 flex-1">
        <ScenePlayer fixture={fixture} />
      </div>
    </main>
  );
}
