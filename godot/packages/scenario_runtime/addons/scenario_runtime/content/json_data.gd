extends RefCounted

## JSON.parse verifies grammar. This additional scan rejects duplicate object
## keys, including differently escaped spellings, before a document is admitted.
static func parse(bytes: PackedByteArray, path: String) -> Dictionary:
	var source := bytes.get_string_from_utf8()
	if source.to_utf8_buffer() != bytes: return _error("content must be valid UTF-8", path)
	var parser := JSON.new()
	if parser.parse(source) != OK or not parser.data is Dictionary:
		return _error("expected a JSON object at line %d" % parser.get_error_line(), path)
	var containers: Array = []
	var index := 0
	while index < source.length():
		var character := source[index]
		if character == "{": containers.append({})
		elif character == "[": containers.append(null)
		elif character in ["}", "]"]: containers.pop_back()
		elif character == '"':
			var start := index
			index += 1
			while index < source.length():
				if source[index] == "\\": index += 2
				elif source[index] == '"': break
				else: index += 1
			var end := index
			var next := index + 1
			while next < source.length() and source[next] in [" ", "\t", "\n", "\r"]: next += 1
			if next < source.length() and source[next] == ":" and not containers.is_empty():
				var key: String = JSON.parse_string(source.substr(start, end - start + 1))
				var keys: Dictionary = containers.back()
				if keys.has(key): return _error("duplicate JSON field: " + key, path)
				keys[key] = true
		index += 1
	return {"value": parser.data}


static func _error(message: String, path: String) -> Dictionary:
	return {"error": {"code": "content_json", "message": message, "path": path}}
