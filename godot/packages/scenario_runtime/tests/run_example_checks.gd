extends SceneTree

const PARTICLES = preload("res://addons/scenario_runtime/presentation/particle_adapter.gd")
var failures: Array[String] = []
var checks := 0
var _capture_root := ""


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	root.size = Vector2i(960, 640)
	var options := OS.get_cmdline_user_args()
	if options.size() == 2 and options[0] == "--capture":
		if DisplayServer.get_name() == "headless":
			push_error("Example captures require the native renderer.")
			quit(1)
			return
		_capture_root = options[1]
		DirAccess.make_dir_recursive_absolute(_capture_root)
	var schema: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://examples/capabilities.json"))
	_check(schema.particle == JSON.parse_string(JSON.stringify(PARTICLES.schema())), "compiler uses the installed particle parameter contract")
	for name: String in ["combat_dialogue", "world_bubbles", "catalog_effects"]:
		var scene: PackedScene = load("res://examples/" + name + "/main.tscn")
		var game: Control = scene.instantiate()
		root.add_child(game)
		await process_frame
		game.set_process(false)
		_check(game.errors.is_empty(), name + " creates a host without prepared media")
		_check(game.session_id.is_empty(), name + " world exists before invocation")
		game._process(1.0)
		_check(not game.session_id.is_empty() and game.errors.is_empty(), name + " invokes during host simulation")
		var before: float = game.combat_seconds
		var snapshot: Dictionary = game.host.snapshot(game.session_id)
		game.toggle_narrative()
		await _capture(name + "_entry")
		game._process(0.5)
		_check(game.combat_seconds > before and not paused, name + " combat keeps advancing while dialogue is suspended")
		_check(game.host.snapshot(game.session_id).state.clocks == snapshot.state.clocks, name + " suspension holds only narrative clocks")
		game.toggle_narrative()
		if name == "world_bubbles":
			game.surface.update_layout()
			var rect: Rect2 = game.surface.inspect().rect
			game._process(0.5)
			_check(game.surface.inspect().rect.position != rect.position, "playable 3D example follows actor motion")
		if name == "combat_dialogue":
			game._submit({"kind": "advance"})
			_check(game.host.view(game.session_id).kind == "choice", "host presents branching dialogue in combat")
			game._submit({"kind": "choose", "choice_id": "close"})
			_check(game.host.view(game.session_id).id == "near", "chosen line uses the same session")
			await _capture("combat_bubble")
		if name == "catalog_effects":
			game._process(1.0)
			_check(game._particles.inspect().size() == 2, "named and inline live particle instances coexist")
			await _capture("parallel_effects")
			game._submit({"kind": "advance"})
			_check(game._particles.inspect().size() == 1, "content stop addresses one live instance")
		_check(not game._checkpoints.is_empty(), name + " preview records validated visited states")
		var checkpoint: Dictionary = game._checkpoints[0]
		var restored: Dictionary = game.restore_checkpoint(checkpoint)
		var resumed: Dictionary = game.host.snapshot(game.session_id).state
		_check(not restored.has("error") and resumed.clocks == checkpoint.state.clocks and resumed.operations == checkpoint.state.operations and resumed.facts == checkpoint.state.facts and resumed.node_id == checkpoint.state.node_id, name + " checkpoint preview restores actual Session state")
		var clock_before: float = game.host.snapshot(game.session_id).state.clocks.sequence
		game.step_narrative()
		_check(is_equal_approx(game.host.snapshot(game.session_id).state.clocks.sequence - clock_before, 0.1) and game.host.view(game.session_id).status == "suspended", name + " time step advances exactly 0.1 seconds and holds only narrative")
		game.host.cancel(game.session_id, "test_cleanup")
		_check(game.host.leases().is_empty(), name + " releases its presentation channel")
		game.free()
	if failures.is_empty():
		print("scenario_examples: %d checks passed" % checks)
		quit(0)
	else:
		for failure: String in failures: push_error(failure)
		quit(1)


func _check(condition: bool, message: String) -> void:
	checks += 1
	if not condition: failures.append(message)


func _capture(name: String) -> void:
	if _capture_root.is_empty(): return
	await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	_check(image.save_png(_capture_root.path_join(name + ".png")) == OK, "native example capture: " + name)
