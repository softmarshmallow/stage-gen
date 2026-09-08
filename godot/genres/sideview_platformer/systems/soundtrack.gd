class_name PlatformerSoundtrackSystem
extends RefCounted

## When the music starts, and which track is on.
##
## A port of the state half of `web/lib/sideview-platformer/soundtrack.ts`. The
## family it belongs to is `cues`; what is here is the one rule that is this
## genre's — a run's music does not start until the player has actually pressed
## something.
##
## **Why a key and not the body's own movement.** The browser gates the first
## track on a real gesture, because a page may not open an audio context without
## one, and it hears that gesture as a `keydown`. A replay drives the body
## through an injected intent that never reaches the keyboard, so a run that
## walks for two seconds still has not "acted" — and the golden shows exactly
## that: `started` turns true on frame 60, the first press of `interact`, and not
## on frame 1 when the body starts walking. Reproduced rather than corrected. It
## is a browser's rule showing through, and a host that ignored it would part
## company with the reference on a field the reference publishes.

## The keys a player presses at the scene rather than through the body. Pressing
## any of them is the gesture.
const GESTURE_KEYS := ["interact", "enter", "up", "space", "jump"]


static func declaration() -> KernelSystem:
	return KernelSystem.of(
		{
			"id": "soundtrack/play",
			"contract_version": "soundtrack-system-v1",
			"reads": ["intent"],
			"owns": ["soundtrack"],
		}
	)


static func update(world: PlatformerWorld, _step: Dictionary) -> void:
	if bool(world.soundtrack.get("started", false)):
		return
	var queued: Variant = world.soundtrack.get("next_track_id")
	if not (queued is String):
		return
	for key: Variant in GESTURE_KEYS:
		if not bool(world.intent.get(String(key), false)):
			continue
		world.soundtrack = {
			"current_track_id": queued,
			"next_track_id": null,
			"started": true,
		}
		return
