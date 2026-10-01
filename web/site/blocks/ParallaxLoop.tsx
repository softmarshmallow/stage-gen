// <ParallaxLoop>: A map's layers alone, scrolling without end, to play with; no ground and no character.
// Port of the retired showcase's `parallax_loop` component.
//
// Every layer is placed by its anchor and scrolled at its own parallax in the game's 1280x720 view.
// The camera runs on its own at a chosen speed and direction, or follows a drag or the arrow keys.
// Toggles move every layer at one speed and mark each layer's wrap and cuts; the table turns each
// layer on or off and changes its speed, height and size. The element's sentence is the caption.
// web/ui/players/parallax-playground.ts drives it through [data-parallax-playground], mounted
// by <ParallaxPlaygroundPlayer>.

import ParallaxPlaygroundPlayer from "@/components/players/ParallaxPlaygroundPlayer";
import type { BlockProps } from "./shared";
import { ACTION, css, KBD, MdxError, SEGMENT, textOf, TOGGLE } from "./shared";
import { LayerTable, parallaxOutput } from "./parallax-shared";

export interface ParallaxLoopProps {
  readonly output: string;
}

export default function ParallaxLoop({ page, children, output }: BlockProps<ParallaxLoopProps>) {
  const backgrounds = parallaxOutput(page, output);
  if (backgrounds === null) {
    throw new MdxError(`<ParallaxLoop output='${output}'> is not a set of parallax maps of this run`);
  }
  const [width, height] = backgrounds.view;
  const config = { maps: backgrounds.maps, view: backgrounds.view };
  return (
    <ParallaxPlaygroundPlayer config={JSON.stringify(config)} className="mt-6">
      <div className="mb-3 flex flex-wrap gap-1">
        {backgrounds.maps.map((m) => (
          <button key={m.id} data-map={m.id} aria-pressed="false" className={SEGMENT}>
            {m.label}
          </button>
        ))}
      </div>
      <div
        data-stage=""
        tabIndex={0}
        aria-label="Layers: drag to scroll, or use the arrow keys"
        className="relative w-full cursor-grab touch-none select-none overflow-hidden rounded-sm border border-zinc-200 bg-sky-200 outline-none active:cursor-grabbing focus-visible:border-zinc-500 dark:border-zinc-800"
        style={css(`aspect-ratio:${width}/${height}`)}
      >
        <div
          data-world=""
          className="absolute left-0 top-0 origin-top-left"
          style={css(`width:${width}px;height:${height}px`)}
        />
        <p data-hint="" className="absolute left-3 top-2 rounded-sm bg-white/80 px-1.5 py-0.5 text-xs text-zinc-600">
          Drag to scroll, or click and use <kbd className={KBD}>←</kbd> <kbd className={KBD}>→</kbd>;{" "}
          <kbd className={KBD}>Space</kbd> pauses
        </p>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-3">
        <button data-play="" aria-pressed="true" className={`${ACTION} w-16`}>
          Pause
        </button>
        <label className={TOGGLE}>
          Camera{" "}
          <input
            data-speed=""
            type="range"
            min="-600"
            max="600"
            step="10"
            defaultValue="110"
            className="w-40 accent-zinc-900"
          />
          <span data-speed-value="" className="w-24 tabular-nums" />
        </label>
        <label className={TOGGLE}>
          <input data-opt="flat" type="checkbox" className="accent-zinc-900" /> Every layer at one speed
        </label>
        <label className={TOGGLE}>
          <input data-opt="marks" type="checkbox" className="accent-zinc-900" /> Mark where each layer repeats, and
          where it was cut
        </label>
      </div>
      <LayerTable />
      <div className="mt-3 flex flex-wrap gap-2">
        <button data-placement="game" className={ACTION}>
          Back to the game&apos;s placement
        </button>
      </div>
      <p className="mt-3 max-w-2xl text-sm text-zinc-500">{textOf(children)}</p>
    </ParallaxPlaygroundPlayer>
  );
}
