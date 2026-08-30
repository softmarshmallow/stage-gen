"use client";

// The whole room runtime: one image, positioned hotspots, an inventory bar,
// and the pure reducer from lib/pointclick/state. Every transition is a
// click; there is no engine underneath to drift from the solvability proof.

import { useMemo, useState } from "react";
import { preparedAssetUrl } from "@/lib/manifest/prepared-manifest";
import type { RoomManifest } from "@/lib/pointclick/contract";
import {
  clickHotspot,
  hotspotVisible,
  initialState,
  inspectHotspot,
  selectItem,
  type RoomPlayState,
} from "@/lib/pointclick/state";

function pct(value: number): string {
  return `${(value * 100).toFixed(3)}%`;
}

export default function RoomPlayer({
  tag,
  manifest,
}: {
  tag: string;
  manifest: RoomManifest;
}) {
  const [state, setState] = useState<RoomPlayState>(() => initialState(manifest));
  const aspect = useMemo(
    () => `${manifest.scene.width} / ${manifest.scene.height}`,
    [manifest.scene.width, manifest.scene.height],
  );

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-2 px-4 pb-6">
      <div
        data-testid="room-stage"
        className="relative w-full select-none overflow-hidden rounded border border-line"
        style={{ aspectRatio: aspect }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={preparedAssetUrl(tag, manifest.scene.backdrop)}
          alt={manifest.displayName}
          className="absolute inset-0 h-full w-full object-cover"
          draggable={false}
        />
        {manifest.hotspots.map((hotspot) => {
          if (!hotspotVisible(manifest, state, hotspot.id)) return null;
          return (
            <button
              key={hotspot.id}
              type="button"
              data-testid={`hotspot-${hotspot.id}`}
              title={hotspot.label}
              aria-label={hotspot.label}
              onClick={() => setState(clickHotspot(manifest, state, hotspot.id))}
              onContextMenu={(event) => {
                event.preventDefault();
                setState(inspectHotspot(manifest, state, hotspot.id));
              }}
              className="absolute cursor-pointer border-0 bg-transparent p-0 outline-none hover:drop-shadow-[0_0_6px_rgba(255,255,255,0.55)] focus-visible:drop-shadow-[0_0_6px_rgba(255,255,255,0.55)]"
              style={{
                left: pct(hotspot.region.x),
                top: pct(hotspot.region.y),
                width: pct(hotspot.region.w),
                height: pct(hotspot.region.h),
              }}
            >
              {hotspot.sprite ? (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img
                  src={preparedAssetUrl(tag, hotspot.sprite)}
                  alt=""
                  className="h-full w-full object-contain"
                  draggable={false}
                />
              ) : null}
            </button>
          );
        })}
        {state.solved ? (
          <div
            data-testid="room-solved"
            className="absolute inset-x-0 bottom-0 bg-bg/85 px-4 py-3 text-center text-sm text-fg"
          >
            ✦ {manifest.win.narration}
          </div>
        ) : null}
      </div>

      <p data-testid="room-narration" className="min-h-10 text-sm text-fg">
        {state.narration}
      </p>

      <div className="flex items-center gap-2" data-testid="room-inventory">
        <span className="text-xs text-dim">inventory</span>
        {state.inventory.length === 0 ? (
          <span className="text-xs text-dim">— empty —</span>
        ) : (
          state.inventory.map((itemId) => {
            const item = manifest.items.find((entry) => entry.id === itemId);
            if (item === undefined) return null;
            const selected = state.selectedItem === itemId;
            return (
              <button
                key={itemId}
                type="button"
                data-testid={`item-${itemId}`}
                title={item.label}
                aria-pressed={selected}
                onClick={() => setState(selectItem(state, itemId))}
                className={`h-12 w-12 rounded border p-1 ${
                  selected ? "border-accent" : "border-line"
                } bg-transparent`}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={preparedAssetUrl(tag, item.icon)}
                  alt={item.label}
                  className="h-full w-full object-contain"
                  draggable={false}
                />
              </button>
            );
          })
        )}
        <span className="ml-auto text-xs text-dim">
          click: act · right-click: inspect · click an item to hold it
        </span>
      </div>
    </div>
  );
}
