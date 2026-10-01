"use client";

// The stage of a <ParallaxStage>. The block renders this root with its markup inside; the player in
// web/ui/players/parallax-stage.ts mounts on it after hydration and is torn down with it.

import type { ReactElement } from "react";
import { mount } from "@stage-gen/ui/players/parallax-stage";
import type { StageConfig } from "@stage-gen/ui/players/parallax";
import { type RootProps, usePlayer } from "./use-player";

export default function ParallaxStagePlayer({ config, className, style, children }: RootProps & { readonly config: string }): ReactElement {
  const ref = usePlayer<HTMLDivElement, StageConfig>(mount, config);
  return (
    <div ref={ref} data-parallax-stage={config} className={className} style={style}>
      {children}
    </div>
  );
}
