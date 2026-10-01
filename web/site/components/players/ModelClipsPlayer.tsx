"use client";

// The clip row under a model <Hero>. The block renders this row with its clip buttons
// inside; the player in web/ui/players/model-viewer.ts mounts on it after hydration, finds
// the hero's <model-viewer id="mv"> by its id, and is torn down with it.

import type { ReactElement } from "react";
import { mount } from "@stage-gen/ui/players/model-viewer";
import { type RootProps, usePlayer } from "./use-player";

export default function ModelClipsPlayer({ className, children }: RootProps): ReactElement {
  const ref = usePlayer<HTMLDivElement, void>(mount);
  return (
    <div ref={ref} id="clips" className={className}>
      {children}
    </div>
  );
}
