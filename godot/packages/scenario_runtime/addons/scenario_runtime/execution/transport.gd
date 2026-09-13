extends RefCounted

## Optional reading/autoplay transport. It requests an action; Session alone
## decides whether that action can progress the graph. Readiness and time are
## explicit caller inputs, so neither audio nor host gameplay is inferred.
const DEFAULTS := {"enabled": false, "delay_seconds": 3.0, "choice_delay_seconds": 5.0}
var _defaults: Dictionary = DEFAULTS.duplicate()
var _policy: Dictionary = {}
var _node_id := ""
var _enabled := false
var _elapsed := 0.0


func configure(defaults: Dictionary) -> Array[String]:
	var candidate := DEFAULTS.duplicate()
	candidate.merge(defaults, true)
	var errors := validate(candidate, false)
	if errors.is_empty():
		_defaults = candidate
		_enabled = candidate["enabled"]
		_elapsed = 0.0
	return errors


func enter(node_id: String, policy: Dictionary = {}, choices: Array = []) -> Array[String]:
	var errors := validate(policy, true, choices)
	if node_id.is_empty(): errors.append("Transport requires a stable current node ID.")
	if errors.is_empty():
		_node_id = node_id
		_policy = _defaults.duplicate()
		_policy.merge(policy, true)
		_elapsed = 0.0
	return errors


func set_enabled(enabled: bool) -> void:
	_enabled = enabled
	_elapsed = 0.0


func manual_action() -> void:
	_elapsed = 0.0


func state(blocked_reason: String = "", choice_pending: bool = false) -> Dictionary:
	var delay := float(_policy.get("choice_delay_seconds", 5.0) if choice_pending else _policy.get("delay_seconds", 3.0))
	var reason := blocked_reason
	if reason.is_empty() and not _enabled: reason = "disabled"
	if reason.is_empty() and bool(_policy.get("require_input", false)): reason = "required_input"
	var default_choice := str(_policy.get("default_choice", ""))
	if reason.is_empty() and choice_pending and default_choice.is_empty(): reason = "choice"
	return {"enabled": _enabled, "elapsed_seconds": _elapsed, "delay_seconds": delay,
		"remaining_seconds": maxf(0.0, delay - _elapsed), "blocked_reason": reason,
		"default_choice": default_choice}


func tick(delta: float, blocked_reason: String, choice_pending: bool, ready_at_tick_start: bool) -> Dictionary:
	if not is_finite(delta) or delta < 0.0: return {}
	var current := state(blocked_reason, choice_pending)
	var reason := str(current["blocked_reason"])
	if reason == "paused": return {}
	if not reason.is_empty():
		_elapsed = 0.0
		if reason == "ended": _enabled = false
		return {}
	# Time spent revealing or completing an effect is not reading time, even if
	# this frame ends with every gate satisfied.
	if not ready_at_tick_start: return {}
	_elapsed += delta
	if _elapsed < float(current["delay_seconds"]): return {}
	_elapsed = 0.0
	return {"kind": "choose", "choice_id": current["default_choice"]} if choice_pending else {"kind": "advance"}


func snapshot() -> Dictionary:
	return {"schema_version": 1, "node_id": _node_id, "enabled": _enabled, "elapsed_seconds": _elapsed}


func restore(value: Variant) -> Array[String]:
	if not value is Dictionary or value.get("schema_version") != 1 or value.get("node_id") != _node_id or not value.get("enabled") is bool:
		return ["Transport snapshot does not match the current node."]
	var elapsed: Variant = value.get("elapsed_seconds")
	if not (elapsed is float or elapsed is int) or not is_finite(float(elapsed)) or elapsed < 0.0 or elapsed > 120.0:
		return ["Transport snapshot elapsed time must be finite and between 0 and 120 seconds."]
	_enabled = value["enabled"]
	_elapsed = float(elapsed)
	return []


static func validate(policy: Dictionary, per_node: bool, choices: Array = []) -> Array[String]:
	var errors: Array[String] = []
	for key: Variant in policy:
		var value: Variant = policy[key]
		if key in ["delay_seconds", "choice_delay_seconds"]:
			if not (value is float or value is int) or not is_finite(float(value)) or value <= 0.0 or value > 120.0:
				errors.append("Transport delays must be positive and at most 120 seconds.")
		elif key in ["enabled", "require_input"]:
			if not value is bool or (per_node and key == "enabled"):
				errors.append("Transport flags must be boolean; enabled belongs to the invocation.")
		elif key == "default_choice" and per_node:
			if not value is String or not choices.has(value): errors.append("Transport default_choice must name a current choice.")
		else:
			errors.append("Unknown transport policy: " + str(key))
	return errors
