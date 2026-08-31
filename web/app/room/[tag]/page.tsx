import Link from "next/link";
import { notFound } from "next/navigation";
import { readRoomManifest } from "@/lib/shell/pointclick-room";
import { isSafeRunTag } from "@/lib/shell/runs";
import RoomPlayer from "./RoomPlayer";

export const dynamic = "force-dynamic";

// The point-and-click room consumer: the run's own manifest, played on the same
// engine as every other stage-gen game. The page gives the canvas the viewport
// and stays out of the way — the room is the whole surface, the way it would be
// embedded on a phone; the only chrome is one way back out.
export default async function RoomPage({ params }: { params: Promise<{ tag: string }> }) {
  const { tag } = await params;
  if (!isSafeRunTag(tag)) notFound();
  const manifest = await readRoomManifest(tag);
  if (!manifest) notFound();
  return (
    <main className="fixed inset-0 flex flex-col bg-black">
      <div className="flex items-center gap-3 px-3 py-1.5 text-[11px] text-dim">
        <Link href="/" className="shrink-0 whitespace-nowrap text-fg no-underline">
          [ ◂ back ]
        </Link>
        <span className="truncate">
          {manifest.displayName} · <span className="text-fg">{tag}</span>
        </span>
      </div>
      <div className="min-h-0 flex-1">
        <RoomPlayer tag={tag} manifest={manifest} />
      </div>
    </main>
  );
}
