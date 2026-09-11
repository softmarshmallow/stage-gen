extends Node

## Optional non-positional audio for a host's text reveal. The host supplies
## visible Unicode codepoints; this node never advances text or story time.
const MODES := ["auto", "typing", "silent"]
const SETTINGS := ["mode", "typing_stream", "typing_volume_db", "voice_volume_db", "min_interval_seconds", "bus", "voice_bus"]

var _mode := "auto"
var _min_interval_seconds := 0.06
var _typing_player := AudioStreamPlayer.new()
var _voice_player := AudioStreamPlayer.new()
var _text := ""
var _visible_characters := 0
var _active_mode := "idle"
var _paused := false
var _time_since_tick := 0.0
var _typing_play_count := 0
var _voice_finished := false
var _voice_position_seconds := 0.0


func _init() -> void:
	_typing_player.name = "TypingAudio"
	_voice_player.name = "VoiceAudio"
	add_child(_typing_player)
	add_child(_voice_player)
	_voice_player.finished.connect(_on_voice_finished)
	_typing_player.stream = create_default_typing_stream()
	_typing_player.volume_db = -14.0


## A valid configuration replaces settings and stops the old cue. Omitted
## values use defaults. Invalid settings leave settings and playback untouched.
func configure(settings: Dictionary = {}) -> Array[String]:
	var errors: Array[String] = []
	for key: Variant in settings:
		if key not in SETTINGS:
			errors.append("Unknown text reveal audio setting: " + str(key))
	if not settings.get("mode", "auto") is String or settings.get("mode", "auto") not in MODES:
		errors.append("Text reveal audio mode must be auto, typing, or silent.")
	var supplied_stream: Variant = settings.get("typing_stream")
	if supplied_stream != null and not supplied_stream is AudioStream:
		errors.append("Text reveal typing_stream must be an AudioStream or null.")
	for key: String in ["typing_volume_db", "voice_volume_db", "min_interval_seconds"]:
		if not settings.has(key):
			continue
		var value: Variant = settings[key]
		var minimum := 0.02 if key == "min_interval_seconds" else -80.0
		var maximum := 1.0 if key == "min_interval_seconds" else 6.0
		if not (value is int or value is float) or not is_finite(float(value)):
			errors.append("Text reveal audio " + key + " must be a finite number.")
		elif float(value) < minimum or float(value) > maximum:
			errors.append("Text reveal audio " + key + " is outside its supported range.")
	var bus: Variant = settings.get("bus", "Master")
	var voice_bus: Variant = settings.get("voice_bus", bus)
	for key: String in ["bus", "voice_bus"]:
		var route: Variant = bus if key == "bus" else voice_bus
		if not (route is String or route is StringName) or str(route).is_empty():
			errors.append("Text reveal audio " + key + " must name an existing audio bus.")
		elif AudioServer.get_bus_index(route) < 0:
			errors.append("Text reveal audio " + key + " does not exist: " + str(route))
	if not errors.is_empty():
		return errors
	stop()
	_mode = settings.get("mode", "auto")
	_min_interval_seconds = float(settings.get("min_interval_seconds", 0.06))
	_typing_player.stream = supplied_stream if supplied_stream != null else create_default_typing_stream()
	_typing_player.volume_db = float(settings.get("typing_volume_db", -14.0))
	_voice_player.volume_db = float(settings.get("voice_volume_db", 0.0))
	_typing_player.bus = bus
	_voice_player.bus = voice_bus
	return errors


## Attach to a scene tree before beginning audible playback. Existing revealed
## text is silent. A voice resume position of -1 marks an already-finished voice.
func begin(text: String, voice: AudioStream = null, visible_characters: int = 0, resume_voice_seconds: float = 0.0) -> void:
	stop()
	_text = text
	_visible_characters = clampi(visible_characters, 0, text.length())
	_time_since_tick = _min_interval_seconds
	_active_mode = "voice" if _mode == "auto" and voice != null else ("typing" if _mode != "silent" else "silent")
	if _active_mode != "voice":
		return
	_voice_player.stream = voice
	var resume := resume_voice_seconds if is_finite(resume_voice_seconds) else 0.0
	var length := voice.get_length()
	_voice_finished = resume == -1.0 or (length > 0.0 and resume >= length)
	_voice_position_seconds = length if _voice_finished else maxf(0.0, resume)
	if not _voice_finished and is_inside_tree():
		_voice_player.play(_voice_position_seconds)
		_voice_player.stream_paused = _paused


## Coalesce newly revealed non-whitespace codepoints to at most one sound per
## update and per minimum interval. Suppressed glyphs are consumed, never queued.
## audible controls typing pulses only; voice has its own playback clock.
func update_reveal(visible_characters: int, delta: float, audible: bool = true) -> void:
	if not is_finite(delta) or delta < 0.0:
		return
	var target := clampi(visible_characters, 0, _text.length())
	if _active_mode != "typing" or _paused or not audible or target < _visible_characters:
		sync_reveal(target)
		return
	_time_since_tick = minf(_time_since_tick + delta, _min_interval_seconds)
	var has_glyph := false
	for index: int in range(_visible_characters, target):
		if not _is_whitespace(_text.unicode_at(index)):
			has_glyph = true
			break
	_visible_characters = target
	if not has_glyph or _time_since_tick < _min_interval_seconds or not is_inside_tree():
		return
	_time_since_tick = 0.0
	_typing_play_count += 1
	_typing_player.play()


## Manual reveal, language replacement, and checkpoint replay use this silent
## cursor jump. A playing voice continues unless the host explicitly stops it.
func sync_reveal(visible_characters: int) -> void:
	_visible_characters = clampi(visible_characters, 0, _text.length())
	_typing_player.stop()


func set_paused(paused: bool) -> void:
	# Godot reports playing=false while stream_paused. Capture the live cursor
	# before that switch so paused checkpoints retain their actual seek position.
	if paused and not _paused and _active_mode == "voice" and _voice_player.playing:
		_voice_position_seconds = _voice_player.get_playback_position()
	_paused = paused
	_typing_player.stream_paused = paused
	_voice_player.stream_paused = paused


func stop() -> void:
	_typing_player.stop()
	_voice_player.stop()
	_voice_player.stream = null
	_text = ""
	_visible_characters = 0
	_active_mode = "idle"
	_time_since_tick = 0.0
	_typing_play_count = 0
	_voice_finished = false
	_voice_position_seconds = 0.0


## Runtime diagnostics; the host owns checkpoint shape and stream identities.
func get_state() -> Dictionary:
	return {
		"mode": _mode,
		"bus": _typing_player.bus,
		"voice_bus": _voice_player.bus,
		"active_mode": _active_mode,
		"visible_characters": _visible_characters,
		"paused": _paused,
		"typing_play_count": _typing_play_count,
		"voice_position_seconds": _voice_player.get_playback_position() if _voice_player.playing else _voice_position_seconds,
		"voice_playing": _voice_player.playing,
		"voice_finished": _voice_finished,
	}


func _on_voice_finished() -> void:
	_voice_finished = true
	_voice_position_seconds = _voice_player.stream.get_length() if _voice_player.stream != null else 0.0


func _exit_tree() -> void:
	stop()


static func _is_whitespace(codepoint: int) -> bool:
	return codepoint in [9, 10, 11, 12, 13, 32, 133, 160, 5760, 8232, 8233, 8239, 8287, 12288] or (codepoint >= 8192 and codepoint <= 8202)


## Original deterministic 26 ms PCM tap. Its envelope starts/ends at zero;
## no asset download, synthesis service, random state, or binary file is needed.
static func create_default_typing_stream() -> AudioStreamWAV:
	const RATE := 44100
	const DURATION := 0.026
	var count := int(RATE * DURATION)
	var pcm := PackedByteArray()
	pcm.resize(count * 2)
	for index: int in range(count):
		var time := float(index) / RATE
		var progress := float(index) / (count - 1)
		var envelope := sin(PI * progress) * exp(-4.0 * progress)
		var tone := 0.72 * sin(TAU * 820.0 * time) + 0.28 * sin(TAU * 1430.0 * time)
		var sample := int(clampf(tone * envelope * 0.7, -1.0, 1.0) * 32767.0)
		pcm.encode_s16(index * 2, sample)
	var stream := AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = RATE
	stream.stereo = false
	stream.loop_mode = AudioStreamWAV.LOOP_DISABLED
	stream.data = pcm
	return stream
