// <UiKit>: A small game screen built from the delivered UI sheets and laid out by the gate's own measurements.
// Port of the retired showcase's `ui_kit` component (and `nine_slice`, TEXT_TONE).
// The player is web/ui/players/ui-kit.ts, mounted on [data-ui-kit] by <UiKitPlayer>.

import UiKitPlayer from "@/components/players/UiKitPlayer";
import type { BlockProps } from "./shared";
import { css, MdxError, pyFloat, pyRound, textOf } from "./shared";
import { picture } from "@/lib/page";

export interface UiKitProps {
  readonly backdrop?: string;
  readonly buttons: readonly unknown[];
}

type Tone = "black" | "white";

interface SheetState {
  readonly state: string;
  readonly src: string;
  readonly width: number;
  readonly height: number;
  readonly text: Tone;
}

interface Sheet {
  readonly insets: { readonly top: number; readonly right: number; readonly bottom: number; readonly left: number };
  readonly draw_scale: number;
  readonly band_fill: string;
  readonly states: readonly SheetState[];
}

interface IconSheet {
  readonly glyphs: readonly { readonly name: string; readonly words: string; readonly src: string }[];
}

/**
 * CSS for a nine-slice sheet at the insets its gate measured, drawn `scale` times its natural size.
 *
 * The source image is left to the caller, so a button can swap it per state from its classes.
 */
function nineSlice(sheet: Sheet, scale: number): string {
  const k = sheet.draw_scale / scale; // sheet pixels per CSS pixel
  const i = sheet.insets;
  const widths = (["top", "right", "bottom", "left"] as const)
    .map((side) => `${pyFloat(pyRound(i[side] / k, 1))}px`)
    .join(" ");
  const repeat = sheet.band_fill === "tile" ? "round" : "stretch";
  return (
    `border-style:solid;border-width:${widths};border-image-slice:${i.top} ${i.right} ${i.bottom} ${i.left} fill;` +
    `border-image-width:${widths};border-image-repeat:${repeat}`
  );
}

const TEXT_TONE: Readonly<Record<Tone, string>> = { black: "text-zinc-900", white: "text-white" };

/**
 * A small game screen built from the delivered UI sheets and laid out by the gate's own measurements.
 *
 * The panel and the top bar stretch by the measured insets, the buttons swap to their hover,
 * pressed and disabled cells, and the icons carry the roles the code names. The text colour on
 * each surface is the one the gate found readable. `backdrop` names an input picture to sit
 * behind it all; the element's sentence is written on the panel.
 */
export default function UiKit({ page, children, backdrop, buttons }: BlockProps<UiKitProps>) {
  const out = page.record.outputs;
  const need = ["panel_frame", "button_rect", "preview_icons"] as const;
  const missing = need.filter((k) => !(k in out));
  if (missing.length > 0) throw new MdxError(`<UiKit> needs the sheets ${missing.join(", ")} in this run`);
  const panel = out.panel_frame as unknown as Sheet;
  const button = out.button_rect as unknown as Sheet;
  const icons = out.preview_icons as unknown as IconSheet;
  const labels = buttons;
  if (labels.length === 0 || !labels.every((x) => typeof x === "string")) {
    throw new MdxError("<UiKit buttons> is a list of button labels");
  }

  const face = panel.states[0];
  const k = panel.draw_scale;
  const panelCss =
    `${nineSlice(panel, 1)};border-image-source:url(${face.src});width:${pyRound((face.width / k) * 0.9)}px;` +
    `height:${pyRound((face.height / k) * 0.75)}px;min-width:${pyRound((panel.insets.left + panel.insets.right) / k + 80)}px;` +
    `min-height:${pyRound((panel.insets.top + panel.insets.bottom) / k + 40)}px`;
  // A grip on the frame's outer corner: the browser's own resize grip would sit under the corner ornament.
  const dialogue = (
    <div className="relative max-w-full">
      <div data-panel="" className={`max-w-full overflow-hidden ${TEXT_TONE[face.text]}`} style={css(panelCss)}>
        <p className="p-3 text-[17px] font-medium leading-relaxed">{textOf(children)}</p>
      </div>
      <button
        data-grip=""
        aria-label="Resize the panel"
        className="absolute -bottom-2 -right-2 flex size-6 cursor-nwse-resize touch-none items-center justify-center rounded-full bg-zinc-900/80 text-white shadow"
      >
        <svg className="size-3" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M3 9h6V3M9 9L3 3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
    </div>
  );

  const barCss = `${nineSlice(panel, 0.32)};border-image-source:url(${face.src})`;
  const bar = (
    <div className="flex flex-wrap items-center gap-1.5" style={css(barCss)}>
      {icons.glyphs.map((g) => (
        <button
          key={g.name}
          data-glyph={g.name.replaceAll("_", " ")}
          data-words={g.words}
          className="size-10 shrink-0 transition-transform hover:-translate-y-0.5"
        >
          <img className="size-full" src={g.src} alt={g.name} />
        </button>
      ))}
    </div>
  );

  const states = Object.fromEntries(button.states.map((s) => [s.state, s]));
  const normal = states.normal;
  const scale = 0.75;
  // The state images reach CSS as variables, which the page's script sets to absolute URLs: a url() inside a
  // variable resolves against the stylesheet that uses it, not against this page.
  const variables = {
    "data-n": states.normal.src,
    "data-h": states.hover.src,
    "data-p": states.pressed.src,
    "data-d": states.disabled.src,
  };
  const buttonCss = `${nineSlice(button, scale)};height:${pyRound(normal.height / (button.draw_scale / scale))}px`;
  const kitButtons = (labels as readonly string[]).map((label, i) => (
    <button
      key={i}
      disabled={i === labels.length - 1}
      className={
        `w-52 px-2 text-[15px] font-semibold ${TEXT_TONE[normal.text]} ` +
        "[border-image-source:var(--n)] hover:[border-image-source:var(--h)] active:[border-image-source:var(--p)] " +
        "disabled:[border-image-source:var(--d)] disabled:opacity-90"
      }
      {...variables}
      style={css(buttonCss)}
    >
      {label}
    </button>
  ));

  let backdropCss = "";
  if (backdrop) {
    const shown = picture(page.record.inputs[backdrop].picture, `input '${backdrop}' picture`);
    // The screen takes the picture's own shape, and still grows if the interface needs more room.
    backdropCss = `background:url(${shown.src}) center/cover;aspect-ratio:${shown.width}/${shown.height}`;
  }
  return (
    <>
      <UiKitPlayer
        className="mt-6 overflow-hidden rounded-sm bg-zinc-200 dark:bg-zinc-800"
        style={css(backdropCss)}
      >
        <div className="flex h-full flex-col gap-6 bg-zinc-950/15 p-6">
          {bar}
          <div className="flex flex-wrap items-start gap-6">
            {dialogue}
            <div className="flex flex-col gap-3">{kitButtons}</div>
          </div>
        </div>
      </UiKitPlayer>
      <p className="mt-3 max-w-3xl text-sm text-zinc-500">
        {"Built in your browser from the sheets the run delivered, laid out by the gate's own measurements. " +
          "Drag the round grip on the panel's corner to resize it; the buttons swap to their hover, pressed and disabled cells. "}
        <span data-kit-caption="">Point at an icon to see its role.</span>
      </p>
    </>
  );
}
