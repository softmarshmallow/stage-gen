"use client";

// The playground of a <ParallaxLoop>. The block renders this root with its markup inside; the player in
// web/ui/players/parallax-playground.ts mounts on it after hydration and is torn down with it.

import type { ReactElement } from "react";
import { mount } from "@stage-gen/ui/players/parallax-playground";
import type { LoopConfig } from "@stage-gen/ui/players/parallax";
import { type RootProps, usePlayer } from "./use-player";

export default function ParallaxPlaygroundPlayer({ config, className, style, children }: RootProps & { readonly config: string }): ReactElement {
  const ref = usePlayer<HTMLDivElement, LoopConfig>(mount, config);
  return (
    <div ref={ref} data-parallax-playground={config} className={className} style={style}>
      {children}
    </div>
  );
}
