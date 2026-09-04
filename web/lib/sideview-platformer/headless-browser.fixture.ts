/**
 * The browser surface the prepared runtime loads through, replaced by the smallest honest stand-in.
 *
 * The scene's load path is a browser: it fetches a manifest, decodes images into canvases, measures
 * their alpha, and hands the result to Phaser. None of that exists under `bun test`, and none of it
 * needs to: the runtime already ships a complete answer for an asset that will not load — the
 * presentation fallback, a magenta placeholder plus one bounded diagnostic. So this serves the
 * manifest and refuses everything else, and the run that follows is the runtime's own degraded
 * presentation path with every gameplay number intact.
 *
 * That is the trade the replay makes, stated once: geometry is authored and therefore real, art is
 * absent and therefore uniform. A golden frame's render bounds are the placeholder's; a golden
 * frame's positions, collisions, reaches, spawns and transitions are the game's.
 */

type FetchResponse = {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
  blob: () => Promise<unknown>;
};

type Installed = Readonly<{ restore: () => void }>;

function stubCanvasContext(): Record<string, unknown> {
  const noop = () => undefined;
  return {
    fillStyle: "",
    strokeStyle: "",
    lineWidth: 0,
    font: "",
    textAlign: "",
    textBaseline: "",
    globalAlpha: 1,
    globalCompositeOperation: "source-over",
    imageSmoothingEnabled: false,
    fillRect: noop,
    clearRect: noop,
    strokeRect: noop,
    beginPath: noop,
    closePath: noop,
    moveTo: noop,
    lineTo: noop,
    arc: noop,
    stroke: noop,
    fill: noop,
    save: noop,
    restore: noop,
    translate: noop,
    scale: noop,
    rotate: noop,
    drawImage: noop,
    fillText: noop,
    measureText: () => ({ width: 0 }),
    getImageData: (_x: number, _y: number, width: number, height: number) => ({
      width,
      height,
      data: new Uint8ClampedArray(Math.max(1, width * height * 4)),
    }),
    putImageData: noop,
  };
}

function stubCanvas(): Record<string, unknown> {
  const context = stubCanvasContext();
  return { width: 300, height: 150, getContext: () => context };
}

export type HeadlessBrowserOptions = Readonly<{
  /** The one document the runtime is allowed to fetch. Everything else answers 404. */
  manifest: unknown;
  /** Simulation time, so `performance.now()` is the harness's clock and not the machine's. */
  now: () => number;
  /** Leave the runtime's own warnings and load failures on stderr, for tuning a script. */
  verbose?: boolean;
}>;

/**
 * Install the surface, and hand back the exact undo.
 *
 * `bun test` shares one process across files, so every global written here is written back on the
 * way out — including the ones that were absent, which are deleted rather than left as stubs.
 */
export function installHeadlessBrowser(options: HeadlessBrowserOptions): Installed {
  const globals = globalThis as unknown as Record<string, unknown>;
  const previous = new Map<string, { present: boolean; value: unknown }>();
  const set = (key: string, value: unknown) => {
    previous.set(key, { present: key in globals, value: globals[key] });
    Object.defineProperty(globals, key, { value, configurable: true, writable: true });
  };

  set("document", { createElement: (tag: string) => (tag === "canvas" ? stubCanvas() : {}) });
  set("performance", { now: options.now });
  set("Audio", class {
    loop = false;
    volume = 1;
    constructor(readonly src: string = "") {}
    play(): Promise<void> {
      return Promise.reject(new Error("headless audio is never unlocked"));
    }
    pause(): void {
      // Nothing is playing; the call is recorded only by the scene's own bookkeeping.
    }
  });
  set("fetch", (input: unknown): Promise<FetchResponse> => {
    const url = String(input);
    if (url.endsWith("manifest.json")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => options.manifest,
        blob: async () => ({}),
      });
    }
    return Promise.resolve({
      ok: false,
      status: 404,
      json: async () => ({}),
      blob: async () => ({}),
    });
  });

  // The runtime warns once per diagnostic and there are dozens of them under a total asset refusal;
  // they are captured in the snapshot's `diagnostics`, which is where the golden reads them.
  const consoleWarn = console.warn;
  const consoleError = console.error;
  if (options.verbose !== true) {
    console.warn = () => undefined;
    console.error = () => undefined;
  }

  return {
    restore: () => {
      console.warn = consoleWarn;
      console.error = consoleError;
      for (const [key, entry] of previous) {
        if (entry.present) {
          Object.defineProperty(globals, key, {
            value: entry.value,
            configurable: true,
            writable: true,
          });
        } else {
          delete globals[key];
        }
      }
    },
  };
}
