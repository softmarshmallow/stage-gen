extends RefCounted
## The design contract: what a game's reward design declares, validated as a whole. A design is one
## dictionary (from a JSON file, several merged files, or design/builder.gd) with these sections:
##   items         id -> {type: currency|material, rarity, stack, name_key}
##   curves        name -> [exp to leave level 1, level 2, ...]; the last step repeats
##   measurements  name -> number|integer|boolean: what the game promises to report with a trigger
##   tables        id -> [{item, count, weight}, ...]: weighted drops
##   sources       id -> {trigger, claims: once|repeat|periodic, name_key, bundle, exp?, objectives?,
##                        objective_bonus?, period_s?, mail_on_claim?}
##   mails         id -> {sender_key, title_key, body_key, attachments, expires_days}
## Every name is a text key the host's text callable resolves; the package imposes no key scheme. Pass
## the host's key list and a key the text set lacks is a configuration error here. configure() answers
## with every problem it found and keeps the previous design on any error; nothing here reads a file,
## the clock or the engine.

const SCHEMA_VERSION := 2
const RARITIES: Array[String] = ["common", "rare", "epic", "legendary"]
const ITEM_TYPES: Array[String] = ["currency", "material"]
const MEASUREMENT_TYPES: Array[String] = ["number", "integer", "boolean"]
const CONDITION_KINDS: Array[String] = ["always", "is_true", "below", "above", "at_most", "at_least", "equals"]
const NUMERIC_KINDS: Array[String] = ["below", "above", "at_most", "at_least"]
const CLAIMS: Array[String] = ["once", "repeat", "periodic"]

var items: Dictionary = {}
var curves: Dictionary = {}
var measurements: Dictionary = {}
var tables: Dictionary = {}
var sources: Dictionary = {}
var mails: Dictionary = {}


func configure(design: Variant, text_keys: Array = []) -> Array[String]:
	var errors: Array[String] = []
	if not design is Dictionary:
		return ["The design must be a dictionary"]
	if int(design.get("schema_version", 0)) != SCHEMA_VERSION:
		return ["The design must declare schema_version %d" % SCHEMA_VERSION]
	var next_items := _read_items(design, text_keys, errors)
	var next_curves := _read_curves(design, errors)
	var next_measurements := _read_measurements(design, errors)
	var next_tables := _read_tables(design, next_items, errors)
	var next_mails := _read_mails(design, next_items, text_keys, errors)
	var next_sources := _read_sources(design, next_items, next_tables, next_curves, next_measurements, next_mails, text_keys, errors)
	if errors.is_empty():
		items = next_items
		curves = next_curves
		measurements = next_measurements
		tables = next_tables
		sources = next_sources
		mails = next_mails
	return errors


# --- lookups ------------------------------------------------------------------------------------------

func item(id: String) -> Dictionary:
	return items.get(id, {})


func curve(name: String) -> Array:
	return curves.get(name, [])


func measurement_type(name: String) -> String:
	return String(measurements.get(name, ""))


func table(id: String) -> Array:
	return tables.get(id, [])


func source(id: String) -> Dictionary:
	return sources.get(id, {})


func sources_for(trigger: String) -> Array:
	## The source ids a trigger fires, in id order.
	var out: Array = []
	for id: String in sources:
		if String(sources[id]["trigger"]) == trigger:
			out.append(id)
	out.sort()
	return out


func mail_template(id: String) -> Dictionary:
	return mails.get(id, {})


func exp_to_leave(curve_name: String, level: int) -> int:
	## EXP needed to go from `level` to the next one on a curve; past the table the last step repeats.
	var steps := curve(curve_name)
	if steps.is_empty():
		return 0
	return int(steps[clampi(level - 1, 0, steps.size() - 1)])


# --- bundles ------------------------------------------------------------------------------------------

func validate_bundle(bundle: Variant, where: String, errors: Array[String], known_items: Dictionary = items, known_tables: Dictionary = tables) -> Array:
	## A bundle is a list of {item, count} or {table, rolls}: known names, whole counts above zero.
	## Returns the clean copy.
	var clean: Array = []
	if not bundle is Array:
		errors.append("%s must be a list of {item, count} or {table, rolls}" % where)
		return clean
	for entry: Variant in bundle:
		if not entry is Dictionary:
			errors.append("%s has an entry that is not a dictionary" % where)
			continue
		if entry.has("table"):
			var table_id := String(entry["table"])
			if not known_tables.has(table_id):
				errors.append("%s names an unknown table: %s" % [where, table_id])
				continue
			var rolls: Variant = entry.get("rolls", 1)
			if not _whole(rolls) or int(rolls) <= 0:
				errors.append("%s rolls must be a whole number above zero for table %s" % [where, table_id])
				continue
			clean.append({"table": table_id, "rolls": int(rolls)})
			continue
		if not entry.has("item") or not entry.has("count"):
			errors.append("%s has an entry without item and count" % where)
			continue
		var id := String(entry["item"])
		if not known_items.has(id):
			errors.append("%s names an unknown item: %s" % [where, id])
			continue
		var count: Variant = entry["count"]
		if not _whole(count) or int(count) <= 0:
			errors.append("%s gives a count that is not a whole number above zero for %s" % [where, id])
			continue
		clean.append({"item": id, "count": int(count)})
	return clean


static func merge(bundles: Array) -> Array:
	## Sums concrete bundles by item, keeping the first-seen order. Table entries are kept as they are
	## (resolve them first with design/tables.gd).
	var order: Array[String] = []
	var totals := {}
	var unresolved: Array = []
	for bundle: Variant in bundles:
		for entry: Dictionary in bundle:
			if entry.has("table"):
				unresolved.append(entry.duplicate())
				continue
			var id := String(entry["item"])
			if not totals.has(id):
				order.append(id)
				totals[id] = 0
			totals[id] += int(entry["count"])
	var merged: Array = []
	for id: String in order:
		merged.append({"item": id, "count": int(totals[id])})
	merged.append_array(unresolved)
	return merged


static func is_concrete(bundle: Array) -> bool:
	for entry: Dictionary in bundle:
		if entry.has("table"):
			return false
	return true


# --- readers ------------------------------------------------------------------------------------------

func _read_items(design: Dictionary, text_keys: Array, errors: Array[String]) -> Dictionary:
	var out := {}
	var table: Variant = design.get("items", null)
	if not table is Dictionary or table.is_empty():
		errors.append("The design needs at least one item")
		return out
	for id: Variant in table:
		var spec: Variant = table[id]
		var where := "Item %s" % id
		if not spec is Dictionary:
			errors.append(where + " must be a dictionary")
			continue
		var type := String(spec.get("type", ""))
		var rarity := String(spec.get("rarity", ""))
		var stack: Variant = spec.get("stack", 0)
		if type not in ITEM_TYPES:
			errors.append(where + " has an unknown type: " + type)
		if rarity not in RARITIES:
			errors.append(where + " has an unknown rarity: " + rarity)
		if not _whole(stack) or int(stack) <= 0:
			errors.append(where + " needs a stack limit above zero")
		var name_key := _key(spec, "name_key", where, text_keys, errors)
		out[String(id)] = {"type": type, "rarity": rarity, "stack": int(stack), "name_key": name_key}
	return out


func _read_curves(design: Dictionary, errors: Array[String]) -> Dictionary:
	var out := {}
	var table: Variant = design.get("curves", {})
	if not table is Dictionary:
		errors.append("The design's curves must map a name to a list of steps")
		return out
	for name: Variant in table:
		var steps: Variant = table[name]
		if not steps is Array or steps.is_empty():
			errors.append("Curve %s needs at least one step" % name)
			continue
		var clean: Array = []
		var ok := true
		for step: Variant in steps:
			if not _whole(step) or int(step) <= 0:
				errors.append("Curve %s has a step that is not a whole number above zero" % name)
				ok = false
				break
			clean.append(int(step))
		if ok:
			out[String(name)] = clean
	return out


func _read_measurements(design: Dictionary, errors: Array[String]) -> Dictionary:
	var out := {}
	var table: Variant = design.get("measurements", {})
	if not table is Dictionary:
		errors.append("The design's measurements must map a name to a type")
		return out
	for name: Variant in table:
		var type := String(table[name])
		if type not in MEASUREMENT_TYPES:
			errors.append("Measurement %s has an unknown type: %s (number, integer or boolean)" % [name, type])
			continue
		out[String(name)] = type
	return out


func _read_tables(design: Dictionary, known_items: Dictionary, errors: Array[String]) -> Dictionary:
	var out := {}
	var table: Variant = design.get("tables", {})
	if not table is Dictionary:
		errors.append("The design's tables must map an id to a list of weighted entries")
		return out
	for id: Variant in table:
		var entries: Variant = table[id]
		var where := "Table %s" % id
		if not entries is Array or entries.is_empty():
			errors.append(where + " needs at least one entry")
			continue
		var clean: Array = []
		for entry: Variant in entries:
			if not entry is Dictionary or not entry.has("item") or not entry.has("count") or not entry.has("weight"):
				errors.append(where + " has an entry without item, count and weight")
				continue
			var item_id := String(entry["item"])
			if not known_items.has(item_id):
				errors.append(where + " names an unknown item: " + item_id)
				continue
			if not _whole(entry["count"]) or int(entry["count"]) <= 0:
				errors.append(where + " gives a count that is not a whole number above zero for " + item_id)
				continue
			var weight: Variant = entry["weight"]
			if not (weight is int or weight is float) or float(weight) <= 0.0:
				errors.append(where + " needs a weight above zero for " + item_id)
				continue
			clean.append({"item": item_id, "count": int(entry["count"]), "weight": float(weight)})
		if not clean.is_empty():
			out[String(id)] = clean
	return out


func _read_mails(design: Dictionary, known_items: Dictionary, text_keys: Array, errors: Array[String]) -> Dictionary:
	var out := {}
	var table: Variant = design.get("mails", {})
	if not table is Dictionary:
		errors.append("The design's mails must map an id to a template")
		return out
	for id: Variant in table:
		var spec: Variant = table[id]
		var where := "Mail %s" % id
		if not spec is Dictionary:
			errors.append(where + " must be a dictionary")
			continue
		var expires: Variant = spec.get("expires_days", null)
		if expires != null and (not _whole(expires) or int(expires) <= 0):
			errors.append(where + " expires_days must be null (keeps) or days above zero")
		out[String(id)] = {
			"sender_key": _key(spec, "sender_key", where, text_keys, errors),
			"title_key": _key(spec, "title_key", where, text_keys, errors),
			"body_key": _key(spec, "body_key", where, text_keys, errors),
			"attachments": validate_bundle(spec.get("attachments", []), where + " attachments", errors, known_items, {}),
			"expires_days": null if expires == null else int(expires),
		}
	return out


func _read_sources(design: Dictionary, known_items: Dictionary, known_tables: Dictionary, known_curves: Dictionary, known_measurements: Dictionary, known_mails: Dictionary, text_keys: Array, errors: Array[String]) -> Dictionary:
	var out := {}
	var table: Variant = design.get("sources", {})
	if not table is Dictionary:
		errors.append("The design's sources must map an id to a source")
		return out
	for id: Variant in table:
		var spec: Variant = table[id]
		var where := "Source %s" % id
		if not spec is Dictionary:
			errors.append(where + " must be a dictionary")
			continue
		var trigger := String(spec.get("trigger", ""))
		if trigger == "":
			errors.append(where + " needs a trigger")
		var claims := String(spec.get("claims", ""))
		if claims not in CLAIMS:
			errors.append(where + " has an unknown claims mode: " + claims + " (once, repeat or periodic)")
		var period: Variant = spec.get("period_s", null)
		if claims == "periodic" and (not _whole(period) or int(period) <= 0):
			errors.append(where + " is periodic and needs period_s above zero")
		var exp_spec: Variant = spec.get("exp", null)
		var exp_out := {}
		if exp_spec != null:
			if not exp_spec is Dictionary or not _whole(exp_spec.get("amount", null)) or int(exp_spec.get("amount", -1)) < 0:
				errors.append(where + " exp needs {curve, amount} with a whole amount of zero or more")
			else:
				var curve_name := String(exp_spec.get("curve", "account"))
				if not known_curves.has(curve_name):
					errors.append(where + " exp names an unknown curve: " + curve_name)
				exp_out = {"curve": curve_name, "amount": int(exp_spec["amount"])}
		var objectives: Array = []
		var raw_objectives: Variant = spec.get("objectives", [])
		if not raw_objectives is Array:
			errors.append(where + " objectives must be a list")
		else:
			for i in raw_objectives.size():
				var objective: Variant = raw_objectives[i]
				var o_where := "%s objective %d" % [where, i + 1]
				if not objective is Dictionary:
					errors.append(o_where + " must be a dictionary")
					continue
				var condition := _read_condition(objective.get("condition", null), o_where, known_measurements, errors)
				objectives.append({"name_key": _key(objective, "name_key", o_where, text_keys, errors), "condition": condition})
		var bonus := {}
		var raw_bonus: Variant = spec.get("objective_bonus", {})
		if not raw_bonus is Dictionary:
			errors.append(where + " objective_bonus must map a met count to a bundle")
		else:
			for count_key: Variant in raw_bonus:
				var count := int(String(count_key)) if String(count_key).is_valid_int() else -1
				if count < 1 or count > objectives.size():
					errors.append(where + " objective_bonus names a count it cannot reach: " + String(count_key))
					continue
				bonus[count] = validate_bundle(raw_bonus[count_key], "%s objective_bonus[%d]" % [where, count], errors, known_items, known_tables)
		var mail := String(spec.get("mail_on_claim", ""))
		if mail != "" and not known_mails.has(mail):
			errors.append(where + " names an unknown mail: " + mail)
		out[String(id)] = {
			"trigger": trigger,
			"claims": claims,
			"period_s": int(period) if claims == "periodic" and _whole(period) else 0,
			"name_key": _key(spec, "name_key", where, text_keys, errors),
			"bundle": validate_bundle(spec.get("bundle", []), where + " bundle", errors, known_items, known_tables),
			"exp": exp_out,
			"objectives": objectives,
			"objective_bonus": bonus,
			"mail_on_claim": mail,
		}
	return out


func _read_condition(condition: Variant, where: String, known_measurements: Dictionary, errors: Array[String]) -> Dictionary:
	if not condition is Dictionary:
		errors.append(where + " needs a condition")
		return {"kind": "always"}
	var kind := String(condition.get("kind", ""))
	if kind not in CONDITION_KINDS:
		errors.append(where + " has an unknown condition kind: " + kind)
		return {"kind": "always"}
	if kind == "always":
		return {"kind": "always"}
	var measure := String(condition.get("measure", ""))
	var type := String(known_measurements.get(measure, ""))
	if type == "":
		errors.append(where + " names an undeclared measurement: " + measure)
		return {"kind": "always"}
	var value: Variant = condition.get("value", null)
	if kind == "is_true":
		if type != "boolean":
			errors.append(where + " is_true needs a boolean measurement, %s is %s" % [measure, type])
		return {"kind": kind, "measure": measure}
	if kind in NUMERIC_KINDS:
		if type == "boolean":
			errors.append(where + " %s needs a numeric measurement, %s is boolean" % [kind, measure])
		if not (value is int or value is float):
			errors.append(where + " %s needs a numeric value" % kind)
			value = 0
	elif kind == "equals":
		if type == "boolean" and not value is bool:
			errors.append(where + " equals on %s needs a boolean value" % measure)
		elif type != "boolean" and not (value is int or value is float):
			errors.append(where + " equals on %s needs a numeric value" % measure)
	return {"kind": kind, "measure": measure, "value": value}


static func _key(spec: Dictionary, field: String, where: String, text_keys: Array, errors: Array[String]) -> String:
	var key := String(spec.get(field, ""))
	if key == "":
		errors.append("%s needs a %s" % [where, field])
	elif not text_keys.is_empty() and key not in text_keys:
		errors.append("%s names a text key the text set lacks: %s" % [where, key])
	return key


static func _whole(value: Variant) -> bool:
	return value is int or (value is float and value == floorf(value))
