import CasePlayer from "@/app/_play/CasePlayer";
import {
  DEMO_CASE_TAG,
  demoCaseDocument,
  demoCaseLeaf,
} from "@/lib/narrative/case.fixture";

export const dynamic = "force-dynamic";

// The demonstration case, played from the consumer's own hand-authored fixture.
//
// It exists because the case container was authored on the producer side at the
// same time as this consumer, and a shell with nothing to play is a shell nobody
// has seen work. Everything here is the real code path: the same parser, the same
// runtime, the same autosave, the same two leaf players. Only the document and
// the leaf declarations are hand-written, and their art is streamed from runs
// that already exist.
//
// `/case/<tag>` is the route that matters; this static segment sits beside it and
// takes precedence over the dynamic one for the single tag "demo".
export default function DemoCasePage() {
  const caseDocument = demoCaseDocument();
  const leaves = caseDocument.beats.map((beat) => {
    const leaf = demoCaseLeaf(beat.beatId);
    return {
      beat,
      scene: leaf?.scene ?? null,
      room: leaf?.room ?? null,
      error: leaf === null ? `the demo case has no leaf for ${beat.beatId}` : null,
    };
  });
  return <CasePlayer tag={DEMO_CASE_TAG} caseDocument={caseDocument} leaves={leaves} />;
}
