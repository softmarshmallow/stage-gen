"use client";

// The scrolling loop of a parallax <Hero>. The block renders this root with its markup inside; the player in
// web/ui/players/parallax-loop.ts mounts on it after hydration and is torn down with it.

import type { ReactElement } from "react";
import { mount } from "@stage-gen/ui/players/parallax-loop";
import type { LoopConfig } from "@stage-gen/ui/players/parallax";
import { type RootProps, usePlayer } from "./use-player";

export default function ParallaxLoopPlayer({ config, className, style, children }: RootProps & { readonly config: string }): ReactElement {
  const ref = usePlayer<HTMLDivElement, LoopConfig>(mount, config);
  return (
    <div ref={ref} data-parallax-loop={config} className={className} style={style}>
      {children}
    </div>
  );
}
