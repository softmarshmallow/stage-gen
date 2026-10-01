// Player: the compare wipe: the range input moves the before layer's clip-path and the handle.
//
// Moved from the [data-compare] section of the retired showcase's page script: same logic,
// same constants and the same comments, typed.
// Root: [data-compare]. Hooks inside it: [data-before], [data-handle], input[type=range].

import type { Mount } from "./dom";

export const mount: Mount = (box) => {
  const controller = new AbortController(), { signal } = controller;
  const range = box.querySelector("input")!, before = box.querySelector<HTMLElement>("[data-before]")!, handle = box.querySelector<HTMLElement>("[data-handle]")!;
  range.addEventListener("input", () => { before.style.clipPath = `inset(0 ${100 - Number(range.value)}% 0 0)`; handle.style.left = range.value + "%"; }, { signal });
  return () => controller.abort();
};
