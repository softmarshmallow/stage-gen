"use client";

// The node graph view of the page shell. The shell renders this #graph root with the
// toolbar, the viewport and the stage inside; the player in web/ui/players/graph.ts mounts
// on it after hydration with the drawer data (`nodes`, the JSON blocks/drawer.ts writes),
// drives the rest of the shell by id, and is torn down with it.

import type { ReactElement } from "react";
import { mount, type GraphNodes } from "@stage-gen/ui/players/graph";
import { type RootProps, usePlayer } from "./use-player";

export default function GraphPlayer({ nodes, className, children }: RootProps & { readonly nodes: string }): ReactElement {
  const ref = usePlayer<HTMLDivElement, GraphNodes>(mount, nodes);
  return (
    <div ref={ref} id="graph" className={className}>
      {children}
    </div>
  );
}
