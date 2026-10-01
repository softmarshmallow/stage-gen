"use client";

// The tabs of a <Try>. The block renders this root with its markup inside; the player in
// web/ui/players/tabs.ts mounts on it after hydration and is torn down with it.

import type { ReactElement } from "react";
import { mount } from "@stage-gen/ui/players/tabs";
import { type RootProps, usePlayer } from "./use-player";

export default function TabsPlayer({ className, style, children }: RootProps): ReactElement {
  const ref = usePlayer<HTMLDivElement, void>(mount);
  return (
    <div ref={ref} data-tabs="" className={className} style={style}>
      {children}
    </div>
  );
}
