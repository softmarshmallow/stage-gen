"use client";

import dynamic from "next/dynamic";
import type { AtlasViewportProps } from "./AtlasViewportImpl";
import { mapSurface } from "./atlas";

const AtlasViewportImpl = dynamic(() => import("./AtlasViewportImpl"), {
  ssr: false,
  loading: () => (
    <div className={`${mapSurface} grid place-items-center text-dim`} role="status">
      Preparing atlas…
    </div>
  ),
});

export default function AtlasViewport(props: AtlasViewportProps) {
  return <AtlasViewportImpl {...props} />;
}
