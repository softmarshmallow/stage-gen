"use client";

// The face rig of a <FaceRig>. The block renders this root with its markup inside; the player in
// web/ui/players/face-rig.ts mounts on it after hydration and is torn down with it.

import type { ReactElement } from "react";
import { mount, type FaceRigConfig } from "@stage-gen/ui/players/face-rig";
import { type RootProps, usePlayer } from "./use-player";

export default function FaceRigPlayer({ config, className, style, children }: RootProps & { readonly config: string }): ReactElement {
  const ref = usePlayer<HTMLDivElement, FaceRigConfig>(mount, config);
  return (
    <div ref={ref} data-face-rig={config} className={className} style={style}>
      {children}
    </div>
  );
}
