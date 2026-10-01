// The landing: what Stage Gen is, how to install it and where to start, then one ordered
// grid of the catalog's cards (amendment A1). A game-made card carries one quiet line naming
// the game it was made inside. A card whose example is absent (a clean clone) is drawn faded,
// without a link, as a planned page was.

import type { ReactElement } from "react";
import { CHECKER, css } from "@/blocks/shared";
import { href } from "@/lib/media";
import type { Card } from "@/lib/pages";

const LINK = "underline decoration-zinc-300 underline-offset-2 hover:text-zinc-900 dark:hover:text-zinc-100";

function CardBody({ card }: { card: Card }): ReactElement {
  const ground =
    card.hero === null ? "background:#e4e4e7" : card.hero.bg === "transparent" ? CHECKER : `background:${card.hero.bg}`;
  // A wide sheet fills the square with its middle instead of shrinking to a strip.
  const fit = card.heroWide ? "h-full w-full object-cover" : "max-h-full max-w-full object-contain";
  return (
    <>
      <div className="flex aspect-square items-center justify-center overflow-hidden rounded-sm" style={css(ground)}>
        {card.hero === null ? null : <img className={fit} src={card.hero.src} alt="" />}
      </div>
      <h2 className="mt-4 font-medium group-hover:underline group-hover:underline-offset-2">{card.title}</h2>
      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{card.promise}</p>
      <p className="mt-3 text-sm text-zinc-500">{card.meta}</p>
      {card.madeInside === null ? null : <p className="mt-1 text-sm text-zinc-400">{card.madeInside}</p>}
    </>
  );
}

/** The cards of the grid, in order: a link each, or a faded card for an absent example. */
export function Cards({ cards }: { cards: readonly Card[] }): ReactElement {
  return (
    <>
      {cards.map((card) =>
        card.href === null ? (
          <div key={card.order} className="opacity-50">
            <CardBody card={card} />
          </div>
        ) : (
          <a key={card.order} className="group block" href={card.href}>
            <CardBody card={card} />
          </a>
        ),
      )}
    </>
  );
}

export default function Landing({ cards }: { cards: readonly Card[] }): ReactElement {
  return (
    <>
      <header className="border-b border-zinc-200 dark:border-zinc-800">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6 text-sm text-zinc-900 dark:text-zinc-100">
          Stage Gen
          <a className="text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100" href={href("/docs/")}>
            Docs
          </a>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 pb-20 pt-12">
        <h1 className="max-w-3xl text-3xl font-semibold tracking-tight">
          Asset workflows you can plan offline, run, inspect and cache.
        </h1>
        <p className="mt-3 max-w-2xl text-lg text-zinc-600 dark:text-zinc-400">
          Stage Gen is a command line and Python SDK for generating assets. Each workflow is a long chain of models,
          local tools and checks, held as one graph that turns a small input into a named deliverable. Every picture
          below is from a real run.
        </p>
        <pre className="mt-6 max-w-2xl overflow-x-auto rounded-md border border-zinc-200 bg-zinc-50 p-4 font-mono text-[13px] leading-relaxed text-zinc-800 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200">
          {"uv sync --frozen\nuv run stage-gen list"}
        </pre>
        <p className="mt-4 flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <a className={LINK} href={href("/docs/getting-started/")}>
            Get started
          </a>
          <a className={LINK} href={href("/docs/cli/")}>
            Command line
          </a>
          <a className={LINK} href={`${href("/docs/")}#workflows`}>
            All workflows
          </a>
        </p>
        <div className="mt-12 grid gap-10 sm:grid-cols-2 lg:grid-cols-3">
          <Cards cards={cards} />
        </div>
      </main>
    </>
  );
}
