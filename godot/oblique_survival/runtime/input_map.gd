class_name HostInput
extends Node

## The keyboard, ported key for key from the viewer's `keydown` handler
## (index.html:5228-5294) and the per-substep sampling in its loop (:5496-5515).
##
## Two kinds of key. **Held** keys (WASD/arrows, Space) are re-read every
## simulation substep, so a held Space starts the next swing the moment the last
## one ends. Every other key is a **one-shot press**: it is remembered here and
## written into `world.input` on the next substep, where it lives for exactly
## one step (`Sim.clear_one_shots` wipes it, as the viewer's loop does).
##
## Mode-level keys (turn, weather, season, map, reset…) are not simulation
## input at all: they are emitted as `action(name)` for the frame owner to act
## on, because they move the camera, the view or the run — never the world's
## input bag.
##
## Naming deviation: the file the plan named `runtime/input_map.gd` cannot
## declare `class_name InputMap` — Godot refuses a script class that hides a
## native class ("Class 'InputMap' hides a native class"), and `InputMap` is the
## engine's action singleton. The class is `HostInput`; the path is unchanged.

## A mode-level key. One of: yaw_left, yaw_right, weather, season, night,
## strike, music, gallery, verdict, map, reset, pause, debug, save, footprints,
## wireframe, stochastic, cutoff_down, cutoff_up, zoom_in, zoom_out,
## debug_mode_0 … debug_mode_6.
signal action(name: String)
## The first non-repeat key of the run: the viewer starts audio here, because a
## browser refuses to play before a gesture.
signal first_input

const MOVE_LEFT := ["a", "arrowleft"]
const MOVE_RIGHT := ["d", "arrowright"]
const MOVE_UP := ["w", "arrowup"]
const MOVE_DOWN := ["s", "arrowdown"]

## Keys currently held, by the viewer's lowercase names.
var keys: Dictionary = {}
var debug_on: bool = false
var mode: String = "play"
## `camera.rotation_allowed !== false` in the manifest.
var yaw_allowed: bool = true
var started: bool = false

var _pending: Dictionary = {}
var _world: Variant = null
## True once a key has been handed to `press`/`release`, which means somebody is
## feeding this node and the keyboard must not be polled behind their back.
var _fed: bool = false

## The viewer's `event.key` names for the keys that are not a single character.
const SPECIAL := {
	KEY_SPACE: "space",
	KEY_ESCAPE: "escape",
	KEY_ENTER: "enter",
	KEY_KP_ENTER: "enter",
	KEY_UP: "arrowup",
	KEY_DOWN: "arrowdown",
	KEY_LEFT: "arrowleft",
	KEY_RIGHT: "arrowright",
	KEY_QUOTELEFT: "`",
	KEY_BRACKETLEFT: "[",
	KEY_BRACKETRIGHT: "]",
	KEY_MINUS: "-",
	KEY_EQUAL: "=",
	KEY_COMMA: ",",
	KEY_PERIOD: ".",
	KEY_SHIFT: "shift",
	KEY_TAB: "tab",
}


func setup(_pkg, world, _fu = null) -> void:
	bind(world)


## The world whose `craft_open` gates the menu keys; also the one `sample`
## writes by default.
func bind(world) -> void:
	_world = world
	if world != null:
		var camera: Dictionary = (world.manifest as Dictionary).get("camera", {})
		yaw_allowed = camera.get("rotation_allowed", true) != false


func set_mode(new_mode: String) -> void:
	mode = new_mode


func set_look(_look: String) -> void:
	pass


func handle_event(_event: Dictionary) -> void:
	pass


func status() -> Dictionary:
	return {"input": "%d held%s" % [keys.size(), ", debug" if debug_on else ""]}


func _input(event: InputEvent) -> void:
	var key := event as InputEventKey
	if key == null:
		return
	var name := key_name(key)
	if name == "":
		return
	if key.pressed:
		press(name, key.echo, key.shift_pressed)
	else:
		release(name)


func _notification(what: int) -> void:
	# `addEventListener('blur', () => keys.clear())` (:5294).
	if what == NOTIFICATION_APPLICATION_FOCUS_OUT or what == NOTIFICATION_WM_WINDOW_FOCUS_OUT:
		keys.clear()


## The viewer's `event.key.toLowerCase()`.
static func key_name(event: InputEventKey) -> String:
	var code := event.keycode
	if code == 0:
		code = event.physical_keycode
	if SPECIAL.has(code):
		return SPECIAL[code]
	if event.unicode > 0:
		return String.chr(event.unicode).to_lower()
	var text := OS.get_keycode_string(code)
	return text.to_lower() if text.length() == 1 else ""


## One key down, in the viewer's order.
func press(name: String, echo: bool = false, shift: bool = false) -> void:
	_fed = true
	if not echo and not started:
		started = true
		first_input.emit()
	if name == "b" and not echo:
		action.emit("music")
	keys[name] = true
	if name == "`":
		# The backtick returns immediately, so it does nothing else (:5233).
		debug_on = not debug_on
		action.emit("debug")
		return
	var craft_open := _craft_open()
	if name == "f" and not echo:
		_pending["light"] = true
	if name == "c" and not echo:
		_pending["craft_toggle"] = true
	if name == "escape" and craft_open:
		_pending["craft_toggle"] = true
	# The crafting table takes W/S and Enter while it is open; the loop zeroes
	# movement and the interact key for as long as it is.
	if craft_open:
		if MOVE_UP.has(name) and not echo:
			_pending["menu_move"] = -1
		if MOVE_DOWN.has(name) and not echo:
			_pending["menu_move"] = 1
		if (name == "enter" or name == "space") and not echo:
			_pending["menu_confirm"] = true
	if name == "x" and not echo and not shift:
		_pending["use"] = true
	if name == "z" and not echo:
		_pending["drop"] = true
	# The pack's slots: digits, or , and . to step. The digits are the ground
	# debug modes while the debug panel is up.
	if not debug_on:
		if name.length() == 1 and name >= "0" and name <= "9":
			_pending["select"] = 9 if name == "0" else int(name) - 1
		if name == ",":
			_pending["cycle"] = -1
		if name == ".":
			_pending["cycle"] = 1
	# One detent per press: auto-repeat is ignored, so a held key does not spin
	# the world at the operating system's repeat rate.
	if (name == "q" or name == "e") and yaw_allowed and mode != "verdict" and not echo:
		action.emit("yaw_right" if name == "e" else "yaw_left")
	if name == "g":
		action.emit("gallery")
	if name == "v":
		action.emit("verdict")
	if name == "p":
		action.emit("pause")
	if name == "m":
		action.emit("map")
	if name == "r":
		action.emit("reset")
	if name == "t" and not echo:
		action.emit("weather")
	if name == "l" and not echo:
		action.emit("strike")
	if name == "k" and not echo and not debug_on:
		action.emit("season")
	if name == "n":
		action.emit("night")
	if not debug_on:
		return
	if name.length() == 1 and name >= "0" and name <= "6":
		action.emit("debug_mode_%s" % name)
	if name == "x" and shift:
		action.emit("footprints")
	if name == "k":
		action.emit("wireframe")
	if name == "j":
		action.emit("stochastic")
	if name == "[":
		action.emit("cutoff_down")
	if name == "]":
		action.emit("cutoff_up")
	if name == "-":
		action.emit("zoom_in")
	if name == "=":
		action.emit("zoom_out")
	if name == "i":
		action.emit("save")


func release(name: String) -> void:
	_fed = true
	keys.erase(name)


func clear() -> void:
	keys.clear()
	_pending.clear()


func held(name: String) -> bool:
	return keys.has(name)


## The raw movement keys, for the gallery pan (:5479-5489).
func movement_axis(held_keys: Variant = null) -> Vector2:
	if held_keys == null and polling():
		var x := _pressed(KEY_D, KEY_RIGHT) - _pressed(KEY_A, KEY_LEFT)
		var z := _pressed(KEY_S, KEY_DOWN) - _pressed(KEY_W, KEY_UP)
		return Vector2(x, z)
	var set: Variant = held_keys if held_keys != null else keys
	var x := (1.0 if _any(set, MOVE_RIGHT) else 0.0) - (1.0 if _any(set, MOVE_LEFT) else 0.0)
	var z := (1.0 if _any(set, MOVE_DOWN) else 0.0) - (1.0 if _any(set, MOVE_UP) else 0.0)
	return Vector2(x, z)


## A frame owner may keep this node outside the scene tree (`main.gd` does), in
## which case no key event ever reaches `_input` and the held keys have to be
## polled off the keyboard instead. Everything else works the same either way.
## A caller that feeds keys itself (a test, a capture) takes the tracked set.
func polling() -> bool:
	return not is_inside_tree() and not _fed


func _pressed(physical: int, code: int) -> float:
	return 1.0 if (Input.is_physical_key_pressed(physical) or Input.is_key_pressed(code)) else 0.0


## Write `world.input` for one simulation substep: the held keys re-read, then
## every press since the last substep, which then lives for exactly that step.
##
## `held_keys` is normally left out (this node's own key set is used). A frame
## owner that keeps its own set may pass it; one that keeps its own key handling
## instead passes its current mode string, which is the form `main.gd` uses.
func sample(world, held_keys: Variant = null) -> void:
	if world == null:
		return
	_world = world
	var set: Variant = held_keys
	if held_keys is String:
		set_mode(held_keys)
		set = null
	var axis := movement_axis(set)
	# Verdict mode and the open craft panel hold the player still.
	var still: bool = mode == "verdict" or bool(world.craft_open)
	var input: Variant = world.input
	_write(input, "x", 0.0 if still else axis.x)
	_write(input, "z", 0.0 if still else axis.y)
	var interact: bool = _pressed(KEY_SPACE, KEY_SPACE) > 0.0 if (set == null and polling()) \
		else _any(set if set != null else keys, ["space"])
	_write(input, "interact", (not still) and interact)
	for key: String in _pending.keys():
		_write(input, key, _pending[key])
	_pending.clear()


func _craft_open() -> bool:
	if _world == null:
		return false
	return bool(_world.craft_open)


func _write(input: Variant, key: String, value: Variant) -> void:
	if input is Dictionary:
		(input as Dictionary)[key] = value
	elif input is Object:
		input.set(key, value)


func _any(set: Variant, names: Array) -> bool:
	if set is Dictionary:
		for name: String in names:
			if (set as Dictionary).has(name):
				return true
		return false
	if set is Array or set is PackedStringArray:
		for name: String in names:
			if set.has(name):
				return true
	return false
