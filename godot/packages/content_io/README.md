# Content I/O

An independent Godot addon for local, explicitly rooted content access and media
decoding. It accepts supplied files without a game manifest, Stage Gen package,
provider, network service or presentation controller.

Copy `addons/content_io` into a consuming project's `addons` directory. The addon
has no runtime dependencies. The package project and tests are development tools,
not part of the installable payload.

```gdscript
const Content = preload("res://addons/content_io/local_content.gd")
var content := Content.new()
var errors := content.configure("/absolute/real/content", "files")
if errors.is_empty():
    var result := content.load_texture("background.webp")
    if result.errors.is_empty():
        $Background.texture = result.resource
```

Each instance owns its root and backend. A failed configuration preserves the
previous settings. The `resources` backend uses a `res://` root and supports
imported Godot resources; `files` uses a normalized absolute local directory.
Bindings reject absolute paths, schemes, backslashes, empty/dot/parent segments
and symbolic links, including linked ancestors. Use the real path of a temporary
directory on systems where a conventional path is a symlink.

`resolve` returns a path or errors. Its optional `must_exist = false` performs
path admission without requiring a file, for adapters with an explicit missing
file policy. Loading methods require the file or imported resource to exist.
The loader does not write content or load scenes/scripts.

| Operation | Successful value | Failure value |
| --- | --- | --- |
| `read_bytes(reference, expected_sha256 = "")` | `bytes`, an admitted byte buffer | Empty bytes and nonempty `errors` |
| `read_json(reference)` | `value`, parsed JSON | Null value and errors |
| `load_image(reference, mipmaps = false)` | `resource`, a CPU `Image` | Null resource and errors |
| `load_texture(reference, mipmaps = false)` | `resource`, an `ImageTexture` | Null resource and errors |
| `load_audio(reference, expected_sha256 = "")` | `resource`, an audio stream | Null resource and errors |
| `load_video(reference)` | `resource`, a Theora stream | Null resource and errors |

Every result contains `errors`; an empty array means this operation succeeded.
Images support PNG, JPEG and WebP, audio supports MP3, WAV and Ogg Vorbis, and
video supports Ogg Theora. Video decoding/playback is asynchronous and must be
checked by the consumer.

SHA-256 verification is explicit. `read_bytes` verifies the exact buffer it
returns when given an expected lowercase digest. Audio loading also supports an
expected source digest; if imported source bytes are unavailable it refuses that
request. No blanket artifact-lineage or all-media digest guarantee is implied.
The caller owns manifests, expected digests, provenance and cache policy.

Files and directories must remain immutable during a call. These checks are not
an OS sandbox against concurrent filesystem replacement. Imported PCK paths are
virtual; source projects additionally check real filesystem links.

Run the package's synthetic, provider-free checks from the repository root:

```sh
godot --headless --path godot/packages/content_io --script res://tests/run_checks.gd
```

The existing `game_presentation` local-content script remains a compatibility
facade over this implementation. The private game run-directory adapter adds
document/layout interpretation and decoded-media caches on top of it.
