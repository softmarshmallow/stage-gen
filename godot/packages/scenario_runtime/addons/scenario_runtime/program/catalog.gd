extends RefCounted

## Installed code supplies type schemas. Content supplies named configurations.
## Catalogs cannot introduce an implementation through a downloaded function name.
const Refusal = preload("../refusal.gd")

static func parse(document: Variant, installed_types: Dictionary) -> Dictionary:
	if not (document is Dictionary):
		return _error("catalog must be a record", "catalog")
	var fields := ["kind", "schema_version", "catalog_id", "revision", "definitions"]
	if document.size() != fields.size():
		return _error("catalog fields differ from the supported schema", "catalog")
	for key: Variant in document:
		if not fields.has(key):
			return _error("unknown catalog field", "catalog." + str(key))
	if not (document.get("kind") is String) or document["kind"] != "scenario-catalog":
		return _error("expected scenario-catalog", "catalog.kind")
	var version: Variant = document.get("schema_version")
	if not (version is int or version is float) or version != 1:
		return _error("expected catalog schema_version 1", "catalog.schema_version")
	for key in ["catalog_id", "revision"]:
		if not _name(document.get(key)):
			return _error("catalog identity must be nonempty", "catalog." + key)
	if document["revision"] != document["revision"].strip_edges():
		return _error("catalog revision must not contain surrounding whitespace", "catalog.revision")
	if not (document.get("definitions", {}) is Dictionary):
		return _error("definitions must be a record", "catalog.definitions")
	var types := installed_types.duplicate(true)
	for key: Variant in types:
		if not _name(key) or not (types[key] is Dictionary):
			return _error("installed type must have a named schema", "types")
		var schema: Dictionary = types[key]
		var type_version: Variant = schema.get("version")
		if not (type_version is int or type_version is float) or not is_finite(float(type_version)) or type_version < 1 or type_version != floor(float(type_version)):
			return _error("installed capability version must be a positive integer", "types." + key)
		for flag in ["reconstructable", "finishable"]:
			if schema.has(flag) and not (schema[flag] is bool):
				return _error("installed lifecycle flag must be boolean", "types." + key + "." + flag)
		if not (schema.get("parameters", {}) is Dictionary):
			return _error("parameter schemas must be a record", "types." + key)
		for parameter: Variant in schema.get("parameters", {}):
			if not _name(parameter) or not (schema["parameters"][parameter] is Dictionary):
				return _error("parameter needs a named type schema", "types." + key)
			var failure := _validate_schema(schema["parameters"][parameter], "types." + key + ".parameters." + parameter)
			if not failure.is_empty():
				return failure
	var catalog := {"catalog_id": document["catalog_id"], "revision": document["revision"], "types": types, "definitions": {}}
	for key: Variant in document.get("definitions", {}):
		if not _name(key):
			return _error("definition must have a nonempty name", "catalog.definitions")
		var definition: Variant = document["definitions"][key]
		if not (definition is Dictionary) or definition.has("preset"):
			return _error("catalog definitions must name installed types directly", "catalog.definitions." + key)
		for field: Variant in definition:
			if not ["type", "parameters", "overrides"].has(field):
				return _error("unknown definition field", "catalog.definitions." + key + "." + str(field))
		var normalized := _inline(definition, types, "catalog.definitions." + key)
		if Refusal.is_refusal(normalized):
			return normalized
		var overrides: Variant = definition.get("overrides", [])
		if not (overrides is Array):
			return _error("overrides must list exposed parameter names", "catalog.definitions." + key)
		var unique := {}
		for parameter: Variant in overrides:
			if not _name(parameter) or unique.has(parameter) or not types[normalized["type"]].get("parameters", {}).has(parameter):
				return _error("unknown or duplicate override parameter", "catalog.definitions." + key)
			unique[parameter] = true
		normalized["overrides"] = overrides.duplicate()
		catalog["definitions"][key] = normalized
	catalog["fingerprint"] = digest(catalog)
	return catalog


## Validate unused and optional declarations too. Installation must not succeed
## merely because today's content does not exercise a malformed schema branch.
static func _validate_schema(schema: Dictionary, path: String, depth: int = 0) -> Dictionary:
	if depth > 64:
		return _error("parameter schema nesting exceeds 64 levels", path)
	for key: Variant in schema:
		if not ["type", "required", "default", "enum", "min", "max", "items", "properties", "additional_properties"].has(key):
			return _error("unknown parameter schema field", path + "." + str(key))
	if not (schema.get("type") is String) or not ["number", "integer", "string", "boolean", "array", "object", "json"].has(schema["type"]):
		return _error("parameter schema needs a supported type", path)
	for flag in ["required", "additional_properties"]:
		if schema.has(flag) and not (schema[flag] is bool):
			return _error("parameter schema flag must be boolean", path + "." + flag)
	for bound in ["min", "max"]:
		if schema.has(bound) and (not (schema[bound] is int or schema[bound] is float) or not is_finite(float(schema[bound]))):
			return _error("numeric bound must be finite", path + "." + bound)
	if schema.has("min") and schema.has("max") and schema["min"] > schema["max"]:
		return _error("minimum exceeds maximum", path)
	if schema.has("enum") and (not (schema["enum"] is Array) or not _json(schema["enum"])):
		return _error("enum must contain JSON values", path + ".enum")
	if schema.has("properties"):
		if not (schema["properties"] is Dictionary):
			return _error("object properties must be schemas", path + ".properties")
		for key: Variant in schema["properties"]:
			if not _name(key) or not (schema["properties"][key] is Dictionary):
				return _error("object property must have a named schema", path + ".properties")
			var failure := _validate_schema(schema["properties"][key], path + ".properties." + key, depth + 1)
			if not failure.is_empty(): return failure
	if schema.has("items"):
		if not (schema["items"] is Dictionary):
			return _error("array items must name a schema", path + ".items")
		var failure := _validate_schema(schema["items"], path + ".items", depth + 1)
		if not failure.is_empty(): return failure
	if schema.has("default"):
		var checked := validate_value(schema["default"], schema, path + ".default")
		if Refusal.is_refusal(checked): return checked
	return {}


static func resolve(value: Variant, catalog: Dictionary, path: String = "effect") -> Dictionary:
	if not (value is Dictionary):
		return _error("effect must be a record", path)
	for key: Variant in value:
		if not ["type", "preset", "parameters"].has(key):
			return _error("unknown effect field", path + "." + str(key))
	if value.has("type") == value.has("preset"):
		return _error("effect requires exactly one type or preset", path)
	if not value.has("preset"):
		return _inline(value, catalog["types"], path)
	if not _name(value["preset"]) or not catalog["definitions"].has(value["preset"]):
		return _error("unknown effect preset", path + ".preset")
	if value.has("type") or not (value.get("parameters", {}) is Dictionary):
		return _error("preset accepts only named parameter overrides", path)
	var definition: Dictionary = catalog["definitions"][value["preset"]]
	var parameters: Dictionary = definition["parameters"].duplicate(true)
	for key: Variant in value.get("parameters", {}):
		if not definition["overrides"].has(key):
			return _error("preset does not expose this parameter", path + ".parameters." + str(key))
		parameters[key] = value["parameters"][key]
	return _inline({"type": definition["type"], "parameters": parameters}, catalog["types"], path)


static func _inline(value: Dictionary, types: Dictionary, path: String) -> Dictionary:
	if not _name(value.get("type")) or not types.has(value["type"]):
		return _error("effect type is not installed", path + ".type")
	if not (value.get("parameters", {}) is Dictionary):
		return _error("effect parameters must be a record", path + ".parameters")
	var schema: Dictionary = types[value["type"]]
	var normalized := validate_value(value.get("parameters", {}), {"type": "object", "properties": schema.get("parameters", {})}, path + ".parameters")
	if Refusal.is_refusal(normalized):
		return normalized
	return {"type": value["type"], "version": int(schema["version"]), "parameters": normalized["value"]}


## Values are JSON-shaped; typed objects are closed unless the installed schema
## explicitly permits additional properties. Defaults are validated too.
static func validate_value(value: Variant, schema: Dictionary, path: String) -> Dictionary:
	var kind: Variant = schema.get("type")
	if not (kind is String):
		return _error("parameter schema needs a type", path)
	var valid := false
	match kind:
		"number": valid = (value is int or value is float) and is_finite(float(value))
		"integer": valid = (value is int or value is float) and is_finite(float(value)) and float(value) == floor(float(value))
		"string": valid = value is String
		"boolean": valid = value is bool
		"array": valid = value is Array
		"object": valid = value is Dictionary
		"json": valid = _json(value)
	if not valid:
		return _error("parameter must be " + kind, path)
	if schema.has("enum"):
		if not (schema["enum"] is Array) or not schema["enum"].has(value):
			return _error("parameter is outside the declared values", path)
	if kind == "number" or kind == "integer":
		for bound in ["min", "max"]:
			if schema.has(bound) and not (schema[bound] is int or schema[bound] is float):
				return _error("numeric bound must be a number", path)
		if schema.has("min") and value < schema["min"]:
			return _error("parameter is below its minimum", path)
		if schema.has("max") and value > schema["max"]:
			return _error("parameter exceeds its maximum", path)
	if kind == "object":
		var properties: Variant = schema.get("properties", {})
		if not (properties is Dictionary):
			return _error("object properties must be schemas", path)
		var result := {}
		for key: Variant in value:
			if not (key is String):
				return _error("object keys must be strings", path)
			if not properties.has(key):
				if not schema.get("additional_properties", false) or not _json(value[key]):
					return _error("unknown object parameter", path + "." + key)
				result[key] = value[key]
		for key: Variant in properties:
			if not (properties[key] is Dictionary):
				return _error("parameter schema must be a record", path + "." + str(key))
			var property: Dictionary = properties[key]
			if not value.has(key) and not property.has("default"):
				if property.get("required", false):
					return _error("required parameter is absent", path + "." + str(key))
				continue
			var checked := validate_value(value.get(key, property.get("default")), property, path + "." + str(key))
			if Refusal.is_refusal(checked):
				return checked
			result[key] = checked["value"]
		return {"value": result}
	if kind == "array":
		var result: Array = []
		var item_schema: Variant = schema.get("items", {"type": "json"})
		if not (item_schema is Dictionary):
			return _error("array items must name a schema", path)
		for index in value.size():
			var checked := validate_value(value[index], item_schema, path + "[%d]" % index)
			if Refusal.is_refusal(checked):
				return checked
			result.append(checked["value"])
		return {"value": result}
	if kind == "number":
		return {"value": float(value)}
	if kind == "integer":
		return {"value": int(value)}
	return {"value": value}


## JSON round trips preserve values but Godot parses integers as floats. Compare
## admitted JSON semantically instead of relying on Variant dictionary equality.
static func equivalent(left: Variant, right: Variant) -> bool:
	if (left is int or left is float) and (right is int or right is float):
		return float(left) == float(right)
	if typeof(left) != typeof(right):
		return false
	if left is Dictionary:
		if left.size() != right.size():
			return false
		for key: Variant in left:
			if not right.has(key) or not equivalent(left[key], right[key]):
				return false
		return true
	if left is Array:
		if left.size() != right.size():
			return false
		for index in left.size():
			if not equivalent(left[index], right[index]):
				return false
		return true
	return left == right


static func digest(value: Variant) -> String:
	return "sha256:" + JSON.stringify(_canonical(value), "", true, true).sha256_text()


static func _canonical(value: Variant) -> Variant:
	if value is float and is_finite(value) and value == floor(value) and absf(value) <= 9007199254740991.0:
		return int(value)
	if value is Array:
		var result: Array = []
		for entry: Variant in value:
			result.append(_canonical(entry))
		return result
	if value is Dictionary:
		var result := {}
		for key: Variant in value:
			result[key] = _canonical(value[key])
		return result
	return value


static func _json(value: Variant) -> bool:
	if value == null or value is bool or value is String:
		return true
	if value is int or value is float:
		return is_finite(float(value))
	if value is Array:
		for entry: Variant in value:
			if not _json(entry):
				return false
		return true
	if value is Dictionary:
		for key: Variant in value:
			if not (key is String) or not _json(value[key]):
				return false
		return true
	return false


static func _name(value: Variant) -> bool:
	return value is String and not value.is_empty()


static func _error(message: String, path: String) -> Dictionary:
	return Refusal.of("scenario/catalog", message, path)
