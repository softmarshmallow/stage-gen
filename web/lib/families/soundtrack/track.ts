// What a soundtrack is made of, and how a place narrows it.
//
// One track is an identity and a source a transport can play. Both genres
// already had exactly this and spelled it differently — `{track_id, path}` in
// the platformer's projection, `{trackId, audio}` in the runner's contract —
// so the family names it once and each genre's parser maps onto it.
//
// A *pool* is the place binding: the subset of the catalog a map, a band or a
// scene admits, named by track id. It is the platformer's half of the family
// and the runner authors none, which is not a branch — a genre that binds no
// place simply never calls `bindPool`, the way a genre with no holder never
// holds the clock.

export type SoundtrackTrack = Readonly<{
  /** Stable identity, unique in the catalog. */
  trackId: string;
  /** Whatever the transport needs to play it: a url, a path, a key. */
  source: string;
}>;

/** A catalog with unique ids, checked once so no consumer has to. */
export function soundtrackCatalog(tracks: readonly SoundtrackTrack[]): readonly SoundtrackTrack[] {
  if (tracks.length === 0) throw new Error("soundtrack player requires at least one track");
  const ids = new Set(tracks.map((track) => track.trackId));
  if (ids.size !== tracks.length) {
    throw new Error("soundtrack player track_id values must be unique");
  }
  return Object.freeze(tracks.map((track) => Object.freeze({ ...track })));
}

/**
 * The tracks a named pool admits, in catalog order.
 *
 * Catalog order and not the order the names were given: the pool is a *set* of
 * admitted tracks and the selection decides what plays, so a map that lists its
 * two tracks the other way round must not hear a different run.
 */
export function resolvePool(
  catalog: readonly SoundtrackTrack[],
  trackIds: readonly string[] | undefined,
): readonly SoundtrackTrack[] {
  if (trackIds === undefined) return catalog;
  if (trackIds.length === 0) {
    throw new Error("soundtrack track pool requires at least one track_id");
  }
  const requested = new Set(trackIds);
  if (requested.size !== trackIds.length) {
    throw new Error("soundtrack track pool track_id values must be unique");
  }
  const selected = catalog.filter((track) => requested.has(track.trackId));
  if (selected.length !== requested.size) {
    throw new Error("soundtrack track pool names an unknown track_id");
  }
  return Object.freeze(selected);
}

/** Identity of a pool, so a rebind to the same place is a no-op rather than a reshuffle. */
export function poolKey(tracks: readonly SoundtrackTrack[]): string {
  return tracks.map((track) => track.trackId).join("\0");
}
