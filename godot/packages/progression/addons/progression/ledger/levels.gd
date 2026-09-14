extends RefCounted
## Level tracks: EXP into levels along a named curve of the design. A track is created at level 1 the
## first time it is asked for, so a game with an account track and a season track declares both as
## curves and nothing else.


static func state(doc: Dictionary, catalog: RefCounted, track: String) -> Dictionary:
	## {level, exp, to_next}; to_next is 0 when the curve is unknown.
	var t := _track(doc, track)
	return {"level": int(t["level"]), "exp": int(t["exp"]), "to_next": catalog.exp_to_leave(track, int(t["level"]))}


static func add_exp(doc: Dictionary, catalog: RefCounted, track: String, amount: int) -> Dictionary:
	## Adds EXP and rolls levels. Returns {track, level_before, exp_before, level, exp, level_ups, errors}.
	if catalog.curve(track).is_empty():
		return {"track": track, "errors": ["Unknown curve: " + track]}
	var t := _track(doc, track)
	var result := {"track": track, "level_before": int(t["level"]), "exp_before": int(t["exp"]), "level_ups": 0, "errors": []}
	var level := int(t["level"])
	var exp_now := int(t["exp"]) + maxi(amount, 0)
	var guard := 0
	while guard < 10000:
		var need: int = catalog.exp_to_leave(track, level)
		if need <= 0 or exp_now < need:
			break
		exp_now -= need
		level += 1
		result["level_ups"] += 1
		guard += 1
	t["level"] = level
	t["exp"] = exp_now
	result["level"] = level
	result["exp"] = exp_now
	return result


static func _track(doc: Dictionary, track: String) -> Dictionary:
	if not doc["tracks"].has(track):
		doc["tracks"][track] = {"level": 1, "exp": 0}
	return doc["tracks"][track]
