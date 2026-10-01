"use client";

// The sprite stage of a <SpriteStage>. The block renders this root with its markup inside; the player in
// web/ui/players/sprite-stage.ts mounts on it after hydration and is torn down with it.

import type { ReactElement } from "react";
import { mount, type SpriteStageConfig } from "@stage-gen/ui/players/sprite-stage";
import { type RootProps, usePlayer } from "./use-player";

export default function SpriteStagePlayer({ config, className, style, children }: RootProps & { readonly config: string }): ReactElement {
  const ref = usePlayer<HTMLDivElement, SpriteStageConfig>(mount, config);
  return (
    <div ref={ref} data-sprite-stage={config} className={className} style={style}>
      {children}
    </div>
  );
}
