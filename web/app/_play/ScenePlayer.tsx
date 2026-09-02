"use client";

// The scene's mount point, and nothing else.
//
// Everything the player sees inside the frame — backdrop, cast, dialogue panel,
// end card — is drawn inside the canvas by the Phaser scene in
// `lib/dialogue-scene/scene-game`. This component exists to give that scene an
// element to fill, to hand it where to start, to report what it drew, and to
// tear it down on unmount. Phaser touches `window` at construction time, so the
// module is imported lazily and never reaches the server render.
//
// The callbacks are held in refs on purpose. A host that autosaves will re-render
// on every line, and a scene that remounted because its `onMoment` prop had a new
// identity would restart the game the player is in the middle of.

import { useEffect, useRef } from "react";
import type {
  DialogueSceneGameHandle,
  DialogueSceneMoment,
} from "@/lib/dialogue-scene/scene-game";
import type { DialogueSceneFixture } from "@/lib/dialogue-scene/schema";
import type { ScenarioState } from "@/lib/scenario/runtime";

export interface ScenePlayerProps {
  readonly fixture: DialogueSceneFixture;
  /** A saved moment to open on, checked against the program before it is used. */
  readonly resume?: ScenarioState | null;
  /** Facts an earlier beat exported, seeded into the flags this scenario declares. */
  readonly carriedFlags?: readonly string[];
  readonly onMoment?: (moment: DialogueSceneMoment) => void;
  /** When given, the ending card hands control back instead of playing again. */
  readonly onFinish?: (outcome: string, flags: readonly string[]) => void;
}

export default function ScenePlayer({
  fixture,
  resume = null,
  carriedFlags,
  onMoment,
  onFinish,
}: ScenePlayerProps) {
  const ref = useRef<HTMLDivElement>(null);
  const latest = useRef({ resume, carriedFlags, onMoment, onFinish });
  latest.current = { resume, carriedFlags, onMoment, onFinish };

  useEffect(() => {
    let game: DialogueSceneGameHandle | undefined;
    let cancelled = false;
    const opening = latest.current;
    void (async () => {
      const { bootDialogueSceneGame } = await import("@/lib/dialogue-scene/scene-game");
      if (cancelled || !ref.current) return;
      game = bootDialogueSceneGame(ref.current, fixture, {
        resume: opening.resume,
        carriedFlags: opening.carriedFlags,
        onMoment: (moment: DialogueSceneMoment) => latest.current.onMoment?.(moment),
        onFinish:
          opening.onFinish === undefined
            ? undefined
            : (outcome: string, flags: readonly string[]) =>
                latest.current.onFinish?.(outcome, flags),
      });
    })();
    return () => {
      cancelled = true;
      game?.destroy(true);
    };
  }, [fixture]);

  return (
    <div
      ref={ref}
      data-testid="scene-stage"
      aria-label={`${fixture.title} — visual novel scene`}
      className="h-full w-full touch-none select-none"
    />
  );
}
