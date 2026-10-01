// Player: the tabs of a <Try>: a tab button shows its own pane and hides the others.
//
// Moved from the tabs section of the retired showcase's page script: same logic, typed.
// Root: [data-tabs]. Hooks inside it: [data-tab], [data-pane].

import type { Mount } from "./dom";

export const mount: Mount = (box) => {
  const controller = new AbortController(), { signal } = controller;
  box.querySelectorAll<HTMLElement>("[data-tab]").forEach((tab) =>
    tab.addEventListener("click", () => {
      box.querySelectorAll("[data-tab]").forEach((t) => t.setAttribute("aria-pressed", String(t === tab)));
      box.querySelectorAll<HTMLElement>("[data-pane]").forEach((p) => p.classList.toggle("hidden", p.dataset.pane !== tab.dataset.tab));
    }, { signal }),
  );
  return () => controller.abort();
};
