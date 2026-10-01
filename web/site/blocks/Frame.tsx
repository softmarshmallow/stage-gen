// <Frame>: One node's pictures with a caption and a link to the node.
// Port of the retired showcase's `frame` component.
//
// `_box` is the aspect class its <Filmstrip> hands it (the showcase's page.frame_box):
// portrait by default, landscape for wide sheets.

import type { ReactElement } from "react";
import { picture } from "@/lib/page";
import type { BlockProps } from "./shared";
import { css, ground, MdxError, NodeLink, textOf } from "./shared";

export interface FrameProps {
  readonly node: string;
  readonly media?: readonly unknown[];
  readonly _box?: string;
}

export default function Frame({
  page,
  children,
  node,
  media,
  _box = "aspect-[3/4]",
}: BlockProps<FrameProps>): ReactElement {
  const record = page.node(node);
  const picks = (media ?? [0]) as readonly number[];
  if (picks.some((i) => i >= record.pictures.length || i < -record.pictures.length)) {
    throw new MdxError(
      `<Frame node='${node}'> has ${record.pictures.length} pictures, asked for [${picks.join(", ")}]`,
    );
  }
  const pictures = picks.map((i) =>
    picture(record.pictures.at(i), `node ${node} picture ${i}`),
  );
  return (
    <figure>
      <div
        className={`flex ${_box} items-center justify-center gap-2 overflow-hidden rounded-sm p-2`}
        style={css(ground(pictures[0]))}
      >
        {pictures.map((p, i) => (
          <img key={i} className="max-h-full min-w-0 flex-1 object-contain" src={p.src} alt="" />
        ))}
      </div>
      <figcaption className="mt-2 text-sm">
        {textOf(children)}
        <br />
        <NodeLink page={page} node={node} />
      </figcaption>
    </figure>
  );
}
