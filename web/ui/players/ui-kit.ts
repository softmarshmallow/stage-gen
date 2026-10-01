// Player: the UI kit: the button state images as CSS variables, the panel's resize grip, the icon captions.
//
// Moved from the [data-ui-kit] section of the retired showcase's page script: same logic,
// same constants and the same comments, typed.
// Root: [data-ui-kit]. Hooks inside it: [data-panel], [data-grip], [data-glyph],
// button[data-n|data-h|data-p|data-d]; the caption is the next sibling's [data-kit-caption].

import type { Mount } from "./dom";

export const mount: Mount = (kit) => {
  const controller = new AbortController(), { signal } = controller;
  kit.querySelectorAll<HTMLButtonElement>("button[data-n]").forEach((b) => {
    for (const k of "nhpd") {
      const url = new URL(b.dataset[k]!, location.href);
      b.style.setProperty(`--${k}`, `url("${url}")`);
      new Image().src = url.href; // load every state up front, so the first hover does not flash empty
    }
  });
  kit.querySelectorAll<HTMLElement>("[data-grip]").forEach((grip) => {
    const box = grip.previousElementSibling as HTMLElement;
    let start: { x: number; y: number; w: number; h: number } | null = null;
    grip.addEventListener("pointerdown", (e) => {
      start = { x: e.clientX, y: e.clientY, w: box.offsetWidth, h: box.offsetHeight };
      grip.setPointerCapture(e.pointerId);
      e.preventDefault();
    }, { signal });
    grip.addEventListener("pointermove", (e) => {
      if (!start) return;
      box.style.width = Math.max(parseFloat(box.style.minWidth), start.w + e.clientX - start.x) + "px";
      box.style.height = Math.max(parseFloat(box.style.minHeight), start.h + e.clientY - start.y) + "px";
    }, { signal });
    grip.addEventListener("pointerup", () => {
      start = null;
    }, { signal });
  });
  const caption = kit.nextElementSibling!.querySelector<HTMLElement>("[data-kit-caption]")!,
    idle = caption.textContent;
  kit.querySelectorAll<HTMLElement>("[data-glyph]").forEach((b) => {
    b.addEventListener("mouseenter", () => {
      caption.textContent = `${b.dataset.glyph}: ${b.dataset.words}.`;
    }, { signal });
    b.addEventListener("mouseleave", () => {
      caption.textContent = idle;
    }, { signal });
  });
  return () => {
    controller.abort();
    caption.textContent = idle;
  };
};
