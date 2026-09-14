extends SceneTree

const ACTOR = preload("res://addons/movie_sprite_actor/movie_sprite_actor.gd")
const CONTENT_IO = preload("res://addons/content_io/local_content.gd")
const FIXTURES = preload("res://examples/standalone/fixture_factory.gd")
var _failures: Array[String] = []
var _checks := 0
var _fixture := "/private/tmp/movie-sprite-actor-checks-" + str(Time.get_ticks_usec())


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	await _geometry_and_lifecycle(Vector2i(37, 61), 3, 7.5, Vector2i(3, 1), "single")
	await _geometry_and_lifecycle(Vector2i(129, 225), 11, 7.5, Vector2i(3, 2), "odd_partial")
	await _geometry_and_lifecycle(Vector2i(193, 257), 17, 13.25, Vector2i(2, 2), "five_pages")
	await _buffering_and_reconfiguration()
	await _refusals()
	await _callback_lifecycle()
	_remove_directory(_fixture)
	if _failures.is_empty(): print("PASS Movie Sprite Actor: %d assertions; variable geometry/timebase, paging, controls, integrity, refusal and lifecycle." % _checks)
	else:
		for failure: String in _failures: push_error(failure)
	quit(0 if _failures.is_empty() else 1)


func _geometry_and_lifecycle(canvas: Vector2i, count: int, fps: float, grid: Vector2i, name: String) -> void:
	var directory := _fixture.path_join(name)
	FIXTURES.create(directory, canvas, count, fps, grid)
	var loader := CONTENT_IO.new()
	_expect(loader.configure(directory, "files").is_empty(), name + ": loader configures.")
	var actor := ACTOR.new()
	root.add_child(actor)
	var ready := [0]
	actor.playback_ready.connect(func(): ready[0] += 1)
	_expect(actor.configure(loader, "manifest.json").is_empty(), name + ": actor configures.")
	_expect(actor.snapshot().state == "loading", name + ": first page loads asynchronously.")
	await _settle(actor)
	_expect(actor.snapshot().state == "ready" and ready[0] == 1, name + ": ready signal emitted once.")
	var sprite := actor.get_child(0) as Sprite2D
	_expect(sprite != null and sprite.region_rect.size == Vector2(canvas), name + ": source canvas controls geometry.")
	_expect(sprite.texture.get_size() == Vector2(canvas * grid), name + ": atlas dimensions match declared grid.")
	_expect(actor.set_eye_state("eyes_closed").is_empty(), name + ": authored eyes available.")
	_expect(actor.set_mouth_state("mouth_a").is_empty(), name + ": authored mouth available.")
	_expect(actor.snapshot().eyes == "eyes_closed", name + ": mouth preserves eye selection.")
	_expect(not actor.set_eye_state("unknown").is_empty() and actor.snapshot().eyes == "eyes_closed", name + ": unsupported state refuses without changing eyes.")
	_expect(actor.set_mouth_state("rest").is_empty() and actor.snapshot().mouth == "rest", name + ": mouth rest restores body pixels.")
	var duration := float(count) / fps
	for loop_index: int in [0, 1, 100]:
		_expect(actor.seek(loop_index * duration + (count - 0.25) / fps).is_empty(), name + ": seek accepts an arbitrary loop.")
		await _settle(actor)
		_expect(actor.snapshot().frame_index == count - 1 and actor.snapshot().loop_count == loop_index, name + ": padded final cells never play.")
		actor.advance(0.5 / fps)
		await _settle(actor)
		_expect(actor.snapshot().frame_index == 0 and actor.snapshot().loop_count == loop_index + 1, name + ": loop wraps at authored count.")
		_expect(actor.snapshot().resident_page_count <= 2, name + ": at most two body pages resident.")
	for index: int in range(count):
		actor.seek((float(index) + 0.1) / fps)
		var in_flight: Dictionary = actor.snapshot()
		_expect(in_flight.displayed_page < 0 or in_flight.displayed_page in in_flight.resident_pages, name + ": visible texture remains accounted for while seeking %d." % index)
		await _settle(actor)
		var cell := index % (grid.x * grid.y)
		_expect(actor.snapshot().frame_index == index and sprite.region_rect.position == Vector2(Vector2i(cell % grid.x, cell / grid.x) * canvas), name + ": frame/cell mapping %d." % index)
		_expect(actor.snapshot().resident_page_count <= 2, name + ": cache remains bounded during seek %d." % index)
	_expect(actor.snapshot().eyes == "eyes_closed", name + ": body playback never changes face direction.")
	actor.set_paused(true)
	var clock_before: float = actor.snapshot().clock_seconds
	for delta: float in [20.0, -1.0, INF, NAN]: actor.advance(delta)
	_expect(actor.snapshot().clock_seconds == clock_before, name + ": pause and invalid deltas accumulate no time.")
	_expect(not actor.seek(-1.0).is_empty() and not actor.seek(INF).is_empty(), name + ": invalid seeks refuse.")
	actor.set_paused(false)
	for delta: float in [-1.0, INF, NAN]: actor.advance(delta)
	_expect(actor.snapshot().clock_seconds == clock_before, name + ": invalid active deltas are ignored.")
	actor.shutdown()
	_expect(actor.snapshot().state == "closed" and not actor.snapshot().worker_active, name + ": shutdown joins workers.")
	_expect(actor.snapshot().resident_page_count == 0 and actor.get_child_count() == 0, name + ": shutdown releases textures and draw node.")
	_expect(not actor.set_eye_state("rest").is_empty() and not actor.seek(0.0).is_empty(), name + ": closed actor refuses controls requiring content.")
	actor.shutdown()
	actor.free()


func _buffering_and_reconfiguration() -> void:
	var directory := _fixture.path_join("lifecycle")
	FIXTURES.create(directory, Vector2i(65, 97), 30, 11.0, Vector2i(2, 2))
	var loader := CONTENT_IO.new()
	loader.configure(directory, "files")
	var actor := ACTOR.new()
	root.add_child(actor)
	actor.configure(loader, "manifest.json")
	actor.set_paused(true)
	await _settle(actor)
	_expect(actor.snapshot().state == "ready" and actor.snapshot().clock_seconds == 0.0, "Pause during first load reaches ready without clock catch-up.")
	actor.set_paused(false)
	actor.advance(19.5 / 11.0)
	_expect(actor.snapshot().state == "buffering" and actor.snapshot().pending_clock_seconds > 0.0, "Unresident large step queues its target frame.")
	_expect(actor.snapshot().displayed_page in actor.snapshot().resident_pages and actor.snapshot().resident_page_count <= 2, "A buffering actor keeps its displayed page inside the two-page budget.")
	actor.set_paused(true)
	_expect(actor.snapshot().pending_clock_seconds == -1.0, "Pause cancels a pending elapsed-time step.")
	await _settle(actor)
	_expect(actor.snapshot().clock_seconds == 0.0 and actor.snapshot().frame_index == 0, "A canceled pending step never advances after decode.")
	_expect(actor.seek(20.1 / 11.0).is_empty(), "Explicit seek works while paused.")
	await _settle(actor)
	_expect(actor.snapshot().frame_index == 20 and actor.snapshot().paused, "Paused seek selects requested source frame.")
	actor.set_eye_state("eyes_closed")
	actor.set_mouth_state("mouth_o")
	actor.seek(28.1 / 11.0)
	_expect(actor.configure(loader, "manifest.json").is_empty(), "Reconfiguration joins any in-flight page before replacing content.")
	await _settle(actor)
	_expect(actor.snapshot().frame_index == 0 and actor.snapshot().clock_seconds == 0.0 and actor.snapshot().eyes == "rest" and actor.snapshot().mouth == "rest" and not actor.snapshot().paused, "Reconfiguration resets body and face state.")
	# The actor snapshots content settings; changing a host loader cannot redirect its worker.
	loader.configure(_fixture.path_join("single"), "files")
	actor.seek(29.1 / 11.0)
	await _settle(actor)
	_expect(actor.snapshot().frame_index == 29 and actor.snapshot().state == "ready", "Host loader reconfiguration cannot redirect an active actor.")
	actor.seek(0.0)
	actor.free()
	_expect(true, "Freeing a loading actor completes without a worker leak.")


func _refusals() -> void:
	var directory := _fixture.path_join("refusals")
	var manifest: Dictionary = FIXTURES.create(directory, Vector2i(37, 61), 7, 7.5, Vector2i(2, 2))
	var loader := CONTENT_IO.new()
	loader.configure(directory, "files")
	var actor := ACTOR.new()
	root.add_child(actor)
	var cases := [
		["frame_size", [0, 61]], ["frame_size", [37.5, 61]], ["frame_size", [true, 61]], ["frame_size", [4097, 61]],
		["frame_count", 0], ["frame_count", 7.5], ["frame_count", true], ["frame_count", 1000001],
		["fps", 0], ["fps", true], ["fps", 241],
		["columns", 0], ["columns", 1.5], ["rows", true], ["rows", 10000],
		["schema_version", 9], ["patch_application", "alpha_over"], ["pages", []],
		["eyes", {"rest": manifest.eyes.eyes_closed}], ["mouths", {"MouthA": manifest.mouths.mouth_a}],
	]
	for index: int in range(cases.size()):
		var invalid := manifest.duplicate(true)
		invalid[cases[index][0]] = cases[index][1]
		FIXTURES.write_json(directory.path_join("invalid.json"), invalid)
		_expect(not actor.configure(loader, "invalid.json").is_empty(), "Invalid structural field is refused before playback: %s / %s." % [cases[index][0], cases[index][1]])
		_expect(actor.snapshot().state == "failed" and not actor.snapshot().worker_active, "Structural refusal starts no worker.")
	var invalid := manifest.duplicate(true)
	invalid.pages[0].file = "../escape.png"
	await _expect_bad_binding(actor, loader, directory, invalid, "Body traversal")
	invalid = manifest.duplicate(true)
	invalid.eyes.eyes_closed.file = "/etc/passwd"
	await _expect_bad_binding(actor, loader, directory, invalid, "Absolute face path")
	invalid = manifest.duplicate(true)
	invalid.mouths.mouth_a.sha256 = "0".repeat(64)
	await _expect_bad_binding(actor, loader, directory, invalid, "Face hash mismatch")
	invalid = manifest.duplicate(true)
	invalid.pages[0].sha256 = "0".repeat(64)
	FIXTURES.write_json(directory.path_join("invalid.json"), invalid)
	_expect(actor.configure(loader, "invalid.json").is_empty(), "Body hash validation runs in async decoder.")
	await _settle(actor)
	_expect(actor.snapshot().state == "failed" and actor.snapshot().resident_page_count == 0, "Corrupt body fails before texture upload.")
	invalid = manifest.duplicate(true)
	invalid.frame_size = [38, 61]
	await _expect_bad_binding(actor, loader, directory, invalid, "Declared/source face size mismatch")
	_expect(actor.configure(loader, "manifest.json").is_empty(), "A failed actor can be configured again with valid content.")
	await _settle(actor)
	_expect(actor.snapshot().state == "ready" and actor.snapshot().errors.is_empty(), "Recovery clears prior errors.")
	actor.free()


func _callback_lifecycle() -> void:
	var loader := CONTENT_IO.new()
	loader.configure(_fixture.path_join("single"), "files")
	var actor := ACTOR.new()
	root.add_child(actor)
	actor.playback_ready.connect(func(): actor.shutdown())
	actor.configure(loader, "manifest.json")
	await _settle(actor)
	_expect(actor.snapshot().state == "closed" and not actor.snapshot().worker_active, "Ready callback may shut down without starting another decode.")
	actor.free()
	actor = ACTOR.new()
	root.add_child(actor)
	var alternate := CONTENT_IO.new()
	alternate.configure(_fixture.path_join("five_pages"), "files")
	var ready_count := [0]
	actor.playback_ready.connect(func():
		ready_count[0] += 1
		if ready_count[0] == 1: actor.configure(alternate, "manifest.json")
	)
	actor.configure(loader, "manifest.json")
	await _settle(actor)
	_expect(ready_count[0] == 2 and actor.snapshot().state == "ready" and actor.snapshot().frame_size == Vector2i(193, 257), "Ready callback may replace content without old-session continuation.")
	actor.free()
	actor = ACTOR.new()
	root.add_child(actor)
	var broken := CONTENT_IO.new()
	broken.configure(_fixture.path_join("refusals"), "files")
	var invalid: Dictionary = broken.read_json("manifest.json").value
	invalid.pages[0].sha256 = "0".repeat(64)
	FIXTURES.write_json(_fixture.path_join("refusals/reentrant_failure.json"), invalid)
	var failures := [0]
	actor.failed.connect(func(_errors: Array[String]):
		failures[0] += 1
		actor.configure(loader, "manifest.json")
	)
	actor.configure(broken, "reentrant_failure.json")
	await _settle(actor)
	_expect(failures[0] == 1 and actor.snapshot().state == "ready" and actor.snapshot().frame_size == Vector2i(37, 61), "Failed callback may recover immediately without old-worker continuation.")
	var refused: Array[String] = actor.configure(loader, "absent.json")
	_expect(not refused.is_empty(), "Synchronous failure returns its original errors even when callback recovers.")
	await _settle(actor)
	_expect(failures[0] == 2 and actor.snapshot().state == "ready", "Synchronous recovery keeps its new content session.")
	actor.free()


func _expect_bad_binding(actor: Node2D, loader: RefCounted, directory: String, invalid: Dictionary, label: String) -> void:
	FIXTURES.write_json(directory.path_join("invalid.json"), invalid)
	var errors: Array[String] = actor.configure(loader, "invalid.json")
	if errors.is_empty(): await _settle(actor)
	_expect(actor.snapshot().state == "failed" and not actor.snapshot().errors.is_empty(), label + " refuses explicitly.")


func _settle(actor: Node2D) -> void:
	var deadline := Time.get_ticks_msec() + 10000
	while Time.get_ticks_msec() < deadline:
		actor.advance(0.0)
		if actor.snapshot().state in ["ready", "failed", "closed"]: return
		await create_timer(0.002).timeout
	_expect(false, "Async decode completed within deadline.")


func _remove_directory(directory: String) -> void:
	if not DirAccess.dir_exists_absolute(directory): return
	for file: String in DirAccess.get_files_at(directory): DirAccess.remove_absolute(directory.path_join(file))
	for child: String in DirAccess.get_directories_at(directory): _remove_directory(directory.path_join(child))
	DirAccess.remove_absolute(directory)


func _expect(condition: bool, message: String) -> void:
	_checks += 1
	if not condition: _failures.append(message)
