// /docs/<slug>/: the staged markdown docs (scripts/site.py SITE_DOCS), the generated CLI
// reference, and the generated reference page of every workflow.

import type { Metadata } from "next";
import CliReference from "@/components/CliReference";
import DocShell from "@/components/DocShell";
import WorkflowReference from "@/components/WorkflowReference";
import { loadCatalog } from "@/lib/catalog";
import { loadCliReference } from "@/lib/cli";
import { href } from "@/lib/media";
import { renderMarkdown } from "@/lib/mdx";
import { docLink, docPages, findDoc, type DocPage } from "@/lib/pages";

type Params = { slug: string[] };

export const dynamicParams = false;

export function generateStaticParams(): Params[] {
  return docPages().map((doc) => ({ slug: [...doc.slug] }));
}

export async function generateMetadata({ params }: { params: Promise<Params> }): Promise<Metadata> {
  const { slug } = await params;
  return { title: `${findDoc(slug).title} · Stage Gen docs` };
}

async function body(doc: DocPage) {
  if (doc.kind === "cli") return <CliReference root={loadCliReference()} />;
  if (doc.kind === "workflow") {
    const workflow = loadCatalog().workflows.find((entry) => entry.id === doc.workflow);
    if (workflow === undefined) throw new Error(`no workflow ${String(doc.workflow)}`);
    return <WorkflowReference workflow={workflow} />;
  }
  const from = doc.path as string;
  return renderMarkdown(doc.source as string, { from, resolve: (target) => docLink(from, target) });
}

export default async function DocRoute({ params }: { params: Promise<Params> }) {
  const { slug } = await params;
  const doc = findDoc(slug);
  return (
    <DocShell crumbs={[{ title: "Docs", href: href("/docs") }, { title: doc.title, href: null }]}>
      {await body(doc)}
    </DocShell>
  );
}
