/**
 * Consumer-owned soundtrack playback for the scrolling preview.
 *
 * The generator publishes track identity and portable artifact paths. Selection,
 * browser gesture gating, and playback order are runtime concerns, so this module
 * deliberately has no stage, provider, or generation dependencies. A caller may
 * narrow the catalog to a map-owned pool by track identity; the player does not
 * need to know what a map is.
 */

import {
  ShuffleBag,
  soundtrackCatalog,
  SoundtrackPlayer as FamilySoundtrackPlayer,
  type SoundtrackSnapshot as FamilySoundtrackSnapshot,
} from "@/lib/families/soundtrack";
import {
  parseSoundtrackBlock,
  type SoundtrackBlockView,
} from "@/lib/families/soundtrack/manifest";
import { PREPARED_RUNTIME_BLOCKS } from "@/lib/manifest/prepared-manifest";
import type { BlockTable } from "@/lib/manifest/blocks";

/**
 * The block this genre's soundtrack is authored in.
 *
 * The catalog is `soundtrack`; the pools that narrow it are `[[map_uses]]
 * track_ids` inside the map book, and the family gates the catalog because a
 * package with no catalog has no soundtrack to bind a place to. A producer that
 * moves it gets `manifest block "soundtrack" is published as …; this build
 * reads platformer-soundtrack-block-v1`, from the soundtrack.
 */
export const PLATFORMER_SOUNDTRACK_BLOCK = Object.freeze({
  block: "soundtrack",
  version: PREPARED_RUNTIME_BLOCKS.soundtrack,
});

/** Gate the platformer's soundtrack block. Refuses by naming `soundtrack`. */
export function parsePlatformerSoundtrackBlock(blocks: BlockTable): SoundtrackBlockView {
  return parseSoundtrackBlock(blocks, PLATFORMER_SOUNDTRACK_BLOCK);
}

export type SoundtrackTrack = Readonly<{
  track_id: string;
  path: string;
}>;

export type SoundtrackSpec = Readonly<{
  playback: Readonly<{
    selection: "shuffle";
    no_immediate_repeat: true;
  }>;
  tracks: readonly SoundtrackTrack[];
  /** The current public projection is narrowed by the active authored map. */
  map_scoped: true;
}>;

/** The family's own snapshot, in this genre's names — which are the same names. */
export type SoundtrackSnapshot = FamilySoundtrackSnapshot;

export type SoundtrackTransport = Readonly<{
  play: (track: SoundtrackTrack, onEnded: () => void) => void;
  stop: () => void;
}>;

type SoundtrackPlayerOptions = Readonly<{
  tracks: readonly SoundtrackTrack[];
  trackIds?: readonly string[];
  seed: string;
  transport: SoundtrackTransport;
  onStateChange?: (snapshot: SoundtrackSnapshot) => void;
}>;

const TRACK_ID = /^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$/;
const GAME_ID = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;
const SHA256 = /^[a-f0-9]{64}$/;
const SOUNDTRACK_KEYS = [
  "schema_version",
  "kind",
  "game_id",
  "revision",
  "source",
  "playback",
  "tracks",
] as const;
const SOURCE_KEYS = [
  "path",
  "provenance_path",
  "source_sha256",
  "canonical_sha256",
] as const;
const PLAYBACK_KEYS = ["selection", "no_immediate_repeat"] as const;
const TRACK_KEYS = [
  "track_id",
  "display_name",
  "path",
  "provenance_path",
  "sha256",
  "bytes",
  "media_type",
  "rights_status",
  "generation_capability",
  "seamless_loop",
  "target_duration_seconds",
  "duration_seconds",
] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isPortableArtifactPath(value: unknown): value is string {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value.trim() !== value
  )
    return false;
  if (
    value.startsWith("/") ||
    value.includes("\\") ||
    value.includes(":") ||
    value.includes("?") ||
    value.includes("#") ||
    value.includes("%") ||
    /[\u0000-\u001f\u007f]/u.test(value)
  ) {
    return false;
  }
  return value
    .split("/")
    .every(
      (segment) => segment.length > 0 && segment !== "." && segment !== "..",
    );
}

function hasExactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
): boolean {
  const actual = Object.keys(value);
  return (
    actual.length === expected.length &&
    actual.every((key) => expected.includes(key))
  );
}

function declaredSoundtrackError(message: string): never {
  throw new Error(`invalid declared soundtrack: ${message}`);
}

/** True when a manifest claims map-scoped playback, even if that claim is malformed. */
export function declaresMapScopedSoundtrack(manifest: unknown): boolean {
  return isRecord(manifest) && Object.hasOwn(manifest, "soundtrack");
}

/** Read the one current map-aware soundtrack projection. */
export function parseSoundtrackManifest(
  manifest: unknown,
): SoundtrackSpec | null {
  if (!isRecord(manifest)) {
    throw new Error("scrolling-preview manifest must be a JSON object");
  }
  const declared = Object.hasOwn(manifest, "soundtrack");
  if (manifest["schema_version"] !== 7) {
    if (declared) {
      return declaredSoundtrackError("parent manifest schema_version must be 7");
    }
    throw new Error("scrolling-preview manifest schema_version must be 7");
  }
  if (!declared) return null;
  const soundtrack = manifest["soundtrack"];
  if (!isRecord(soundtrack) || !hasExactKeys(soundtrack, SOUNDTRACK_KEYS)) {
    return declaredSoundtrackError("block keys are invalid");
  }
  if (
    soundtrack["schema_version"] !== 2 ||
    soundtrack["kind"] !== "game-soundtrack-manifest-v2" ||
    typeof soundtrack["game_id"] !== "string" ||
    soundtrack["game_id"].length > 96 ||
    !GAME_ID.test(soundtrack["game_id"]) ||
    !Number.isSafeInteger(soundtrack["revision"]) ||
    (soundtrack["revision"] as number) < 1
  ) {
    return declaredSoundtrackError("identity is invalid");
  }

  const source = soundtrack["source"];
  if (
    !isRecord(source) ||
    !hasExactKeys(source, SOURCE_KEYS) ||
    !isPortableArtifactPath(source["path"]) ||
    !isPortableArtifactPath(source["provenance_path"]) ||
    source["provenance_path"] !== `${source["path"]}.meta.json` ||
    typeof source["source_sha256"] !== "string" ||
    !SHA256.test(source["source_sha256"]) ||
    typeof source["canonical_sha256"] !== "string" ||
    !SHA256.test(source["canonical_sha256"])
  ) {
    return declaredSoundtrackError("source binding is invalid");
  }

  const mapBook = manifest["map_book"];
  if (
    !isRecord(mapBook) ||
    mapBook["schema_version"] !== 2 ||
    mapBook["kind"] !== "game-map-book-manifest-v2" ||
    mapBook["game_id"] !== soundtrack["game_id"]
  ) {
    return declaredSoundtrackError(
      "requires the matching game-map-book-manifest-v2 projection",
    );
  }

  const playback = soundtrack["playback"];
  if (
    !isRecord(playback) ||
    !hasExactKeys(playback, PLAYBACK_KEYS) ||
    playback["selection"] !== "shuffle" ||
    playback["no_immediate_repeat"] !== true
  ) {
    return declaredSoundtrackError("playback policy is invalid");
  }

  const rawTracks = soundtrack["tracks"];
  if (
    !Array.isArray(rawTracks) ||
    rawTracks.length < 2 ||
    rawTracks.length > 64
  )
    return declaredSoundtrackError("tracks must contain between 2 and 64 entries");

  const tracks: SoundtrackTrack[] = [];
  const trackIds = new Set<string>();
  const paths = new Set<string>();
  for (const rawTrack of rawTracks) {
    if (!isRecord(rawTrack) || !hasExactKeys(rawTrack, TRACK_KEYS)) {
      return declaredSoundtrackError("track keys are invalid");
    }
    const trackId = rawTrack["track_id"];
    const path = rawTrack["path"];
    const displayName = rawTrack["display_name"];
    const provenancePath = rawTrack["provenance_path"];
    const bytes = rawTrack["bytes"];
    const targetDuration = rawTrack["target_duration_seconds"];
    const duration = rawTrack["duration_seconds"];
    if (
      typeof trackId !== "string" ||
      trackId.length > 64 ||
      !TRACK_ID.test(trackId) ||
      typeof displayName !== "string" ||
      displayName.length === 0 ||
      displayName.trim() !== displayName ||
      !isPortableArtifactPath(path) ||
      !path.endsWith(".mp3") ||
      !isPortableArtifactPath(provenancePath) ||
      provenancePath !== `${path}.meta.json` ||
      typeof rawTrack["sha256"] !== "string" ||
      !SHA256.test(rawTrack["sha256"]) ||
      !Number.isSafeInteger(bytes) ||
      (bytes as number) < 1 ||
      rawTrack["media_type"] !== "audio/mpeg" ||
      rawTrack["generation_capability"] !== "generate-music" ||
      (rawTrack["rights_status"] !== "unreviewed" &&
        rawTrack["rights_status"] !== "redistribution-approved") ||
      typeof rawTrack["seamless_loop"] !== "boolean" ||
      !Number.isSafeInteger(targetDuration) ||
      (targetDuration as number) < 15 ||
      (targetDuration as number) > 600 ||
      typeof duration !== "number" ||
      !Number.isFinite(duration) ||
      duration <= 0 ||
      trackIds.has(trackId) ||
      paths.has(path)
    ) {
      return declaredSoundtrackError("track entry is invalid");
    }
    trackIds.add(trackId);
    paths.add(path);
    tracks.push(Object.freeze({ track_id: trackId, path }));
  }

  return Object.freeze({
    playback: Object.freeze({
      selection: "shuffle",
      no_immediate_repeat: true,
    }),
    tracks: Object.freeze(tracks),
    map_scoped: true,
  });
}

/** Compose catalog parsing with the map-pool coupling required by scene boot. */
export function parseSoundtrackForMapPool(
  manifest: unknown,
  trackIds?: readonly string[],
): SoundtrackSpec | null {
  const soundtrack = parseSoundtrackManifest(manifest);
  if (trackIds !== undefined && soundtrack === null) {
    throw new Error("authored map book requires a valid map-aware soundtrack");
  }
  if (soundtrack !== null && trackIds === undefined) {
    throw new Error("map-aware soundtrack requires an authored opening map pool");
  }
  return soundtrack;
}

/**
 * The platformer's binding of the `soundtrack` family: a seeded bag and a place.
 *
 * This genre authors the other half of the family from the runner's. There are
 * no transitions here — no run edge fades the music, because until `session`
 * reaches this genre there is no run edge to fade it at — and what it does
 * author is the place binding: every map names a pool of track ids, and
 * entering one narrows what may play without interrupting a track the
 * destination also admits.
 *
 * Everything the class used to implement itself is the family's now: the bag,
 * the no-immediate-repeat rule, the pool narrowing with its retained-track
 * sentinel, the gesture gate and the snapshot. What is left is this genre's
 * vocabulary — `{track_id, path}` against the family's `{trackId, source}` —
 * and the transport it hands over, which is why the adapter below is the whole
 * of the difference.
 */
export class DeterministicSoundtrackPlayer {
  private readonly player: FamilySoundtrackPlayer;

  constructor(options: SoundtrackPlayerOptions) {
    const byId = new Map(options.tracks.map((track) => [track.track_id, track]));
    const catalog = soundtrackCatalog(
      options.tracks.map((track) => ({ trackId: track.track_id, source: track.path })),
    );
    this.player = new FamilySoundtrackPlayer({
      selector: new ShuffleBag(catalog, options.seed, options.trackIds),
      transport: {
        play: (track, onEnded) => {
          const authored = byId.get(track.trackId);
          if (authored) options.transport.play(authored, onEnded);
        },
        stop: () => options.transport.stop(),
      },
      // A browser will not start audible playback a player never asked for, so
      // the first track waits for a real gesture. The runner's half of the
      // family starts eagerly and retries instead.
      start: "gesture",
      onStateChange: options.onStateChange,
    });
  }

  get current_track_id(): string | null {
    return this.player.current_track_id;
  }

  get next_track_id(): string | null {
    return this.player.next_track_id;
  }

  snapshot(): SoundtrackSnapshot {
    return this.player.snapshot();
  }

  /** Must be called synchronously from a real pointer or keyboard gesture. */
  beginFromPlayerGesture(): boolean {
    return this.player.beginFromPlayerGesture();
  }

  /**
   * Narrow playback to a game-global track pool selected by the current map.
   *
   * If the current track belongs to the destination pool it keeps playing and
   * only the planned remainder changes. Otherwise playback switches at once.
   * The prior track remains the no-repeat sentinel across that switch.
   */
  setTrackPool(trackIds: readonly string[]): boolean {
    return this.player.bindPool(trackIds);
  }

  stop(): void {
    this.player.stop();
  }
}

/**
 * One reusable browser media element keeps subsequent `ended` transitions in
 * the same playback session that the player gesture unlocked.
 */
export function createBrowserSoundtrackTransport(
  resolveUrl: (track: SoundtrackTrack) => string,
): SoundtrackTransport {
  const audio = new Audio();
  audio.preload = "none";
  let endedListener: (() => void) | null = null;

  return Object.freeze({
    play(track: SoundtrackTrack, onEnded: () => void): void {
      if (endedListener) audio.removeEventListener("ended", endedListener);
      audio.pause();
      audio.currentTime = 0;
      audio.src = resolveUrl(track);
      endedListener = onEnded;
      audio.addEventListener("ended", endedListener, { once: true });
      // Invocation is synchronous with the initial player gesture. A rejected
      // media promise is intentionally contained: optional audio must not turn
      // a playable scene into an unhandled rejection.
      void audio.play().catch(() => undefined);
    },
    stop(): void {
      if (endedListener) audio.removeEventListener("ended", endedListener);
      endedListener = null;
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
    },
  });
}
