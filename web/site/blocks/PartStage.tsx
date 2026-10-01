// <PartStage>: The delivered model with each of its parts shown or hidden on its own.
// Port of the retired showcase's `part_stage` component.
// The player is web/ui/players/part-stage.ts, mounted by <PartStagePlayer>; it reads the JSON
// config and the data-* hooks below.

import type { JsonObject } from "@stage-gen/ui/contracts/wire";
import { capitalize, picture } from "@/lib/page";
import PartStagePlayer from "@/components/players/PartStagePlayer";
import type { BlockProps } from "./shared";
import { ClipButtons, css, ground, MdxError, SEGMENT, textOf } from "./shared";

export interface PartStageProps {
  readonly output: string;
  readonly clip?: string;
}

/**
 * The delivered model with each of its parts shown or hidden on its own.
 *
 * The export keeps the parts it was fitted from as separate meshes on one skeleton, which is what
 * lets a game swap one of them. The buttons hide a part by its material, so the rest keeps
 * playing the chosen clip. The element's sentence is the caption.
 */
export default function PartStage({ page, children, output, clip }: BlockProps<PartStageProps>) {
  const model = page.record.outputs[output] as JsonObject | undefined;
  const parts = (model?.parts ?? null) as readonly JsonObject[] | null;
  if (model === undefined || model.kind !== "model" || !parts || parts.length === 0) {
    throw new MdxError(`<PartStage output='${output}'> is not a model made of separate parts`);
  }
  const clips = (model.clips ?? []) as readonly string[];
  const first = clip || clips[0];
  const viewer = (
    <div
      className="relative aspect-square w-full max-w-[520px] overflow-hidden rounded-sm"
      style={css(ground(picture(model.poster, "poster")))}
    >
      <model-viewer
        className="absolute inset-0 h-full w-full"
        src={String(model.src)}
        loading="lazy"
        camera-controls=""
        autoplay=""
        animation-name={first}
        shadow-intensity="0"
        interaction-prompt="none"
      />
    </div>
  );
  const rows = parts.map((part) => (
    <div key={String(part.id)} className="flex items-center gap-3">
      <button data-part={String(part.id)} aria-pressed="true" className={`${SEGMENT} w-16`}>
        {capitalize(String(part.id))}
      </button>
      <span className="text-zinc-500">{`${Number(part.triangles).toLocaleString("en-US")} triangles`}</span>
    </div>
  ));
  const controls = (
    <div className="flex flex-col gap-3 text-sm">
      {rows}
      <div className="mt-3 flex flex-wrap gap-1.5">
        <ClipButtons clips={clips} first={first} />
      </div>
      <p className="mt-3 max-w-md text-sm text-zinc-500">{textOf(children)}</p>
    </div>
  );
  const config = Object.fromEntries(parts.map((part) => [String(part.id), part.materials]));
  return (
    <PartStagePlayer
      config={JSON.stringify(config)}
      className="mt-6 grid items-start gap-8 md:grid-cols-[minmax(0,520px)_1fr]"
    >
      {viewer}
      {controls}
    </PartStagePlayer>
  );
}
