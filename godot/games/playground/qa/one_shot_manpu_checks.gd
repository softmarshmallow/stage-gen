extends SceneTree

## Renderer-independent proof for finite Manpu events alongside persistent cues.
const MANPU = preload("res://addons/game_presentation/actors/manpu_animation.gd")
const CATALOG := "res://addons/game_presentation/actors/presets/manpu.json"
var _errors: Array[String] = []


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_check_event_lifecycle()
	_check_pool_separation()
	_check_atomic_validation()
	_check_frame_partitions()
	_check_persistent_sigh()
	_check_falling_sweat()
	for issue: String in _errors:
		printerr("FAIL One-Shot Manpu: " + issue)
	if _errors.is_empty():
		print("PASS One-Shot Manpu: independent duplicate events, finite expiry, signed movement/growth/fade, frame partitions, frozen sampling, immutable snapshots, atomic emission, targeted cancellation, stable handles, persistent-cue separation and falling-sweat preset composition")
	quit(0 if _errors.is_empty() else 1)


func _new() -> MANPU:
	var controller: MANPU = MANPU.new()
	_expect(controller.initialize(CATALOG).is_empty(), "The prepared Manpu catalog must initialize.")
	return controller


func _emit(controller: MANPU, actor: String = "world_actor", id: String = "sigh") -> int:
	var result: Dictionary = controller.emit_one_shot(actor, id, "sigh_puff")
	_expect(result["errors"].is_empty() and int(result["instance_id"]) > 0, "A valid one-shot event must create a positive instance handle.")
	return int(result["instance_id"])


func _check_event_lifecycle() -> void:
	var controller := _new()
	var first := _emit(controller)
	var first_sample: Dictionary = controller.one_shots()[0]["sample"]
	_expect(is_zero_approx(float(first_sample["opacity"])) and float(first_sample["scale"]) < 1.0, "A Sigh Puff must begin small with a brief appearance envelope.")
	controller.advance(0.2)
	first_sample = controller.one_shots()[0]["sample"]
	_expect(float(first_sample["offset_x_ratio"]) > 0 and float(first_sample["offset_y_ratio"]) < 0, "A live Sigh Puff must move outward and upward in mark-height units.")
	_expect(float(first_sample["scale"]) >= 1.0 and float(first_sample["opacity"]) > 0.8, "The puff must become readable quickly while its motion continues.")
	var second := _emit(controller)
	var entries := controller.one_shots()
	_expect(first != second and entries.size() == 2, "Repeated actor/id events must coexist under distinct handles.")
	_expect(entries[0]["instance_id"] == first and entries[1]["instance_id"] == second, "Live events must retain emission order.")
	_expect(float(entries[0]["sample"]["offset_x_ratio"]) > 0 and is_zero_approx(float(entries[1]["sample"]["offset_x_ratio"])), "The duplicate event must begin at its own zero-time sample.")
	controller.advance(0.45)
	entries = controller.one_shots()
	_expect(entries.size() == 1 and entries[0]["instance_id"] == second, "The earlier event must expire without shortening its overlapping duplicate.")
	_expect(float(entries[0]["sample"]["opacity"]) > 0 and float(entries[0]["sample"]["opacity"]) < 0.8, "The surviving puff must fade during its own final movement.")
	controller.advance(0.2)
	_expect(controller.one_shots().is_empty(), "The second event must disappear at its own finite duration.")
	controller.sync([{"actor": "world_actor", "id": "sigh"}])
	controller.replay()
	controller.configure("shake")
	for redraw in 5:
		controller.one_shots()
		controller.sample("world_actor", "sigh")
	_expect(controller.one_shots().is_empty(), "Sync, replay, preset changes and sampling must never respawn an expired event.")
	var third := _emit(controller)
	_expect(third > second, "Later explicit events must receive fresh handles.")
	controller.advance(1000.0)
	_expect(controller.one_shots().is_empty(), "A large delta must expire the event in one call.")


func _check_pool_separation() -> void:
	var controller := _new()
	controller.configure("shake")
	controller.sync([{"actor": "guard", "id": "surprise"}])
	controller.advance(0.08)
	var persistent: Dictionary = controller.get_state()["states"].duplicate(true)
	var first := _emit(controller, "guard")
	_expect(controller.get_state()["states"] == persistent, "Event emission must not restart the actor's persistent mark.")
	controller.advance(0.09)
	var events := controller.one_shots()
	var persistent_sample: Dictionary = controller.sample("guard", "surprise")
	controller.configure("scale_pulse")
	_expect(controller.one_shots() == events, "Persistent preset changes must leave live event snapshots unchanged.")
	_expect(controller.sample("guard", "surprise") == persistent_sample, "Persistent retargeting must retain its existing continuity contract.")
	controller.sync([{"actor": "guard", "id": "surprise"}, {"actor": "visitor", "id": "heart"}])
	controller.replay("guard", "surprise")
	controller.replay()
	_expect(controller.one_shots() == events, "Persistent synchronization and both replay forms must not retime live events.")
	controller.sync([])
	_expect(controller.get_state()["states"].is_empty() and controller.one_shots() == events, "Removing the persistent cue set must leave transient events alive.")
	var second := _emit(controller, "visitor")
	controller.sync([{"actor": "guard", "id": "sigh"}], false)
	persistent = controller.get_state()["states"].duplicate(true)
	controller.cancel_one_shots("guard")
	_expect(controller.one_shots().size() == 1 and controller.one_shots()[0]["instance_id"] == second, "Targeted cancellation must remove only the named actor's events.")
	_expect(controller.get_state()["states"] == persistent, "Targeted cancellation must leave persistent sighs intact.")
	var snapshot := controller.get_state()
	controller.cancel_one_shots("unknown_actor")
	_expect(controller.get_state() == snapshot, "Cancelling an absent actor must be a no-op.")
	controller.cancel_one_shots()
	_expect(controller.one_shots().is_empty() and controller.get_state()["states"] == persistent, "Cancelling every event must still preserve persistent cues.")
	var third := _emit(controller)
	controller.clear()
	_expect(controller.one_shots().is_empty() and controller.get_state()["states"].is_empty(), "Clear must cancel both pools.")
	var fourth := _emit(controller)
	_expect(first < second and second < third and third < fourth, "Clearing events must not reuse stale renderer handles.")
	controller.initialize(CATALOG)
	var fifth := _emit(controller)
	_expect(fifth > fourth, "Successful reinitialization must also avoid reusing handles.")


func _check_atomic_validation() -> void:
	var uninitialized: MANPU = MANPU.new()
	var before := uninitialized.get_state()
	var rejected: Dictionary = uninitialized.emit_one_shot("actor", "sigh", "sigh_puff")
	_expect(not rejected["errors"].is_empty() and rejected["instance_id"] == -1 and uninitialized.get_state() == before, "Uninitialized emission must fail without changing state.")
	var controller := _new()
	_emit(controller)
	controller.advance(0.11)
	before = controller.get_state()
	for arguments: Array in [["", "sigh", "sigh_puff"], ["Actor", "sigh", "sigh_puff"], ["actor", "bad:id", "sigh_puff"], ["actor", "sigh", "missing"], ["actor", "sigh", "none"], ["actor", "sigh", "shake"], ["actor", "sigh", "fade_in"]]:
		rejected = controller.emit_one_shot(arguments[0], arguments[1], arguments[2])
		_expect(not rejected["errors"].is_empty() and rejected["instance_id"] == -1, "Invalid identifiers, missing presets, zero duration and nonzero ending alpha must be refused.")
		_expect(controller.get_state() == before, "Rejected events must preserve both pools and the next instance handle.")
	for delta: float in [0.0, -1.0, INF, NAN]:
		controller.advance(delta)
	_expect(controller.get_state() == before, "Invalid deltas must not advance or expire events.")
	for redraw in 10:
		var returned := controller.one_shots()
		returned[0]["actor"] = "changed"
		returned[0]["sample"]["opacity"] = 0.0
		var state := controller.get_state()
		var instance_id: int = state["one_shots"].keys()[0]
		state["one_shots"][instance_id]["elapsed"] = 100.0
		state["one_shots"][instance_id]["tracks"]["offset_x_ratio"][1][1] = -999.0
	_expect(controller.get_state() == before, "Sampling, frozen redraw and mutation of returned data must not affect event clocks or snapshotted tracks.")
	_expect(not controller.initialize("res://missing_manpu_catalog.json").is_empty() and controller.get_state() == before, "Failed reinitialization must preserve live events and handles.")
	# Actor and art existence are intentionally resolved by each renderer host.
	var arbitrary := controller.emit_one_shot("billboard_actor", "custom_world_mark", "sigh_puff")
	_expect(arbitrary["errors"].is_empty(), "The controller must accept valid identifiers without assuming a VN cast or art set.")


func _check_frame_partitions() -> void:
	for time: float in [0.13, 0.4, 0.649, 0.65, 1.2]:
		var once := _new()
		var partitioned := _new()
		_emit(once)
		_emit(partitioned)
		once.advance(time)
		for frame in 30:
			partitioned.advance(time / 30.0)
		var left := once.one_shots()
		var right := partitioned.one_shots()
		_expect(left.size() == right.size(), "Event expiry must be independent of frame partitioning.")
		if left.size() == 1 and right.size() == 1:
			for channel: String in left[0]["sample"]:
				_expect(is_equal_approx(float(left[0]["sample"][channel]), float(right[0]["sample"][channel])), "Every movement/appearance channel must match across frame partitions.")


func _check_persistent_sigh() -> void:
	var controller := _new()
	controller.configure("none")
	controller.sync([{"actor": "guard", "id": "sigh"}])
	controller.advance(100.0)
	_expect(is_equal_approx(float(controller.sample("guard", "sigh")["opacity"]), 1.0), "The sigh raster must remain usable as a persistent static mark.")
	controller.configure("shake")
	controller.replay("guard", "sigh")
	controller.advance(0.36 * 0.12)
	_expect(is_equal_approx(float(controller.sample("guard", "sigh")["offset_y_ratio"]), -0.08), "The same persistent sigh must retain the existing shake behavior.")
	controller.advance(3.0)
	_expect(is_equal_approx(float(controller.sample("guard", "sigh")["opacity"]), 1.0), "Persistent shaking must settle visibly instead of expiring.")
	controller.configure("sigh_puff")
	controller.replay("guard", "sigh")
	controller.advance(1.0)
	_expect(controller.get_state()["states"].has("guard:sigh") and is_zero_approx(float(controller.sample("guard", "sigh")["opacity"])), "A persistent sigh_puff cue must hold its invisible ending until explicitly removed or replayed.")
	_expect(controller.one_shots().is_empty(), "Selecting the finite preset for a persistent cue must not implicitly emit an event.")


func _check_falling_sweat() -> void:
	var controller := _new()
	controller.sync([{"actor": "guard", "id": "surprise", "preset": "step_loop"}])
	var sweat: Dictionary = controller.emit_one_shot("guard", "sweat_drop", "sweat_drop_fall")
	_expect(sweat["errors"].is_empty(), "Falling Sweat Drop must use the existing finite-event API.")
	if not sweat["errors"].is_empty(): return
	var first: Dictionary = controller.one_shots()[0]["sample"]
	_expect(is_zero_approx(float(first["opacity"])) and is_equal_approx(float(first["scale"]), 0.65), "The falling drop must enter from a small invisible sample.")
	_emit(controller, "guard", "sigh_puff")
	controller.advance(0.3)
	var entries: Array = controller.one_shots()
	_expect(entries.size() == 2 and entries[0]["id"] == "sweat_drop" and entries[1]["id"] == "sigh_puff", "Both supplied raster identities must retain independent event handles.")
	var falling: Dictionary = entries[0]["sample"]
	_expect(is_zero_approx(float(falling["offset_x_ratio"])) and float(falling["offset_y_ratio"]) > 0.0 and float(falling["opacity"]) > 0.0, "The drop must fall downward without lateral drift while visible.")
	_expect(float(entries[1]["sample"]["offset_y_ratio"]) < 0.0, "The simultaneous Sigh Puff must retain its independent upward drift.")
	controller.advance(0.35)
	entries = controller.one_shots()
	_expect(entries.size() == 1 and entries[0]["instance_id"] == sweat["instance_id"], "The 0.65-second puff must expire before the 0.75-second falling drop.")
	controller.advance(0.1)
	_expect(controller.one_shots().is_empty() and controller.get_state()["states"].has("guard:surprise"), "Drop expiry must retain the persistent loop and must not respawn either event.")


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)
