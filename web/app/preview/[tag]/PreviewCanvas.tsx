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
    let unsubscribe: (() => void) | undefined;
    let cancelled = false;
    const capture = automationMode !== null;

    // The browser adapter touches window at construction time, so load it
    // lazily and keep its lifecycle out of the headless pipeline.
    void (async () => {
      const { bootPreparedGame, DEVTOOLS_KIT_SWITCHED } = await import(
        "@/lib/sideview-platformer/prepared-scene"
      );
      // Before the scene, not inside it. A Phaser text object rasterises when it is constructed,
      // so a damage number drawn before its face is usable is drawn in a fallback and stays in it,
      // and a capture taken then is a capture of whatever font the machine happened to have.
      const { loadBrowserCombatTextFont } = await import(
        "@/lib/sideview-platformer/combat-font"
      );
      await loadBrowserCombatTextFont();
      if (cancelled || !ref.current) return;
      preview = bootPreparedGame(
        ref.current,
        tag,
        transparencyPolicy,
        capture ? "capture" : "interactive",
      );
      handle.current = preview;
      if (capture) return;
      // The subscription, not a timer. The scene is still the source of truth
      // and it changes the kit on its own — `K` switches without React hearing
      // anything — but it now *says* so, on the frame it happened, through the
      // handle's own seam. What used to be a 200 ms poll running for as long as
      // the canvas was mounted is a listener that does nothing on the frames
      // where nothing changed.
      unsubscribe = preview.subscribe((_world, frame) => {
        if (!preview) return;
        if (!frame.some((event) => event.type === DEVTOOLS_KIT_SWITCHED)) return;
        const options = preview.developerKitOptions();
        setKits((current) => (current.length === options.length ? current : options));
        const scene = preview.activeDeveloperKit();
        setActive((current) =>
          current === scene || (current && scene && sameDeveloperKit(current, scene))
            ? current
            : scene,
        );
      });
    })();

    return () => {
      cancelled = true;
      unsubscribe?.();
      handle.current = null;
      setKits([]);
      setActive(null);
      preview?.destroy(true);
    };
  }, [automationMode, tag, transparencyPolicy]);

  const select = useCallback((kit: DeveloperKit, isPublished: boolean) => {
    // Applied immediately for a responsive control, but the subscription above is what keeps it
    // true: the scene owns whether the switch happened, and it says so on the frame it did.
    if (handle.current?.setDeveloperKit(isPublished ? null : kit)) {
      setActive(isPublished ? null : kit);
    }
  }, []);

  // A capture keeps the design-space canvas at exactly its own size, because a frame hash
  // taken at another size is a different recording. Nothing else here may vary it.
  if (automationMode) {
    return (
      <div
        ref={ref}
        aria-label="optional scrolling-game preview"
        data-automation={automationMode}
        style={{ width: 1280, height: 720, margin: "0 auto", background: "#000" }}
      />
    );
  }
  // A person gets the whole surface the page hands over, the same shape the runner route
  // uses. The canvas keeps its 16:9 design space -- `Phaser.Scale.FIT` with `CENTER_BOTH`
  // already letterboxes it inside whatever this element turns out to be -- so filling the
  // viewport changes how big the game is drawn and never how much of the world is in it.
  return (
    <div className="flex h-full w-full min-h-0 flex-col">
      <div
        ref={ref}
        aria-label="optional scrolling-game preview"
        className="min-h-0 flex-1"
        style={{ background: "#000" }}
      />
      {kits.length > 1 ? (
        <DeveloperKitBar kits={kits} active={active} onSelect={select} />
      ) : null}
    </div>
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
