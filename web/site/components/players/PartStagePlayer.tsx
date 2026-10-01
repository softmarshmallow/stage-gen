"use client";

// The part stage of a <PartStage>. The block renders this root with its markup inside; the player in
// web/ui/players/part-stage.ts mounts on it after hydration and is torn down with it.

import type { ReactElement } from "react";
import { mount, type PartStageConfig } from "@stage-gen/ui/players/part-stage";
import { type RootProps, usePlayer } from "./use-player";

export default function PartStagePlayer({ config, className, style, children }: RootProps & { readonly config: string }): ReactElement {
  const ref = usePlayer<HTMLDivElement, PartStageConfig>(mount, config);
  return (
    <div ref={ref} data-part-stage={config} className={className} style={style}>
      {children}
    </div>
  );
}
