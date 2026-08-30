"use client";

// What the floating panel shows: run facts and the exporter's gap list when
// nothing is selected, otherwise everything the view document holds about one
// node. Per-state, because a pending node has estimates where a finished one
// has artifacts.

import { useState } from "react";
import { cx, errorBanner, linkGhost, metaLine } from "@/app/ui";
import ImageLightbox, { type LightboxImage } from "@/app/generate/[tag]/ImageLightbox";
import {
  type ExecutionNodeState,
  type ExecutionRunLiveness,
  type ExecutionView,
  type ExecutionViewArtifact,
  type ExecutionViewNode,
  nodeStateLabel,
  RUN_LIVENESS_LABELS,
} from "@/lib/runtime/execution-view";
import { preparedAssetUrl } from "@/lib/runtime/prepared-manifest";
import MotionPlayer from "./MotionPlayer";

export const STATE_MARK: Record<ExecutionNodeState, string> = {
  pending: "·",
  running: "▸",
  succeeded: "✓",
  failed: "✗",
  skipped: "∅",
};

export function formatMs(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000) return `${ms}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${String(Math.round(seconds % 60)).padStart(2, "0")}s`;
}

export function formatUsd(value: number | null): string {
  return value === null ? "—" : `$${value.toFixed(2)}`;
}

function Fact({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[110px_minmax(0,1fr)] gap-2 border-b border-border px-2 py-1 text-xs last:border-b-0">
      <dt className="text-dim">{term}</dt>
      <dd className="m-0 wrap-anywhere">{children}</dd>
    </div>
  );
}

function SidecarDetail({ tag, artifactRef }: { tag: string; artifactRef: string }) {
  const [state, setState] = useState<"idle" | "loading" | "absent" | "failed">("idle");
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  if (detail) {
    const prompt = typeof detail.prompt === "string" ? detail.prompt : null;
    return (
      <div className="mt-1 border border-border p-1.5 text-[11px]">
        <p className="m-0 text-dim">
          {String(detail.provider ?? "?")} · {String(detail.model ?? "?")}
          {detail.seed != null ? ` · seed ${String(detail.seed)}` : ""}
        </p>
        {prompt ? (
          <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap text-fg">{prompt}</pre>
        ) : null}
      </div>
    );
  }
  return (
    <button
      type="button"
      className={cx(linkGhost, "mt-1 cursor-pointer")}
      disabled={state === "loading"}
      onClick={async () => {
        setState("loading");
        try {
          const response = await fetch(preparedAssetUrl(tag, `${artifactRef}.meta.json`));
          if (response.status === 404) {
            setState("absent");
            return;
          }
          if (!response.ok) throw new Error(String(response.status));
          setDetail((await response.json()) as Record<string, unknown>);
        } catch {
          setState("failed");
        }
      }}
    >
      {state === "absent"
        ? "no provenance sidecar"
        : state === "failed"
          ? "provenance unreadable"
          : state === "loading"
            ? "loading…"
            : "load provenance"}
    </button>
  );
}

function ArtifactCard({
  tag,
  artifact,
  onZoom,
}: {
  tag: string;
  artifact: ExecutionViewArtifact;
  onZoom: (image: LightboxImage) => void;
}) {
  const url = preparedAssetUrl(tag, artifact.artifactRef);
  return (
    <li className="border border-border p-1.5">
      <p className="m-0 truncate text-[11px] text-dim" title={artifact.artifactRef}>
        {artifact.artifactRef}
      </p>
      {!artifact.present ? (
        <p className="m-0 mt-1 text-[11px] text-dim">not on disk (pruned or elsewhere)</p>
      ) : artifact.display === "motion_atlas" && artifact.motion ? (
        <div className="mt-1">
          <MotionPlayer
            url={url}
            frameCount={artifact.motion.frameCount}
            framesPerSecond={artifact.motion.framesPerSecond}
            label={artifact.artifactRef}
          />
        </div>
      ) : artifact.display === "image" || artifact.display === "motion_atlas" ? (
        <button
          type="button"
          className="alpha-checker mt-1 flex aspect-square w-full cursor-pointer items-center justify-center overflow-hidden border border-border hover:border-fg"
          onClick={() =>
            onZoom({
              path: artifact.artifactRef,
              label: artifact.artifactRef,
              url,
              transparent: artifact.mediaType === "image/png",
            })
          }
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            className="max-h-full max-w-full object-contain [image-rendering:pixelated]"
            src={url}
            alt={artifact.artifactRef}
            loading="lazy"
          />
        </button>
      ) : artifact.display === "audio" ? (
        <audio className="mt-1 w-full" controls preload="metadata" src={url} />
      ) : (
        <a
          className={cx(linkGhost, "mt-1 inline-block")}
          href={url}
          target="_blank"
          rel="noreferrer"
        >
          {"{ } open"}
        </a>
      )}
      {artifact.present ? <SidecarDetail tag={tag} artifactRef={artifact.artifactRef} /> : null}
    </li>
  );
}

export function RunFacts({
  view,
  liveness,
}: {
  view: ExecutionView;
  liveness: ExecutionRunLiveness;
}) {
  return (
    <div className="p-3 text-xs">
      <dl className="m-0 border border-border">
        <Fact term="game">{view.gameId}</Fact>
        <Fact term="recipe">{view.recipe}</Fact>
        <Fact term="invocation">{view.invocationId ?? "—"}</Fact>
        <Fact term="result">{RUN_LIVENESS_LABELS[liveness]}</Fact>
        {view.runState === "unfinished" ? (
          <Fact term="last event">{view.traceModifiedAt ?? "—"}</Fact>
        ) : null}
        <Fact term="duration">{formatMs(view.durationMs)}</Fact>
        <Fact term="known cost">{formatUsd(view.knownCostUsd)}</Fact>
        <Fact term="graph">{view.graphSha256.slice(0, 12)}…</Fact>
      </dl>
      <h3 className="mt-4 mb-2 text-sm font-semibold">Exporter gaps</h3>
      <ul className="m-0 list-none space-y-1.5">
        {view.gaps.map((gap) => (
          <li key={gap.gapId} className="border border-border p-1.5">
            <span className="text-fg">{gap.gapId}</span>
            <p className="m-0 mt-0.5 text-dim">{gap.detail}</p>
          </li>
        ))}
      </ul>
      <p className="mt-4 text-dim">Click a node to inspect it.</p>
    </div>
  );
}

export default function NodeInspector({
  tag,
  node,
  liveness,
  onSelect,
}: {
  tag: string;
  node: ExecutionViewNode;
  liveness: ExecutionRunLiveness;
  onSelect: (nodeId: string) => void;
}) {
  const [lightbox, setLightbox] = useState<LightboxImage | null>(null);
  return (
    <div className="p-3 text-xs">
      <p className={cx(metaLine, "mb-1")}>
        {STATE_MARK[node.state]} {nodeStateLabel(node.state, liveness)} · {node.domain}
      </p>
      <p className="mt-0 mb-2 text-dim">{node.description}</p>
      {node.error ? <p className={errorBanner}>{node.error}</p> : null}
      <dl className="m-0 border border-border">
        <Fact term="operation">
          {node.operation}
          {node.provider ? ` · ${node.provider} / ${node.model}` : ""}
        </Fact>
        {node.state === "pending" || node.state === "running" ? (
          <Fact term="estimate">
            {node.estimatedDurationSeconds}s · ${node.estimatedCostLowUsd.toFixed(2)}–$
            {node.estimatedCostHighUsd.toFixed(2)}
          </Fact>
        ) : null}
        {node.startedOffsetMs !== null ? (
          <Fact term="started at">{formatMs(node.startedOffsetMs)}</Fact>
        ) : null}
        {node.durationMs !== null ? (
          <Fact term="ran for">
            {formatMs(node.durationMs)}
            {node.queueMs ? ` (+${formatMs(node.queueMs)} queued)` : ""}
          </Fact>
        ) : null}
        {node.cache !== null ? <Fact term="cache">{node.cache}</Fact> : null}
        {node.attempts !== null ? (
          <Fact term="attempts">
            {node.attempts}/{node.maxAttempts} · retry owner {node.retryOwner}
          </Fact>
        ) : null}
        {node.knownCostUsd !== null ? (
          <Fact term="known cost">{formatUsd(node.knownCostUsd)}</Fact>
        ) : null}
        {node.blockedBy.length > 0 ? (
          <Fact term="blocked by">
            {node.blockedBy.map((id) => (
              <button
                key={id}
                type="button"
                className="mr-1 cursor-pointer text-error underline"
                onClick={() => onSelect(id)}
              >
                {id}
              </button>
            ))}
          </Fact>
        ) : null}
        {node.dependsOn.length > 0 ? (
          <Fact term="depends on">
            {node.dependsOn.map((id) => (
              <button
                key={id}
                type="button"
                className="mr-1 cursor-pointer text-dim underline hover:text-fg"
                onClick={() => onSelect(id)}
              >
                {id}
              </button>
            ))}
          </Fact>
        ) : null}
        {node.state === "pending" || node.state === "running" ? (
          <Fact term="inputs">
            {node.inputSha256.length === 0
              ? "none"
              : node.inputSha256.map((digest) => digest.slice(0, 12)).join(", ")}
          </Fact>
        ) : null}
        {node.state === "pending" ? (
          <Fact term="will write">{node.outputs.join(", ") || "—"}</Fact>
        ) : null}
        <Fact term="cache key">{node.cacheKey.slice(0, 12)}…</Fact>
      </dl>
      {node.artifacts.length > 0 ? (
        <>
          <h4 className="mt-3 mb-1.5 text-xs font-semibold text-dim">
            artifacts ({node.artifacts.length})
          </h4>
          <ul className="m-0 list-none space-y-1.5">
            {node.artifacts.map((artifact) => (
              <ArtifactCard
                key={artifact.artifactRef}
                tag={tag}
                artifact={artifact}
                onZoom={setLightbox}
              />
            ))}
          </ul>
        </>
      ) : null}
      {lightbox ? <ImageLightbox asset={lightbox} onClose={() => setLightbox(null)} /> : null}
    </div>
  );
}
