// What a workflow page shows in place of its body when this build lacks the cover example
// its page.mdx binds (a clean clone, built with --allow-missing-examples): a note, and the
// examples the build does hold, such as the library characters, each by its first
// output's poster.

import type { ReactElement } from "react";
import { Framed } from "@/blocks/shared";
import { picture, type Page } from "@/lib/page";

export default function ExampleShelf({ page }: { page: Page }): ReactElement {
  const present = (page.data.workflow?.examples ?? []).filter((entry) => entry.example !== null);
  return (
    <>
      <p className="mt-6 max-w-3xl text-zinc-700 dark:text-zinc-300">
        This build does not hold the example this page is written around. These examples are here.
      </p>
      <div className="mt-10 grid gap-10 sm:grid-cols-2 lg:grid-cols-3">
        {present.map((entry) => {
          const first = entry.example === null ? undefined : Object.values(entry.example.outputs)[0];
          return (
            <figure key={entry.id}>
              {first?.poster === undefined ? null : (
                <Framed picture={picture(first.poster, `${entry.id} poster`)} cls="aspect-square" />
              )}
              <figcaption className="mt-3 text-sm">{entry.title}</figcaption>
            </figure>
          );
        })}
      </div>
    </>
  );
}
