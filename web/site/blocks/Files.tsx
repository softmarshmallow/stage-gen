// <Files>: A file-browser list of the run folder: the named paths, their parents, and a count of the rest.
// Port of the retired showcase's `files` component.

import type { ReactElement, ReactNode } from "react";
import type { BlockProps } from "./shared";
import { childrenOf, css, MdxError, size, textOf } from "./shared";

export type FilesProps = Record<string, never>;

function Folder(): ReactElement {
  return (
    <svg className="size-4 shrink-0 text-zinc-400" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.2">
      <path d="M1.5 3.5h4.2l1.4 1.5h7.4v8.5h-13z" strokeLinejoin="round" />
    </svg>
  );
}

function FileIcon(): ReactElement {
  return (
    <svg className="size-4 shrink-0 text-zinc-400" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.2">
      <path d="M3.5 1.5h6l3 3v10h-9z M9.5 1.5v3h3" strokeLinejoin="round" />
    </svg>
  );
}

function ChevronOpen(): ReactElement {
  return (
    <svg className="size-3 text-zinc-400" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.3">
      <path d="M3 4.5l3 3 3-3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ChevronShut(): ReactElement {
  return (
    <svg className="size-3 text-zinc-400" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.3">
      <path d="M4.5 3l3 3-3 3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const KINDS: Readonly<Record<string, string>> = {
  ".glb": "3D model",
  ".json": "JSON record",
  ".png": "PNG image",
  ".webp": "WebP image",
  ".mkv": "Video",
  ".mp4": "Video",
  ".zip": "Archive",
  ".blend": "Blender file",
};

/** pathlib's PurePath(name).suffix: the last dot's extension, none for a dotfile or a trailing dot. */
function suffix(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot > 0 && dot < name.length - 1 ? name.slice(dot) : "";
}

const parentOf = (path: string): string => (path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "");
const nameOf = (path: string): string => path.slice(path.lastIndexOf("/") + 1);

export default function Files({ page, children }: BlockProps<FilesProps>): ReactElement {
  const tree = page.record.tree;
  const listed = childrenOf(children, "File");
  const notes = new Map<string, ReactNode>();
  const order: string[] = [];
  for (const f of listed) {
    const asked = String(f.props.path);
    const path = asked.replace(/\/+$/, "");
    if (tree[path] === undefined) throw new MdxError(`<File path='${asked}'> is not in this run`);
    notes.set(path, textOf(f.props.children));
    const parts = path.split("/");
    for (let depth = 1; depth <= parts.length; depth += 1) {
      const ancestor = parts.slice(0, depth).join("/");
      if (!order.includes(ancestor)) order.push(ancestor);
    }
  }

  const childrenInOrder = (parent: string): string[] => order.filter((p) => parentOf(p) === parent);

  const rows: ReactElement[] = [];

  const walk = (parent: string, depth: number): void => {
    for (const path of childrenInOrder(parent)) {
      const entry = tree[path];
      const name = nameOf(path);
      const folder = entry.kind === "dir";
      const isOpen = folder && childrenInOrder(path).length > 0;
      const chevron = folder ? isOpen ? <ChevronOpen /> : <ChevronShut /> : null;
      const kind =
        notes.get(path) ||
        (folder ? `Folder, ${entry.files} files` : (KINDS[suffix(name)] ?? "File"));
      rows.push(
        <tr key={path} className="even:bg-zinc-50 dark:even:bg-zinc-900/60">
          <td className="py-1.5 pr-4">
            <span className="flex items-center gap-1.5" style={css(`padding-left:${depth * 18}px`)}>
              <span className="flex w-3 justify-center">{chevron}</span>
              {folder ? <Folder /> : <FileIcon />}
              <span className={notes.has(path) ? "font-medium" : ""}>{name}</span>
            </span>
          </td>
          <td className="whitespace-nowrap py-1.5 pr-4 text-right tabular-nums text-zinc-500">{size(entry.bytes)}</td>
          <td className="py-1.5 text-zinc-500">{kind}</td>
        </tr>,
      );
      walk(path, depth + 1);
    }
  };

  walk("", 0);
  const top = Object.keys(tree).filter((p) => p && !p.includes("/"));
  const rest = top.filter((p) => !order.includes(p));
  if (rest.length > 0) {
    const folders = rest.filter((p) => tree[p].kind === "dir").length;
    const counts = (
      [
        [folders, "folder"],
        [rest.length - folders, "file"],
      ] as const
    )
      .filter(([n]) => n)
      .map(([n, word]) => `${n} more ${word}${n === 1 ? "" : "s"}`);
    rows.push(
      <tr key="">
        <td className="py-1.5 pr-4 pl-[18px] text-zinc-400" colSpan={3}>
          {`and ${counts.join(" and ")} the pipeline keeps for recovery and auditing`}
        </td>
      </tr>,
    );
  }
  const root = nameOf(page.record.deliveredRun.replace(/\/+$/, ""));
  return (
    <div className="mt-4 overflow-hidden rounded-md border border-zinc-200 dark:border-zinc-800">
      <div className="flex items-center gap-2 border-b border-zinc-200 bg-zinc-50 px-3 py-2 text-sm text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
        <Folder />
        <span>{root}</span>
        <span className="ml-auto tabular-nums text-zinc-400">
          {`${tree[""].files} files, ${size(tree[""].bytes)}`}
        </span>
      </div>
      <div className="overflow-x-auto px-3 pb-2">
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th className="py-2 pr-4 text-left text-xs font-normal text-zinc-400">Name</th>
              <th className="py-2 pr-4 text-right text-xs font-normal text-zinc-400">Size</th>
              <th className="py-2 text-left text-xs font-normal text-zinc-400">Kind</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </div>
  );
}
