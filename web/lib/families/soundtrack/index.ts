export {
  SoundtrackPlayer,
  type FadingTransport,
  type MusicAction,
  type MusicDuck,
  type SoundtrackPlayerOptions,
  type SoundtrackSnapshot,
  type SoundtrackTransport,
} from "./player";
export { ShuffleBag, ShuffleQueue, seedFromString, type TrackSelector } from "./selection";
export { FadeRunner, fadeGain, type FadeCurve, type FadeStep } from "./fade";
export { poolKey, resolvePool, soundtrackCatalog, type SoundtrackTrack } from "./track";
export {
  parseSoundtrackBlock,
  type SoundtrackBlockBinding,
  type SoundtrackBlockView,
} from "./manifest";
