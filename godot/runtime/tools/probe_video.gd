class_name VideoProbe
extends SceneTree

## Does the pinned host play an `.ogv` that lives **outside** the project?
##
##   Godot --path godot/runtime -s res://tools/probe_video.gd -- <absolute .ogv path>
##   Godot --path godot/runtime --headless -s res://tools/probe_video.gd -- <path>
##
## This is the go/no-go for carrying video in a run directory. A run's assets
## are never imported: they are written by the pipeline long after the project
## was exported, so every reader in `hosts/common/run_dir.gd` opens a plain
## filesystem path. Textures and MP3s already do (`Image.load_from_file`,
## `AudioStreamMP3.data`), and so does the shell's typeface
## (`FontFile.load_dynamic_font`). Video would be the fourth, and it is the
## only one whose class the engine also exposes as an importable resource — so
## whether `VideoStreamTheora.file` accepts an un-imported outside path is a
## question to measure rather than assume.
##
## The structural argument that it does: Godot ships a `ResourceImporter` for
## every format that genuinely needs importing — `ResourceImporterMP3`,
## `ResourceImporterOggVorbis`, `ResourceImporterTexture` are all in the binary
## — and there is **no** importer for `.ogv`. That says Theora is served by a
## plain loader that opens the path. It is an argument, not a result, hence
## this file.
##
## Run it both ways. Headless has no rendering device, so `get_video_texture()`
## can be null there while playback is fine; a windowed run is what settles the
## picture. `is_playing` and an advancing `stream_position` are the signal.

## How long to let the clip run before reading the clock.
const WATCH_SECONDS := 1.5


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.is_empty():
		push_error("usage: -s res://tools/probe_video.gd -- <absolute .ogv path>")
		quit(2)
		return
	var path := String(args[0])
	if not FileAccess.file_exists(path):
		push_error("no file at %s" % path)
		quit(2)
		return

	var report := {
		"path": path,
		"bytes": FileAccess.get_file_as_bytes(path).size(),
		"headless": DisplayServer.get_name() == "headless",
	}

	# The route a run directory has to use: construct the stream and hand it a
	# filesystem path. `ResourceLoader.load` is reported beside it only to show
	# which of the two works, because that is the finding either way.
	var stream := VideoStreamTheora.new()
	stream.file = path
	report["file_roundtrip"] = stream.file == path
	report["resource_loader"] = ResourceLoader.load(path) != null

	var player := VideoStreamPlayer.new()
	player.stream = stream
	player.volume_db = -80.0
	root.add_child(player)
	# `play()` refuses outside the tree, and in `_initialize` the node is only
	# parented once the loop has turned over once.
	await process_frame
	player.play()
	report["playing_immediately"] = player.is_playing()

	await create_timer(WATCH_SECONDS).timeout

	report["playing_after_wait"] = player.is_playing()
	report["stream_position"] = player.stream_position
	report["advanced"] = player.stream_position > 0.0
	report["has_texture"] = player.get_video_texture() != null
	var texture := player.get_video_texture()
	report["texture_size"] = str(texture.get_size()) if texture != null else "null"

	print(JSON.stringify(report, "  "))
	player.queue_free()
	quit(0 if report["advanced"] else 1)
