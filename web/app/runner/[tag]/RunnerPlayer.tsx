"use client";

// The runner's mount point, and nothing else.
//
// Everything the player sees — parallax bands, ground, avatar, hazards,
// pickups, the HUD, the death card — is drawn inside the canvas by the sealed
// systems in `lib/sideview-runner/game`. This component exists to give that
// boot an element to fill and to tear it down on unmount, the same shape the
// room player uses. Phaser touches `window` at construction time, so the
// module is imported lazily and never reaches the server render.

import { useEffect, useRef } from "react";
import type { RunnerRuntimeManifest } from "@/lib/sideview-runner/contract";
import type { RunnerGameHandle } from "@/lib/sideview-runner/game";

export default function RunnerPlayer({
  tag,
  manifest,
}: {
  tag: string;
  manifest: RunnerRuntimeManifest;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const supportsSlide =
    manifest.gameplay.duckProfile !== null &&
    manifest.avatar.motions.some((motion) => motion.state === "slide");
  // The same control, stated once per verb it wears: press to jump while
  // running, hold to climb while a boss is on the line.
  const controlsLabel = [
    supportsSlide
      ? "Tap the upper screen or press Space to jump. Hold the lower screen or Arrow Down to slide."
      : "Tap the screen or press Space to jump.",
    manifest.gameplay.encounter === null
      ? null
      : "Hold to fly when a boss blocks the way.",
  ]
    .filter((line) => line !== null)
    .join(" ");

  useEffect(() => {
    let game: RunnerGameHandle | undefined;
    let cancelled = false;
    void (async () => {
      const { bootRunnerGame } = await import("@/lib/sideview-runner/game");
      if (cancelled || !ref.current) return;
      game = bootRunnerGame(ref.current, tag, manifest);
    })();
    return () => {
      cancelled = true;
      game?.destroy(true);
    };
  }, [manifest, tag]);

  return (
    <div className="relative h-full w-full overflow-hidden">
      <div
        ref={ref}
        data-testid="runner-stage"
        aria-label={`${manifest.displayName} — infinite runner. ${controlsLabel}`}
        className="h-full w-full touch-none select-none"
      />
      <div className="pointer-events-none absolute right-3 bottom-2 left-3 z-10 flex justify-between text-[10px] tracking-[0.12em] text-white/55 uppercase drop-shadow-[0_1px_2px_rgba(0,0,0,0.9)]">
        <span>Tap / Space · Jump</span>
        {supportsSlide ? <span>Hold lower screen / ↓ · Slide</span> : null}
      </div>
    </div>
  );
}
