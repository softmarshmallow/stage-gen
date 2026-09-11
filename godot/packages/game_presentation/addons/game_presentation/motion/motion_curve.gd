extends RefCounted

## A normalized translation curve, shared by runtime motion and its graph.
## Spring frequency means cycles per normalized phase, not cycles per second.
## This analytic step response is a visual curve, not a physical spring solver.


static func validate(settings: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	if settings.get("curve") not in ["linear", "ease_in_out", "spring"]:
		errors.append("Motion curve must be linear, ease_in_out, or spring.")
	if not _finite_number(settings.get("frequency")) or float(settings["frequency"]) < 1.0 or float(settings["frequency"]) > 3.0:
		errors.append("Motion frequency must be finite and between 1 and 3 cycles per phase.")
	if not _finite_number(settings.get("damping_ratio")) or float(settings["damping_ratio"]) < 0.2 or float(settings["damping_ratio"]) > 1.0:
		errors.append("Motion damping_ratio must be finite and between 0.2 and 1.")
	return errors


static func sample(progress: float, settings: Dictionary) -> float:
	if not is_finite(progress):
		return 0.0
	var t := clampf(progress, 0.0, 1.0)
	if t == 0.0 or t == 1.0:
		return t
	if not validate(settings).is_empty():
		return t
	match settings["curve"]:
		"linear":
			return t
		"ease_in_out":
			return _smoothstep(t)
		"spring":
			var omega := TAU * float(settings["frequency"])
			var damping := float(settings["damping_ratio"])
			var response: float
			if damping >= 1.0:
				response = 1.0 - exp(-omega * t) * (1.0 + omega * t)
			else:
				var damped_omega := omega * sqrt(1.0 - damping * damping)
				response = 1.0 - exp(-damping * omega * t) * (cos(damped_omega * t) + damping * omega / damped_omega * sin(damped_omega * t))
			# A smooth final-quarter taper reaches exact rest with zero end slope.
			# Keep overshoot: only translation consumes this curve, never opacity.
			var settling := _smoothstep(clampf((t - 0.75) / 0.25, 0.0, 1.0))
			return lerpf(response, 1.0, settling)
	return t


static func _smoothstep(t: float) -> float:
	return t * t * (3.0 - 2.0 * t)


static func _finite_number(value: Variant) -> bool:
	return (value is float or value is int) and is_finite(float(value))
