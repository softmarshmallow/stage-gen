"use client";

// One entity, opened over the grid.
//
// The right column reads as an encyclopaedia page: what this is, how it works
// or lives, what it is caught in, the facts behind those claims, and who it is
// connected to — each connection a way further into the world rather than a
// dead reference. Production notes are real and kept, but they are a
// disclosure at the bottom, because they answer a question a reader did not
// ask.

import Image from "next/image";
import { useEffect } from "react";
import { createPortal } from "react-dom";
import { cx } from "@/app/ui";
import { preparedAssetUrl } from "@/lib/shell/asset-url";
import { REVIEW_CHECK_LABELS, REVIEW_CHECKS } from "@/lib/universe/contract";
import type { EntityCard } from "@/lib/universe/gallery-view";

/** Concept images are opaque compositions; this is the recipe's widest plan. */
const FALLBACK_WIDTH = 2560;
const FALLBACK_HEIGHT = 1712;

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-3">
      <div className="mb-0.5 text-[11px] text-dim">{label}</div>
      <div className="text-[13px] leading-relaxed">{children}</div>
    </div>
  );
}

/** A quieter label/value pair, for the production disclosure. */
function Note({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-2">
      <span className="text-[11px] text-dim">{label} </span>
      <span className="text-[12px] text-dim">{children}</span>
    </div>
  );
}

export default function EntityDetail({
  tag,
  card,
  names,
  onOpen,
  onClose,
}: {
  tag: string;
  card: EntityCard;
  names: ReadonlyMap<string, string>;
  onOpen: (entityId: string) => void;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const register = card.plan?.sceneRegister;
  const registerText = register
    ? [
        register.scale,
        register.timeOfDay,
        register.weather,
        register.setting,
        register.population,
        register.energy,
      ]
        .filter((value) => value.length > 0)
        .join(" · ")
    : "";

  const overlay = (
    <div
      className="fixed inset-0 z-[100] flex bg-black/85 p-6 backdrop-blur-sm max-[900px]:p-0"
      role="dialog"
      aria-modal="true"
      aria-label={card.displayName}
      onClick={onClose}
    >
      <div
        className="m-auto flex max-h-full w-full max-w-[1600px] border border-border bg-bg max-[900px]:h-full max-[900px]:flex-col"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex min-w-0 flex-[3] items-center justify-center overflow-hidden bg-well max-[900px]:flex-none">
          {card.image ? (
            <Image
              className="max-h-full w-full object-contain"
              src={preparedAssetUrl(tag, card.image)}
              alt={card.displayName}
              width={card.imageWidth ?? FALLBACK_WIDTH}
              height={card.imageHeight ?? FALLBACK_HEIGHT}
              sizes="(max-width: 900px) 100vw, 60vw"
            />
          ) : (
            <span className="p-16 text-dim">
              no image was produced for this entity
            </span>
          )}
        </div>

        <div className="min-w-0 flex-[2] overflow-y-auto border-l border-border p-5 max-[900px]:border-t max-[900px]:border-l-0">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                {card.status !== "admitted" ? (
                  <span
                    className="h-2 w-2 shrink-0 rounded-full bg-error"
                    title={`flagged: ${card.status.replace(/_/g, " ")}`}
                  />
                ) : null}
                <span className="text-[17px] text-fg">{card.displayName}</span>
              </div>
              <div className="mt-1 text-[11px] text-dim">
                {[card.primaryClass, ...card.facets].join(" · ")}
                {card.entityKind ? ` · ${card.entityKind}` : ""}
              </div>
            </div>
            <button
              type="button"
              className="shrink-0 cursor-pointer border border-border px-2 py-0.5 text-xs text-dim hover:border-fg hover:text-fg"
              onClick={onClose}
            >
              esc
            </button>
          </div>

          <Field label="summary">{card.summary}</Field>
          {card.howItWorksOrLives ? (
            <Field label="how it works or lives">
              {card.howItWorksOrLives}
            </Field>
          ) : null}
          {card.presentTension ? (
            <Field label="present tension">{card.presentTension}</Field>
          ) : null}

          {card.facts.length > 0 ? (
            <Field label={`facts · ${card.facts.length}`}>
              <ul className="m-0 list-none p-0">
                {card.facts.map((fact) => (
                  <li
                    key={fact.claim}
                    className="mb-1.5 border-l border-border pl-2"
                  >
                    {fact.claim}
                  </li>
                ))}
              </ul>
            </Field>
          ) : null}

          {card.relationships.length > 0 ? (
            <Field label={`connections · ${card.relationships.length}`}>
              <ul className="m-0 list-none p-0">
                {card.relationships.map((edge, index) => (
                  <li
                    key={`${edge.otherEntityId}-${edge.kind}-${index}`}
                    className="mb-1.5"
                  >
                    <span className="mr-1 text-[11px] text-dim">
                      {edge.outgoing ? "→" : "←"} {edge.kind.replace(/_/g, " ")}
                    </span>
                    <button
                      type="button"
                      className="cursor-pointer border-none bg-transparent p-0 text-fg underline decoration-border underline-offset-2 hover:text-accent"
                      onClick={() => onOpen(edge.otherEntityId)}
                    >
                      {names.get(edge.otherEntityId) ?? edge.otherEntityId}
                    </button>
                    <span className="text-dim"> {edge.summary}</span>
                  </li>
                ))}
              </ul>
            </Field>
          ) : null}

          {card.markers.length > 0 ? (
            <Field label={`identity markers · ${card.markers.length}`}>
              <ul className="m-0 list-none p-0">
                {card.markers.map((marker) => (
                  <li
                    key={marker.markerId}
                    className="mb-1.5 border-l border-border pl-2"
                  >
                    <span className="text-fg">{marker.form}</span>
                    <span className="text-dim"> — {marker.meaning}</span>
                  </li>
                ))}
              </ul>
            </Field>
          ) : null}

          {card.review?.whatTheImageTeaches ? (
            <Field label="what this picture teaches on its own">
              {card.review.whatTheImageTeaches}
            </Field>
          ) : null}

          {/* Everything below is about how the picture was made and judged. A
              reader never has to open it; a producer always can. */}
          {card.plan || card.direction || card.review ? (
            <details className="mt-4 border-t border-border pt-3">
              <summary className="cursor-pointer text-[11px] text-dim hover:text-fg">
                production notes
                {card.status !== "admitted" ? (
                  <span className="text-error"> · flagged</span>
                ) : null}
              </summary>
              <div className="mt-3">
                {card.status !== "admitted" ? (
                  <div className="mb-3 border border-error px-2 py-1 text-[11px] text-error">
                    {card.status.replace(/_/g, " ")}
                    {card.reason ? ` · ${card.reason}` : ""}
                  </div>
                ) : null}

                {card.plan ? (
                  <>
                    <Note label="purpose">
                      {card.plan.primaryPurpose.replace(/_/g, " ")}
                      {card.plan.audienceQuestion
                        ? ` · ${card.plan.audienceQuestion}`
                        : ""}
                    </Note>
                    {registerText ? (
                      <Note label="sealed register">{registerText}</Note>
                    ) : null}
                    {card.plan.signatureMotif ? (
                      <Note label="signature motif">
                        {[
                          card.plan.signatureMotif.actionVerb,
                          card.plan.signatureMotif.dominantProp,
                          card.plan.signatureMotif.vantage,
                        ]
                          .map((stroke) => stroke.replace(/_/g, " "))
                          .join(" / ")}
                      </Note>
                    ) : null}
                    {card.plan.scenePremise ? (
                      <Note label="scene premise">
                        {card.plan.scenePremise}
                      </Note>
                    ) : null}
                    {card.plan.inFrameContrast ? (
                      <Note label="in-frame contrast">
                        {card.plan.inFrameContrast}
                      </Note>
                    ) : null}
                  </>
                ) : null}

                {card.direction ? (
                  <Note label="visible state change">
                    {card.direction.actionBeat.visibleStateChange}
                  </Note>
                ) : null}

                {card.review ? (
                  <>
                    <ul className="m-0 mt-3 mb-2 flex list-none flex-wrap gap-1 p-0">
                      {REVIEW_CHECKS.map((check) => {
                        const value = card.review?.checks[check] ?? "";
                        if (value === "") return null;
                        return (
                          <li
                            key={check}
                            className={cx(
                              "border px-1.5 py-0.5 text-[10px]",
                              value === "pass"
                                ? "border-border text-dim"
                                : "border-error text-error",
                            )}
                          >
                            {REVIEW_CHECK_LABELS[check]}
                          </li>
                        );
                      })}
                    </ul>
                    {card.review.blockingFindings.length > 0 ? (
                      <ul className="m-0 mb-2 list-none p-0 text-[12px] text-error">
                        {card.review.blockingFindings.map((finding) => (
                          <li
                            key={finding}
                            className="mb-1 border-l border-error pl-2"
                          >
                            {finding}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                    {card.review.advisoryFindings.length > 0 ? (
                      <ul className="m-0 list-none p-0 text-[12px] text-dim">
                        {card.review.advisoryFindings.map((finding) => (
                          <li
                            key={finding}
                            className="mb-1 border-l border-border pl-2"
                          >
                            {finding}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </>
                ) : null}

                {card.image ? (
                  <a
                    className="mt-3 inline-block border border-border px-2.5 py-1 text-xs text-dim no-underline hover:border-fg hover:text-fg"
                    href={preparedAssetUrl(tag, card.image)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    [ open original ]
                  </a>
                ) : null}
              </div>
            </details>
          ) : null}
        </div>
      </div>
    </div>
  );

  return createPortal(overlay, document.body);
}
