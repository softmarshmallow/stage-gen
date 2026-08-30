"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { PreviewTransparencyPolicy } from "@/lib/shell/transparency";
import type { GameplayAutomationMode } from "@/lib/sideview-platformer/automation";
import type { PreparedPreviewGameHandle } from "@/lib/sideview-platformer/prepared-scene";
import { cx } from "@/app/ui";
import {
  developerKitLabel,
  developerKitToken,
  sameDeveloperKit,
  type DeveloperKit,
} from "@/lib/sideview-platformer/developer-kit";

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
  const handle = useRef<PreparedPreviewGameHandle | null>(null);
  const [kits, setKits] = useState<readonly DeveloperKit[]>([]);
  const [active, setActive] = useState<DeveloperKit | null>(null);

  useEffect(() => {
    let preview: PreparedPreviewGameHandle | undefined;
    let cancelled = false;
    // One poll, running for as long as the canvas is mounted, mirroring the scene rather than
    // remembering what this component last did. The scene is the source of truth and it changes
    // the kit on its own - `K` switches without React hearing anything - so a console that tracked
    // only its own clicks would sit on a stale answer the moment the keyboard was used. The kit
    // list doubles as readiness: it is empty until the manifest has loaded and the weapon class has
    // been settled, so the console is simply not there until there is something true to render.
    let poll: ReturnType<typeof setInterval> | undefined;

    // The browser adapter touches window at construction time, so load it
    // lazily and keep its lifecycle out of the headless pipeline.
    void (async () => {
      const { bootPreparedGame } = await import("@/lib/sideview-platformer/prepared-scene");
      if (cancelled || !ref.current) return;
      preview = bootPreparedGame(ref.current, tag, transparencyPolicy, automationMode);
      handle.current = preview;
      if (automationMode !== null) return;
      poll = setInterval(() => {
        if (cancelled || !preview) return;
        const options = preview.developerKitOptions();
        setKits((current) => (current.length === options.length ? current : options));
        const scene = preview.activeDeveloperKit();
        setActive((current) =>
          current === scene || (current && scene && sameDeveloperKit(current, scene))
            ? current
            : scene,
        );
      }, 200);
    })();

    return () => {
      cancelled = true;
      clearInterval(poll);
      handle.current = null;
      setKits([]);
      setActive(null);
      preview?.destroy(true);
    };
  }, [automationMode, tag, transparencyPolicy]);

  const select = useCallback((kit: DeveloperKit, isPublished: boolean) => {
    // Applied immediately for a responsive control, but the poll above is what keeps it true: the
    // scene owns whether the switch happened, and a refused switch is corrected on the next tick.
    if (handle.current?.setDeveloperKit(isPublished ? null : kit)) {
      setActive(isPublished ? null : kit);
    }
  }, []);

  return (
    <>
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
      {kits.length > 1 ? (
        <DeveloperKitBar kits={kits} active={active} onSelect={select} />
      ) : null}
    </>
  );
}

/**
 * The developer's kit switcher, in the chrome below the canvas rather than inside it.
 *
 * Below rather than above so the game keeps the top of the viewport: the controls are consulted
 * between comparisons, and the thing being compared should not be pushed down the page by them.
 *
 * Buttons that act on the running scene, not links that reload it. A kit change is a question
 * about how the character plays on the map already in front of you, and answering it by navigating
 * would throw away the map, the level, and the position that made the question worth asking.
 *
 * The scene keeps its own `K` cycle for the same switch, through the same entry point; this is the
 * discoverable half, and it names what the run can actually be played as rather than what the
 * vocabulary allows.
 */
export function DeveloperKitBar({
  kits,
  active,
  onSelect,
}: {
  kits: readonly DeveloperKit[];
  active: DeveloperKit | null;
  onSelect: (kit: DeveloperKit, isPublished: boolean) => void;
}) {
  const current = active ?? kits[0];
  return (
    <div
      data-testid="developer-kit-console"
      className="flex flex-wrap items-center gap-2 px-4 pt-2 text-xs text-dim"
    >
      <span>kit</span>
      {kits.map((kit, index) => {
        // The package's own kit is always first, and selecting it clears the override rather than
        // setting one - so "back to what shipped" is the same control, not a separate reset.
        const isPublished = index === 0;
        const isCurrent =
          kit.weaponClass === current.weaponClass && kit.projectileId === current.projectileId;
        return (
          <button
            key={developerKitToken(kit)}
            type="button"
            data-testid={`developer-kit-option-${developerKitToken(kit)}`}
            aria-pressed={isCurrent}
            onClick={() => onSelect(kit, isPublished)}
            className={cx(
              "cursor-pointer rounded-[3px] border border-border px-1.5 py-px",
              isCurrent ? "bg-fg text-bg" : "text-fg",
            )}
          >
            {developerKitLabel(kit)}
            {isPublished ? " ·authored" : ""}
          </button>
        );
      })}
      <span>{active ? "developer override — not what this run published" : "as published"}</span>
    </div>
  );
}
