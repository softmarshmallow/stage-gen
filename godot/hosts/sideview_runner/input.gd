class_name RunnerInput
extends RefCounted

## Keyboard and pointer, written into the simulation's latch.
##
## A port of the two `attach*IntentSource` functions in
## `web/lib/sideview-runner/intent.ts`.
##
## The distinction the latch draws is the one this file has to respect, and
## getting it wrong is a defect that has already shipped once in this repository:
## a panel button that latched its key as *held* stopped the keyboard being
## polled for the rest of the run. So a jump and a restart are **requested**
## (one edge, spent by the sample that reports it) and a duck and a thrust are
## **set** (a level, true while the key is down). A key that arrives as a repeat
## is dropped, because a held key is already a level and must not re-fire an
## edge.
##
## Jump and thrust share a key on purpose: the same press is a jump while
## running and a climb while flying, and which one it means is the locomotion's
## business rather than the keyboard's.

## Below this fraction of the window's height, a touch is a duck rather than a
## jump.
const POINTER_DUCK_ZONE_START := 0.68

var _latch: FamilyIntent = null
var _duck_pointers: Dictionary = {}
var _thrust_pointers: Dictionary = {}


static func of(latch: FamilyIntent) -> RunnerInput:
	var made := RunnerInput.new()
	made._latch = latch
	return made


## One input event from the host's `_input`. Returns whether it was consumed.
func handle(event: InputEvent, viewport_height: float) -> bool:
	if event is InputEventKey:
		return _key(event as InputEventKey)
	if event is InputEventScreenTouch:
		return _touch(event as InputEventScreenTouch, viewport_height)
	if event is InputEventMouseButton:
		return _mouse(event as InputEventMouseButton, viewport_height)
	return false


## Let go of everything. What a host calls when it loses focus, so a key held
## through an alt-tab is not still held when the window comes back.
func release_all() -> void:
	_duck_pointers.clear()
	_thrust_pointers.clear()
	_latch.set_level("duck", false)
	_latch.set_level("thrust", false)


func _key(event: InputEventKey) -> bool:
	if event.echo:
		return false
	var pressed := event.pressed
	match event.keycode:
		KEY_SPACE, KEY_UP, KEY_W:
			if pressed:
				_latch.request("jump")
			_latch.set_level("thrust", pressed)
			return true
		KEY_DOWN, KEY_S:
			_latch.set_level("duck", pressed)
			return true
		KEY_R:
			if pressed:
				_latch.request("action")
			return true
	return false


func _touch(event: InputEventScreenTouch, viewport_height: float) -> bool:
	return _zone(event.index, event.pressed, event.position.y, viewport_height)


func _mouse(event: InputEventMouseButton, viewport_height: float) -> bool:
	if event.button_index != MOUSE_BUTTON_LEFT:
		return false
	return _zone(-1, event.pressed, event.position.y, viewport_height)


## The screen is two zones: the upper two thirds jump, the foot ducks. Several
## fingers may be down at once, so each zone counts its own and the level only
## drops when the last one lifts.
func _zone(pointer: int, pressed: bool, y: float, viewport_height: float) -> bool:
	var boundary := viewport_height * POINTER_DUCK_ZONE_START
	if pressed:
		if y < boundary:
			_thrust_pointers[pointer] = true
			_latch.request("jump")
		else:
			_duck_pointers[pointer] = true
	else:
		_thrust_pointers.erase(pointer)
		_duck_pointers.erase(pointer)
	_latch.set_level("duck", not _duck_pointers.is_empty())
	_latch.set_level("thrust", not _thrust_pointers.is_empty())
	return true
