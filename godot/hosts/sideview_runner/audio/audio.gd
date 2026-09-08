class_name RunnerAudioView
extends Node

## What the run sounds like: the cue table, the effect voices, and the music bed.
##
## A port of the sink half of `web/lib/sideview-runner/audio.ts` and of
## `soundtrack.ts`. The cue table lives here rather than in the system, exactly
## as it did in the browser — which event fires which sound, on which channel and
## at what strength is a fact about *playing* a run, and the system's business is
## only the `consumes` list that orders it after everything that speaks.
##
## The run published four effects, two spoken and generated clips among them, two
## soundtrack tracks and a `[music]` table of ducks and fades. The port opened
## none of it: there was no audio node anywhere in this host, so a run was
## silent from the first frame to the death card.
##
## Two channels, because one event can be two things. A hit both plays a stinger
## and ducks the music under it; a death both plays a sound and stops the bed.
##
## Nothing here draws from the simulation's generator. The soundtrack's shuffle
## uses the engine's own randomness, because which song plays must never be able
## to move the world — the replay that proves this port would stop being a
## function of its seed.

## The bus effects play on. Created if the project does not define it, so a run
## plays on a machine whose project was authored before this host existed.
const EFFECT_BUS := "RunnerEffects"
const MUSIC_BUS := "RunnerMusic"
## Enough voices that a landing's stinger, a coin and a hurt can overlap.
const VOICES := 12
## The bed sits under the cues.
const MUSIC_LEVEL_DB := -9.0

## Sample rate for a synthesised sweep. The authored frequencies are all well
## under a tenth of this, so nothing here needs oversampling.
const SWEEP_RATE := 44100

var _package: HostRunDir = null
var _effects: Dictionary = {}
var _bindings: Dictionary = {}
var _streams: Dictionary = {}
var _voices: Array = []
var _next_voice: int = 0

var _music: AudioStreamPlayer = null
var _music_table: Dictionary = {}
var _tracks: Array = []
## Where the bed's gain is heading and how fast, in linear units.
var _music_gain: float = 1.0
var _music_target: float = 1.0
var _music_rate: float = 0.0
var _music_curve: String = "linear"
## A duck holds at the bottom before it recovers.
var _duck_hold: float = 0.0
var _duck_recovery: float = 0.0
var _stopping: bool = false
## The announcement waits for the first frame and is dropped the moment anything
## else speaks, because by then the run has begun and announcing its start is
## stale. In the browser this waited on a user gesture too; Godot needs none.
var _announce: String = "stage_start"


static func of(package: HostRunDir) -> RunnerAudioView:
	var audio: Dictionary = package.manifest.get("audio", {})
	if audio.is_empty():
		return null
	var view := RunnerAudioView.new()
	view._package = package
	view._bindings = audio.get("bindings", {})
	view._music_table = audio.get("music", {})
	for entry: Variant in (audio.get("effects", []) as Array):
		var effect: Dictionary = entry
		view._effects[String(effect["effect_id"])] = effect.get("realization", {})
	view._build_buses()
	for index in VOICES:
		var voice := AudioStreamPlayer.new()
		voice.bus = EFFECT_BUS
		view.add_child(voice)
		view._voices.append(voice)
	view._music = AudioStreamPlayer.new()
	view._music.bus = MUSIC_BUS
	view.add_child(view._music)
	view._tracks = (package.manifest.get("soundtrack", {}) as Dictionary).get("tracks", [])
	return view


## One frame's cues. Called from the roster, so it sees every step's events.
##
## Post order is the order the browser's table posted in: the traversal verbs,
## then the field, then the consequence, then the end of the run.
func sync(world: RunnerWorld) -> void:
	var alive := String(world.run["phase"]) != "dead"
	var spoke := false
	for entry: Variant in world.events.of_type("jumped"):
		# The air jump is a different sound from the push off the ground, and
		# the occurrence says which it was.
		_cue("air_jump" if bool((entry as Dictionary).get("airJump", false)) else "takeoff")
		spoke = true
	if alive:
		for _entry: Variant in world.events.of_type("landed"):
			_cue("land")
			spoke = true
	for _entry: Variant in world.events.of_type("slid"):
		_cue("slide")
		spoke = true
	if alive:
		for _entry: Variant in world.events.of_type("hazard-cleared"):
			_cue("hazard_cleared")
			spoke = true
		for _entry: Variant in world.events.of_type("collected"):
			# The chain is this frame's: the scorer is sealed before this system.
			_cue("collect", minf(1.0, float(world.score["chain"]) / 30.0))
			spoke = true
		for _entry: Variant in world.events.of_type("drained"):
			# A survivable hit: the stinger, and the duck under it.
			_cue("hurt")
			_music_transition("hurt")
			spoke = true
	for _entry: Variant in world.events.of_type("run-ended"):
		_cue("death")
		_music_transition("death")
		spoke = true

	if _announce != "":
		if spoke:
			_announce = ""
		elif not world.fx.is_empty() or String(world.run["phase"]) == "running":
			# With a stage-start moment this is the intro's first frame, so the
			# line and the rip are one beat; without one it is the first running
			# frame. Never on a restart.
			var announced := _announce
			_announce = ""
			_cue(announced)
			_start_music()


## A restart starts the bed again over the run that exists.
func reset_cues(scope: String) -> void:
	if scope != FamilySession.SCOPE_RUN:
		return
	for entry: Variant in _voices:
		(entry as AudioStreamPlayer).stop()
	_music_transition("restart")


func _process(delta: float) -> void:
	if _music == null:
		return
	if _duck_hold > 0.0:
		_duck_hold -= delta
		if _duck_hold <= 0.0 and _duck_recovery > 0.0:
			_music_target = 1.0
			_music_rate = 1.0 / maxf(0.001, _duck_recovery)
			_duck_recovery = 0.0
		return
	if is_equal_approx(_music_gain, _music_target):
		return
	var step := _music_rate * delta
	_music_gain = move_toward(_music_gain, _music_target, step)
	_apply_music_gain()
	if _stopping and _music_gain <= 0.001:
		_stopping = false
		_music.stop()


## Play one cue by name, at a strength in [0, 1].
func _cue(cue: String, strength: float = 0.0) -> void:
	var effect_id := String(_bindings.get(cue, ""))
	if effect_id.is_empty():
		return
	var realization: Dictionary = _effects.get(effect_id, {})
	if realization.is_empty():
		push_warning("runner audio: %s binds %s, which this run does not publish" % [cue, effect_id])
		return
	var stream := _stream_for(effect_id, realization)
	if stream == null:
		return
	var voice: AudioStreamPlayer = _voices[_next_voice]
	_next_voice = (_next_voice + 1) % _voices.size()
	voice.stream = stream
	voice.volume_db = linear_to_db(maxf(0.0001, float(realization.get("gain", 1.0))))
	# A strength-graded cue lifts its playback rate; a chain of coins climbs.
	voice.pitch_scale = 1.0 + clampf(strength, 0.0, 1.0) * float(
		realization.get("strength_pitch_multiplier", 0.0)
	)
	voice.play()


## The stream behind one effect, built once.
##
## A published clip is read from the run. A sweep is synthesised, because that is
## what the realization *is* — the package authored a waveform, two frequencies
## and a duration rather than a file, and a host that shipped a substitute sample
## would be playing something the producer never wrote.
func _stream_for(effect_id: String, realization: Dictionary) -> AudioStream:
	if _streams.has(effect_id):
		return _streams[effect_id]
	var made: AudioStream = null
	var kind := String(realization.get("kind", ""))
	if kind == "oscillator_sweep_v1":
		made = _sweep(realization)
	elif realization.has("clip"):
		made = _package.audio(String(realization["clip"]))
	else:
		push_warning("runner audio: %s has a realization this build cannot play (%s)" % [effect_id, kind])
	_streams[effect_id] = made
	return made


## A single oscillator sweeping between two frequencies, with a short attack and
## a release so it starts and ends on a zero rather than a click.
func _sweep(realization: Dictionary) -> AudioStreamWAV:
	var seconds := maxf(0.001, float(realization.get("duration_milliseconds", 100)) / 1000.0)
	var start_hz := float(realization.get("start_frequency_hz", 440.0))
	var end_hz := float(realization.get("end_frequency_hz", start_hz))
	var waveform := String(realization.get("waveform", "sine"))
	var frames := int(seconds * float(SWEEP_RATE))
	var attack := mini(frames / 8, int(0.004 * float(SWEEP_RATE)))
	var release := mini(frames / 2, int(0.03 * float(SWEEP_RATE)))
	var data := PackedByteArray()
	data.resize(frames * 2)
	var phase := 0.0
	for index in frames:
		var progress := float(index) / float(maxi(1, frames - 1))
		# Linear in frequency, which is what "start" and "end" name; the phase
		# is the running integral of it rather than the frequency times the
		# time, or the sweep would land on the wrong pitch.
		var hz := start_hz + (end_hz - start_hz) * progress
		phase += TAU * hz / float(SWEEP_RATE)
		var envelope := 1.0
		if index < attack:
			envelope = float(index) / float(maxi(1, attack))
		elif index > frames - release:
			envelope = float(frames - index) / float(maxi(1, release))
		var value := _waveform_at(waveform, phase) * envelope
		var sample := int(clampf(value, -1.0, 1.0) * 32767.0)
		data.encode_s16(index * 2, sample)
	var stream := AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = SWEEP_RATE
	stream.stereo = false
	stream.data = data
	return stream


static func _waveform_at(waveform: String, phase: float) -> float:
	var cycle := fposmod(phase, TAU) / TAU
	match waveform:
		"square":
			return 1.0 if cycle < 0.5 else -1.0
		"sawtooth":
			return cycle * 2.0 - 1.0
		"triangle":
			return 1.0 - absf(cycle * 4.0 - 2.0)
		_:
			return sin(phase)


## Start the bed on whichever track the selection names.
func _start_music() -> void:
	if _music == null or _tracks.is_empty() or _music.playing:
		return
	var selection := String(
		(_package.manifest.get("soundtrack", {}) as Dictionary).get("selection", "shuffle")
	)
	var index := 0
	if selection == "shuffle" and _tracks.size() > 1:
		# The engine's randomness, never the run's: which song plays must not be
		# able to move the world.
		index = randi() % _tracks.size()
	var stream := _package.audio(String((_tracks[index] as Dictionary)["audio"]))
	if stream == null:
		return
	stream.loop = true
	_music.stream = stream
	_music_gain = 1.0
	_music_target = 1.0
	_stopping = false
	_apply_music_gain()
	_music.play()


## Apply one authored `[music]` action: a stop, a start, or a duck.
func _music_transition(event: String) -> void:
	var action: Dictionary = _music_table.get(event, {})
	if action.is_empty() or _music == null:
		return
	if action.has("duck_gain"):
		_music_gain = 1.0 if _music_gain > float(action["duck_gain"]) else _music_gain
		_music_target = float(action["duck_gain"])
		_music_rate = (
			(_music_gain - _music_target) / maxf(0.001, float(action.get("fade_seconds", 0.05)))
		)
		_music_gain = _music_target
		_apply_music_gain()
		_duck_hold = float(action.get("hold_seconds", 0.0))
		_duck_recovery = float(action.get("recovery_seconds", 0.0))
		return
	_music_curve = String(action.get("curve", "linear"))
	var seconds := maxf(0.001, float(action.get("fade_seconds", 0.5)))
	match String(action.get("action", "")):
		"stop":
			_music_target = 0.0
			_music_rate = _music_gain / seconds
			_stopping = true
		"play":
			_duck_hold = 0.0
			_duck_recovery = 0.0
			_stopping = false
			if not _music.playing:
				_music_gain = 0.0
				_start_music()
			_music_target = 1.0
			_music_rate = (1.0 - _music_gain) / seconds


func _apply_music_gain() -> void:
	# The authored curve shapes the *fade*, not the level: a linear fade walks
	# the gain, an exponential one walks its cube, which is what a listener hears
	# as an even drop to nothing.
	var shaped := _music_gain
	if _music_curve == "exponential":
		shaped = _music_gain * _music_gain * _music_gain
	elif _music_curve == "equal_power":
		shaped = sin(_music_gain * PI / 2.0)
	_music.volume_db = MUSIC_LEVEL_DB + linear_to_db(maxf(0.0001, shaped))


## Two buses, made if the project does not carry them.
func _build_buses() -> void:
	for name in [EFFECT_BUS, MUSIC_BUS]:
		if AudioServer.get_bus_index(name) >= 0:
			continue
		var index := AudioServer.bus_count
		AudioServer.add_bus(index)
		AudioServer.set_bus_name(index, name)
		AudioServer.set_bus_send(index, "Master")
