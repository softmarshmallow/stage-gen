// /docs/: every doc page: the staged guides first, then the CLI reference, then the
// reference of every workflow.

import DocShell from "@/components/DocShell";
import { href } from "@/lib/media";
import { docPages, docRoute } from "@/lib/pages";

export const metadata = { title: "Stage Gen docs" };

export default function DocsIndex() {
  const docs = docPages();
  const guides = docs.filter((doc) => doc.kind === "markdown");
  const references = docs.filter((doc) => doc.kind === "cli");
  const workflows = docs.filter((doc) => doc.kind === "workflow");
  const list = (entries: typeof docs) => (
    <ul className="mt-4 max-w-3xl list-disc space-y-1.5 pl-5 text-zinc-700 dark:text-zinc-300">
      {entries.map((doc) => (
        <li key={doc.slug.join("/")}>
          <a className="underline underline-offset-2" href={href(docRoute(doc.slug))}>
            {doc.title}
          </a>
        </li>
      ))}
    </ul>
  );
  return (
    <DocShell crumbs={[{ title: "Docs", href: null }]}>
      <h1 className="text-3xl font-semibold tracking-tight">Docs</h1>
      <h2 className="mt-16 border-b border-zinc-200 pb-2 font-medium dark:border-zinc-800">Guides</h2>
      {list(guides)}
      {references.length > 0 ? (
        <>
          <h2 className="mt-16 border-b border-zinc-200 pb-2 font-medium dark:border-zinc-800">Command line</h2>
          {list(references)}
        </>
      ) : null}
      <h2 id="workflows" className="mt-16 border-b border-zinc-200 pb-2 font-medium dark:border-zinc-800">
        Workflow reference
      </h2>
      {list(workflows)}
    </DocShell>
  );
}
