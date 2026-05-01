"use client";

// Client island for the generation view. Owns:
//   - SSE subscription to /api/run/<tag>/events
//   - Current map of present filenames under out/<tag>/
//   - Live log buffer
//   - Pipeline status (running / done / failed)
//   - Lightbox open/close state
//
// Visual contract per DESIGN.md:
//   - Header strip with prompt + tag + Play CTA (right)
//   - Progress strip using █░ block characters as text
//   - Concept image full width once present
//   - Asset slot grid sectioned by family; loading.gif when absent
//   - Failed slots show red × + retry affordance
//   - Pipeline-fatal error → red banner above progress; CTA stays disabled
//   - Append-only log strip at bottom

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  expectedSlots,
  groupSlots,
  type SlotDef,
  type WorldSpecLite,
} from "@/lib/shell/slots";

interface InitialState {
  tag: string;
  prompt: string | null;
  status: "missing" | "running" | "done" | "failed";
  failedStage: string | null;
  spec: WorldSpecLite | null;
  present: string[];
}

interface LightboxState {
  filename: string;
  label: string;
  url: string;
  /** True for chroma-keyed sprite assets (everything except concept). */
  chromaKeyed: boolean;
  width?: number;
  height?: number;
}

const LOG_MAX = 500;

function progressBarText(filled: number, total: number, width = 24): {
  filled: string;
  rest: string;
} {
  if (total <= 0) return { filled: "", rest: "░".repeat(width) };
  const ratio = Math.max(0, Math.min(1, filled / total));
  const fillCount = Math.round(ratio * width);
  return {
    filled: "█".repeat(fillCount),
    rest: "░".repeat(width - fillCount),
  };
}

function isChromaKeyed(filename: string): boolean {
  // Only the concept image and the opaque skybox layer are NOT chroma-keyed.
  // Conservatively: concept and the run.json are not; everything else is.
  if (filename.startsWith("concept_")) return false;
  if (filename.endsWith(".json")) return false;
  return true;
}

function extractMatchedFilename(
  slot: SlotDef,
  present: Set<string>,
): string | null {
  for (const f of slot.filenames) if (present.has(f)) return f;
  return null;
}

export default function GenerateView({ initial }: { initial: InitialState }) {
  const { tag } = initial;

  const [present, setPresent] = useState<Set<string>>(
    () => new Set(initial.present),
  );
  const [spec, setSpec] = useState<WorldSpecLite | null>(initial.spec);
  const [status, setStatus] = useState<InitialState["status"]>(initial.status);
  const [failedStage, setFailedStage] = useState<string | null>(
    initial.failedStage,
  );
  const [logLines, setLogLines] = useState<string[]>([]);
  const [lightbox, setLightbox] = useState<LightboxState | null>(null);
  const [showAlpha, setShowAlpha] = useState(false);
  const [retrying, setRetrying] = useState<Set<string>>(new Set());
  const logRef = useRef<HTMLDivElement>(null);

  // Subscribe to SSE while the run could still progress. If the initial
  // status is "done" we still open the connection briefly (it'll close
  // itself), to absorb any post-processing files that landed since the
  // server snapshot.
  useEffect(() => {
    if (status === "missing") return;
    const es = new EventSource(`/api/run/${tag}/events`);

    es.addEventListener("present", (ev: MessageEvent) => {
      try {
        const data = JSON.parse(ev.data) as { files: string[] };
        setPresent((prev) => {
          const next = new Set(prev);
          for (const f of data.files) next.add(f);
          // Files might also be deleted (retry path) — sync exact set.
          for (const f of [...next]) {
            if (!data.files.includes(f)) next.delete(f);
          }
          return next;
        });
        // If the world spec just landed, hot-load it so the slot grid
        // reshapes to the agent's invented layer ids.
        const specName = `world_spec_${tag}.json`;
        if (data.files.includes(specName) && !spec) {
          fetch(`/api/assets/${tag}/${specName}`)
            .then((r) => (r.ok ? r.json() : null))
            .then((parsed) => {
              if (parsed) {
                setSpec({
                  layers: parsed.layers ?? [],
                  mobs: parsed.mobs ?? [],
                  obstacles: parsed.obstacles ?? [],
                  items: parsed.items ?? [],
                });
              }
            })
            .catch(() => {});
        }
      } catch {
        // ignore
      }
    });

    es.addEventListener("log", (ev: MessageEvent) => {
      try {
        const data = JSON.parse(ev.data) as { line: string };
        setLogLines((prev) => {
          const next = [...prev, data.line];
          if (next.length > LOG_MAX) next.splice(0, next.length - LOG_MAX);
          return next;
        });
      } catch {
        // ignore
      }
    });

    es.addEventListener("pipeline-done", (ev: MessageEvent) => {
      try {
        const data = JSON.parse(ev.data) as {
          ok: boolean;
          failedStage: string | null;
        };
        setStatus(data.ok ? "done" : "failed");
        setFailedStage(data.failedStage);
      } catch {
        // ignore
      }
    });

    es.onerror = () => {
      // Browser will auto-reconnect on transient network blip; we close
      // explicitly only on unmount.
    };

    return () => {
      es.close();
    };
  }, [tag, status, spec]);

  // Auto-scroll log to bottom on new lines.
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logLines.length]);

  // Esc closes the lightbox.
  useEffect(() => {
    if (!lightbox) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setLightbox(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [lightbox]);

  // Build the canonical slot list. spec change re-derives it.
  const slots = useMemo(() => expectedSlots(tag, spec), [tag, spec]);
  const grouped = useMemo(() => groupSlots(slots), [slots]);

  // Concept image gets a banner of its own — lift it out of the grid.
  const conceptSlot = slots.find((s) => s.id === "concept")!;
  const nonConceptGroups = grouped
    .map((g) => ({
      ...g,
      slots: g.slots.filter((s) => s.id !== "concept"),
    }))
    .filter((g) => g.slots.length > 0);

  const conceptFile = extractMatchedFilename(conceptSlot, present);

  // Progress = matched-file count / total-slot count.
  const matchedCount = slots.filter((s) =>
    extractMatchedFilename(s, present),
  ).length;
  const totalCount = slots.length;
  const pct =
    totalCount === 0 ? 0 : Math.round((matchedCount / totalCount) * 100);
  const bar = progressBarText(matchedCount, totalCount, 24);

  const playReady = status === "done";

  function openLightbox(slot: SlotDef, filename: string) {
    const url = `/api/assets/${tag}/${filename}`;
    setShowAlpha(false);
    setLightbox({
      filename,
      label: slot.label,
      url,
      chromaKeyed: isChromaKeyed(filename),
    });
  }

  async function onRetry(slot: SlotDef) {
    const filename = slot.filenames[0];
    if (!filename) return;
    if (retrying.has(filename)) return;
    setRetrying((prev) => new Set(prev).add(filename));
    try {
      await fetch(`/api/run/${tag}/retry`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ asset: filename }),
      });
      // Returning to a "running" state lets the SSE re-open and pick up
      // the new file when it lands.
      setStatus("running");
      setFailedStage(null);
    } finally {
      setRetrying((prev) => {
        const next = new Set(prev);
        next.delete(filename);
        return next;
      });
    }
  }

  // A slot is "failed" if the run is fatally failed AND its file isn't on
  // disk. We don't try to enumerate per-stage failures — that's coarser
  // than ideal but matches what the orchestrator currently surfaces.
  function slotFailed(slot: SlotDef): boolean {
    if (status !== "failed") return false;
    return extractMatchedFilename(slot, present) === null;
  }

  return (
    <main className="sg-page">
      <div className="sg-meta-line">
        <Link href="/">stage-gen</Link> /{" "}
        <span style={{ color: "var(--fg)" }}>
          {initial.prompt ?? "(unknown prompt)"}
        </span>
      </div>

      <div className="sg-header-strip">
        <div>
          <div className="sg-meta-line">
            tag: <span style={{ color: "var(--fg)" }}>{tag}</span>
          </div>
          <div className="sg-meta-line">
            status: <span style={{ color: "var(--fg)" }}>{status}</span>
            {failedStage ? ` (${failedStage})` : ""}
          </div>
        </div>
        <Link
          href={playReady ? `/play/${tag}` : "#"}
          className={`sg-play${playReady ? " is-active" : ""}`}
          aria-disabled={!playReady}
          tabIndex={playReady ? 0 : -1}
          data-testid="play-cta"
          onClick={(e) => {
            if (!playReady) e.preventDefault();
          }}
        >
          [ play ▸ ]
        </Link>
      </div>

      {status === "failed" ? (
        <div className="sg-error-banner" role="alert">
          pipeline failed{failedStage ? ` at stage ${failedStage}` : ""}.
          check log below for details. retry individual assets via the slot
          retry button, or restart the whole run from the picker.
        </div>
      ) : null}

      <div className="sg-progress" data-testid="progress">
        <span>progress: </span>
        <span className="sg-progress-fill">{bar.filled}</span>
        <span>{bar.rest}</span>
        <span>
          {"  "}
          {matchedCount} / {totalCount} ({pct}%)
        </span>
      </div>

      {/* Concept image full-width banner — DESIGN.md: appears the moment
          it's ready, full-size at the top of the page. */}
      <div className="sg-concept-banner">
        {conceptFile ? (
          <button
            type="button"
            style={{
              all: "unset",
              cursor: "pointer",
              width: "100%",
              display: "block",
            }}
            onClick={() => openLightbox(conceptSlot, conceptFile)}
            aria-label="open world concept fullscreen"
          >
            <img
              src={`/api/assets/${tag}/${conceptFile}`}
              alt={conceptSlot.label}
            />
          </button>
        ) : (
          <img className="is-loading" src="/loading.gif" alt="loading" />
        )}
      </div>

      {nonConceptGroups.map((g) => (
        <section key={g.section}>
          <div className="sg-section-h">{g.section}</div>
          <div className="sg-grid">
            {g.slots.map((slot) => {
              const matched = extractMatchedFilename(slot, present);
              const failed = slotFailed(slot);
              return (
                <div key={slot.id}>
                  <button
                    type="button"
                    className={`sg-slot${failed ? " is-failed" : ""}${
                      matched ? " is-active" : ""
                    }`}
                    onClick={() => {
                      if (matched) openLightbox(slot, matched);
                      else if (failed) onRetry(slot);
                    }}
                    disabled={!matched && !failed}
                    aria-label={
                      matched
                        ? `${slot.label} — ${matched}`
                        : failed
                          ? `${slot.label} failed; click to retry`
                          : `${slot.label} loading`
                    }
                  >
                    <div className="sg-slot-inner">
                      {matched ? (
                        <img
                          className="sg-slot-img"
                          src={`/api/assets/${tag}/${matched}`}
                          alt={slot.label}
                        />
                      ) : failed ? (
                        <span className="sg-slot-fail" aria-hidden>
                          ×
                        </span>
                      ) : (
                        <img
                          className="sg-slot-loading"
                          src="/loading.gif"
                          alt="loading"
                        />
                      )}
                    </div>
                    <div className="sg-slot-label">
                      {slot.label}
                      {failed
                        ? retrying.has(slot.filenames[0] ?? "")
                          ? " (retrying…)"
                          : " (retry)"
                        : ""}
                    </div>
                  </button>
                </div>
              );
            })}
          </div>
        </section>
      ))}

      <div className="sg-log" ref={logRef} data-testid="log">
        {logLines.length === 0 ? (
          <div className="sg-log-line">
            (no log lines yet — waiting for pipeline output…)
          </div>
        ) : (
          logLines.map((line, i) => (
            <div className="sg-log-line" key={i}>
              {line}
            </div>
          ))
        )}
      </div>

      {lightbox ? (
        <div
          className="sg-lightbox"
          role="dialog"
          aria-modal="true"
          onClick={(e) => {
            // Click-anywhere-to-dismiss, but ignore clicks inside the meta
            // strip (where the toggle lives).
            if ((e.target as HTMLElement).closest(".sg-lightbox-meta"))
              return;
            setLightbox(null);
          }}
        >
          <img
            className={`sg-lightbox-img${
              lightbox.chromaKeyed && showAlpha ? " alpha-checker" : ""
            }`}
            src={lightbox.url}
            alt={lightbox.label}
            style={
              lightbox.chromaKeyed && showAlpha
                ? {
                    // crude chroma-key preview: rely on the checker bg + the
                    // browser's blend; we don't actually strip pixels here.
                  }
                : undefined
            }
            onLoad={(e) => {
              const img = e.currentTarget;
              setLightbox((prev) =>
                prev
                  ? {
                      ...prev,
                      width: img.naturalWidth,
                      height: img.naturalHeight,
                    }
                  : prev,
              );
            }}
          />
          <div className="sg-lightbox-meta">
            <span>{lightbox.filename}</span>
            {lightbox.width && lightbox.height ? (
              <span>
                {lightbox.width}×{lightbox.height}
              </span>
            ) : null}
            {lightbox.chromaKeyed ? (
              <button
                type="button"
                className="sg-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  setShowAlpha((s) => !s);
                }}
              >
                [ {showAlpha ? "hide" : "show"} alpha ]
              </button>
            ) : null}
            <span style={{ color: "var(--dim)" }}>(esc to close)</span>
          </div>
        </div>
      ) : null}
    </main>
  );
}
