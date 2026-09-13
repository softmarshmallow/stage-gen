extends RefCounted

## The host supplies actual objects. Content sees only a binding ID and policy.
## Positions are returned in the supplied viewport's logical canvas coordinates.
static func sample(binding: Dictionary, viewport: Viewport) -> Dictionary:
	if not is_instance_valid(viewport): return {"error": "anchor requires a live viewport"}
	var kind := str(binding.get("type", ""))
	if binding.get("lost", "hide") not in ["hide", "refuse"]: return {"error": "lost policy must be hide or refuse"}
	if binding.get("offscreen", "hide") not in ["hide", "clamp"]: return {"error": "offscreen policy must be hide or clamp"}
	var position := Vector2.ZERO
	var behind := false
	match kind:
		"screen":
			if not binding.get("position") is Vector2:
				return {"error": "screen anchor requires a Vector2 position"}
			position = binding.position
		"world_2d":
			var offset = binding.get("offset", Vector2.ZERO)
			if not offset is Vector2 or not offset.is_finite(): return {"error": "world_2d offset must be a finite Vector2"}
			var actor = binding.get("node")
			if typeof(actor) != TYPE_OBJECT or not is_instance_valid(actor) or not actor is CanvasItem or not actor.is_inside_tree():
				return _lost(binding)
			if actor.get_viewport() != viewport:
				return {"error": "anchor and dialogue must use the same viewport"}
			position = actor.get_global_transform_with_canvas() * offset
		"world_3d":
			var offset = binding.get("offset", Vector3.ZERO)
			if not offset is Vector3 or not offset.is_finite(): return {"error": "world_3d offset must be a finite Vector3"}
			var actor = binding.get("node")
			if typeof(actor) != TYPE_OBJECT or not is_instance_valid(actor) or not actor is Node3D or not actor.is_inside_tree():
				return _lost(binding)
			# Read the active camera each sample; switching cameras is a host action.
			var camera: Camera3D = viewport.get_camera_3d()
			if camera == null:
				return {"error": "world_3d anchor requires an active host camera"}
			if actor.get_viewport() != viewport:
				return {"error": "anchor and dialogue must use the same viewport"}
			var world_position: Vector3 = actor.global_transform * offset
			behind = camera.is_position_behind(world_position)
			position = camera.unproject_position(world_position)
		_:
			return {"error": "unknown anchor binding type: " + kind}
	if not position.is_finite():
		return {"visible": false, "reason": "unprojectable"}
	if behind:
		return {"visible": false, "reason": "behind_camera"}
	var bounds := viewport.get_visible_rect()
	var offscreen := not bounds.has_point(position)
	var policy := str(binding.get("offscreen", "hide"))
	if policy not in ["hide", "clamp"]:
		return {"error": "offscreen policy must be hide or clamp"}
	if offscreen and policy == "hide":
		return {"visible": false, "reason": "offscreen"}
	return {"visible": true, "position": position.clamp(bounds.position, bounds.end), "clamped": offscreen}


static func _lost(binding: Dictionary) -> Dictionary:
	if str(binding.get("lost", "hide")) == "refuse":
		return {"error": "required speaker anchor was lost"}
	return {"visible": false, "reason": "lost_anchor"}
