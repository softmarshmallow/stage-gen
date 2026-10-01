// Player: the part stage: each part's button hides its materials on the <model-viewer>, the clip row plays a clip.
//
// Moved from the [data-part-stage] section of the retired showcase's page script: same logic,
// same constants and the same comments, typed.
// Root: [data-part-stage]; its config maps a part id to its material names. Hooks inside it:
// [data-part], [data-clip], model-viewer.
//
// The old script handled the hero's #mv and the part stages in one whenDefined callback;
// model-viewer.ts keeps #mv and this module the part stages, each in its own callback.
// model-viewer itself is loaded by the site's components/ModelViewer.tsx; this module never
// imports it and types only what it touches.

import { $, type Mount } from "./dom";
import { clipRow } from "./model-viewer";

/** The block's config: each part's material names, by part id. */
export type PartStageConfig = Readonly<Record<string, readonly string[]>>;

/** The few <model-viewer> scene-graph members the part buttons use. */
interface ViewerMaterial {
  ensureLoaded(): Promise<void>;
  setAlphaMode(mode: "OPAQUE" | "MASK" | "BLEND"): void;
  setAlphaCutoff(cutoff: number): void;
  readonly pbrMetallicRoughness: {
    readonly baseColorFactor: readonly [number, number, number, number];
    setBaseColorFactor(factor: [number, number, number, number]): void;
  };
}

type ModelViewerElement = HTMLElement & {
  readonly loaded: boolean;
  readonly model: { getMaterialByName(name: string): ViewerMaterial };
};

export const mount: Mount<PartStageConfig> = (stage, materials) => {
  let aborted = false;
  const parts = [...stage.querySelectorAll<HTMLElement>("[data-part]")];
  let unbind = (): void => {};
  void customElements.whenDefined("model-viewer").then(() => {
    if (aborted) return;
    // <PartStage>: a part is hidden through its own material, so the skeleton and the clip carry on.
    const view = $<ModelViewerElement>("model-viewer", stage) as ModelViewerElement;
    unbind = clipRow(stage, view);
    for (const b of parts) b.onclick = async () => {
      const shown = b.getAttribute("aria-pressed") !== "true";
      b.setAttribute("aria-pressed", String(shown));
      if (!view.loaded) await new Promise(done => view.addEventListener("load", done, { once: true }));
      for (const name of materials[b.dataset.part as string]) {
        const m = view.model.getMaterialByName(name);
        await m.ensureLoaded();
        const [r, g, bl] = m.pbrMetallicRoughness.baseColorFactor;
        m.setAlphaMode(shown ? "OPAQUE" : "MASK");
        m.setAlphaCutoff(0.5);
        m.pbrMetallicRoughness.setBaseColorFactor([r, g, bl, shown ? 1 : 0]);
      }
    };
  });
  return () => {
    aborted = true;
    unbind();
    for (const b of parts) b.onclick = null;
  };
};
