// The genre-runtime registry: which manifest kind boots which consumer.
//
// This is the modular boundary a second (and every later) 2D genre plugs
// into: a runtime module is declared by the manifest kind it can boot and the
// route that boots it. Nothing here parses a manifest — each module keeps its
// own strict contract; this table only says who answers for which kind.

import { POINTCLICK_RUNTIME_KIND } from "@/lib/pointclick/contract";
import { PREPARED_RUNTIME_KIND } from "@/lib/manifest/prepared-manifest";

export interface SceneModule {
  /** The manifest kind this runtime consumes (out/<tag>/manifest.json `kind`). */
  readonly kind: string;
  /** Human name of the genre runtime. */
  readonly label: string;
  /** The route that boots one published run of this kind. */
  readonly route: (tag: string) => string;
}

export const SCENE_MODULES: readonly SceneModule[] = [
  {
    kind: PREPARED_RUNTIME_KIND,
    label: "side-view platformer",
    route: (tag) => `/preview/${encodeURIComponent(tag)}`,
  },
  {
    kind: POINTCLICK_RUNTIME_KIND,
    label: "point-and-click room",
    route: (tag) => `/room/${encodeURIComponent(tag)}`,
  },
];

export function sceneModuleForKind(kind: string): SceneModule | null {
  return SCENE_MODULES.find((module) => module.kind === kind) ?? null;
}
