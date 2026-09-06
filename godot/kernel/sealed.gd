class_name KernelSealed
extends RefCounted

## A sealed roster: the derived order, and the tick that walks it.
##
## The order is data on purpose. A genre asserts it in one test, so a
## declaration edit that reorders a frame is a visible diff rather than a
## behaviour change nobody sees until a replay drifts.

## The derived tick order, by system id.
var order: PackedStringArray = PackedStringArray()

var _sequence: Array[KernelSystem] = []
## Sum microseconds per system id since `reset_profile`. Off unless `profile` is
## set: a `Time.get_ticks_usec()` pair around every system is cheap but not
## free, and only the smoke run asks for it.
var profile: bool = false
var system_micros: Dictionary = {}


static func of(order: PackedStringArray, sequence: Array[KernelSystem]) -> KernelSealed:
	var made := KernelSealed.new()
	made.order = order
	made._sequence = sequence
	return made


## One step, in sealed order. The caller writes the world's input first and the
## frame queue is the caller's to clear, because what clears it is a property of
## the world rather than of the roster.
func tick(world: Variant, step: Variant) -> void:
	if not profile:
		for system in _sequence:
			system.handler.call("update", world, step)
		return
	for system in _sequence:
		var started := Time.get_ticks_usec()
		system.handler.call("update", world, step)
		system_micros[system.id] = (
			int(system_micros.get(system.id, 0)) + (Time.get_ticks_usec() - started)
		)


## Forget whatever every system remembers between frames, in sealed order, with
## the world unguarded: a reset is not a tick, and the system that owns a
## lifecycle may rebuild the world that lifecycle covers. A system with nothing
## to forget declares no `reset` and is skipped.
func reset(world: Variant, scope: String) -> void:
	for system in _sequence:
		if system.handler.has_method("reset"):
			system.handler.call("reset", world, scope)


func reset_profile() -> void:
	system_micros.clear()


## The systems, in order, for a harness that wants more than the ids.
func systems() -> Array[KernelSystem]:
	return _sequence
