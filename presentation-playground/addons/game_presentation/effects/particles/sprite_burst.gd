extends Control

## Finite, seeded Radial Sprite Bursts. The host supplies time, world framing,
## textures and layer placement. No scene processing or particle respawning.
const DEFAULTS := {
	"count": 16, "duration": 1.2, "spread_degrees": 360.0,
	"angle_degrees": -90.0, "start_radius": 12.0, "distance": 190.0,
	"sprite_size": 28.0, "pop_seconds": 0.10, "fade_start": 0.55,
	"spin_degrees": 120.0, "seed": 0,
}
const MAX_EVENTS := 24
const MAX_COUNT := 128
const MAX_PARTICLES := 1024
const MAX_TEXTURES := 64
var _events: Array[Dictionary] = []
var _next_id := 1
var _camera := Transform2D.IDENTITY


func _init() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	focus_mode = Control.FOCUS_NONE
	visible = false


## Options and sprite selection are captured per event. Texture resources are
## retained by reference; hosts must not edit their pixels while in use.
func emit_burst(origin: Vector2, textures: Array[Texture2D], options: Dictionary = {}) -> Dictionary:
	var errors := _validate_options(options)
	if not origin.is_finite():
		errors.append("Radial Sprite Burst origin must be finite.")
	if textures.is_empty() or textures.size() > MAX_TEXTURES:
		errors.append("Radial Sprite Burst requires between 1 and 64 textures.")
	for texture: Texture2D in textures:
		if texture == null or texture.get_width() <= 0 or texture.get_height() <= 0:
			errors.append("Radial Sprite Burst textures must have positive dimensions.")
	if not errors.is_empty():
		return {"instance_id": -1, "errors": errors}
	var settings := DEFAULTS.duplicate()
	settings.merge(options, true)
	var count := int(settings["count"])
	var active_count := 0
	for event: Dictionary in _events:
		active_count += int(event["settings"]["count"])
	if _events.size() >= MAX_EVENTS or active_count + count > MAX_PARTICLES:
		errors.append("Radial Sprite Burst capacity exceeded (24 events / 1024 particles).")
		return {"instance_id": -1, "errors": errors}
	var rng := RandomNumberGenerator.new()
	rng.seed = int(settings["seed"])
	var particles: Array[Dictionary] = []
	for index in count:
		# Stratified directions make small counts feel like a group; every random
		# draw is independent of texture count, so swapping art preserves motion.
		var sector := (float(index) + rng.randf_range(0.08, 0.92)) / float(count) - 0.5
		var direction := Vector2.from_angle(deg_to_rad(float(settings["angle_degrees"]) + sector * float(settings["spread_degrees"])))
		particles.append({
			"direction": direction,
			"radius": float(settings["start_radius"]) * rng.randf_range(0.65, 1.35),
			"distance": float(settings["distance"]) * rng.randf_range(0.72, 1.20),
			"sprite_size": float(settings["sprite_size"]) * rng.randf_range(0.70, 1.25),
			"rotation": rng.randf_range(-PI, PI),
			"spin": deg_to_rad(float(settings["spin_degrees"])) * rng.randf_range(-1.0, 1.0),
			"texture_index": mini(int(floor(rng.randf() * textures.size())), textures.size() - 1),
		})
	var instance_id := _next_id
	_next_id += 1
	_events.append({
		"instance_id": instance_id, "origin": origin, "elapsed": 0.0,
		"settings": settings, "textures": textures.duplicate(), "particles": particles,
	})
	_refresh()
	return {"instance_id": instance_id, "errors": errors}


## Pause by withholding advance. Oversized steps expire events without loops.
func advance(delta: float) -> Array[String]:
	if not is_finite(delta) or delta < 0.0:
		return ["Radial Sprite Burst delta must be finite and nonnegative."]
	if delta == 0.0:
		return []
	for index in range(_events.size() - 1, -1, -1):
		var event := _events[index]
		if delta >= float(event["settings"]["duration"]) - float(event["elapsed"]):
			_events.remove_at(index)
		else:
			event["elapsed"] = float(event["elapsed"]) + delta
	_refresh()
	return []


## World-to-parent framing; the layer itself should have an identity transform.
## Applying the final camera moves the whole burst, including its sprite sizes.
func present(camera: Transform2D) -> Array[String]:
	if not camera.x.is_finite() or not camera.y.is_finite() or not camera.origin.is_finite():
		return ["Radial Sprite Burst camera must be finite."]
	if camera.x.y != 0.0 or camera.y.x != 0.0 or camera.x.x <= 0.0 or camera.y.y <= 0.0:
		return ["Radial Sprite Burst camera requires positive axis-aligned scale and translation."]
	var determinant := camera.determinant()
	if not is_finite(determinant) or determinant <= 0.0:
		return ["Radial Sprite Burst camera must be invertible within canvas precision."]
	var inverse := camera.affine_inverse()
	if not inverse.x.is_finite() or not inverse.y.is_finite() or not inverse.origin.is_finite():
		return ["Radial Sprite Burst camera must have a finite inverse."]
	_camera = camera
	queue_redraw()
	return []


func cancel(instance_id: int) -> void:
	for index in range(_events.size() - 1, -1, -1):
		if int(_events[index]["instance_id"]) == instance_id:
			_events.remove_at(index)
			_refresh()
			return


## Clear releases event textures and resets framing. IDs are never reused.
func clear() -> void:
	_events.clear()
	_camera = Transform2D.IDENTITY
	_refresh()


## Read-only copies: logical-world samples, not a persistence/save format.
## No texture resources or pixels are exposed through this inspection surface.
func get_state() -> Array[Dictionary]:
	var state: Array[Dictionary] = []
	for event: Dictionary in _events:
		var samples: Array[Dictionary] = []
		for particle: Dictionary in event["particles"]:
			samples.append(_sample(event, particle))
		state.append({
			"instance_id": event["instance_id"], "origin": event["origin"],
			"elapsed": event["elapsed"], "seed": event["settings"]["seed"],
			"settings": event["settings"].duplicate(),
			"texture_count": event["textures"].size(), "particles": samples,
		})
	return state


func _sample(event: Dictionary, particle: Dictionary) -> Dictionary:
	var settings: Dictionary = event["settings"]
	var elapsed := float(event["elapsed"])
	var progress := clampf(elapsed / float(settings["duration"]), 0.0, 1.0)
	var travel := 1.0 - pow(1.0 - progress, 3.0)
	var pop := 1.0
	if float(settings["pop_seconds"]) > 0.0:
		pop = sin(clampf(elapsed / float(settings["pop_seconds"]), 0.0, 1.0) * PI * 0.5)
	var fade := clampf((progress - float(settings["fade_start"])) / (1.0 - float(settings["fade_start"])), 0.0, 1.0)
	var alpha := 1.0 - fade * fade * (3.0 - 2.0 * fade)
	var texture: Texture2D = event["textures"][int(particle["texture_index"])]
	var texture_size := texture.get_size()
	var sprite_size := float(particle["sprite_size"])
	return {
		"position": event["origin"] + particle["direction"] * (float(particle["radius"]) + float(particle["distance"]) * travel),
		"rotation": float(particle["rotation"]) + float(particle["spin"]) * travel,
		"scale": pop, "sprite_size": sprite_size,
		"size": texture_size / maxf(texture_size.x, texture_size.y) * sprite_size * pop,
		"alpha": alpha, "texture_index": particle["texture_index"],
	}


func _draw() -> void:
	for event: Dictionary in _events:
		for particle: Dictionary in event["particles"]:
			var sample := _sample(event, particle)
			if float(sample["scale"]) <= 0.0 or float(sample["alpha"]) <= 0.0:
				continue
			var sprite_transform := Transform2D(float(sample["rotation"]), sample["position"])
			draw_set_transform_matrix(_camera * sprite_transform)
			var sprite_size: Vector2 = sample["size"]
			draw_texture_rect(event["textures"][int(sample["texture_index"])], Rect2(-sprite_size * 0.5, sprite_size), false, Color(1.0, 1.0, 1.0, float(sample["alpha"])))
	draw_set_transform_matrix(Transform2D.IDENTITY)


func _refresh() -> void:
	visible = not _events.is_empty()
	queue_redraw()


static func _validate_options(options: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	for key: Variant in options:
		if not key is String or not DEFAULTS.has(key):
			errors.append("Unknown Radial Sprite Burst setting: " + str(key))
			continue
		var value: Variant = options[key]
		match key:
			"count":
				if not value is int or value < 1 or value > MAX_COUNT:
					errors.append("Radial Sprite Burst count must be an integer in [1, 128].")
			"seed":
				if not value is int:
					errors.append("Radial Sprite Burst seed must be an integer.")
			"duration":
				if not _between(value, 0.05, 30.0):
					errors.append("Radial Sprite Burst duration must be in [0.05, 30] seconds.")
			"spread_degrees":
				if not _between(value, 0.0, 360.0):
					errors.append("Radial Sprite Burst spread_degrees must be in [0, 360].")
			"angle_degrees", "spin_degrees":
				if not _between(value, -36000.0, 36000.0):
					errors.append("Radial Sprite Burst angles must be in [-36000, 36000] degrees.")
			"start_radius", "distance":
				if not _between(value, 0.0, 8192.0):
					errors.append("Radial Sprite Burst radii/distances must be in [0, 8192] logical pixels.")
			"sprite_size":
				if not _between(value, 0.1, 2048.0):
					errors.append("Radial Sprite Burst sprite_size must be in [0.1, 2048] logical pixels.")
			"pop_seconds":
				if not _between(value, 0.0, 30.0):
					errors.append("Radial Sprite Burst pop_seconds must be in [0, 30].")
			"fade_start":
				if not _between(value, 0.0, 0.99):
					errors.append("Radial Sprite Burst fade_start must be in [0, 0.99].")
	if errors.is_empty() and float(options.get("pop_seconds", DEFAULTS["pop_seconds"])) > float(options.get("duration", DEFAULTS["duration"])):
		errors.append("Radial Sprite Burst pop_seconds must not exceed duration.")
	return errors


static func _between(value: Variant, lower: float, upper: float) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and float(value) >= lower and float(value) <= upper
