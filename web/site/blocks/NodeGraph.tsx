// The node graph section: one <section> per stage with its node cards, which the graph
// player lays out with ELK. Port of the retired showcase's `node_graph` and `node_card`
// components (with NOT_NEEDED). It reads page.data.steps (the stages, node ids in order) and
// page.data.outputNode.
//
// The showcase's stages held `rows`, several rows of cards per stage. The catalog's steps
// are flat, so each stage is one row here. The rows only shaped the stage before ELK placed
// its cards (the player then turns every row into `display: contents`), and the cards keep
// their order, which is the model order ELK is asked to respect.

import type { ReactElement } from "react";
import type { Page, PageStep, Picture } from "@/lib/page";
import { picture } from "@/lib/page";
import { NOT_NEEDED } from "./drawer";
import { clock, Framed, inline, MdxError, money } from "./shared";

/** The rows of cards a stage shows: one, in node order (see the note at the top). */
function rowsOf(step: PageStep): readonly (readonly string[])[] {
  return [step.nodes];
}

function NodeCard({ page, nodeId }: { page: Page; nodeId: string }): ReactElement {
  const n = page.node(nodeId);
  const idle = Boolean(n.notNeeded);
  let status: ReactElement | null = null;
  if (n.verdict) {
    status = n.verdict.accepted ? (
      <span className="text-[11px] text-emerald-700 dark:text-emerald-400">✓ accepted</span>
    ) : (
      <span className="text-[11px] text-red-600 dark:text-red-400">✗ refused</span>
    );
  } else if (n.checks.length > 0 && !idle) {
    status = n.checks.every((c) => c.passed) ? (
      <span className="text-[11px] text-emerald-700 dark:text-emerald-400">✓ checked</span>
    ) : (
      <span className="text-[11px] text-red-600 dark:text-red-400">✗ check failed</span>
    );
  } else if (n.state === "failed") {
    status = <span className="text-[11px] text-red-600 dark:text-red-400">failed</span>;
  }
  let thumb = n.thumb;
  if (thumb === null && n.kind === "Reviewer" && !idle) {
    thumb = n.dependsOn.map((d) => page.node(d).thumb).find((t) => t) ?? null; // what it judged
  }
  if (n.kind === "Gate" && nodeId !== page.data.outputNode) thumb = null;
  const shown: Picture | null = thumb && !idle ? picture(thumb, `${nodeId} thumb`) : null;
  let foot: ReactElement;
  let frame: string;
  if (idle) {
    foot = (
      <p className="text-[11px] leading-snug text-zinc-400">
        {NOT_NEEDED[n.notNeeded ?? ""] ?? "Not needed"}
      </p>
    );
    frame = "border-dashed border-zinc-300 bg-transparent text-zinc-400 dark:border-zinc-700";
  } else {
    const bits = [n.model, clock(n.durationMs), money(n.costUsd)].filter((b): b is string => Boolean(b));
    foot = <p className="text-[11px] leading-snug text-zinc-500">{bits.join(" · ")}</p>;
    frame =
      "border-zinc-200 bg-white hover:border-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:border-zinc-600";
  }
  return (
    <button
      className={`node relative z-[2] flex w-48 flex-col gap-1.5 rounded-sm border p-2.5 text-left ${frame}`}
      data-node={nodeId}
      id={`node-${nodeId}`}
    >
      <span className="flex items-center justify-between">
        <span className="text-[11px] text-zinc-400">{n.kind}</span>
        {status}
      </span>
      <span className="text-[13px] font-medium leading-snug">{page.titleOf(nodeId)}</span>
      {shown === null ? null : <Framed picture={shown} cls="aspect-[16/10] w-full" />}
      {foot}
    </button>
  );
}

export default function NodeGraph({ page }: { page: Page }): ReactElement {
  // A workflow step none of this example's nodes ran in (an example made with an earlier
  // version) has nothing to show; the showcase's stages were never empty.
  const stages = page.data.steps.filter((s) => s.nodes.length > 0);
  const nodes = Object.keys(page.record.nodes);
  const placed = stages.flatMap((s) => rowsOf(s).flat());
  const sorted = (ids: Iterable<string>) => [...new Set(ids)].sort();
  const missing = sorted(nodes.filter((nid) => !placed.includes(nid)));
  const unknown = sorted(placed.filter((nid) => !nodes.includes(nid)));
  const doubled = sorted(placed.filter((nid, i) => placed.indexOf(nid) !== i));
  if (missing.length || unknown.length || doubled.length) {
    const list = (ids: string[]) => `[${ids.map((id) => `'${id}'`).join(", ")}]`;
    throw new MdxError(
      `stages must place every node once: unplaced ${list(missing)}, unknown ${list(unknown)}, doubled ${list(doubled)}`,
    );
  }
  return (
    <>
      {stages.map((s, index) => (
        <section
          key={index}
          className="w-min rounded-sm border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950"
        >
          <header className="mb-4">
            <h3 className="text-sm font-medium">{s.label}</h3>
            <p className="mt-1 text-xs leading-snug text-zinc-500">{inline(s.note)}</p>
          </header>
          {rowsOf(s).map((row, r) => (
            <div key={r} className="mt-4 flex items-start gap-5 first-of-type:mt-0">
              {row.map((nid) => (
                <NodeCard key={nid} page={page} nodeId={nid} />
              ))}
            </div>
          ))}
        </section>
      ))}
    </>
  );
}
