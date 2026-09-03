// One universe gallery, read back from its run.
//
// Every join and tally happens here on the server, from the three documents
// the run publishes; the client component receives finished cards and owns
// only what the reader does to them — filtering, and opening one.

import Link from "next/link";
import { notFound } from "next/navigation";
import { errorBanner, h1, metaLine, page } from "@/app/ui";
import { readUniverseGallery } from "@/lib/shell/universe";
import { isSafeRunTag } from "@/lib/shell/runs";
import {
  buildEntityCards,
  presentClasses,
  tallyReviewChecks,
} from "@/lib/universe/gallery-view";
import UniverseViewer from "./UniverseViewer";

export const dynamic = "force-dynamic";

export default async function UniverseGalleryPage({
  params,
}: {
  params: Promise<{ tag: string }>;
}) {
  const { tag } = await params;
  if (!isSafeRunTag(tag)) notFound();

  let gallery: Awaited<ReturnType<typeof readUniverseGallery>> = null;
  let refusal: string | null = null;
  try {
    gallery = await readUniverseGallery(tag);
  } catch (error) {
    refusal = error instanceof Error ? error.message : String(error);
  }

  if (refusal !== null) {
    return (
      <main className={page}>
        <p className={metaLine}>
          <Link
            className="text-dim no-underline hover:text-accent"
            href="/universe"
          >
            ← universes
          </Link>
        </p>
        <h1 className={h1}>{tag}</h1>
        <p className={errorBanner}>{refusal}</p>
      </main>
    );
  }
  if (!gallery) notFound();

  const cards = buildEntityCards(
    gallery.manifest,
    gallery.universe,
    gallery.records,
  );
  return (
    <UniverseViewer
      tag={tag}
      manifest={gallery.manifest}
      universe={gallery.universe}
      cards={cards}
      classes={presentClasses(cards)}
      tallies={tallyReviewChecks(cards)}
      unreadableRecords={gallery.unreadableRecords}
      hasExecutionView={gallery.hasExecutionView}
    />
  );
}
