// <Compare>: Two same-sized pictures of one node, one over the other, with a handle to wipe between them.
// Port of the retired showcase's `compare` component.
// The wipe itself is web/ui/players/compare.ts, mounted on [data-compare] by <ComparePlayer>.

import { picture } from "@/lib/page";
import ComparePlayer from "@/components/players/ComparePlayer";
import type { BlockProps } from "./shared";
import { css, ground, MdxError, NodeLink, pyRound, textOf } from "./shared";

export interface CompareProps {
  readonly node: string;
  readonly media?: readonly unknown[];
  readonly left: string;
  readonly right: string;
  readonly at?: number;
}

/** Python's repr of a list of picks, for the error message: "[0, 1]". */
function pyList(values: readonly unknown[]): string {
  return `[${values.map((value) => (typeof value === "string" ? `'${value}'` : String(value))).join(", ")}]`;
}

/**
 * Two same-sized pictures of one node, one over the other, with a handle to wipe between them.
 *
 * `at` is where the handle starts, in percent from the left; halfway unless the middle is the
 * very thing the reader should see first.
 */
export default function Compare({ page, children, node, media, left, right, at }: BlockProps<CompareProps>) {
  const record = page.node(node);
  const picks = media ?? [0, 1];
  const pictures = record.pictures;
  // Python indexes with each pick, negative from the end, and unpacks exactly two.
  const index = (pick: unknown): number | null =>
    typeof pick === "number" && Number.isInteger(pick) && pick >= -pictures.length && pick < pictures.length
      ? (pick + pictures.length) % pictures.length
      : null;
  const chosen = picks.map(index);
  if (chosen.length !== 2 || chosen.some((i) => i === null)) {
    throw new MdxError(
      `<Compare node='${node}'> needs two of its ${pictures.length} pictures, asked for ${pyList(picks)}`,
    );
  }
  const before = picture(pictures[chosen[0] as number]);
  const after = picture(pictures[chosen[1] as number]);
  if (before.width !== after.width || before.height !== after.height) {
    throw new MdxError(`<Compare node='${node}'>: the two pictures differ in size`);
  }
  const label = "absolute top-2 rounded-sm bg-zinc-900/70 px-1.5 py-0.5 text-xs text-white";
  const start = at ?? 50;
  if (!(start >= 0 && start <= 100)) {
    throw new MdxError(`<Compare at=${start}> must be a percentage`);
  }
  return (
    <figure className="mt-6">
      {/* A transparent picture sits on its checkerboard in both layers, so the one underneath never shows through.
          Height is capped at 560 px, so a square sheet does not fill the screen while a wide one keeps the full width. */}
      <ComparePlayer
        className="relative select-none overflow-hidden rounded-sm"
        style={css(
          `aspect-ratio:${after.width}/${after.height};` +
            `max-width:${pyRound((560 * after.width) / after.height)}px;${ground(after)}`,
        )}
      >
        <img className="absolute inset-0 h-full w-full" src={after.src} alt="" />
        <div
          data-before=""
          className="absolute inset-0"
          style={css(`clip-path:inset(0 ${100 - start}% 0 0);${ground(before)}`)}
        >
          <img className="h-full w-full" src={before.src} alt="" />
        </div>
        <div
          data-handle=""
          className="pointer-events-none absolute inset-y-0 w-0.5 -translate-x-1/2 bg-white shadow"
          style={css(`left:${start}%`)}
        >
          <span className="absolute top-1/2 left-1/2 flex size-7 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-white text-xs text-zinc-700 shadow">
            ⇆
          </span>
        </div>
        <span className={`${label} left-2`}>{left}</span>
        <span className={`${label} right-2`}>{right}</span>
        <input
          type="range"
          min="0"
          max="100"
          defaultValue={start}
          aria-label="Wipe between the two pictures"
          className="absolute inset-0 h-full w-full cursor-ew-resize opacity-0"
        />
      </ComparePlayer>
      <figcaption className="mt-3 max-w-3xl text-sm text-zinc-600 dark:text-zinc-400">
        {textOf(children)}
        <br />
        <NodeLink page={page} node={node} />
      </figcaption>
    </figure>
  );
}
