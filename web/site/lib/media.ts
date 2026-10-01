// Served URLs. Everything under public/ is served from the site root, below the optional
// base path a copy is built for (SITE_BASE_PATH, the same value next.config.mjs reads).

export function basePath(): string {
  return process.env.SITE_BASE_PATH ?? "";
}

/** Where scripts/site.py copies an example's files: /examples/<owner>/<id>. */
export function exampleMediaBase(owner: string, id: string): string {
  return `${basePath()}/examples/${owner}/${id}`;
}

/** One example file: /examples/<owner>/<id>/media/<file>. */
export function mediaUrl(owner: string, id: string, file: string): string {
  return `${exampleMediaBase(owner, id)}/media/${file}`;
}

/** A page link, with the base path and the trailing slash the static export writes. */
export function href(route: string): string {
  const trimmed = route.replace(/^\/+|\/+$/g, "");
  return `${basePath()}/${trimmed}${trimmed ? "/" : ""}`;
}
