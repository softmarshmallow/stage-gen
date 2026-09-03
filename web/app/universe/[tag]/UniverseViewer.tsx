"use client";

// The gallery reading surface.
//
// This page is for someone reading a world, not inspecting a run: the poster
// and the prose lead, the pictures are the body, and every production fact —
// which checks failed, what the planner sealed — is one deliberate click away
// behind the review panel and each entity's own notes.
//
// An entity the pipeline did not admit still appears, because a world with
// holes in it is the truth about this run. It carries a single red dot rather
// than a coloured frame, so the grid reads as artwork and the flag reads as a
// flag.

import Link from "next/link";
import Image from "next/image";
import { useMemo, useState } from "react";
import { cx, h1, linkGhost, metaLine, page, sectionHeading } from "@/app/ui";
import { preparedAssetUrl } from "@/lib/shell/asset-url";
import {
  type AdmittedUniverse,
  type GalleryManifest,
  REVIEW_CHECK_LABELS,
} from "@/lib/universe/contract";
import type { CheckTally, EntityCard } from "@/lib/universe/gallery-view";
import EntityDetail from "./EntityDetail";

function chipButton(active: boolean): string {
  return cx(
    "cursor-pointer border px-2.5 py-1 text-xs lowercase",
    active
      ? "border-accent text-accent"
      : "border-border text-dim hover:border-fg hover:text-fg",
  );
}

/** `─ label ───`, the shell's section rule. */
function Section({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h2 className={cx(sectionHeading, "text-[13px]")}>{label}</h2>
      {children}
    </section>
  );
}

function AnchorLinks({
  ids,
  names,
  onOpen,
}: {
  ids: readonly string[];
  names: ReadonlyMap<string, string>;
  onOpen: (entityId: string) => void;
}) {
  return (
    <>
      {ids.map((id) => (
        <button
          key={id}
          type="button"
          className="mr-2 cursor-pointer border-none bg-transparent p-0 text-[11px] text-dim underline decoration-border underline-offset-2 hover:text-accent"
          onClick={() => onOpen(id)}
        >
          {names.get(id) ?? id}
        </button>
      ))}
    </>
  );
}

export default function UniverseViewer({
  tag,
  manifest,
  universe,
  cards,
  classes,
  tallies,
  unreadableRecords,
  hasExecutionView,
}: {
  tag: string;
  manifest: GalleryManifest;
  universe: AdmittedUniverse;
  cards: readonly EntityCard[];
  classes: readonly string[];
  tallies: readonly CheckTally[];
  unreadableRecords: readonly {
    readonly entityId: string;
    readonly reason: string;
  }[];
  hasExecutionView: boolean;
}) {
  const [activeClass, setActiveClass] = useState<string>("all");
  const [hideFlagged, setHideFlagged] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);

  const names = useMemo(
    () => new Map(cards.map((card) => [card.entityId, card.displayName])),
    [cards],
  );
  const visible = useMemo(
    () =>
      cards.filter(
        (card) =>
          (activeClass === "all" || card.primaryClass === activeClass) &&
          (!hideFlagged || card.status === "admitted"),
      ),
    [cards, activeClass, hideFlagged],
  );
  const open =
    openId === null
      ? null
      : (cards.find((card) => card.entityId === openId) ?? null);
  const flagged = cards.filter((card) => card.status !== "admitted").length;
  const reviewed = cards.filter((card) => card.review !== null).length;

  return (
    <main className={cx(page, "max-w-[1400px]")}>
      <div className="mb-3 flex items-baseline justify-between gap-4">
        <p className={cx(metaLine, "mb-0")}>
          <Link
            className="text-dim no-underline hover:text-accent"
            href="/universe"
          >
            ← universes
          </Link>
        </p>
        {hasExecutionView ? (
          <Link className={linkGhost} href={`/runs/${encodeURIComponent(tag)}`}>
            [ ⌕ run view ]
          </Link>
        ) : (
          <span
            className="text-[11px] text-dim"
            title="this run carries no execution-view.json"
          >
            no trace
          </span>
        )}
      </div>

      <div className="grid grid-cols-[minmax(260px,380px)_minmax(0,1fr)] items-start gap-8 max-[720px]:grid-cols-[minmax(0,300px)] max-[720px]:gap-5">
        <div className="border border-border bg-well">
          <Image
            className="h-auto w-full"
            src={preparedAssetUrl(tag, manifest.inputs.posterProxyPath)}
            alt={`${universe.title} poster`}
            width={1024}
            height={1536}
            sizes="(max-width: 720px) 300px, 380px"
            priority
          />
        </div>
        <div className="min-w-0">
          <h1 className={cx(h1, "mb-1 text-[22px]")}>{universe.title}</h1>
          <p className={cx(metaLine, "mb-4")}>
            {manifest.mediumId.replace(/_/g, " ")} · {manifest.entityCount}{" "}
            entities
            {flagged > 0 ? ` · ${flagged} flagged` : ""}
          </p>
          <p className="mt-0 mb-3 max-w-[70ch] text-[14px] leading-relaxed">
            {universe.premise.claim}
          </p>
          <p className="mt-0 mb-0 max-w-[70ch] text-[14px] leading-relaxed">
            <span className="text-dim">Now. </span>
            {universe.presentState.claim}
          </p>

          <div className="mt-4 mb-1">
            <p className={cx(metaLine, "mb-1.5")}>
              {reviewed} of {manifest.entityCount} images judged
              {flagged > 0 ? ` · ${flagged} flagged` : ""}
              {unreadableRecords.length > 0
                ? ` · ${unreadableRecords.length} record${
                    unreadableRecords.length === 1 ? "" : "s"
                  } this build could not read`
                : ""}
            </p>
            <ul className="m-0 grid list-none grid-cols-2 gap-x-8 gap-y-1 p-0 max-[1080px]:grid-cols-1">
              {tallies.map((tally) => {
                const total = tally.passed + tally.failed + tally.other;
                const failedPercent =
                  total === 0 ? 0 : (tally.failed / total) * 100;
                return (
                  <li
                    key={tally.check}
                    className="grid grid-cols-[84px_1fr_auto] items-center gap-2"
                  >
                    <span className="truncate text-[11px] text-dim">
                      {REVIEW_CHECK_LABELS[tally.check]}
                    </span>
                    <span className="flex h-2 border border-border" aria-hidden>
                      <span
                        className="bg-error"
                        style={{ width: `${failedPercent}%` }}
                      />
                    </span>
                    <span
                      className={cx(
                        "text-[11px] tabular-nums",
                        tally.failed > 0 ? "text-error" : "text-dim",
                      )}
                    >
                      {tally.failed} fail
                    </span>
                  </li>
                );
              })}
            </ul>
            {unreadableRecords.length > 0 ? (
              <ul className="m-0 mt-1.5 list-none p-0 text-[11px] text-error">
                {unreadableRecords.map((failure) => (
                  <li key={failure.entityId}>
                    {failure.entityId}: {failure.reason}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>

          <Section label={`ways in · ${universe.viewpoints.length}`}>
            <ul className="m-0 list-none p-0 text-[13px]">
              {universe.viewpoints.map((viewpoint) => (
                <li key={viewpoint.viewpointId} className="mb-2.5 max-w-[95ch]">
                  <span className="text-fg">{viewpoint.displayName}</span>
                  <span className="text-dim"> — {viewpoint.summary}</span>
                  <div className="mt-0.5 text-[12px] text-dim italic">
                    {viewpoint.entryQuestion}
                  </div>
                  <div className="mt-1">
                    <AnchorLinks
                      ids={viewpoint.anchorEntityIds}
                      names={names}
                      onOpen={setOpenId}
                    />
                  </div>
                </li>
              ))}
            </ul>
          </Section>
        </div>
      </div>

      <Section
        label={`how the world works · ${universe.physicalEcologicalRules.length}`}
      >
        <ul className="m-0 max-w-[95ch] list-none p-0 text-[13px]">
          {universe.physicalEcologicalRules.map((rule) => (
            <li
              key={rule.claim}
              className="mb-1.5 border-l border-border pl-2.5"
            >
              {rule.claim}
            </li>
          ))}
        </ul>
      </Section>

      <Section
        label={`what people disagree about · ${universe.institutionalTensions.length}`}
      >
        <ul className="m-0 list-none p-0 text-[13px]">
          {universe.institutionalTensions.map((tension) => (
            <li
              key={tension.tensionId}
              className="mb-2.5 max-w-[95ch] border-l border-border pl-2.5"
            >
              <div className="text-fg">{tension.summary}</div>
              <div className="mt-0.5 text-dim">{tension.materialStakes}</div>
              <div className="mt-0.5 text-dim italic">
                {tension.competingLegitimateNeeds}
              </div>
              <div className="mt-1">
                <AnchorLinks
                  ids={tension.participantEntityIds}
                  names={names}
                  onOpen={setOpenId}
                />
              </div>
            </li>
          ))}
        </ul>
      </Section>

      <Section
        label={`open questions · ${universe.unresolvedQuestions.length}`}
      >
        <ul className="m-0 max-w-[95ch] list-none p-0 text-[13px]">
          {universe.unresolvedQuestions.map((question) => (
            <li
              key={question}
              className="mb-1.5 border-l border-border pl-2.5 text-dim"
            >
              {question}
            </li>
          ))}
        </ul>
      </Section>

      <Section label={`entities · ${visible.length}`}>
        <div className="mb-3 flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            className={chipButton(activeClass === "all")}
            onClick={() => setActiveClass("all")}
          >
            all
          </button>
          {classes.map((name) => (
            <button
              key={name}
              type="button"
              className={chipButton(activeClass === name)}
              onClick={() => setActiveClass(name)}
            >
              {name}
            </button>
          ))}
          {flagged > 0 ? (
            <>
              <span className="mx-1 text-border" aria-hidden>
                │
              </span>
              <button
                type="button"
                className={chipButton(hideFlagged)}
                onClick={() => setHideFlagged(!hideFlagged)}
              >
                hide flagged
              </button>
            </>
          ) : null}
        </div>

        <ul className="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-2.5 p-0 pb-16 max-[480px]:grid-cols-[repeat(auto-fill,minmax(150px,1fr))]">
          {visible.map((card) => (
            <li key={card.entityId}>
              <button
                type="button"
                className="flex w-full cursor-pointer flex-col border border-border bg-bg p-0 text-left hover:border-fg"
                onClick={() => setOpenId(card.entityId)}
              >
                <span className="relative flex aspect-[3/2] w-full items-center justify-center overflow-hidden bg-well">
                  {card.image ? (
                    <Image
                      className="h-full w-full object-cover"
                      src={preparedAssetUrl(tag, card.image)}
                      alt={card.displayName}
                      fill
                      sizes="(max-width: 480px) 50vw, 300px"
                    />
                  ) : (
                    <span className="text-dim" aria-hidden>
                      ·
                    </span>
                  )}
                  {card.status !== "admitted" ? (
                    <span
                      className="absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-error"
                      title={`flagged: ${card.status.replace(/_/g, " ")}`}
                    />
                  ) : null}
                </span>
                <span className="block w-full px-2 py-1.5">
                  <span className="block truncate text-[13px] text-fg">
                    {card.displayName}
                  </span>
                  <span className="mt-0.5 block truncate text-[11px] text-dim">
                    {card.primaryClass}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
        {visible.length === 0 ? (
          <p className="text-dim">Nothing matches those filters.</p>
        ) : null}
      </Section>

      {open ? (
        <EntityDetail
          tag={tag}
          card={open}
          names={names}
          onOpen={setOpenId}
          onClose={() => setOpenId(null)}
        />
      ) : null}
    </main>
  );
}
