// /workflows/<id>/contract/: the workflow's contract.md.

import type { Metadata } from "next";
import DocShell from "@/components/DocShell";
import { loadCatalog } from "@/lib/catalog";
import { href } from "@/lib/media";
import { renderMarkdown } from "@/lib/mdx";
import { workflowParams, workflowRoute } from "@/lib/pages";

type Params = { id: string };

export const dynamicParams = false;

export function generateStaticParams(): Params[] {
  return workflowParams();
}

function titleOf(id: string): string {
  const workflow = loadCatalog().workflows.find((entry) => entry.id === id);
  if (workflow === undefined) throw new Error(`no workflow ${id}`);
  return workflow.manifest.title;
}

export async function generateMetadata({ params }: { params: Promise<Params> }): Promise<Metadata> {
  const { id } = await params;
  return { title: `${titleOf(id)} contract · Stage Gen` };
}

export default async function ContractRoute({ params }: { params: Promise<Params> }) {
  const { id } = await params;
  return (
    <DocShell crumbs={[{ title: titleOf(id), href: href(workflowRoute(id)) }, { title: "Contract", href: null }]}>
      {await renderMarkdown(`workflows/${id}/contract.md`)}
    </DocShell>
  );
}
