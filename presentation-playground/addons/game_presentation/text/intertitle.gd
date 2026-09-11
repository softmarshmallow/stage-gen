extends RefCounted

## Time-driven plain-text reveal. The host owns typography, backdrop, input,
## scene suspension, and what happens after the explicit continuation action.
const DEFAULT_CHARS_PER_SECOND := 32.0
const MIN_CHARS_PER_SECOND := 0.1
const MAX_CHARS_PER_SECOND := 240.0
const MAX_TEXT_CHARACTERS := 16384
const STATE_FIELDS := ["version", "text", "chars_per_second", "elapsed", "phase"]
const PHASES := ["idle", "revealing", "holding", "finished"]
const CHARACTER_EPSILON := 0.00000001

var _text := ""
var _chars_per_second := DEFAULT_CHARS_PER_SECOND
var _elapsed := 0.0
var _phase := "idle"


## A successful start replaces any prior cue. A refused start changes nothing.
## Count and speed use Unicode codepoints, including spaces and line breaks.
func start(text: String, settings: Dictionary = {}) -> Array[String]:
	var errors := _validate_settings(settings)
	errors.append_array(_validate_text(text))
	if not errors.is_empty():
		return errors
	_text = text
	_chars_per_second = float(settings.get("chars_per_second", DEFAULT_CHARS_PER_SECOND))
	_elapsed = 0.0
	_phase = "revealing"
	return errors


## No internal clock or automatic dismissal. Invalid deltas are ignored.
func advance(delta: float) -> void:
	if _phase != "revealing" or not is_finite(delta) or delta <= 0.0:
		return
	_elapsed = minf(_elapsed + delta, _duration())
	if _visible_characters() == _text.length():
		_elapsed = _duration()
		_phase = "holding"


## The reveal action is consumed without continuing. Only a later action while
## holding finishes the cue and returns true, once. Idle/finished return false.
func request_advance() -> bool:
	if _phase == "revealing":
		_elapsed = _duration()
		_phase = "holding"
		return false
	if _phase == "holding":
		_phase = "finished"
		return true
	return false


func sample() -> Dictionary:
	return {"text": _text, "visible_characters": _visible_characters(), "phase": _phase}


## Holding remains active until the host supplies an explicit continuation.
func is_active() -> bool:
	return _phase == "revealing" or _phase == "holding"


func clear() -> void:
	_text = ""
	_chars_per_second = DEFAULT_CHARS_PER_SECOND
	_elapsed = 0.0
	_phase = "idle"


func get_state() -> Dictionary:
	return {
		"version": 1,
		"text": _text,
		"chars_per_second": _chars_per_second,
		"elapsed": _elapsed,
		"phase": _phase,
	}


## Portable snapshots contain no UI or clock. Restore never consumes input or
## elapsed wall time. All fields are validated before any state is replaced.
func restore(state: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	for key: Variant in state:
		if key not in STATE_FIELDS:
			errors.append("Unknown Intertitle state field: " + str(key))
	for key: String in STATE_FIELDS:
		if not state.has(key):
			errors.append("Missing Intertitle state field: " + key)
	if not errors.is_empty():
		return errors
	if not _is_number(state["version"]) or float(state["version"]) != 1.0:
		errors.append("Intertitle state version must be 1.")
	if not state["text"] is String:
		errors.append("Intertitle state text must be a string.")
	if not state["phase"] is String or state["phase"] not in PHASES:
		errors.append("Invalid Intertitle state phase.")
	errors.append_array(_validate_settings({"chars_per_second": state["chars_per_second"]}))
	if not _is_number(state["elapsed"]) or not is_finite(float(state["elapsed"])):
		errors.append("Intertitle state elapsed must be a finite number.")
	if not errors.is_empty():
		return errors
	var text: String = state["text"]
	var phase: String = state["phase"]
	var elapsed := float(state["elapsed"])
	var rate := float(state["chars_per_second"])
	if phase == "idle":
		if text != "" or elapsed != 0.0 or rate != DEFAULT_CHARS_PER_SECOND:
			errors.append("Idle Intertitle state must have empty text, zero elapsed, and the default rate.")
	else:
		errors.append_array(_validate_text(text))
		var duration := float(text.length()) / rate
		if elapsed < 0.0:
			errors.append("Intertitle elapsed is outside its reveal duration.")
		elif phase == "revealing" and (elapsed > duration or _count_visible(text.length(), elapsed, rate) >= text.length()):
			errors.append("Revealing Intertitle state must still have unrevealed text.")
		elif phase in ["holding", "finished"]:
			if absf(elapsed - duration) * rate > CHARACTER_EPSILON:
				errors.append("Held or finished Intertitle state must have its complete reveal duration.")
			else:
				# JSON decimal serialization may round the saved endpoint slightly.
				elapsed = duration
	if not errors.is_empty():
		return errors
	_text = text
	_chars_per_second = rate
	_elapsed = elapsed
	_phase = phase
	return errors


func _validate_settings(settings: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	for key: Variant in settings:
		if key != "chars_per_second":
			errors.append("Unknown Intertitle setting: " + str(key))
	if settings.has("chars_per_second"):
		var rate: Variant = settings["chars_per_second"]
		if not _is_number(rate) or not is_finite(float(rate)):
			errors.append("Intertitle chars_per_second must be a finite number.")
		elif float(rate) < MIN_CHARS_PER_SECOND or float(rate) > MAX_CHARS_PER_SECOND:
			errors.append("Intertitle chars_per_second must be between 0.1 and 240.")
	return errors


func _validate_text(text: String) -> Array[String]:
	if text.is_empty() or text.length() > MAX_TEXT_CHARACTERS:
		return ["Intertitle text must contain between 1 and 16384 Unicode codepoints."]
	return []


func _is_number(value: Variant) -> bool:
	return value is int or value is float


func _duration() -> float:
	return float(_text.length()) / _chars_per_second


func _visible_characters() -> int:
	return _count_visible(_text.length(), _elapsed, _chars_per_second)


func _count_visible(length: int, elapsed: float, rate: float) -> int:
	# A tiny codepoint tolerance avoids a one-character delay from summing frames.
	return clampi(int(floor(elapsed * rate + CHARACTER_EPSILON)), 0, length)
