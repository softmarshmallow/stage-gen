extends Node

## Audio Effects -> Voice Processing. Hosts route only their selected voices
## through this private bus and coordinate any separate visual treatment.
const SETTINGS := ["preset", "parent_bus", "strength", "bypass"]
const PRESET := "transmission_voice"

var _parent_bus: StringName = &"Master"
var _output_bus: StringName = &""
var _strength := 0.65
var _bypass := true
var _high_pass: AudioEffectHighPassFilter
var _distortion: AudioEffectDistortion
var _low_pass: AudioEffectLowPassFilter


## Complete replacement with defaults. Validate before allocating or changing
## a bus. The destination must already exist and precede this private bus.
func configure(settings: Dictionary = {}) -> Array[String]:
	var errors: Array[String] = []
	for key: Variant in settings:
		if key not in SETTINGS:
			errors.append("Unknown voice processing setting: " + str(key))
	if not settings.get("preset", PRESET) is String or settings.get("preset", PRESET) != PRESET:
		errors.append("Voice processing preset must be transmission_voice.")
	errors.append_array(_strength_errors(settings.get("strength", 0.65)))
	if not settings.get("bypass", true) is bool:
		errors.append("Voice processing bypass must be a boolean.")
	var parent: Variant = settings.get("parent_bus", "Master")
	if not (parent is String or parent is StringName) or str(parent).is_empty():
		errors.append("Voice processing parent_bus must name an existing audio bus.")
	else:
		var parent_index := AudioServer.get_bus_index(parent)
		var own_index := _owned_bus_index()
		if parent_index < 0:
			errors.append("Voice processing parent_bus does not exist: " + str(parent))
		elif own_index >= 0 and parent_index >= own_index:
			errors.append("Voice processing parent_bus must precede its private bus.")
	if not errors.is_empty():
		return errors
	_parent_bus = StringName(parent)
	_strength = float(settings.get("strength", 0.65))
	_bypass = settings.get("bypass", true)
	if _owned_bus_index() < 0:
		_create_bus()
	AudioServer.set_bus_send(_owned_bus_index(), _parent_bus)
	_apply_settings()
	return errors


## Bind this name to an AudioStreamPlayer or Text Reveal Audio's voice_bus.
## An unconfigured or cleaned-up processor has no route and returns empty.
func get_output_bus() -> StringName:
	return _output_bus if _owned_bus_index() >= 0 else &""


func set_bypassed(value: Variant) -> Array[String]:
	var errors: Array[String] = []
	if not value is bool:
		errors.append("Voice processing bypass must be a boolean.")
	if not errors.is_empty():
		return errors
	_bypass = value
	_apply_settings()
	return errors


func set_strength(value: Variant) -> Array[String]:
	var errors := _strength_errors(value)
	if not errors.is_empty():
		return errors
	_strength = float(value)
	_apply_settings()
	return errors


## After stopping the old player, discard the short filter history before
## replacement/replay. This preserves the route, settings, and bus identity.
func reset() -> void:
	var index := _owned_bus_index()
	if index < 0:
		return
	for effect_index in range(2, -1, -1):
		AudioServer.remove_bus_effect(index, effect_index)
	_create_effects(index)
	_apply_settings()


## Stop or reroute players before cleanup. Exit and deletion also clean up;
## repeated cleanup never removes a different processor's bus.
func cleanup() -> void:
	var index := _owned_bus_index()
	if index >= 0:
		AudioServer.remove_bus(index)
	_output_bus = &""
	_high_pass = null
	_distortion = null
	_low_pass = null


func get_state() -> Dictionary:
	var index := _owned_bus_index()
	return {
		"preset": PRESET,
		"configured": index >= 0,
		"parent_bus": _parent_bus,
		"output_bus": get_output_bus(),
		"strength": _strength,
		"bypass": _bypass,
		"processing": index >= 0 and not _bypass and _strength > 0.0,
		"high_pass_hz": _high_pass.cutoff_hz if _high_pass != null else 0.0,
		"low_pass_hz": _low_pass.cutoff_hz if _low_pass != null else 0.0,
	}


func _create_bus() -> void:
	var base := "VoiceProcessing_" + str(get_instance_id())
	var candidate := base
	var suffix := 0
	while AudioServer.get_bus_index(candidate) >= 0:
		suffix += 1
		candidate = base + "_" + str(suffix)
	var index := AudioServer.bus_count
	AudioServer.add_bus(index)
	_output_bus = StringName(candidate)
	AudioServer.set_bus_name(index, _output_bus)
	_create_effects(index)


func _create_effects(index: int) -> void:
	_high_pass = AudioEffectHighPassFilter.new()
	_high_pass.db = AudioEffectFilter.FILTER_12DB
	_high_pass.resonance = 0.5
	_distortion = AudioEffectDistortion.new()
	_distortion.mode = AudioEffectDistortion.MODE_WAVESHAPE
	_distortion.keep_hf_hz = 20000.0
	_low_pass = AudioEffectLowPassFilter.new()
	_low_pass.db = AudioEffectFilter.FILTER_12DB
	_low_pass.resonance = 0.5
	AudioServer.add_bus_effect(index, _high_pass, 0)
	AudioServer.add_bus_effect(index, _distortion, 1)
	AudioServer.add_bus_effect(index, _low_pass, 2)


func _apply_settings() -> void:
	var index := _owned_bus_index()
	if index < 0:
		return
	_high_pass.cutoff_hz = lerpf(100.0, 420.0, _strength)
	_low_pass.cutoff_hz = lerpf(9000.0, 2800.0, _strength)
	_distortion.drive = 0.12 * _strength
	_distortion.pre_gain = 0.0
	_distortion.post_gain = -2.0 * _strength
	var processing := not _bypass and _strength > 0.0
	# Zero drive still colors audio, so disable the entire chain for true dry.
	for effect_index in 3:
		AudioServer.set_bus_effect_enabled(index, effect_index, processing)


func _owned_bus_index() -> int:
	if _output_bus.is_empty():
		return -1
	var index := AudioServer.get_bus_index(_output_bus)
	if index < 0 or AudioServer.get_bus_effect_count(index) < 3:
		return -1
	if AudioServer.get_bus_effect(index, 0) != _high_pass or AudioServer.get_bus_effect(index, 1) != _distortion or AudioServer.get_bus_effect(index, 2) != _low_pass:
		return -1
	return index


static func _strength_errors(value: Variant) -> Array[String]:
	var errors: Array[String] = []
	if not (value is int or value is float) or not is_finite(float(value)):
		errors.append("Voice processing strength must be a finite number.")
	elif float(value) < 0.0 or float(value) > 1.0:
		errors.append("Voice processing strength must be between zero and one.")
	return errors


func _exit_tree() -> void:
	cleanup()


func _notification(what: int) -> void:
	if what == NOTIFICATION_PREDELETE:
		cleanup()
