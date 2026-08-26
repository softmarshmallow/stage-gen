"use client";

import { useEffect, useRef } from "react";
import type { PreviewTransparencyPolicy } from "@/lib/shell/transparency";
import type { GameplayAutomationMode } from "@/lib/runtime/automation";

export default function PreviewCanvas({
  tag,
  transparencyPolicy,
  automationMode,
}: {
  tag: string;
  transparencyPolicy: PreviewTransparencyPolicy;
  automationMode: GameplayAutomationMode | null;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let preview: { destroy: (removeCanvas: boolean) => void } | undefined;
    let cancelled = false;

    // The browser adapter touches window at construction time, so load it
    // lazily and keep its lifecycle out of the headless pipeline.
    void (async () => {
      const { bootPreparedGame } = await import("@/lib/runtime/prepared-scene");
      if (cancelled || !ref.current) return;
      preview = bootPreparedGame(ref.current, tag, transparencyPolicy, automationMode);
    })();

    return () => {
      cancelled = true;
      preview?.destroy(true);
    };
  }, [automationMode, tag, transparencyPolicy]);

  return (
    <div
      ref={ref}
      aria-label="optional scrolling-game preview"
      data-automation={automationMode ?? undefined}
      style={{
        width: automationMode ? 1280 : "100%",
        maxWidth: automationMode ? undefined : 1280,
        height: automationMode ? 720 : undefined,
        aspectRatio: automationMode ? undefined : "1280 / 720",
        margin: "0 auto",
        background: "#000",
      }}
    />
  );
}
