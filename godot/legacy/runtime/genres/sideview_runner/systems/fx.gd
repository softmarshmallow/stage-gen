class_name RunnerFxSystem
extends RefCounted

## The moment that plays over a stopped world.
##
## A port of `web/lib/families/screen-fx/moment-system.ts`, which is one of the
## few pieces the browser wrote as a whole system rather than a binding — so it
## keeps its family id here.
##
## The ask is heard **one frame late** and deliberately so: `fx-requested` is
## consumed deferred, which is what lets this system be sealed *before* the
## director that asks. Declaring it as a same-frame consume would demand this
## run after the director, and the director waits on `fx-released` from here —
## a cycle the sealer would refuse. One frame of delay is the price of a roster
## that seals, and it is a declared price rather than a surprise.
##
## The elapsed time is measured on the **frame** clock. A moment stops the
## simulation clock; measuring itself against the clock it stopped would freeze
## the picture too.

static var view: Object = null


static func declaration() -> KernelSystem:
	return KernelSystem.of({
		"id": "fx/moment",
		"contract_version": "fx-moment-system-v2",
		"owns": ["fx"],
		"emits": ["fx-released", "fx-finished"],
		"consumes_deferred": ["fx-requested"],
		"after": ["runner/avatar"],
	})


static func update(world: RunnerWorld, step: Dictionary) -> void:
	if world.fx.is_empty():
		var asked: Array[Dictionary] = world.events.previous("fx-requested")
		if not asked.is_empty():
			var first: Dictionary = asked[0]
			world.fx = {
				"moment": String(first["moment"]),
				"choreography": String(first["choreography"]),
				"startedAt": null,
				"released": false,
			}
	if world.fx.is_empty():
		_hide()
		return
	if world.fx["startedAt"] == null:
		world.fx["startedAt"] = float(step["now"])
	var elapsed_ms := (float(step["now"]) - float(world.fx["startedAt"])) * 1000.0
	var choreography := FamilyCutIn.choreography(String(world.fx["choreography"]))
	if choreography.is_empty():
		return
	var frame := FamilyCutIn.frame(elapsed_ms, choreography)
	if frame.is_empty():
		return
	if view != null and view.has_method("sync"):
		view.call("sync", frame, String(world.fx["moment"]))
	if bool(frame["released"]) and not bool(world.fx["released"]):
		world.fx["released"] = true
		world.events.emit({"type": "fx-released", "moment": world.fx["moment"]})
	if bool(frame["finished"]):
		world.events.emit({"type": "fx-finished", "moment": world.fx["moment"]})
		world.fx = {}
		_hide()


## Ask for a moment. The director calls this rather than writing `fx` itself,
## because the slice has one owner and it is this system.
static func request(world: RunnerWorld, moment: String, choreography: String) -> void:
	world.events.emit(
		{"type": "fx-requested", "moment": moment, "choreography": choreography}
	)


static func _hide() -> void:
	if view != null and view.has_method("hide_moment"):
		view.call("hide_moment")
