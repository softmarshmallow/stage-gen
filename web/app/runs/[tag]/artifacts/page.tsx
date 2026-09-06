// Every artifact one run produced, grouped by what it is.
//
// This replaced `/packages/<tag>`, which read one genre's runtime manifest and
// walked that genre's block names — so it answered for the platformer and 404'd
// for every other recipe, and it was a manifest parser living in the viewer.
//
// The run view already carries what an inspector needs, for all six recipes and
// with no gameplay vocabulary: each node's declared artifacts with a portable
// ref, a digest, a byte count, a media type, whether the bytes are present, and
// a display kind from the engine's own closed vocabulary. Grouping those is the
// whole page. A run with no view has nothing to group and says so, rather than
// the viewer learning a second way to find files.

import Link from "next/link";
import { notFound } from "next/navigation";
import { errorBanner, h1, linkGhost, metaLine, page } from "@/app/ui";
import type {
  ArtifactDisplay,
  ExecutionView,
  ExecutionViewArtifact,
} from "@/lib/run-viewer/execution-view";
import { subjectLabel } from "@/lib/run-viewer/execution-view";
import { preparedAssetUrl } from "@/lib/shell/asset-url";
import { readExecutionView } from "@/lib/shell/execution-view";
import { isSafeRunTag } from "@/lib/shell/runs";

export const dynamic = "force-dynamic";

/** One artifact, with the node that declared it. */
interface Row {
  readonly artifact: ExecutionViewArtifact;
  readonly nodeId: string;
  readonly typeId: string;
}

/** Display order, most-looked-at first. The vocabulary is the engine's. */
const DISPLAY_ORDER: readonly ArtifactDisplay[] = [
  "image",
  "motion_atlas",
  "audio",
  "data",
  "text",
];

const DISPLAY_HEADING: Readonly<Record<ArtifactDisplay, string>> = {
  image: "images",
  motion_atlas: "motion atlases",
  audio: "audio",
  data: "data",
  text: "text",
};

function collect(view: ExecutionView): Map<ArtifactDisplay, Row[]> {
  const grouped = new Map<ArtifactDisplay, Row[]>();
  for (const node of view.nodes) {
    for (const artifact of node.artifacts) {
      const rows = grouped.get(artifact.display) ?? [];
      rows.push({ artifact, nodeId: node.nodeId, typeId: node.typeId });
      grouped.set(artifact.display, rows);
    }
  }
  for (const rows of grouped.values()) {
    rows.sort((a, b) => a.artifact.artifactRef.localeCompare(b.artifact.artifactRef));
  }
  return grouped;
}

function bytes(count: number): string {
  if (count < 1024) return `${count} B`;
  if (count < 1024 * 1024) return `${(count / 1024).toFixed(1)} KiB`;
  return `${(count / (1024 * 1024)).toFixed(1)} MiB`;
}

function ArtifactRow({ tag, row }: { tag: string; row: Row }) {
  const { artifact } = row;
  const url = preparedAssetUrl(tag, artifact.artifactRef);
  return (
    <li className="grid grid-cols-[64px_1fr_auto] items-center gap-3 border border-border px-2.5 py-1.5 max-[480px]:grid-cols-[48px_1fr]">
      <div className="flex h-12 w-16 items-center justify-center overflow-hidden bg-well text-dim">
        {artifact.present && (artifact.display === "image" || artifact.display === "motion_atlas") ? (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img className="h-full w-full object-contain" src={url} alt="" aria-hidden />
        ) : (
          <span aria-hidden>{artifact.present ? "·" : "×"}</span>
        )}
      </div>
      <div className="min-w-0">
        <div className="truncate text-[13px] text-fg">{artifact.artifactRef}</div>
        <div className="mt-0.5 truncate text-[11px] text-dim">
          {row.nodeId} · {artifact.mediaType} · {bytes(artifact.bytes)} ·{" "}
          <code>{artifact.sha256.slice(0, 12)}</code>
          {artifact.present ? "" : " · absent"}
        </div>
      </div>
      {artifact.present ? (
        <Link className={linkGhost} href={url}>
          [ open ]
        </Link>
      ) : null}
    </li>
  );
}

export default async function RunArtifactsPage({
  params,
}: {
  params: Promise<{ tag: string }>;
}) {
  const { tag } = await params;
  if (!isSafeRunTag(tag)) notFound();

  let view: ExecutionView | null = null;
  let refusal: string | null = null;
  try {
    view = await readExecutionView(tag);
  } catch (error) {
    refusal = error instanceof Error ? error.message : String(error);
  }

  const back = (
    <p className={metaLine}>
      <Link className="text-dim no-underline hover:text-accent" href={`/runs/${encodeURIComponent(tag)}`}>
        ← run
      </Link>
    </p>
  );

  if (refusal !== null) {
    return (
      <main className={page}>
        {back}
        <h1 className={h1}>{tag}</h1>
        <p className={errorBanner}>{refusal}</p>
      </main>
    );
  }
  if (view === null) {
    return (
      <main className={page}>
        {back}
        <h1 className={h1}>{tag}</h1>
        <p className={metaLine}>
          This run carries no execution view, so there is nothing to list. Derive
          one with <code>stage-gen export-view --run out/{tag}</code>; a run
          whose execution plan predates this build cannot be re-derived and keeps
          only its published document.
        </p>
      </main>
    );
  }

  const grouped = collect(view);
  const total = [...grouped.values()].reduce((sum, rows) => sum + rows.length, 0);
  const label = subjectLabel(view.subject);
  return (
    <main className={page}>
      {back}
      <h1 className={h1}>{tag}</h1>
      <p className={metaLine}>
        {label ? `${label} · ` : ""}
        {total} artifact{total === 1 ? "" : "s"} across {view.nodes.length} nodes
      </p>
      {DISPLAY_ORDER.filter((display) => grouped.has(display)).map((display, index) => {
        const rows = grouped.get(display) ?? [];
        return (
          <section
            key={display}
            className={index === 0 ? "mt-5" : "mt-8 border-t border-border pt-4"}
          >
            <div className="mb-2 text-[13px]">
              <span className="text-dim">{DISPLAY_HEADING[display]}</span>
              <span className="text-dim opacity-60"> · {rows.length}</span>
            </div>
            <ul className="flex list-none flex-col gap-1.5">
              {rows.map((row) => (
                <ArtifactRow key={`${row.nodeId}:${row.artifact.artifactRef}`} tag={tag} row={row} />
              ))}
            </ul>
          </section>
        );
      })}
      {total === 0 ? (
        <p className={metaLine}>This run declared no artifacts.</p>
      ) : null}
    </main>
  );
}
