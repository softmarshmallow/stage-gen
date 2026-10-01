// /workflows/<id>/contract/: the workflow's contract.md.

import type { Metadata } from "next";
import DocShell from "@/components/DocShell";
import { loadCatalog } from "@/lib/catalog";
import { href } from "@/lib/media";
import { renderMarkdown } from "@/lib/mdx";
import { docLink, workflowParams, workflowRoute } from "@/lib/pages";
import type { CatalogWorkflow } from "@stage-gen/ui/contracts/catalog";

type Params = { id: string };

export const dynamicParams = false;

export function generateStaticParams(): Params[] {
  return workflowParams();
}

function workflowOf(id: string): CatalogWorkflow {
  const workflow = loadCatalog().workflows.find((entry) => entry.id === id);
  if (workflow === undefined) throw new Error(`no workflow ${id}`);
  return workflow;
}

function titleOf(id: string): string {
  return workflowOf(id).manifest.title;
}

export async function generateMetadata({ params }: { params: Promise<Params> }): Promise<Metadata> {
  const { id } = await params;
  return { title: `${titleOf(id)} contract · Stage Gen` };
}

/** The contract's relative links resolve from where it lives in the checkout. */
function contractLinks(workflow: CatalogWorkflow) {
  if (workflow.sourceFolder === null) return null;
  const from = `${workflow.sourceFolder}/contract.md`;
  return { from, resolve: (target: string) => docLink(from, target) };
}

export default async function ContractRoute({ params }: { params: Promise<Params> }) {
  const { id } = await params;
  return (
    <DocShell crumbs={[{ title: titleOf(id), href: href(workflowRoute(id)) }, { title: "Contract", href: null }]}>
      {await renderMarkdown(`workflows/${id}/contract.md`, contractLinks(workflowOf(id)))}
    </DocShell>
  );
}
