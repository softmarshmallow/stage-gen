// /workflows/<id>/<example>/: an example with its own prose (examples/<example>.mdx),
// bound to that example rather than the workflow's cover.

import type { Metadata } from "next";
import { notFound } from "next/navigation";
import PageShell from "@/components/PageShell";
import { renderBody } from "@/lib/mdx";
import { exampleParams, examplePage, isPlaceholder } from "@/lib/pages";

type Params = { id: string; example: string };

export const dynamicParams = false;

export function generateStaticParams(): Params[] {
  return exampleParams();
}

export async function generateMetadata({ params }: { params: Promise<Params> }): Promise<Metadata> {
  const { id, example } = await params;
  if (isPlaceholder(id, example)) return {};
  return { title: `${examplePage(id, example).data.title} · Stage Gen` };
}

export default async function ExampleRoute({ params }: { params: Promise<Params> }) {
  const { id, example } = await params;
  if (isPlaceholder(id, example)) notFound();
  const page = examplePage(id, example);
  return <PageShell page={page} body={await renderBody(page)} />;
}
