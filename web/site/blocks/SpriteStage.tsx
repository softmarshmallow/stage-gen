// <SpriteStage>: The delivered strips on a stage, drawn the way the game draws them, to play one by one or to drive.
// Port of the retired showcase's `sprite_stage` component.
// The player is web/ui/players/sprite-stage.ts, mounted by <SpriteStagePlayer>; it reads the
// JSON config and the data-* hooks below.

import type { JsonObject } from "@stage-gen/ui/contracts/wire";
import { capitalize } from "@/lib/page";
import SpriteStagePlayer from "@/components/players/SpriteStagePlayer";
import type { BlockProps } from "./shared";
import { css, KBD, MdxError, SEGMENT, textOf, TOGGLE } from "./shared";

export interface SpriteStageProps {
  readonly output: string;
}

const MOTION_WORDS: Readonly<Record<string, string>> = {
  idle: "Idle",
  walk: "Walk",
  run: "Run",
  jump: "Jump",
  crouch: "Crouch",
  climb_ladder: "Ladder",
  climb_rope: "Rope",
  basic_attack: "Attack",
  skill_cast: "Cast",
  hurt: "Hurt",
  death: "Death",
};
const MOTION_GROUPS: readonly (readonly [string, readonly string[]])[] = [
  ["Move", ["idle", "walk", "run", "jump", "crouch"]],
  ["Climb", ["climb_ladder", "climb_rope"]],
  ["Act", ["basic_attack", "skill_cast"]],
  ["React", ["hurt", "death"]],
];

/**
 * The delivered strips on a stage, drawn the way the game draws them, to play one by one or to drive.
 *
 * Each strip is scaled by the ruler and its own size correction and stood on the ground by the
 * bottom of its cell; right-facing strips are mirrored for left. Loops loop, one-shots play once,
 * a hold holds its frame, and a climb steps its frames by the distance climbed. The buttons play a
 * state; the keyboard drives the character as a game would. The element's sentence is the caption.
 */
export default function SpriteStage({ page, children, output }: BlockProps<SpriteStageProps>) {
  const sprite = page.record.outputs[output] as JsonObject | undefined;
  if (sprite === undefined || sprite.kind !== "sprite_set") {
    throw new MdxError(`<SpriteStage output='${output}'> is not an animation set of this run`);
  }
  const known = (sprite.states as readonly JsonObject[]).map((s) => String(s.state));
  const groups: [string, string[]][] = MOTION_GROUPS.map(([label, names]) => [
    label,
    names.filter((s) => known.includes(s)),
  ]);
  groups.push([
    "Other",
    known.filter((s) => !MOTION_GROUPS.some(([, names]) => names.includes(s))),
  ]);
  const rows = groups
    .filter(([, names]) => names.length > 0)
    .map(([label, names]) => (
      <div key={label} className="flex flex-wrap items-center gap-3">
        <span className="w-14 text-zinc-500">{label}</span>
        <div className="flex flex-wrap gap-1">
          {names.map((s) => (
            <button key={s} data-play={s} aria-pressed="false" className={SEGMENT}>
              {MOTION_WORDS[s] ?? capitalize(s.replaceAll("_", " "))}
            </button>
          ))}
        </div>
      </div>
    ));
  const stage = (
    <div
      data-stage=""
      tabIndex={0}
      aria-label="Character stage: click, then use the arrow keys"
      className="relative w-full touch-manipulation select-none overflow-hidden rounded-sm border border-zinc-200 bg-zinc-50 outline-none focus-visible:border-zinc-500 dark:border-zinc-800 dark:bg-zinc-900"
      style={css("aspect-ratio:16/7")}
    >
      <div
        data-ground=""
        className="absolute inset-x-0 bottom-0 top-[84%] border-t border-zinc-300 bg-zinc-100 dark:border-zinc-700 dark:bg-zinc-800/60"
      />
      <div data-ladder="" className="absolute top-0 hidden border-x-[3px] border-zinc-400 dark:border-zinc-500" />
      <div data-rope="" className="absolute top-0 hidden w-[3px] bg-zinc-400 dark:bg-zinc-500" />
      <div data-shadow="" className="absolute rounded-[50%] bg-black blur-[3px]" />
      <div data-body="" className="absolute bg-no-repeat" />
      <p data-hint="" className="absolute left-3 top-2 text-xs text-zinc-400">
        {"Click here, then use "}
        <kbd className={KBD}>←</kbd> <kbd className={KBD}>→</kbd> <kbd className={KBD}>↑</kbd>{" "}
        <kbd className={KBD}>↓</kbd>
      </p>
    </div>
  );
  const controls = (
    <>
      <div className="mt-5 grid gap-6 text-sm md:grid-cols-[1fr_minmax(0,22rem)]">
        <div className="flex flex-col gap-2.5">{rows}</div>
        <div className="flex flex-col gap-2">
          <label className={TOGGLE}>
            <input data-opt="raw" type="checkbox" className="accent-zinc-900" /> Without the size correction
          </label>
          <label className={TOGGLE}>
            <input data-opt="box" type="checkbox" className="accent-zinc-900" /> Show each frame&apos;s box
          </label>
          <p className="mt-2 text-xs leading-relaxed text-zinc-500">
            <kbd className={KBD}>←</kbd> <kbd className={KBD}>→</kbd>
            {" walk, with "}
            <kbd className={KBD}>Shift</kbd>
            {" run, "}
            <kbd className={KBD}>↑</kbd>
            {" jump, "}
            <kbd className={KBD}>↓</kbd>
            {" crouch, "}
            <kbd className={KBD}>Z</kbd>
            {" attack, "}
            <kbd className={KBD}>X</kbd>
            {" cast. On a ladder or rope, "}
            <kbd className={KBD}>↑</kbd> <kbd className={KBD}>↓</kbd>
            {" climb and "}
            <kbd className={KBD}>←</kbd> <kbd className={KBD}>→</kbd>
            {" let go."}
          </p>
        </div>
      </div>
      <p data-info="" className="mt-4 min-h-5 text-sm text-zinc-700 dark:text-zinc-300" />
      <p className="mt-2 max-w-2xl text-sm text-zinc-500">
        {textOf(children)}
        {
          " Every strip was cut again from the model's own picture when this page was built, and matched the delivered file byte for byte."
        }
      </p>
    </>
  );
  const config = { states: sprite.states, per_unit: sprite.per_unit, baseline: sprite.baseline };
  return (
    <SpriteStagePlayer config={JSON.stringify(config)} className="mt-6">
      {stage}
      {controls}
    </SpriteStagePlayer>
  );
}
