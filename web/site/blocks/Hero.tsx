// <Hero>: The input beside the output, with the output's player when it has one.
// Port of the retired showcase's `hero` component.
//
// The parallax loop's markup (data-parallax-loop, data-loop, data-world, data-loop-map,
// data-loop-reference) is driven by web/ui/players/parallax-loop.ts through
// <ParallaxLoopPlayer>; the model's <model-viewer id="mv"> and #clips by
// web/ui/players/model-viewer.ts through <ModelClipsPlayer>.

import { Fragment, type ReactElement, type ReactNode } from "react";
import type { JsonObject, JsonValue } from "@stage-gen/ui/contracts/wire";
import { picture } from "@/lib/page";
import ModelClipsPlayer from "@/components/players/ModelClipsPlayer";
import ParallaxLoopPlayer from "@/components/players/ParallaxLoopPlayer";
import type { BlockProps } from "./shared";
import { ClipButtons, css, Framed, ground, MdxError, SEGMENT, size } from "./shared";

export interface HeroProps {
  readonly input: string;
  readonly output: string;
  readonly also?: string;
  readonly clip?: string;
}

interface LoopMap {
  readonly id: string;
  readonly label: string;
}

const text = (value: JsonValue | undefined): string => String(value);

export default function Hero({ page, input, output, also, clip }: BlockProps<HeroProps>): ReactElement {
  const source: JsonObject | undefined = page.record.inputs[input];
  const result: JsonObject | undefined = page.record.outputs[output];
  if (source === undefined || result === undefined) {
    throw new MdxError("<Hero> input and output must name entries of the record");
  }
  let left: ReactNode;
  if (source.kind === "text") {
    const brief = text(source.text);
    const split = brief.indexOf("\n\n");
    const first = split < 0 ? brief : brief.slice(0, split);
    const rest = split < 0 ? "" : brief.slice(split + 2);
    left = (
      <>
        <p className="text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">{first}</p>
        {rest.trim() ? (
          <details className="mt-4 text-sm text-zinc-500">
            <summary className="cursor-pointer select-none hover:text-zinc-900 dark:hover:text-zinc-100">
              Rest of the brief
            </summary>
            <p className="mt-3 leading-relaxed">{rest.trim()}</p>
          </details>
        ) : null}
      </>
    );
  } else {
    const shown: JsonObject[] = [source];
    if (also !== undefined) {
      // A second picture the workflow takes, stacked under the first.
      const second = page.record.inputs[also];
      if (second === undefined || second.kind !== "image") {
        throw new MdxError("<Hero also> must name a picture among the record's inputs");
      }
      shown.push(second);
    }
    const box = shown.length === 1 ? "aspect-square" : "aspect-[3/2]";
    left = shown.map((s, i) => (
      <Fragment key={i}>
        {i > 0 ? <div className="h-6"></div> : null}
        <Framed picture={picture(s.picture, `input ${input} picture`)} cls={box} />
        <p className="mt-3 text-xs text-zinc-500">{text(s.file)}</p>
      </Fragment>
    ));
  }
  if (result.kind === "parallax") {
    // The loop's map buttons swap this picture for the map they show.
    left = <div data-loop-reference="">{left}</div>;
  }
  const poster = picture(result.poster, `output ${output} poster`);
  let note = `${text(result.file)} · ${size(Number(result.bytes))}`;
  let right: ReactNode;
  if (result.kind === "parallax") {
    // The layers alone, scrolling for as long as the page is open: a recorded clip cannot show
    // it, because the layers' periods at their own speeds never line up again in a short loop.
    const [width, height] = result.view as readonly number[];
    const maps = result.maps as unknown as readonly LoopMap[];
    const config = JSON.stringify({ maps: result.maps, view: result.view });
    right = (
      <ParallaxLoopPlayer config={config}>
        <div
          data-loop=""
          className="relative w-full overflow-hidden rounded-sm"
          style={css(`aspect-ratio:${width}/${height}`)}
        >
          <div
            data-world=""
            className="absolute left-0 top-0 origin-top-left"
            style={css(`width:${width}px;height:${height}px`)}
          ></div>
        </div>
        <div className="mt-3 flex flex-wrap gap-1">
          {maps.map((m) => (
            <button key={m.id} data-loop-map={m.id} aria-pressed="false" className={SEGMENT}>
              {m.label}
            </button>
          ))}
        </div>
      </ParallaxLoopPlayer>
    );
    note += " · the layers alone, scrolling without end";
  } else if (result.kind === "model") {
    const clips = result.clips as readonly string[];
    const first = clip || clips[0];
    right = (
      <>
        <div className="relative aspect-square overflow-hidden rounded-sm" style={css(ground(poster))}>
          <img className="absolute inset-0 h-full w-full object-contain" src={poster.src} alt="" />
          <model-viewer
            id="mv"
            className="invisible absolute inset-0 h-full w-full"
            src={text(result.src)}
            camera-controls=""
            autoplay=""
            animation-name={first}
            shadow-intensity="0.5"
            interaction-prompt="none"
          ></model-viewer>
        </div>
        <ModelClipsPlayer className="mt-3 flex flex-wrap gap-1.5">
          <ClipButtons clips={clips} first={first} />
        </ModelClipsPlayer>
      </>
    );
    note += " · drag to turn";
  } else {
    right = <Framed picture={poster} cls="aspect-square" />;
  }
  return (
    <div className="mt-10 grid gap-px overflow-hidden rounded-sm border border-zinc-200 bg-zinc-200 md:grid-cols-2 dark:border-zinc-800 dark:bg-zinc-800">
      <div className="bg-white p-6 dark:bg-zinc-950">{left}</div>
      <div className="bg-white p-6 dark:bg-zinc-950">
        {right}
        <p className="mt-3 text-xs text-zinc-500">{note}</p>
      </div>
    </div>
  );
}
