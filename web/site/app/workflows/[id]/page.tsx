// /workflows/<id>/: the workflow's page.mdx bound to its cover example. A workflow without
// an example renders its prose alone; its page source holds no example-bound blocks. A
// build without the cover (a clean clone) shows the examples it does hold instead.

import type { Metadata } from "next";
import ExampleShelf from "@/components/ExampleShelf";
import PageShell from "@/components/PageShell";
import { renderBody } from "@/lib/mdx";
import { workflowPage, workflowParams } from "@/lib/pages";

type Params = { id: string };

export const dynamicParams = false;

export function generateStaticParams(): Params[] {
  return workflowParams();
}

export async function generateMetadata({ params }: { params: Promise<Params> }): Promise<Metadata> {
  const { id } = await params;
  return { title: `${workflowPage(id).data.title} · Stage Gen showcase` };
}

export default async function WorkflowRoute({ params }: { params: Promise<Params> }) {
  const { id } = await params;
  const page = workflowPage(id);
  const body = page.data.coverMissing ? <ExampleShelf page={page} /> : await renderBody(page);
  return <PageShell page={page} body={body} />;
}
