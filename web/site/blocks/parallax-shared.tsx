// What <ParallaxLoop> and <ParallaxStage> share: the record's parallax output, read as the
// player's config types, and the layer table's head.

import type { ParallaxMap, ParallaxWalker } from "@stage-gen/ui/players/parallax";
import type { Page } from "@/lib/page";
import { HEAD } from "./shared";

/** A record's set of parallax maps: the maps, the character that walks them, and the game's view. */
export interface ParallaxOutput {
  readonly kind: "parallax";
  readonly maps: readonly ParallaxMap[];
  readonly walker: ParallaxWalker;
  readonly view: readonly [number, number];
}

/** The output `name` when it is a set of parallax maps of this run, else null. */
export function parallaxOutput(page: Page, name: string): ParallaxOutput | null {
  const value = page.record.outputs[name];
  if (value === undefined || value.kind !== "parallax") return null;
  return value as unknown as ParallaxOutput;
}

/** The layer table's head; the player fills `[data-layers]` with one row per layer. */
export function LayerTable() {
  return (
    <div className="mt-5 overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr>
            <th className={`${HEAD} w-8`} />
            <th className={HEAD}>Layer</th>
            <th className={HEAD}>Moves at</th>
            <th className={HEAD}>Repeats every</th>
            <th className={HEAD}>How it loops</th>
            <th className={HEAD}>Move down</th>
            <th className={HEAD}>Size</th>
          </tr>
        </thead>
        <tbody data-layers="" />
      </table>
    </div>
  );
}
