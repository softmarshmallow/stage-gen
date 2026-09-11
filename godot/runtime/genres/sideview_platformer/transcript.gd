class_name PlatformerTranscript
extends RefCounted

## What the runtime named this frame, in the shape the golden hashes.
##
## A port of `recordEvent` in `web/lib/sideview-platformer/prepared-scene.ts`.
## The four fields are load bearing: the kind, the frame it happened on, the
## simulation clock rounded to whole milliseconds, and a payload that is `null`
## rather than an empty record when there is nothing to say. A digest compares
## them field for field, so an event that carried its payload at the top level
## would differ on every line while describing exactly the same thing.
##
## The clock is rounded rather than truncated because the browser's is, and at
## 1/30 the two disagree on two frames in three.

## What one frame may name before the record stops growing. A pathological frame
## cannot make one entry of the golden unbounded.
const FRAME_LIMIT := 64


## Record one occurrence, or drop it because the frame is already full.
static func record(
	world: PlatformerWorld, kind: String, frame: int, now_ms: float, data: Variant = null
) -> void:
	if world.events.frame().size() >= FRAME_LIMIT:
		return
	world.events.emit(
		{
			"kind": kind,
			"frame": frame,
			"simulationMs": int(round(now_ms)),
			"data": data,
		}
	)


## Every occurrence of one kind this frame.
##
## The kernel's queue matches on `type`; this genre's records carry `kind`,
## because that is the word the golden hashes and a record that carried both
## would differ from the browser on every line. So the channel is the kernel's
## and the vocabulary is this genre's, and reading it goes through here rather
## than through `of_type`, which would silently find nothing.
static func of_kind(world: PlatformerWorld, kind: String) -> Array:
	var found: Array = []
	for entry: Variant in world.events.frame():
		var event: Dictionary = entry
		if String(event.get("kind", "")) == kind:
			found.append(event)
	return found
