"use client";

// The room's mount point, and nothing else.
//
// Everything the player sees — backdrop, hotspots, narration, inventory, verb
// controls — is drawn inside the canvas by the Phaser scene in
// `lib/pointclick/room-scene`. This component exists to give that scene an
// element to fill, to hand it where to start, to report every click, and to tear
// it down on unmount. Phaser touches `window` at construction time, so the module
// is imported lazily and never reaches the server render.
//
// As with the scene, the callback is held in a ref: a host that autosaves
// re-renders on every click, and a room that remounted on a new prop identity
// would put the player back at the door.

import { useEffect, useRef } from "react";
import type { RoomManifest } from "@/lib/pointclick/contract";
import type { RoomGameHandle } from "@/lib/pointclick/room-scene";
import type { RoomPlayState } from "@/lib/pointclick/state";

export interface RoomPlayerProps {
  readonly tag: string;
  readonly manifest: RoomManifest;
  readonly resume?: RoomPlayState | null;
  readonly carriedFlags?: readonly string[];
  readonly onChange?: (state: RoomPlayState) => void;
}

export default function RoomPlayer({
  tag,
  manifest,
  resume = null,
  carriedFlags,
  onChange,
}: RoomPlayerProps) {
  const ref = useRef<HTMLDivElement>(null);
  const latest = useRef({ resume, carriedFlags, onChange });
  latest.current = { resume, carriedFlags, onChange };

  useEffect(() => {
    let game: RoomGameHandle | undefined;
    let cancelled = false;
    const opening = latest.current;
    void (async () => {
      const { bootRoomGame } = await import("@/lib/pointclick/room-scene");
      if (cancelled || !ref.current) return;
      game = bootRoomGame(ref.current, tag, manifest, {
        resume: opening.resume,
        carriedFlags: opening.carriedFlags,
        onChange: (state: RoomPlayState) => latest.current.onChange?.(state),
      });
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
