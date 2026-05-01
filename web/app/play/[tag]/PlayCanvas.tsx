"use client";

import { useEffect, useRef } from "react";

export default function PlayCanvas({ tag }: { tag: string }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let game: { destroy: (removeCanvas: boolean) => void } | undefined;
    let cancelled = false;

    // Phaser touches window at construct time → load it lazily on the client.
    (async () => {
      const [{ bootGame }, { startRandomBgm, stopBgm }] = await Promise.all([
        import("@/lib/runtime/scene"),
        import("@/lib/runtime/bgm"),
      ]);
      if (cancelled || !ref.current) return;
      game = bootGame(ref.current, tag);
      // Fire-and-forget: random BGM (no AI picker yet).
      void startRandomBgm();
      // Expose stop for cleanup teardown.
      (window as unknown as { __stopBgm?: () => void }).__stopBgm = stopBgm;
    })();

    return () => {
      cancelled = true;
      if (game) game.destroy(true);
      const w = window as unknown as { __stopBgm?: () => void };
      if (w.__stopBgm) w.__stopBgm();
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
