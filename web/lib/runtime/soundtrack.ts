/**
 * Consumer-owned soundtrack playback for the scrolling preview.
 *
 * The generator publishes track identity and portable artifact paths. Selection,
 * browser gesture gating, and playback order are runtime concerns, so this module
 * deliberately has no stage, provider, or generation dependencies. A caller may
 * narrow the catalog to a map-owned pool by track identity; the player does not
 * need to know what a map is.
 */

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

export type SoundtrackSnapshot = Readonly<{
  started: boolean;
  current_track_id: string | null;
  next_track_id: string | null;
}>;

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

function seedFromString(value: string): number {
  let seed = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    seed ^= value.charCodeAt(index);
    seed = Math.imul(seed, 0x01000193);
  }
  return seed >>> 0;
}

/** A small deterministic generator used only to order a finite shuffle bag. */
function nextRandom(state: { value: number }): number {
  state.value = (state.value + 0x6d2b79f5) >>> 0;
  let value = state.value;
  value = Math.imul(value ^ (value >>> 15), value | 1);
  value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
  return ((value ^ (value >>> 14)) >>> 0) / 0x1_0000_0000;
}

/**
 * A deterministic, cyclic shuffle bag. Every multi-track bag is exhausted once
 * before refill, and the first item after refill cannot equal the prior item.
 * A one-track catalog ends after one play because a repeat-free cycle is
 * impossible for that catalog.
 */
export class DeterministicSoundtrackPlayer {
  private readonly tracks: readonly SoundtrackTrack[];
  private activeTracks: readonly SoundtrackTrack[];
  private activePoolKey: string;
  private readonly randomState: { value: number };
  private readonly transport: SoundtrackTransport;
  private readonly onStateChange?: (snapshot: SoundtrackSnapshot) => void;
  private bag: SoundtrackTrack[] = [];
  private currentTrack: SoundtrackTrack | null = null;
  private lastTrackId: string | null = null;
  private hasStarted = false;
  private disposed = false;
  private playToken = 0;

  constructor(options: SoundtrackPlayerOptions) {
    if (options.tracks.length === 0) {
      throw new Error("soundtrack player requires at least one track");
    }
    const ids = new Set(options.tracks.map((track) => track.track_id));
    if (ids.size !== options.tracks.length) {
      throw new Error("soundtrack player track_id values must be unique");
    }
    this.tracks = Object.freeze(
      options.tracks.map((track) => Object.freeze({ ...track })),
    );
    this.activeTracks = this.resolveTrackPool(options.trackIds);
    this.activePoolKey = this.poolKey(this.activeTracks);
    this.randomState = { value: seedFromString(options.seed) };
    this.transport = options.transport;
    this.onStateChange = options.onStateChange;
    this.refillBag();
  }

  get current_track_id(): string | null {
    return this.currentTrack?.track_id ?? null;
  }

  get next_track_id(): string | null {
    return this.bag[0]?.track_id ?? null;
  }

  snapshot(): SoundtrackSnapshot {
    return Object.freeze({
      started: this.hasStarted,
      current_track_id: this.current_track_id,
      next_track_id: this.next_track_id,
    });
  }

  /** Must be called synchronously from a real pointer or keyboard gesture. */
  beginFromPlayerGesture(): boolean {
    if (this.disposed || this.hasStarted || this.bag.length === 0) return false;
    this.hasStarted = true;
    this.playNext();
    return true;
  }

  /**
   * Narrow playback to a game-global track pool selected by the current map.
   *
   * If the current track belongs to the destination pool it keeps playing and
   * only the planned remainder changes. Otherwise playback switches at once.
   * The prior track remains the no-repeat sentinel across that switch.
   */
  setTrackPool(trackIds: readonly string[]): boolean {
    if (this.disposed) return false;
    const nextTracks = this.resolveTrackPool(trackIds);
    const nextPoolKey = this.poolKey(nextTracks);
    if (nextPoolKey === this.activePoolKey) return false;

    this.activeTracks = nextTracks;
    this.activePoolKey = nextPoolKey;
    this.bag = [];
    const currentAllowed =
      this.currentTrack !== null &&
      nextTracks.some((track) => track.track_id === this.currentTrack?.track_id);
    if (currentAllowed || !this.hasStarted) {
      // A retained current track counts as the first consumed item in the
      // destination's new bag. Do not schedule it a second time before every
      // other destination track has had its turn.
      this.refillBag(currentAllowed ? this.currentTrack?.track_id : undefined);
      this.emitState();
      return true;
    }

    // Invalidate the prior transport callback before replacing its media.
    this.currentTrack = null;
    this.playToken += 1;
    this.refillBag();
    this.playNext();
    return true;
  }

  stop(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.hasStarted = false;
    this.currentTrack = null;
    this.bag = [];
    this.playToken += 1;
    this.transport.stop();
    this.emitState();
  }

  private playNext(): void {
    if (this.disposed) return;
    const track = this.bag.shift();
    if (!track) {
      this.currentTrack = null;
      this.emitState();
      return;
    }

    this.currentTrack = track;
    this.lastTrackId = track.track_id;
    this.refillBag();
    const token = ++this.playToken;
    this.emitState();
    this.transport.play(track, () => {
      if (this.disposed || token !== this.playToken) return;
      this.currentTrack = null;
      this.playNext();
    });
  }

  private refillBag(excludedTrackId?: string): void {
    if (this.bag.length > 0) return;
    if (
      excludedTrackId === undefined &&
      this.activeTracks.length === 1 &&
      this.lastTrackId !== null
    )
      return;

    const next = this.activeTracks.filter(
      (track) => track.track_id !== excludedTrackId,
    );
    for (let index = next.length - 1; index > 0; index -= 1) {
      const swapIndex = Math.floor(nextRandom(this.randomState) * (index + 1));
      [next[index], next[swapIndex]] = [next[swapIndex], next[index]];
    }
    if (this.lastTrackId !== null && next[0]?.track_id === this.lastTrackId) {
      const replacement = next.findIndex(
        (track) => track.track_id !== this.lastTrackId,
      );
      if (replacement > 0) {
        [next[0], next[replacement]] = [next[replacement], next[0]];
      }
    }
    this.bag = next;
  }

  private resolveTrackPool(trackIds?: readonly string[]): readonly SoundtrackTrack[] {
    if (trackIds === undefined) return this.tracks;
    if (trackIds.length === 0) {
      throw new Error("soundtrack track pool requires at least one track_id");
    }
    const requested = new Set(trackIds);
    if (requested.size !== trackIds.length) {
      throw new Error("soundtrack track pool track_id values must be unique");
    }
    const selected = this.tracks.filter((track) => requested.has(track.track_id));
    if (selected.length !== requested.size) {
      throw new Error("soundtrack track pool names an unknown track_id");
    }
    return Object.freeze(selected);
  }

  private poolKey(tracks: readonly SoundtrackTrack[]): string {
    return tracks.map((track) => track.track_id).join("\0");
  }

  private emitState(): void {
    this.onStateChange?.(this.snapshot());
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
