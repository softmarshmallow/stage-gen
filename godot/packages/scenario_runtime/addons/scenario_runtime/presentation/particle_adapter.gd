extends RefCounted

## Scenario adapter around the existing deterministic Sprite Particle Emitter.
## A definition is data; every invocation/operation gets its own emitter instance.
const EMITTER = preload("res://addons/game_presentation/effects/particles/ambient_particles.gd")
var _emitters: Dictionary = {}


static func schema() -> Dictionary:
	return {"version": 1, "reconstructable": true, "finishable": false, "parameters": {
		"sprite": {"type": "string", "required": true},
		"seed": {"type": "integer", "default": 1, "min": 0, "max": 2147483647},
		"x": {"type": "number", "default": 0.0, "min": -32768, "max": 32768},
		"y": {"type": "number", "default": 0.0, "min": -32768, "max": 32768},
		"width": {"type": "number", "default": 320.0, "min": 0, "max": 32768},
		"height": {"type": "number", "default": 240.0, "min": 0, "max": 32768},
		"rate": {"type": "number", "default": 12.0, "min": 0, "max": 100},
		"velocity_x": {"type": "number", "default": 0.0, "min": -256, "max": 256},
		"velocity_y": {"type": "number", "default": -24.0, "min": -256, "max": 256},
		"size": {"type": "number", "default": 8.0, "min": 1, "max": 256},
	}}


func validate(event: Dictionary, bindings: Dictionary) -> Dictionary:
	var parent = bindings.get(str(event.get("target", "")))
	var settings: Dictionary = event.effect.parameters
	if typeof(parent) != TYPE_OBJECT or not is_instance_valid(parent) or not parent is Node:
		return {"error": {"code": "particle_binding", "message": "particle target must bind a host-owned Node", "path": "target"}}
	var sprites = bindings.get(str(settings.sprite))
	if not sprites is Array or sprites.is_empty():
		return {"error": {"code": "particle_binding", "message": "particle sprite binding must contain textures", "path": "sprite"}}
	for texture: Variant in sprites:
		if not texture is Texture2D: return {"error": {"code": "particle_binding", "message": "particle binding contains a non-texture", "path": "sprite"}}
	return {}


func start(event: Dictionary, bindings: Dictionary) -> Dictionary:
	var validation := validate(event, bindings)
	if validation.has("error"): return {"status": "failed", "message": validation.error.message}
	var parent: Node = bindings[str(event.target)]
	var settings: Dictionary = event.effect.parameters
	var textures: Array[Texture2D] = []
	for texture: Texture2D in bindings[str(settings.sprite)]:
		textures.append(texture)
	var id := str(event.operation_id)
	if _emitters.has(id): return {"status": "failed", "message": "operation already has an emitter"}
	var emitter := EMITTER.new()
	var velocity := Vector2(float(settings.velocity_x), float(settings.velocity_y))
	var errors := emitter.start(Rect2(float(settings.x), float(settings.y), float(settings.width), float(settings.height)), textures, {
		"seed": int(settings.seed), "rate": float(settings.rate), "max_particles": 512,
		"velocity_min": velocity, "velocity_max": velocity,
		"size_min": float(settings.size), "size_max": float(settings.size),
	})
	if not errors.is_empty():
		emitter.free()
		return {"status": "failed", "message": "; ".join(errors)}
	parent.add_child(emitter)
	_emitters[id] = emitter
	return {"status": "running"}


func advance(operation_id: String, delta: float) -> Dictionary:
	if not _emitters.has(operation_id): return {"status": "failed", "message": "particle operation is absent"}
	var emitter = _emitters[operation_id]
	if not is_instance_valid(emitter): return {"status": "failed", "message": "particle host was removed"}
	var errors: Array[String] = emitter.advance(delta)
	return {"status": "running"} if errors.is_empty() else {"status": "failed", "message": "; ".join(errors)}


func cancel(operation_id: String) -> void:
	if not _emitters.has(operation_id): return
	var emitter = _emitters[operation_id]
	if is_instance_valid(emitter):
		emitter.clear()
		if emitter.get_parent() != null: emitter.get_parent().remove_child(emitter)
		emitter.free()
	_emitters.erase(operation_id)


func restore(event: Dictionary, bindings: Dictionary, elapsed: float) -> Dictionary:
	var result := start(event, bindings)
	if result.status == "failed": return result
	var errors: Array[String] = _emitters[str(event.operation_id)].seek(elapsed)
	if not errors.is_empty():
		cancel(str(event.operation_id))
		return {"status": "failed", "message": "; ".join(errors)}
	return result


func inspect() -> Dictionary:
	var result := {}
	for id: String in _emitters:
		if is_instance_valid(_emitters[id]): result[id] = _emitters[id].get_state()
	return result
