// Player: a copy button: it copies its data-copy text and says so on its label for a moment.
//
// Moved from the copy section of the retired showcase's page script: same logic, same
// constants, typed.
// Root: button[data-copy], whose <span> is the label.

import type { Mount } from "./dom";

export const mount: Mount = (button) => {
  const controller = new AbortController(), { signal } = controller;
  const timers = new Set<ReturnType<typeof setTimeout>>();
  button.addEventListener("click", async () => {
    const label = button.querySelector("span")!, before = label.textContent;
    try {
      await navigator.clipboard.writeText(button.dataset.copy as string);
      label.textContent = "Copied";
    } catch {
      label.textContent = "Select and copy by hand";
    }
    const timer = setTimeout(() => {
      timers.delete(timer);
      label.textContent = before;
    }, 1500);
    timers.add(timer);
  }, { signal });
  return () => {
    controller.abort();
    timers.forEach(clearTimeout);
    timers.clear();
  };
};
