class_name KernelEventQueue
extends RefCounted

## The frame queue: what one system tells the others happened.
##
## Slices carry *state* — the value of a slice at the moment a reader looks at
## it. They cannot carry an *occurrence*. A system that needs to know "a hazard
## was struck this frame", not "a hazard is overlapping now", otherwise has two
## options, and both are already in this repository's history: widen a slice
## into a per-frame flag every consumer must remember to clear, or keep a
## private shadow of last frame's state and rediscover the edge by comparing.
## The browser runner's audio kept five such shadows and had to special-case a
## restart, because a shadow cannot tell a rewind from an event.
##
## So: one queue per frame, cleared at the top of the tick, appended to in
## sealed order, readable by anything ordered after the emitter. The queue holds
## no subscriptions and dispatches nothing — a consumer asks for what it cares
## about when its own update runs, which keeps the whole thing inside the
## deterministic tick rather than beside it.
##
## An event is a Dictionary with a `type` and scalars: ids and numbers, never
## object references, so an event means the same thing to a replay as to a
## frame. It is frozen on the way in — recursively, because a shallow freeze
## leaves a nested payload a view could still write.

var _this_frame: Array[Dictionary] = []
var _last_frame: Array[Dictionary] = []


## Append one occurrence to this frame. The type is `<family>/<verb>`.
func emit(event: Dictionary) -> void:
	_this_frame.append(_frozen(event))


## Start a frame: this frame's occurrences become last frame's.
func begin_frame() -> void:
	_last_frame = _this_frame
	_this_frame = []


## Throw both frames away. What a composition reset calls: a restart is not a
## frame boundary — the run those occurrences described no longer exists — so
## they must not survive as a deferred consumer's history.
func discard_frames() -> void:
	_this_frame = []
	_last_frame = []


## Every event of `type` emitted so far this frame, in emission order.
func of_type(type: String) -> Array[Dictionary]:
	return _matching(_this_frame, type)


## Every event of `type` from the frame before this one.
##
## The other end of `consumes_deferred`: a system sealed before an emitter
## cannot hear it this frame at any price, because the emitter has not run. It
## hears it one frame later, which is a declared delay rather than a private
## shadow of somebody else's state.
func previous(type: String) -> Array[Dictionary]:
	return _matching(_last_frame, type)


## Everything emitted this frame, for a view mirroring after the tick.
func frame() -> Array[Dictionary]:
	return _this_frame


func is_empty() -> bool:
	return _this_frame.is_empty()


static func _matching(frame: Array[Dictionary], type: String) -> Array[Dictionary]:
	var found: Array[Dictionary] = []
	for event in frame:
		if String(event.get("type", "")) == type:
			found.append(event)
	return found


## Freeze recursively. `Dictionary.make_read_only` is shallow, so a nested
## payload would stay writable and a view could still mutate what it was handed.
static func _frozen(value: Dictionary) -> Dictionary:
	for key: Variant in value:
		var entry: Variant = value[key]
		if entry is Dictionary:
			_frozen(entry as Dictionary)
		elif entry is Array:
			_frozen_array(entry as Array)
	value.make_read_only()
	return value


static func _frozen_array(value: Array) -> void:
	for entry: Variant in value:
		if entry is Dictionary:
			_frozen(entry as Dictionary)
		elif entry is Array:
			_frozen_array(entry as Array)
	value.make_read_only()
