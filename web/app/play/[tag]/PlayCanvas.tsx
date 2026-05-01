"use client";

import { useEffect, useRef } from "react";

export default function PlayCanvas({ tag }: { tag: string }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let game: { destroy: (removeCanvas: boolean) => void } | undefined;
    let cancelled = false;

    // Phaser touches window at construct time → load it lazily on the client.
    (async () => {
      const { bootGame } = await import("@/lib/runtime/scene");
      if (cancelled || !ref.current) return;
      game = bootGame(ref.current, tag);
    })();

    return () => {
      cancelled = true;
      if (game) game.destroy(true);
    };
  }, [tag]);

  return (
    <div
      ref={ref}
      style={{
        width: "100%",
        maxWidth: 1280,
        aspectRatio: "1280 / 720",
        margin: "0 auto",
        background: "#000",
      }}
    />
  );
}
