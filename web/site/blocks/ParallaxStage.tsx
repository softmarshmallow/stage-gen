// <ParallaxStage>: The maps as the game draws them, with the character walking the ground and the camera following.
// Port of the retired showcase's `parallax_stage` component.
//
// Every layer is placed by its anchor and scrolled at its own parallax in the game's 1280x720 view,
// the ground is composed from the map's atlas and grid, and the character walks on it. Toggles
// move every layer at the ground's speed, and mark each layer's wrap and cuts so a seam could be
// looked for. The table below lists the current map's layers and hides any of them. The element's
// sentence is the caption. web/ui/players/parallax-stage.ts drives it through
// [data-parallax-stage], mounted by <ParallaxStagePlayer>.

import ParallaxStagePlayer from "@/components/players/ParallaxStagePlayer";
import type { BlockProps } from "./shared";
import { ACTION, css, KBD, MdxError, SEGMENT, textOf, TOGGLE } from "./shared";
import { LayerTable, parallaxOutput } from "./parallax-shared";

export interface ParallaxStageProps {
  readonly output: string;
}

export default function ParallaxStage({ page, children, output }: BlockProps<ParallaxStageProps>) {
  const backgrounds = parallaxOutput(page, output);
  if (backgrounds === null) {
    throw new MdxError(`<ParallaxStage output='${output}'> is not a set of parallax maps of this run`);
  }
  const [width, height] = backgrounds.view;
  const config = { maps: backgrounds.maps, walker: backgrounds.walker, view: backgrounds.view };
  return (
    <ParallaxStagePlayer config={JSON.stringify(config)} className="mt-6">
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
        aria-label="Map stage: click, then use the arrow keys"
        className="relative w-full select-none overflow-hidden rounded-sm border border-zinc-200 bg-sky-200 outline-none focus-visible:border-zinc-500 dark:border-zinc-800"
        style={css(`aspect-ratio:${width}/${height}`)}
      >
        <div
          data-world=""
          className="absolute left-0 top-0 origin-top-left"
          style={css(`width:${width}px;height:${height}px`)}
        />
        <p data-hint="" className="absolute left-3 top-2 rounded-sm bg-white/80 px-1.5 py-0.5 text-xs text-zinc-600">
          Click here, then <kbd className={KBD}>←</kbd> <kbd className={KBD}>→</kbd> to walk,{" "}
          <kbd className={KBD}>Shift</kbd> to run, <kbd className={KBD}>↑</kbd> or <kbd className={KBD}>Space</kbd> to
          jump
        </p>
      </div>
      <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2">
        <label className={TOGGLE}>
          <input data-opt="auto" type="checkbox" defaultChecked className="accent-zinc-900" /> Walk automatically
        </label>
        <label className={TOGGLE}>
          <input data-opt="flat" type="checkbox" className="accent-zinc-900" /> Every layer at the ground&apos;s speed
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
      <p className="mt-3 max-w-2xl text-sm text-zinc-500">
        {textOf(children)} Each layer is baked for this page the way the game bakes it: resized to the 720-pixel view,
        then given its contrast, saturation, haze and blur by the game&apos;s own formulas.
      </p>
    </ParallaxStagePlayer>
  );
}
