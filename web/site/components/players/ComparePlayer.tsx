"use client";

// The wipe of a <Compare>. The block renders this root with its markup inside; the player in
// web/ui/players/compare.ts mounts on it after hydration and is torn down with it.

import type { ReactElement } from "react";
import { mount } from "@stage-gen/ui/players/compare";
import { type RootProps, usePlayer } from "./use-player";

export default function ComparePlayer({ className, style, children }: RootProps): ReactElement {
  const ref = usePlayer<HTMLDivElement, void>(mount);
  return (
    <div ref={ref} data-compare="" className={className} style={style}>
      {children}
    </div>
  );
}
