// /games/<game>/<example>/: an example a game made, from its store entry and page.mdx.

import type { Metadata } from "next";
import { notFound } from "next/navigation";
import PageShell from "@/components/PageShell";
import { renderBody } from "@/lib/mdx";
import { gamePage, gameParams, isPlaceholder } from "@/lib/pages";

type Params = { game: string; example: string };

export const dynamicParams = false;

export function generateStaticParams(): Params[] {
  return gameParams();
}

export async function generateMetadata({ params }: { params: Promise<Params> }): Promise<Metadata> {
  const { game, example } = await params;
  if (isPlaceholder(game, example)) return {};
  return { title: `${gamePage(game, example).data.title} · Stage Gen` };
}

export default async function GameExampleRoute({ params }: { params: Promise<Params> }) {
  const { game, example } = await params;
  if (isPlaceholder(game, example)) notFound();
  const page = gamePage(game, example);
  return <PageShell page={page} body={await renderBody(page)} />;
}
