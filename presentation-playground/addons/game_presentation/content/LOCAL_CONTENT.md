# Local content

[local_content.gd](local_content.gd) is an optional `RefCounted` loader for supplied
local media. Games may instead bind existing `Texture2D`, `AudioStream` and
`VideoStream` resources directly. The loader owns no game schema, generation,
provider, network connection, scene, player, global registry or UI.

```gdscript
const LocalContent = preload("res://addons/game_presentation/content/local_content.gd")
var content := LocalContent.new()
var errors: Array[String] = content.configure("/absolute/prepared-content", "files")
if errors.is_empty():
    var result: Dictionary = content.load_texture("actors/hero.webp", true)
    if result.errors.is_empty():
        portrait.texture = result.resource
```

| Method | Contract |
| --- | --- |
| `configure(root = "res://", backend = "resources")` | Returns `Array[String]` diagnostics. Validates before replacing either setting. Independent instances retain independent roots. |
| `get_settings()` | Returns a detached `{root, backend}` dictionary. |
| `resolve(relative_path)` | Returns `{path, errors}`. Validates binding, symlinks and existence. An invalid path is empty. The resolved path is runtime information, not portable content metadata. |
| `read_bytes(relative_path)` | Returns `{bytes, errors}`. Reads source bytes; imported-only resources may have no accessible original bytes. |
| `read_json(relative_path)` | Returns `{value, errors}` for a `.json` document. The caller validates its own JSON shape/schema. |
| `load_texture(relative_path, mipmaps = false)` | Returns `{resource, errors}`. PNG, JPEG and WebP; an `ImageTexture` preserves decoded image size/alpha. Optional mipmaps are generated when absent. No resizing, geometry inference or asset mutation. |
| `load_audio(relative_path, expected_sha256 = "")` | Returns `{resource, errors}`. MP3, WAV or Ogg Vorbis; requires a finite positive decoded duration. Optional lowercase SHA-256 checks source bytes before activation. |
| `load_video(relative_path)` | Returns `{resource, errors}`. Ogg Theora `.ogv` only. Raw files require an Ogg container header; actual asynchronous decoder/playback success remains the `VideoStreamPlayer` host's check. |

Every failed load returns a null resource and diagnostics. The loader does not
cache streams or textures, modify files, play media or mutate previously returned
resources. The host chooses fallbacks and lifetime. Source dimensions, channel
formats, artistic quality and content identity remain consumer concerns.

The **files** backend requires a normalized absolute local directory. Every
binding is a nonempty relative path with forward slashes. Absolute paths, schemes,
backslashes, empty/dot/parent segments, and symbolic links anywhere in the path
are rejected, including linked roots and ancestors. For example, on macOS use
`/private/tmp/content` if `/tmp` is a symbolic link. This is path confinement for
stable local content; it is not an OS sandbox against concurrent filesystem
replacement by another process.

The **resources** backend requires `res://` or a directory below it. Available
source bytes are decoded directly, preserving the existing examples' pixels
without import-time alpha-border changes. When source bytes are absent, imported
media use `ResourceLoader` so Godot's export remapping works. Imported-only images
therefore reflect their import settings; exact source-image parity requires
equivalent import settings or a supplied raw content directory. JSON and other
raw documents must be included explicitly in an export. The loader does not
mount PCKs or change the export configuration. Godot documents the distinction
between source files and imported resources in its
[runtime-loading guide](https://docs.godotengine.org/en/stable/tutorials/io/runtime_file_loading_and_saving.html)
and [DirAccess reference](https://docs.godotengine.org/en/stable/classes/class_diraccess.html).

For imported MP3, `AudioStreamMP3.data` retains compressed source bytes and can
be checked against a source-file hash even when the original path is remapped.
Hash verification of other imported-only codecs fails explicitly if original
bytes are unavailable; it never treats transformed sample data as the source file.
No hashes or revisions are generated from placement paths.

Checks live in `qa/local_content_checks.gd` in the SDK development project.
Full external example equivalence is a separate host check.
