class_name PlatformerMusic
extends Node

## The track a map is played under.
##
## The package publishes a soundtrack — three instrumental loops, each with a
## seamless-loop flag and a target duration — the world binds a pool per map and
## shuffles it, and the golden hashes which track is on. Every part of that was
## ported except the part that makes a sound: the host read `world.soundtrack`
## nowhere, so a run that knew exactly what should be playing played nothing.
##
## **The world chooses and this obeys.** Which track is on is simulation state: it
## comes off a shuffle bag seeded from the package digest, it changes when a map is
## entered, and a gate's boss swaps the pool for the length of the fight. Nothing
## here picks a track — it follows `current_track_id`, and a fade is the only thing
## it decides for itself.
##
## Two players rather than one, because a cut between two pieces of music is the
## one transition an ear cannot forgive. The outgoing track falls as the incoming
## one rises over the same window, on equal-power gains so the sum does not dip
## through the middle of the crossing.
##
## The clock is the caller's wall clock rather than the world's. Music is furniture
## and keeps running while the simulation is held — through a conversation, through
## a hitstop, and behind the card that stands in front of a map being built, which
## is precisely when a silence would be most obvious.

## How long one track takes to give way to the next.
const CROSSFADE_MS := 1200.0

## Where the bed sits. Under everything, because it is a bed: a soundtrack that
## competes with the blow that just landed is a soundtrack turned down by the
## player and never turned up again.
const MUSIC_LEVEL := 0.34

## Below this a player is stopped outright rather than left running at a gain
## nothing can hear.
const SILENT := 0.0005

var _players: Array = []
## Which player is carrying the track that should be heard, and what it is.
var _live: int = 0
var _playing: String = ""
## Per-player gain, followed toward its target rather than set, so a switch that
## arrives mid-fade bends the curve instead of restarting it.
var _gains: PackedFloat64Array = PackedFloat64Array([0.0, 0.0])
var _targets: PackedFloat64Array = PackedFloat64Array([0.0, 0.0])
var _package: HostRunDir = null
## Every track the package published, by the id the world names it with.
var _tracks: Dictionary = {}
var _last_ms: float = -1.0


## Build from a run's soundtrack block, or nothing when it publishes no tracks.
static func of(package: HostRunDir, manifest: Dictionary) -> PlatformerMusic:
	var block: Dictionary = manifest.get("soundtrack", {})
	var tracks: Array = block.get("tracks", [])
	if tracks.is_empty():
		push_warning("platformer host: this package publishes no soundtrack, so it plays silent")
		return null
	var made := PlatformerMusic.new()
	made._package = package
	for entry: Variant in tracks:
		var track: Dictionary = entry
		made._tracks[str(track.get("track_id", ""))] = track
	for index in range(2):
		var player := AudioStreamPlayer.new()
		player.volume_db = -80.0
		made.add_child(player)
		made._players.append(player)
	return made


## Follow whatever the world says is on.
##
## `now_ms` is wall time, and the reason it is passed rather than read is the same
## reason every other motion in this host takes one: a clock this file owned would
## be a second answer to what time it is.
func sync(world: PlatformerWorld, now_ms: float) -> void:
	var elapsed := 0.0 if _last_ms < 0.0 else maxf(0.0, now_ms - _last_ms)
	_last_ms = now_ms
	var wanted: Variant = world.soundtrack.get("current_track_id")
	# The world holds the first track back until a key is pressed, and keeps doing
	# so on purpose: a page may not open an audio context without a gesture, the
	# browser heard that gesture as a `keydown`, and both goldens hash the frame
	# `started` turns true. That rule is the reference's and the state keeps it.
	#
	# It is not this engine's rule, though, and obeying it here would mean a player
	# who walks off with the arrow keys and never presses anything else hears
	# nothing at all, for as long as they play. So the host plays what the world has
	# *queued* while it waits — the same track, chosen by the same bag, started a
	# few seconds earlier — and the moment the gesture lands the two agree anyway.
	if wanted == null:
		wanted = world.soundtrack.get("next_track_id")
	var track_id := "" if wanted == null else str(wanted)
	if track_id != _playing:
		_change_to(track_id)
	_advance(elapsed)


## Start a track on the idle player and hand the fade over to it.
func _change_to(track_id: String) -> void:
	_playing = track_id
	# Whatever was live is now leaving, whether or not anything replaces it: a map
	# that publishes no track should fall silent rather than keep the last map's.
	_targets[_live] = 0.0
	if track_id.is_empty():
		return
	var track: Dictionary = _tracks.get(track_id, {})
	if track.is_empty():
		push_warning(
			"platformer host: the world asked for track %s and the package publishes none" % track_id
		)
		return
	var stream := _package.audio(str((track.get("asset", {}) as Dictionary).get("path", "")))
	if stream == null:
		push_warning(
			"platformer host: track %s names audio the run does not carry, so it plays silent"
			% track_id
		)
		return
	# The package says whether the piece was written to come round again. One that
	# was not is left to end, and the world will name the next when it is ready.
	stream.loop = bool(track.get("seamless_loop", false))
	_live = 1 - _live
	var player: AudioStreamPlayer = _players[_live]
	player.stream = stream
	player.volume_db = linear_to_db(maxf(SILENT, _gains[_live] * MUSIC_LEVEL))
	player.play()
	_targets[_live] = 1.0
	_targets[1 - _live] = 0.0


## Move both gains toward their targets and apply them.
func _advance(elapsed_ms: float) -> void:
	var step := 1.0 if CROSSFADE_MS <= 0.0 else clampf(elapsed_ms / CROSSFADE_MS, 0.0, 1.0)
	for index in range(_players.size()):
		_gains[index] = move_toward(_gains[index], _targets[index], step)
		var player: AudioStreamPlayer = _players[index]
		# Equal power rather than linear: two tracks at half gain are not half as
		# loud as one at full, so a linear crossing dips audibly through its middle.
		var level := sin(_gains[index] * PI / 2.0) * MUSIC_LEVEL
		if level <= SILENT:
			if player.playing and is_zero_approx(_targets[index]):
				player.stop()
			continue
		if not player.playing and player.stream != null:
			player.play()
		player.volume_db = linear_to_db(level)
