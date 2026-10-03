// How the viewer names one run in a URL: its root's key and its tag.
//
// A run sits up to four folders below one of the roots `gnode view` was given, so its
// tag is its root-relative path with each `/` written as `~`, which a safe path segment
// never contains. This module holds only names and URLs, so client components import it;
// resolving a name to a folder belongs to runs.ts on the server.

export interface RunRef {
  /** The root's key: its folder name and a short digest of its real path. */
  readonly root: string;
  /** The run's root-relative path, `/` written as `~`. */
  readonly tag: string;
}

export const TAG_SEPARATOR = "~";

export function tagFor(relative: string): string {
  return relative.split("/").join(TAG_SEPARATOR);
}

/** The run's root-relative path, as a reader recognises it. */
export function relativeOf(tag: string): string {
  return tag.split(TAG_SEPARATOR).join("/");
}

/** The run page, or one of its sub-pages. */
export function runHref(run: RunRef, sub = ""): string {
  const base = `/runs/${encodeURIComponent(run.root)}/${encodeURIComponent(run.tag)}`;
  return sub ? `${base}/${sub}` : base;
}

/**
 * The one URL builder for a run's artifacts served by /api/assets. Every consumer —
 * the run inspector, the asset list and the gallery view — addresses an
 * artifact the same way: the root, the tag and each path segment percent-encoded so a
 * document-supplied path can never smuggle a separator into the route.
 */
export function preparedAssetUrl(run: RunRef, path: string): string {
  return (
    `/api/assets/${encodeURIComponent(run.root)}/${encodeURIComponent(run.tag)}/` +
    path.split("/").map(encodeURIComponent).join("/")
  );
}
