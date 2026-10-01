"use client";

// The tile painter of a <Painter>. The block renders this root with its markup inside; the player in
// web/ui/players/painter.ts mounts on it after hydration and is torn down with it.

import type { ReactElement } from "react";
import { mount, type PainterConfig } from "@stage-gen/ui/players/painter";
import { type RootProps, usePlayer } from "./use-player";

export default function PainterPlayer({ config, className, style, children }: RootProps & { readonly config: string }): ReactElement {
  const ref = usePlayer<HTMLDivElement, PainterConfig>(mount, config);
  return (
    <div ref={ref} data-painter={config} className={className} style={style}>
      {children}
    </div>
  );
}
