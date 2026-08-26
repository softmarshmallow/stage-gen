"use client";

import dynamic from "next/dynamic";
import type { AtlasViewportProps } from "./AtlasViewportImpl";
import styles from "./UniverseDemo.module.css";

const AtlasViewportImpl = dynamic(() => import("./AtlasViewportImpl"), {
  ssr: false,
  loading: () => (
    <div className={styles.mapLoading} role="status">
      Preparing atlas…
    </div>
  ),
});

export default function AtlasViewport(props: AtlasViewportProps) {
  return <AtlasViewportImpl {...props} />;
}
