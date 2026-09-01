// The one URL builder for a run's artifacts served by /api/assets.
//
// Every consumer — the platformer scene, the room scene, the scene bundle
// projection, the package explorer, the run inspector — addresses a run
// artifact the same way: the tag and each path segment percent-encoded so a
// manifest-supplied path can never smuggle a separator into the route. Genre
// code owns which artifacts it loads; this module owns only how one is named.

export function preparedAssetUrl(tag: string, path: string): string {
  return `/api/assets/${encodeURIComponent(tag)}/${path.split("/").map(encodeURIComponent).join("/")}`;
}
