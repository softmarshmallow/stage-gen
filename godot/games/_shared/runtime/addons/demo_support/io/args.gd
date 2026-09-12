class_name HostArgs
extends RefCounted

## Private token parsing only. Each game declares its flags, defaults and types.
## Both --flag value and --flag=value retain their existing spelling semantics.
static func tokens(argv: PackedStringArray, accepted: Array) -> Dictionary:
	var values := {}
	var unknown := PackedStringArray()
	var index := 0
	while index < argv.size():
		var token := argv[index]
		var value := ""
		var inline := false
		var equals := token.find("=")
		if token.begins_with("--") and equals > 0:
			value = token.substr(equals + 1)
			token = token.substr(0, equals)
			inline = true
		var next_is_value := index + 1 < argv.size() and not argv[index + 1].begins_with("--")
		if not inline and next_is_value: value = argv[index + 1]
		if not accepted.has(token):
			unknown.append(token)
			index += 1
		else:
			values[token] = value
			index += 2 if not inline and next_is_value else 1
	return {"values": values, "unknown": unknown}
