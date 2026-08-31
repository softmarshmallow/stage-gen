"use client";

// What the floating panel shows: run facts and the exporter's gap list when
// nothing is selected, otherwise everything the view document holds about one
// node. Per-state, because a pending node has estimates where a finished one
// has artifacts — and per-archetype, because a node's *definition* differs in
// kind: an image node is defined by a prompt and the artwork it was shown, a
// judge by a schema and the answer it wrote, a package node by its ports.

import { useState } from "react";
import { cx, errorBanner, linkGhost, metaLine } from "@/app/ui";
import ImageLightbox, { type LightboxImage } from "@/app/ImageLightbox";
import {
  type ExecutionNodeState,
  type ExecutionRunLiveness,
  type ExecutionView,
  type ExecutionViewArtifact,
  type ExecutionViewNode,
  type ExecutionViewPort,
  nodeStateLabel,
  RUN_LIVENESS_LABELS,
  subjectLabel,
} from "@/lib/run-viewer/execution-view";
import {
  isPrompted,
  nodeHeading,
  type ResolvedAuthoredInput,
  type ResolvedReference,
  resolveAuthoredInputs,
  resolveReferenceInputs,
  sidecarRefFor,
  verdictPort,
} from "@/lib/run-viewer/execution-view-node";
import {
  hasVerdictContent,
  parseReviewVerdict,
  type ReviewOutcome,
  type ReviewVerdict,
} from "@/lib/run-viewer/execution-view-verdict";
import { preparedAssetUrl } from "@/lib/manifest/prepared-manifest";
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

/** A labelled scrap of node identity: `template inventory_grid_4x2_v1`. */
function Tag({ term, value }: { term: string; value: string }) {
  return (
    <span className="inline-flex max-w-full items-baseline gap-1 border border-border px-1.5 py-0.5 text-[11px]">
      <span className="shrink-0 text-dim">{term}</span>
      <span className="truncate text-fg" title={value}>
        {value}
      </span>
    </span>
  );
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return <h4 className="mt-3 mb-1.5 text-xs font-semibold text-dim">{children}</h4>;
}

function SidecarDetail({ tag, sidecarRef }: { tag: string; sidecarRef: string }) {
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
          const response = await fetch(preparedAssetUrl(tag, sidecarRef));
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
  sidecarRef,
  onZoom,
}: {
  tag: string;
  artifact: ExecutionViewArtifact;
  /** The node's declared pairing, so provenance is fetched and not guessed. */
  sidecarRef: string;
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
      {artifact.present ? <SidecarDetail tag={tag} sidecarRef={sidecarRef} /> : null}
    </li>
  );
}

/** One derived input: the upstream artwork this node was actually shown. */
function ReferenceInput({
  tag,
  resolved,
  onSelect,
  onZoom,
}: {
  tag: string;
  resolved: ResolvedReference;
  onSelect: (nodeId: string) => void;
  onZoom: (image: LightboxImage) => void;
}) {
  const { reference, port, artifact } = resolved;
  const url = artifact ? preparedAssetUrl(tag, artifact.artifactRef) : null;
  const isPicture =
    artifact !== null &&
    artifact.present &&
    (artifact.display === "image" || artifact.display === "motion_atlas");
  return (
    <li className="flex items-start gap-2 border border-border p-1.5">
      {isPicture && url && artifact ? (
        <button
          type="button"
          className="alpha-checker flex size-14 shrink-0 cursor-pointer items-center justify-center overflow-hidden border border-border hover:border-fg"
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
      ) : null}
      <div className="min-w-0 flex-1 text-[11px]">
        <button
          type="button"
          className="cursor-pointer truncate text-dim underline hover:text-fg"
          onClick={() => onSelect(reference.nodeId)}
        >
          {reference.nodeId}
        </button>
        <p className="m-0 truncate text-dim">
          <span className="text-fg">{reference.portId}</span>
          {port ? ` · ${port.kind}` : " · undeclared port"}
        </p>
        {port ? (
          <p className="m-0 truncate text-dim" title={port.artifactRef}>
            {port.artifactRef}
          </p>
        ) : null}
        {port && artifact === null ? <p className="m-0 text-dim">not written yet</p> : null}
        {artifact && !artifact.present ? (
          <p className="m-0 text-dim">not on disk (pruned or elsewhere)</p>
        ) : null}
      </div>
    </li>
  );
}

/**
 * One authored input: a package member the node is handed that nothing
 * upstream produced. It has no source node to jump to, so it shows the file,
 * its digest, and — when the run republished those exact bytes — the picture
 * the node was actually given.
 */
function AuthoredInputEntry({
  tag,
  resolved,
  onZoom,
}: {
  tag: string;
  resolved: ResolvedAuthoredInput;
  onZoom: (image: LightboxImage) => void;
}) {
  const { input, artifact } = resolved;
  const url = artifact?.present ? preparedAssetUrl(tag, artifact.artifactRef) : null;
  const isPicture = artifact !== null && artifact.present && artifact.display === "image";
  return (
    <li className="flex items-start gap-2 border border-border p-1.5">
      {isPicture && url && artifact ? (
        <button
          type="button"
          className="alpha-checker flex size-14 shrink-0 cursor-pointer items-center justify-center overflow-hidden border border-border hover:border-fg"
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
            className="max-h-full max-w-full object-contain"
            src={url}
            alt={input.ref}
            loading="lazy"
          />
        </button>
      ) : null}
      <div className="min-w-0 flex-1 text-[11px]">
        <p className="m-0 truncate text-fg">{input.label}</p>
        <p className="m-0 truncate text-dim" title={input.ref}>
          {input.ref}
        </p>
        <p className="m-0 truncate text-dim">sha256 {input.sha256.slice(0, 12)}</p>
        {artifact === null ? <p className="m-0 text-dim">authored, not republished</p> : null}
      </div>
    </li>
  );
}

/** The node's declared outputs, whether or not the run has written them. */
function PortList({ ports }: { ports: readonly ExecutionViewPort[] }) {
  return (
    <ul className="m-0 list-none space-y-1">
      {ports.map((port) => (
        <li key={port.portId} className="border border-border px-1.5 py-1 text-[11px]">
          <p className="m-0">
            <span className="text-fg">{port.portId}</span>{" "}
            <span className="text-dim">{port.kind}</span>
          </p>
          <p className="m-0 truncate text-dim" title={port.artifactRef}>
            {port.artifactRef}
          </p>
        </li>
      ))}
    </ul>
  );
}

const VERDICT_BADGE: Record<ReviewOutcome, string> = {
  accept: "border-accent text-accent",
  reject: "border-error text-error",
  // The palette has three colours; an unresolved reading gets the neutral one
  // rather than a fourth invented for it.
  uncertain: "border-fg text-fg",
};

function VerdictBody({ verdict }: { verdict: ReviewVerdict }) {
  return (
    <div className="mt-1 border border-border p-1.5 text-[11px]">
      <p className="m-0 flex flex-wrap items-baseline gap-2">
        {verdict.outcome ? (
          <span className={cx("border px-1.5 py-0.5", VERDICT_BADGE[verdict.outcome])}>
            {verdict.outcome}
          </span>
        ) : (
          <span className="text-dim">no verdict in this record</span>
        )}
        {verdict.confidence !== null ? (
          <span className="text-dim">confidence {verdict.confidence.toFixed(2)}</span>
        ) : null}
      </p>
      {verdict.checks.length > 0 ? (
        <ul className="m-0 mt-1 list-none">
          {verdict.checks.map((check) => (
            <li key={check.name} className={check.passed ? "text-dim" : "text-error"}>
              {check.passed ? "✓" : "✗"} {check.name}
            </li>
          ))}
        </ul>
      ) : null}
      {verdict.issues.length > 0 ? (
        <ul className="m-0 mt-1 list-disc pl-4 text-fg">
          {verdict.issues.map((issue) => (
            <li key={issue}>{issue}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/**
 * A judge's answer, read from its own artifact. Fetched on demand like the
 * provenance sidecar: the panel opens on a node, not on a run, so paying for
 * every verdict up front would be paying for answers nobody asked to see.
 */
function VerdictDetail({ tag, port }: { tag: string; port: ExecutionViewPort }) {
  const [state, setState] = useState<"idle" | "loading" | "failed">("idle");
  const [verdict, setVerdict] = useState<ReviewVerdict | null>(null);
  const url = preparedAssetUrl(tag, port.artifactRef);
  return (
    <div>
      <div className="flex flex-wrap items-center gap-1.5">
        {verdict === null ? (
          <button
            type="button"
            className={cx(linkGhost, "cursor-pointer")}
            disabled={state === "loading"}
            onClick={async () => {
              setState("loading");
              try {
                const response = await fetch(url);
                if (!response.ok) throw new Error(String(response.status));
                setVerdict(parseReviewVerdict(await response.json()));
              } catch {
                setState("failed");
              }
            }}
          >
            {state === "failed"
              ? `${port.portId} unreadable`
              : state === "loading"
                ? "loading…"
                : `read ${port.portId}`}
          </button>
        ) : null}
        <a className={linkGhost} href={url} target="_blank" rel="noreferrer">
          {"{ } open"}
        </a>
      </div>
      {verdict && hasVerdictContent(verdict) ? <VerdictBody verdict={verdict} /> : null}
      {verdict && !hasVerdictContent(verdict) ? (
        <p className="m-0 mt-1 text-[11px] text-dim">
          this record carries no verdict fields — open it raw
        </p>
      ) : null}
    </div>
  );
}

/**
 * The node's definition, rendered by archetype. Every node keeps the same
 * facts above; what differs here is what *defines* the work: a prompt and the
 * artwork it was shown, a schema and the answer it wrote, or just the ports it
 * fills. An unregistered type (archetype null) gets the generic tail.
 */
function Definition({
  tag,
  node,
  nodesById,
  onSelect,
  onZoom,
}: {
  tag: string;
  node: ExecutionViewNode;
  nodesById: ReadonlyMap<string, ExecutionViewNode>;
  onSelect: (nodeId: string) => void;
  onZoom: (image: LightboxImage) => void;
}) {
  const card = node.card;
  const prompt = isPrompted(node.archetype) ? card?.prompt : null;
  const references = resolveReferenceInputs(card, nodesById);
  const authored = resolveAuthoredInputs(card, nodesById.values());
  const answer = verdictPort(node);
  if (
    !prompt &&
    !card?.templateRef &&
    !card?.schemaName &&
    references.length === 0 &&
    authored.length === 0 &&
    node.ports.length === 0 &&
    answer === null
  ) {
    return null;
  }
  return (
    <>
      <SectionHeading>definition</SectionHeading>
      {card?.templateRef || card?.schemaName ? (
        <div className="mb-1.5 flex flex-wrap gap-1.5">
          {card.templateRef ? <Tag term="template" value={card.templateRef} /> : null}
          {card.schemaName ? <Tag term="schema" value={card.schemaName} /> : null}
        </div>
      ) : null}
      {prompt ? (
        <details className="mb-1.5 border border-border">
          <summary className="cursor-pointer px-1.5 py-1 text-[11px] text-dim">
            prompt · {prompt.length} chars
          </summary>
          <pre className="m-0 max-h-64 overflow-auto border-t border-border p-1.5 text-[11px] whitespace-pre-wrap text-fg">
            {prompt}
          </pre>
        </details>
      ) : null}
      {answer ? <VerdictDetail tag={tag} port={answer} /> : null}
      {references.length > 0 ? (
        <>
          <SectionHeading>reference inputs ({references.length})</SectionHeading>
          <ul className="m-0 list-none space-y-1.5">
            {references.map((resolved) => (
              <ReferenceInput
                key={`${resolved.reference.nodeId}/${resolved.reference.portId}`}
                tag={tag}
                resolved={resolved}
                onSelect={onSelect}
                onZoom={onZoom}
              />
            ))}
          </ul>
        </>
      ) : null}
      {authored.length > 0 ? (
        <>
          <SectionHeading>authored inputs ({authored.length})</SectionHeading>
          <ul className="m-0 mb-1.5 list-none space-y-1.5">
            {authored.map((resolved) => (
              <AuthoredInputEntry
                key={resolved.input.label}
                tag={tag}
                resolved={resolved}
                onZoom={onZoom}
              />
            ))}
          </ul>
        </>
      ) : null}
      {node.ports.length > 0 ? (
        <>
          <SectionHeading>ports ({node.ports.length})</SectionHeading>
          <PortList ports={node.ports} />
        </>
      ) : null}
    </>
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
        <Fact
          term={
            view.subject.kind === "dialogue-scene-execution-view-v1"
              ? "scene"
              : view.subject.kind === "pointclick-room-execution-view-v1"
                ? "room"
                : "game"
          }
        >
          {subjectLabel(view.subject)}
        </Fact>
        <Fact term="recipe">{view.subject.recipe}</Fact>
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
  nodesById,
  liveness,
  onSelect,
}: {
  tag: string;
  node: ExecutionViewNode;
  /** Every node in the run, so a card's reference inputs can be resolved. */
  nodesById: ReadonlyMap<string, ExecutionViewNode>;
  liveness: ExecutionRunLiveness;
  onSelect: (nodeId: string) => void;
}) {
  const [lightbox, setLightbox] = useState<LightboxImage | null>(null);
  const params = Object.entries(node.params);
  return (
    <div className="p-3 text-xs">
      <p className={cx(metaLine, "mb-1")}>
        {STATE_MARK[node.state]} {nodeStateLabel(node.state, liveness)} ·{" "}
        {node.archetype ?? "unregistered"} · {node.domain}
      </p>
      <h3 className="mt-0 mb-0.5 text-sm font-semibold">{nodeHeading(node)}</h3>
      <p className="m-0 truncate text-[11px] text-dim" title={node.typeId}>
        {node.typeId}
      </p>
      {node.templateId ? (
        <p className="m-0 mt-1">
          <Tag term="template" value={node.templateId} />
        </p>
      ) : null}
      <p className="mt-1.5 mb-2 text-dim">{node.description}</p>
      {node.error ? <p className={errorBanner}>{node.error}</p> : null}
      {params.length > 0 ? (
        <dl className="m-0 mb-2 border border-border">
          {params.map(([key, value]) => (
            <Fact key={key} term={key}>
              {value}
            </Fact>
          ))}
        </dl>
      ) : null}
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
                className={cx(
                  "mr-1 cursor-pointer hover:text-fg",
                  // A barrier only orders execution; it carries no lineage into
                  // this node's cache key, and reads dashed here as on the graph.
                  node.barrierOnly.includes(id)
                    ? "text-dim underline decoration-dashed"
                    : "text-dim underline",
                )}
                title={node.barrierOnly.includes(id) ? "cache barrier" : "lineage"}
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
        <Fact term="cache key">{node.cacheKey.slice(0, 12)}…</Fact>
      </dl>
      <Definition
        tag={tag}
        node={node}
        nodesById={nodesById}
        onSelect={onSelect}
        onZoom={setLightbox}
      />
      {node.artifacts.length > 0 ? (
        <>
          <SectionHeading>artifacts ({node.artifacts.length})</SectionHeading>
          <ul className="m-0 list-none space-y-1.5">
            {node.artifacts.map((artifact) => (
              <ArtifactCard
                key={artifact.artifactRef}
                tag={tag}
                artifact={artifact}
                sidecarRef={sidecarRefFor(node, artifact.artifactRef)}
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
