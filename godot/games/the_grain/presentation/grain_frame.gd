extends RefCounted

## Typed game binding. Direction is a complete pair of authored frames, so
## resuming or finishing never depends on a previous scene or a story identifier.
var _operations: Dictionary = {}


func validate(event: Dictionary, bindings: Dictionary) -> Dictionary:
	var stage: Variant = bindings.get(str(event.get("target", "")))
	if typeof(stage) != TYPE_OBJECT or not is_instance_valid(stage) or not stage is Control or not stage.has_method("admit_frame") or not stage.has_method("present_frame"):
		return _failure("grain_frame requires the game's bound presentation stage")
	var errors: Array[String] = stage.admit_frame(event.effect.parameters)
	return {} if errors.is_empty() else _failure("; ".join(errors))


func start(event: Dictionary, bindings: Dictionary) -> Dictionary:
	var admission := validate(event, bindings)
	if admission.has("error"):
		return {"status": "failed", "message": admission.error.message}
	var id := str(event.operation_id)
	_operations[id] = {"stage": weakref(bindings[str(event.target)]), "parameters": event.effect.parameters.duplicate(true), "elapsed": 0.0, "suspended": false}
	return _present(id)


func advance(operation_id: String, delta: float) -> Dictionary:
	if not _operations.has(operation_id):
		return {"status": "failed", "message": "grain frame operation is absent"}
	if not is_finite(delta) or delta < 0.0:
		return {"status": "failed", "message": "grain frame time must be finite and nonnegative"}
	var operation: Dictionary = _operations[operation_id]
	if not operation.suspended:
		operation.elapsed = minf(float(operation.parameters.seconds), float(operation.elapsed) + delta)
	return _present(operation_id)


func finish(operation_id: String) -> Dictionary:
	if not _operations.has(operation_id):
		return {"status": "failed", "message": "grain frame operation is absent"}
	var operation: Dictionary = _operations[operation_id]
	operation.elapsed = float(operation.parameters.seconds)
	return _present(operation_id)


func suspend(operation_id: String, value: bool) -> void:
	if _operations.has(operation_id):
		_operations[operation_id].suspended = value


func cancel(operation_id: String) -> void:
	# Session retirement releases work; the game's final frame remains on screen.
	_operations.erase(operation_id)


func restore(event: Dictionary, bindings: Dictionary, elapsed: float) -> Dictionary:
	if not is_finite(elapsed) or elapsed < 0.0:
		return {"status": "failed", "message": "grain frame restore time is invalid"}
	var result := start(event, bindings)
	if result.status == "failed":
		return result
	_operations[str(event.operation_id)].elapsed = minf(elapsed, float(event.effect.parameters.seconds))
	return _present(str(event.operation_id))


func _present(operation_id: String) -> Dictionary:
	var operation: Dictionary = _operations[operation_id]
	var stage: Variant = operation.stage.get_ref()
	if stage == null:
		return {"status": "failed", "message": "grain frame stage was removed"}
	stage.present_frame(operation.parameters, float(operation.elapsed))
	return {"status": "completed" if float(operation.elapsed) >= float(operation.parameters.seconds) else "running"}


static func _failure(message: String) -> Dictionary:
	return {"error": {"code": "grain_frame_binding", "message": message, "path": "grain_frame"}}
