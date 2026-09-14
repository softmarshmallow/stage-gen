# Movie Sprite Actor API

`movie_sprite_actor.gd` is a drawable `Node2D`. It depends only on the declared
`content_io` addon and its private `compositor.gdshader`. The supported Godot
renderer is Compatibility; current verification uses Godot 4.7.2.

## Prepared representation

The version-1 JSON descriptor retains the existing `movie_sprite` field names:

```json
{
  "schema_version": 1,
  "character_id": "example_actor",
  "patch_application": "replace_selected_rgb_preserve_original_alpha",
  "frame_size": [128, 256],
  "frame_count": 11,
  "fps": 12.5,
  "columns": 3,
  "rows": 2,
  "pages": [
    {"file": "body/0.png", "sha256": "<64 lowercase hexadecimal digits>"},
    {"file": "body/1.png", "sha256": "<64 lowercase hexadecimal digits>"}
  ],
  "eyes": {
    "eyes_closed": {"file": "face/closed.png", "sha256": "<64 lowercase hexadecimal digits>"}
  },
  "mouths": {
    "mouth_a": {"file": "face/a.png", "sha256": "<64 lowercase hexadecimal digits>"},
    "mouth_o": {"file": "face/o.png", "sha256": "<64 lowercase hexadecimal digits>"}
  }
}
```

The example digests are illustrative placeholders. Extra preparation/provenance
fields may accompany the descriptor; the runtime does not interpret or discard
their persisted source. `character_id` is a nonempty opaque string, not a story
binding. `schema_version` must be the integer value 1. Future representation
profiles require explicit admission; this profile does not silently accept them.

Frames occupy row-major cells, with no gutters. Each PNG page is exactly
`frame_size * [columns, rows]`, including a padded final page. Page count is
exactly `ceil(frame_count / (columns * rows))`; unused final cells are never
played. A single frame/page is valid. All frames share an untrimmed canvas whose
origin is top left, +X right and +Y down. The drawable's local origin is that
canvas's top left. Host `Node2D` transforms/modulation apply to the entire
composition. Frame count and FPS establish the timebase; loop duration is
`frame_count / fps` and playback wraps indefinitely.

`eyes` and `mouths` are required dictionaries and may be empty. Each declares up
to 32 feature states. Keys are ASCII `lower_snake_case`, at most 64 characters,
beginning with a letter and containing nonempty underscore-separated segments. The reserved `rest` key cannot bind a texture.
Names carry authored visual meaning; an `eyes_closed` input may be a bilateral
blink or one wink. The runtime does not infer anatomical sides or speech sounds.

Every replacement PNG has exactly `frame_size` dimensions. Binary alpha selects
already composed RGB, including any prepared feathering. The shader replaces
RGB where mask alpha is at least 0.5, preserves the current body alpha, then
filters the composed pixels once. `rest` disables replacement for that channel.
Eye and mouth channels are independent of each other and body time.

### Producer and preparation invariants

Preparation owns fixed registration, binary feature masks, disjoint eye/mouth
support, loop quality, original source lineage and rights. The neutral face is
baked into the body; selected support must remain compatible on every frame.
Canonical equality on selected RGB is one sufficient registration check. A
different head trajectory must not be represented by unregistered fixed patches.

Runtime admission verifies structure, bounds, exact decoded dimensions and
bound source SHA-256. It does not scan every body frame on entry or claim a
semantic registration/loop-quality verdict. Mask binary alpha and non-overlap
are preparation preconditions, not pixel scans performed by this player. The
shader processes eyes then mouth, but that ordering is not permission to author
overlapping support. A fractional-alpha input is outside this profile even
though thresholding would draw it. More profiles can be added when their input
semantics and consumers are defined.

### Admission and resource limits

| Field/resource | Limit |
| --- | --- |
| Frame dimensions | Each a positive integer, at most 4096 |
| Grid columns/rows | Each a positive integer, at most 4096 |
| Full atlas page | At most 4096 per edge and 8,388,608 pixels |
| Frame count | Positive integer, at most 1,000,000 |
| FPS | Finite number greater than zero and at most 240; duration must also be finite |
| Pages | Exact calculated count, at most 4096 |
| Feature states | At most 32 in each channel |
| Combined decoded face RGBA8 | At most 64 MiB across all declared states |
| Encoded PNG source | At most 64 MiB per file |
| Manifest source | At most 4 MiB |
| Body texture cache | At most two pages, plus one in-flight CPU decode |
| Accepted absolute playback clock | Zero through 1e12 seconds |

Boolean, fractional, nonfinite, zero and negative values are refused where an
integer is required. JSON integral numbers such as `16.0` are accepted as 16.
Multiplications occur only after bounded scalar admission. PNG size/header
checks precede image decode. Encoded-source length is checked before reading;
SHA-256 verifies the exact returned buffer. Decode is reconfirmed against the
expected dimensions before upload.

The limits bound major resource allocations per actor, not a whole-process or
GPU-driver memory ceiling. Two body textures, all face textures, one CPU page
decode and transient encoded buffers can coexist. Faces load synchronously;
body pages decode one at a time on a worker thread and upload on the main thread.
The cache is intentionally small; backing storage must be fast enough to avoid
visible holds. This package does not guarantee zero buffering.

## Public methods and events

| API | Contract |
| --- | --- |
| `configure(loader, manifest_path) -> Array[String]` | Shuts down the prior configuration, snapshots the `content_io` root/backend into a private loader, validates descriptor/face inputs, begins page 0 asynchronously. Empty errors mean admission succeeded, not yet visibly ready. |
| `advance(delta)` | Host-owned progression and worker polling; call while loading or paused too. Loading/buffering holds elapsed time; accepted positive delta advances a ready unpaused actor. Invalid, negative, nonfinite or clock-overflowing steps are ignored. |
| `seek(seconds) -> Array[String]` | Selects an absolute body clock, retaining face states and pause policy. May buffer for the target page. Finite nonnegative values through 1e12 accepted; larger/invalid values return errors without changing playback. |
| `set_paused(bool)` | Freezes body clock and cancels an unaccepted buffered time step. Explicit seek/face changes remain allowed. Resume has no wall-time catch-up. |
| `set_eye_state(name) -> Array[String]` | Selects declared eye replacement or reserved `rest`; unknown names return errors and preserve the prior state. |
| `set_mouth_state(name) -> Array[String]` | Same, for the independent mouth channel. |
| `snapshot() -> Dictionary` | Diagnostic state described below; contains no serializable save guarantee. |
| `get_state() -> Dictionary` | Alias of `snapshot`, retained for existing consumers. |
| `shutdown()` | Idempotently joins a pending worker, frees the internal drawable/material/textures and closes playback. This can wait for a decode to finish. |
| `playback_ready` signal | Emitted once per successful configuration after the first selected body frame is available to draw. It is not GPU presentation/capture proof. |
| `failed(errors: Array[String])` signal | Admission/decode failure closes owned resources, records errors and enters `failed`. No placeholder, generation or cross-root fallback runs. |

Ready/failure callbacks may shut down or reconfigure the actor. The originating
operation stops work on its old session; an admission failure still returns its
own errors even if the failure callback starts a replacement configuration.

Returning errors for a face selector or `seek` is a recoverable caller error;
it does not emit `failed`. Reconfiguration recovers from a failed player. Leaving
the scene tree invokes `shutdown`; re-adding the same node requires configure.
No body-loop, speech or audio event advances a story. No internal `_process`
clock runs: hosts supply one consistent clock and retain UI/audio policy.

`snapshot` includes state (`closed`, `loading`, `ready`, `buffering`, `failed`),
identity, geometry/timebase, frame index, displayed page, absolute clock, loop count, pause flag,
pending clock, resident page IDs/count, worker state, decoded/buffering counters,
selected eye/mouth names, declared states and errors. It retains admitted
descriptor diagnostics after shutdown; `closed` and zero residency indicate
that resources are released. It is for inspection, not cross-version saves.

## Content and export boundary

Configure the public `content_io` loader before passing it in. Descriptor and
texture references use that one explicit root; confinement, path and symlink
admission are provided by `content_io`. External files and retained raw `res://`
sources work. This profile hashes and decodes **source PNG bytes**; it does not
use imported texture remaps when sources are absent. Export the JSON and raw PNG
sources explicitly, or supply an external immutable content directory.

Files must remain immutable during a read, as required by `content_io`; path and
file-size preflights are not an OS sandbox against concurrent replacement.
Payload code imports no game assets, Scenario, generation package or remote
service. Provenance is preserved in game-owned preparation/output records;
playback never changes it or produces new assets.

Native video, separate neutral face plates, animated patch transforms, phoneme
inference, rig deformation, semantic annotation, save migration and generation
integration are intentionally unsupported. These are future explicit contracts,
not capabilities implied by the package name.
