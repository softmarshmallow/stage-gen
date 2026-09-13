extends RefCounted

## Optional capability bridge for multiple game-owned invocations. This object
## owns only the adapters/channels explicitly registered with it, never the game.
const CATALOG = preload("../program/catalog.gd")
const PROGRAM = preload("../program/program.gd")
const SESSION = preload("../execution/session.gd")
var _types: Dictionary = {}
var _adapters: Dictionary = {}
var _sessions: Dictionary = {}
var _leases: Dictionary = {}
var _surfaces: Dictionary = {}
var _events: Array[Dictionary] = []
var _batches: Array[Dictionary] = []
var _applying := false


func register_capability(type: String, schema: Dictionary, adapter: RefCounted) -> Dictionary:
	if not _sessions.is_empty(): return _failure("capability_registry", "register capabilities before creating sessions")
	if type.is_empty() or _types.has(type): return _failure("capability_registry", "capability ID is empty or already registered")
	for method: String in ["start", "advance", "cancel"]:
		if adapter == null or not adapter.has_method(method): return _failure("capability_registry", "adapter must implement " + method)
	if bool(schema.get("finishable", false)) and not adapter.has_method("finish"):
		return _failure("capability_registry", "finishable adapter must implement finish")
	if bool(schema.get("reconstructable", false)) and not adapter.has_method("restore"):
		return _failure("capability_registry", "reconstructable adapter must implement restore")
	var candidate := _types.duplicate(true)
	candidate[type] = schema.duplicate(true)
	var admitted := CATALOG.parse(_empty_catalog(), candidate)
	if admitted.has("error"): return admitted
	_types = candidate
	_adapters[type] = adapter
	return {}


func installed_types() -> Dictionary:
	return _types.duplicate(true)


## Binding a stock surface is optional; a game can consume presentation events
## through its own typed presenter. Both paths use this same Session executor.
func bind_surface(channel: String, surface: Control) -> Dictionary:
	if channel.is_empty() or _leases.has(channel): return _failure("channel", "cannot replace an occupied presentation surface")
	for method: String in ["admit", "present", "clear"]:
		if surface == null or not surface.has_method(method): return _failure("surface", "surface must implement " + method)
	_surfaces[channel] = surface
	return {}


func invoke(document: Dictionary, catalog_document: Dictionary, policy: Dictionary, bindings: Dictionary = {}, initial_facts: Dictionary = {}) -> Dictionary:
	var admitted := prepare(document, catalog_document, policy, bindings)
	if admitted.has("error"): return admitted
	var session := SESSION.new()
	var result: Dictionary = session.start(admitted.program, admitted.catalog, policy, initial_facts)
	if result.has("error"): return result
	var id := str(policy.session_id)
	_own(id, session, policy, bindings)
	_apply(id, result)
	return {"session_id": id, "view": session.view()}


func prepare(document: Dictionary, catalog_document: Dictionary, policy: Dictionary, bindings: Dictionary) -> Dictionary:
	var id := str(policy.get("session_id", ""))
	if id.is_empty() or _sessions.has(id): return _failure("session_identity", "session ID must be nonempty and unused")
	var channels = policy.get("channels", [])
	if not channels is Array: return _failure("channel", "channels must be an array")
	var unique := {}
	for channel: Variant in channels:
		if not channel is String or channel.is_empty() or unique.has(channel): return _failure("channel", "channels must have unique nonempty IDs")
		if _leases.has(channel): return _failure("channel_conflict", "channel already has a writer: " + channel)
		unique[channel] = true
	if not policy.get("bindings", []) is Array or not policy.get("capabilities", {}) is Dictionary:
		return _failure("policy", "bindings and capabilities have invalid shapes")
	for binding: Variant in policy.get("bindings", []):
		if not binding is String or not bindings.has(binding): return _failure("binding", "host has not supplied a granted binding: " + str(binding))
	for type: String in policy.get("capabilities", {}):
		if not _types.has(type) or _types[type].version != policy.capabilities[type]: return _failure("capability", "host has not installed granted capability: " + type)
	var catalog := CATALOG.parse(catalog_document, _types)
	if catalog.has("error"): return catalog
	var program := PROGRAM.parse(document, catalog)
	if program.has("error"): return program
	for channel: String in channels:
		if _surfaces.has(channel):
			if not is_instance_valid(_surfaces[channel]): return _failure("surface", "host surface was removed: " + channel)
			var surface_admission: Dictionary = _surfaces[channel].admit(program, channel)
			if surface_admission.has("error"): return surface_admission
	var granted := {}
	for key: String in policy.get("bindings", []): granted[key] = bindings[key]
	for node: Dictionary in program.nodes.values():
		var effects: Array = [node] if node.kind == "effect" else node.get("cues", [])
		for effect: Dictionary in effects:
			var adapter: RefCounted = _adapters[effect.effect.type]
			if adapter.has_method("validate"):
				var validation: Dictionary = adapter.validate(effect, granted)
				if validation.has("error"): return validation
	return {"program": program, "catalog": catalog}


func _own(id: String, session: RefCounted, policy: Dictionary, bindings: Dictionary) -> void:
	var granted := {}
	for key: String in policy.get("bindings", []): granted[key] = bindings[key]
	_sessions[id] = {"session": session, "policy": policy.duplicate(true), "bindings": granted, "operations": {}, "active": true, "pending": []}
	for channel: String in policy.get("channels", []): _leases[channel] = id


func tick(id: String, delta: Variant, input_events: Array = []) -> Dictionary:
	if not _sessions.has(id): return _failure("session_identity", "unknown session")
	var result: Dictionary = _sessions[id].session.tick(delta, input_events)
	if result.has("error"): return result
	_apply(id, result)
	return result


func submit(id: String, action: Dictionary) -> Dictionary:
	if not _sessions.has(id): return _failure("session_identity", "unknown session")
	var result: Dictionary = _sessions[id].session.submit(action)
	if result.has("error"): return result
	_apply(id, result)
	return result


func suspend(id: String) -> Dictionary:
	if not _sessions.has(id): return _failure("session_identity", "unknown session")
	var result: Dictionary = _sessions[id].session.suspend()
	if not result.has("error"): _apply(id, result)
	return result


func resume(id: String) -> Dictionary:
	if not _sessions.has(id): return _failure("session_identity", "unknown session")
	var result: Dictionary = _sessions[id].session.resume()
	if not result.has("error"): _apply(id, result)
	return result


func cancel(id: String, reason: String = "host_cancelled") -> Dictionary:
	if not _sessions.has(id): return _failure("session_identity", "unknown session")
	var result: Dictionary = _sessions[id].session.cancel(reason)
	if not result.has("error"): _apply(id, result)
	return result


func view(id: String) -> Dictionary:
	return _sessions[id].session.view() if _sessions.has(id) else {}


func snapshot(id: String) -> Dictionary:
	return _sessions[id].session.snapshot() if _sessions.has(id) else _failure("session_identity", "unknown session")


func drain_events() -> Array[Dictionary]:
	var result := _events.duplicate(true)
	_events.clear()
	return result


func leases() -> Dictionary:
	return _leases.duplicate()


func restore(document: Dictionary, catalog_document: Dictionary, policy: Dictionary, bindings: Dictionary, saved: Dictionary) -> Dictionary:
	var admitted := prepare(document, catalog_document, policy, bindings)
	if admitted.has("error"): return admitted
	var session := SESSION.new()
	var result: Dictionary = session.restore(admitted.program, admitted.catalog, policy, saved)
	if result.has("error"): return result
	var id := str(policy.session_id)
	_own(id, session, policy, bindings)
	_apply(id, result)
	return {"session_id": id, "view": session.view()}


func _apply(id: String, result: Dictionary) -> void:
	_batches.append({"id": id, "result": result})
	if _applying: return
	_applying = true
	var count := 0
	while not _batches.is_empty() and count < 4096:
		count += 1
		var batch: Dictionary = _batches.pop_front()
		_apply_batch(batch.id, batch.result)
	if not _batches.is_empty():
		var stalled := {}
		for batch: Dictionary in _batches: stalled[batch.id] = true
		_batches.clear()
		# Adapter completions can form an otherwise invisible asynchronous loop.
		# Cancel invocations still producing work; independent sessions continue.
		for owned_id: String in stalled:
			if _sessions[owned_id].active:
				_apply_batch(owned_id, _sessions[owned_id].session.cancel("adapter_result_budget"))
	_applying = false


func _apply_batch(id: String, result: Dictionary) -> void:
	var owned: Dictionary = _sessions[id]
	var work: Array = result.get("events", []).duplicate(true)
	# Session methods return their occurrence batch; drain its mirror so callers
	# of this bridge never accidentally reapply the same occurrences.
	owned.session.drain_events()
	for event: Dictionary in work:
		_advance_to(id, event.get("clocks", {}))
		_events.append(event.duplicate(true))
		match str(event.get("type", "")):
			"scenario/presented":
				_refresh_surface(id)
			"scenario/effect_started", "scenario/effect_restored":
				var operation_id := str(event.operation_id)
				var type := str(event.effect.type)
				var adapter: RefCounted = _adapters[type]
				var response: Dictionary
				if event.type == "scenario/effect_restored":
					if not adapter.has_method("restore"):
						response = {"status": "failed", "message": "adapter cannot reconstruct effect"}
					else:
						response = adapter.restore(event, owned.bindings, float(event.get("elapsed", 0.0)))
				else:
					response = adapter.start(event, owned.bindings)
				owned.operations[operation_id] = {"adapter": adapter, "type": type, "clock": str(event.get("clock", "presentation")), "at": float(event.get("clocks", {}).get(str(event.get("clock", "presentation")), 0.0))}
				if event.type == "scenario/effect_restored" and owned.session.view().get("status") == "suspended" and adapter.has_method("suspend"):
					adapter.suspend(operation_id, true)
				_feedback(id, operation_id, response)
			"scenario/finish_requested":
				# Only an operation gate identifies work this bridge may finish.
				# Other named gates remain observable requests for the game.
				var gate := str(event.gate_event)
				if gate.begins_with("operation_completed:"):
					var state: Dictionary = owned.session.snapshot().state
					var operation_id := str(state.instances.get(gate.trim_prefix("operation_completed:"), ""))
					if owned.operations.has(operation_id):
						var operation: Dictionary = owned.operations[operation_id]
						if bool(_types[operation.type].get("finishable", false)):
							_feedback(id, operation_id, operation.adapter.finish(operation_id))
			"scenario/effect_finished", "scenario/effect_cancelled":
				_stop(id, str(event.operation_id))
			"scenario/suspended", "scenario/resumed":
				for operation_id: String in owned.operations:
					var adapter: RefCounted = owned.operations[operation_id].adapter
					if adapter.has_method("suspend"): adapter.suspend(operation_id, event.type == "scenario/suspended")
				for channel: String in owned.policy.get("channels", []):
					if _surfaces.has(channel) and is_instance_valid(_surfaces[channel]): _surfaces[channel].present(owned.session.view())
			"scenario/ended", "scenario/cancelled", "scenario/failed":
				for operation_id: String in owned.operations.keys(): _stop(id, operation_id)
				_release(id)
	_advance_to(id, result.get("state", {}).get("clocks", {}))
	# Restore intentionally emits no historical terminal occurrence. Ownership
	# still follows the validated current state, including already-ended saves.
	if owned.session.view().get("status") in ["ended", "cancelled", "failed"]:
		for operation_id: String in owned.operations.keys(): _stop(id, operation_id)
		if owned.active: _release(id)
	var count := 0
	while not owned.pending.is_empty() and count < 256:
		count += 1
		var action: Dictionary = owned.pending.pop_front()
		# A duration/scope end may have retired an adapter before its queued result.
		if not owned.operations.has(str(action.operation_id)): continue
		var feedback: Dictionary = owned.session.submit(action)
		if feedback.has("error"):
			_events.append({"type": "scenario/adapter_result_refused", "session_id": id, "error": feedback.error})
		else:
			_apply(id, feedback)
	if count == 256 and not owned.pending.is_empty():
		owned.pending.clear()
		cancel(id, "adapter_result_budget")
	_refresh_surface(id)


func _refresh_surface(id: String) -> void:
	var owned: Dictionary = _sessions[id]
	if not owned.active: return
	var view: Dictionary = owned.session.view()
	var channel := str(view.get("presentation", {}).get("channel", "dialogue"))
	if _surfaces.has(channel) and is_instance_valid(_surfaces[channel]): _surfaces[channel].present(view)


func _advance_to(id: String, clocks: Dictionary) -> void:
	var owned: Dictionary = _sessions[id]
	for operation_id: String in owned.operations.keys():
		var operation: Dictionary = owned.operations[operation_id]
		var target := float(clocks.get(operation.clock, operation.at))
		var delta := target - float(operation.at)
		if delta <= 0.0: continue
		operation.at = target
		var response: Dictionary = operation.adapter.advance(operation_id, delta)
		_feedback(id, operation_id, response)


func _feedback(id: String, operation_id: String, response: Dictionary) -> void:
	var status := str(response.get("status", "running"))
	if status not in ["completed", "failed"]: return
	_sessions[id].pending.append({"kind": "operation_completed" if status == "completed" else "operation_failed", "session_id": id, "operation_id": operation_id, "result": response.get("result", {}), "message": str(response.get("message", "adapter failed"))})


func _stop(id: String, operation_id: String) -> void:
	var operations: Dictionary = _sessions[id].operations
	if not operations.has(operation_id): return
	operations[operation_id].adapter.cancel(operation_id)
	operations.erase(operation_id)


func _release(id: String) -> void:
	_sessions[id].active = false
	for channel: String in _leases.keys():
		if _leases[channel] == id:
			if _surfaces.has(channel) and is_instance_valid(_surfaces[channel]): _surfaces[channel].clear()
			_leases.erase(channel)


static func _empty_catalog() -> Dictionary:
	return {"kind": "scenario-catalog", "schema_version": 1, "catalog_id": "installed", "revision": "1", "definitions": {}}


static func _failure(code: String, message: String) -> Dictionary:
	return {"error": {"code": code, "message": message, "path": "host"}}
