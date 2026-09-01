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
    <div
      ref={ref}
      data-testid="runner-stage"
      aria-label={`${manifest.displayName} — infinite runner`}
      className="h-full w-full touch-none select-none"
    />
  );
}
