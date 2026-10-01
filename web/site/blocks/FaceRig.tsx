// <FaceRig>: The delivered face patches stacked on the rest state, with each eye and the mouth set separately.
// Port of the retired showcase's `face_rig` component (and FEATURE_WORDS).
// The player is web/ui/players/face-rig.ts, mounted on [data-face-rig] by <FaceRigPlayer>.

import FaceRigPlayer from "@/components/players/FaceRigPlayer";
import type { BlockProps } from "./shared";
import { ACTION, CHECKER, css, MdxError, pyFixed, SEGMENT, stateWords, textOf, TOGGLE } from "./shared";

export interface FaceRigProps {
  readonly output: string;
}

interface Feature {
  readonly id: string;
  readonly group: string;
  readonly states: readonly string[];
}

interface Rig {
  readonly kind: string;
  readonly base: string;
  readonly changes: string;
  readonly place: { readonly left: number; readonly top: number; readonly width: number; readonly height: number };
  readonly features: readonly Feature[];
  readonly timeline: readonly unknown[];
  readonly patches: readonly { readonly feature: string; readonly state: string; readonly src: string }[];
  readonly combinations_verified: number;
}

const FEATURE_WORDS: Readonly<Record<string, string>> = {
  canvas_left_eye: "Eye on the left",
  canvas_right_eye: "Eye on the right",
  mouth: "Mouth",
};

/**
 * The delivered face patches stacked on the rest state, with each eye and the mouth set separately.
 *
 * This is what a game does with the output: every feature is its own patch at one offset. The
 * buttons set a feature's state; Blink and Wink replay the run's own blink timing; the timeline
 * button plays the exact timeline the run rendered. The element's sentence is the caption.
 */
export default function FaceRig({ page, children, output }: BlockProps<FaceRigProps>) {
  const found = page.record.outputs[output] as unknown as Rig | undefined;
  if (found === undefined || found.kind !== "face_rig") {
    throw new MdxError(`<FaceRig output='${output}'> is not a face rig of this run`);
  }
  const rig = found;
  const place = rig.place;
  const at = css(
    `left:${pyFixed(place.left, 3)}%;top:${pyFixed(place.top, 3)}%;` +
      `width:${pyFixed(place.width, 3)}%;height:${pyFixed(place.height, 3)}%`,
  );
  const picture = (
    <div className="relative aspect-square w-full max-w-[520px] overflow-hidden rounded-sm" style={css(CHECKER)}>
      <img className="absolute inset-0 size-full" src={rig.base} alt="" />
      {rig.patches.map((p) => (
        <img
          key={`${p.feature}|${p.state}`}
          data-patch=""
          data-feature={p.feature}
          data-state={p.state}
          className="absolute hidden"
          style={at}
          src={p.src}
          alt=""
        />
      ))}
      <img data-changes="" className="absolute hidden" style={at} src={rig.changes} alt="" />
    </div>
  );
  const rows = rig.features.map((f) => (
    <div key={f.id} className="flex flex-wrap items-center gap-3">
      <span className="w-32 text-zinc-500">{FEATURE_WORDS[f.id] ?? f.id}</span>
      <div className="flex gap-1">
        {f.states.map((s) => (
          <button
            key={s}
            data-set={f.id}
            data-state={s}
            aria-pressed={s === "rest" ? "true" : "false"}
            className={SEGMENT}
          >
            {stateWords(f.group, s)}
          </button>
        ))}
      </div>
    </div>
  ));
  const controls = (
    <div className="flex flex-col gap-3 text-sm">
      {rows}
      <div className="mt-3 flex flex-wrap gap-2">
        <button data-action="blink" className={ACTION}>
          Blink
        </button>
        <button data-action="wink" className={ACTION}>
          Wink
        </button>
        <button data-action="timeline" className={ACTION}>
          Play the run&apos;s timeline
        </button>
      </div>
      <label className={`${TOGGLE} mt-1`}>
        <input data-auto="blink" type="checkbox" className="accent-zinc-900" /> Blink on its own
      </label>
      <label className={TOGGLE}>
        <input data-auto="talk" type="checkbox" className="accent-zinc-900" /> Talk
      </label>
      <label className={TOGGLE}>
        <input data-show-changes="" type="checkbox" className="accent-zinc-900" /> Show every pixel that can change
      </label>
      <p className="mt-3 max-w-md text-sm text-zinc-500">
        {textOf(children)}
        {` All ${rig.combinations_verified} combinations the run rendered were rebuilt from these patches when this page was built, pixel for pixel.`}
      </p>
    </div>
  );
  const config = JSON.stringify({ features: rig.features, timeline: rig.timeline });
  return (
    <FaceRigPlayer config={config} className="mt-6 grid items-start gap-8 md:grid-cols-[minmax(0,520px)_1fr]">
      {picture}
      {controls}
    </FaceRigPlayer>
  );
}
