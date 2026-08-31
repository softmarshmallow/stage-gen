"use client";

// The scene's mount point, and nothing else.
//
// Everything the player sees — backdrop, character, dialogue panel, end card —
// is drawn inside the canvas by the Phaser scene in
// `lib/dialogue-scene/scene-game`. This component exists to give that scene an
// element to fill and to tear it down on unmount, the same shape the room and
// the platformer preview use. Phaser touches `window` at construction time, so
// the module is imported lazily and never reaches the server render.

import { useEffect, useRef } from "react";
import type { DialogueSceneGameHandle } from "@/lib/dialogue-scene/scene-game";
import type { DialogueSceneDemoFixture } from "@/lib/dialogue-scene/schema";

export default function ScenePlayer({ fixture }: { fixture: DialogueSceneDemoFixture }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let game: DialogueSceneGameHandle | undefined;
    let cancelled = false;
    void (async () => {
      const { bootDialogueSceneGame } = await import("@/lib/dialogue-scene/scene-game");
      if (cancelled || !ref.current) return;
      game = bootDialogueSceneGame(ref.current, fixture);
    })();
    return () => {
      cancelled = true;
      game?.destroy(true);
    };
  }, [fixture]);

  return <div ref={ref} className="h-full w-full" />;
}
