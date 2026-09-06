class_name Music
extends Node

## The two loops the clock chooses between, ported from viewer/index.html
## section 5b (`class Music`, :4220-4653) — the music half of it; the one-shot
## cues, the weather beds and the thunder live in `audio/sfx.gd`.
##
## The design point the viewer records at :4230-4238 is kept exactly: the clock
## only picks the cue (`switch_at` with ±CUE_HYSTERESIS), and the fade then runs
## on its own timeline (`crossfade_seconds`). Riding the night factor directly
## held two unrelated songs together at half gain for twenty seconds.
##
## Both loops start together on the first key press and run forever; only their
## gains move. Web Audio's `setTargetAtTime(value, now, tau)` is an exponential
## follower, and `_smooth` is the same curve at a frame's delta.

## Rising gain over a fade's own window, by name. See music.toml [transition].
const CURVES := ["linear", "equal_power", "exponential"]
const DEFAULT_TRANSITION := {
	"crossfade_seconds": 2.5, "curve": "equal_power", "overlap": 0.3, "switch_at": 0.5,
}
## The cue does not flip again until the clock is this far past the switch.
const CUE_HYSTERESIS := 0.05
## The bed sits under chopping and footsteps (:4237-4238).
const MASTER_LEVEL := 0.35
const EFFECTS_LEVEL := 0.8
const SFX_LEVEL := 1.0
## The time constants the viewer hands `setTargetAtTime`.
const GAIN_TAU := 0.02
const TOGGLE_TAU := 0.08
const MUSIC_BUS := "Music"
const EFFECTS_BUS := "Effects"
const FOLEY_BUS := "Foley"

var package: Variant = null
## The viewer waits for a key because a browser refuses to play before a
## gesture; Godot has no such rule, so the loops start on the first frame
## unless the frame owner wants to call `start()` itself.
var auto_start: bool = true
## Whether this node answers the B key itself. A frame owner that binds B (none
## does today) should set it false.
var owns_keys: bool = true
var transition: Dictionary = DEFAULT_TRANSITION.duplicate()
var enabled: bool = true
var started: bool = false
var available: bool = false
var cue: String = "day"
var mix: float = 0.0
var settled: bool = false
var night: float = 0.0

var _players: Dictionary = {}
var _durations: Dictionary = {}
var _gains: Dictionary = {"day": 0.0, "night": 0.0}
var _master: float = MASTER_LEVEL
var _effects: float = EFFECTS_LEVEL


func setup(pkg, world, _fu = null) -> void:
	package = pkg
	ensure_buses()
	var block: Dictionary = (world.manifest as Dictionary).get("music", {})
	var authored: Variant = block.get("transition", null)
	# Mixing, never identity: a copy, because a dev panel retunes it live.
	transition = DEFAULT_TRANSITION.duplicate()
	if authored is Dictionary:
		for key: String in (authored as Dictionary).keys():
			transition[key] = (authored as Dictionary)[key]
	for track: String in ["day", "night"]:
		var entry: Variant = block.get(track, null)
		if not (entry is Dictionary):
			continue
		var stream: AudioStreamMP3 = pkg.audio(str((entry as Dictionary).get("audio", "")))
		if stream == null:
			continue
		# AudioStreamMP3.loop defaults to false; music must set it (capabilities §2f).
		stream.loop = true
		stream.loop_offset = 0.0
		var player := AudioStreamPlayer.new()
		player.name = "music_%s" % track
		player.stream = stream
		player.bus = MUSIC_BUS
		player.volume_linear = 0.0
		add_child(player)
		_players[track] = player
		_durations[track] = float((entry as Dictionary).get("duration_seconds", stream.get_length()))
	available = not _players.is_empty()
	_apply_buses(true)


## The viewer's three gain nodes, as buses: music under `master` (0.35),
## weather under `effects` (0.8), one-shots on `foley` (1.0) under effects.
static func ensure_buses() -> void:
	for name: String in [MUSIC_BUS, EFFECTS_BUS, FOLEY_BUS]:
		if AudioServer.get_bus_index(name) >= 0:
			continue
		var index := AudioServer.bus_count
		AudioServer.add_bus(index)
		AudioServer.set_bus_name(index, name)
		AudioServer.set_bus_send(index, EFFECTS_BUS if name == FOLEY_BUS else "Master")
	AudioServer.set_bus_volume_db(AudioServer.get_bus_index(FOLEY_BUS), linear_to_db(SFX_LEVEL))


## Called from the first key press; safe to call again.
func start() -> void:
	if not available or started:
		return
	started = true
	# Both sources start together and run forever (:4546-4548).
	for track: String in _players.keys():
		play_when_ready(_players[track])
	_write(true)


## `play` refuses while a node is outside the tree, which is where a host that
## builds its modules before the first frame still is. Deferring keeps the two
## loops starting on the same frame either way.
static func play_when_ready(player: AudioStreamPlayer, from: float = 0.0) -> void:
	if player.is_inside_tree():
		player.play(from)
	else:
		player.call_deferred("play", from)


func _unhandled_key_input(event: InputEvent) -> void:
	if not owns_keys:
		return
	var key := event as InputEventKey
	if key != null and key.pressed and not key.echo and key.physical_keycode == KEY_B:
		toggle()


func set_mode(_mode: String) -> void:
	pass


func set_look(_look: String) -> void:
	pass


func handle_event(_event: Dictionary) -> void:
	pass


func update(world, delta: float, _cam: Dictionary = {}) -> void:
	if auto_start and not started:
		start()
	if world != null:
		follow(float(world.night), delta)
	_ease_buses(delta)


## The clock chooses a cue, the mixer walks toward it (`follow`, :4551-4565).
func follow(night_factor: float, dt: float) -> void:
	night = night_factor
	var switch_at := float(transition.get("switch_at", 0.5))
	if night_factor > switch_at + CUE_HYSTERESIS:
		cue = "night"
	elif night_factor < switch_at - CUE_HYSTERESIS:
		cue = "day"
	var target := 1.0 if cue == "night" else 0.0
	if not settled:
		settled = true
		mix = target
		_write(true)
		return
	if is_equal_approx(mix, target):
		mix = target
		return
	var step := maxf(0.0, dt) / maxf(0.05, float(transition.get("crossfade_seconds", 2.5)))
	mix = minf(target, mix + step) if target > mix else maxf(target, mix - step)
	_write(false, dt)


## The fade as a pure function of its position, 0 (day) to 1 (night)
## (`fadeGains`, :4534-4543). Each loop owns a share `span` of the window;
## `overlap` is how much of the window they share, so 0 fades one out before
## the other starts and 1 is the classic crossfade.
func fade_gains(value: float) -> Dictionary:
	var span := 0.5 + 0.5 * clampf(float(transition.get("overlap", 0.3)), 0.0, 1.0)
	var m := clampf(value, 0.0, 1.0)
	return {
		"day": rise(1.0 - clampf(m / span, 0.0, 1.0)),
		"night": rise(clampf((m - (1.0 - span)) / span, 0.0, 1.0)),
	}


## One named curve, evaluated. Unknown names fall back to equal power.
func rise(p: float) -> float:
	return curve_value(str(transition.get("curve", "equal_power")), p)


static func curve_value(name: String, p: float) -> float:
	match name:
		"linear":
			return p
		"exponential":
			return p * p
		_:
			return sin(p * PI * 0.5)


func toggle() -> bool:
	enabled = not enabled
	if not started:
		start()
	return enabled


## The same curve as data, for a dev panel to draw (`fadeGraph`, :4599-4618).
func fade_graph() -> Dictionary:
	var day := []
	var night_points := []
	var steps := 60
	for i: int in steps + 1:
		var m := float(i) / float(steps)
		var g := fade_gains(m)
		day.append(Vector2(m, g["day"]))
		night_points.append(Vector2(m, g["night"]))
	return {
		"day": day, "night": night_points, "marker": mix,
		"caption": "%.1fs · %s · overlap %.2f · switch %.2f" % [
			float(transition.get("crossfade_seconds", 2.5)), str(transition.get("curve", "")),
			float(transition.get("overlap", 0.3)), float(transition.get("switch_at", 0.5)),
		],
	}


func describe() -> String:
	if not available:
		return "none"
	if not started:
		return "press any key"
	var parts := PackedStringArray()
	for track: String in ["day", "night"]:
		if not _players.has(track):
			continue
		parts.append("%s %.1fs g=%.2f" % [track, float(_durations[track]), float(_gains[track])])
	parts.append("fade %s %.2f" % [cue, mix])
	return "%s %s" % ["on" if enabled else "muted", " | ".join(parts)]


func status() -> Dictionary:
	return {"music": describe()}


func _write(immediate: bool, dt: float = 0.0) -> void:
	var gains := fade_gains(mix)
	for track: String in _players.keys():
		var value := float(gains.get(track, 0.0))
		if immediate:
			_gains[track] = value
		else:
			# A short follower rather than a step: sixty gain steps a second zips.
			_gains[track] = _smooth(float(_gains[track]), value, GAIN_TAU, dt)
		(_players[track] as AudioStreamPlayer).volume_linear = float(_gains[track])


func _ease_buses(delta: float) -> void:
	var master_target := MASTER_LEVEL if enabled else 0.0
	var effects_target := EFFECTS_LEVEL if enabled else 0.0
	if is_equal_approx(_master, master_target) and is_equal_approx(_effects, effects_target):
		return
	_master = _smooth(_master, master_target, TOGGLE_TAU, delta)
	_effects = _smooth(_effects, effects_target, TOGGLE_TAU, delta)
	_apply_buses(false)


func _apply_buses(immediate: bool) -> void:
	if immediate:
		_master = MASTER_LEVEL if enabled else 0.0
		_effects = EFFECTS_LEVEL if enabled else 0.0
	AudioServer.set_bus_volume_db(AudioServer.get_bus_index(MUSIC_BUS), _to_db(_master))
	AudioServer.set_bus_volume_db(AudioServer.get_bus_index(EFFECTS_BUS), _to_db(_effects))


## Web Audio's `setTargetAtTime(target, now, tau)` sampled at one frame.
static func smooth(current: float, target: float, tau: float, dt: float) -> float:
	if dt <= 0.0 or tau <= 0.0:
		return target
	return target + (current - target) * exp(-dt / tau)


func _smooth(current: float, target: float, tau: float, dt: float) -> float:
	return Music.smooth(current, target, tau, dt)


static func _to_db(level: float) -> float:
	return -80.0 if level <= 0.0001 else linear_to_db(level)
