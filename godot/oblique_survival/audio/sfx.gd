class_name Sfx
extends Node

## The one-shot cues, the footsteps, the fire bed, the weather ambience and the
## thunder — the half of the viewer's `class Music` that is not the two music
## loops (viewer/index.html :4268-4506, and the frame-driven calls at
## :5546-5551 and :5551-5601).
##
## Two things are load-bearing here:
##  * the onset cut (`cutAtOnsets`, :4268-4300). A cue declaring `onsets` is a
##    run of events in one clip, and one slice of it is played per trigger,
##    never the same slice twice running. The file is never touched; this is
##    only where playback starts and stops. Godot cannot decode an mp3 to
##    samples with a loader, but `AudioStreamPlayback.mix_audio` does exactly
##    that offline, so the RMS envelope is computed the viewer's way at boot.
##  * the pitch jitter draws from Godot's own RNG, never from the sim PRNG, so
##    audio cannot perturb the simulation (:4416 uses `Math.random`).

const WALK_RATE := 9.5
const FIRE_HEARING_METERS := 9.0
const ONSET_HOP_SECONDS := 0.005
const ONSET_GAP_SECONDS := 0.2
const ONSET_FLOOR := 0.3
const ONSET_LEAD_SECONDS := 0.008
const MIN_SLICE_SECONDS := 0.05
## The envelope on a cut slice: 4 ms in, 40 ms out (:4429-4432).
const SLICE_ATTACK := 0.004
const SLICE_RELEASE := 0.04
const RAIN_GAIN := 0.7
const RAIN_TAU := 0.4
const SNOW_GAIN := 0.6
const SNOW_TAU := 0.6
const FIRE_TAU := 0.3
## The viewer only rewrites a continuous gain when its factor moved this far.
const FACTOR_EPSILON := 0.005
const VOICES := 12

var package: Variant = null
## As `Music.auto_start`: nothing in Godot requires a gesture before audio.
var auto_start: bool = true
var started: bool = false
var snow_level: float = 0.0
var fire_level: float = 0.0
var rain_level: float = 0.0

var _sounds: Dictionary = {}
var _streams: Dictionary = {}
## Per cue declared `onsets`: `[[start, length], ...]` of each event in its clip.
var _slices: Dictionary = {}
var _last_slice: Dictionary = {}
var _voices: Array = []
var _envelopes: Array = []
var _fire: AudioStreamPlayer = null
var _ambience: AudioStreamPlayer = null
var _wind: AudioStreamPlayer = null
var _thunder: AudioStreamPlayer = null
var _thunder_stream: AudioStream = null
var _rain_duration: float = 0.0
var _fire_gain: float = 0.0
var _fire_target: float = 0.0
var _rain_gain: float = 0.0
var _rain_target: float = 0.0
var _wind_gain: float = 0.0
var _wind_target: float = 0.0
var _step_count: int = -1
var _step_side: int = 0
var _rng := RandomNumberGenerator.new()


func setup(pkg, world, _fu = null) -> void:
	package = pkg
	Music.ensure_buses()
	_rng.randomize()
	var manifest: Dictionary = world.manifest
	_sounds = manifest.get("sounds", {})
	for cue: String in _sounds.keys():
		var entry: Dictionary = _sounds[cue]
		var stream: AudioStreamMP3 = pkg.audio(str(entry.get("audio", "")))
		if stream == null:
			continue
		_streams[cue] = stream
		if bool(entry.get("onsets", false)):
			_slices[cue] = cut_at_onsets(stream, entry.get("onsets_seconds", null))
	for index: int in VOICES:
		var voice := AudioStreamPlayer.new()
		voice.name = "voice_%d" % index
		voice.bus = Music.FOLEY_BUS
		add_child(voice)
		_voices.append(voice)
	if _streams.has("fire"):
		_fire = _loop_player("fire", _streams["fire"], Music.FOLEY_BUS)
	var weather: Dictionary = manifest.get("weather", {})
	var rain_sound: Dictionary = (weather.get("rain", {}) as Dictionary).get("sound", {})
	var snow_sound: Dictionary = (weather.get("snow", {}) as Dictionary).get("sound", {})
	if rain_sound.get("ambience") is Dictionary:
		var stream: AudioStreamMP3 = pkg.audio(str((rain_sound["ambience"] as Dictionary).get("audio", "")))
		if stream != null:
			_rain_duration = float((rain_sound["ambience"] as Dictionary).get("duration_seconds",
				stream.get_length()))
			_ambience = _loop_player("rain", stream, Music.EFFECTS_BUS)
	if snow_sound.get("ambience") is Dictionary:
		var stream: AudioStreamMP3 = pkg.audio(str((snow_sound["ambience"] as Dictionary).get("audio", "")))
		if stream != null:
			_wind = _loop_player("wind", stream, Music.EFFECTS_BUS)
	if rain_sound.get("strike") is Dictionary:
		_thunder_stream = pkg.audio(str((rain_sound["strike"] as Dictionary).get("audio", "")))
		if _thunder_stream != null:
			_thunder = AudioStreamPlayer.new()
			_thunder.name = "thunder"
			_thunder.bus = Music.EFFECTS_BUS
			_thunder.stream = _thunder_stream
			add_child(_thunder)


## The loops begin with the music, on the first key press. Safe to call again.
func start() -> void:
	if started:
		return
	started = true
	for player: AudioStreamPlayer in [_fire, _ambience, _wind]:
		if player != null:
			player.volume_linear = 0.0
			Music.play_when_ready(player)


func set_mode(_mode: String) -> void:
	pass


func set_look(_look: String) -> void:
	pass


## The event drain (:5551-5601): the verb is the cue name for a hit.
func handle_event(event: Dictionary) -> void:
	match str(event.get("type", "")):
		"hit":
			play(str(event.get("verb", "")))
		"pickup", "craft":
			play("pickup")
		"eat":
			play("eat")
		"thunder":
			thunder(float(event.get("distance", 0.0)))


func update(world, _delta: float, _cam: Dictionary = {}) -> void:
	if auto_start and not started:
		start()
	if not started or world == null:
		return
	var weather: Dictionary = world.weather
	var rain := float(weather.get("rain", 0.0))
	if absf(rain - rain_level) > FACTOR_EPSILON:
		set_rain(rain)
	var snow := float(weather.get("snow", 0.0))
	if absf(snow - snow_level) > FACTOR_EPSILON:
		set_snow(snow)
	hear_fire(world)
	footsteps(world.player, snow_level)


func _process(delta: float) -> void:
	if not started:
		return
	if _fire != null:
		_fire_gain = Music.smooth(_fire_gain, _fire_target, FIRE_TAU, delta)
		_fire.volume_linear = _fire_gain
	if _ambience != null:
		_rain_gain = Music.smooth(_rain_gain, _rain_target, RAIN_TAU, delta)
		_ambience.volume_linear = _rain_gain
	if _wind != null:
		_wind_gain = Music.smooth(_wind_gain, _wind_target, SNOW_TAU, delta)
		_wind.volume_linear = _wind_gain
	_advance_envelopes(delta)


## One play of a cue: the authored gain times the caller's, detuned by up to the
## authored jitter either way (`play`, :4410-4440). False when the cue is not in
## the package, or is a loop (the fire is driven by `hear_fire` alone).
func play(cue: String, scale: float = 1.0) -> bool:
	if cue == "" or not _streams.has(cue):
		return false
	var entry: Dictionary = _sounds[cue]
	if bool(entry.get("loop", false)):
		return false
	if not started:
		start()
	var voice := _free_voice()
	if voice == null:
		return false
	voice.stream = _streams[cue]
	var jitter := float(entry.get("pitch_jitter", 0.0))
	voice.pitch_scale = pow(2.0, ((_rng.randf() * 2.0 - 1.0) * jitter) / 12.0) if jitter > 0.0 else 1.0
	var level := float(entry.get("gain", 1.0)) * maxf(0.0, scale)
	var slices: Array = _slices.get(cue, [])
	if slices.size() > 1:
		# One event out of the run, never the same one twice running, with a
		# short envelope so the cut is not heard as a click.
		var index := int(floor(_rng.randf() * slices.size()))
		index = mini(index, slices.size() - 1)
		if index == int(_last_slice.get(cue, -1)):
			index = (index + 1) % slices.size()
		_last_slice[cue] = index
		var slice: Array = slices[index]
		var start_at := float(slice[0])
		var length := float(slice[1])
		voice.volume_linear = 0.0
		Music.play_when_ready(voice, start_at)
		_envelopes.append({"voice": voice, "level": level, "elapsed": 0.0, "length": length})
		return true
	voice.volume_linear = level
	Music.play_when_ready(voice)
	return true


## Every frame: how near the nearest lit campfire is, as a hearing level
## (`hearFire`, :4443-4454).
func hear_fire(world) -> void:
	var nearest := INF
	var px := _num(world.player, "x", 0.0)
	var pz := _num(world.player, "z", 0.0)
	for entity: Variant in world.entities:
		if not (entity is Dictionary):
			continue
		var e: Dictionary = entity
		if e.get("state", "") != "lit" or e.get("kind", "") != "prop":
			continue
		var dx := float(e.get("x", 0.0)) - px
		var dz := float(e.get("z", 0.0)) - pz
		nearest = minf(nearest, sqrt(dx * dx + dz * dz))
	var level := 0.0 if is_inf(nearest) else pow(clampf(1.0 - nearest / FIRE_HEARING_METERS, 0.0, 1.0), 1.5)
	if absf(level - fire_level) > FACTOR_EPSILON:
		set_fire(level)


## The fire loop's level on [0, 1]: a fire is walked up to, not switched on.
func set_fire(level: float) -> void:
	fire_level = clampf(level, 0.0, 1.0)
	var entry: Dictionary = _sounds.get("fire", {})
	_fire_target = float(entry.get("gain", 1.0)) * fire_level


## A footstep each time the walk cycle plants a foot (`footsteps`, :4461-4474).
## The cadence is the mannequin's: a foot lands every half turn of WALK_RATE.
func footsteps(player, snow: float = -1.0) -> void:
	if snow >= 0.0:
		snow_level = snow
	var walking: bool = str(_field(player, "state", "")) == "walk" \
		and _field(player, "busy", null) == null
	if not walking:
		_step_count = -1
		return
	var count := int(floor((_num(player, "elapsed", 0.0) * WALK_RATE) / PI))
	if _step_count == -1:
		_step_count = count
		return
	if count == _step_count:
		return
	_step_count = count
	_step_side = 1 - _step_side
	# The off foot a touch lighter, so a walk reads left-right, not tick-tick.
	# Under snow the walk crunches, when the package has that cue.
	var cue := "footstep_snow" if snow_level >= 0.5 and _streams.has("footstep_snow") else "footstep"
	play(cue, 0.85 if _step_side == 1 else 1.0)


func set_rain(rain: float) -> void:
	rain_level = rain
	_rain_target = clampf(rain, 0.0, 1.0) * RAIN_GAIN


## The wind: the snow condition's ambience, its gain the snow factor.
func set_snow(snow: float) -> void:
	snow_level = snow
	_wind_target = clampf(snow, 0.0, 1.0) * SNOW_GAIN


## Louder when close; a strike twenty metres off is still most of the way up.
func thunder(distance: float) -> void:
	if _thunder == null:
		return
	_thunder.volume_linear = maxf(0.3, 1.0 - distance / 45.0)
	Music.play_when_ready(_thunder)


func describe() -> String:
	var parts := PackedStringArray()
	var cues := _sounds.keys()
	if not cues.is_empty():
		var cut := PackedStringArray()
		for cue: String in _slices.keys():
			cut.append("%s×%d" % [cue, (_slices[cue] as Array).size()])
		parts.append("sfx %d/%d%s" % [_streams.size(), cues.size(),
			(" " + " ".join(cut)) if not cut.is_empty() else ""])
	if _fire != null:
		parts.append("fire g=%.2f" % _fire_gain)
	if _ambience != null:
		parts.append("rain %.1fs g=%.2f" % [_rain_duration, _rain_gain])
	if _wind != null:
		parts.append("wind g=%.2f" % _wind_gain)
	if _thunder_stream != null:
		parts.append("thunder")
	return " | ".join(parts) if not parts.is_empty() else "none"


func status() -> Dictionary:
	return {"sfx": describe()}


# ===========================================================================
# The onset cut
# ===========================================================================

## Where the events are in a clip that is a run of them (`cutAtOnsets`,
## :4273-4300): the RMS envelope in 5 ms hops; a peak standing above a share of
## the loudest hop and at least ONSET_GAP_SECONDS after the last is an onset;
## each slice runs from a hair before its onset to the next one.
##
## `authored` short-circuits the analysis when the package ships the onset
## table itself (`onsets_seconds`), which full-v66 does not.
static func cut_at_onsets(stream: AudioStream, authored: Variant = null) -> Array:
	if authored is Array and not (authored as Array).is_empty():
		var listed: Array = authored
		var out: Array = []
		for index: int in listed.size():
			var start := float(listed[index])
			var end := float(listed[index + 1]) if index + 1 < listed.size() else stream.get_length()
			out.append([start, maxf(MIN_SLICE_SECONDS, end - start)])
		return out
	var samples := decode(stream)
	if samples.is_empty():
		return []
	var rate := AudioServer.get_mix_rate()
	var hop := maxi(1, int(round(rate * ONSET_HOP_SECONDS)))
	var env := PackedFloat32Array()
	var index := 0
	while index + hop <= samples.size():
		var sum := 0.0
		for j: int in range(index, index + hop):
			var frame := samples[j]
			sum += frame.x * frame.x + frame.y * frame.y
		env.append(sqrt(sum / float(hop * 2)))
		index += hop
	var peak := 0.0
	for value: float in env:
		peak = maxf(peak, value)
	if peak <= 0.0:
		return []
	var floor_level := peak * ONSET_FLOOR
	var gap := int(round(ONSET_GAP_SECONDS / ONSET_HOP_SECONDS))
	var onsets := PackedFloat32Array()
	var last := -gap
	for i: int in range(1, env.size() - 1):
		if env[i] >= floor_level and env[i] >= env[i - 1] and env[i] > env[i + 1] and i - last >= gap:
			onsets.append(maxf(0.0, i * ONSET_HOP_SECONDS - ONSET_LEAD_SECONDS))
			last = i
	var slices: Array = []
	for k: int in onsets.size():
		var end := float(onsets[k + 1]) if k + 1 < onsets.size() else stream.get_length()
		slices.append([float(onsets[k]), maxf(MIN_SLICE_SECONDS, end - float(onsets[k]))])
	return slices


## The clip as samples, decoded offline through a playback instance. This is
## the only way to read an mp3's waveform in Godot; it costs ~1.5 ms for a
## 2.5 s clip and works headless and under `--audio-driver Dummy`.
static func decode(stream: AudioStream) -> PackedVector2Array:
	var playback: Variant = stream.instantiate_playback()
	if playback == null or not playback.has_method("mix_audio"):
		return PackedVector2Array()
	playback.start(0.0)
	var wanted := int(stream.get_length() * AudioServer.get_mix_rate()) + 1
	var samples := PackedVector2Array()
	while samples.size() < wanted:
		var chunk: PackedVector2Array = playback.mix_audio(1.0, mini(4096, wanted - samples.size()))
		if chunk.is_empty():
			break
		samples.append_array(chunk)
		if not playback.is_playing():
			break
	playback.stop()
	return samples


# ===========================================================================
# Plumbing
# ===========================================================================

func _loop_player(id: String, stream: AudioStreamMP3, bus: String) -> AudioStreamPlayer:
	stream.loop = true
	stream.loop_offset = 0.0
	var player := AudioStreamPlayer.new()
	player.name = "loop_%s" % id
	player.stream = stream
	player.bus = bus
	player.volume_linear = 0.0
	add_child(player)
	return player


func _free_voice() -> AudioStreamPlayer:
	for voice: AudioStreamPlayer in _voices:
		if not voice.playing:
			return voice
	# Every voice is busy: steal the oldest, as a browser would simply layer on.
	return _voices[0] if not _voices.is_empty() else null


func _advance_envelopes(delta: float) -> void:
	if _envelopes.is_empty():
		return
	var kept: Array = []
	for envelope: Dictionary in _envelopes:
		var voice: AudioStreamPlayer = envelope["voice"]
		var length := float(envelope["length"])
		var level := float(envelope["level"])
		var t := float(envelope["elapsed"]) + delta
		envelope["elapsed"] = t
		if t >= length:
			voice.stop()
			continue
		var hold := maxf(SLICE_ATTACK, length - SLICE_RELEASE)
		var gain := level
		if t < SLICE_ATTACK:
			gain = level * (t / SLICE_ATTACK)
		elif t > hold:
			gain = level * maxf(0.0, (length - t) / maxf(0.0001, length - hold))
		voice.volume_linear = gain
		kept.append(envelope)
	_envelopes = kept


func _num(object: Variant, key: String, fallback: float) -> float:
	var value: Variant = _field(object, key, fallback)
	return float(value) if (value is float or value is int) else fallback


func _field(object: Variant, key: String, fallback: Variant) -> Variant:
	if object is Dictionary:
		return (object as Dictionary).get(key, fallback)
	if object is Object and key in object:
		return object.get(key)
	return fallback
