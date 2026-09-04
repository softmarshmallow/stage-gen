import { notFound } from "next/navigation";
import CasePlayer from "@/app/_play/CasePlayer";
import { singleBeatCase } from "@/lib/narrative/case";
import { readRoomManifest } from "@/lib/shell/pointclick-room";
import { isSafeRunTag } from "@/lib/shell/runs";

export const dynamic = "force-dynamic";

// The point-and-click room consumer: the run's own manifest, played on the same
// engine as every other stage-gen game. The room is the whole surface, the way it
// would be embedded on a phone.
//
// As with a scene, it is a case of one beat, so a room played on its own gets the
// same autosave, Continue and backlog a room inside a case does.
export default async function RoomPage({ params }: { params: Promise<{ tag: string }> }) {
  const { tag } = await params;
  if (!isSafeRunTag(tag)) notFound();
  const manifest = await readRoomManifest(tag);
  if (!manifest) notFound();
  const caseDocument = singleBeatCase(manifest.displayName, "room", tag);
  return (
    <CasePlayer
      tag={tag}
      caseDocument={caseDocument}
      leaves={[
        {
          beat: caseDocument.beats[0]!,
          scene: null,
          room: manifest,
          error: null,
        },
      ]}
    />
  );
}
