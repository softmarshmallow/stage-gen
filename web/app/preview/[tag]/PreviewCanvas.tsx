"use client";

import { useEffect, useRef } from "react";
import type { PreviewTransparencyPolicy } from "@/lib/shell/transparency";

export default function PreviewCanvas({
  tag,
  transparencyPolicy,
}: {
  tag: string;
  transparencyPolicy: PreviewTransparencyPolicy;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let preview: { destroy: (removeCanvas: boolean) => void } | undefined;
    let cancelled = false;

    // The browser adapter touches window at construction time, so load it
    // lazily and keep its lifecycle out of the headless pipeline.
    void (async () => {
      const { bootGame } = await import("@/lib/runtime/scene");
      if (cancelled || !ref.current) return;
      preview = bootGame(ref.current, tag, transparencyPolicy);
    })();

    return () => {
      cancelled = true;
      preview?.destroy(true);
    };
  }, [tag, transparencyPolicy]);

  return (
    <div
      ref={ref}
      aria-label="optional scrolling-game preview"
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
