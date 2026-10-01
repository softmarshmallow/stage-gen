"use client";

// <model-viewer> from npm, loaded only on pages that show a model (a Hero or PartStage
// whose output is a model). The showcase loaded the same 3.5.0 build from a CDN on every
// page; the custom element upgrades the server-rendered tags in place once it is defined.

import { useEffect } from "react";

export default function ModelViewer(): null {
  useEffect(() => {
    void import("@google/model-viewer");
  }, []);
  return null;
}
