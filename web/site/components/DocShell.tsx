// The shell of the docs and contract pages: the landing's plain header with a breadcrumb,
// and one reading column. The showcase had no docs; this keeps its type and colours.

import type { ReactElement, ReactNode } from "react";
import { href } from "@/lib/media";

export interface Crumb {
  readonly title: string;
  readonly href: string | null;
}

export default function DocShell({ crumbs, children }: { crumbs: readonly Crumb[]; children: ReactNode }): ReactElement {
  return (
    <>
      <header className="border-b border-zinc-200 dark:border-zinc-800">
        <div className="mx-auto flex h-14 max-w-6xl items-center px-6">
          <nav className="flex items-center gap-2 text-sm text-zinc-500">
            <a className="hover:text-zinc-900 dark:hover:text-zinc-100" href={href("/")}>
              Stage Gen
            </a>
            {crumbs.map((crumb) => (
              <span key={crumb.title} className="flex items-center gap-2">
                <span>/</span>
                {crumb.href === null ? (
                  <span className="text-zinc-900 dark:text-zinc-100">{crumb.title}</span>
                ) : (
                  <a className="hover:text-zinc-900 dark:hover:text-zinc-100" href={crumb.href}>
                    {crumb.title}
                  </a>
                )}
              </span>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 pb-20 pt-12">{children}</main>
    </>
  );
}
