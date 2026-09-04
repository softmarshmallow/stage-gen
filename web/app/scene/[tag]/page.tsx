import { notFound } from "next/navigation";
import CasePlayer from "@/app/_play/CasePlayer";
import { singleBeatCase } from "@/lib/narrative/case";
import { readSceneFixture } from "@/lib/shell/dialogue-scene";
import { isSafeRunTag } from "@/lib/shell/runs";

export const dynamic = "force-dynamic";

// The visual-novel consumer, played straight out of the run that produced it —
// the same shape the point-and-click room uses, on the same engine. This page is
// for looking at what you just generated, so it reads `out/<tag>/bundle.json`
// and streams that run's own assets.
//
// It is a case of one beat. The shell — autosave at every statement, a Continue
// when a save is waiting, the backlog — belongs to every leaf, not only to the
// ones a case chains, and a scene played on its own that could not be resumed
// would be a second, worse consumer of the same runtime.
export default async function ScenePage({ params }: { params: Promise<{ tag: string }> }) {
  const { tag } = await params;
  if (!isSafeRunTag(tag)) notFound();
  const fixture = await readSceneFixture(tag);
  if (!fixture) notFound();
  const caseDocument = singleBeatCase(fixture.title, "scenario", tag);
  return (
    <CasePlayer
      tag={tag}
      caseDocument={caseDocument}
      leaves={[
        {
          beat: caseDocument.beats[0]!,
          scene: fixture,
          room: null,
          error: null,
        },
      ]}
    />
  );
}
