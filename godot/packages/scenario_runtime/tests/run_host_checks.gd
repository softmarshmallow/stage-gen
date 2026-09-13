extends SceneTree

const HOST = preload("res://addons/scenario_runtime/bindings/host.gd")
const PARTICLE = preload("res://addons/scenario_runtime/presentation/particle_adapter.gd")
const CATALOG = preload("res://addons/scenario_runtime/program/catalog.gd")
var checks := 0
var failures: Array[String] = []


class AuditAdapter extends RefCounted:
	var running: Dictionary = {}
	var finished: Array[String] = []
	var suspended: Dictionary = {}

	func start(event: Dictionary, _bindings: Dictionary) -> Dictionary:
		running[event.operation_id] = true
		return {"status": "running"}

	func restore(event: Dictionary, bindings: Dictionary, _elapsed: float) -> Dictionary:
		return start(event, bindings)

	func advance(_id: String, _delta: float) -> Dictionary:
		return {"status": "running"}

	func cancel(id: String) -> void:
		running.erase(id)

	func finish(id: String) -> Dictionary:
		finished.append(id)
		return {"status": "completed"}

	func suspend(id: String, value: bool) -> void:
		suspended[id] = value


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var canvas := Control.new()
	root.add_child(canvas)
	var unrelated := Node.new()
	canvas.add_child(unrelated)
	var pixels := Image.create(4, 4, false, Image.FORMAT_RGBA8)
	pixels.fill(Color.ORANGE)
	var bindings := {"air": canvas, "ember_sprite": [ImageTexture.create_from_image(pixels)]}
	var adapter := PARTICLE.new()
	var host := HOST.new()
	_check(not host.register_capability("particle", PARTICLE.schema(), adapter).has("error"), "installed typed particle adapter")
	var catalog := {"kind": "scenario-catalog", "schema_version": 1, "catalog_id": "weather", "revision": "1", "definitions": {"ember": {"type": "particle", "parameters": {"sprite": "ember_sprite"}, "overrides": ["rate"]}}}
	var admitted := CATALOG.parse(catalog, host.installed_types())
	_check(CATALOG.resolve({"preset": "ember", "parameters": {"rate": 20}}, admitted) == CATALOG.resolve({"type": "particle", "parameters": {"sprite": "ember_sprite", "rate": 20}}, admitted), "named and inline effects normalize identically")
	var program := {"kind": "scenario-program-v3", "schema_version": 3, "scenario_id": "weather_demo", "entry": "opening", "nodes": [
		{"id": "opening", "kind": "line", "text": "Combat continues.", "next": "closing", "cues": [
			{"id": "early", "at": 0.25, "effect": {"preset": "ember"}, "instance_id": "near", "target": "air", "scope": "sequence", "duration": 1.0},
			{"id": "late", "at": 0.75, "effect": {"type": "particle", "parameters": {"sprite": "ember_sprite"}}, "instance_id": "far", "target": "air", "scope": "sequence", "duration": 3.0}]},
		{"id": "closing", "kind": "line", "text": "The embers may outlive a line.", "next": "done"},
		{"id": "done", "kind": "end", "outcome": "complete"}]}
	var policy := {"session_id": "first", "capabilities": {"particle": 1}, "channels": ["dialogue"], "bindings": ["air", "ember_sprite"]}
	_check(host.prepare(program, catalog, policy, {"air": 42, "ember_sprite": bindings.ember_sprite}).has("error"), "invalid game object binding refuses before invocation")
	_check(not host.invoke(program, catalog, policy, bindings).has("error"), "host invokes an admitted sequence")
	var conflict := policy.duplicate(true)
	conflict.session_id = "conflict"
	_check(host.invoke(program, catalog, conflict, bindings).get("error", {}).get("code") == "channel_conflict", "shared channel refuses second writer before starting effects")
	_check(canvas.get_child_count() == 1, "future cues do not instantiate early")
	_check(not host.tick("first", 2.0).has("error"), "large tick crosses cue and completion boundaries")
	var state := adapter.inspect()
	_check(state.size() == 1, "two definitions create separate instances and only early instance completes")
	if not state.is_empty():
		_check(is_equal_approx(float(state.values()[0].get("elapsed", -1.0)), 1.25), "late emitter receives only its actual 1.25 seconds")
	var saved := host.snapshot("first")
	host.suspend("first")
	host.tick("first", 20.0)
	_check(adapter.inspect() == state and not paused, "invocation suspension freezes owned work without pausing host")
	host.resume("first")
	host.submit("first", {"kind": "advance"})
	_check(host.view("first").get("id") == "closing" and adapter.inspect().size() == 1, "sequence-scoped effects survive utterance changes")
	var events := host.drain_events()
	var operation_id := ""
	for event: Dictionary in events:
		if event.type == "scenario/effect_started": operation_id = str(event.operation_id)
	host.submit("first", {"kind": "operation_completed", "session_id": "different", "operation_id": operation_id})
	_check(adapter.inspect().size() == 1, "cross-session result cannot complete owned effect")
	host.cancel("first", "combat_changed")
	_check(adapter.inspect().is_empty() and canvas.get_child_count() == 1 and is_instance_valid(unrelated), "cancellation releases only invocation-owned nodes")
	_check(host.leases().is_empty(), "cancellation releases channel lease")
	var resumed := HOST.new()
	var resumed_adapter := PARTICLE.new()
	resumed.register_capability("particle", PARTICLE.schema(), resumed_adapter)
	_check(not resumed.restore(program, catalog, policy, bindings, saved).has("error"), "matching content reconstructs currently active effects")
	_check(resumed_adapter.inspect().size() == 1, "restore does not replay completed effects")
	if not resumed_adapter.inspect().is_empty():
		_check(is_equal_approx(float(resumed_adapter.inspect().values()[0].get("elapsed", -1.0)), 1.25), "restored emitter resumes its own clock")
	resumed.cancel("first")
	var independent := policy.duplicate(true)
	independent.session_id = "second"
	_check(not host.invoke(program, catalog, independent, bindings).has("error"), "released channel can be leased by a new invocation")
	host.submit("second", {"kind": "advance"})
	host.submit("second", {"kind": "advance"})
	host.submit("second", {"kind": "advance"})
	var endings := 0
	for event: Dictionary in host.drain_events():
		if event.type == "scenario/ended": endings += 1
	_check(endings == 1 and host.leases().is_empty(), "outcome and terminal cleanup happen once")
	_lifecycle_audit()
	canvas.free()
	if failures.is_empty():
		print("scenario_host: %d checks passed" % checks)
		quit(0)
	else:
		for message: String in failures: push_error(message)
		quit(1)


func _check(condition: bool, message: String) -> void:
	checks += 1
	if not condition: failures.append(message)


func _audit_document(channel: String = "dialogue") -> Dictionary:
	return {"kind": "scenario-program-v3", "schema_version": 3, "scenario_id": "adapter_audit", "entry": "line", "nodes": [
		{"id": "line", "kind": "line", "text": "The host owns these operations.", "next": "done", "presentation": {"channel": channel},
			"gates": [{"event": "operation_completed:owned", "finish_on_advance": true}], "cues": [
				{"id": "owned", "at": 0.0, "effect": {"type": "audit"}, "instance_id": "owned"},
				{"id": "ambient", "at": 0.0, "effect": {"type": "audit"}, "instance_id": "ambient", "scope": "sequence"}]},
		{"id": "done", "kind": "end", "outcome": "complete"}]}


func _audit_policy(id: String, channel: String = "dialogue") -> Dictionary:
	return {"session_id": id, "capabilities": {"audit": 1}, "channels": [channel]}


func _audit_host(adapter: RefCounted) -> RefCounted:
	var host := HOST.new()
	_check(not host.register_capability("audit", {"version": 1, "finishable": true, "reconstructable": true, "parameters": {}}, adapter).has("error"), "audit capability registered")
	return host


func _lifecycle_audit() -> void:
	var catalog := {"kind": "scenario-catalog", "schema_version": 1, "catalog_id": "audit", "revision": "1", "definitions": {}}
	var adapter := AuditAdapter.new()
	var host := _audit_host(adapter)
	host.invoke(_audit_document(), catalog, _audit_policy("finish"))
	var before: Dictionary = host.snapshot("finish")
	var owned_id: String = before.state.instances.owned
	var ambient_id: String = before.state.instances.ambient
	host.submit("finish", {"kind": "advance"})
	_check(adapter.finished == [owned_id], "finish request selects its exact operation and preserves unrelated finishable work")
	_check(adapter.running.has(ambient_id) and not adapter.running.has(owned_id), "completion retires only the finished adapter operation")
	_check(host.view("finish").node_id == "line", "finishing a gate does not also skip its line")
	host.submit("finish", {"kind": "advance"})
	_check(host.view("finish").status == "ended" and adapter.running.is_empty(), "a subsequent advance completes and cleans the invocation")
	var terminal: Dictionary = host.snapshot("finish")
	var terminal_adapter := AuditAdapter.new()
	var terminal_host := _audit_host(terminal_adapter)
	_check(not terminal_host.restore(_audit_document(), catalog, _audit_policy("finish"), {}, terminal).has("error"), "terminal snapshot is admitted by Host")
	_check(terminal_host.leases().is_empty() and terminal_adapter.running.is_empty(), "terminal restore acquires no live presentation or adapter ownership")
	_check(terminal_host.drain_events().is_empty(), "terminal restore never redelivers the ending")
	var source := _audit_host(AuditAdapter.new())
	source.invoke(_audit_document(), catalog, _audit_policy("suspended"))
	source.suspend("suspended")
	var saved: Dictionary = source.snapshot("suspended")
	source.cancel("suspended")
	var restored_adapter := AuditAdapter.new()
	var restored := _audit_host(restored_adapter)
	_check(not restored.restore(_audit_document(), catalog, _audit_policy("suspended"), {}, saved).has("error"), "suspended snapshot restores active adapters")
	_check(restored_adapter.suspended.size() == 2 and restored_adapter.suspended.values() == [true, true], "restored adapters immediately receive suspension before host time can progress")
	restored.resume("suspended")
	_check(restored_adapter.suspended.values() == [false, false], "resuming restored invocation resumes both owned adapters")
	restored.cancel("suspended")
	var concurrent_adapter := AuditAdapter.new()
	var concurrent := _audit_host(concurrent_adapter)
	_check(not concurrent.invoke(_audit_document("left"), catalog, _audit_policy("left_session", "left")).has("error"), "first independent channel starts")
	_check(not concurrent.invoke(_audit_document("right"), catalog, _audit_policy("right_session", "right")).has("error"), "second independent channel runs concurrently")
	concurrent.cancel("left_session")
	_check(concurrent.leases() == {"right": "right_session"} and concurrent_adapter.running.size() == 2, "cancelling one invocation preserves the other channel and both of its operations")
	_check(concurrent.view("right_session").status == "running", "concurrent invocation remains live after unrelated cleanup")
	concurrent.cancel("right_session")
