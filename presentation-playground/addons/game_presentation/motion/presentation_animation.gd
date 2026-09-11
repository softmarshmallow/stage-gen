extends RefCounted

## Target-neutral scalar animation shared by actor focus and individual manpu.
## Callers own target identity and clocks; this sampler owns the common track
## schema, easing, interruption continuity, and channel bounds.

# Both spatial offsets are fractions of the original target height. This keeps
# authored motion stable when sprites have different canvas aspect ratios.
const CHANNEL_DEFAULTS := {"offset_x_ratio": 0.0, "offset_y_ratio": 0.0, "scale": 1.0, "opacity": 1.0, "brightness": 1.0, "rotation_degrees": 0.0}
const MIN_SCALE := 0.001
const ROOT_FIELDS := ["version", "presets"]
const PRESET_FIELDS := ["id", "label", "duration_seconds"]


## An omitted from_sample starts at the authored first sample. This is crucial
## for introductions such as opacity 0 -> 1. Retargeting passes a current sample.
static func sample(tracks: Dictionary, elapsed: float, duration_seconds: float, from_sample: Dictionary = {}, interpolation: String = "smooth") -> Dictionary:
	var normalized_time := 1.0 if duration_seconds <= 0.0 else clampf(elapsed / duration_seconds, 0.0, 1.0)
	var target := evaluate(tracks, normalized_time, interpolation)
	if normalized_time >= 1.0 or interpolation == "step":
		return target
	var start := evaluate(tracks, 0.0)
	var from: Dictionary = start if from_sample.is_empty() else CHANNEL_DEFAULTS.duplicate()
	if not from_sample.is_empty():
		# Missing channels remain neutral. Renderer metadata never enters the
		# numeric sampler even when a controller passes its complete result.
		for channel: String in CHANNEL_DEFAULTS:
			if from_sample.has(channel):
				from[channel] = from_sample[channel]
	if normalized_time <= 0.0:
		return from.duplicate()
	var residual := 1.0 - _smoothstep(normalized_time)
	for channel: String in CHANNEL_DEFAULTS:
		target[channel] = float(target[channel]) + (float(from[channel]) - float(start[channel])) * residual
	# Interrupted custom tracks can overshoot despite valid endpoints. Preserve
	# exact valid endpoints while bounding their intermediate residual samples.
	target["opacity"] = clampf(float(target["opacity"]), 0.0, 1.0)
	target["brightness"] = clampf(float(target["brightness"]), 0.0, 1.0)
	target["scale"] = maxf(MIN_SCALE, float(target["scale"]))
	return target


static func evaluate(tracks: Dictionary, normalized_time: float, interpolation: String = "smooth") -> Dictionary:
	var result := CHANNEL_DEFAULTS.duplicate()
	for channel: String in tracks:
		result[channel] = track_value(tracks[channel], normalized_time, interpolation)
	return result


static func track_value(keyframes: Array, normalized_time: float, interpolation: String = "smooth") -> float:
	if normalized_time <= 0.0:
		return float(keyframes[0][1])
	if normalized_time >= 1.0:
		return float(keyframes[-1][1])
	if interpolation == "step":
		for index in range(1, keyframes.size()):
			if normalized_time + 0.000000000001 < float(keyframes[index][0]):
				return float(keyframes[index - 1][1])
		return float(keyframes[-1][1])
	for index in range(1, keyframes.size()):
		var right: Array = keyframes[index]
		if normalized_time <= float(right[0]):
			var left: Array = keyframes[index - 1]
			var interval := (normalized_time - float(left[0])) / (float(right[0]) - float(left[0]))
			return lerpf(float(left[1]), float(right[1]), _smoothstep(interval))
	return float(keyframes[-1][1])


static func _smoothstep(value: float) -> float:
	var t := clampf(value, 0.0, 1.0)
	return t * t * (3.0 - 2.0 * t)


static func valid_id(value: Variant) -> bool:
	return value is String and not value.is_empty() and value == value.to_lower() and value.is_valid_identifier()


static func finite_number(value: Variant) -> bool:
	return (value is float or value is int) and is_finite(float(value))


static func validate_catalog(value: Variant, track_groups: Array[String], catalog_label: String = "Presentation animation", allow_rotation: bool = false) -> Dictionary:
	var errors: Array[String] = []
	var validated := {}
	var order: Array[String] = []
	var result := {"errors": errors, "presets": validated, "order": order}
	if not (value is Dictionary):
		errors.append("The " + catalog_label + " catalog must be an object.")
		return result
	for field: String in value:
		if not ROOT_FIELDS.has(field):
			errors.append("Unknown " + catalog_label + " catalog field: " + field)
	if not finite_number(value.get("version")) or float(value["version"]) != 1.0:
		errors.append("The " + catalog_label + " catalog must have version 1.")
	var presets: Variant = value.get("presets")
	if not (presets is Array) or presets.is_empty():
		errors.append("The " + catalog_label + " catalog must have a nonempty presets array.")
		return result
	for index in presets.size():
		var preset: Variant = presets[index]
		var context := "%s preset %d" % [catalog_label, index]
		if not (preset is Dictionary):
			errors.append(context + " must be an object.")
			continue
		for field: String in preset:
			if not PRESET_FIELDS.has(field) and not track_groups.has(field):
				errors.append(context + " has an unknown field: " + field)
		var id: Variant = preset.get("id")
		if not valid_id(id):
			errors.append(context + " must have a lower_snake_case id.")
		elif validated.has(id):
			errors.append("Duplicate " + catalog_label + " preset id: " + String(id))
		var label: Variant = preset.get("label")
		if not (label is String) or label.strip_edges().is_empty():
			errors.append(context + " must have a label.")
		var duration: Variant = preset.get("duration_seconds")
		if not finite_number(duration) or float(duration) < 0.0 or float(duration) > 2.0:
			errors.append(context + " duration_seconds must be finite and between 0 and 2.")
		for group: String in track_groups:
			validate_tracks(preset.get(group), context + "." + group, errors, allow_rotation)
		if valid_id(id) and not validated.has(id):
			validated[id] = preset.duplicate(true)
			order.append(id)
	return result


static func validate_tracks(value: Variant, context: String, errors: Array[String], allow_rotation: bool = false) -> void:
	if not (value is Dictionary):
		errors.append(context + " must be a track object.")
		return
	for channel: String in value:
		if not CHANNEL_DEFAULTS.has(channel) or (channel == "rotation_degrees" and not allow_rotation):
			errors.append(context + " has an unknown channel: " + channel)
			continue
		var frames: Variant = value[channel]
		if not (frames is Array) or frames.size() < 2:
			errors.append(context + "." + channel + " must have at least two keyframes.")
			continue
		var previous_time := -1.0
		for index in frames.size():
			var frame: Variant = frames[index]
			var frame_context := "%s.%s[%d]" % [context, channel, index]
			if not (frame is Array) or frame.size() != 2 or not finite_number(frame[0]) or not finite_number(frame[1]):
				errors.append(frame_context + " must be a finite [normalized_time, value] pair.")
				continue
			var time := float(frame[0])
			var amount := float(frame[1])
			if time < 0.0 or time > 1.0 or time <= previous_time:
				errors.append(frame_context + " time must increase strictly within 0 to 1.")
			if (index == 0 and time != 0.0) or (index == frames.size() - 1 and time != 1.0):
				errors.append(context + "." + channel + " must start at time 0 and end at time 1.")
			if channel in ["opacity", "brightness"] and (amount < 0.0 or amount > 1.0):
				errors.append(frame_context + " must have a value between 0 and 1.")
			elif channel == "scale" and amount < MIN_SCALE:
				errors.append(frame_context + " scale must be at least 0.001.")
			previous_time = time
