extends RefCounted
## Conditions over a measurement bag: the objectives a source's claim scores. The design declared
## which measurements exist and their types; the game reports a bag with a trigger; a condition names
## one measurement and a comparison. A bag missing a measurement a condition needs is an error the
## game gets back, never a silent false.


static func evaluate(condition: Dictionary, measurements: Dictionary, catalog: RefCounted) -> Dictionary:
	## Returns {met: bool, errors}.
	var kind := String(condition.get("kind", "always"))
	if kind == "always":
		return {"met": true, "errors": []}
	var measure := String(condition.get("measure", ""))
	var type: String = catalog.measurement_type(measure)
	if type == "":
		return {"met": false, "errors": ["Condition names an undeclared measurement: " + measure]}
	if not measurements.has(measure):
		return {"met": false, "errors": ["The report lacks the measurement " + measure]}
	var actual: Variant = measurements[measure]
	if type == "boolean":
		if not actual is bool:
			return {"met": false, "errors": ["The measurement %s must be a boolean" % measure]}
	elif not (actual is int or actual is float):
		return {"met": false, "errors": ["The measurement %s must be a number" % measure]}
	var value: Variant = condition.get("value", null)
	var met := false
	match kind:
		"is_true":
			met = bool(actual)
		"below":
			met = float(actual) < float(value)
		"above":
			met = float(actual) > float(value)
		"at_most":
			met = float(actual) <= float(value)
		"at_least":
			met = float(actual) >= float(value)
		"equals":
			met = (bool(actual) == bool(value)) if type == "boolean" else is_equal_approx(float(actual), float(value))
	return {"met": met, "errors": []}


static func objectives_met(objectives: Array, measurements: Dictionary, catalog: RefCounted) -> Dictionary:
	## Scores every objective of a source. Returns {met: Array[bool], count: int, errors}.
	var met: Array[bool] = []
	var count := 0
	var errors: Array[String] = []
	for objective: Dictionary in objectives:
		var one := evaluate(objective["condition"], measurements, catalog)
		errors.append_array(one["errors"])
		met.append(bool(one["met"]))
		if bool(one["met"]):
			count += 1
	return {"met": met, "count": count, "errors": errors}


static func label_values(condition: Dictionary) -> Dictionary:
	## Placeholders for an objective's text: {value} as the design wrote it, whole numbers without ".0".
	var value: Variant = condition.get("value", null)
	if value == null:
		return {}
	if value is float and value == floorf(value):
		return {"value": str(int(value))}
	return {"value": str(value)}
