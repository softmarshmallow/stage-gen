// Player: the hero's 3D model: the <model-viewer id="mv"> replaces its poster once it has
// loaded, and the clip row under it plays a clip. clipRow is also the part stage's.
//
// Moved from the clip-row section and the model-viewer callback of the retired showcase's page
// script: same logic, same constants and the same comments, typed.
// Root: the hero's #clips row of [data-clip] buttons. The viewer it drives is #mv, found by
// its id as the old script found it. <model-viewer> itself is loaded by the site's
// components/ModelViewer.tsx; this module never imports it and types only what it touches.

import { $, type Mount } from "./dom";

/** The <model-viewer> members a clip row uses. */
type ClipView = HTMLElement & { animationName: string | undefined; play(): void };

// Clip buttons: the pressed one is playing. Returns the cleanup that unbinds them.
export function clipRow(root: ParentNode, view: HTMLElement): () => void {
  const player = view as ClipView;
  const buttons = [...root.querySelectorAll<HTMLElement>("[data-clip]")];
  for (const b of buttons) b.onclick = () => {
    root.querySelectorAll("[data-clip]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    player.animationName = b.dataset.clip;
    player.play();
  };
  return () => {
    for (const b of buttons) b.onclick = null;
  };
}

export const mount: Mount = (clips) => {
  const controller = new AbortController(), { signal } = controller;
  let unbind = (): void => {};
  void customElements.whenDefined("model-viewer").then(() => {
    if (signal.aborted) return;
    const mv = $("#mv", clips.ownerDocument);
    if (mv) {
      mv.addEventListener("load", () => {
        mv.classList.remove("invisible");
        mv.previousElementSibling!.classList.add("invisible");
      }, { signal });
      unbind = clipRow(clips, mv);
    }
  });
  return () => {
    controller.abort();
    unbind();
  };
};
