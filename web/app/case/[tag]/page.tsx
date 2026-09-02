import { notFound } from "next/navigation";
import CasePlayer from "@/app/_play/CasePlayer";
import { readPlayableCase } from "@/lib/shell/case-io";
import { isSafeRunTag } from "@/lib/shell/runs";

export const dynamic = "force-dynamic";

// A whole case at one URL: the beats in order, the facts carried between them,
// and one autosave. The player never types a second address — the shell moves
// from a scenario to a room to a scenario on the outcome each leaf reports.
//
// The case document is published beside the runs it chains, as
// `out/<tag>/case.json`. Every beat's leaf is read here, on the server, so the
// crossing from one to the next is a swap rather than a fetch.
export default async function CaseRoutePage({
  params,
}: {
  params: Promise<{ tag: string }>;
}) {
  const { tag } = await params;
  if (!isSafeRunTag(tag)) notFound();
  const playable = await readPlayableCase(tag);
  if (playable === null) notFound();
  return (
    <CasePlayer
      tag={tag}
      caseDocument={playable.document}
      leaves={playable.leaves}
    />
  );
}
