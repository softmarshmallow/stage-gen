extends RefCounted

## Small, instance-local lookup. Hosts supply dictionaries and own language/UI.
var _sets: Dictionary = {}
var _language := "en"
var _fallback := "en"


func configure(sets: Dictionary, preferred_language: String = "en", fallback_language: String = "en") -> Array[String]:
	var errors: Array[String] = []
	if not sets.has(fallback_language) or not sets.has(preferred_language):
		return ["Text set requires the selected and fallback languages."]
	for language: Variant in sets:
		if not language is String or not sets[language] is Dictionary:
			errors.append("Each text language must name a dictionary.")
			continue
		for key: Variant in sets[language]:
			if not key is String or str(key).is_empty() or not sets[language][key] is String or str(sets[language][key]).is_empty():
				errors.append("Text keys and translations must be nonempty strings.")
	if not errors.is_empty():
		return errors
	var base: Dictionary = sets[fallback_language]
	if base.is_empty():
		return ["The fallback text set cannot be empty."]
	for language: String in sets:
		for key: String in sets[language]:
			if not base.has(key):
				errors.append("Unknown translated text key: " + key)
			elif _placeholders(sets[language][key]) != _placeholders(base[key]):
				errors.append("Translation placeholders differ for " + language + ": " + key)
	if errors.is_empty():
		_sets = sets.duplicate(true)
		_language = preferred_language
		_fallback = fallback_language
	return errors


func set_language(language: String) -> Array[String]:
	if not _sets.has(language):
		return ["Unsupported text language: " + language]
	_language = language
	return []


func get_language() -> String:
	return _language


func text(key: String, values: Dictionary = {}) -> String:
	return text_in_language(key, _language, values)


func text_in_language(key: String, language: String, values: Dictionary = {}) -> String:
	var base: Dictionary = _sets.get(_fallback, {})
	var selected: Dictionary = _sets.get(language, {})
	return str(selected.get(key, base.get(key, "[" + key + "]"))).format(values)


func missing_keys(language: String) -> Array[String]:
	var missing: Array[String] = []
	var selected: Dictionary = _sets.get(language, {})
	for key: String in _sets.get(_fallback, {}):
		if not selected.has(key): missing.append(key)
	missing.sort()
	return missing


func _placeholders(value: String) -> Array[String]:
	var pattern := RegEx.new()
	pattern.compile("\\{([a-z][a-z0-9_]*)\\}")
	var names: Array[String] = []
	for found: RegExMatch in pattern.search_all(value):
		var name := found.get_string(1)
		if name not in names: names.append(name)
	names.sort()
	return names
