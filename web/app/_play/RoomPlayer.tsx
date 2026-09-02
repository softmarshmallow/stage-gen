"use client";

// The room's mount point, and nothing else.
//
// Everything the player sees — backdrop, hotspots, narration, inventory, verb
// controls — is drawn inside the canvas by the Phaser scene in
// `lib/pointclick/room-scene`. This component exists to give that scene an
// element to fill and to tear it down on unmount, the same shape the platformer
// preview uses. Phaser touches `window` at construction time, so the module is
// imported lazily and never reaches the server render.

import { useEffect, useRef } from "react";
import type { RoomManifest } from "@/lib/pointclick/contract";
import type { RoomGameHandle } from "@/lib/pointclick/room-scene";

export default function RoomPlayer({ tag, manifest }: { tag: string; manifest: RoomManifest }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let game: RoomGameHandle | undefined;
    let cancelled = false;
    void (async () => {
      const { bootRoomGame } = await import("@/lib/pointclick/room-scene");
      if (cancelled || !ref.current) return;
      game = bootRoomGame(ref.current, tag, manifest);
    })();
    return () => {
      cancelled = true;
      game?.destroy(true);
    };
  }, [manifest, tag]);

  return (
    <div
      ref={ref}
      data-testid="room-stage"
      aria-label={`${manifest.displayName} — point-and-click room`}
      className="h-full w-full touch-none select-none"
    />
  );
}
