extends SceneTree

const SURFACE = preload("res://addons/scenario_runtime/presentation/dialogue_surface.gd")
const ANCHOR = preload("res://addons/scenario_runtime/bindings/anchor.gd")
var checks := 0
var failures: Array[String] = []


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	root.size = Vector2i(960, 640)
	var surface := SURFACE.new()
	root.add_child(surface)
	await process_frame
	_check(surface.configure({"left": {"portrait": "left"}, "right": {"portrait": "right"}, "bubble": {"layout": "bubble"}, "narrator": {"layout": "narration"}}).is_empty(), "profiles admitted")
	surface.speakers = {"pilot": {"name": "Pilot", "portraits": {"happy": "smile"}, "anchor": "pilot_anchor"}}
	var image := Image.create(8, 8, false, Image.FORMAT_RGBA8)
	image.fill(Color.CORAL)
	surface.portraits = {"smile": ImageTexture.create_from_image(image)}
	var line := {"id": "hello", "kind": "line", "text": "The host still owns the world.", "speaker": "pilot", "expression": "happy", "presentation": {"profile": "bottom"}}
	_check(surface.present(line).is_empty(), "ordinary dialogue needs no actor or portrait")
	var plain: Dictionary = surface.inspect()
	_check(plain.visible and plain.speaker == "Pilot" and not plain.portrait_visible, "default is bottom with optional name and no portrait")
	line.presentation.profile = "left"
	_check(surface.present(line).is_empty(), "portrait works without a staged actor")
	var left: Dictionary = surface.inspect()
	_check(left.portrait_visible and left.text_rect.position.x > plain.text_rect.position.x, "left portrait reserves a column")
	line.presentation.profile = "right"
	surface.present(line)
	var right: Dictionary = surface.inspect()
	_check(right.portrait_visible and right.text_rect.position.x == plain.text_rect.position.x, "right portrait keeps text on the left")
	line.expression = "unpictured"
	surface.present(line)
	_check(not surface.inspect().portrait_visible and surface.inspect().text_rect.size.x == plain.text_rect.size.x, "intentionally absent portrait reflows text")
	line.presentation.portrait = "missing"
	_check(not surface.present(line).is_empty(), "missing required art differs from no portrait")
	line.presentation.erase("portrait")
	line.presentation.profile = "narrator"
	line.speaker = ""
	surface.present(line)
	_check(surface.inspect().speaker == "" and surface.inspect().rect.position.y < plain.rect.position.y, "narration has no mandatory speaker")
	_check(not surface.configure({"bad": {"layout": "tree_editor"}}).is_empty(), "unsupported layouts are refused")
	_check(surface.profiles.has("bubble"), "profile refusal preserves previous configuration")
	var actor := Node2D.new()
	root.add_child(actor)
	actor.position = Vector2(300, 420)
	_check(ANCHOR.sample({"type": "world_2d", "node": actor, "offset": [1, 2]}, root).has("error"), "2D anchor rejects unconverted data offsets before arithmetic")
	_check(ANCHOR.sample({"type": "world_3d", "node": actor, "offset": Vector3(INF, 0, 0)}, root).has("error"), "3D anchor refuses nonfinite offsets before projection")
	_check(ANCHOR.sample({"type": "world_2d", "node": 42, "lost": "restart_game"}, root).has("error"), "invalid lost policy is refused even for absent actors")
	surface.anchors = {"pilot_anchor": {"type": "world_2d", "node": actor, "offset": Vector2(0, -10), "offscreen": "clamp"}}
	line.speaker = "pilot"
	line.presentation.profile = "bubble"
	surface.present(line)
	var before: Rect2 = surface.inspect().rect
	var compact := {"layout": "bubble", "width": 400.0, "height": 100.0}
	surface.configure({"bubble": compact})
	var long_line := line.duplicate(true)
	long_line.text = "I am a 3D character in the game's world. My bubble follows its camera."
	surface.present(long_line)
	_check(surface.inspect().rect.size.y > 150.0 and surface.inspect().text_rect.size.y >= 90.0, "wrapped bubble text grows its panel instead of escaping the background")
	surface.configure({"bubble": {"layout": "bubble"}})
	surface.present(line)
	actor.position.x += 100
	surface.update_layout()
	_check(is_equal_approx(surface.inspect().rect.position.x - before.position.x, 100.0), "bubble follows live 2D actor motion")
	actor.position.x = 3000
	surface.update_layout()
	_check(surface.visible and surface.inspect().rect.end.x <= root.size.x, "clamp policy preserves visible dialogue")
	surface.anchors.pilot_anchor.offscreen = "hide"
	surface.update_layout()
	_check(not surface.visible, "offscreen hide policy")
	actor.free()
	surface.update_layout()
	_check(not surface.visible, "lost actor does not crash or bind another object")
	var actor3 := Node3D.new()
	var camera := Camera3D.new()
	root.add_child(actor3)
	root.add_child(camera)
	camera.position = Vector3(0, 0, 5)
	camera.current = true
	await process_frame
	var binding := {"type": "world_3d", "node": actor3, "offscreen": "clamp"}
	var projected := ANCHOR.sample(binding, root)
	_check(projected.get("visible", false), "world_3d projection uses active host camera")
	actor3.position.x = 1
	var moved := ANCHOR.sample(binding, root)
	_check(moved.position.x > projected.position.x, "moving 3D actor changes projected anchor")
	var camera2 := Camera3D.new()
	root.add_child(camera2)
	camera2.position = Vector3(1, 0, 5)
	camera2.current = true
	await process_frame
	var switched := ANCHOR.sample(binding, root)
	_check(switched.position.x < moved.position.x, "bubble follows camera switch without claiming it")
	actor3.position.z = 10
	_check(not ANCHOR.sample(binding, root).visible, "behind-camera actor is hidden before projection")
	_check(root.get_camera_3d() == camera2 and not paused, "presentation leaves camera and simulation authority with host")
	actor3.free()
	camera.free()
	camera2.free()
	surface.free()
	if failures.is_empty():
		print("scenario_embedding: %d checks passed" % checks)
		quit(0)
	else:
		for failure: String in failures: push_error(failure)
		quit(1)


func _check(condition: bool, message: String) -> void:
	checks += 1
	if not condition: failures.append(message)
