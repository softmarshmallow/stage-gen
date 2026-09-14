extends RefCounted
## Weighted drop tables. The package never draws a random number itself: the host passes `draw`, a
## Callable answering a float in [0, 1), seeded however the game wants (replayable loot from a seed,
## or fresh). resolve() turns a bundle with {table, rolls} entries into a concrete {item, count} bundle.

const CATALOG := preload("catalog.gd")


static func roll(table: Array, draw: Callable) -> Dictionary:
	## One weighted pick: {item, count}. A draw outside [0, 1) is clamped.
	var total := 0.0
	for entry: Dictionary in table:
		total += float(entry["weight"])
	var point := clampf(float(draw.call()), 0.0, 0.999999) * total
	var run := 0.0
	for entry: Dictionary in table:
		run += float(entry["weight"])
		if point < run:
			return {"item": String(entry["item"]), "count": int(entry["count"])}
	var last: Dictionary = table[table.size() - 1]
	return {"item": String(last["item"]), "count": int(last["count"])}


static func resolve(bundle: Array, catalog: RefCounted, draw: Callable) -> Dictionary:
	## Returns {bundle: concrete merged bundle, errors}. A table entry with no valid draw is an error,
	## never a silent skip.
	var errors: Array[String] = []
	var parts: Array = []
	for entry: Dictionary in bundle:
		if not entry.has("table"):
			parts.append([entry])
			continue
		var table: Array = catalog.table(String(entry["table"]))
		if table.is_empty():
			errors.append("Unknown table: " + String(entry["table"]))
			continue
		if not draw.is_valid():
			errors.append("Table %s needs a draw callable to roll" % String(entry["table"]))
			continue
		for i in int(entry.get("rolls", 1)):
			parts.append([roll(table, draw)])
	return {"bundle": CATALOG.merge(parts), "errors": errors}
