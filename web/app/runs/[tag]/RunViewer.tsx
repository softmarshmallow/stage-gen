"use client";

// Read-only run viewer: the layered DAG fills the window, and the inspector
// floats over it rather than splitting it, so the graph is the page.
//
// The canvas is one transformed layer, not a scroll container. That is the
// whole reason gestures are hand-wired: over a scroller, a macOS trackpad's
// horizontal two-finger swipe is the browser's back gesture, and a pinch is
// page zoom. Both are cancelled here and spent on the graph instead. Layout
// and camera are computed every load and never persisted — a read-only
// viewer that stores hand-placed nodes has quietly become an editor.

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { button, cx } from "@/app/ui";
import type { ExecutionNodeState, ExecutionView } from "@/lib/runtime/execution-view";
import { layoutExecutionGraph } from "@/lib/runtime/execution-view-layout";
import {
  centerOn,
  fitViewport,
  IDENTITY_VIEWPORT,
  initialViewport,
  panBy,
  wheelPanDelta,
  wheelZoomFactor,
  zoomAt,
  type Size,
  type Viewport,
} from "@/lib/runtime/execution-view-viewport";
import NodeInspector, { RunFacts, STATE_MARK } from "./Inspector";

const STATE_CHIP: Record<ExecutionNodeState, string> = {
  pending: "border-border text-dim",
  running: "border-fg text-fg",
  succeeded: "border-accent/60 text-fg",
  failed: "border-error text-error",
  skipped: "border-dashed border-dim text-dim",
};

/** Panel width, and the slice of frame it covers when centring on a node. */
const PANEL_WIDTH = 380;

/** Pointer travel, in px, past which a press is a pan and not a click. */
const DRAG_SLOP = 4;

const ZOOM_STEP = 1.25;

/** Where the opening camera puts the graph's corner: clear of the header. */
const OPENING_INSET = { x: 24, y: 88 } as const;

/** Safari reports a trackpad pinch as gesture events, not ctrl-flagged wheel. */
interface GestureLikeEvent extends Event {
  readonly scale?: number;
  readonly clientX?: number;
  readonly clientY?: number;
}

const STATES = ["pending", "running", "succeeded", "failed", "skipped"] as const;

/** A collapsed chip wears the loudest state among the nodes it stands for. */
const CHIP_STATE_PRIORITY = ["failed", "running", "pending", "skipped", "succeeded"] as const;

export default function RunViewer({ tag, view }: { tag: string; view: ExecutionView }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(true);
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const [viewport, setViewport] = useState<Viewport>(IDENTITY_VIEWPORT);
  const [frame, setFrame] = useState<Size>({ width: 0, height: 0 });
  const [panning, setPanning] = useState(false);

  const surfaceRef = useRef<HTMLDivElement | null>(null);
  /** True once the camera is the operator's; until then it stays framed. */
  const cameraOwnedRef = useRef(false);
  const refitRef = useRef(false);
  const draggedRef = useRef(false);

  const nodesById = useMemo(
    () => new Map(view.nodes.map((node) => [node.nodeId, node])),
    [view.nodes],
  );
  const layout = useMemo(() => layoutExecutionGraph(view.nodes, collapsed), [view.nodes, collapsed]);
  const selected = selectedId ? (nodesById.get(selectedId) ?? null) : null;
  const domains = useMemo(() => [...new Set(view.nodes.map((node) => node.domain))], [view.nodes]);

  // The frame is whatever the window leaves us; the graph is fitted into it once.
  useEffect(() => {
    const surface = surfaceRef.current;
    if (!surface) return;
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (rect) setFrame({ width: rect.width, height: rect.height });
    });
    observer.observe(surface);
    return () => observer.disconnect();
  }, []);

  const fit = useCallback(() => {
    cameraOwnedRef.current = true;
    setViewport(fitViewport({ width: layout.width, height: layout.height }, frame));
  }, [frame, layout.height, layout.width]);

  // Re-frame on every measurement until someone moves the camera, rather than
  // latching the first one: the first ResizeObserver delivery can precede the
  // settled window, and framing a graph to a stale frame is a wrong opening.
  useEffect(() => {
    if (cameraOwnedRef.current || frame.width === 0) return;
    setViewport(
      initialViewport({ width: layout.width, height: layout.height }, frame, OPENING_INSET),
    );
  }, [frame, layout.height, layout.width]);

  // Collapsing or expanding every domain is a "show me the shape" command, so
  // the camera follows the new shape. Layout has already been recomputed by
  // the time this runs, which is why the refit is an effect and not a handler.
  useEffect(() => {
    if (!refitRef.current) return;
    refitRef.current = false;
    fit();
  }, [fit]);

  const setAllCollapsed = (next: ReadonlySet<string>) => {
    refitRef.current = true;
    setCollapsed(next);
  };

  const zoomBy = useCallback(
    (factor: number) => {
      cameraOwnedRef.current = true;
      setViewport((current) =>
        zoomAt(current, factor, { x: frame.width / 2, y: frame.height / 2 }),
      );
    },
    [frame.height, frame.width],
  );

  // React attaches wheel listeners passively at the root, so preventDefault
  // only lands from a listener registered here by hand.
  useEffect(() => {
    const surface = surfaceRef.current;
    if (!surface) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      cameraOwnedRef.current = true;
      const rect = surface.getBoundingClientRect();
      const at = { x: event.clientX - rect.left, y: event.clientY - rect.top };
      if (event.ctrlKey || event.metaKey) {
        setViewport((current) => zoomAt(current, wheelZoomFactor(event.deltaY, event.deltaMode), at));
        return;
      }
      const { dx, dy } = wheelPanDelta(event.deltaX, event.deltaY, event.deltaMode);
      setViewport((current) => panBy(current, -dx, -dy));
    };
    surface.addEventListener("wheel", onWheel, { passive: false });
    return () => surface.removeEventListener("wheel", onWheel);
  }, []);

  // The canvas covers most of the page, but the floating chrome does not, and
  // a horizontal two-finger swipe anywhere else would still be the browser's
  // back gesture. Nothing on this page navigates by swipe, so horizontal-
  // dominant wheels are cancelled page-wide; vertical scrolling inside the
  // panel is untouched.
  useEffect(() => {
    const onWheel = (event: WheelEvent) => {
      if (event.cancelable && Math.abs(event.deltaX) > Math.abs(event.deltaY)) {
        event.preventDefault();
      }
    };
    document.addEventListener("wheel", onWheel, { passive: false });
    return () => document.removeEventListener("wheel", onWheel);
  }, []);

  // Safari's pinch: an absolute scale per gesture, so track the previous one.
  useEffect(() => {
    const surface = surfaceRef.current;
    if (!surface) return;
    let previousScale = 1;
    let anchor = { x: 0, y: 0 };
    const onStart = (event: Event) => {
      event.preventDefault();
      const gesture = event as GestureLikeEvent;
      previousScale = gesture.scale ?? 1;
      const rect = surface.getBoundingClientRect();
      anchor = {
        x: (gesture.clientX ?? rect.width / 2) - rect.left,
        y: (gesture.clientY ?? rect.height / 2) - rect.top,
      };
    };
    const onChange = (event: Event) => {
      event.preventDefault();
      const scale = (event as GestureLikeEvent).scale ?? previousScale;
      if (previousScale === 0) return;
      const factor = scale / previousScale;
      previousScale = scale;
      cameraOwnedRef.current = true;
      setViewport((current) => zoomAt(current, factor, anchor));
    };
    const onEnd = (event: Event) => event.preventDefault();
    surface.addEventListener("gesturestart", onStart, { passive: false });
    surface.addEventListener("gesturechange", onChange, { passive: false });
    surface.addEventListener("gestureend", onEnd, { passive: false });
    return () => {
      surface.removeEventListener("gesturestart", onStart);
      surface.removeEventListener("gesturechange", onChange);
      surface.removeEventListener("gestureend", onEnd);
    };
  }, []);

  const beginPan = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 && event.button !== 1) return;
    let last = { x: event.clientX, y: event.clientY };
    let travelled = 0;
    const onMove = (move: PointerEvent) => {
      const dx = move.clientX - last.x;
      const dy = move.clientY - last.y;
      last = { x: move.clientX, y: move.clientY };
      travelled += Math.abs(dx) + Math.abs(dy);
      if (travelled > DRAG_SLOP) {
        draggedRef.current = true;
        cameraOwnedRef.current = true;
        setPanning(true);
      }
      setViewport((current) => panBy(current, dx, dy));
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      setPanning(false);
      // The click that follows a drag is that drag's own mouseup: chips read
      // the flag to ignore it, and it is cleared once the click has passed.
      window.setTimeout(() => {
        draggedRef.current = false;
      }, 0);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  const toggleDomain = (domain: string) =>
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(domain)) next.delete(domain);
      else next.add(domain);
      return next;
    });

  const select = (nodeId: string) => {
    setSelectedId(nodeId);
    setPanelOpen(true);
  };

  /** Selecting from the inspector jumps the camera; clicking a chip does not. */
  const focusNode = useCallback(
    (nodeId: string) => {
      select(nodeId);
      const placed = layout.nodes.find(
        (node) => node.id === nodeId || node.memberIds.includes(nodeId),
      );
      if (!placed || frame.width === 0) return;
      cameraOwnedRef.current = true;
      setViewport((current) =>
        centerOn(
          current,
          { x: placed.x + layout.chipWidth / 2, y: placed.y + layout.chipHeight / 2 },
          { width: Math.max(240, frame.width - PANEL_WIDTH), height: frame.height },
        ),
      );
    },
    [frame.height, frame.width, layout],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      // The lightbox is modal and owns Escape while it is up.
      if (document.querySelector('[role="dialog"]')) return;
      if (event.key === "Escape") {
        setSelectedId(null);
        setPanelOpen(false);
      } else if (event.key === "f") {
        fit();
      } else if (event.key === "+" || event.key === "=") {
        zoomBy(ZOOM_STEP);
      } else if (event.key === "-") {
        zoomBy(1 / ZOOM_STEP);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fit, zoomBy]);

  const controlButton = cx(button, "px-2 py-0.5 text-[11px]");

  return (
    <div className="absolute inset-0 overflow-hidden">
      <div
        ref={surfaceRef}
        data-graph-surface
        className={cx(
          "absolute inset-0 touch-none overscroll-none select-none",
          panning ? "cursor-grabbing" : "cursor-grab",
        )}
        onPointerDown={beginPan}
      >
        <div
          className="absolute top-0 left-0 origin-top-left will-change-transform"
          style={{
            width: layout.width,
            height: layout.height,
            transform: `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.scale})`,
          }}
        >
          <svg
            className="pointer-events-none absolute inset-0"
            width={layout.width}
            height={layout.height}
            aria-hidden="true"
          >
            {layout.edges.map((edge) => {
              const active =
                selectedId !== null &&
                (edge.from === selectedId ||
                  edge.to === selectedId ||
                  layout.nodes.some(
                    (node) =>
                      (node.id === edge.from || node.id === edge.to) &&
                      node.memberIds.includes(selectedId),
                  ));
              const bend = Math.max(24, (edge.x2 - edge.x1) / 2);
              return (
                <path
                  key={`${edge.from}->${edge.to}`}
                  d={`M ${edge.x1} ${edge.y1} C ${edge.x1 + bend} ${edge.y1}, ${edge.x2 - bend} ${edge.y2}, ${edge.x2} ${edge.y2}`}
                  fill="none"
                  stroke={active ? "var(--color-accent)" : "var(--color-border)"}
                  strokeWidth={active ? 1.5 : 1}
                />
              );
            })}
          </svg>
          {layout.lanes.map((lane) => (
            <button
              key={lane.domain}
              type="button"
              className="absolute left-0 cursor-pointer pl-4 text-[10px] tracking-[0.08em] text-dim uppercase hover:text-fg"
              style={{ top: lane.y }}
              title="toggle domain collapse"
              onClick={() => {
                if (draggedRef.current) return;
                toggleDomain(lane.domain);
              }}
            >
              {collapsed.has(lane.domain) ? "▸" : "▾"} {lane.domain} · {lane.nodeCount}
            </button>
          ))}
          {layout.nodes.map((placed) => {
            const isCollapsedChip = placed.memberIds.length > 1;
            const member = nodesById.get(placed.memberIds[0]);
            const chipState: ExecutionNodeState = isCollapsedChip
              ? (CHIP_STATE_PRIORITY.find((state) =>
                  placed.memberIds.some((id) => nodesById.get(id)?.state === state),
                ) ?? "pending")
              : (member?.state ?? "pending");
            const isSelected =
              selectedId !== null &&
              (placed.id === selectedId || placed.memberIds.includes(selectedId));
            const label = isCollapsedChip
              ? `${placed.domain} ×${placed.memberIds.length}`
              : placed.id;
            return (
              <button
                key={placed.id}
                type="button"
                className={cx(
                  "absolute cursor-pointer truncate border bg-bg px-1.5 text-left text-[11px] leading-[30px] hover:border-fg",
                  STATE_CHIP[chipState],
                  isSelected && "shadow-[inset_0_0_0_1px_var(--color-accent)]",
                )}
                style={{
                  left: placed.x,
                  top: placed.y,
                  width: layout.chipWidth,
                  height: layout.chipHeight,
                }}
                title={label}
                aria-pressed={isSelected}
                onClick={() => {
                  if (draggedRef.current) return;
                  if (isCollapsedChip) toggleDomain(placed.domain);
                  else select(placed.id);
                }}
              >
                {STATE_MARK[chipState]} {label}
              </button>
            );
          })}
        </div>
      </div>

      <header className="fixed top-3 left-3 z-20 max-w-[min(560px,calc(100vw-24px))] border border-border bg-bg/90 px-3 py-2 backdrop-blur-sm">
        <p className="m-0 flex flex-wrap items-baseline gap-x-3 text-xs text-dim">
          <Link className="text-dim no-underline hover:text-accent" href="/runs">
            ← runs
          </Link>
          <span className="text-sm font-semibold text-fg">{tag}</span>
          <span>
            {view.gameId} · {view.recipe} ·{" "}
            {view.ok === null ? "in flight" : view.ok ? "ok" : "failed"} · {view.nodes.length} nodes
          </span>
        </p>
        <p className="m-0 mt-1 flex flex-wrap gap-x-3 text-[11px] text-dim">
          {STATES.map((state) => (
            <span key={state} className={view.stateCounts[state] > 0 ? "text-fg" : undefined}>
              {STATE_MARK[state]} {view.stateCounts[state]} {state}
            </span>
          ))}
        </p>
      </header>

      <div className="fixed bottom-3 left-3 z-20 flex flex-wrap items-center gap-1.5 border border-border bg-bg/90 px-2 py-1.5 backdrop-blur-sm">
        <button type="button" className={controlButton} onClick={() => zoomBy(1 / ZOOM_STEP)}>
          -
        </button>
        <span className="w-12 text-center text-[11px] text-dim">
          {Math.round(viewport.scale * 100)}%
        </span>
        <button type="button" className={controlButton} onClick={() => zoomBy(ZOOM_STEP)}>
          +
        </button>
        <button type="button" className={controlButton} onClick={fit}>
          fit
        </button>
        <span className="mx-1 text-border">│</span>
        <button
          type="button"
          className={controlButton}
          onClick={() => setAllCollapsed(new Set(domains))}
        >
          collapse all
        </button>
        <button
          type="button"
          className={controlButton}
          onClick={() => setAllCollapsed(new Set())}
        >
          expand all
        </button>
        <span className="mx-1 text-border">│</span>
        <button
          type="button"
          className={controlButton}
          aria-pressed={panelOpen}
          onClick={() => setPanelOpen((open) => !open)}
        >
          {panelOpen ? "hide panel" : "show panel"}
        </button>
        <span className="ml-1 text-[11px] text-dim">pinch to zoom · drag to pan · f fit</span>
      </div>

      {panelOpen ? (
        <aside
          className="fixed top-3 right-3 bottom-3 z-30 flex w-[380px] max-w-[calc(100vw-24px)] flex-col border border-border bg-bg/95 backdrop-blur-sm"
          aria-label="Node inspector"
          aria-live="polite"
        >
          <div className="flex items-baseline gap-2 border-b border-border px-3 py-2">
            <h2 className="m-0 min-w-0 flex-1 truncate text-sm font-semibold" title={selected?.nodeId ?? "Run"}>
              {selected ? selected.nodeId : "Run"}
            </h2>
            <button
              type="button"
              className="cursor-pointer text-xs text-dim hover:text-fg"
              aria-label="close panel"
              onClick={() => setPanelOpen(false)}
            >
              ✕
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-auto overscroll-none">
            {selected ? (
              <NodeInspector tag={tag} node={selected} onSelect={focusNode} />
            ) : (
              <RunFacts view={view} />
            )}
          </div>
        </aside>
      ) : null}
    </div>
  );
}
