extends SceneTree

## Bounded blocking extends the concrete cast adapter and existing motion curve.
const STAGE = preload("res://games/bishoujo_afterlight/cast_stage.gd")
var _errors: Array[String] = []


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var stage_script: Script = STAGE
	if not stage_script.can_instantiate():
		printerr("FAIL Actor Blocking: cast adapter must compile.")
		quit(1)
		return
	_directions_and_hold()
	_clock_and_retarget()
	_composition_and_reset()
	_atomic_rejection()
	for issue: String in _errors:
		printerr("FAIL Actor Blocking: " + issue)
	if _errors.is_empty():
		print("PASS Actor Blocking: bidirectional approach, stationary target, explicit clock, exact hold, retarget, camera/manpu attachment, reset, and atomic rejection.")
	quit(0 if _errors.is_empty() else 1)


func _make():
	var stage = STAGE.new()
	root.add_child(stage)
	var pixels := Image.create(20, 30, false, Image.FORMAT_RGBA8)
	pixels.fill(Color.WHITE)
	var texture := ImageTexture.create_from_image(pixels)
	var profiles: Array = []
	var textures := {}
	for id: String in ["nami", "yuzu", "sena"]:
		profiles.append({"id": id, "eye_uv": [0.5, 0.14]})
		textures[id] = texture
	_expect(stage.initialize(profiles, textures).is_empty(), "Fixture must initialize.")
	stage.set_cast(["nami", "yuzu"])
	return stage


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)


func _x(stage, actor: String) -> float:
	return stage.get_actor_rect(actor).get_center().x


func _directions_and_hold() -> void:
	var stage = _make()
	for mover: String in ["nami", "yuzu"]:
		stage.set_cast(["nami", "yuzu"])
		var target := "yuzu" if mover == "nami" else "nami"
		var before := _x(stage, mover)
		var stationary := _x(stage, target)
		var top: float = stage.get_actor_rect(mover).position.y
		_expect(stage.approach_actor(mover, target).is_empty() and stage.is_busy(), "Either side must be able to approach.")
		stage.advance(0.16)
		_expect(absf(_x(stage, mover) - before) > 0.0 and absf(_x(stage, mover) - stationary) < absf(before - stationary), "Approach must move toward its target.")
		_expect(_x(stage, target) == stationary and stage.get_actor_rect(mover).position.y == top, "The target and vertical pose must stay in place.")
		stage.advance(10.0)
		_expect(absf(_x(stage, mover) - stationary) == 280.0 and not stage.is_busy(), "Approach must hold the exact requested gap.")
		var held: Dictionary = stage.movement_state()
		stage.advance(10.0)
		_expect(stage.movement_state() == held, "Completed movement must remain held without time drift.")
	stage.free()


func _clock_and_retarget() -> void:
	var whole = _make()
	var split = _make()
	for curve: String in ["linear", "ease_in_out", "spring"]:
		whole.set_cast(["nami", "yuzu"])
		split.set_cast(["nami", "yuzu"])
		whole.move_actor("nami", 700.0, {"duration_seconds": 1.0, "curve": curve})
		split.move_actor("nami", 700.0, {"duration_seconds": 1.0, "curve": curve})
		whole.advance(0.375)
		for index in 24:
			split.advance(0.015625)
		_expect(is_equal_approx(_x(whole, "nami"), _x(split, "nami")), "Equal elapsed time must preserve each existing motion curve.")
		var current := _x(whole, "nami")
		var frozen: Dictionary = whole.movement_state()
		whole.present(Transform2D.IDENTITY)
		whole.present(Transform2D.IDENTITY)
		whole.advance(NAN)
		whole.advance(-1.0)
		_expect(whole.movement_state() == frozen, "Rendering and invalid time must not advance movement.")
		whole.move_actor("nami", 350.0, {"duration_seconds": 0.2})
		_expect(_x(whole, "nami") == current, "A reversal must preserve the current sample.")
		whole.advance(0.2)
		_expect(_x(whole, "nami") == 350.0 and not whole.is_busy(), "Retargeted movement must reach its exact endpoint.")
	whole.move_actor("nami", 420.0, {"duration_seconds": 0.0})
	_expect(_x(whole, "nami") == 420.0 and not whole.is_busy(), "Zero duration must place immediately.")
	whole.free()
	split.free()


func _composition_and_reset() -> void:
	var stage = _make()
	stage.mark("nami", "surprise")
	stage.advance(1.0)
	var camera := Transform2D(Vector2(1.6, 0), Vector2(0, 1.6), Vector2(-240, -160))
	stage.present(camera)
	var actor_before: Rect2 = stage.get_presented_actor_rect("nami")
	var mark: TextureRect = stage._mark_nodes["nami:surprise"]
	var mark_before := Rect2(mark.position, mark.size)
	stage.move_actor("nami", 610.0)
	stage.advance(0.32)
	stage.present(camera)
	_expect(stage.get_presented_actor_rect("nami").position.is_equal_approx(actor_before.position + Vector2(320, 0)), "Camera must apply once to world movement.")
	_expect(mark.position.is_equal_approx(mark_before.position + Vector2(320, 0)) and mark.size == mark_before.size, "Persistent manpu must follow the posed actor through the camera.")
	stage.move_actor("nami", 650.0)
	stage.advance(0.1)
	var dismissed_x := _x(stage, "nami")
	_expect(stage.dismiss("nami").is_empty() and stage.movement_state().is_empty(), "Dismissal must cancel its mover.")
	stage.advance(0.1)
	_expect(_x(stage, "nami") == dismissed_x, "Dismissal must retain the interrupted base position.")
	stage.set_cast(["nami", "yuzu"])
	_expect(stage.movement_state().is_empty() and _x(stage, "nami") == 410.0 and not stage.is_busy(), "Scene placement must reset movement and restore the authored slots.")
	stage.free()


func _atomic_rejection() -> void:
	var stage = _make()
	stage.move_actor("nami", 610.0)
	stage.advance(0.1)
	var before: Dictionary = stage.movement_state()
	for settings: Dictionary in [{"unexpected": true}, {"duration_seconds": NAN}, {"duration_seconds": -1}, {"duration_seconds": 5.1}, {"curve": "other"}, {"frequency": 0.9}, {"damping_ratio": 1.1}]:
		_expect(not stage.move_actor("nami", 600.0, settings).is_empty() and stage.movement_state() == before, "Invalid movement settings must leave the active cue untouched.")
	for target: float in [NAN, INF, -1.0, 1281.0]:
		_expect(not stage.move_actor("nami", target).is_empty() and stage.movement_state() == before, "Invalid destination must be atomic.")
	_expect(not stage.move_actor("yuzu", 650.0).is_empty() and not stage.move_actor("sena", 650.0).is_empty() and stage.movement_state() == before, "Another mover or hidden actor must be rejected.")
	for gap: float in [-1.0, 0.0, 900.0, NAN]:
		_expect(not stage.approach_actor("nami", "yuzu", {"stop_distance": gap}).is_empty() and stage.movement_state() == before, "Invalid approach gaps must be atomic.")
	_expect(not stage.approach_actor("nami", "nami").is_empty(), "Approach cannot target its own actor.")
	_expect(not stage.handoff("nami", "yuzu", "sena").is_empty(), "A handoff must wait for active blocking.")
	stage.advance(1.0)
	_expect(not stage.handoff("nami", "yuzu", "sena").is_empty(), "Held custom positions must not bypass the fixed-slot handoff contract.")
	stage.set_cast(["nami", "yuzu"])
	stage.handoff("nami", "yuzu", "sena")
	_expect(not stage.move_actor("nami", 600.0).is_empty() and stage.movement_state().is_empty(), "Active handoff must reject independent blocking.")
	stage.set_cast(["nami", "yuzu"])
	stage.dismiss("nami")
	_expect(not stage.move_actor("nami", 600.0).is_empty() and not stage.approach_actor("yuzu", "nami").is_empty(), "Exiting actors cannot move or receive an approach.")
	stage.free()
