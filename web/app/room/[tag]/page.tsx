import Link from "next/link";
import { notFound } from "next/navigation";
import { readRoomManifest } from "@/lib/shell/pointclick-room";
import { isSafeRunTag } from "@/lib/shell/runs";
import RoomPlayer from "./RoomPlayer";

export const dynamic = "force-dynamic";

// The point-and-click room consumer: one fixed painted scene rendered from the
// run's own manifest. This page is a preview adapter, not the pipeline.
export default async function RoomPage({ params }: { params: Promise<{ tag: string }> }) {
  const { tag } = await params;
  if (!isSafeRunTag(tag)) notFound();
  const manifest = await readRoomManifest(tag);
  if (!manifest) notFound();
  return (
    <main className="bg-bg min-h-screen">
      <div className="flex items-center gap-4 px-4 py-2 text-xs text-dim">
        <Link href="/" className="text-fg no-underline">
          [ ◂ back ]
        </Link>
        <span>
          stage-gen / point-and-click room / <span className="text-fg">{tag}</span>
        </span>
        <span>{manifest.displayName}</span>
      </div>
      <RoomPlayer tag={tag} manifest={manifest} />
    </main>
  );
}
