extends Control

## A supplied line/choice view, never a director. The game routes action_requested.
## Actor anchors, localized strings and portrait textures are independent bindings.
signal action_requested(action: Dictionary)
const ANCHOR = preload("../bindings/anchor.gd")
const DEFAULT_PROFILE := {
	"layout": "bottom", "portrait": "none", "reserve_portrait": false,
	"margin": 24.0, "padding": 20.0, "height": 180.0, "width": 440.0,
	"font_size": 24, "name_font_size": 18, "portrait_width": 120.0,
	"background": "#171b27ef", "foreground": "#f3f1eb", "bubble_offset": [0.0, -28.0],
	"overlap": "stack", "gap": 8.0,
}
var speakers: Dictionary = {}
var portraits: Dictionary = {}
var anchors: Dictionary = {}
var translations: Dictionary = {}
var profiles: Dictionary = {"bottom": DEFAULT_PROFILE.duplicate(true)}
var errors: Array[String] = []
var _view: Dictionary = {}
var _profile: Dictionary = DEFAULT_PROFILE.duplicate(true)
var _panel := Panel.new()
var _speaker := Label.new()
var _text := Label.new()
var _portrait := TextureRect.new()
var _choices := VBoxContainer.new()
var _revealed := true
var _reveal_fraction := 1.0


func _init() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_panel)
	for child: Control in [_speaker, _text, _portrait, _choices]:
		child.mouse_filter = Control.MOUSE_FILTER_IGNORE
		_panel.add_child(child)
	_text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_portrait.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_portrait.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	visible = false


func configure(profile_definitions: Dictionary = {}) -> Array[String]:
	var admitted := {"bottom": DEFAULT_PROFILE.duplicate(true)}
	var failures: Array[String] = []
	for id: String in profile_definitions:
		var result := admit_profile(profile_definitions[id])
		if result.has("error"):
			failures.append("profile %s: %s" % [id, result.error])
		else:
			admitted[id] = result
	if failures.is_empty():
		profiles = admitted
		invalidate()
	return failures


static func admit_profile(value: Variant) -> Dictionary:
	if not value is Dictionary: return {"error": "expected a profile object"}
	for key: String in value:
		if not DEFAULT_PROFILE.has(key): return {"error": "unknown field: " + key}
	var result := DEFAULT_PROFILE.duplicate(true)
	result.merge(value, true)
	if result.layout not in ["bottom", "narration", "subtitle", "bubble"]:
		return {"error": "layout must be bottom, narration, subtitle or bubble"}
	if result.portrait not in ["none", "left", "right"]:
		return {"error": "portrait must be none, left or right"}
	if not result.reserve_portrait is bool or result.overlap not in ["stack", "allow"]:
		return {"error": "invalid portrait reservation or overlap policy"}
	for key: String in ["margin", "padding", "height", "width", "font_size", "name_font_size", "portrait_width", "gap"]:
		var number = result[key]
		if not (number is float or number is int) or not is_finite(float(number)) or float(number) < 0.0 or float(number) > 8192.0:
			return {"error": "invalid finite geometry: " + key}
	if float(result.height) <= 2.0 * float(result.padding) or float(result.width) <= 2.0 * float(result.padding):
		return {"error": "surface must have positive content area"}
	for key: String in ["background", "foreground"]:
		if not result[key] is String or not Color.html_is_valid(result[key]):
			return {"error": "expected HTML color: " + key}
	var offset = result.bubble_offset
	if not offset is Array or offset.size() != 2:
		return {"error": "bubble_offset must contain two numbers"}
	for component: Variant in offset:
		if not (component is float or component is int) or not is_finite(float(component)):
			return {"error": "bubble_offset must be finite"}
	return result


func present(node: Dictionary, reveal_fraction: float = 1.0) -> Array[String]:
	if node == _view and errors.is_empty() and is_equal_approx(reveal_fraction, _reveal_fraction):
		if is_inside_tree(): update_layout()
		return []
	errors.clear()
	if node.is_empty() or str(node.get("kind", "")) not in ["line", "choice"]:
		clear()
		return []
	var selection: Dictionary = node.get("presentation", {})
	var profile_id := str(selection.get("profile", "bottom"))
	if not profiles.has(profile_id):
		return ["unknown dialogue profile: " + profile_id]
	_profile = profiles[profile_id].duplicate(true)
	_view = node.duplicate(true)
	_reveal_fraction = reveal_fraction
	_speaker.text = ""
	var speaker_id := _name(node.get("speaker"))
	var speaker: Dictionary = speakers.get(speaker_id, {})
	if not speaker_id.is_empty():
		_speaker.text = str(speaker.get("name", speaker_id))
	_text.text = _text_for(node)
	_portrait.texture = null
	if _profile.portrait != "none":
		# Explicit portrait binding overrides expression mapping; no stage lookup.
		var portrait_id := str(selection.get("portrait", speaker.get("portraits", {}).get(_name(node.get("expression"), "default"), "")))
		if not portrait_id.is_empty():
			if not portraits.get(portrait_id) is Texture2D:
				errors.append("required dialogue portrait is missing: " + portrait_id)
			else:
				_portrait.texture = portraits[portrait_id]
	_revealed = reveal_fraction >= 1.0
	_text.visible_ratio = clampf(reveal_fraction, 0.0, 1.0)
	for child: Node in _choices.get_children():
		_choices.remove_child(child)
		child.queue_free()
	for option: Dictionary in node.get("options", []):
		var button := Button.new()
		button.text = _text_for(option)
		button.disabled = node.get("status", "running") == "suspended"
		button.pressed.connect(func() -> void: action_requested.emit({"kind": "choose", "choice_id": str(option.id)}))
		_choices.add_child(button)
	var style := StyleBoxFlat.new()
	style.bg_color = Color(_profile.background)
	style.set_corner_radius_all(10)
	_panel.add_theme_stylebox_override("panel", style)
	for label: Label in [_speaker, _text]:
		label.add_theme_color_override("font_color", Color(_profile.foreground))
	_speaker.add_theme_font_size_override("font_size", int(_profile.name_font_size))
	_text.add_theme_font_size_override("font_size", int(_profile.font_size))
	visible = errors.is_empty()
	if is_inside_tree(): update_layout()
	return errors.duplicate()


func _text_for(value: Dictionary) -> String:
	if value.has("text"): return str(value.text)
	var key := str(value.get("text_key", ""))
	if key.is_empty(): return ""
	if not translations.has(key): errors.append("translation is missing: " + key)
	return str(translations.get(key, key))


## Call after host motion/camera updates. Occupied rects implement deterministic
## invocation order for bubbles sharing a canvas; the host decides that order.
func update_layout(occupied: Array[Rect2] = []) -> Rect2:
	if _view.is_empty() or not is_inside_tree(): return Rect2()
	var viewport_size := get_viewport_rect().size
	var margin := float(_profile.margin)
	var height := minf(float(_profile.height), maxf(1.0, viewport_size.y - margin * 2.0))
	var width := maxf(1.0, viewport_size.x - margin * 2.0)
	if _profile.layout == "bubble": width = minf(float(_profile.width), width)
	var pad := float(_profile.padding)
	var portrait_column := float(_profile.portrait_width) if _profile.portrait != "none" and (_portrait.texture != null or bool(_profile.reserve_portrait)) else 0.0
	var left := pad + (portrait_column + pad if portrait_column > 0.0 and _profile.portrait == "left" else 0.0)
	var text_width := maxf(1.0, width - pad * 2.0 - (portrait_column + pad if portrait_column > 0.0 else 0.0))
	_speaker.visible = not _speaker.text.is_empty()
	var name_height := 30.0 if _speaker.visible else 0.0
	var text_height := _text.get_theme_font("font").get_multiline_string_size(_text.text, HORIZONTAL_ALIGNMENT_LEFT, text_width, int(_profile.font_size)).y
	_choices.visible = _revealed and _choices.get_child_count() > 0
	var choice_height := _choices.get_combined_minimum_size().y + pad if _choices.visible else 0.0
	# Profile height is a minimum. Wrapped text and choice buttons reserve their
	# own space before positioning, including narrow world-anchored bubbles.
	height = minf(maxf(height, text_height + name_height + choice_height + pad * 2.0), maxf(1.0, viewport_size.y - margin * 2.0))
	var point := Vector2(margin, viewport_size.y - margin - height)
	if _profile.layout == "narration": point.y = (viewport_size.y - height) * 0.5
	if _profile.layout == "bubble":
		width = minf(float(_profile.width), width)
		var speaker: Dictionary = speakers.get(_name(_view.get("speaker")), {})
		var anchor_id := str(_view.get("presentation", {}).get("anchor", speaker.get("anchor", "")))
		if not anchors.has(anchor_id):
			visible = false
			return Rect2()
		var anchor := ANCHOR.sample(anchors[anchor_id], get_viewport())
		if anchor.has("error"):
			errors.assign([str(anchor.error)])
			visible = false
			return Rect2()
		visible = bool(anchor.get("visible", false)) and errors.is_empty()
		if not visible: return Rect2()
		var offset: Array = _profile.bubble_offset
		point = anchor.position + Vector2(float(offset[0]) - width * 0.5, float(offset[1]) - height)
		point = point.clamp(Vector2(margin, margin), Vector2(maxf(margin, viewport_size.x - width - margin), maxf(margin, viewport_size.y - height - margin)))
		if _profile.overlap == "stack":
			for rect: Rect2 in occupied:
				if Rect2(point, Vector2(width, height)).intersects(rect):
					point.y = maxf(margin, rect.position.y - height - float(_profile.gap))
	else:
		visible = errors.is_empty()
	_panel.position = point
	_panel.size = Vector2(width, height)
	_portrait.visible = _portrait.texture != null and _profile.portrait != "none"
	_portrait.position = Vector2(pad if _profile.portrait == "left" else width - pad - portrait_column, pad)
	_portrait.size = Vector2(portrait_column, height - pad * 2.0)
	_speaker.position = Vector2(left, pad)
	_speaker.size = Vector2(text_width, 26.0)
	_text.position = Vector2(left, pad + name_height)
	_text.size = Vector2(text_width, maxf(1.0, height - pad * 2.0 - name_height - choice_height))
	_choices.position = Vector2(left, height - pad - _choices.get_combined_minimum_size().y)
	_choices.size.x = text_width
	return Rect2(_panel.position, _panel.size)


func clear() -> void:
	_view.clear()
	visible = false


## After replacing text/portrait/profile bindings, invalidate once before the
## next present call. Moving actor anchors only need update_layout.
func invalidate() -> void:
	_view.clear()


func inspect() -> Dictionary:
	return {"visible": visible, "text": _text.text, "speaker": _speaker.text,
		"portrait_visible": _portrait.visible, "text_rect": Rect2(_text.position, _text.size),
		"rect": Rect2(_panel.position, _panel.size), "errors": errors.duplicate()}


## Validate the whole presentation closure before Host acquires the channel or
## starts effects. World anchors may intentionally disappear under a hide policy.
func admit(program: Dictionary, channel: String) -> Dictionary:
	for node: Dictionary in program.get("nodes", {}).values():
		if not node.has("presentation") or node.presentation.get("channel") != channel: continue
		var profile_id := str(node.presentation.get("profile", "bottom"))
		if not profiles.has(profile_id): return _admission_error("unknown profile: " + profile_id, node.id)
		var profile: Dictionary = profiles[profile_id]
		var speaker: Dictionary = speakers.get(_name(node.get("speaker")), {})
		if profile.portrait != "none":
			var portrait_id := str(node.presentation.get("portrait", speaker.get("portraits", {}).get(_name(node.get("expression"), "default"), "")))
			if not portrait_id.is_empty() and not portraits.get(portrait_id) is Texture2D:
				return _admission_error("required portrait is missing: " + portrait_id, node.id)
		if profile.layout == "bubble":
			var anchor_id := str(node.presentation.get("anchor", speaker.get("anchor", "")))
			if not anchors.has(anchor_id): return _admission_error("required anchor is unbound: " + anchor_id, node.id)
			if is_inside_tree():
				var projected := ANCHOR.sample(anchors[anchor_id], get_viewport())
				if projected.has("error"): return _admission_error(str(projected.error), node.id)
		for text: Dictionary in [node] + node.get("options", []):
			if text.has("text_key") and not translations.has(text.text_key):
				return _admission_error("required translation is missing: " + str(text.text_key), node.id)
	return {}


static func _name(value: Variant, fallback: String = "") -> String:
	return value if value is String else fallback


static func _admission_error(message: String, node_id: String) -> Dictionary:
	return {"error": {"code": "dialogue_binding", "message": message, "path": node_id}}
