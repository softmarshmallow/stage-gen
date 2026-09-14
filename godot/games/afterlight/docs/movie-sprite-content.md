# Movie Sprite Actor: Afterlight content profile

The [canonical representation](../../../docs/movie-sprite-actor.md) is a
**Movie Sprite Actor**: pre-rendered body motion with independently controlled
facial states. This file owns Afterlight's preparation profile for the
[package's version-1 runtime contract](../../../packages/movie_sprite_actor/addons/movie_sprite_actor/README.md). Its
neutral face is baked into the body; only eye/mouth replacements are separate
runtime textures. A separately swappable facial base is not implemented here.

Status: **Afterlight-local prepared content, version 1**. This is the content
preparation boundary for the [local diagnostic](movie-sprite-diagnostic.md), not a public
Stage Gen asset contract or promotion of the generation module. The existing
repaint pipeline and its `portrait-face-motion-v1` manifests remain unchanged.

## Preparation and ownership

Run the provider-free game adapter from the repository root:

```sh
.venv/bin/python godot/games/afterlight/tools/prepare_movie_sprite.py
```

The adapter reads the final Yuzu and Riko sources selected in
`spikes/movie_sprite/GAME_ASSET_HANDOFF.md`. It writes new actor directories under
`assets/movie_sprite/` inside the Afterlight game; existing destinations are refused.
Use `--output-root /absolute/new/movie_sprite` to prepare another copy, and
`--source-root /absolute/movie_sprite` if the source handoff moved. The tool needs
FFmpeg/FFprobe, Pillow and NumPy, already used by local media preparation. Neither
playing nor replaying invokes this tool or any provider.

Each actor directory contains 24 lossless PNG body pages, full-canvas facial
replacement PNGs, a runtime manifest, an unpatched 720-pixel-wide canonical,
a complete copied-file inventory and a `provenance/` directory. The provenance
directory preserves the actual 720-pixel-wide FFV1 source, native canonical,
facial input canonicals, selected patch PNGs, manifests, crop transforms,
sidecars and processing/review reports byte-for-byte. Native body masters,
preview movies and generation code are not needed or copied. Upstream sidecar
references retain their original scope; the new inventory separately maps each
selected original reference to its game-owned copy and verifies its hash.

The preparation record contains source and output lineage, the preparation tool
hash, library versions, native patch placement, and mechanical validation. Its
rights note records the user's authorization for this **local diagnostic only**.
Original rights and review limits remain intact; redistribution and publication
are not established. The whole prepared directory, including metadata, stays
ignored by Git. A `.gdignore` keeps the Godot editor from importing the large
atlases and provenance copies; the diagnostic loads validated raw PNG bytes.

The [prepared-content exporter](../tools/prepare_example_content.py) includes the
same inventory-verified closure and `.gdignore` across an external-content
boundary. Its narrow support for copied `.mkv` provenance does not admit other
videos or executable source. Runtime file bindings retain the
[Afterlight content-root rules](../CONTENT.md).

## Runtime manifest

Bindings are relative to the selected game content root, not to the manifest.
Names use the existing repaint state vocabulary. The following fragment omits
most page records and uses illustrative hash placeholders:

```json
{
  "schema_version": 1,
  "character_id": "yuzu",
  "frame_size": [720, 1280],
  "frame_count": 192,
  "fps": 16,
  "columns": 4,
  "rows": 2,
  "pages": [
    {"file": "assets/movie_sprite/yuzu/body_000.png", "sha256": "<64 hex digits>"}
  ],
  "eyes": {
    "eyes_half": {"file": "assets/movie_sprite/yuzu/eyes_half.png", "sha256": "<64 hex digits>"},
    "eyes_closed": {"file": "assets/movie_sprite/yuzu/eyes_closed.png", "sha256": "<64 hex digits>"}
  },
  "mouths": {
    "mouth_a": {"file": "assets/movie_sprite/yuzu/mouth_a.png", "sha256": "<64 hex digits>"},
    "mouth_o": {"file": "assets/movie_sprite/yuzu/mouth_o.png", "sha256": "<64 hex digits>"}
  },
  "eye_semantics": "bilateral_blink",
  "patch_application": "replace_selected_rgb_preserve_original_alpha",
  "preparation_ref": "assets/movie_sprite/yuzu/provenance/preparation.json"
}
```

The shared player reads dimensions, packing, frame count, FPS and supported state
IDs from the descriptor. The values below describe these two prepared assets;
they are not hardcoded SDK requirements. Runtime admission and resource ceilings
are owned by the package contract. Registration and mask semantics are validated
by preparation; the player does not eagerly scan every body page.

Pages are 2880×2560, with eight 720×1280 frames arranged in row-major order.
Frame `i` uses page `i / 8`, column `i % 4`, and row `(i % 8) / 4`, with integer
division. Playback time is derived from 192 frames at 16 FPS, exactly 12 seconds;
it does not use the container's rounded 12.001-second duration. Endpoint pixels
match. The adapter adds no interpolation, stabilization, keying or loop closure.
The runtime owns bounded page loading rather than keeping every decoded page in
memory. Each decoded RGBA page is about 28.1 MiB without mipmaps.

The source coordinate system is the 2160×3840 native canvas, top-left origin,
positive X right and positive Y down. Original integer patch offsets remain
recorded. Runtime canvas coordinates use 720×1280 and the same origin; the final
actor transform moves body and facial replacement together. These positions are
view-specific registration data, not anatomical landmarks or standing-framing
calibration. Visible alpha bounds in preparation evidence describe image
geometry only and must not become an anatomical size claim.

## Independent face controls

| Actor | Eyes | Mouth |
| --- | --- | --- |
| Yuzu | `rest`, `eyes_half`, `eyes_closed`; bilateral blink | `rest`, `mouth_a`, `mouth_o` |
| Riko | `rest`, `eyes_closed`; canvas-left wink only | `rest`, `mouth_a`, `mouth_o` |

`rest` has no replacement texture: it reveals the current unpatched body frame.
Eye and mouth selection are independent of the body clock and of each other.
The host owns blinking, wink timing, and when a speaker's mouth changes. A/O are
coarse demonstration shapes, not a complete viseme inventory or a claim of
phoneme/audio synchronization. Canvas-left names follow the source manifest and
do not mean anatomical left.

Preparation applies each native patch's selected RGB at its original integer
offset on the matching **video-derived** canonical. Patch alpha is binary;
feathering is already baked into its RGB. It then downsamples the whole canvas
once using float premultiplied channels, Lanczos resampling and final rounding.
The matching unpatched canonical uses the same operation. Each runtime texture
contains the precomposed resized RGB and binary alpha selecting pixels where
those RGB values differ from the resized canonical. That alpha is a **replacement
selection mask**, not character opacity and not another feather weight.

The runtime uses selected eye and mouth RGB while retaining each body's original
alpha. It must not alpha-compose a second translucent face layer or re-feather
these textures. For these supplied inputs, preparation verifies that eye and mouth
selection masks do not overlap and that independent replacement exactly matches
joint native eye-and-mouth application followed by one downsample. Other assets
are refused if those assumptions do not hold; version 1 does not silently choose
an overwrite order for overlapping controls.

Riko's original facial-source canonical differs elsewhere from the final body
canonical. This specific reuse is allowed because the adapter verifies equality
on every selected native patch pixel. Both actors additionally verify that the
resized unpatched canonical matches every body frame at every runtime replacement
pixel. This is not a promise that arbitrary older facial atlases remain compatible.

## Validation and limits

The provider-free preparation tests cover path/symlink confinement, provenance
hashes, native RGB-only patching, opacity and bounds refusals, downsample
composition, exact atlas round trips, endpoint/registration failures, and real
FFV1 decoding with explicit frame count and timebase. Real preparation additionally
verifies all 192 frames per actor and all available eye/mouth combinations.

Runtime/native checks and independent visual review are recorded in the
[diagnostic integration note](movie-sprite-diagnostic.md). Mechanical preparation
alone does not prove smooth native playback, attractive rendering, continuous
visual acceptance, listening approval or arbitrary-character reliability. Native
edge softness and the source handoff's other recorded limitations remain.
