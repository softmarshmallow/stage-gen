// Player: the face rig: one patch per feature by state, blink and wink, the run's timeline, auto blink and talk, the changes overlay.
//
// Moved from the [data-face-rig] section of the retired showcase's page script: same logic,
// same constants and the same comments, typed.
// Root: [data-face-rig], with its config. Hooks inside it: [data-patch], [data-set],
// [data-action], [data-auto], [data-show-changes], [data-changes].

import type { Mount } from "./dom";

interface FaceRigFeature {
  readonly id: string;
  readonly group: string;
  readonly states: readonly string[];
}

interface FaceRigStep {
  readonly duration_ms: number;
  readonly eyes: string;
  readonly mouth: string;
}

/** The block's data-face-rig config (web/site/blocks/FaceRig.tsx). */
export interface FaceRigConfig {
  readonly features: readonly FaceRigFeature[];
  readonly timeline: readonly FaceRigStep[];
}

// Face rig: each eye and the mouth is its own patch; show the one patch per feature that matches its state.
export const mount: Mount<FaceRigConfig> = (box, cfg) => {
  const controller = new AbortController(), { signal } = controller;
  const now: Record<string, string> = Object.fromEntries(cfg.features.map((f) => [f.id, "rest"]));
  const ids = (group: string) => cfg.features.filter((f) => f.group === group).map((f) => f.id);
  const eyes = ids("eyes"),
    mouth = ids("mouth");
  const show = () => {
    box.querySelectorAll<HTMLElement>("[data-patch]").forEach((img) =>
      img.classList.toggle("hidden", now[img.dataset.feature!] !== img.dataset.state),
    );
    box.querySelectorAll<HTMLElement>("[data-set]").forEach((b) =>
      b.setAttribute("aria-pressed", String(now[b.dataset.set!] === b.dataset.state)),
    );
  };
  const set = (features: readonly string[], state: string) => {
    features.forEach((id) => {
      now[id] = state;
    });
    show();
  };
  let timers: ReturnType<typeof setTimeout>[] = [];
  const later = (fn: () => void, ms: number) => timers.push(setTimeout(fn, ms));
  const stop = () => {
    timers.forEach(clearTimeout);
    timers = [];
  };
  // The run's own blink: the first stretch of its timeline where the eyes leave rest.
  const first = cfg.timeline.findIndex((s) => s.eyes !== "rest"),
    blink: [string, number][] = [];
  for (let i = first; i >= 0 && i < cfg.timeline.length && cfg.timeline[i].eyes !== "rest"; i++)
    blink.push([cfg.timeline[i].eyes, cfg.timeline[i].duration_ms]);
  const run = (features: readonly string[], steps: readonly (readonly [string, number])[]) => {
    let t = 0;
    for (const [state, ms] of steps) {
      later(() => set(features, state), t);
      t += ms;
    }
    later(() => set(features, "rest"), t);
  };
  box.querySelectorAll<HTMLElement>("[data-set]").forEach((b) =>
    b.addEventListener("click", () => {
      stop();
      set([b.dataset.set!], b.dataset.state!);
    }, { signal }),
  );
  box.querySelector('[data-action="blink"]')!.addEventListener("click", () => run(eyes, blink), { signal });
  box
    .querySelector('[data-action="wink"]')!
    .addEventListener("click", () =>
      run(eyes.slice(-1), blink.map(([s, ms]) => [s, s.endsWith("closed") ? ms * 3 : ms] as const)),
    { signal });
  box.querySelector('[data-action="timeline"]')!.addEventListener("click", () => {
    stop();
    let t = 0;
    for (const s of cfg.timeline) {
      later(() => {
        set(eyes, s.eyes);
        set(mouth, s.mouth);
      }, t);
      t += s.duration_ms;
    }
    later(() => {
      set(eyes, "rest");
      set(mouth, "rest");
    }, t);
  }, { signal });
  const mouthStates = cfg.features.find((f) => f.group === "mouth")?.states ?? ["rest"];
  let blinking: ReturnType<typeof setTimeout> | undefined, talking: ReturnType<typeof setTimeout> | undefined;
  const blinkLoop = () => {
    run(eyes, blink);
    blinking = setTimeout(blinkLoop, 1800 + Math.random() * 2700);
  };
  const talkLoop = () => {
    set(mouth, mouthStates[Math.floor(Math.random() * mouthStates.length)]);
    talking = setTimeout(talkLoop, 120 + Math.random() * 120);
  };
  box.querySelector('[data-auto="blink"]')!.addEventListener("change", (e) => {
    clearTimeout(blinking);
    if ((e.target as HTMLInputElement).checked) blinkLoop();
  }, { signal });
  box.querySelector('[data-auto="talk"]')!.addEventListener("change", (e) => {
    clearTimeout(talking);
    if ((e.target as HTMLInputElement).checked) talkLoop();
    else set(mouth, "rest");
  }, { signal });
  box
    .querySelector("[data-show-changes]")!
    .addEventListener("change", (e) =>
      box.querySelector("[data-changes]")!.classList.toggle("hidden", !(e.target as HTMLInputElement).checked),
    { signal });
  show();
  return () => {
    controller.abort();
    stop();
    clearTimeout(blinking);
    clearTimeout(talking);
  };
};
